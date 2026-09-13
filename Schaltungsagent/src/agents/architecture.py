import logging
import uuid
from typing import Any

from src.domain.agents import BaseAgent, AgentTask, AgentResult, AgentStatus
from src.domain.models import DesignState, ModuleInfo, ArchitectureInfo
from src.domain.models.design_state import Requirement

logger = logging.getLogger(__name__)


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
    ):
        self.modules = modules
        self.interfaces = interfaces
        self.clock_domain = clock_domain
        self.reset_concept = reset_concept
        self.task_graph = task_graph or {}
    
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

    def __init__(self, llm_service, rag_service, event_publisher=None):
        super().__init__("ArchitectureAgent", event_publisher)
        self._llm = llm_service
        self._rag = rag_service

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
        """Erstellt initiale Architektur aus Anforderungen."""
        request = task.inputs.get("request", "")
        analysis = task.inputs.get("analysis", "")
        knowledge = task.inputs.get("knowledge", {})
        domain = task.inputs.get("domain", "vhdl")
        
        # RAG für Architektur-Patterns abfragen
        arch_knowledge = self._rag.retrieve_knowledge(
            f"hardware architecture {request}", domain
        )
        
        # Prompt für Architektur-Erstellung
        prompt = self._build_architecture_prompt(request, analysis, knowledge, arch_knowledge)
        
        try:
            # LLM ruft Architektur-Entscheidung ab
            architecture_yaml = self._llm.generate_code(prompt, temperature=0.2)
            
            # YAML parsen und validieren
            architecture = self._parse_architecture_yaml(architecture_yaml)
            
            # ArchitectureInfo erstellen - decisions als dict konvertieren
            decisions = architecture.get("decisions", [])
            if decisions and isinstance(decisions[0], str):
                decisions = [{"decision": d} for d in decisions]
            
            arch_info = ArchitectureInfo(
                status="completed",
                version=1,
                modules=architecture.get("modules", []),
                interfaces=architecture.get("interfaces", {}),
                clock_domain=architecture.get("clock_domain", "clk"),
                reset_concept=architecture.get("reset_concept", "async_active_high"),
                decisions=decisions,
            )
            
            # Create structured handoff for downstream agents
            handoff = ArchitectureHandoff(
                modules=[m.model_dump() if hasattr(m, 'model_dump') else m for m in arch_info.modules],
                interfaces=arch_info.interfaces,
                clock_domain=arch_info.clock_domain,
                reset_concept=arch_info.reset_concept,
            )
            
            # Generate task graph from module dependencies
            task_graph = self._generate_task_graph(architecture.get("modules", []))
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
                    "raw_yaml": architecture_yaml,
                },
            )
            
        except Exception as e:
            logger.exception("Architecture creation failed")
            self.emit_event("ARCHITECTURE_FAILED", {
                "task_id": task.id,
                "error": str(e),
            })
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.FAILED,
                error_message=f"Architecture creation failed: {e}",
            )

    def _build_architecture_prompt(
        self, request: str, analysis: str, knowledge: dict, arch_knowledge
    ) -> str:
        """Baut Prompt für Architekturentwurf."""
        coding_rules = "\n".join([f"- {r}" for r in knowledge.get("coding_rules", [])])
        ref_designs = "\n".join([f"- {d}" for d in knowledge.get("reference_designs", [])])
        
        return f"""Entwirf eine Hardware-Architektur für folgende Anforderung:

ANFORDERUNG:
{request}

ANALYSE:
{analysis}

CODING REGELN:
{coding_rules}

REFERENZ-DESIGNS:
{ref_designs}

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

    def _parse_architecture_yaml(self, yaml_str: str) -> dict:
        """Parst YAML und validiert Struktur."""
        import yaml
        import re
        
        # YAML aus Code-Block extrahieren falls vorhanden
        yaml_match = re.search(r'```yaml\n(.*?)\n```', yaml_str, re.DOTALL)
        if yaml_match:
            yaml_str = yaml_match.group(1)
        
        data = yaml.safe_load(yaml_str)
        
        if not data or "modules" not in data:
            raise ValueError("Invalid architecture YAML: missing modules")
        
        # Module validieren und in ModuleInfo konvertieren
        modules = []
        for m in data.get("modules", []):
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
        
        return {
            "modules": modules,
            "interfaces": data.get("interfaces", {}),
            "clock_domain": data.get("clock_domain", "clk"),
            "reset_concept": data.get("reset_concept", "async_active_high"),
            "decisions": data.get("decisions", []),
        }

    def _generate_task_graph(self, modules: list) -> dict:
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
        top_modules = [m for m in modules 
                       if not (m.get("dependencies", []) if isinstance(m, dict) else [])]
        if top_modules:
            top_name = top_modules[-1].get("name", "") if isinstance(top_modules[-1], dict) else top_modules[-1].name
            # Top depends on all other modules
            top_deps = [f"implement_{m.get('name', '') if isinstance(m, dict) else m.name}" 
                       for m in modules 
                       if m != top_modules[-1]]
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
        """Verfeinert bestehende Architektur basierend auf Feedback."""
        current_arch = task.inputs.get("current_architecture", {})
        feedback = task.inputs.get("feedback", "")
        
        prompt = f"""Verfeinere die folgende Architektur basierend auf dem Feedback:

AKTUELLE ARCHITEKTUR:
{current_arch}

FEEDBACK:
{feedback}

Erstelle eine aktualisierte YAML-Struktur."""
        
        try:
            architecture_yaml = self._llm.generate_code(prompt, temperature=0.2)
            architecture = self._parse_architecture_yaml(architecture_yaml)
            
            arch_info = ArchitectureInfo(
                status="completed",
                version=task.inputs.get("version", 1) + 1,
                modules=architecture.get("modules", []),
                interfaces=architecture.get("interfaces", {}),
                clock_domain=architecture.get("clock_domain", "clk"),
                reset_concept=architecture.get("reset_concept", "async_active_high"),
                decisions=architecture.get("decisions", []),
            )
            
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.COMPLETED,
                outputs={"architecture": arch_info.model_dump()},
            )
        except Exception as e:
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.FAILED,
                error_message=f"Architecture refinement failed: {e}",
            )

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