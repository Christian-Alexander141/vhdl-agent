import json
import logging
import uuid
from pathlib import Path
from typing import Any

from src.domain.agents import BaseAgent, AgentTask, AgentResult, AgentStatus
from src.domain.models import DesignState, ArchitectureInfo, ModuleInfo

logger = logging.getLogger(__name__)


class HDLAgent(BaseAgent):
    """Implementiert VHDL-Code basierend auf der Architektur.
    
    Aufgaben:
    - VHDL-Entities und Architectures erstellen
    - Interfaces gemäß Architektur einhalten
    - Synthesizable VHDL erzeugen
    - Coding Guidelines einhalten
    - Bei Architektur-Problemen strukturiert melden
    """

    def __init__(
        self,
        llm_service,
        rag_service,
        opencode_service,
        filesystem_service,
        event_publisher=None,
    ):
        super().__init__("HDLAgent", event_publisher)
        self._llm = llm_service
        self._rag = rag_service
        self._opencode = opencode_service
        self._fs = filesystem_service

    @property
    def supported_task_types(self) -> list[str]:
        return ["implement_hdl", "modify_hdl", "fix_hdl", "review_hdl"]

    async def execute(self, task: AgentTask) -> AgentResult:
        task_type = task.type
        
        if task_type == "implement_hdl":
            return await self._implement_hdl(task)
        elif task_type == "modify_hdl":
            return await self._modify_hdl(task)
        elif task_type == "fix_hdl":
            return await self._fix_hdl(task)
        elif task_type == "review_hdl":
            return await self._review_hdl(task)
        else:
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.FAILED,
                error_message=f"Unknown task type: {task_type}",
            )

    async def _implement_hdl(self, task: AgentTask) -> AgentResult:
        """Implementiert VHDL für alle Module der Architektur."""
        architecture = task.inputs.get("architecture", {})
        workspace = task.inputs.get("workspace", "")
        domain = task.inputs.get("domain", "vhdl")
        
        modules = architecture.get("modules", [])
        if not modules:
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.FAILED,
                error_message="No modules in architecture",
            )
        
        # Workspace vorbereiten
        workspace_path = Path(workspace)
        src_dir = workspace_path / "src"
        src_dir.mkdir(parents=True, exist_ok=True)
        
        generated_files = []
        all_errors = []
        
        # Für jedes Modul VHDL generieren
        for module_data in modules:
            module = ModuleInfo(**module_data) if isinstance(module_data, dict) else module_data
            
            try:
                vhdl_code = await self._generate_module_vhdl(module, architecture, domain)
                
                # Datei schreiben
                file_name = f"{module.name}.vhd"
                file_path = src_dir / file_name
                self._fs.write_file(str(file_path), vhdl_code)
                generated_files.append(f"src/{file_name}")
                
                self.emit_event("MODULE_IMPLEMENTED", {
                    "task_id": task.id,
                    "module": module.name,
                    "file": file_name,
                })
                
            except Exception as e:
                logger.exception(f"Failed to generate module {module.name}")
                all_errors.append({"module": module.name, "error": str(e)})
        
        # Testbenches generieren
        tb_files = await self._generate_testbenches(modules, workspace, domain)
        generated_files.extend(tb_files)
        
        if all_errors:
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.FAILED,
                error_message=f"Failed to generate {len(all_errors)} modules",
                outputs={"files": generated_files, "errors": all_errors},
            )
        
        return AgentResult(
            task_id=task.id,
            status=AgentStatus.COMPLETED,
            outputs={
                "files": generated_files,
                "generated_files": generated_files,
            },
        )

    async def _generate_module_vhdl(
        self, module: ModuleInfo, architecture: dict, domain: str
    ) -> str:
        """Generiert VHDL-Code für ein einzelnes Modul."""
        
        # RAG für VHDL-Patterns abfragen
        vhdl_knowledge = self._rag.retrieve_knowledge(
            f"VHDL {module.type} module {module.name}", domain
        )
        
        # Interface-Signale aufbauen
        ports = self._build_port_list(module)
        generics = self._build_generic_list(module)
        
        # Strukturiertes RAG-Wissen aufbauen (mit Fallbacks für robustness)
        coding_rules = getattr(vhdl_knowledge, 'coding_rules', []) or []
        reference_designs = getattr(vhdl_knowledge, 'reference_designs', []) or []
        matched_template = getattr(vhdl_knowledge, 'matched_template', None)
        template_status = getattr(vhdl_knowledge, 'template_status', 'none')
        template_score = getattr(vhdl_knowledge, 'template_score', 0.0)
        template_metadata = getattr(vhdl_knowledge, 'template_metadata', None)
        
        coding_rules_text = ""
        if coding_rules:
            rules = "\n".join(f"- {rule.description}" for rule in coding_rules[:5])
            coding_rules_text = f"\nCODING RULES:\n{rules}"
        
        reference_text = ""
        if reference_designs:
            refs = "\n".join(f"- {ref.name}: {ref.description}" for ref in reference_designs[:3])
            reference_text = f"\nREFERENCE DESIGNS:\n{refs}"
        
        template_text = ""
        if matched_template and template_status == "matched":
            template_text = f"\n--- MATCHED TEMPLATE: {matched_template} (score: {template_score:.2f}) ---"
            if template_metadata:
                meta = template_metadata
                template_text += f"\nPurpose: {getattr(meta, 'purpose', '')}"
                template_text += f"\nInterfaces: {', '.join(getattr(meta, 'interfaces', []))}"
                if hasattr(meta, 'fpga_family') and meta.fpga_family:
                    template_text += f"\nFPGA: {meta.fpga_family}"
                template_text += "\nUse this template as reference, adapt to current requirements."
        
        prompt = f"""Du bist ein VHDL-Experte. Generiere synthesizable VHDL-Code für folgendes Modul:

MODUL:
- Name: {module.name}
- Typ: {module.type} (combinational/sequential/fsm)
- Generics: {generics}
- Ports: {ports}
- Beschreibung: {module.description}
- Dependencies: {module.dependencies}

ARCHITEKTUR-KONTEXT:
- Clock Domain: {architecture.get('clock_domain', 'clk')}
- Reset Concept: {architecture.get('reset_concept', 'async_active_high')}
{coding_rules_text}
{reference_text}
{template_text}

VHDL CODING GUIDELINES:
- IEEE 1076-2008 Standard
- Keine wait-Anweisungen in synthesizable Code
- Asynchroner Reset: process(clk, rst) mit rst in sensitivity list
- Synchroner Reset: process(clk) mit if rst then
- Keine ungebundenen Loops in Kombinatorik
- Alle Signale in sensitivity list (Kombinatorik) oder clock edge (Sequentiell)
- Explizite Typ-Definitionen für Ports

WICHTIG: Generiere NUR den VHDL-Code (Entity + Architecture). Keine Erklärungen."""
        
        vhdl_code = self._llm.generate_code(prompt, temperature=0.1)
        
        # Code validieren und bereinigen
        vhdl_code = self._clean_vhdl_code(vhdl_code)
        
        return vhdl_code

    def _build_port_list(self, module: ModuleInfo) -> str:
        """Erstellt Port-Liste als String."""
        ports = []
        
        # Clock und Reset hinzufügen für sequentielle Module
        if module.type in ["sequential", "fsm"]:
            ports.append("clk : in std_logic")
            ports.append("rst : in std_logic")
        
        # Inputs (ohne clk/rst, die schon oben hinzugefügt wurden)
        for inp in module.inputs:
            if inp not in ["clk", "rst"]:
                ports.append(f"{inp} : in std_logic_vector")
        
        # Outputs
        for out in module.outputs:
            ports.append(f"{out} : out std_logic_vector")
        
        return "; ".join(ports)

    def _build_generic_list(self, module: ModuleInfo) -> str:
        """Erstellt Generic-Liste als String."""
        generics = []
        for name, value in module.parameters.items():
            if isinstance(value, int):
                generics.append(f"{name} : positive := {value}")
            else:
                generics.append(f"{name} : string := \"{value}\"")
        return "; ".join(generics)

    def _clean_vhdl_code(self, code: str) -> str:
        """Bereinigt VHDL-Code von Markdown-Artefakten."""
        import re
        
        # Code-Block Marker entfernen
        code = re.sub(r'^```vhdl\s*', '', code, flags=re.MULTILINE)
        code = re.sub(r'^```\s*', '', code, flags=re.MULTILINE)
        code = code.strip()
        
        return code

    async def _generate_testbenches(
        self, modules: list, workspace: str, domain: str
    ) -> list[str]:
        """Generiert Testbenches für alle Module."""
        workspace_path = Path(workspace)
        tb_dir = workspace_path / "tests"
        tb_dir.mkdir(parents=True, exist_ok=True)
        
        tb_files = []
        
        for module_data in modules:
            module = ModuleInfo(**module_data) if isinstance(module_data, dict) else module_data
            
            # Nur für Leaf-Module oder Haupt-Module Testbenches
            if module.type == "combinational" or not module.dependencies:
                try:
                    tb_code = await self._generate_testbench(module, workspace, domain)
                    
                    file_name = f"{module.name}_tb.vhd"
                    file_path = tb_dir / file_name
                    self._fs.write_file(str(file_path), tb_code)
                    tb_files.append(f"tests/{file_name}")
                    
                except Exception as e:
                    logger.warning(f"Failed to generate testbench for {module.name}: {e}")
        
        return tb_files

    async def _generate_testbench(
        self, module: ModuleInfo, workspace: str, domain: str
    ) -> str:
        """Generiert Testbench für ein Modul."""
        
        vhdl_knowledge = self._rag.retrieve_knowledge(
            f"VHDL testbench {module.name}", domain
        )
        
        ports = self._build_port_list(module)
        
        prompt = f"""Generiere eine VHDL-Testbench für folgendes Modul:

MODUL: {module.name}
PORTS: {ports}
TYP: {module.type}

ANFORDERUNGEN:
- Vollständige Testbench mit Clock/Reset Generation
- Stimulus für alle Input-Kombinationen (kombinatorisch) oder State-Transitions (sequentiell)
- Assertions für erwartete Outputs
- Report am Ende: "TB_COMPLETE: PASS" oder "TB_COMPLETE: FAIL"
- Stop-Time: 20 us für kombinatorisch, 50 us für sequentiell
- GHDL-kompatibel (keine VHDL-2019 Features)

Generiere COMPLETE VHDL Testbench Code."""

        tb_code = self._llm.generate_code(prompt, temperature=0.1)
        return self._clean_vhdl_code(tb_code)

    async def _modify_hdl(self, task: AgentTask) -> AgentResult:
        """Modifiziert existierenden VHDL-Code."""
        workspace = task.inputs.get("workspace", "")
        file_path = task.inputs.get("file_path", "")
        instruction = task.inputs.get("instruction", "")
        
        if not file_path:
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.FAILED,
                error_message="No file path provided",
            )
        
        full_path = Path(workspace) / file_path
        if not self._fs.file_exists(str(full_path)):
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.FAILED,
                error_message=f"File not found: {file_path}",
            )
        
        # Aktuellen Code lesen
        current_code = self._fs.read_file(str(full_path))
        
        # Modifikation via OpenCode
        result = self._opencode.execute(
            workspace,
            f"Modifiziere {file_path} gemäß: {instruction}\n\nAktueller Code:\n{current_code}",
        )
        
        if result.success:
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.COMPLETED,
                outputs={"modified_file": file_path},
            )
        else:
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.FAILED,
                error_message=f"Modification failed: {result.stderr}",
            )

    async def _fix_hdl(self, task: AgentTask) -> AgentResult:
        """Repariert VHDL-Code basierend auf Fehlerinformationen.

        PRODUCTION PATH: Uses OpenCode to patch existing VHDL files.
        Does NOT regenerate all modules from scratch.
        """
        workspace = task.inputs.get("workspace", "")
        error_info = task.inputs.get("error_info", {})
        failed_module = task.inputs.get("failed_module", "")
        architecture = task.inputs.get("architecture", {})
        diagnosis = task.inputs.get("diagnosis", {})
        affected_files = task.inputs.get("affected_files", [])
        original_requirement = task.inputs.get("original_requirement", "")

        # Build comprehensive context for OpenCode
        from src.services.opencode_context import OpenCodeContextBuilder
        context_builder = OpenCodeContextBuilder(self._fs, self._rag)

        context = context_builder.build_context(
            workspace=workspace,
            task={
                "id": task.id,
                "type": "fix_hdl",
                "project_id": task.project_id,
                "inputs": task.inputs,
                "description": f"Repair VHDL code for module {failed_module}",
            },
            architecture=architecture,
            previous_results=[{
                "passed": False,
                "stage": "simulation",
                "error": error_info.get("message", ""),
                "details": error_info.get("details", {}),
            }],
        )

        instruction = f"""{context}

=====================================================================
REPAIR TASK: Fix VHDL code for module '{failed_module}'
=====================================================================

ORIGINAL REQUIREMENT:
{original_requirement}

ARCHITECTURE:
{json.dumps(architecture, indent=2) if architecture else 'Not available'}

FAILED MODULE: {failed_module}
AFFECTED FILES: {', '.join(affected_files) if affected_files else 'auto-detect'}

GHDL ERROR:
{error_info.get('message', 'Unknown error')}

DEBUG DIAGNOSIS:
- failure_type: {diagnosis.get('failure_type', 'unknown')}
- suspected_modules: {diagnosis.get('suspected_modules', [])}
- evidence: {diagnosis.get('evidence', [])}
- recommended_action: {diagnosis.get('recommended_action', 'Investigate error')}

ACCEPTANCE CRITERIA:
- GHDL compilation succeeds (analyze + elaborate)
- GHDL simulation passes (no assertion failures)
- Preserve working modules
- Do not rewrite unrelated files
- Fix the root cause of the reported verification failure
- Run the relevant verification after the modification

INSTRUCTIONS:
1. Read the affected VHDL files listed above
2. Analyze the GHDL error and the debug diagnosis
3. Fix ONLY the root cause in the identified file(s)
4. Preserve all working code - do NOT rewrite unrelated files
5. After fixing, run: ghdl -a --std=08 src/{failed_module}.vhd
6. Then run the full GHDL validation to verify the fix
7. Stop only when the acceptance criteria are satisfied

IMPORTANT:
- This is a REPAIR, not a rewrite. Patch the existing code.
- Preserve working modules. Do not rewrite unrelated files.
- Fix the root cause of the reported verification failure.
- Run the relevant verification after the modification."""

        logger.info("OPENCODE_STARTED module=%s files=%s", failed_module, affected_files)
        self.emit_event("OPENCODE_STARTED", {
            "task_id": task.id,
            "module": failed_module,
            "affected_files": affected_files,
        })

        result = self._opencode.execute(workspace, instruction)

        if result.success:
            logger.info("OPENCODE_COMPLETED module=%s", failed_module)
            self.emit_event("OPENCODE_COMPLETED", {
                "task_id": task.id,
                "module": failed_module,
                "modified_files": affected_files,
                "stdout": result.stdout[-4000:],
                "stderr": result.stderr[-4000:],
            })
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.COMPLETED,
                outputs={
                    "repaired": True,
                    "modified_files": affected_files,
                },
            )
        else:
            logger.error("OPENCODE_FAILED module=%s error=%s", failed_module, result.stderr)
            self.emit_event("OPENCODE_FAILED", {
                "task_id": task.id,
                "module": failed_module,
                "error": result.stderr,
                "stdout": result.stdout[-4000:],
                "stderr": result.stderr[-4000:],
            })
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.FAILED,
                error_message=f"Fix failed: {result.stderr}",
            )

    async def _review_hdl(self, task: AgentTask) -> AgentResult:
        """Reviewed VHDL-Code auf Coding Guidelines."""
        workspace = task.inputs.get("workspace", "")
        files = task.inputs.get("files", [])
        
        issues = []
        for file_path in files:
            full_path = Path(workspace) / file_path
            if self._fs.file_exists(str(full_path)):
                code = self._fs.read_file(str(full_path))
                file_issues = self._check_coding_guidelines(code, file_path)
                issues.extend(file_issues)
        
        if issues:
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.FAILED,
                error_message="Coding guideline violations found",
                diagnostics=[{"type": "style_violation", "issues": issues}],
            )
        
        return AgentResult(
            task_id=task.id,
            status=AgentStatus.COMPLETED,
            outputs={"reviewed_files": len(files), "issues": 0},
        )

    def _check_coding_guidelines(self, code: str, file_path: str) -> list[dict]:
        """Prüft VHDL-Code auf Coding Guidelines."""
        issues = []
        lines = code.split('\n')
        
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            
            # Keine wait in synthesizable Code
            if 'wait' in stripped.lower() and 'testbench' not in file_path.lower():
                issues.append({
                    "file": file_path,
                    "line": i,
                    "rule": "no_wait_in_synthesizable",
                    "message": "wait statement in synthesizable code",
                })
            
            # Sensitivity list completeness check (basic)
            if 'process(' in stripped.lower() and 'begin' not in stripped.lower():
                # Could check sensitivity list completeness
                pass
        
        return issues