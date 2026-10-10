"""Mutationsanalyse: Erkennen die Testbenches absichtlich fehlerhafte Entwürfe?

Aus den Quellen unter src/ werden deterministisch kleine Fehlervarianten
(Mutanten) erzeugt, je Mutant genau eine Änderung. Jeder Mutant wird mit
allen Testbenches simuliert. Erkennt die Testsuite ihn (Simulation scheitert),
gilt er als „getötet“; besteht sie trotzdem, hat sie eine Lücke. Mutanten,
die schon nicht kompilieren, zählen nicht.

Anlass: Im Benchmark bestand die eigene Testbench des MAS, obwohl die Ampel
dauerhaft auf Grün stand – genau einen solchen Fehler bildet ein Mutant nach.

Herkunft (siehe docs/doku.html, Abschnitt 16): Mutationstesten nach DeMillo,
Lipton und Sayward (1978) sowie Jia und Harman (2011, Übersicht);
Validierung LLM-erzeugter Testbenches an absichtlich fehlerhaften
RTL-Varianten nach CorrectBench (arXiv:2411.08510); Fehlererkennung an
Mutanten als Gütemaß nach PRO-V (arXiv:2506.12200). Eigener Beitrag:
deterministische VHDL-Mutationsoperatoren statt LLM-erzeugter Varianten,
Einbindung als Gate mit genau einem Nachbesserungsversuch.

Grenze: Äquivalente Mutanten (Änderung ohne beobachtbare Wirkung) können
nicht getötet werden; deshalb ist die Schwelle kleiner als 1 und das Gate
blockiert nach einem Nachbesserungsversuch nicht mehr.
"""
from __future__ import annotations

import random
import re
import shutil
import tempfile
from dataclasses import dataclass, asdict
from pathlib import Path

DEFAULT_MAX_MUTANTS = 10
_INVALID_PREFIXES = ("GHDL analysis failed", "GHDL elaboration failed", "No VHDL files", "No src directory")


@dataclass(frozen=True)
class Mutant:
    file: str        # relativer Pfad, z. B. src/control.vhd
    line: int        # 1-basiert
    operator: str
    before: str
    after: str
    text: str        # vollständiger mutierter Dateiinhalt

    def describe(self) -> str:
        return f"{self.file}:{self.line} [{self.operator}] '{self.before.strip()}' -> '{self.after.strip()}'"


def _code_part(line: str) -> tuple[str, str]:
    """Trennt Code und Kommentar einer Zeile (Kommentare werden nie mutiert)."""
    idx = line.find("--")
    return (line, "") if idx < 0 else (line[:idx], line[idx:])


def _body_start(lines: list[str]) -> int:
    """Index der ersten Zeile nach 'architecture ... is' (Deklarationen bleiben unangetastet)."""
    for i, line in enumerate(lines):
        if re.search(r"\barchitecture\s+\w+\s+of\s+\w+\s+is\b", _code_part(line)[0], re.IGNORECASE):
            return i + 1
    return len(lines)


_CLOCK_EDGE = re.compile(r"rising_edge|falling_edge|'event", re.IGNORECASE)
_COND = re.compile(r"\b(if|elsif)\b(\s+)(.+?)(\s+)\bthen\b", re.IGNORECASE)

# (Name, Funktion: Codezeile -> mutierte Codezeile oder None)


def _flip_bit(code: str) -> str | None:
    match = re.search(r"(<=\s*)'([01])'", code)
    if not match:
        return None
    flipped = "1" if match.group(2) == "0" else "0"
    return code[:match.start()] + f"{match.group(1)}'{flipped}'" + code[match.end():]


def _negate_condition(code: str) -> str | None:
    match = _COND.search(code)
    if not match or _CLOCK_EDGE.search(match.group(3)):
        return None
    return code[:match.start(3)] + f"not ({match.group(3)})" + code[match.end(3):]


def _swap_relation(code: str) -> str | None:
    match = _COND.search(code)
    if not match or _CLOCK_EDGE.search(match.group(3)):
        return None
    condition = match.group(3)
    swapped = re.sub(r"(?<![/<>=])=(?!=|>)", "/=", condition, count=1)
    if swapped == condition:
        swapped = condition.replace("/=", "=", 1)
    if swapped == condition:
        return None
    return code[:match.start(3)] + swapped + code[match.end(3):]


def _change_constant(code: str) -> str | None:
    if "<=" not in code or re.search(r"\b(downto|to)\b", code, re.IGNORECASE):
        return None
    match = re.search(r"([+-])\s*1\b", code)
    if not match:
        return None
    return code[:match.start()] + f"{match.group(1)} 2" + code[match.end():]


def _drop_transition(code: str) -> str | None:
    """Zustandsübergang entfernen: 'state <= X;' -> 'null;' (nur sequentielle Zuweisung)."""
    if not re.match(r"\s*\w*(state|st)\w*\s*<=\s*\w+\s*;", code, re.IGNORECASE):
        return None
    indent = re.match(r"\s*", code).group(0)
    return f"{indent}null;\n" if code.endswith("\n") else f"{indent}null;"


OPERATORS = {
    "bit_flip": _flip_bit,
    "negate_condition": _negate_condition,
    "swap_relation": _swap_relation,
    "change_constant": _change_constant,
    "drop_transition": _drop_transition,
}


def generate_mutants(sources: dict[str, str], max_mutants: int = DEFAULT_MAX_MUTANTS, seed: int = 0) -> list[Mutant]:
    """Deterministische Auswahl, reihum über Operatoren verteilt (Vielfalt vor Menge)."""
    by_operator: dict[str, list[Mutant]] = {name: [] for name in OPERATORS}
    for rel, text in sorted(sources.items()):
        lines = text.splitlines(keepends=True)
        for index in range(_body_start(lines), len(lines)):
            code, comment = _code_part(lines[index])
            for name, operator in OPERATORS.items():
                mutated = operator(code)
                if mutated is None or mutated == code:
                    continue
                new_lines = list(lines)
                new_lines[index] = mutated + comment if not mutated.endswith("\n") or not comment else mutated.rstrip("\n") + comment
                if not new_lines[index].endswith("\n") and lines[index].endswith("\n"):
                    new_lines[index] += "\n"
                by_operator[name].append(Mutant(rel, index + 1, name, code, mutated, "".join(new_lines)))
    rng = random.Random(seed)
    for candidates in by_operator.values():
        rng.shuffle(candidates)
    selected: list[Mutant] = []
    while len(selected) < max_mutants and any(by_operator.values()):
        for name in OPERATORS:
            if by_operator[name] and len(selected) < max_mutants:
                selected.append(by_operator[name].pop())
    return selected


def run_mutation_analysis(workspace: str, validator, max_mutants: int = DEFAULT_MAX_MUTANTS, seed: int = 0) -> dict:
    """Simuliert jeden Mutanten mit der vollständigen Testsuite (src/ + tests/).

    Liefert score = getötet / (getötet + überlebt); None, wenn kein gültiger Mutant entstand.
    """
    ws = Path(workspace)
    sources = {
        f"src/{path.name}": path.read_text(errors="replace")
        for path in sorted((ws / "src").glob("*.vhd"))
        if not path.stem.endswith("_tb")
    }
    mutants = generate_mutants(sources, max_mutants=max_mutants, seed=seed)
    killed, survived, invalid = [], [], []
    for mutant in mutants:
        with tempfile.TemporaryDirectory(prefix="mutant_") as tmp:
            for folder in ("src", "tests"):
                if (ws / folder).is_dir():
                    shutil.copytree(ws / folder, Path(tmp) / folder)
            (Path(tmp) / mutant.file).write_text(mutant.text, encoding="utf-8")
            result = validator.validate(tmp)
        entry = {**{k: v for k, v in asdict(mutant).items() if k != "text"}, "description": mutant.describe(),
                 "module": Path(mutant.file).stem}
        if result.passed:
            survived.append(entry)
        elif str(result.message).startswith(_INVALID_PREFIXES):
            invalid.append(entry)
        else:
            killed.append({**entry, "detected_by": str(result.message)[:160]})
    valid = len(killed) + len(survived)
    return {
        "mutants": len(mutants),
        "killed": killed,
        "survived": survived,
        "invalid": invalid,
        "score": round(len(killed) / valid, 3) if valid else None,
    }
