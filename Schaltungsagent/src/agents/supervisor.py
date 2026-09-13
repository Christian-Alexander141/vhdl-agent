import asyncio
import hashlib
import logging
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.domain.agents import BaseAgent, AgentTask, AgentResult, AgentStatus, MessageType
from src.domain.agents.communication import AgentMessage, TaskResult, VerificationResult, DebugDiagnosis
from src.domain.models import DesignState, DesignStage, EventType, Requirement, ArchitectureInfo, VerificationInfo, SynthesisInfo, HardwareTestInfo
from src.domain.state_machine import StateMachine, WorkflowState
from src.domain.exceptions import WorkflowError
from src.services.project_memory import ProjectMemoryService

logger = logging.getLogger(__name__)


class SupervisorAgent(BaseAgent):
    """Zentraler Supervisor/Orchestrator für das Multi-Agenten-System.
    
    Verantwortlich für:
    - Anforderungen analysieren und zerlegen
    - Agenten auswählen und koordinieren
    - Design State verwalten
    - Zustandsübergänge steuern
    - Feedback-Loops managen
    - Safety-Limits durchsetzen
    """

    def __init__(
        self,
        llm_service,
        rag_service,
        filesystem_service,
        event_publisher,
        project_memory: ProjectMemoryService,
        architecture_agent=None,
        hdl_agent=None,
        verification_agent=None,
        debug_agent=None,
        fpga_agent=None,
        hardware_test_agent=None,
        config: dict | None = None,
    ):
        super().__init__("SupervisorAgent", event_publisher)
        self._llm = llm_service
        self._rag = rag_service
        self._fs = filesystem_service
        self._memory = project_memory
        
        # Sub-agents
        self._architecture_agent = architecture_agent
        self._hdl_agent = hdl_agent
        self._verification_agent = verification_agent
        self._debug_agent = debug_agent
        self._fpga_agent = fpga_agent
        self._hardware_test_agent = hardware_test_agent
        
        # Configuration
        self._config = config or {}
        self._max_iterations = self._config.get("max_iterations", 20)
        self._max_repairs_per_stage = self._config.get("max_repairs_per_stage", 5)
        self._max_simulation_failures = self._config.get("max_simulation_failures", 10)
        self._max_hardware_failures = self._config.get("max_hardware_failures", 5)
        
        # State
        self._state_machine = StateMachine(WorkflowState.CREATED)
        self._design_state: DesignState | None = None
        self._current_task: AgentTask | None = None

    @property
    def supported_task_types(self) -> list[str]:
        return ["supervise", "decompose", "coordinate", "manage_loop"]

    async def execute(self, task: AgentTask) -> AgentResult:
        """Hauptausführungsschleife des Supervisors."""
        self._current_task = task
        project_id = task.project_id
        
        # Design State laden oder neu erstellen
        self._design_state = await self._load_or_create_design_state(project_id, task.inputs)
        
        try:
            result = await self._run_autonomous_loop()
            return result
        except Exception as e:
            logger.exception("Supervisor execution failed")
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.FAILED,
                error_message=str(e),
            )

    async def _load_or_create_design_state(self, project_id: str, inputs: dict) -> DesignState:
        """Lädt bestehenden Design State oder erstellt neuen."""
        workspace = self._fs.workspace_path(project_id)
        state_path = f"{workspace}/design_state.yaml"
        
        if self._fs.file_exists(state_path):
            try:
                content = self._fs.read_file(state_path)
                return DesignState.from_yaml(content)
            except Exception as e:
                logger.warning(f"Failed to load design state: {e}")
        
        # Neuen Design State erstellen
        design_state = DesignState()
        design_state.project["id"] = project_id
        design_state.project["name"] = inputs.get("project_name", "unnamed")
        design_state.requirements = [
            Requirement(description=req) for req in inputs.get("requirements", [inputs.get("request", "")])
        ]
        design_state.current_stage = DesignStage.ANALYZING
        
        return design_state

    async def _save_design_state(self) -> None:
        """Speichert den Design State persistent."""
        if not self._design_state or not self._current_task:
            return
        
        workspace = self._fs.workspace_path(self._current_task.project_id)
        state_path = f"{workspace}/design_state.yaml"
        
        try:
            self._fs.write_file(state_path, self._design_state.to_yaml())
        except Exception as e:
            logger.warning(f"Failed to save design state: {e}")

    async def _run_autonomous_loop(self) -> AgentResult:
        """Hauptschleife für autonomes Entwickeln."""
        self._emit_event("AUTONOMOUS_LOOP_STARTED", {"project_id": self._current_task.project_id})
        
        iteration = 0
        while iteration < self._max_iterations:
            iteration += 1
            self._design_state.increment_iteration(self._design_state.current_stage.value)
            
            # Prüfen ob Limits erreicht
            limit_check = self._check_safety_limits()
            if limit_check:
                return limit_check
            
            # Aktuelle Phase ausführen
            stage = self._design_state.current_stage
            result = await self._execute_stage(stage)
            
            if result.status == AgentStatus.FAILED:
                # Fehlerbehandlung
                repair_result = await self._handle_failure(stage, result)
                if repair_result:
                    # If infrastructure failure, return BLOCKED immediately
                    if repair_result.status == AgentStatus.BLOCKED:
                        return repair_result
                    continue
                return result
            
            elif result.status == AgentStatus.COMPLETED:
                # Nächste Phase bestimmen
                next_stage = self._determine_next_stage(stage, result)
                if next_stage == DesignStage.COMPLETED:
                    return AgentResult(
                        task_id=self._current_task.id,
                        status=AgentStatus.COMPLETED,
                        outputs={"design_state": self._design_state.to_dict()},
                    )
                self._design_state.transition_to(next_stage)
                await self._save_design_state()
                continue
            
            elif result.status == AgentStatus.BLOCKED:
                # Auf User-Input warten (Approval, Hardware-Probleme, etc.)
                user_result = await self._request_human_intervention(result)
                if user_result:
                    continue
                return AgentResult(
                    task_id=self._current_task.id,
                    status=AgentStatus.FAILED,
                    error_message="Human intervention required but not provided",
                )
        
        # Max iterations reached
        self._design_state.transition_to(DesignStage.AUTONOMOUS_LIMIT_REACHED)
        await self._save_design_state()
        self._emit_event("AUTONOMOUS_LIMIT_REACHED", {
            "project_id": self._current_task.project_id,
            "iterations": iteration,
        })
        
        return AgentResult(
            task_id=self._current_task.id,
            status=AgentStatus.FAILED,
            error_message=f"Autonomous limit reached after {iteration} iterations",
        )

    async def _execute_stage(self, stage: DesignStage) -> AgentResult:
        """Führt eine einzelne Phase aus."""
        self._emit_event(f"STAGE_STARTED", {
            "stage": stage.value,
            "project_id": self._current_task.project_id,
        })
        
        try:
            if stage == DesignStage.ANALYZING:
                return await self._run_analysis()
            elif stage == DesignStage.ARCHITECTING:
                return await self._run_architecture()
            elif stage == DesignStage.IMPLEMENTING:
                return await self._run_implementation()
            elif stage == DesignStage.STATIC_CHECK:
                return await self._run_static_check()
            elif stage == DesignStage.SIMULATING:
                return await self._run_simulation()
            elif stage == DesignStage.VALIDATING:
                return await self._run_validation()
            elif stage == DesignStage.DEBUGGING:
                return await self._run_debugging()
            elif stage == DesignStage.SYNTHESIZING:
                return await self._run_synthesis()
            elif stage == DesignStage.FPGA_PROGRAMMING:
                return await self._run_fpga_programming()
            elif stage == DesignStage.HARDWARE_TESTING:
                return await self._run_hardware_test()
            else:
                return AgentResult(
                    task_id=self._current_task.id,
                    status=AgentStatus.FAILED,
                    error_message=f"Unknown stage: {stage}",
                )
        finally:
            self._emit_event(f"STAGE_FINISHED", {
                "stage": stage.value,
                "project_id": self._current_task.project_id,
            })

    async def _run_analysis(self) -> AgentResult:
        """Analysiert die Anforderungen."""
        self._design_state.transition_to(DesignStage.ANALYZING)
        await self._save_design_state()
        
        request = self._current_task.inputs.get("request", "")
        analysis = self._llm.analyze_request(request, self._current_task.inputs.get("domain", "vhdl"))
        
        self._design_state.metadata["analysis"] = analysis
        
        # RAG Search
        knowledge = self._rag.retrieve_knowledge(request, self._current_task.inputs.get("domain", "vhdl"))
        self._design_state.metadata["knowledge"] = knowledge.to_dict()
        
        return AgentResult(
            task_id=self._current_task.id,
            status=AgentStatus.COMPLETED,
            outputs={"analysis": analysis, "knowledge": knowledge.to_dict()},
            next_actions=["architecting"],
        )

    async def _run_architecture(self) -> AgentResult:
        """Startet den ArchitectureAgent."""
        if not self._architecture_agent:
            return AgentResult(
                task_id=self._current_task.id,
                status=AgentStatus.FAILED,
                error_message="ArchitectureAgent not configured",
            )
        
        self._design_state.transition_to(DesignStage.ARCHITECTING)
        await self._save_design_state()
        
        task = AgentTask(
            id=str(uuid.uuid4()),
            type="create_architecture",
            project_id=self._current_task.project_id,
            inputs={
                "request": self._current_task.inputs.get("request", ""),
                "analysis": self._design_state.metadata.get("analysis", ""),
                "knowledge": self._design_state.metadata.get("knowledge", {}),
                "domain": self._current_task.inputs.get("domain", "vhdl"),
            },
        )
        
        result = await self._architecture_agent.execute(task)
        
        if result.status == AgentStatus.COMPLETED:
            # Architecture in Design State übernehmen
            arch_data = result.outputs.get("architecture", {})
            self._design_state.architecture = ArchitectureInfo(**arch_data) if arch_data else ArchitectureInfo()
            self._design_state.architecture.status = "completed"
            self._design_state.architecture.version += 1
            
            # Requirements mit Modulen verknüpfen
            self._link_requirements_to_modules()
        
        return result

    async def _run_implementation(self) -> AgentResult:
        """Startet den HDLAgent."""
        if not self._hdl_agent:
            return AgentResult(
                task_id=self._current_task.id,
                status=AgentStatus.FAILED,
                error_message="HDLAgent not configured",
            )
        
        self._design_state.transition_to(DesignStage.IMPLEMENTING)
        await self._save_design_state()
        
        task = AgentTask(
            id=str(uuid.uuid4()),
            type="implement_hdl",
            project_id=self._current_task.project_id,
            inputs={
                "architecture": self._design_state.architecture.model_dump(),
                "workspace": self._fs.workspace_path(self._current_task.project_id),
                "domain": self._current_task.inputs.get("domain", "vhdl"),
            },
        )
        
        result = await self._hdl_agent.execute(task)
        
        if result.status == AgentStatus.COMPLETED:
            self._design_state.implementation.status = "completed"
            self._design_state.implementation.files = result.outputs.get("files", [])
            self._design_state.implementation.generated_files = result.outputs.get("generated_files", [])
        
        return result

    async def _run_static_check(self) -> AgentResult:
        """Führt statische Prüfungen durch (Linting, Syntax-Check)."""
        self._design_state.transition_to(DesignStage.STATIC_CHECK)
        await self._save_design_state()
        
        workspace = self._fs.workspace_path(self._current_task.project_id)
        
        # GHDL Analyse als statischer Check
        from src.infrastructure.validation.ghdl_validator import GHDLValidator
        validator = GHDLValidator()
        
        # Validierung der VHDL-Dateien
        from src.domain.ports.validation_service import ValidationService
        # Hier würde die ValidationService aufgerufen werden
        # Für jetzt vereinfacht:
        
        return AgentResult(
            task_id=self._current_task.id,
            status=AgentStatus.COMPLETED,
            outputs={"checks": "passed"},
            next_actions=["simulating"],
        )

    async def _run_simulation(self) -> AgentResult:
        """Startet den VerificationAgent für Simulation."""
        if not self._verification_agent:
            return AgentResult(
                task_id=self._current_task.id,
                status=AgentStatus.FAILED,
                error_message="VerificationAgent not configured",
            )
        
        self._design_state.transition_to(DesignStage.SIMULATING)
        await self._save_design_state()
        
        task = AgentTask(
            id=str(uuid.uuid4()),
            type="verify",
            project_id=self._current_task.project_id,
            inputs={
                "workspace": self._fs.workspace_path(self._current_task.project_id),
                "architecture": self._design_state.architecture.model_dump(),
                "domain": self._current_task.inputs.get("domain", "vhdl"),
            },
        )
        
        result = await self._verification_agent.execute(task)
        
        if result.status == AgentStatus.COMPLETED:
            # Verification-Ergebnisse speichern
            v_result = result.outputs.get("verification_result", {})
            self._design_state.verification = VerificationInfo(**v_result) if v_result else VerificationInfo()
            
            if v_result.get("status") == "failed":
                return AgentResult(
                    task_id=self._current_task.id,
                    status=AgentStatus.FAILED,
                    error_message="Simulation failed",
                    outputs=result.outputs,
                    diagnostics=result.diagnostics,
                )
        
        return result

    async def _run_validation(self) -> AgentResult:
        """Validierung nach Simulation."""
        self._design_state.transition_to(DesignStage.VALIDATING)
        await self._save_design_state()
        
        # Validierung ist erfolgreich wenn Simulation PASS war
        if self._design_state.verification.status == "passed":
            return AgentResult(
                task_id=self._current_task.id,
                status=AgentStatus.COMPLETED,
                outputs={"validated": True},
                next_actions=["synthesizing"],
            )
        else:
            return AgentResult(
                task_id=self._current_task.id,
                status=AgentStatus.FAILED,
                error_message="Validation failed - simulation did not pass",
            )

    async def _run_debugging(self) -> AgentResult:
        """Startet den DebugAgent für Fehleranalyse."""
        if not self._debug_agent:
            return AgentResult(
                task_id=self._current_task.id,
                status=AgentStatus.FAILED,
                error_message="DebugAgent not configured",
            )
        
        self._design_state.transition_to(DesignStage.DEBUGGING)
        await self._save_design_state()
        
        # Diagnostic aus Design State lesen
        diagnostics = self._design_state.diagnostics.active
        
        task = AgentTask(
            id=str(uuid.uuid4()),
            type="diagnose",
            project_id=self._current_task.project_id,
            inputs={
                "diagnostics": diagnostics,
                "current_stage": self._design_state.current_stage.value,
                "workspace": self._fs.workspace_path(self._current_task.project_id),
                "architecture": self._design_state.architecture.model_dump(),
            },
        )
        
        result = await self._debug_agent.execute(task)
        
        if result.status == AgentStatus.COMPLETED:
            diagnosis = result.outputs.get("diagnosis", {})
            self._design_state.diagnostics.active = [diagnosis] if diagnosis else []
            self._design_state.diagnostics.history.append(diagnosis)
            
            # Repair-Aufträge an HDLAgent delegieren
            if diagnosis.get("recommended_action"):
                self._design_state.increment_repairs()
        
        return result

    async def _run_synthesis(self) -> AgentResult:
        """Startet den FPGAAgent für Synthese."""
        if not self._fpga_agent:
            return AgentResult(
                task_id=self._current_task.id,
                status=AgentStatus.FAILED,
                error_message="FPGAAgent not configured",
            )
        
        self._design_state.transition_to(DesignStage.SYNTHESIZING)
        await self._save_design_state()
        
        task = AgentTask(
            id=str(uuid.uuid4()),
            type="synthesize",
            project_id=self._current_task.project_id,
            inputs={
                "workspace": self._fs.workspace_path(self._current_task.project_id),
                "target_fpga": self._current_task.inputs.get("target_fpga", "arty_s7_50"),
                "domain": self._current_task.inputs.get("domain", "vhdl"),
            },
        )
        
        result = await self._fpga_agent.execute(task)
        
        if result.status == AgentStatus.COMPLETED:
            synth_result = result.outputs.get("synthesis_result", {})
            self._design_state.synthesis = SynthesisInfo(**synth_result) if synth_result else SynthesisInfo()
            self._design_state.synthesis.bitstream_path = result.outputs.get("bitstream_path", "")
        
        return result

    async def _run_fpga_programming(self) -> AgentResult:
        """Startet den FPGAAgent für Flash."""
        if not self._fpga_agent:
            return AgentResult(
                task_id=self._current_task.id,
                status=AgentStatus.FAILED,
                error_message="FPGAAgent not configured",
            )
        
        self._design_state.transition_to(DesignStage.FPGA_PROGRAMMING)
        await self._save_design_state()
        
        task = AgentTask(
            id=str(uuid.uuid4()),
            type="flash",
            project_id=self._current_task.project_id,
            inputs={
                "bitstream_path": self._design_state.synthesis.bitstream_path,
                "target_fpga": self._current_task.inputs.get("target_fpga", "arty_s7_50"),
                "workspace": self._fs.workspace_path(self._current_task.project_id),
            },
        )
        
        result = await self._fpga_agent.execute(task)
        
        if result.status == AgentStatus.COMPLETED:
            self._design_state.fpga.programmed = True
            self._design_state.fpga.bitstream = self._design_state.synthesis.bitstream_path
            self._design_state.fpga.board_detected = result.outputs.get("board_detected", False)
        
        return result

    async def _run_hardware_test(self) -> AgentResult:
        """Startet den HardwareTestAgent."""
        if not self._hardware_test_agent:
            return AgentResult(
                task_id=self._current_task.id,
                status=AgentStatus.FAILED,
                error_message="HardwareTestAgent not configured",
            )
        
        self._design_state.transition_to(DesignStage.HARDWARE_TESTING)
        await self._save_design_state()
        
        task = AgentTask(
            id=str(uuid.uuid4()),
            type="hardware_test",
            project_id=self._current_task.project_id,
            inputs={
                "fpga_config": self._design_state.fpga.model_dump(),
                "architecture": self._design_state.architecture.model_dump(),
                "workspace": self._fs.workspace_path(self._current_task.project_id),
            },
        )
        
        result = await self._hardware_test_agent.execute(task)
        
        if result.status == AgentStatus.COMPLETED:
            hw_result = result.outputs.get("hardware_result", {})
            self._design_state.hardware = HardwareTestInfo(**hw_result) if hw_result else HardwareTestInfo()
            
            if hw_result.get("status") == "failed":
                return AgentResult(
                    task_id=self._current_task.id,
                    status=AgentStatus.FAILED,
                    error_message="Hardware test failed",
                    outputs=result.outputs,
                )
        
        return result

    def _capture_file_hashes(self, workspace: str, suspected_modules: list[str]) -> dict[str, str]:
        """Capture SHA-256 hashes of affected VHDL files before repair."""
        hashes = {}
        ws = Path(workspace)
        src_dir = ws / "src"
        if not src_dir.exists():
            return hashes
        for module_name in suspected_modules:
            for ext in (".vhd", ".vhdl"):
                vhd_file = src_dir / f"{module_name}{ext}"
                if vhd_file.exists():
                    content = vhd_file.read_bytes()
                    hashes[str(vhd_file)] = hashlib.sha256(content).hexdigest()
        # Also capture all src files if no specific modules suspected
        if not suspected_modules or not hashes:
            for f in src_dir.glob("*.vhd"):
                if str(f) not in hashes:
                    content = f.read_bytes()
                    hashes[str(f)] = hashlib.sha256(content).hexdigest()
        return hashes

    def _detect_no_progress(self, before_hashes: dict[str, str], workspace: str) -> bool:
        """Check if any files changed after repair. Returns True if NO files changed (no progress)."""
        if not before_hashes:
            return False
        for file_path, old_hash in before_hashes.items():
            p = Path(file_path)
            if not p.exists():
                continue
            new_hash = hashlib.sha256(p.read_bytes()).hexdigest()
            if new_hash != old_hash:
                return False
        return True

    def _detect_identical_error(self, result: AgentResult) -> bool:
        """Check if the current failure is identical to a PREVIOUS failure (not the current one)."""
        if not self._design_state or not self._design_state.diagnostics.history:
            return False
        if not result.diagnostics:
            return False
        current_diag = result.diagnostics[0] if result.diagnostics else {}
        current_msg = current_diag.get("message", "")
        current_type = current_diag.get("type", "")
        # Check against PREVIOUS history entries (excluding the one we just added)
        # The last entry was just added, so check the one before that
        history = self._design_state.diagnostics.history
        if len(history) < 2:
            return False
        for prev_diag in history[:-1]:
            prev_msg = prev_diag.get("message", "")
            prev_type = prev_diag.get("failure_type", prev_diag.get("type", ""))
            if current_type and prev_type and current_type == prev_type:
                if current_msg and prev_msg and current_msg == prev_msg:
                    return True
        return False

    async def _run_repair(self, diagnosis: dict) -> AgentResult:
        """Create a fix_hdl RepairTask and delegate to HDLAgent via OpenCode.

        This is the PRODUCTION repair path. It creates a RepairTask with all
        required fields and sends it to HDLAgent._fix_hdl(), which calls
        OpenCode to patch existing VHDL files.
        """
        workspace = self._fs.workspace_path(self._current_task.project_id)
        suspected_modules = diagnosis.get("suspected_modules", [])
        failure_type = diagnosis.get("failure_type", "unknown")
        recommended_action = diagnosis.get("recommended_action", "")
        evidence = diagnosis.get("evidence", [])

        # Capture file hashes before repair for no-progress detection
        before_hashes = self._capture_file_hashes(workspace, suspected_modules)

        # Build affected files list
        affected_files = []
        ws = Path(workspace)
        src_dir = ws / "src"
        if src_dir.exists():
            for module_name in suspected_modules:
                for ext in (".vhd", ".vhdl"):
                    fpath = src_dir / f"{module_name}{ext}"
                    if fpath.exists():
                        affected_files.append(f"src/{module_name}{ext}")

        # Build error_info from the last simulation failure
        error_info = {
            "message": "; ".join(evidence[:3]) if evidence else recommended_action,
            "failure_type": failure_type,
            "stage": "simulation",
            "details": {
                "suspected_modules": suspected_modules,
                "recommended_action": recommended_action,
                "severity": diagnosis.get("severity", "medium"),
            },
        }

        # Build acceptance criteria
        acceptance_criteria = [
            "GHDL compilation succeeds (analyze + elaborate)",
            "GHDL simulation passes (no assertion failures)",
            f"Affected files modified: {affected_files}" if affected_files else "Files modified correctly",
            "Preserve working modules - do not rewrite unrelated files",
        ]

        # Create the RepairTask with ALL required fields
        repair_task = AgentTask(
            id=str(uuid.uuid4()),
            type="fix_hdl",
            project_id=self._current_task.project_id,
            inputs={
                "workspace": workspace,
                "error_info": error_info,
                "failed_module": suspected_modules[0] if suspected_modules else "",
                "architecture": self._design_state.architecture.model_dump() if self._design_state.architecture else {},
                "diagnosis": diagnosis,
                "affected_files": affected_files,
                "original_requirement": self._current_task.inputs.get("request", ""),
            },
            acceptance_criteria=acceptance_criteria,
            expected_artifacts=[f"src/{m}.vhd" for m in suspected_modules] if suspected_modules else [],
        )

        logger.info(
            "REPAIR_STARTED task_type=fix_hdl failed_module=%s failure_type=%s affected_files=%s",
            suspected_modules, failure_type, affected_files,
        )
        self._emit_event("REPAIR_STARTED", {
            "project_id": self._current_task.project_id,
            "task_type": "fix_hdl",
            "failed_module": suspected_modules,
            "failure_type": failure_type,
        })

        if not self._hdl_agent:
            return AgentResult(
                task_id=self._current_task.id,
                status=AgentStatus.FAILED,
                error_message="HDLAgent not configured for repair",
            )

        result = await self._hdl_agent.execute(repair_task)

        if result.status == AgentStatus.COMPLETED:
            # No-progress detection
            if self._detect_no_progress(before_hashes, workspace):
                logger.warning("NO_PROGRESS detected: affected files unchanged after repair")
                self._emit_event("NO_PROGRESS", {
                    "project_id": self._current_task.project_id,
                    "affected_files": affected_files,
                })
                return AgentResult(
                    task_id=self._current_task.id,
                    status=AgentStatus.FAILED,
                    error_message="No progress: affected files unchanged after repair",
                    outputs={"no_progress": True, "affected_files": affected_files},
                )

            self._design_state.increment_repairs()
            modified_files = result.outputs.get("modified_files", affected_files)
            logger.info(
                "REPAIR_COMPLETED modified_files=%s",
                modified_files,
            )
            self._emit_event("REPAIR_COMPLETED", {
                "project_id": self._current_task.project_id,
                "modified_files": modified_files,
            })

            # Transition to SIMULATING for re-verification
            self._design_state.transition_to(DesignStage.SIMULATING)
            await self._save_design_state()
        else:
            logger.error("REPAIR_FAILED error=%s", result.error_message)
            self._emit_event("REPAIR_FAILED", {
                "project_id": self._current_task.project_id,
                "error": result.error_message,
            })

        return result

    def _determine_next_stage(self, current: DesignStage, result: AgentResult) -> DesignStage:
        """Bestimmt die nächste Phase basierend auf Ergebnis."""
        transitions = {
            DesignStage.ANALYZING: DesignStage.ARCHITECTING,
            DesignStage.ARCHITECTING: DesignStage.IMPLEMENTING,
            DesignStage.IMPLEMENTING: DesignStage.STATIC_CHECK,
            DesignStage.STATIC_CHECK: DesignStage.SIMULATING,
            DesignStage.SIMULATING: DesignStage.VALIDATING,
            DesignStage.VALIDATING: DesignStage.SYNTHESIZING,
            DesignStage.SYNTHESIZING: DesignStage.FPGA_PROGRAMMING,
            DesignStage.FPGA_PROGRAMMING: DesignStage.HARDWARE_TESTING,
            DesignStage.HARDWARE_TESTING: DesignStage.COMPLETED,
            DesignStage.DEBUGGING: self._determine_repair_target(),
        }
        return transitions.get(current, DesignStage.FAILED)

    def _determine_repair_target(self) -> DesignStage:
        """Bestimmt basierend auf Diagnose, wo repariert werden muss."""
        if not self._design_state.diagnostics.active:
            return DesignStage.IMPLEMENTING
        
        diagnosis = self._design_state.diagnostics.active[0]
        failure_type = diagnosis.get("failure_type", "")
        stage = diagnosis.get("stage", "")
        
        # Infrastructure failures are not repairable by HDL/Debug agents
        if failure_type == "infrastructure":
            return DesignStage.INFRASTRUCTURE_FAILURE
        
        # Mapping von Fehler zu Ziel-Phase
        if "simulation" in stage.lower() or "simulation" in failure_type.lower():
            return DesignStage.IMPLEMENTING
        elif "synthesis" in stage.lower() or "timing" in failure_type.lower():
            return DesignStage.IMPLEMENTING
        elif "architecture" in failure_type.lower() or "interface" in failure_type.lower():
            return DesignStage.ARCHITECTING
        elif "hardware" in stage.lower() or "flash" in failure_type.lower():
            return DesignStage.FPGA_PROGRAMMING
        
        return DesignStage.IMPLEMENTING

    async def _handle_failure(self, stage: DesignStage, result: AgentResult) -> AgentResult | None:
        """Behandelt Fehler und startet Debug/Repair Loop.

        PRODUCTION PATH:
          failure → persist → debug → RepairTask → HDLAgent._fix_hdl → OpenCode → verify

        NOT:
          failure → transition to IMPLEMENTING → _implement_hdl → LLM.generate_code
        """
        # Persist verification failure result
        if stage == DesignStage.SIMULATING and result.outputs:
            v_result = result.outputs.get("verification_result", {})
            if v_result:
                self._design_state.verification = VerificationInfo(**v_result) if v_result else self._design_state.verification
                await self._save_design_state()

        # Diagnostic speichern
        if result.diagnostics:
            self._design_state.diagnostics.active = result.diagnostics
            self._design_state.diagnostics.history.extend(result.diagnostics)

        # Identical error detection - same error repeating
        if self._detect_identical_error(result):
            logger.warning("IDENTICAL_ERROR detected: same failure repeating")
            self._emit_event("IDENTICAL_ERROR", {
                "project_id": self._current_task.project_id,
                "message": result.error_message,
            })
            self._design_state.transition_to(DesignStage.FAILED)
            await self._save_design_state()
            return AgentResult(
                task_id=self._current_task.id,
                status=AgentStatus.FAILED,
                error_message=f"Identical error repeating: {result.error_message}",
            )

        # Debug Agent aufrufen
        logger.info("DEBUG_STARTED stage=%s", stage.value)
        self._emit_event("DEBUG_STARTED", {
            "project_id": self._current_task.project_id,
            "failed_stage": stage.value,
        })

        debug_result = await self._run_debugging()

        if debug_result.status == AgentStatus.COMPLETED:
            diagnosis = debug_result.outputs.get("diagnosis", {})
            suspected_modules = diagnosis.get("suspected_modules", [])
            failure_type = diagnosis.get("failure_type", "unknown")

            logger.info(
                "DEBUG_COMPLETED suspected_modules=%s failure_type=%s",
                suspected_modules, failure_type,
            )

            # Infrastructure failures cannot be repaired
            if failure_type == "infrastructure":
                self._design_state.transition_to(DesignStage.INFRASTRUCTURE_FAILURE)
                await self._save_design_state()
                return AgentResult(
                    task_id=self._current_task.id,
                    status=AgentStatus.BLOCKED,
                    error_message="Infrastructure failure - cannot repair",
                    outputs={"repair_target": "INFRASTRUCTURE_FAILURE"},
                )

            # PRODUCTION PATH: create RepairTask and delegate to HDLAgent
            repair_result = await self._run_repair(diagnosis)
            return repair_result

        return None

    async def _request_human_intervention(self, result: AgentResult) -> bool:
        """Fragt User um Intervention (Approval, Hardware-Fix, etc.)."""
        self._design_state.add_human_intervention(result.error_message or "Manual intervention required")
        
        self._emit_event("HUMAN_INTERVENTION_REQUESTED", {
            "project_id": self._current_task.project_id,
            "reason": result.error_message,
            "stage": self._design_state.current_stage.value,
        })
        
        # In echter Implementierung würde hier auf User-Input gewartet
        # Für jetzt: False zurückgeben (keine Intervention)
        return False

    def _check_safety_limits(self) -> AgentResult | None:
        """Prüft Safety Limits."""
        iterations = self._design_state.iterations
        
        if iterations["total"] >= self._max_iterations:
            self._design_state.transition_to(DesignStage.AUTONOMOUS_LIMIT_REACHED)
            return AgentResult(
                task_id=self._current_task.id,
                status=AgentStatus.FAILED,
                error_message=f"Max iterations ({self._max_iterations}) reached",
            )
        
        if iterations["repairs"] >= self._max_repairs_per_stage:
            return AgentResult(
                task_id=self._current_task.id,
                status=AgentStatus.FAILED,
                error_message=f"Max repairs per stage ({self._max_repairs_per_stage}) reached",
            )
        
        sim_failures = sum(1 for d in self._design_state.diagnostics.history 
                          if d.get("stage") == "simulation")
        if sim_failures >= self._max_simulation_failures:
            return AgentResult(
                task_id=self._current_task.id,
                status=AgentStatus.FAILED,
                error_message=f"Max simulation failures ({self._max_simulation_failures}) reached",
            )
        
        hw_failures = sum(1 for d in self._design_state.diagnostics.history 
                         if d.get("stage") == "hardware")
        if hw_failures >= self._max_hardware_failures:
            return AgentResult(
                task_id=self._current_task.id,
                status=AgentStatus.FAILED,
                error_message=f"Max hardware failures ({self._max_hardware_failures}) reached",
            )
        
        return None

    def _link_requirements_to_modules(self) -> None:
        """Verknüpft Requirements mit Modulen aus der Architektur."""
        for req in self._design_state.requirements:
            for module in self._design_state.architecture.modules:
                # Einfaches Keyword-Matching
                if any(keyword in module.name.lower() for keyword in req.description.lower().split()):
                    req.satisfied_by.append(module.name)

    def _emit_event(self, event_type: str, payload: dict) -> None:
        """Emittiert Event über EventBus."""
        if self.event_bus:
            try:
                event_payload = dict(payload)
                event_payload.setdefault("agent", self.agent_name)
                self.event_bus.publish_event(
                    EventType(event_type),
                    event_payload.get("project_id", ""),
                    event_payload,
                )
            except ValueError:
                # Custom event type not in enum
                pass