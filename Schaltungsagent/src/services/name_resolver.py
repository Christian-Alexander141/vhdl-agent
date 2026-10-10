"""Projekt- und Entity-Namen: OpenCode legt sie im Plan fest, hier werden sie nur bereinigt.

Früher fragte der Resolver bei ungültigen Namen ein separates Ollama-LLM und
blockierte den ganzen Lauf, wenn das nicht antwortete (BLOCKED_NEEDS_NAME,
Benchmark 20261010-091252, Muse/task04). Jetzt gilt: Der Name aus
plan/manifest.json wird deterministisch bereinigt; nur wenn davon nichts
Gültiges übrig bleibt, wird ein Ersatzname abgeleitet. Ein Lauf scheitert
nie mehr an der Namensvergabe.
"""
from __future__ import annotations

import hashlib
import re
from copy import deepcopy
from dataclasses import dataclass, field

from src.services.plan_service import PlanValidator
from src.services.project_namer import extract_project_topic

# Präfixe, die keinen Inhalt beschreiben (z. B. "task04-sram" -> "sram").
_FILLER_PREFIX = re.compile(
    r"^(?:(?:aufgabe|task|prompt|projekt|project|uebung|übung|erstelle|schaltung|vhdl|fpga|entity)"
    r"[-_ ]*\d*[-_ ]*)+",
    re.IGNORECASE,
)
_UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "Ä": "ae", "Ö": "oe", "Ü": "ue"})


@dataclass
class NameSet:
    project_name: str | None
    module_entities: list[str | None]
    unresolved: list[str] = field(default_factory=list)
    manifest: dict = field(default_factory=dict)


def _slug(text: str, sep: str) -> str:
    text = str(text or "").translate(_UMLAUTS).lower()
    text = re.sub(r"[^a-z0-9]+", sep, text).strip(sep)
    return re.sub(re.escape(sep) + "+", sep, text)


def normalize_project_name(candidate: str) -> str:
    slug = _slug(candidate, "-")
    stripped = _FILLER_PREFIX.sub("", slug).strip("-")
    for name in (stripped, slug):
        name = name[:40].strip("-")
        if name and name[0].isdigit():
            name = f"p-{name}"[:40].strip("-")
        if PlanValidator.valid_project_name(name):
            return name
    return ""


def normalize_entity(candidate: str) -> str:
    name = _slug(candidate, "_")[:32].strip("_")
    if name and name[0].isdigit():
        name = f"m_{name}"[:32]
    return name if PlanValidator.valid_entity(name) else ""


class NameResolver:
    """Bereinigt die von OpenCode im Plan vergebenen Namen (kein eigenes Sprachmodell)."""

    def resolve(self, request_full: str, plan_names: dict) -> NameSet:
        manifest = deepcopy(plan_names or {})
        modules = manifest.get("modules")
        if not isinstance(modules, list):
            modules = []
            manifest["modules"] = modules

        old_to_new: dict[str, str] = {}
        entities: list[str | None] = []
        used: set[str] = set()
        for index, module in enumerate(modules):
            if not isinstance(module, dict):
                entities.append(None)
                continue
            old = str(module.get("entity", ""))
            candidate = old if PlanValidator.valid_entity(old) else normalize_entity(old)
            if not candidate:
                candidate = normalize_entity(module.get("role", "")) or f"module_{index}"
            base, n = candidate, 2
            while candidate in used:
                candidate = f"{base}_{n}"[:32]
                n += 1
            used.add(candidate)
            if old:
                old_to_new[old] = candidate
            module["entity"] = candidate
            module["file"] = f"src/{candidate}.vhd"
            entities.append(candidate)

        top_old = manifest.get("top_entity")
        if top_old in old_to_new:
            manifest["top_entity"] = old_to_new[top_old]

        project_name = manifest.get("project_name", "")
        if not PlanValidator.valid_project_name(project_name):
            project_name = (
                normalize_project_name(project_name)
                or normalize_project_name(manifest.get("top_entity", ""))
                or normalize_project_name(extract_project_topic(request_full) or "")
                or "design-" + hashlib.sha256((request_full or "").encode()).hexdigest()[:6]
            )
        manifest["project_name"] = project_name

        for module in modules:
            if isinstance(module, dict):
                module["depends_on"] = [old_to_new.get(dep, dep) for dep in module.get("depends_on", [])]
        for testbench in manifest.get("testbenches", []):
            if not isinstance(testbench, dict):
                continue
            dut = old_to_new.get(testbench.get("dut"), testbench.get("dut"))
            testbench.update({"dut": dut, "entity": f"{dut}_tb", "file": f"tests/{dut}_tb.vhd"})

        return NameSet(project_name, entities, [], manifest)
