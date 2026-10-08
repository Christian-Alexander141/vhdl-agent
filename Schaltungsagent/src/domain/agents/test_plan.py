"""Testplan und Abdeckung pro Modul und Requirement.

Ein Modul ohne Golden-Model-Vektoren (``ModuleInfo.simulation_vectors``) gilt
als abgedeckt, wenn es von mindestens einer Testbench unter ``tests/`` über
die Instanziierungshierarchie erreicht wird (reine Erreichbarkeit). Ein Modul
MIT Vektoren gilt erst als abgedeckt, wenn zusätzlich jeder Vektor im
Quelltext der erreichenden Testbench(en) referenziert wird – reine
Erreichbarkeit genügt dann nicht mehr. Ein Requirement gilt als abgedeckt,
wenn alle Module, die es erfüllen sollen, abgedeckt sind.

Das ersetzt keine vollständige funktionale Coverage (der Vektor-Check ist ein
Literal-Abgleich, kein Beweis korrekter Verdrahtung), verhindert aber, dass
Module ohne jede Simulation oder mit ignorierten Golden-Vektoren in die
Synthese gelangen.
"""
import re
from pathlib import Path

_ENTITY_DECL = re.compile(r"\bentity\s+(\w+)\s+is\b", re.IGNORECASE)
_DIRECT_INST = re.compile(r"\bentity\s+(?:\w+\.)?(\w+)", re.IGNORECASE)
_COMPONENT_INST = re.compile(
    r"^\s*\w+\s*:\s*(?:component\s+)?(\w+)\s*(?:generic|port)\s+map",
    re.IGNORECASE | re.MULTILINE,
)


def _strip_comments(text: str) -> str:
    return re.sub(r"--[^\n]*", "", text)


def _instantiations(text: str) -> set[str]:
    body = _strip_comments(text)
    arch = re.search(r"\barchitecture\b", body, re.IGNORECASE)
    if arch:
        body = body[arch.start():]
    return {m.lower() for m in _DIRECT_INST.findall(body)} | {
        m.lower() for m in _COMPONENT_INST.findall(body)
    }


def _entity_graph(directory: Path) -> dict[str, set[str]]:
    graph: dict[str, set[str]] = {}
    if not directory.exists():
        return graph
    for path in sorted(directory.iterdir()):
        if path.suffix.lower() not in (".vhd", ".vhdl") or not path.is_file():
            continue
        text = path.read_text(errors="replace")
        decl = _ENTITY_DECL.search(_strip_comments(text))
        if decl:
            graph[decl.group(1).lower()] = _instantiations(text)
    return graph


def _tb_sources(directory: Path) -> dict[str, str]:
    """Kommentarbereinigter Quelltext je Testbench-Entity (klein gehalten:
    nur für den Vektor-Referenz-Check in :func:`build_test_plan`)."""
    sources: dict[str, str] = {}
    if not directory.exists():
        return sources
    for path in sorted(directory.iterdir()):
        if path.suffix.lower() not in (".vhd", ".vhdl") or not path.is_file():
            continue
        text = _strip_comments(path.read_text(errors="replace"))
        decl = _ENTITY_DECL.search(text)
        if decl:
            sources[decl.group(1).lower()] = text
    return sources


def _module_vectors(module) -> list[dict]:
    raw = module.get("simulation_vectors") if isinstance(module, dict) else getattr(module, "simulation_vectors", None)
    return raw or []


def format_simulation_vectors(vectors: list[dict]) -> str:
    """Rendert Golden-Model-Vektoren als verbindliche Testbench-Anforderung.

    Leere Liste ergibt einen leeren String (kein zusätzlicher Prompt-Abschnitt).
    Eingesetzt in den Testbench-Prompts von ``hdl.py`` und ``verification.py``,
    damit Erwartungswerte aus der Spezifikation stammen statt vom Modell selbst
    erfunden zu werden.
    """
    if not vectors:
        return ""
    lines = [
        "GOLDEN-MODEL-VEKTOREN (verbindlich, aus der Spezifikation abgeleitet "
        "– keine abweichenden oder selbst erfundenen Erwartungswerte verwenden):",
    ]
    for i, vec in enumerate(vectors, 1):
        inputs = vec.get("inputs", {})
        expected = vec.get("expected", {})
        after = vec.get("after_clocks")
        requirement = vec.get("requirement", "")
        parts = [f"Vektor {i}: setze {inputs}"]
        if after:
            parts.append(f"warte {after} Takt(e)")
        parts.append(f"erwarte exakt {expected}")
        if requirement:
            parts.append(f"(prüft: {requirement})")
        lines.append("; ".join(parts) + ".")
    lines.append(
        "Für jeden Vektor eine eigene Assertion mit eindeutigem Report-Text "
        '(z. B. "VECTOR_FAIL: <Nummer/Anforderung>"), damit ein Fehlschlag '
        "einem konkreten Vektor zuzuordnen ist."
    )
    return "\n".join(lines)


def _referenced_vectors(text: str, vectors: list[dict]) -> int:
    """Heuristik: ein Vektor gilt als referenziert, wenn alle seine erwarteten
    Literalwerte im Testbench-Quelltext vorkommen. Das beweist keine korrekte
    Verdrahtung, deckt aber den Fall ab, dass eine Testbench ein Modul zwar
    erreicht, seine Golden-Vektoren aber nie anfasst."""
    count = 0
    for vec in vectors:
        expected = vec.get("expected") or {}
        values = [str(v) for v in expected.values()]
        if values and all(val in text for val in values):
            count += 1
    return count


def _reachable(start: set[str], graph: dict[str, set[str]]) -> set[str]:
    seen: set[str] = set()
    stack = list(start)
    while stack:
        node = stack.pop()
        if node in seen:
            continue
        seen.add(node)
        stack.extend(graph.get(node, set()) - seen)
    return seen


def build_test_plan(
    architecture: dict,
    workspace: str,
    requirements: list[dict] | None = None,
) -> dict:
    """Erzeugt Testplan + Abdeckung aus Architektur und Workspace."""
    ws = Path(workspace)
    src_graph = _entity_graph(ws / "src")
    tb_graph = _entity_graph(ws / "tests")
    graph = {**src_graph, **tb_graph}

    modules_raw = architecture.get("modules", [])
    modules = [
        (m.get("name", "") if isinstance(m, dict) else getattr(m, "name", ""))
        for m in modules_raw
    ]
    vectors_by_name = {
        (m.get("name", "") if isinstance(m, dict) else getattr(m, "name", "")): _module_vectors(m)
        for m in modules_raw
    }
    tb_sources = _tb_sources(ws / "tests")
    module_plan: dict[str, dict] = {}
    for name in modules:
        module_plan[name] = {
            "testbenches": [],
            "covered": False,
            "simulation_vectors": len(vectors_by_name.get(name) or []),
            "vectors_referenced": 0,
        }

    for tb_name in tb_graph:
        reached = _reachable(tb_graph[tb_name], graph)
        for name in modules:
            if name.lower() in reached:
                module_plan[name]["testbenches"].append(tb_name)

    for name in modules:
        plan = module_plan[name]
        reached_by_tb = bool(plan["testbenches"])
        vectors = vectors_by_name.get(name) or []
        if not vectors:
            # Keine Golden-Vektoren definiert: reine Erreichbarkeit wie bisher.
            plan["covered"] = reached_by_tb
            continue
        combined_text = "".join(tb_sources.get(tb, "") for tb in plan["testbenches"])
        referenced = _referenced_vectors(combined_text, vectors)
        plan["vectors_referenced"] = referenced
        # Vektoren definiert: Abdeckung erfordert, dass jeder Vektor auch
        # tatsächlich geprüft wird – reine Erreichbarkeit genügt nicht mehr.
        plan["covered"] = reached_by_tb and referenced == len(vectors)

    covered = [n for n, p in module_plan.items() if p["covered"]]
    uncovered = [n for n, p in module_plan.items() if not p["covered"]]

    requirement_plan: dict[str, dict] = {}
    for req in requirements or []:
        satisfied_by = [m for m in req.get("satisfied_by", []) if m in module_plan]
        requirement_plan[req.get("id", "")] = {
            "description": req.get("description", "")[:200],
            "modules": satisfied_by,
            "covered": all(module_plan[m]["covered"] for m in satisfied_by) if satisfied_by else bool(covered),
        }

    return {
        "modules": module_plan,
        "requirements": requirement_plan,
        "testbenches": sorted(tb_graph),
        "covered": covered,
        "uncovered": uncovered,
        "coverage": (len(covered) / len(modules)) if modules else 0.0,
    }
