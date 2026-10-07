import logging
import re
import unicodedata
import uuid
from typing import Any

from src.domain.agents import BaseAgent, AgentTask, AgentResult, AgentStatus
from src.domain.models import DesignState, ModuleInfo, ArchitectureInfo
from src.domain.models.design_state import Requirement
from src.services.deterministic_design import DeterministicDesignService
from src.services.plan_service import PlanService, PlanValidator

logger = logging.getLogger(__name__)


def module_from_manifest(item: dict) -> ModuleInfo:
    """ModuleInfo aus einem Manifest-Modul inkl. typisiertem Port-Contract.

    Ports dürfen als Name, als ``"name: typ"`` oder als Dict
    ``{"name", "type", "direction"}`` angegeben sein. Namen landen in
    inputs/outputs, Typen im maschinenprüfbaren ``ports``-Contract.
    """
    raw_ports = item.get("ports", {}) or {}
    names: dict[str, list[str]] = {"in": [], "out": []}
    ports: dict = {}
    if isinstance(raw_ports, dict):
        ports = dict(raw_ports)
    else:  # Manifest-Liste [{"name", "direction", "type"}]
        for port in raw_ports:
            if not isinstance(port, dict) or not port.get("name"):
                continue
            direction = str(port.get("direction", "in")).lower()
            names["out" if direction in ("out", "buffer") else "in"].append(port["name"])
            spec = {"direction": direction}
            if port.get("type"):
                spec["type"] = port["type"]
            ports[port["name"]] = spec
    for direction, key in (("in", "inputs"), ("out", "outputs")):
        for entry in item.get(key, []) or []:
            if isinstance(entry, dict):
                name, port_type = entry.get("name", ""), entry.get("type")
            elif isinstance(entry, str) and ":" in entry:
                name, port_type = (part.strip() for part in entry.split(":", 1))
            else:
                name, port_type = str(entry).strip(), None
            if not name or name in names[direction]:
                continue
            names[direction].append(name)
            if port_type:
                ports.setdefault(name, {"direction": direction, "type": port_type})
    return ModuleInfo(
        name=item["entity"],
        type=item.get("type", "sequential"),
        inputs=names["in"],
        outputs=names["out"],
        parameters=item.get("parameters", {}),
        description=item.get("role", item.get("description", "")),
        dependencies=item.get("depends_on", []),
        files=[item["file"]],
        ports=ports,
    )


class ArchitectureHandoff:
    """Structured handoff data from architecture agent.
    
    Contains all information needed by downstream agents to implement
    individual modules without requiring the full architecture context.
    """
    
    def __init__(
        self,
        modules: list[dict],
        interfaces: dict,
        clock_domain: str,
        reset_concept: str,
        task_graph: dict | None = None,
        top_module: str = "",
    ):
        self.modules = modules
        self.interfaces = interfaces
        self.clock_domain = clock_domain
        self.reset_concept = reset_concept
        self.task_graph = task_graph or {}
        self.top_module = top_module
    
    def get_module(self, name: str) -> dict | None:
        for m in self.modules:
            if m.get("name") == name:
                return m
        return None
    
    def get_dependencies(self, module_name: str) -> list[str]:
        module = self.get_module(module_name)
        if module:
            return module.get("dependencies", [])
        return []
    
    def get_interface(self, source: str, target: str) -> dict | None:
        for iface_name, iface_data in self.interfaces.items():
            if isinstance(iface_data, dict):
                if iface_data.get("from") == source and iface_data.get("to") == target:
                    return iface_data
        return None
    
    def get_module_task_context(self, module_name: str) -> dict:
        """Get context specific to a single module implementation task."""
        module = self.get_module(module_name)
        if not module:
            return {}
        
        # Collect interfaces involving this module
        relevant_interfaces = {}
        for iface_name, iface_data in self.interfaces.items():
            if isinstance(iface_data, dict):
                if iface_data.get("from") == module_name or iface_data.get("to") == module_name:
                    relevant_interfaces[iface_name] = iface_data
        
        # Determine expected output file
        expected_file = f"src/{module_name}.vhd"
        
        return {
            "module": module,
            "interfaces": relevant_interfaces,
            "clock_domain": self.clock_domain,
            "reset_concept": self.reset_concept,
            "expected_file": expected_file,
            "dependencies": module.get("dependencies", []),
        }
    
    def to_dict(self) -> dict:
        return {
            "modules": self.modules,
            "interfaces": self.interfaces,
            "clock_domain": self.clock_domain,
            "reset_concept": self.reset_concept,
            "top_module": self.top_module,
            "task_graph": self.task_graph,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'ArchitectureHandoff':
        return cls(
            modules=data.get("modules", []),
            interfaces=data.get("interfaces", {}),
            clock_domain=data.get("clock_domain", "clk"),
            reset_concept=data.get("reset_concept", "async_active_high"),
            task_graph=data.get("task_graph", {}),
            top_module=data.get("top_module", ""),
        )


class ArchitectureAgent(BaseAgent):
    """Erstellt Hardware-Architektur aus Anforderungen.
    
    Aufgaben:
    - Modulstruktur definieren
    - Interfaces spezifizieren
    - Signal-Verbindungen planen
    - Clock/Reset-Konzept festlegen
    - Abhängigkeiten zwischen Modulen identifizieren
    - Strukturierte Handoff-Daten für Downstream-Agenten erzeugen
    """

    def __init__(self, plan_service, event_publisher=None):
        super().__init__("ArchitectureAgent", event_publisher)
        self._plan = plan_service

    @property
    def supported_task_types(self) -> list[str]:
        return ["create_architecture", "refine_architecture", "validate_architecture"]

    async def execute(self, task: AgentTask) -> AgentResult:
        task_type = task.type
        
        if task_type == "create_architecture":
            return await self._create_architecture(task)
        elif task_type == "refine_architecture":
            return await self._refine_architecture(task)
        elif task_type == "validate_architecture":
            return await self._validate_architecture(task)
        else:
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.FAILED,
                error_message=f"Unknown task type: {task_type}",
            )

    async def _create_architecture(self, task: AgentTask) -> AgentResult:
        """Build ArchitectureInfo from an OpenCode-produced plan manifest."""
        request = task.inputs.get("request", "")
        workspace = task.inputs.get("workspace", "")
        try:
            manifest = (
                task.inputs.get("manifest")
                if task.inputs.get("manifest") and not task.inputs.get("change_request")
                else self._plan.plan(
                    workspace,
                    request,
                    task.id,
                    change_request=task.inputs.get("change_request", ""),
                )
            )
            errors = PlanValidator.validate(manifest)
            if errors:
                raise ValueError("Invalid plan manifest: " + "; ".join(errors))
            modules = [module_from_manifest(item) for item in manifest["modules"]]
            architecture = {
                "modules": modules,
                "top_module": manifest["top_entity"],
                "interfaces": manifest.get("interfaces", {}),
                "clock_domain": manifest.get("clock_domain", "clk"),
                "reset_concept": manifest.get("reset_concept", "async_active_high"),
                "decisions": [{"decision": "Plan aus OpenCode-Manifest übernommen"}],
            }
            
            decisions = architecture.get("decisions", [])
            if decisions and isinstance(decisions[0], str):
                decisions = [{"decision": d} for d in decisions]
            
            arch_info = ArchitectureInfo(
                status="completed",
                version=1,
                modules=architecture.get("modules", []),
                top_module=architecture.get("top_module") or self._last_module_name(architecture.get("modules", [])),
                interfaces=architecture.get("interfaces", {}),
                clock_domain=architecture.get("clock_domain", "clk"),
                reset_concept=architecture.get("reset_concept", "async_active_high"),
                decisions=decisions,
                hardware_tests=manifest.get("hardware_tests", []) or [],
            )
            
            # Create structured handoff for downstream agents
            handoff = ArchitectureHandoff(
                modules=[m.model_dump() if hasattr(m, 'model_dump') else m for m in arch_info.modules],
                interfaces=arch_info.interfaces,
                clock_domain=arch_info.clock_domain,
                reset_concept=arch_info.reset_concept,
                top_module=arch_info.top_module,
            )
            
            # Generate task graph from module dependencies
            task_graph = self._generate_task_graph(
                architecture.get("modules", []), arch_info.top_module
            )
            handoff.task_graph = task_graph
            
            self.emit_event("ARCHITECTURE_CREATED", {
                "task_id": task.id,
                "module_count": len(arch_info.modules),
                "handoff_created": True,
            })
            
            self.emit_event("ARCHITECTURE_HANDOFF_CREATED", {
                "task_id": task.id,
                "module_count": len(arch_info.modules),
                "task_graph_tasks": len(task_graph.get("tasks", [])),
            })
            
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.COMPLETED,
                outputs={
                    "architecture": arch_info.model_dump(),
                    "handoff": handoff.to_dict(),
                    "task_graph": task_graph,
                    "manifest": manifest,
                    "open_questions": manifest.get("open_questions", []),
                },
            )
            
        except Exception as e:
            logger.exception("Architecture creation failed")
            failure_type = getattr(e, "failure_type", "")
            self.emit_event("ARCHITECTURE_FAILED", {
                "task_id": task.id,
                "error": str(e),
            })
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.FAILED,
                error_message=f"Architecture creation failed: {e}",
                diagnostics=[{
                    "type": "architecture_failure",
                    "stage": "architecture",
                    "message": str(e),
                    **({"failure_type": failure_type} if failure_type else {}),
                    **({"details": e.to_dict()} if hasattr(e, "to_dict") else {}),
                }],
            )

    def _build_architecture_prompt(
        self, request: str, analysis: str
    ) -> str:
        """Baut Prompt für Architekturentwurf."""
        return f"""Entwirf eine Hardware-Architektur für folgende Anforderung:

ANFORDERUNG:
{request}

ANALYSE:
{analysis}

Erstelle eine YAML-Struktur mit:
- modules: Liste von Modulen (name, type, inputs, outputs, parameters, description, dependencies)
- interfaces: Signal-Definitionen zwischen Modulen
- clock_domain: Haupt-Takt-Signal Name
- reset_concept: Reset-Strategie (sync/async, active high/low)
- decisions: Wichtige Architektur-Entscheidungen mit Begründung

Beispiel:
```yaml
modules:
  - name: alu
    type: combinational
    inputs: [a, b, operation]
    outputs: [result, flags]
    parameters: {{width: 8}}
    description: "Arithmetic Logic Unit"
    dependencies: []
  - name: register_file
    type: sequential
    inputs: [clk, rst, read_addr_a, read_addr_b, write_addr, write_data, write_enable]
    outputs: [data_a, data_b]
    parameters: {{width: 8, depth: 16}}
    description: "Register File mit 16 Registern"
    dependencies: []

interfaces:
  alu_to_flags: "flags"
  regfile_to_alu: "data_a, data_b"

clock_domain: "clk"
reset_concept: "async_active_high"
decisions:
  - "Einzel-Takt-Domain für einfache Synchronisation"
  - "Asynchroner Reset für schnelle Initialisierung"
```"""

    def _parse_architecture_yaml(
        self, yaml_str: str, request: str = "", fallback_name: str | None = None
    ) -> dict:
        """Parst YAML und validiert Struktur."""
        import yaml
        import re
        
        if not isinstance(yaml_str, str) or not yaml_str.strip():
            raise ValueError("Invalid architecture YAML: empty response")

        # LLMs variieren die Code-Fence-Schreibweise und liefern gelegentlich
        # JSON statt YAML; beides ist fuer diesen strukturierten Vertrag lesbar.
        yaml_match = re.search(
            r"```(?:yaml|yml|json)?\s*\n?(.*?)\n?```",
            yaml_str,
            re.IGNORECASE | re.DOTALL,
        )
        if yaml_match:
            yaml_str = yaml_match.group(1)

        try:
            data = yaml.safe_load(yaml_str.strip())
        except yaml.YAMLError as exc:
            raise ValueError(f"Invalid architecture YAML: {exc}") from exc

        if not isinstance(data, dict):
            raise ValueError("Invalid architecture YAML: expected a mapping")
        if "modules" not in data:
            raise ValueError("Invalid architecture YAML: missing modules")
        if not isinstance(data["modules"], list) or not data["modules"]:
            raise ValueError("Invalid architecture YAML: modules must be a non-empty list")
        
        # Module validieren und in ModuleInfo konvertieren
        modules = []
        for m in data.get("modules", []):
            if not isinstance(m, dict) or not m.get("name"):
                raise ValueError("Invalid architecture YAML: every module needs a name")
            module = ModuleInfo(
                name=m.get("name", ""),
                type=m.get("type", "module"),
                inputs=m.get("inputs", []),
                outputs=m.get("outputs", []),
                parameters=m.get("parameters", {}),
                description=m.get("description", ""),
                dependencies=m.get("dependencies", []),
            )
            modules.append(module)

        modules = self._normalize_module_names(modules, request, fallback_name)
        requested_top = str(data.get("top_module") or "").strip().lower()
        requested_module = next(
            (module for module in modules if module.name.lower() == requested_top),
            None,
        )
        
        return {
            "modules": modules,
            "top_module": requested_module.name if requested_module else "",
            "interfaces": data.get("interfaces", {}),
            "clock_domain": data.get("clock_domain", "clk"),
            "reset_concept": data.get("reset_concept", "async_active_high"),
            "decisions": data.get("decisions", []),
        }

    def _normalize_module_names(
        self,
        modules: list[ModuleInfo],
        request: str,
        fallback_name: str | None = None,
    ) -> list[ModuleInfo]:
        from src.services.artifact_generator import VHDLArtifactGenerator

        fallback_name = fallback_name or VHDLArtifactGenerator._extract_entity_name(
            request, "my_component"
        )
        reserved_names = {
            "architecture", "begin", "block", "case", "component", "configuration",
            "entity", "end", "generate", "generic", "if", "is", "library", "of",
            "package", "port", "process", "signal", "then", "type", "use", "when",
        }
        rename_map: dict[str, str] = {}
        used_names: set[str] = set()

        for index, module in enumerate(modules):
            original_name = module.name
            normalized = unicodedata.normalize("NFKD", original_name.replace("ß", "ss"))
            normalized = normalized.encode("ascii", "ignore").decode("ascii")
            normalized = re.sub(r"[^a-zA-Z0-9_]", "_", normalized).lower()
            normalized = re.sub(r"_+", "_", normalized).strip("_")
            if not normalized or normalized[0].isdigit():
                normalized = f"c_{normalized}" if normalized else ""

            is_unhelpful = (
                not normalized
                or normalized in reserved_names
                or normalized.startswith((
                    "synthetisier", "synthesier", "optimier", "verbesser",
                    "prompt", "aufgabe", "erstelle", "entwickel", "generier",
                ))
            )
            if is_unhelpful:
                normalized = fallback_name if index == len(modules) - 1 else f"{fallback_name}_block_{index + 1}"
            if normalized in used_names:
                normalized = f"{normalized}_block_{index + 1}"

            rename_map[original_name] = normalized
            used_names.add(normalized)
            module.name = normalized

        for module in modules:
            module.dependencies = [rename_map.get(name, name) for name in module.dependencies]
        return modules

    def _deterministic_architecture(self, request: str, analysis: str) -> dict:
        """Erstellt die Architektur ohne LLM aus der Anforderung ab.

        Liefert dasselbe Schema wie _parse_architecture_yaml (modules als
        ModuleInfo), damit der restliche Ablauf identisch weiterläuft.
        """
        service = DeterministicDesignService()
        architecture = service.build_architecture(request, analysis)
        architecture["decisions"] = architecture.get("decisions", []) or [
            {
                "decision": "Deterministische Architektur aus Anforderung",
                "reason": "LLM nicht verfügbar",
            }
        ]
        return architecture

    def _generate_task_graph(self, modules: list, top_module: str = "") -> dict:
        """Generate a task graph from module dependencies.
        
        Creates tasks for each module implementation and connects them
        based on module dependencies.
        """
        tasks = {}
        dependencies = {}
        
        for m in modules:
            name = m.get("name", "") if isinstance(m, dict) else m.name
            deps = m.get("dependencies", []) if isinstance(m, dict) else []
            task_id = f"implement_{name}"
            
            tasks[task_id] = {
                "id": task_id,
                "type": "implement_hdl",
                "module": name,
                "depends_on": [f"implement_{d}" for d in deps],
            }
            dependencies[task_id] = [f"implement_{d}" for d in deps]
        
        # Add top-level task
        module_name = lambda module: module.get("name", "") if isinstance(module, dict) else module.name
        top_candidates = [
            module for module in modules
            if module_name(module).lower() != "uart"
        ]
        selected_top = next(
            (module for module in top_candidates if module_name(module) == top_module),
            None,
        )
        if selected_top is None:
            leaves = [
                module for module in top_candidates
                if not (module.get("dependencies", []) if isinstance(module, dict) else module.dependencies)
            ]
            selected_top = leaves[-1] if leaves else (top_candidates[-1] if top_candidates else None)
        if selected_top is not None:
            # Top depends on all other modules
            top_deps = [
                f"implement_{module_name(module)}"
                for module in modules if module is not selected_top
            ]
            if top_deps:
                tasks["implement_top"] = {
                    "id": "implement_top",
                    "type": "implement_hdl",
                    "module": "top",
                    "depends_on": top_deps,
                }
                dependencies["implement_top"] = top_deps
        
        # Add verification task
        all_impl_tasks = list(tasks.keys())
        tasks["verify"] = {
            "id": "verify",
            "type": "verify",
            "depends_on": all_impl_tasks,
        }
        dependencies["verify"] = all_impl_tasks
        
        return {
            "tasks": tasks,
            "dependencies": dependencies,
        }

    async def _refine_architecture(self, task: AgentTask) -> AgentResult:
        """Refine the plan through OpenCode without replacing the original request."""
        try:
            manifest = self._plan.plan(
                task.inputs.get("workspace", ""),
                task.inputs.get("request_full", task.inputs.get("request", "")),
                task.id,
                change_request=task.inputs.get("feedback", ""),
            )
            modules = [module_from_manifest(item) for item in manifest["modules"]]
            architecture = ArchitectureInfo(
                status="completed",
                version=task.inputs.get("version", 1) + 1,
                modules=modules,
                top_module=manifest["top_entity"],
                interfaces=manifest.get("interfaces", {}),
                clock_domain=manifest.get("clock_domain", "clk"),
                reset_concept=manifest.get("reset_concept", "async_active_high"),
                decisions=[{"decision": "Plan durch OpenCode verfeinert"}],
                hardware_tests=manifest.get("hardware_tests", []) or [],
            )
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.COMPLETED,
                outputs={
                    "architecture": architecture.model_dump(),
                    "manifest": manifest,
                    "open_questions": manifest.get("open_questions", []),
                },
            )
        except Exception as exc:
            logger.exception("Architecture refinement failed")
            failure_type = getattr(exc, "failure_type", "")
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.FAILED,
                error_message=f"Architecture refinement failed: {exc}",
                diagnostics=[{
                    "type": "architecture_failure",
                    "stage": "architecture",
                    "message": str(exc),
                    **({"failure_type": failure_type} if failure_type else {}),
                    **({"details": exc.to_dict()} if hasattr(exc, "to_dict") else {}),
                }],
            )

    @staticmethod
    def _last_module_name(modules: list) -> str:
        if not modules:
            return ""
        module = modules[-1]
        return module.get("name", "") if isinstance(module, dict) else module.name

    async def _validate_architecture(self, task: AgentTask) -> AgentResult:
        """Validiert Architektur auf Konsistenz."""
        architecture = task.inputs.get("architecture", {})
        
        # Prüfungen durchführen
        issues = []
        modules = architecture.get("modules", [])
        module_names = {m.get("name") for m in modules}
        
        # 1. Alle Dependencies existieren
        for m in modules:
            for dep in m.get("dependencies", []):
                if dep not in module_names:
                    issues.append(f"Module {m['name']} depends on non-existent module {dep}")
        
        # 2. Keine zirkulären Dependencies (einfache Prüfung)
        # TODO: Implementiere echte Cycle-Detection
        
        # 3. Top-Level Module identifizieren (keine Dependencies)
        top_level = [m for m in modules if not m.get("dependencies")]
        if not top_level:
            issues.append("No top-level module found (all modules have dependencies)")
        
        if issues:
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.FAILED,
                error_message="Architecture validation failed",
                diagnostics=[{"type": "validation_error", "issues": issues}],
            )
        
        return AgentResult(
            task_id=task.id,
            status=AgentStatus.COMPLETED,
            outputs={"valid": True, "top_level_modules": [m["name"] for m in top_level]},
        )