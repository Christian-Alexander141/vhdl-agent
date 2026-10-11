"""Einzelanforderungen: vom Prompt über den Plan bis zur Abschlussprüfung.

Lauf gray-countdown (2026-10-10): Der Prompt verlangte, dass bei 0 die
RGB-LEDs rot leuchten. Der Plan enthielt keinen RGB-Port, und alle Prüfungen
waren grün, weil sie nur gegen den Plan prüften, nie gegen die Anforderung.

Darum:
1. Der Planer zerlegt PROMPT.md in Einzelanforderungen (``R1``, ``R2`` ...)
   mit wörtlichem Zitat, zuständigen Modulen und Ports. Das Zitat muss in
   PROMPT.md vorkommen (Schutz gegen erfundene Anforderungen), die Ports
   müssen im Plan stehen und werden so Teil des Port-Contracts.
2. Testbenches kennzeichnen Prüfungen mit ``REQ Rn`` im report-Text; jede
   simulierbare Anforderung braucht mindestens eine solche Prüfung.
3. Eine unabhängige Abschlussprüfung bewertet jede Anforderung am fertigen
   Entwurf und meldet Anforderungen aus PROMPT.md, die in der Liste fehlen.
"""
from __future__ import annotations

import json
import re

REQUIREMENTS_FILE = "plan/requirements.md"
REVIEW_FILE = "reports/requirements_review.json"
CHECK_KINDS = ("simulation", "structure")
_ID_RE = re.compile(r"^R\d+$")


def normalize(text: str) -> str:
    """Kleinbuchstaben, nur Buchstaben/Ziffern, einfache Leerzeichen."""
    return " ".join(re.sub(r"[^\w]+", " ", str(text).lower()).split())


def quote_in_prompt(quote: str, prompt: str) -> bool:
    q = normalize(quote)
    return bool(q) and q in normalize(prompt)


def _module_ports(manifest: dict) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for module in manifest.get("modules", []) or []:
        if not isinstance(module, dict):
            continue
        ports = module.get("ports", [])
        names = (
            {str(p.get("name", "")).lower() for p in ports if isinstance(p, dict)}
            if isinstance(ports, list) else {str(k).lower() for k in (ports or {})}
        )
        result[str(module.get("entity", ""))] = names
    return result


def check_requirements(manifest: dict, prompt: str) -> tuple[list[dict], list[str]]:
    """Gültige Anforderungen und Regelverstöße des Abschnitts ``requirements``."""
    raw = manifest.get("requirements")
    if not isinstance(raw, list) or not raw:
        return [], [
            "requirements is missing: list every individual requirement of PROMPT.md "
            "(id R1, R2 ..., text, verbatim quote, modules, ports, check)"
        ]
    modules = _module_ports(manifest)
    valid: list[dict] = []
    problems: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            problems.append(f"requirements[{index}] must be an object")
            continue
        rid = str(item.get("id", "")).strip()
        label = rid or f"requirements[{index}]"
        errors = []
        if not _ID_RE.match(rid):
            errors.append(f"{label}: id must look like R1, R2 ...")
        elif rid in seen:
            errors.append(f"{label}: duplicate id")
        if not str(item.get("text", "")).strip():
            errors.append(f"{label}: text is empty")
        if not quote_in_prompt(item.get("quote", ""), prompt):
            errors.append(f"{label}: quote must be an exact excerpt of PROMPT.md")
        owners = item.get("modules") or []
        if not isinstance(owners, list) or not owners:
            errors.append(f"{label}: modules must name at least one responsible entity")
            owners = []
        unknown = [m for m in owners if m not in modules]
        if unknown:
            errors.append(f"{label}: unknown modules {unknown}")
        for port in item.get("ports") or []:
            entity, _, name = str(port).partition(".")
            if not name or entity not in modules or name.lower() not in modules[entity]:
                errors.append(
                    f"{label}: port {port!r} does not exist; add it to the ports of that module "
                    "or reference an existing port as entity.port"
                )
        check = item.get("check", "simulation")
        if check not in CHECK_KINDS:
            errors.append(f"{label}: check must be simulation or structure")
        if errors:
            problems.extend(errors)
            continue
        seen.add(rid)
        valid.append({
            "id": rid,
            "text": str(item["text"]).strip(),
            "quote": str(item.get("quote", "")).strip(),
            "modules": list(owners),
            "ports": [str(p) for p in item.get("ports") or []],
            "check": check,
        })
    return valid, problems


def fallback_requirements(valid: list[dict], prompt: str, top: str) -> list[dict]:
    """Planer lieferte keine saubere Liste: gültige Einträge behalten und den
    vollständigen Prompt als Sammelanforderung ergänzen (Abschlussprüfung)."""
    return [*valid, {
        "id": "R0", "text": prompt.strip(), "quote": "", "modules": [top] if top else [],
        "ports": [], "check": "structure",
    }]


def render_markdown(requirements: list[dict]) -> str:
    lines = [
        "# Einzelanforderungen (aus PROMPT.md abgeleitet, verbindlich)",
        "",
        "Jede Änderung muss alle Anforderungen erfüllt lassen. Bei Widerspruch gilt PROMPT.md.",
        "Prüfart `simulation`: mindestens eine Testbench-Prüfung mit `REQ <id>` im report-Text.",
        "",
    ]
    for req in requirements:
        lines.append(f"- **{req['id']}** ({req.get('check', 'simulation')}): {req['text']}")
        if req.get("quote"):
            lines.append(f"  - Zitat: „{req['quote']}“")
        if req.get("modules") or req.get("ports"):
            lines.append(
                f"  - Module: {', '.join(req.get('modules') or []) or '-'}; "
                f"Ports: {', '.join(req.get('ports') or []) or '-'}"
            )
    return "\n".join(lines) + "\n"


def marker_pattern(rid: str) -> re.Pattern:
    return re.compile(rf"\bREQ\s+{re.escape(rid)}\b")


def uncovered_simulation_requirements(requirements: list[dict], testbench_sources: dict[str, str]) -> list[dict]:
    """Simulierbare Anforderungen ohne gekennzeichnete Testbench-Prüfung.

    ``testbench_sources`` sind kommentarbereinigt: ein ``-- REQ R3`` allein
    zählt nicht, die Kennung muss in einer Prüfung (report/assert) stehen.
    """
    text = "\n".join(testbench_sources.values())
    return [
        r for r in requirements
        if r.get("check") == "simulation" and not marker_pattern(r["id"]).search(text)
    ]


REVIEW_INSTRUCTION = """Unabhängige Abschlussprüfung der Anforderungen. Du hast den Entwurf NICHT geschrieben.
Ändere KEINE Dateien unter src/, tests/, model/ oder plan/; schreibe nur {review_file}.

Lies PROMPT.md, {requirements_file}, alle Dateien unter src/ und tests/ (bei Bedarf ghdl ausführen).
Bewerte jede Anforderung aus {requirements_file} am tatsächlichen Code:
- "met": der Code erfüllt sie nachweisbar (Datei:Zeile oder Testbench-Prüfung nennen),
- "not_met": der Code verletzt sie oder setzt sie nicht um (konkret begründen).
Prüfe außerdem PROMPT.md Satz für Satz: Steht dort eine Anforderung, die in {requirements_file}
fehlt (z. B. eine Ausgabe, LED, Zeitangabe, ein Reset-Verhalten oder Port), trage sie unter "missing"
mit wörtlichem Zitat aus PROMPT.md ein.

Schreibe {review_file} genau in dieser Form:
{{"requirements":[{{"id":"R1","status":"met|not_met","evidence":"..."}}],
 "missing":[{{"text":"...","quote":"wörtlicher Ausschnitt aus PROMPT.md","modules":["entity"]}}]}}
"""


def parse_review(text: str, requirements: list[dict], prompt: str) -> dict:
    """Wertet die Abschlussprüfung aus.

    Ergebnis: ``violations`` (not_met mit Begründung), ``missing`` (nur mit
    wörtlichem Zitat aus PROMPT.md), ``unrated`` (Anforderungen ohne Urteil).
    Ein ``not_met`` ohne Begründung zählt nicht, damit ein unbegründetes
    Urteil keinen korrekten Entwurf in die Reparatur schickt.
    """
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("review must be a JSON object")
    known = {r["id"]: r for r in requirements}
    verdicts = {}
    for item in data.get("requirements") or []:
        if isinstance(item, dict) and item.get("id") in known:
            verdicts[item["id"]] = item
    violations = [
        {**known[rid], "evidence": str(v.get("evidence", "")).strip()}
        for rid, v in verdicts.items()
        if v.get("status") == "not_met" and str(v.get("evidence", "")).strip()
    ]
    missing = [
        {"text": str(m.get("text", "")).strip(), "quote": str(m.get("quote", "")).strip(),
         "modules": [x for x in (m.get("modules") or []) if isinstance(x, str)]}
        for m in data.get("missing") or []
        if isinstance(m, dict) and str(m.get("text", "")).strip() and quote_in_prompt(m.get("quote", ""), prompt)
    ]
    # Bereits erfasste Zitate nicht erneut als fehlend melden.
    covered = {normalize(r.get("quote", "")) for r in requirements if r.get("quote")}
    missing = [m for m in missing if normalize(m["quote"]) not in covered]
    unrated = [rid for rid in known if rid not in verdicts and known[rid]["id"] != "R0"]
    return {"violations": violations, "missing": missing, "unrated": unrated,
            "met": [rid for rid, v in verdicts.items() if v.get("status") == "met"]}


def review_complete(path, requirements: list[dict]) -> bool:
    """Liegt ein vollständiges Urteil vor (gültiges JSON, jede Anforderung bewertet)?"""
    from pathlib import Path

    try:
        data = json.loads(Path(path).read_text(errors="replace"))
    except (OSError, ValueError):
        return False
    if not isinstance(data, dict):
        return False
    rated = {item.get("id") for item in data.get("requirements") or [] if isinstance(item, dict)}
    return all(r["id"] in rated for r in requirements if r["id"] != "R0")


def next_id(requirements: list[dict]) -> str:
    numbers = [int(r["id"][1:]) for r in requirements if _ID_RE.match(str(r.get("id", "")))]
    return f"R{max(numbers, default=0) + 1}"


_TESTBENCH_STAGES = {"implement_testbench", "implement_project", "repair_testbench"}


def task_instruction_suffix(workspace: str, stage: str) -> str:
    """Zusatz für jeden OpenCode-Auftrag nach der Planung.

    Lauf traffic-light (2026-10-10): Eine Reparatur baute den in PROMPT.md
    verlangten synchronen Reset in einen asynchronen um. Die Einzelanforderungen
    stehen deshalb ausdrücklich in jedem Auftrag als Invariante.
    """
    from pathlib import Path

    if stage in ("plan", "requirements_review") or not (Path(workspace) / REQUIREMENTS_FILE).is_file():
        return ""
    text = (
        f"\n\n---\nVerbindliche Einzelanforderungen: {REQUIREMENTS_FILE} (lesen). Deine Arbeit muss "
        "jede davon erfüllt lassen; ändere nichts, was eine Anforderung verletzt (z. B. Reset-Art, "
        "Zeiten, Ports, Ausgaben), auch nicht, um einen Test grün zu bekommen."
    )
    if stage in _TESTBENCH_STAGES:
        text += (
            " Testbenches: Prüfe jede Anforderung mit Prüfart simulation, an der der DUT beteiligt ist, "
            "mit mindestens einer assert-Anweisung, deren report-Text mit `REQ <id>` beginnt, z. B. "
            '`assert led = "1111" report "REQ R3: alle LEDs an bei 15" severity error;`. '
            "Kommentare zählen nicht als Prüfung."
        )
    return text
