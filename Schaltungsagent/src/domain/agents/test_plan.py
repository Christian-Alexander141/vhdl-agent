"""Testplan und strukturelle Abdeckung pro Modul und Requirement.

Ein Modul gilt als abgedeckt, wenn es von mindestens einer Testbench unter
``tests/`` über die Instanziierungshierarchie erreicht wird. Ein Requirement
gilt als abgedeckt, wenn alle Module, die es erfüllen sollen, abgedeckt sind.
Das ersetzt keine funktionale Coverage, verhindert aber, dass Module ohne
jede Simulation in die Synthese gelangen.
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

    modules = [
        (m.get("name", "") if isinstance(m, dict) else getattr(m, "name", ""))
        for m in architecture.get("modules", [])
    ]
    module_plan: dict[str, dict] = {}
    for name in modules:
        module_plan[name] = {"testbenches": [], "covered": False}

    for tb_name in tb_graph:
        reached = _reachable(tb_graph[tb_name], graph)
        for name in modules:
            if name.lower() in reached:
                module_plan[name]["testbenches"].append(tb_name)
                module_plan[name]["covered"] = True

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
