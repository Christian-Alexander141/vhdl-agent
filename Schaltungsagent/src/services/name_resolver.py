"""Resolve project and entity names in OpenCode -> Ollama -> rules order."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field

from src.services.ollama_gateway import CodeGuard
from src.services.plan_service import PlanValidator
from src.services.project_namer import extract_project_topic


@dataclass
class NameSet:
    project_name: str | None
    module_entities: list[str | None]
    unresolved: list[str] = field(default_factory=list)
    manifest: dict = field(default_factory=dict)


class NameResolver:
    def __init__(self, naming_llm=None):
        self._naming = naming_llm

    def resolve(self, request_full: str, plan_names: dict) -> NameSet:
        manifest = deepcopy(plan_names or {})
        modules = manifest.get("modules")
        if not isinstance(modules, list):
            modules = []
            manifest["modules"] = modules

        missing: set[str] = set()
        if not PlanValidator.valid_project_name(manifest.get("project_name", "")):
            missing.add("project_name")
        for index, module in enumerate(modules):
            if not isinstance(module, dict) or not PlanValidator.valid_entity(module.get("entity", "")):
                missing.add(f"module_{index}")

        suggestions = {}
        if missing and self._naming:
            suggestions = self._naming.suggest_names(
                request_full,
                set(missing),
                {
                    "topic": extract_project_topic(request_full),
                    "existing_project_name": manifest.get("project_name", ""),
                    "existing_entities": [
                        item.get("entity", "") for item in modules if isinstance(item, dict)
                    ],
                },
            ) or {}

        unresolved: list[str] = []
        project_name = manifest.get("project_name")
        if "project_name" in missing:
            candidate = suggestions.get("project_name", "")
            if self._valid_project(candidate):
                project_name = candidate
            else:
                topic = extract_project_topic(request_full)
                project_name = topic.replace("_", "-") if topic else None
            if not self._valid_project(project_name):
                project_name = None
                unresolved.append("project_name")
        manifest["project_name"] = project_name

        old_to_new: dict[str, str] = {}
        entities: list[str | None] = []
        top_old = manifest.get("top_entity")
        for index, module in enumerate(modules):
            if not isinstance(module, dict):
                entities.append(None)
                unresolved.append(f"module_{index}")
                continue
            old = str(module.get("entity", ""))
            if PlanValidator.valid_entity(old):
                candidate = old
            else:
                candidate = suggestions.get(f"module_{index}", "")
                if not self._valid_entity(candidate):
                    role = str(module.get("role", module.get("description", ""))).lower()
                    topic = extract_project_topic(request_full)
                    if old == top_old and topic:
                        candidate = topic.replace("-", "_")
                    elif any(word in role for word in ("timer", "zeitgeber")):
                        candidate = "timer"
                    elif any(word in role for word in ("control", "schaltwerk")):
                        candidate = "control"
                    else:
                        candidate = ""
                if not self._valid_entity(candidate):
                    unresolved.append(f"module_{index}")
                    entities.append(None)
                    continue
            if old:
                old_to_new[old] = candidate
            module["entity"] = candidate
            module["file"] = f"src/{candidate}.vhd"
            entities.append(candidate)

        if top_old in old_to_new:
            manifest["top_entity"] = old_to_new[top_old]
        for module in modules:
            if not isinstance(module, dict):
                continue
            module["depends_on"] = [old_to_new.get(dep, dep) for dep in module.get("depends_on", [])]
        for testbench in manifest.get("testbenches", []):
            if not isinstance(testbench, dict):
                continue
            dut = old_to_new.get(testbench.get("dut"), testbench.get("dut"))
            testbench.update({
                "dut": dut,
                "entity": f"{dut}_tb",
                "file": f"tests/{dut}_tb.vhd",
            })

        return NameSet(project_name, entities, sorted(set(unresolved)), manifest)

    @staticmethod
    def _valid_project(name: str) -> bool:
        return PlanValidator.valid_project_name(name) and not CodeGuard.is_code(name)

    @staticmethod
    def _valid_entity(name: str) -> bool:
        return PlanValidator.valid_entity(name) and not CodeGuard.is_code(name)