"""OpenCode planning and deterministic manifest validation."""
from __future__ import annotations

import json
import logging
import re

from src.domain.agents import requirements as reqs
from src.domain.exceptions import WorkflowError
from src.services.opencode_task_runner import OpenCodeTaskRunner

logger = logging.getLogger(__name__)
_ENTITY_RE = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$")
_PROJECT_RE = re.compile(r"^[a-z][a-z0-9-]{2,39}$")
_VHDL_RESERVED = {
    "abs", "access", "after", "alias", "all", "and", "architecture", "array", "assert", "attribute",
    "begin", "block", "body", "buffer", "bus", "case", "component", "configuration", "constant",
    "disconnect", "downto", "else", "elsif", "end", "entity", "exit", "file", "for", "function",
    "generate", "generic", "group", "guarded", "if", "impure", "in", "inertial", "inout", "is",
    "label", "library", "linkage", "literal", "loop", "map", "mod", "nand", "new", "next", "nor",
    "not", "null", "of", "on", "open", "or", "others", "out", "package", "port", "postponed",
    "procedure", "process", "pure", "range", "record", "register", "reject", "rem", "report",
    "return", "rol", "ror", "select", "severity", "signal", "shared", "sla", "sll", "sra", "srl",
    "subtype", "then", "to", "transport", "type", "unaffected", "units", "until", "use",
    "variable", "wait", "when", "while", "with", "xnor", "xor",
    "context", "force", "parameter", "release", "default", "sequence", "property",
}


class PlanValidationError(WorkflowError, ValueError):
    """Projektplan fehlt oder ist ungültig (mit Ursache und Hinweis)."""


class PlanValidator:
    MAX_MODULES = 12

    @classmethod
    def validate(cls, manifest: dict) -> list[str]:
        errors = []
        if not isinstance(manifest, dict):
            return ["Manifest must be a JSON object"]

        project_name = manifest.get("project_name")
        if project_name and not cls.valid_project_name(project_name):
            errors.append("Invalid project_name")

        modules = manifest.get("modules")
        if not isinstance(modules, list) or not modules:
            return errors + ["Manifest must contain at least one module"]
        if len(modules) > cls.MAX_MODULES:
            errors.append(f"Manifest may contain at most {cls.MAX_MODULES} modules")

        names = []
        by_name = {}
        for index, module in enumerate(modules):
            if not isinstance(module, dict):
                errors.append(f"Module {index} must be an object")
                continue
            name = module.get("entity")
            if not isinstance(name, str) or not cls.valid_entity(name):
                errors.append(f"Invalid entity name in module {index}")
                continue
            if name in by_name:
                errors.append(f"Duplicate entity: {name}")
            by_name[name] = module
            names.append(name)
            if module.get("file") != f"src/{name}.vhd":
                errors.append(f"Invalid file for entity {name}; expected src/{name}.vhd")

        top = manifest.get("top_entity")
        if top not in by_name:
            errors.append("top_entity must name a declared module")

        for name, module in by_name.items():
            dependencies = module.get("depends_on", [])
            if not isinstance(dependencies, list):
                errors.append(f"Dependencies for {name} must be a list")
                continue
            for dependency in dependencies:
                if dependency not in by_name:
                    errors.append(f"Unknown dependency {dependency!r} in module {name}")

        cycle = cls.find_cycle(by_name)
        if cycle:
            errors.append(
                "Module dependencies contain a cycle: " + " -> ".join(cycle)
                + " (depends_on lists only the modules a module instantiates; a module never depends on itself or on its parent)"
            )

        for name, module in by_name.items():
            ports = module.get("ports", [])
            if not isinstance(ports, (list, dict)):
                errors.append(f"ports for {name} must be a list")
                continue
            for port in ports if isinstance(ports, list) else []:
                if not isinstance(port, dict) or not port.get("name"):
                    errors.append(f"Each port of {name} needs a name")
                elif port.get("direction", "in") not in ("in", "out", "inout", "buffer"):
                    errors.append(f"Invalid direction for port {port['name']} of {name}")

        for name, module in by_name.items():
            if not isinstance(module.get("parameters", {}), dict):
                errors.append(f"parameters for {name} must be an object of generic defaults")
            vectors = module.get("simulation_vectors", [])
            if not isinstance(vectors, list):
                errors.append(f"simulation_vectors for {name} must be a list")
                continue
            for vector in vectors:
                if not isinstance(vector, dict) or not isinstance(vector.get("expected"), dict) or not vector.get("expected"):
                    errors.append(f"Each simulation_vector of {name} needs a non-empty 'expected' mapping")

        if not isinstance(manifest.get("hardware_tests", []), list):
            errors.append("hardware_tests must be a list")

        testbenches = manifest.get("testbenches", [])
        if not isinstance(testbenches, list):
            errors.append("testbenches must be a list")
        else:
            for testbench in testbenches:
                if not isinstance(testbench, dict):
                    errors.append("Each testbench must be an object")
                    continue
                dut = testbench.get("dut")
                if dut not in by_name:
                    errors.append(f"Unknown testbench DUT: {dut}")
                    continue
                if testbench.get("entity") != f"{dut}_tb":
                    errors.append(f"Testbench entity for {dut} must be {dut}_tb")
                if testbench.get("file") != f"tests/{dut}_tb.vhd":
                    errors.append(f"Testbench file for {dut} must be tests/{dut}_tb.vhd")
        return errors

    @staticmethod
    def valid_project_name(name: str) -> bool:
        return bool(
            isinstance(name, str)
            and _PROJECT_RE.fullmatch(name)
            and not name.startswith((
                "aufgabe", "task", "prompt", "projekt", "uebung", "erstelle",
                "schaltung", "vhdl", "fpga",
                "entity",
            ))
        )

    @staticmethod
    def valid_entity(name: str) -> bool:
        return bool(
            isinstance(name, str)
            and len(name) <= 32
            and _ENTITY_RE.fullmatch(name)
            # VHDL-Schlüsselwörter sind als Entity-Name ungültig; "uart" belegt
            # das MAS selbst für die UART-Echo-Brücke. Früher standen hier auch
            # gängige Namen wie "alu" oder "top" – ein Prompt, der eine Entity
            # "alu" verlangt, wäre damit abgelehnt bzw. umbenannt worden.
            and name not in _VHDL_RESERVED | {"uart"}
        )

    @staticmethod
    def _has_cycle(modules: dict) -> bool:
        return bool(PlanValidator.find_cycle(modules))

    @staticmethod
    def find_cycle(modules: dict) -> list[str]:
        """Erster Abhängigkeitszyklus als Pfad (z. B. ["a", "b", "a"]), sonst []."""
        visiting: list[str] = []
        visited: set[str] = set()

        def visit(name: str) -> list[str]:
            if name in visiting:
                return visiting[visiting.index(name):] + [name]
            if name in visited or name not in modules:
                return []
            visiting.append(name)
            for dependency in modules[name].get("depends_on", []) or []:
                if dependency in modules:
                    cycle = visit(dependency)
                    if cycle:
                        return cycle
            visiting.pop()
            visited.add(name)
            return []

        for name in modules:
            cycle = visit(name)
            if cycle:
                return cycle
        return []


class PlanService:
    def __init__(
        self,
        task_runner: OpenCodeTaskRunner,
        timeout_seconds: int = 180,
        name_resolver=None,
        max_attempts: int = 3,
    ):
        self._runner = task_runner
        self._timeout = timeout_seconds
        self._name_resolver = name_resolver
        # Ein ungültiger Plan beendete früher den ganzen Lauf (z. B. "Module
        # dependencies contain a cycle"); jetzt bekommt OpenCode die Fehlerliste
        # zur Korrektur zurück.
        self._max_attempts = max(1, max_attempts)

    def plan(
        self,
        workspace: str,
        request_full: str,
        task_id: str = "",
        change_request: str = "",
    ) -> dict:
        instruction = """Read PROMPT.md as the complete, authoritative request. Create plan/manifest.json using this shape:
{"project_name":"short-kebab-name","top_entity":"entity","reset_concept":"sync_active_high|async_active_high|sync_active_low|async_active_low|none","modules":[{"entity":"entity","file":"src/entity.vhd","role":"role","type":"combinational|sequential|structural","depends_on":[],"parameters":{"WIDTH":8},"ports":[{"name":"clk","direction":"in","type":"std_logic"},{"name":"data_out","direction":"out","type":"std_logic_vector(7 downto 0)"}]}],"testbenches":[{"entity":"entity_tb","file":"tests/entity_tb.vhd","dut":"entity"}],"hardware_tests":[{"name":"short_name","type":"uart_exchange|echo|cpu_program","send":"hex bytes","program":"hex bytes (cpu_program only)","expected":"hex bytes","requirement":"which requirement it proves"}],"requirements":[{"id":"R1","text":"precise, testable statement","quote":"exact verbatim excerpt of PROMPT.md","modules":["entity"],"ports":["entity.port"],"check":"simulation|structure"}],"open_questions":[]}
Derive the hierarchy and modules from PROMPT.md without splitting, summarizing, replacing, or simplifying the request. Choose meaningful names: project_name is 3-40 characters of lowercase letters, digits and hyphens describing the design (e.g. "traffic-light", "sram-controller"), never starting with words like task, aufgabe, projekt, vhdl or fpga; entity names are lowercase snake_case VHDL identifiers and must keep any entity names that PROMPT.md prescribes. Do not write implementation code at this stage.
Every module lists all entity ports with exact VHDL types and bit widths; these ports are a binding contract that the implementation is checked against. List every clock/reset port explicitly with the exact name you want; nothing is added implicitly. "parameters" are the entity generics (name: default value), omit it when there are none. The top_entity must itself be listed as a module whose depends_on names every module it instantiates.
reset_concept is the reset behavior PROMPT.md demands (e.g. "synchroner Reset" -> sync_active_high); only if PROMPT.md says nothing about the reset, use async_active_high. Every module implements this reset concept.
requirements lists EVERY individual requirement of PROMPT.md as its own entry: each behavior, each output or indicator (e.g. every LED or RGB LED that must light up), each timing value, the reset behavior, each interface/port, generic, file name and language standard. Do not merge, drop, weaken or reinterpret anything. "quote" is copied verbatim from PROMPT.md. "modules" are the entities responsible for it, "ports" the involved ports as entity.port; every port named there must exist in that module's ports, so add ports the requirement needs (e.g. an RGB output) to the module. "check" is "simulation" when a testbench can observe it, otherwise "structure".
hardware_tests are optional UART test vectors that prove the requested behavior on the real board; only add them when the design exposes a UART protocol whose responses can be predicted exactly.
"""
        if change_request:
            instruction += (
                "\nApply this follow-up change while preserving PROMPT.md unchanged:\n"
                + change_request
            )
        problems: list[str] = []
        manifest_text = ""
        for attempt in range(1, self._max_attempts + 1):
            delivery = self._runner.run(
                workspace=workspace,
                request_full=request_full,
                stage="plan",
                task_instruction=instruction,
                expected_files=["plan/manifest.json"],
                task_id=f"{task_id}_try{attempt}" if attempt > 1 else task_id,
                timeout_seconds=self._timeout,
            )
            if not delivery.ok:
                cause_error = delivery.error("Projektplan")
                # Provider-/Infrastrukturfehler: ein weiterer Versuch hilft nicht.
                if cause_error.failure_type == "infrastructure" or attempt == self._max_attempts:
                    raise PlanValidationError(
                        cause_error.message,
                        cause=cause_error.cause or delivery.reason or "OpenCode hat plan/manifest.json nicht geschrieben",
                        hint=cause_error.hint,
                        context=cause_error.context,
                        failure_type=cause_error.failure_type,
                    ) from delivery.exception
                problems = [f"plan/manifest.json was not delivered ({delivery.reason})"]
                instruction = self._correction(problems, first=instruction)
                continue
            manifest_text = delivery.files.get("plan/manifest.json", "")
            try:
                manifest = json.loads(manifest_text)
            except json.JSONDecodeError as exc:
                problems = [f"plan/manifest.json ist kein gültiges JSON ({exc.msg}, Zeile {exc.lineno})"]
                instruction = self._correction(problems)
                continue
            if not isinstance(manifest, dict):
                problems = ["plan/manifest.json must contain a JSON object"]
                instruction = self._correction(problems)
                continue
            if self._name_resolver:
                manifest = self._name_resolver.resolve(request_full, manifest).manifest
            self._autofix(manifest)
            structural = PlanValidator.validate(manifest)
            valid_reqs, req_problems = reqs.check_requirements(manifest, request_full)
            problems = structural + req_problems
            if not problems:
                manifest["requirements"] = valid_reqs
                if attempt > 1:
                    logger.info("Plan valid after %d attempts", attempt)
                return manifest
            if not structural and attempt == self._max_attempts:
                # Eine unvollständige Anforderungsliste beendet den Lauf nicht:
                # gültige Einträge bleiben, der ganze Prompt wird Sammel-
                # anforderung R0 für die Abschlussprüfung.
                logger.warning("Plan requirements incomplete, using fallback: %s", "; ".join(req_problems))
                manifest["requirements"] = reqs.fallback_requirements(
                    valid_reqs, request_full, manifest.get("top_entity", ""))
                manifest["requirements_warnings"] = req_problems
                return manifest
            logger.warning("Plan attempt %d invalid: %s", attempt, "; ".join(problems))
            instruction = self._correction(problems)
        raise PlanValidationError(
            "OpenCode manifest is invalid",
            cause="; ".join(problems),
            hint=f"Nach {self._max_attempts} Korrekturversuchen weiterhin ungültig; Anforderung präzisieren oder erneut starten.",
            context={"Letzter Plan (Auszug)": manifest_text[:1500]},
        )

    @staticmethod
    def _correction(problems: list[str], first: str = "") -> str:
        if first:
            return first
        return (
            "plan/manifest.json violates these rules:\n- " + "\n- ".join(problems)
            + "\nRead PROMPT.md and plan/manifest.json, fix exactly these problems in plan/manifest.json "
            "(keep everything else unchanged) and write the corrected file. Do not write implementation code."
        )

    @staticmethod
    def _autofix(manifest: dict) -> None:
        """Eindeutige Fehler ohne Sprachmodell beheben: Selbstabhängigkeiten, Dubletten."""
        for module in manifest.get("modules", []) or []:
            if not isinstance(module, dict) or not isinstance(module.get("depends_on"), list):
                continue
            own = module.get("entity")
            module["depends_on"] = [d for d in dict.fromkeys(module["depends_on"]) if d != own]
        reset = str(manifest.get("reset_concept", "")).strip().lower()
        if reset and reset not in _RESET_CONCEPTS:
            logger.warning("Ignoring invalid reset_concept %r in plan", manifest.get("reset_concept"))
            manifest.pop("reset_concept", None)
        elif reset:
            manifest["reset_concept"] = reset


_RESET_CONCEPTS = {"sync_active_high", "async_active_high", "sync_active_low", "async_active_low", "none"}
