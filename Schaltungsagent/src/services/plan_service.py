"""OpenCode planning and deterministic manifest validation."""
from __future__ import annotations

import json
import re

from src.domain.exceptions import WorkflowError
from src.services.opencode_task_runner import OpenCodeTaskRunner

_ENTITY_RE = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$")
_PROJECT_RE = re.compile(r"^[a-z][a-z0-9-]{2,39}$")


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

        if cls._has_cycle(by_name):
            errors.append("Module dependencies contain a cycle")

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
            and name not in {
                "architecture", "begin", "block", "case", "component",
                "configuration", "entity", "end", "generate", "generic",
                "if", "is", "library", "of", "package", "port", "process",
                "signal", "then", "type", "use", "when", "my_component",
                "module", "top", "design", "test", "tb", "uart",
                "fpga", "alu", "control_unit",
            }
        )

    @staticmethod
    def _has_cycle(modules: dict) -> bool:
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(name: str) -> bool:
            if name in visiting:
                return True
            if name in visited or name not in modules:
                return False
            visiting.add(name)
            for dependency in modules[name].get("depends_on", []):
                if dependency in modules and visit(dependency):
                    return True
            visiting.remove(name)
            visited.add(name)
            return False

        return any(visit(name) for name in modules)


class PlanService:
    def __init__(
        self,
        task_runner: OpenCodeTaskRunner,
        timeout_seconds: int = 180,
        name_resolver=None,
    ):
        self._runner = task_runner
        self._timeout = timeout_seconds
        self._name_resolver = name_resolver

    def plan(
        self,
        workspace: str,
        request_full: str,
        task_id: str = "",
        change_request: str = "",
    ) -> dict:
        instruction = """Read PROMPT.md as the complete, authoritative request. Create plan/manifest.json using this shape:
{"project_name":"short-kebab-name","top_entity":"entity","modules":[{"entity":"entity","file":"src/entity.vhd","role":"role","depends_on":[],"ports":[{"name":"clk","direction":"in","type":"std_logic"},{"name":"data_out","direction":"out","type":"std_logic_vector(7 downto 0)"}]}],"testbenches":[{"entity":"entity_tb","file":"tests/entity_tb.vhd","dut":"entity"}],"hardware_tests":[{"name":"short_name","type":"uart_exchange|echo|cpu_program","send":"hex bytes","program":"hex bytes (cpu_program only)","expected":"hex bytes","requirement":"which requirement it proves"}],"open_questions":[]}
Derive the hierarchy and modules from PROMPT.md without splitting, summarizing, replacing, or simplifying the request. Choose meaningful names. Do not write implementation code at this stage.
Every module lists all entity ports with exact VHDL types and bit widths; these ports are a binding contract that the implementation is checked against.
hardware_tests are optional UART test vectors that prove the requested behavior on the real board; only add them when the design exposes a UART protocol whose responses can be predicted exactly.
"""
        if change_request:
            instruction += (
                "\nApply this follow-up change while preserving PROMPT.md unchanged:\n"
                + change_request
            )
        delivery = self._runner.run(
            workspace=workspace,
            request_full=request_full,
            stage="plan",
            task_instruction=instruction,
            expected_files=["plan/manifest.json"],
            task_id=task_id,
            timeout_seconds=self._timeout,
        )
        if not delivery.ok:
            cause_error = delivery.error("Projektplan")
            raise PlanValidationError(
                cause_error.message,
                cause=cause_error.cause or delivery.reason or "OpenCode hat plan/manifest.json nicht geschrieben",
                hint=cause_error.hint,
                context=cause_error.context,
                failure_type=cause_error.failure_type,
            ) from delivery.exception
        try:
            manifest = json.loads(delivery.files["plan/manifest.json"])
        except (KeyError, json.JSONDecodeError) as exc:
            detail = (
                f"{exc.msg}, Zeile {exc.lineno}" if isinstance(exc, json.JSONDecodeError)
                else "Datei fehlt in der Lieferung"
            )
            raise PlanValidationError(
                "OpenCode manifest is not valid JSON",
                cause=f"plan/manifest.json ist kein gültiges JSON ({detail}).",
                hint="Das Modell hat vermutlich Text oder Markdown in die Datei geschrieben; Planung erneut starten.",
            ) from exc
        if self._name_resolver:
            names = self._name_resolver.resolve(request_full, manifest)
            if names.unresolved:
                raise PlanValidationError(
                    "BLOCKED_NEEDS_NAME: " + ", ".join(names.unresolved),
                    cause="Für diese Bezeichner konnte kein eindeutiger Name abgeleitet werden.",
                    hint="Projekt- bzw. Modulnamen in der Anforderung ausdrücklich angeben.",
                )
            manifest = names.manifest
        errors = PlanValidator.validate(manifest)
        if errors:
            raise PlanValidationError(
                "OpenCode manifest is invalid",
                cause="; ".join(errors),
                hint="Die Anforderung präzisieren (Modulnamen, Top-Level) oder die Planung erneut starten.",
            )
        return manifest