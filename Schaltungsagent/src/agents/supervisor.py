import asyncio
import hashlib
import logging
import json
import os
import re
import uuid
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from src.domain.agents import BaseAgent, AgentTask, AgentResult, AgentStatus, MessageType, TaskStatus
from src.domain.agents.communication import AgentMessage, TaskResult, VerificationResult, DebugDiagnosis
from src.domain.agents.task_graph import TaskGraph
from src.domain.agents.contract_check import ContractChecker
from src.domain.agents import reference_model as refmodel
from src.domain.agents.repair_routing import RepairTarget, route_repair
from src.domain.agents.test_plan import build_test_plan
from src.domain.models import DesignState, DesignStage, EventType, Requirement, ModuleInfo, ArchitectureInfo, VerificationInfo, SynthesisInfo, HardwareTestInfo
from src.domain.state_machine import StateMachine, WorkflowState
from src.domain.exceptions import WorkflowError, StateMachineError
from src.services.project_memory import ProjectMemoryService
from src.domain_plugins.vhdl.templates import VHDLTemplates
from src.services.fpga_target import AmbiguousTargetError, resolve_fpga_target

logger = logging.getLogger(__name__)
UART_TEMPLATE_VERSION = "1.0.0"
UART_INTERFACE = {
    "clk": {"direction": "in", "type": "std_logic"},
    "rst": {"direction": "in", "type": "std_logic"},
    "uart_rx": {"direction": "in", "type": "std_logic"},
    "uart_tx": {"direction": "out", "type": "std_logic"},
    "rx_data": {"direction": "out", "type": "std_logic_vector(7 downto 0)"},
    "rx_valid": {"direction": "out", "type": "std_logic"},
    "tx_data": {"direction": "in", "type": "std_logic_vector(7 downto 0)"},
    "tx_valid": {"direction": "in", "type": "std_logic"},
    "tx_ready": {"direction": "out", "type": "std_logic"},
}


class SupervisorAgent(BaseAgent):
    """Zentraler Supervisor/Orchestrator für das Multi-Agenten-System.
    
    Verantwortlich für:
    - Anforderungen analysieren und zerlegen
    - Agenten auswählen und koordinieren
    - Design State verwalten
    - Zustandsübergänge steuern
    - Feedback-Loops managen
    - Safety-Limits durchsetzen
    
    Thread-Sicherheit: Pro Projekt wird ein eigener Lock verwaltet,
    um mutable Zustände (_current_task, _design_state) zu isolieren.
    """

    def __init__(
        self,
        filesystem_service,
        event_publisher,
        project_memory: ProjectMemoryService,
        architecture_agent=None,
        hdl_agent=None,
        verification_agent=None,
        debug_agent=None,
        fpga_agent=None,
        hardware_test_agent=None,
        approval_handler: Callable[[str, str], tuple[bool, str]] | None = None,
        validation_service=None,
        config: dict | None = None,
        fpga_registry: dict | None = None,
        model_switcher: Callable[[bool], str] | None = None,
    ):
        super().__init__("SupervisorAgent", event_publisher)
        self._model_switcher = model_switcher
        self._fs = filesystem_service
        self._memory = project_memory
        self._validation_service = validation_service
        self._fpga_registry = fpga_registry
        self._contract_checker = ContractChecker()
        
        # Sub-agents
        self._architecture_agent = architecture_agent
        self._hdl_agent = hdl_agent
        self._verification_agent = verification_agent
        self._debug_agent = debug_agent
        self._fpga_agent = fpga_agent
        self._hardware_test_agent = hardware_test_agent
        self._approval_handler = approval_handler
        
        # Configuration
        self._config = config or {}
        self._max_iterations = self._config.get("max_iterations", 20)
        self._max_repairs_per_stage = self._config.get("max_repairs_per_stage", 5)
        self._max_simulation_failures = self._config.get("max_simulation_failures", 10)
        # "persistent": bei Fehlern eskalieren statt aufzugeben (siehe _escalate).
        self._persistent = self._config.get("repair_policy", "standard") == "persistent"
        self._max_hardware_failures = self._config.get("max_hardware_failures", 5)
        self._heartbeat_interval_seconds = max(
            float(self._config.get("heartbeat_interval_seconds", 20)), 0.1
        )
        self._min_module_coverage = float(self._config.get("min_module_coverage", 1.0))
        self._max_parallel_workers = max(int(self._config.get("max_parallel_workers", 2)), 1)
        self._enforce_contracts = bool(self._config.get("enforce_contracts", True))
        # Mutationsanalyse der Testbenches (Doku Abschnitt 16, Maßnahme B); 0 = aus.
        self._min_mutation_score = float(self._config.get("min_mutation_score", 0.0))
        self._max_mutants = int(self._config.get("max_mutants", 10))
        self._default_fpga = self._config.get("default_fpga", "arty_s7_50")
        
        # State - per-project isolation via locks
        self._state_machine = StateMachine(WorkflowState.CREATED)
        self._design_state: DesignState | None = None
        self._current_task: AgentTask | None = None
        self._project_locks: dict[str, threading.Lock] = {}
        self._global_lock = threading.Lock()

    def _get_project_lock(self, project_id: str) -> threading.Lock:
        """Get or create a lock for a specific project."""
        with self._global_lock:
            if project_id not in self._project_locks:
                self._project_locks[project_id] = threading.Lock()
            return self._project_locks[project_id]

    def _acquire_project_lock(self, project_id: str, timeout: float = 30.0) -> threading.Lock:
        """Acquire the lock for a project. Raises TimeoutError on contention."""
        lock = self._get_project_lock(project_id)
        acquired = lock.acquire(timeout=timeout)
        if not acquired:
            raise TimeoutError(f"Could not acquire lock for project {project_id} within {timeout}s")
        return lock

    def _release_project_lock(self, project_id: str) -> None:
        """Release the lock for a project."""
        lock = self._project_locks.get(project_id)
        if lock and lock.locked():
            lock.release()

    @property
    def supported_task_types(self) -> list[str]:
        return ["supervise", "decompose", "coordinate", "manage_loop"]

    def set_opencode_service(self, service) -> None:
        """Update the shared OpenCode service used by all sub-agents."""
        if self._hdl_agent is not None and hasattr(self._hdl_agent, "_opencode"):
            self._hdl_agent._opencode = service
        if self._verification_agent is not None and hasattr(self._verification_agent, "_opencode"):
            self._verification_agent._opencode = service

    async def execute(self, task: AgentTask) -> AgentResult:
        """Hauptausführungsschleife des Supervisors mit Projekt-Isolation."""
        project_id = task.project_id
        lock = self._acquire_project_lock(project_id)
        try:
            self._current_task = task
            self._design_state = await self._load_or_create_design_state(project_id, task.inputs)
            current_stage = self._design_state.current_stage
            current_stage_name = current_stage.value if isinstance(current_stage, DesignStage) else str(current_stage or WorkflowState.CREATED)
            self._state_machine = StateMachine(current_stage_name)
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
        finally:
            self._release_project_lock(project_id)

    async def _load_or_create_design_state(self, project_id: str, inputs: dict) -> DesignState:
        """Lädt bestehenden Design State oder erstellt neuen."""
        workspace = self._fs.workspace_path(project_id)
        state_path = f"{workspace}/design_state.yaml"
        
        if self._fs.file_exists(state_path):
            try:
                content = self._fs.read_file(state_path)
                design_state = DesignState.from_yaml(content)
                if (
                    design_state.metadata.get("prompt_sha256")
                    and design_state.current_stage == DesignStage.CREATED
                    and not design_state.architecture.modules
                ):
                    design_state.current_stage = DesignStage.ANALYZING
                if not design_state.requirements:
                    request_full = inputs.get("request_full", inputs.get("request", ""))
                    if request_full:
                        design_state.requirements = [Requirement(description=request_full)]
                if inputs.get("request_full"):
                    design_state.metadata.setdefault("request_full", inputs["request_full"])
                if (
                    design_state.current_stage == DesignStage.HARDWARE_TESTING
                    and design_state.fpga.programmed
                    and not getattr(self._hardware_test_agent, "has_real_hardware", False)
                ):
                    # Ohne echte Hardware gibt es keinen Test fortzusetzen; mit
                    # echter Hardware wird der Test nach dem Neustart wiederholt.
                    design_state.current_stage = DesignStage.COMPLETED
                if (
                    design_state.current_stage == DesignStage.IMPLEMENTING
                    and not design_state.metadata.get("uart_required")
                ):
                    design_state.current_stage = DesignStage.UART_INTEGRATION
                if design_state.current_stage == DesignStage.COMPLETED:
                    change_request = str(inputs.get("change_request", ""))
                    if change_request and self._is_hardware_revision_request(change_request):
                        design_state.current_stage = (
                            DesignStage.IMPLEMENTING
                            if design_state.metadata.get("uart_required")
                            else DesignStage.UART_INTEGRATION
                        )
                return design_state
            except Exception as e:
                logger.warning(f"Failed to load design state: {e}")
        
        # Neuen Design State erstellen
        design_state = DesignState()
        design_state.project["id"] = project_id
        design_state.project["name"] = inputs.get(
            "project_name", project_id.rsplit("-", 1)[0]
        )
        design_state.requirements = [
            Requirement(description=req) for req in inputs.get(
                "requirements", [inputs.get("request_full", inputs.get("request", ""))]
            )
        ]
        design_state.metadata["request_full"] = inputs.get(
            "request_full", inputs.get("request", "")
        )
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
        """Hauptschleife; schaltet ein per Eskalation gewähltes Fallback-Modell danach zurück."""
        try:
            return await self._run_autonomous_loop_inner()
        finally:
            self._restore_model()

    async def _run_autonomous_loop_inner(self) -> AgentResult:
        """Hauptschleife für autonomes Entwickeln."""
        self._emit_event("AUTONOMOUS_LOOP_STARTED", {"project_id": self._current_task.project_id})

        if self._normalize_stage(self._design_state.current_stage) == DesignStage.COMPLETED:
            return AgentResult(
                task_id=self._current_task.id,
                status=AgentStatus.COMPLETED,
                outputs={"design_state": self._design_state.to_dict()},
            )
        
        iteration = 0
        while iteration < self._max_iterations:
            iteration += 1
            current_stage = self._design_state.current_stage
            current_stage_name = current_stage.value if isinstance(current_stage, DesignStage) else str(current_stage or WorkflowState.CREATED)
            self._design_state.increment_iteration(current_stage_name)
            
            # Prüfen ob Limits erreicht
            limit_check = self._check_safety_limits()
            if limit_check:
                return limit_check
            
            # Aktuelle Phase ausführen
            stage = self._design_state.current_stage
            try:
                result = await self._execute_stage(stage)
            except Exception as exc:
                # Ein Agent hat eine Ausnahme durchgereicht: als fehlgeschlagene
                # Phase behandeln, damit Diagnose und Routing greifen.
                result = self._result_from_exception(exc, f"Phase {self._normalize_stage(stage).value}")

            if result.status == AgentStatus.FAILED:
                # Fehlerbehandlung
                try:
                    repair_result = await self._handle_failure(stage, result)
                except Exception as exc:
                    # Auch die Reparatur selbst darf den Workflow nicht ohne
                    # Diagnose beenden; der Fehler wird als Eingriff gemeldet.
                    failure = self._result_from_exception(exc, "Reparatur")
                    self._design_state.diagnostics.history.extend(failure.diagnostics)
                    self._design_state.add_human_intervention(failure.error_message)
                    await self._save_design_state()
                    return AgentResult(
                        task_id=self._current_task.id,
                        status=AgentStatus.BLOCKED,
                        error_message=failure.error_message,
                        diagnostics=failure.diagnostics,
                    )
                if repair_result:
                    # If infrastructure failure, return BLOCKED immediately
                    if repair_result.status == AgentStatus.BLOCKED:
                        return repair_result
                    if self._normalize_stage(self._design_state.current_stage) in self._TERMINAL_STAGES:
                        await self._save_design_state()
                        return repair_result
                    continue
                return result
            
            elif result.status == AgentStatus.COMPLETED:
                # Nächste Phase bestimmen
                next_stage = self._determine_next_stage(stage, result)
                if next_stage == DesignStage.COMPLETED:
                    self._safe_transition_to(DesignStage.COMPLETED)
                    self._design_state.metadata["last_completed_request"] = (
                        self._current_task.inputs.get("request", "")
                    )
                    self._design_state.metadata["completed_runs"] = (
                        self._design_state.metadata.get("completed_runs", 0) + 1
                    )
                    await self._save_design_state()
                    return AgentResult(
                        task_id=self._current_task.id,
                        status=AgentStatus.COMPLETED,
                        outputs={
                            "design_state": self._design_state.to_dict(),
                            "hardware_validated": self._design_state.hardware.status == "passed",
                            "message": self._completion_message(),
                        },
                    )
                self._safe_transition_to(next_stage)
                await self._save_design_state()
                continue
            
            elif result.status == AgentStatus.BLOCKED:
                # Auf User-Input warten (Approval, Hardware-Probleme, etc.)
                user_result = await self._request_human_intervention(result)
                if user_result:
                    continue
                await self._save_design_state()
                return AgentResult(
                    task_id=self._current_task.id,
                    status=AgentStatus.BLOCKED,
                    error_message=(
                        f"Human intervention required: {result.error_message}"
                        if result.error_message
                        else "Human intervention required but not provided"
                    ),
                    outputs=result.outputs,
                )
        
        # Max iterations reached
        self._safe_transition_to(DesignStage.AUTONOMOUS_LIMIT_REACHED)
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

    def _result_from_exception(self, exc: Exception, subject: str) -> AgentResult:
        """Wandelt eine unerwartete Ausnahme in ein klassifizierbares Ergebnis um."""
        if isinstance(exc, WorkflowError):
            message = f"{subject}: {exc}"
            failure_type = exc.failure_type
            details = exc.to_dict()
        else:
            message = f"{subject}: unerwarteter Fehler {type(exc).__name__}: {exc}"
            failure_type = ""
            details = {"type": type(exc).__name__, "message": str(exc)}
        logger.error("%s", message, exc_info=not isinstance(exc, WorkflowError))
        return AgentResult(
            task_id=self._current_task.id,
            status=AgentStatus.FAILED,
            error_message=message,
            diagnostics=[{
                "type": "agent_exception",
                "message": message,
                **({"failure_type": failure_type} if failure_type else {}),
                "details": details,
            }],
        )

    def _completion_message(self) -> str:
        hardware = self._design_state.hardware
        if hardware.status == "passed":
            return (
                f"FPGA erfolgreich geflasht und Hardwaretest bestanden "
                f"({hardware.passed} Test(s), {hardware.test_mode}). Workflow abgeschlossen."
            )
        return (
            "FPGA erfolgreich geflasht. Workflow abgeschlossen. Es wurde KEIN "
            "automatischer Hardwaretest ausgeführt (keine echte UART-Schnittstelle "
            "konfiguriert); die Board-Funktion ist nicht validiert. Bitte teste die "
            "Hardware und sende bei Problemen deine Änderungswünsche."
        )

    def _normalize_stage(self, stage: DesignStage | str | None) -> DesignStage:
        """Normalize persisted string stages back to the enum used by the runtime."""
        if isinstance(stage, DesignStage):
            return stage
        if isinstance(stage, str):
            try:
                return DesignStage(stage)
            except ValueError:
                normalized = stage.strip().upper()
                for enum_value in DesignStage:
                    if enum_value.value == normalized:
                        return enum_value
        return DesignStage.CREATED

    @staticmethod
    def _is_hardware_revision_request(request: str) -> bool:
        lowered = request.lower()
        revision_hints = (
            "problem", "fehler", "falsch", "geht nicht", "funktioniert nicht",
            "nicht funktioniert", "leuchtet nicht", "reagiert nicht", "bleibt aus",
            "keine ausgabe", "kein signal", "statt", "soll ", "muss ",
            "ändern", "aender", "ändere", "anpass",
            "ergänz", "ergaenz", "hinzufügen", "hinzufuegen", "entfernen",
            "korrigier", "verbesser", "fix", "bug", "issue", "broken",
            "wrong", "not working", "doesn't work", "instead of", "should ",
            "change", "modify",
            "please add", "please change",
        )
        return any(hint in lowered for hint in revision_hints)

    async def _execute_stage(self, stage: DesignStage | str) -> AgentResult:
        """Führt eine einzelne Phase aus."""
        normalized_stage = self._normalize_stage(stage)
        self._emit_event(f"STAGE_STARTED", {
            "stage": normalized_stage.value,
            "project_id": self._current_task.project_id,
        })
        heartbeat_stop = threading.Event()
        heartbeat_thread = threading.Thread(
            target=self._emit_stage_heartbeats,
            args=(heartbeat_stop, normalized_stage.value),
            daemon=True,
        )
        heartbeat_thread.start()
        
        try:
            if normalized_stage == DesignStage.ANALYZING:
                return await self._run_analysis()
            elif normalized_stage == DesignStage.ARCHITECTING:
                return await self._run_architecture()
            elif normalized_stage == DesignStage.UART_INTEGRATION:
                return await self._run_uart_integration()
            elif normalized_stage == DesignStage.IMPLEMENTING:
                return await self._run_implementation()
            elif normalized_stage == DesignStage.STATIC_CHECK:
                return await self._run_static_check()
            elif normalized_stage == DesignStage.SIMULATING:
                return await self._run_simulation()
            elif normalized_stage == DesignStage.VALIDATING:
                return await self._run_validation()
            elif normalized_stage == DesignStage.DEBUGGING:
                return await self._run_debugging()
            elif normalized_stage == DesignStage.SYNTHESIZING:
                return await self._run_synthesis()
            elif normalized_stage == DesignStage.FPGA_PROGRAMMING:
                return await self._run_fpga_programming()
            elif normalized_stage == DesignStage.HARDWARE_TESTING:
                return await self._run_hardware_test()
            else:
                return AgentResult(
                    task_id=self._current_task.id,
                    status=AgentStatus.FAILED,
                    error_message=f"Unknown stage: {normalized_stage}",
                )
        finally:
            heartbeat_stop.set()
            heartbeat_thread.join(timeout=1)
            self._emit_event(f"STAGE_FINISHED", {
                "stage": normalized_stage.value,
                "project_id": self._current_task.project_id,
            })

    def _emit_stage_heartbeats(
        self, stop_event: threading.Event, stage_name: str
    ) -> None:
        stage_labels = {
            "SYNTHESIZING": "Synthese",
            "IMPLEMENTING": "Implementierung",
            "FPGA_PROGRAMMING": "FPGA-Flash",
        }
        stage_label = stage_labels.get(stage_name, stage_name.lower().replace("_", " "))
        elapsed = 0
        while not stop_event.wait(self._heartbeat_interval_seconds):
            elapsed += self._heartbeat_interval_seconds
            self._emit_event("AGENT_HEARTBEAT", {
                "project_id": self._current_task.project_id,
                "stage": stage_name,
                "elapsed_seconds": int(elapsed),
                "message": f"Ich arbeite weiter an {stage_label} ({int(elapsed)} s).",
            })

    async def _run_analysis(self) -> AgentResult:
        """Analysiert die Anforderungen."""
        self._design_state.transition_to(DesignStage.ANALYZING)
        await self._save_design_state()
        
        request = self._design_state.metadata.get(
            "request_full",
            self._current_task.inputs.get("request_full", self._current_task.inputs.get("request", "")),
        )
        manifest = self._current_task.inputs.get("plan_manifest", {})
        analysis = (
            f"OpenCode-Plan mit {len(manifest.get('modules', []))} Modulen; "
            f"Top-Entity: {manifest.get('top_entity', 'offen')}"
        )
        
        self._design_state.metadata["analysis"] = analysis
        self._check_toolchain()

        target_result = self._resolve_target(request)
        if target_result is not None:
            return target_result

        return AgentResult(
            task_id=self._current_task.id,
            status=AgentStatus.COMPLETED,
            outputs={"analysis": analysis, "target_fpga": self._design_state.fpga.target},
            next_actions=["architecting"],
        )

    def _registry(self) -> dict:
        if self._fpga_registry is None:
            from src.config import load_fpga_registry
            self._fpga_registry = load_fpga_registry()
        return self._fpga_registry

    def _resolve_target(self, request: str) -> AgentResult | None:
        """Normalisiert das Ziel-FPGA früh und speichert es im DesignState.

        Liefert ein BLOCKED-Ergebnis mit Rückfrage, wenn das Ziel mehrdeutig ist.
        """
        registry = self._registry()
        explicit = self._current_task.inputs.get("target_fpga") or None
        try:
            target = resolve_fpga_target(
                request,
                list(registry),
                explicit=explicit,
                default=self._default_fpga,
            )
        except AmbiguousTargetError as exc:
            self._design_state.metadata["open_questions"] = [
                *self._design_state.metadata.get("open_questions", []),
                f"Für welches FPGA soll entworfen werden? ({', '.join(exc.candidates)})",
            ]
            self._design_state.diagnostics.active = [{
                "type": "target_ambiguous",
                "failure_type": "target_ambiguous",
                "stage": "analysis",
                "message": str(exc),
            }]
            return AgentResult(
                task_id=self._current_task.id,
                status=AgentStatus.BLOCKED,
                error_message=str(exc),
                outputs={"target_candidates": exc.candidates},
            )
        self._design_state.fpga.target = target.key
        board = registry.get(target.key)
        if board is not None:
            self._design_state.fpga.programmer = getattr(board, "programmer", "vivado")
            self._design_state.synthesis.fpga_part = getattr(board, "part", "")
        self._design_state.metadata["target_fpga_source"] = target.source
        return None

    def _target_fpga(self) -> str:
        """Ziel-FPGA aus dem DesignState (Fallback für ältere Zustände)."""
        if not self._design_state.fpga.target:
            self._resolve_target(self._design_state.metadata.get("request_full", ""))
        return (
            self._design_state.fpga.target
            or self._current_task.inputs.get("target_fpga")
            or self._default_fpga
        )

    def _check_toolchain(self) -> None:
        """Fehlt Vivado bei eingeschalteter Synthese, gleich zu Beginn melden.

        Früher fiel das erst nach Implementierung und Simulation auf (eine
        Stunde später) und wurde als Designfehler gemeldet.
        """
        if not self._config.get("synthesis_enabled", True) or not self._fpga_agent:
            return
        service = getattr(self._fpga_agent, "_bitstream_service", None)
        if service is None or not hasattr(service, "toolchain_available"):
            return
        if service.toolchain_available():
            return
        message = (
            f"Vivado nicht gefunden ('{getattr(service, '_vivado_binary', 'vivado')}'). Entwurf und Simulation "
            "laufen, die Synthese wird aber scheitern; vivado.binary in den Einstellungen prüfen."
        )
        self._design_state.metadata["toolchain_warning"] = message
        self._emit_event("TOOLCHAIN_WARNING", {"project_id": self._current_task.project_id, "message": message})


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
                "request": self._design_state.metadata.get("request_full", self._current_task.inputs.get("request", "")),
                "request_full": self._design_state.metadata.get("request_full", self._current_task.inputs.get("request", "")),
                "manifest": self._current_task.inputs.get("plan_manifest", {}),
                "change_request": self._current_task.inputs.get("change_request", ""),
                "analysis": self._design_state.metadata.get("analysis", ""),
                "domain": self._current_task.inputs.get("domain", "vhdl"),
                "workspace": self._fs.workspace_path(self._current_task.project_id),
            },
        )
        
        result = await self._architecture_agent.execute(task)
        
        if result.status == AgentStatus.COMPLETED:
            # Architecture in Design State übernehmen
            arch_data = result.outputs.get("architecture", {})
            self._design_state.architecture = ArchitectureInfo(**arch_data) if arch_data else ArchitectureInfo()
            manifest = result.outputs.get("manifest", {})
            if manifest.get("project_name"):
                self._design_state.project["name"] = manifest["project_name"]
                self._design_state.metadata["project_name"] = manifest["project_name"]
            self._design_state.metadata["plan_manifest"] = manifest
            self._design_state.metadata["open_questions"] = result.outputs.get("open_questions", [])
            if not self._design_state.architecture.top_module:
                self._design_state.architecture.top_module = self._last_module_name(
                    self._design_state.architecture.modules
                )
            self._design_state.architecture.status = "completed"
            self._design_state.architecture.version += 1
            
            # Requirements mit Modulen verknüpfen
            self._link_requirements_to_modules()
        
        return result

    def _uart_required(self) -> bool:
        """UART-Echo-Brücke nur, wenn sie gebraucht wird (siehe hardware_test.uart_integration).

        Früher wurde sie in jedes Projekt eingebaut: zusätzliches Modul,
        nachträglich umgebautes Top-Level und eine Abweichung vom
        Manifest-Contract – auch wenn niemand UART verlangt hatte.
        """
        mode = str(self._config.get("uart_integration", "auto")).lower()
        if mode == "always":
            return True
        if mode == "off":
            return False
        if getattr(self._hardware_test_agent, "has_real_hardware", False):
            return True
        if self._design_state.architecture.hardware_tests:
            return True
        request = self._design_state.metadata.get(
            "request_full", self._current_task.inputs.get("request_full", self._current_task.inputs.get("request", "")),
        )
        return bool(re.search(r"\buart\b", request or "", re.IGNORECASE))

    async def _run_uart_integration(self) -> AgentResult:
        """Make UART a persistent architectural requirement before HDL generation."""
        architecture = self._design_state.architecture
        modules = architecture.modules
        if not self._uart_required():
            self._design_state.metadata.update({
                "uart_required": False,
                "uart_integration_status": "skipped",
            })
            await self._save_design_state()
            return AgentResult(
                task_id=self._current_task.id,
                status=AgentStatus.COMPLETED,
                outputs={"uart_required": False, "top_module": architecture.top_module},
            )
        before = self._architecture_snapshot(architecture)
        non_uart_modules = [module for module in modules if module.name.lower() != "uart"]
        non_uart_names = {module.name for module in non_uart_modules}
        if (
            not architecture.top_module
            or architecture.top_module.lower() == "uart"
            or architecture.top_module not in non_uart_names
        ):
            architecture.top_module = self._last_module_name(non_uart_modules)
        if not architecture.top_module:
            return AgentResult(
                task_id=self._current_task.id,
                status=AgentStatus.FAILED,
                error_message="Cannot integrate UART without an original top module",
            )

        uart_modules = [module for module in modules if module.name.lower() == "uart"]
        uart_module = uart_modules[0] if uart_modules else None
        if uart_module is not None:
            uart_module.name = "uart"
        if len(uart_modules) > 1:
            architecture.modules = [
                module for module in modules
                if module.name.lower() != "uart"
            ] + [uart_module]
        if uart_module is None:
            uart_module = ModuleInfo(
                name="uart",
                type="sequential",
                inputs=["clk", "rst", "uart_rx", "tx_data", "tx_valid"],
                outputs=["uart_tx", "rx_data", "rx_valid", "tx_ready"],
                parameters={"CLOCK_FREQ_HZ": 100_000_000, "BAUD_RATE": 115_200},
                description="8N1 UART transmitter and receiver for FPGA hardware testing",
            )
            architecture.modules.append(uart_module)
        uart_module.inputs = list(dict.fromkeys([
            *uart_module.inputs, "clk", "rst", "uart_rx", "tx_data", "tx_valid",
        ]))
        uart_module.outputs = list(dict.fromkeys([
            *uart_module.outputs, "uart_tx", "rx_data", "rx_valid", "tx_ready",
        ]))
        uart_module.parameters.setdefault("CLOCK_FREQ_HZ", 100_000_000)
        uart_module.parameters.setdefault("BAUD_RATE", 115_200)
        uart_module.parameters.setdefault("DATA_BITS", 8)
        uart_module.parameters.setdefault("PARITY", "none")
        uart_module.parameters.setdefault("STOP_BITS", 1)
        existing_uart_interface = architecture.interfaces.get("uart", {})
        existing_ports = (
            existing_uart_interface.get("ports", {})
            if isinstance(existing_uart_interface, dict) else {}
        )
        architecture.interfaces["uart"] = {
            **(existing_uart_interface if isinstance(existing_uart_interface, dict) else {}),
            "module": "uart",
            "ports": {**existing_ports, **UART_INTERFACE},
            "baud_rate": uart_module.parameters.get("BAUD_RATE", 115_200),
            "data_bits": 8,
            "parity": "none",
            "stop_bits": 1,
        }
        # Nur bei echter Änderung hochzählen: jede neue Version invalidiert
        # abhängige Implementierungs-Tasks und erzwingt Neugenerierung.
        if self._architecture_snapshot(architecture) != before:
            architecture.version += 1
            architecture.updated_at = datetime.now(timezone.utc).isoformat()

        self._design_state.metadata.update({
            "uart_required": True,
            "uart_module": "uart",
            "uart_template_version": UART_TEMPLATE_VERSION,
            "uart_integration_status": "integrated",
            "uart_template_path": str(
                Path(__file__).resolve().parents[1]
                / "domain_plugins" / "vhdl" / "templates.py"
            ),
        })
        await self._save_design_state()
        return AgentResult(
            task_id=self._current_task.id,
            status=AgentStatus.COMPLETED,
            outputs={
                "uart_required": True,
                "uart_module": "uart",
                "top_module": architecture.top_module,
                "module_count": len(architecture.modules),
            },
        )

    @staticmethod
    def _architecture_snapshot(architecture) -> str:
        data = architecture.model_dump(exclude={"version", "created_at", "updated_at"})
        return json.dumps(data, sort_keys=True, default=str)

    @staticmethod
    def _last_module_name(modules: list) -> str:
        if not modules:
            return ""
        module = modules[-1]
        return module.name if hasattr(module, "name") else module.get("name", "")

    async def _run_implementation(self) -> AgentResult:
        """Implementiert alle Module über einen TaskGraph.

        Für jedes Modul wird ein Implement-Task mit Datei-Property
        (_fs.src/<name>.vhd) und Interface-Contract erzeugt. Tasks mit
        Modul-Abhängigkeiten werden sequenziell, unabhängige Tasks parallel
        ausgeführt. Ein Top-Level-Integrations-Task (falls mehrere Module)
        bindet die Module. Der TaskGraph wird dauerhaft gespeichert.
        """
        if not self._hdl_agent:
            return AgentResult(
                task_id=self._current_task.id,
                status=AgentStatus.FAILED,
                error_message="HDLAgent not configured",
            )
        
        self._design_state.transition_to(DesignStage.IMPLEMENTING)
        await self._save_design_state()
        await self._ensure_reference_model()
        
        architecture = self._design_state.architecture.model_dump()
        modules = architecture.get("modules", [])
        if not modules:
            return AgentResult(
                task_id=self._current_task.id,
                status=AgentStatus.FAILED,
                error_message="No modules in architecture for implementation",
            )
        
        request = self._design_state.metadata.get(
            "request_full", self._current_task.inputs.get("request_full", self._current_task.inputs.get("request", ""))
        )
        change_request = self._current_task.inputs.get("change_request", "")
        analysis = self._design_state.metadata.get("analysis", "")
        workspace = self._fs.workspace_path(self._current_task.project_id)
        domain = self._current_task.inputs.get("domain", "vhdl")
        
        # --- TaskGraph aufbauen (Module + Top-Integration) ---
        graph = TaskGraph()
        module_tasks: dict[str, str] = {}  # module name -> task id
        
        for module_data in modules:
            if isinstance(module_data, dict):
                name = module_data.get("name", "")
                deps = module_data.get("dependencies", [])
            else:
                name = getattr(module_data, "name", "")
                deps = getattr(module_data, "dependencies", [])
            
            if not name:
                continue

            uart_template = VHDLTemplates.render("uart", "vhdl")
            uart_testbench = VHDLTemplates.render("uart", "testbench")
            uart_handoff = {
                "uart_required": bool(self._design_state.metadata.get("uart_required")),
                "uart_module": "uart",
                "uart_template_path": self._design_state.metadata.get("uart_template_path", ""),
                "uart_template": uart_template,
                "uart_interface": UART_INTERFACE,
                "uart_adaptation_required": True,
                "uart_testbench": uart_testbench,
            }
            
            task_id = f"implement_module_{name}"
            module_tasks[name] = task_id
            task = AgentTask(
                id=task_id,
                type="implement_module",
                project_id=self._current_task.project_id,
                depends_on=[module_tasks.get(d, f"implement_module_{d}") for d in deps],
                inputs={
                    "module": module_data if isinstance(module_data, dict) else module_data.model_dump(),
                    "architecture": architecture,
                    "workspace": workspace,
                    "domain": domain,
                    "request": request,
                    "request_full": request,
                    "change_request": change_request,
                    "analysis": analysis,
                    "plan_manifest": self._current_task.inputs.get("plan_manifest", {}),
                    "interfaces": architecture.get("interfaces", {}),
                    "clock_domain": architecture.get("clock_domain", "clk"),
                    "reset_concept": architecture.get("reset_concept", "async_active_high"),
                    **uart_handoff,
                },
                acceptance_criteria=[
                    f"Entity '{name}' mit korrektem Interface erzeugt",
                    "VHDL ist GHDL-kompilierbar",
                    "Ports entsprechen dem Interface-Contract der Architektur",
                ],
                expected_artifacts=[f"src/{name}.vhd"],
            )
            graph.add_task(task, owned_files=[f"src/{name}.vhd"])
        
        # Top-Level-Integrations-Task (nur bei mehreren Modulen sinnvoll)
        non_uart_modules = [
            module for module in modules
            if (module.get("name", "") if isinstance(module, dict) else module.name).lower() != "uart"
        ]
        top_module = architecture.get("top_module") or (
            non_uart_modules[-1].get("name") if non_uart_modules and isinstance(non_uart_modules[-1], dict)
            else getattr(non_uart_modules[-1], "name", "") if non_uart_modules else ""
        )
        integration_task_id = None
        # Steht das Top-Level selbst als Modul im Manifest, implementiert es
        # bereits sein Modul-Task (nach allen Abhängigkeiten); ein zweiter
        # Task für dieselbe Datei würde sie überschreiben.
        if (
            len(modules) > 1
            and not self._design_state.metadata.get("uart_required")
            and top_module not in module_tasks
        ):
            integration_task_id = "implement_top"
            graph.add_task(
                AgentTask(
                    id=integration_task_id,
                    type="implement_top",
                    project_id=self._current_task.project_id,
                    depends_on=list(module_tasks.values()),
                    inputs={
                        "architecture": architecture,
                        "workspace": workspace,
                        "domain": domain,
                        "request": request,
                        "request_full": request,
                        "change_request": change_request,
                        "plan_manifest": self._current_task.inputs.get("plan_manifest", {}),
                        "analysis": analysis,
                    },
                    acceptance_criteria=[
                        "Top-Level-Entity instanziiert alle Module",
                        "Ports der Module sind verdrahtet",
                    ],
                    expected_artifacts=[f"src/{top_module}.vhd"] if top_module else [],
                ),
                owned_files=[f"src/{top_module}.vhd"] if top_module else None,
            )
        
        if self._config.get("implementation_mode") == "single_session":
            # Ein OpenCode-Aufruf für das ganze Projekt: gemeinsamer Kontext
            # statt kalter Einzelaufrufe je Modul. Gates, Reparatur und
            # Hardware-Stufen bleiben unverändert.
            owned = [f"src/{name}.vhd" for name in module_tasks]
            graph = TaskGraph()
            integration_task_id = None
            graph.add_task(
                AgentTask(
                    id="implement_project",
                    type="implement_project",
                    project_id=self._current_task.project_id,
                    inputs={
                        "architecture": architecture,
                        "workspace": workspace,
                        "domain": domain,
                        "request": request,
                        "request_full": request,
                        "change_request": change_request,
                        "analysis": analysis,
                        "uart_required": bool(self._design_state.metadata.get("uart_required")),
                        "uart_template": VHDLTemplates.render("uart", "vhdl"),
                        "uart_testbench": VHDLTemplates.render("uart", "testbench"),
                    },
                    acceptance_criteria=[
                        "Alle Module und das Top-Level sind implementiert",
                        "Jedes Modul hat eine Testbench unter tests/",
                        "GHDL analysiert, elaboriert und simuliert ohne Fehler",
                    ],
                    expected_artifacts=owned,
                ),
                owned_files=owned,
            )

        # --- Wiederaufnahme: unveränderte, abgeschlossene Tasks übernehmen ---
        reused, rerun = self._reuse_completed_tasks(graph, workspace, architecture, change_request)

        self._emit_event("TASK_GRAPH_CREATED", {
            "project_id": self._current_task.project_id,
            "task_count": len(graph.get_all_tasks()),
            "module_count": len(modules),
            "reused_tasks": reused,
            "scheduled_tasks": rerun,
        })
        self._persist_task_graph(workspace, graph)

        # --- Batches sequentiell, Tasks innerhalb eines Batches parallel ---
        graph_files: list[str] = []
        all_errors: list[dict] = []
        for task_id in reused:
            graph_files.extend(graph.get_task(task_id).result.get("files", []) or [])
        logger.info(
            "IMPLEMENTATION_GRAPH_STARTED project=%s modules=%d tasks=%d reused=%d",
            self._current_task.project_id, len(modules), len(graph.get_all_tasks()), len(reused),
        )

        semaphore = asyncio.Semaphore(self._max_parallel_workers)

        async def run_task(task: AgentTask) -> AgentResult:
            # HDL-Aufträge blockieren (OpenCode-Subprozess); jeder Worker
            # bekommt daher einen eigenen Thread mit eigener Event-Loop.
            async with semaphore:
                try:
                    return await asyncio.to_thread(asyncio.run, self._hdl_agent.execute(task))
                except Exception as exc:  # Worker-Absturz isolieren
                    logger.exception("HDL worker failed for %s", task.id)
                    return AgentResult(task_id=task.id, status=AgentStatus.FAILED, error_message=str(exc))

        for batch in graph.get_parallel_batches():
            runnable = []
            for task in batch:
                failed_deps = [
                    dep.id for dep in graph.get_dependencies(task.id)
                    if dep.status not in (TaskStatus.COMPLETED, TaskStatus.PASSED)
                ]
                if failed_deps:
                    graph.update_task_status(
                        task.id, TaskStatus.BLOCKED,
                        error=f"blocked by failed dependencies: {failed_deps}",
                    )
                    self._emit_event("TASK_BLOCKED", {
                        "project_id": self._current_task.project_id,
                        "task": task.id,
                        "blocked_by": failed_deps,
                    })
                    continue
                task.context["attempts"] = int(task.context.get("attempts", 0)) + 1
                graph.mark_running(task.id, worker_id=f"hdl_worker_{len(runnable) + 1}")
                runnable.append(task)
            if not runnable:
                continue

            self._emit_event("PARALLEL_BATCH_STARTED", {
                "project_id": self._current_task.project_id,
                "batch": [t.id for t in runnable],
                "max_parallel_workers": self._max_parallel_workers,
            })
            results = await asyncio.gather(*[run_task(t) for t in runnable])

            for task, result in zip(runnable, results):
                if result.status == AgentStatus.COMPLETED:
                    graph.update_task_status(
                        task.id,
                        TaskStatus.COMPLETED,
                        result=result.outputs or {},
                    )
                    graph_files.extend(result.outputs.get("files", []) or [])
                else:
                    graph.update_task_status(
                        task.id,
                        TaskStatus.FAILED,
                        result=result.outputs or {},
                        error=result.error_message or "module implementation failed",
                    )
                    all_errors.append({
                        "task": task.id,
                        "module": (task.inputs.get("module") or {}).get("name", task.id)
                        if isinstance(task.inputs.get("module"), dict)
                        else task.id,
                        "error": result.error_message,
                        "failure_type": next(
                            (d.get("failure_type") for d in result.diagnostics or [] if d.get("failure_type")), ""
                        ),
                    })
            self._emit_event("PARALLEL_BATCH_COMPLETED", {
                "project_id": self._current_task.project_id,
                "batch": [t.id for t in runnable],
                "failed": [e["task"] for e in all_errors],
            })
            # Checkpoint nach jedem Batch: ein Neustart wiederholt nur offene Tasks.
            graph.clear_invalidated()
            self._persist_task_graph(workspace, graph)

        # --- TaskGraph persistieren ---
        self._persist_task_graph(workspace, graph)
        self._design_state.metadata["task_graph"] = graph.to_dict()
        
        if all_errors:
            self._emit_event("IMPLEMENTATION_GRAPH_FAILED", {
                "project_id": self._current_task.project_id,
                "failed": all_errors,
            })
            return AgentResult(
                task_id=self._current_task.id,
                status=AgentStatus.FAILED,
                error_message=(
                    f"Failed to implement {len(all_errors)} module(s):\n"
                    + "\n".join(e["error"] or e["task"] for e in all_errors)
                ),
                outputs={"files": graph_files, "errors": all_errors},
                diagnostics=[
                    {
                        "type": "implementation_failure",
                        "stage": "implementation",
                        "modules": [e["module"]],
                        "message": e["error"] or f"{e['module']} implementation failed",
                        **({"failure_type": e["failure_type"]} if e["failure_type"] else {}),
                    }
                    for e in all_errors
                ],
            )
        
        self._design_state.implementation.status = "completed"
        self._design_state.implementation.files = graph_files
        self._design_state.implementation.generated_files = graph_files
        
        self._emit_event("IMPLEMENTATION_GRAPH_COMPLETED", {
            "project_id": self._current_task.project_id,
            "files": graph_files,
            "tasks": len(graph.get_all_tasks()),
        })
        
        return AgentResult(
            task_id=self._current_task.id,
            status=AgentStatus.COMPLETED,
            outputs={
                "files": graph_files,
                "generated_files": graph_files,
                "task_graph": graph.to_dict(),
                "integration_task": integration_task_id if integration_task_id else "single_top_module",
            },
        )

    def _run_key(self, change_request: str) -> str:
        """Kennung des aktuellen Auftrags.

        Gleich bei Wiederaufnahme nach Absturz, neu nach jedem abgeschlossenen
        Lauf (auch bei wortgleichem Änderungswunsch).
        """
        completed_runs = self._design_state.metadata.get("completed_runs", 0)
        return hashlib.sha256(f"{completed_runs}:{change_request}".encode()).hexdigest()[:16]

    @staticmethod
    def _task_fingerprint(task: AgentTask, architecture: dict) -> str:
        """Hash des Contracts, den ein Implementierungs-Task umsetzen muss."""
        def contract(module: dict) -> dict:
            return {k: v for k, v in module.items() if k not in ("status", "files")}

        if task.type == "implement_module":
            module = contract(dict(task.inputs.get("module") or {}))
            name = module.get("name", "")
            payload = {
                "module": module,
                "interfaces": {
                    key: value for key, value in (architecture.get("interfaces") or {}).items()
                    if isinstance(value, dict)
                    and name in (value.get("from"), value.get("to"), value.get("module"))
                },
                "clock": architecture.get("clock_domain"),
                "reset": architecture.get("reset_concept"),
            }
        else:
            payload = {
                "modules": [contract(dict(m)) for m in architecture.get("modules", [])],
                "interfaces": architecture.get("interfaces"),
                "top": architecture.get("top_module"),
            }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode()
        ).hexdigest()[:16]

    def _load_task_graph(self, workspace: str) -> TaskGraph | None:
        path = f"{workspace}/task_graph.json"
        try:
            if not self._fs.file_exists(path):
                return None
            return TaskGraph.from_dict(json.loads(self._fs.read_file(path)))
        except Exception as exc:
            logger.warning("Ignoring unreadable task graph %s: %s", path, exc)
            return None

    def _reuse_completed_tasks(
        self,
        graph: TaskGraph,
        workspace: str,
        architecture: dict,
        change_request: str,
    ) -> tuple[list[str], list[str]]:
        """Übernimmt abgeschlossene Tasks aus dem persistierten Graphen.

        Ein Task wird wiederverwendet, wenn er im selben Auftrag bereits
        abgeschlossen wurde, sein Contract-Fingerprint unverändert ist und
        seine Artefakte existieren. Ändert sich ein Contract, werden der Task
        und alle von ihm abhängigen Tasks neu ausgeführt; alle anderen bleiben
        unangetastet.
        """
        run_key = self._run_key(change_request)
        for task in graph.get_all_tasks():
            task.context["fingerprint"] = self._task_fingerprint(task, architecture)
            task.context["run_key"] = run_key

        forced = set(self._design_state.metadata.pop("invalidated_modules", []) or [])
        previous = self._load_task_graph(workspace)
        if previous is None:
            return [], [t.id for t in graph.get_all_tasks()]

        contract_changed: set[str] = set()
        rerun: set[str] = set()
        for task in graph.get_all_tasks():
            old = previous.get_task(task.id)
            module = task.inputs.get("module") or {}
            module_name = module.get("name", "") if isinstance(module, dict) else ""
            if old is None or old.context.get("fingerprint") != task.context["fingerprint"]:
                contract_changed.add(task.id)
                rerun.add(task.id)
            elif (
                old.status not in (TaskStatus.COMPLETED, TaskStatus.PASSED)
                or old.context.get("run_key") != run_key
                or module_name in forced
                or not all(Path(workspace, f).exists() for f in task.expected_artifacts)
            ):
                rerun.add(task.id)

        # Contract-Änderungen invalidieren abhängige Tasks (transitiv).
        frontier = list(contract_changed)
        while frontier:
            current = frontier.pop()
            for dependent in graph.get_dependents(current):
                if dependent.id not in rerun:
                    rerun.add(dependent.id)
                    frontier.append(dependent.id)

        reused = []
        for task in graph.get_all_tasks():
            old = previous.get_task(task.id)
            if task.id in rerun:
                if old is not None and old.status in (TaskStatus.COMPLETED, TaskStatus.PASSED):
                    self._emit_event("TASK_INVALIDATED", {
                        "project_id": self._current_task.project_id,
                        "task": task.id,
                        "reason": "contract_changed" if task.id in contract_changed else "rerun_required",
                    })
                continue
            task.status = TaskStatus.COMPLETED
            task.result = {**(old.result or {}), "reused": True}
            task.context["attempts"] = old.context.get("attempts", 1)
            graph.ownership.release(task.id)
            reused.append(task.id)
        return reused, sorted(rerun)

    def _persist_task_graph(self, workspace: str, graph: TaskGraph) -> None:
        """Speichert den TaskGraph atomar im Workspace (Checkpoint)."""
        try:
            content = json.dumps(graph.to_dict(), indent=2, ensure_ascii=False)
            path = f"{workspace}/task_graph.json"
            temporary = f"{path}.tmp"
            self._fs.write_file(temporary, content)
            if Path(temporary).exists():
                os.replace(temporary, path)
            else:  # Filesystem-Abstraktion ohne echte Dateien (Tests)
                self._fs.write_file(path, content)
            logger.info(
                "TASK_GRAPH_SAVED workspace=%s tasks=%d",
                workspace, len(graph.get_all_tasks()),
            )
        except Exception as e:
            logger.warning("Failed to persist task graph: %s", e)

    def _check_contracts(self, workspace: str) -> dict:
        """ContractChecker gegen die aktuelle Architektur; Ergebnis wird versioniert."""
        architecture = self._design_state.architecture.model_dump()
        self._emit_event("CONTRACT_CHECK_STARTED", {
            "project_id": self._current_task.project_id,
            "architecture_version": self._design_state.architecture.version,
        })
        result = self._contract_checker.check(architecture, workspace)
        record = {
            **result.to_dict(),
            "architecture_version": self._design_state.architecture.version,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "summary": result.summary(),
            "error_modules": sorted({v.module for v in result.errors}),
        }
        self._design_state.verification.contract_check = record
        self._emit_event(
            "CONTRACT_CHECK_PASSED" if result.passed else "CONTRACT_CHECK_FAILED",
            {
                "project_id": self._current_task.project_id,
                "violations": [v.to_dict() for v in result.violations][:20],
            },
        )
        return record

    async def _run_static_check(self) -> AgentResult:
        """Gatekeeper vor der Simulation: Architektur-Contracts + GHDL-Analyse."""
        self._design_state.transition_to(DesignStage.STATIC_CHECK)
        await self._save_design_state()

        workspace = self._fs.workspace_path(self._current_task.project_id)

        contract = self._check_contracts(workspace)
        if self._enforce_contracts and not contract["passed"]:
            await self._save_design_state()
            return AgentResult(
                task_id=self._current_task.id,
                status=AgentStatus.FAILED,
                error_message=f"Contract violation: {contract['summary']}",
                outputs={"checks": "failed", "contract_check": contract},
                diagnostics=[{
                    "type": "contract_violation",
                    "failure_type": "contract_violation",
                    "stage": "static_check",
                    "message": f"Contract violation: {contract['summary']}",
                    "modules": contract["error_modules"],
                    "details": {"violations": contract["violations"]},
                }],
            )

        self._refresh_model_testbench(workspace)

        validator = self._validation_service
        if validator is None:
            from src.infrastructure.validation.ghdl_validator import GHDLValidator
            validator = GHDLValidator()
        domain = self._current_task.inputs.get("domain", "vhdl")
        if self._validation_service is None:
            result = await asyncio.to_thread(validator.validate, workspace, domain)
        else:
            result = validator.validate(workspace, domain)
            if asyncio.iscoroutine(result):
                result = await result
        validation = result.to_dict() if hasattr(result, "to_dict") else {}
        if result.passed:
            return AgentResult(
                task_id=self._current_task.id,
                status=AgentStatus.COMPLETED,
                outputs={"checks": "passed", "validation": validation, "contract_check": contract},
                next_actions=["simulating"],
            )
        return AgentResult(
            task_id=self._current_task.id,
            status=AgentStatus.FAILED,
            error_message=result.message,
            outputs={"checks": "failed", "validation": validation, "contract_check": contract},
            diagnostics=[{
                "type": "validation_failure", "message": result.message, "stage": "static_check",
                "details": validation.get("details", {}),
            }],
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
        self._record_verification(result.outputs.get("verification_result", {}))

        if result.status == AgentStatus.COMPLETED:
            if self._design_state.verification.status == "failed":
                return AgentResult(
                    task_id=self._current_task.id,
                    status=AgentStatus.FAILED,
                    error_message="Simulation failed",
                    outputs=result.outputs,
                    diagnostics=result.diagnostics,
                )

        return result

    def _record_verification(self, v_result: dict) -> None:
        """Speichert ein Simulationsergebnis versioniert im DesignState."""
        if not v_result:
            return
        previous = self._design_state.verification
        workspace = self._fs.workspace_path(self._current_task.project_id)
        test_plan = build_test_plan(
            self._design_state.architecture.model_dump(),
            workspace,
            [r.model_dump() for r in self._design_state.requirements],
        )
        entry = {
            "status": v_result.get("status", "pending"),
            "architecture_version": self._design_state.architecture.version,
            "tests_passed": v_result.get("tests_passed", 0),
            "tests_failed": v_result.get("tests_failed", 0),
            "coverage": test_plan["coverage"],
            "uncovered": test_plan["uncovered"],
            "run_at": datetime.now(timezone.utc).isoformat(),
        }
        self._design_state.verification = VerificationInfo(
            status=entry["status"],
            passed=entry["tests_passed"],
            failed=entry["tests_failed"],
            coverage=test_plan["coverage"],
            last_run=entry["run_at"],
            architecture_version=entry["architecture_version"],
            test_plan=test_plan,
            contract_check=previous.contract_check,
            history=[*previous.history, entry][-20:],
        )

    async def _run_validation(self) -> AgentResult:
        """Gate vor der Synthese: Simulation, Contracts und Testplan-Abdeckung."""
        self._design_state.transition_to(DesignStage.VALIDATING)
        await self._save_design_state()

        verification = self._design_state.verification
        current_version = self._design_state.architecture.version
        problems: list[dict] = []

        if verification.status != "passed":
            problems.append({
                "failure_type": "functional_simulation_error",
                "message": "Validation failed - simulation did not pass",
            })
        if verification.architecture_version != current_version:
            problems.append({
                "failure_type": "testbench_error",
                "message": (
                    f"Simulation result belongs to architecture v{verification.architecture_version}, "
                    f"current is v{current_version}"
                ),
            })
        contract = verification.contract_check or {}
        if self._enforce_contracts and (
            not contract.get("passed") or contract.get("architecture_version") != current_version
        ):
            problems.append({
                "failure_type": "contract_violation",
                "message": f"Contract violation: {contract.get('summary') or 'contract check missing for current architecture'}",
                "modules": contract.get("error_modules", []),
            })
        uncovered = verification.test_plan.get("uncovered", [])
        if verification.coverage < self._min_module_coverage:
            problems.append({
                "failure_type": "coverage_gap",
                "message": (
                    f"Coverage gap: {verification.coverage:.0%} of modules simulated "
                    f"(required {self._min_module_coverage:.0%}); "
                    f"not covered by any simulated testbench: {', '.join(uncovered)}"
                ),
                "modules": uncovered,
            })

        if not problems:
            weak = await self._mutation_gate()
            if weak:
                problems.append(weak)

        if not problems:
            for requirement in self._design_state.requirements:
                plan = verification.test_plan.get("requirements", {}).get(requirement.id, {})
                requirement.verified = bool(plan.get("covered"))
            return AgentResult(
                task_id=self._current_task.id,
                status=AgentStatus.COMPLETED,
                outputs={"validated": True, "coverage": verification.coverage},
                next_actions=["synthesizing"],
            )
        return AgentResult(
            task_id=self._current_task.id,
            status=AgentStatus.FAILED,
            error_message=problems[0]["message"],
            diagnostics=[{"type": "validation_gate", "stage": "validation", **p} for p in problems],
        )

    async def _mutation_gate(self) -> dict | None:
        """Erkennen die Testbenches absichtlich fehlerhafte Varianten des Entwurfs?

        Bei zu niedriger Quote genau ein gezielter Nachbesserungsversuch der
        Testbenches; danach nur noch Warnung. Ein Gate, das einen korrekten
        Entwurf endlos blockiert (vgl. Golden-Vektoren im Benchmark), ist
        schlimmer als eine Lücke in der Testgüte.
        """
        if self._min_mutation_score <= 0:
            return None
        from src.domain.agents.mutation import run_mutation_analysis
        from src.infrastructure.validation.ghdl_validator import GHDLValidator

        workspace = self._fs.workspace_path(self._current_task.project_id)
        validator = self._validation_service if self._validation_service is not None else GHDLValidator()
        try:
            report = await asyncio.to_thread(run_mutation_analysis, workspace, validator, self._max_mutants)
        except Exception as exc:
            logger.exception("Mutation analysis failed")
            self._design_state.metadata["mutation"] = {"error": str(exc)[:500]}
            return None
        meta = self._design_state.metadata
        meta["mutation"] = report
        self._design_state.verification.test_plan["mutation_score"] = report["score"]
        self._emit_event("MUTATION_ANALYSIS", {
            "project_id": self._current_task.project_id,
            "score": report["score"], "killed": len(report["killed"]),
            "survived": len(report["survived"]), "invalid": len(report["invalid"]),
        })
        score = report["score"]
        if score is None or score >= self._min_mutation_score:
            return None
        if meta.get("mutation_repair_done"):
            meta["mutation_warning"] = (
                f"Mutationsquote {score:.0%} unter {self._min_mutation_score:.0%} auch nach Nachbesserung; "
                "fortgesetzt (mögliche äquivalente Mutanten)."
            )
            self._emit_event("MUTATION_WARNING", {"project_id": self._current_task.project_id, "message": meta["mutation_warning"]})
            return None
        meta["mutation_repair_done"] = True
        undetected = "; ".join(s["description"] for s in report["survived"][:5])
        return {
            "failure_type": "weak_testbench",
            "message": (
                f"Weak testbench: mutation score {score:.0%} (required {self._min_mutation_score:.0%}); "
                f"undetected mutants: {undetected}"
            ),
            "modules": sorted({s["module"] for s in report["survived"]}),
        }

    async def _run_debugging(self) -> AgentResult:
        """Startet den DebugAgent und hängt das verbindliche Reparaturziel an."""
        if not self._debug_agent:
            return AgentResult(
                task_id=self._current_task.id,
                status=AgentStatus.FAILED,
                error_message="DebugAgent not configured",
            )

        self._safe_transition_to(DesignStage.DEBUGGING)
        await self._save_design_state()

        diagnostics = self._design_state.diagnostics.active

        task = AgentTask(
            id=str(uuid.uuid4()),
            type="diagnose",
            project_id=self._current_task.project_id,
            inputs={
                "diagnostics": diagnostics,
                "current_stage": str(self._design_state.metadata.get("failed_stage", self._design_state.current_stage)),
                "workspace": self._fs.workspace_path(self._current_task.project_id),
                "architecture": self._design_state.architecture.model_dump(),
            },
        )

        result = await self._debug_agent.execute(task)

        if result.status == AgentStatus.COMPLETED:
            diagnosis = result.outputs.get("diagnosis", {})
            if diagnosis:
                diagnosis.setdefault("stage", self._design_state.metadata.get("failed_stage", ""))
                target = route_repair(diagnosis.get("failure_type", ""), self._contracts_ok())
                diagnosis["repair_target"] = target.value
                diagnosis["architecture_version"] = self._design_state.architecture.version
                diagnosis["diagnosed_at"] = datetime.now(timezone.utc).isoformat()
                result.outputs["diagnosis"] = diagnosis
            self._design_state.diagnostics.active = [diagnosis] if diagnosis else []
            self._design_state.diagnostics.history.append(diagnosis)
            await self._save_design_state()

        return result

    def _contracts_ok(self) -> bool | None:
        """Contract-Status der aktuellen Architekturversion (None = unbekannt)."""
        record = self._design_state.verification.contract_check or {}
        if record.get("architecture_version") != self._design_state.architecture.version:
            return None
        return bool(record.get("passed"))

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
                "target_fpga": self._target_fpga(),
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
                "target_fpga": self._target_fpga(),
                "workspace": self._fs.workspace_path(self._current_task.project_id),
            },
        )

        if self._approval_handler:
            approved, feedback = self._approval_handler(
                self._current_task.project_id,
                self._design_state.synthesis.bitstream_path,
            )
            if not approved:
                self._emit_event("APPROVAL_REJECTED", {
                    "project_id": self._current_task.project_id,
                    "feedback": feedback,
                })
                return AgentResult(
                    task_id=self._current_task.id,
                    status=AgentStatus.BLOCKED,
                    error_message=feedback or "Bitstream approval rejected",
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
                # Golden-Vektor-Simulation bereits grün? Weicht die Hardware
                # trotzdem ab, ist das kein Infra-/Board-Fehler, sondern eine
                # Software/Hardware-Diskrepanz (siehe hardware_test.py).
                "verification_passed": self._design_state.verification.status == "passed",
            },
        )

        result = await self._hardware_test_agent.execute(task)
        hw_result = result.outputs.get("hardware_result", {})
        if hw_result:
            self._design_state.hardware = HardwareTestInfo(
                status=hw_result.get("status", "pending"),
                test_mode=hw_result.get("test_mode", "NONE"),
                passed=hw_result.get("passed", 0),
                failed=hw_result.get("failed", 0),
                last_run=datetime.now(timezone.utc).isoformat(),
                communication_log=hw_result.get("tests", []),
            )

        if result.status == AgentStatus.SKIPPED:
            # Kein echter Test gelaufen: kein Erfolg, aber auch kein Designfehler.
            return AgentResult(
                task_id=self._current_task.id,
                status=AgentStatus.COMPLETED,
                outputs={**result.outputs, "hardware_validated": False},
            )
        if result.status == AgentStatus.COMPLETED and (
            hw_result.get("status") != "passed" or hw_result.get("test_mode") != "REAL_HARDWARE"
        ):
            return AgentResult(
                task_id=self._current_task.id,
                status=AgentStatus.FAILED,
                error_message="Hardware test did not pass on real hardware",
                outputs=result.outputs,
                diagnostics=result.diagnostics,
            )
        return result

    # ------------------------------------------------------------------
    # Differentieller Test gegen das Python-Referenzmodell (Doku Abschnitt 16, Maßnahme A)
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Eskalation statt Aufgeben (repair_policy = "persistent")
    # ------------------------------------------------------------------

    # Versuchszahl je Fehler (Fehlerklasse + Modul) -> Maßnahme
    _ESCALATION_LADDER = (
        (2, "repair"),        # gezielte Reparatur
        (4, "regenerate"),    # Modul vollständig neu schreiben
        (5, "rearchitect"),   # Architektur/Plan dieses Teils überarbeiten
        (7, "switch_model"),  # Fallback-Modell, dann wieder reparieren
    )

    def _escalate(self, failure_type: str, diagnosis: dict, target: RepairTarget) -> tuple[RepairTarget, str]:
        """Wählt je nach bisherigen Versuchen für denselben Fehler die nächste Maßnahme.

        Früher: nach 3 Reparaturen insgesamt Abbruch, bei gleichem Fehler sofort.
        Jetzt wird bei wiederholtem Scheitern die Maßnahme gewechselt; erst nach
        allen Stufen geht der Fehler mit einer Zusammenfassung an den Benutzer.
        Werkzeug-, Board- und Ressourcenprobleme (Ziel HUMAN) bleiben unverändert.
        """
        if target == RepairTarget.HUMAN:
            return target, "human"
        module = (diagnosis.get("suspected_modules") or [""])[0]
        key = f"{failure_type}|{module}"
        counts = self._design_state.metadata.setdefault("escalation", {})
        attempt = int(counts.get(key, 0)) + 1
        counts[key] = attempt
        action = next((a for limit, a in self._ESCALATION_LADDER if attempt <= limit), "human")
        if diagnosis.get("regenerate_model"):
            action = "repair"  # Modellprüfung (Maßnahme A) hat Vorrang
        if action == "regenerate" and target not in (RepairTarget.HDL, RepairTarget.FPGA):
            action = "repair"
        if action == "switch_model" and (self._model_switcher is None or self._design_state.metadata.get("fallback_model_active")):
            action = "repair"
        if action == "rearchitect":
            target = RepairTarget.ARCHITECTURE
        if action == "human":
            target = RepairTarget.HUMAN
            log = self._design_state.metadata.get("escalation_log", [])
            diagnosis["recommended_action"] = (
                f"Nach {attempt - 1} Versuchen für '{failure_type}' ({module or 'Gesamtentwurf'}) nicht gelöst. "
                f"Versucht: {', '.join(dict.fromkeys(self._ESCALATION_LABELS[e['action']] for e in log if e['key'] == key and e['action'] != 'human')) or 'gezielte Reparatur'}."
            )
        self._design_state.metadata.setdefault("escalation_log", []).append(
            {"key": key, "attempt": attempt, "action": action, "at": datetime.now(timezone.utc).isoformat()}
        )
        self._emit_event("ESCALATION", {
            "project_id": self._current_task.project_id,
            "failure_type": failure_type, "module": module, "attempt": attempt, "action": action,
            "message": f"{failure_type} ({module or 'Entwurf'}), Versuch {attempt}: {self._ESCALATION_LABELS[action]}",
        })
        return target, action

    _ESCALATION_LABELS = {
        "repair": "gezielte Reparatur",
        "regenerate": "Modul wird neu geschrieben",
        "rearchitect": "Architektur wird überarbeitet",
        "switch_model": "Wechsel auf das Fallback-Modell",
        "human": "Eingriff erforderlich",
    }

    def _switch_to_fallback_model(self) -> None:
        if self._model_switcher is None or self._design_state.metadata.get("fallback_model_active"):
            return
        try:
            model = self._model_switcher(True)
        except Exception:
            logger.exception("Switching to fallback model failed")
            return
        self._design_state.metadata["fallback_model_active"] = model
        logger.info("Escalation: switched OpenCode to fallback model %s", model)

    def _restore_model(self) -> None:
        if self._model_switcher is None or not self._design_state or not self._design_state.metadata.get("fallback_model_active"):
            return
        try:
            self._model_switcher(False)
        finally:
            self._design_state.metadata.pop("fallback_model_active", None)

    async def _regenerate_module(self, diagnosis: dict) -> AgentResult:
        """Modul vollständig neu schreiben statt weiter zu flicken (Eskalationsstufe 2)."""
        architecture = self._design_state.architecture
        by_name = {m.name: m for m in architecture.modules}
        name = next((m for m in diagnosis.get("suspected_modules", []) if m in by_name), architecture.top_module)
        if not self._hdl_agent or name not in by_name:
            return await self._run_repair(diagnosis, RepairTarget.HDL)
        workspace = self._fs.workspace_path(self._current_task.project_id)
        request = self._design_state.metadata.get(
            "request_full", self._current_task.inputs.get("request_full", self._current_task.inputs.get("request", "")),
        )
        evidence = " | ".join(str(e)[:600] for e in diagnosis.get("evidence", [])[:3])
        change = (
            f"Schreibe das Modul '{name}' vollständig neu, nicht als Flicken des bestehenden Codes. "
            f"Mehrere gezielte Reparaturen sind gescheitert ({diagnosis.get('failure_type')}). "
            f"Letzte Fehlermeldungen: {evidence}"
        )
        self._emit_event("REPAIR_STARTED", {
            "project_id": self._current_task.project_id, "task_type": "regenerate_module",
            "repair_target": RepairTarget.HDL.value, "failed_module": [name],
            "failure_type": diagnosis.get("failure_type"),
        })
        task = AgentTask(
            id=f"regenerate_{name}_{uuid.uuid4().hex[:6]}", type="implement_module",
            project_id=self._current_task.project_id,
            inputs={
                "module": by_name[name].model_dump(), "architecture": architecture.model_dump(),
                "workspace": workspace, "domain": self._current_task.inputs.get("domain", "vhdl"),
                "request": request, "request_full": request, "change_request": change,
                "analysis": self._design_state.metadata.get("analysis", ""),
                "uart_required": bool(self._design_state.metadata.get("uart_required")),
                "uart_template": VHDLTemplates.render("uart", "vhdl"),
                "uart_testbench": VHDLTemplates.render("uart", "testbench"),
            },
        )
        result = await self._hdl_agent.execute(task)
        self._safe_transition_to(DesignStage.STATIC_CHECK)
        await self._save_design_state()
        return result

    _MODEL_MISMATCH_HDL_ATTEMPTS = 2

    def _model_agent(self):
        agent = self._verification_agent
        return agent if agent and "reference_model" in getattr(agent, "supported_task_types", []) else None

    async def _ensure_reference_model(self, hint: str = "", force: bool = False) -> dict:
        """Referenzmodell erzeugen, bevor VHDL existiert (Unabhängigkeit vom Entwurf).

        Ein fehlendes oder ungültiges Modell blockiert nichts; es fehlt dann
        nur der differentielle Test. Neu erzeugt wird bei Änderungswunsch,
        auf Anforderung (force) oder wenn noch keins existiert.
        """
        agent = self._model_agent()
        if agent is None:
            return {"status": "skipped", "reason": "kein Modell-Agent"}
        workspace = self._fs.workspace_path(self._current_task.project_id)
        change_request = self._current_task.inputs.get("change_request", "")
        exists = (Path(workspace) / refmodel.MODEL_FILE).is_file()
        if exists and not force and not change_request:
            return self._design_state.metadata.get("reference_model", {"status": "ready"})
        if self._design_state.metadata.get("uart_required"):
            status = {"status": "skipped", "reason": "UART-Echo-Brücke im Top-Level ist nicht modellierbar"}
            self._design_state.metadata["reference_model"] = status
            return status
        request = self._design_state.metadata.get(
            "request_full", self._current_task.inputs.get("request_full", self._current_task.inputs.get("request", "")),
        )
        if change_request:
            hint = (hint + "\n" if hint else "") + f"Änderungswunsch, der im Modell berücksichtigt werden muss:\n{change_request}"
        task = AgentTask(
            id=str(uuid.uuid4()), type="reference_model", project_id=self._current_task.project_id,
            inputs={
                "workspace": workspace,
                "architecture": self._design_state.architecture.model_dump(),
                "request_full": request,
                "hint": hint,
            },
        )
        try:
            result = await agent.execute(task)
            status = (result.outputs or {}).get("reference_model") or {
                "status": "failed", "reason": result.error_message,
            }
        except Exception as exc:  # Modell ist Zusatznutzen; nie den Lauf abbrechen
            logger.exception("Reference model generation failed")
            status = {"status": "failed", "reason": str(exc)[:500]}
        self._design_state.metadata["reference_model"] = status
        self._emit_event("REFERENCE_MODEL", {"project_id": self._current_task.project_id, **status})
        await self._save_design_state()
        return status

    def _refresh_model_testbench(self, workspace: str) -> None:
        top = self._design_state.architecture.top_module
        if not top or not (Path(workspace) / refmodel.MODEL_FILE).is_file():
            return
        if self._design_state.metadata.get("uart_required"):
            return
        try:
            status = refmodel.write_model_testbench(workspace, top)
        except Exception as exc:
            logger.exception("Model testbench generation failed")
            status = {"status": "model_error", "reason": str(exc)[:500]}
        if status.get("status") != "written":
            # Ein veraltetes Vergleichs-Testbench darf nicht weiterlaufen.
            stale = Path(workspace) / refmodel.model_testbench_path(top)
            if stale.is_file():
                stale.unlink()
        self._design_state.metadata["model_testbench"] = status

    def _classify_model_mismatch(self, diagnostic: dict) -> dict:
        details = diagnostic.get("details") or {}
        output = details.get("error", "") if isinstance(details, dict) else ""
        line = refmodel.mismatch_line(output) or refmodel.mismatch_line(diagnostic.get("message", ""))
        if not line:
            return diagnostic
        top = self._design_state.architecture.top_module if self._design_state else ""
        return {
            **diagnostic,
            "failure_type": "model_mismatch",
            "message": f"{diagnostic.get('message', '')}: {line}".strip(": "),
            "modules": diagnostic.get("modules") or ([top] if top else []),
        }

    def _model_mismatch_target(self, diagnosis: dict, target: RepairTarget) -> RepairTarget:
        """Zuerst HDL reparieren; hilft das zweimal nicht, ist evtl. das Modell falsch.

        Anlehnung an VeriRefine (arXiv:2607.18519): Fehler je nach Ursache an
        die Verständnis- bzw. Codierungsstufe zurückgeben. Das Modell wird
        höchstens einmal neu erzeugt.
        """
        meta = self._design_state.metadata
        meta["model_mismatch_repairs"] = int(meta.get("model_mismatch_repairs", 0)) + 1
        if meta["model_mismatch_repairs"] > self._MODEL_MISMATCH_HDL_ATTEMPTS and not meta.get("model_regenerated"):
            diagnosis["regenerate_model"] = True
            diagnosis["repair_target"] = RepairTarget.VERIFICATION.value
            return RepairTarget.VERIFICATION
        return target

    async def _regenerate_reference_model(self, diagnosis: dict) -> AgentResult:
        self._design_state.metadata["model_regenerated"] = True
        evidence = "; ".join(str(e) for e in diagnosis.get("evidence", [])[:2])[:1500]
        hint = (
            "Der VHDL-Entwurf weicht nach zwei Reparaturen weiterhin vom Modell ab. Prüfe, ob das Modell "
            "PROMPT.md korrekt auslegt (z. B. Takt-/Phasenzählung, Reset-Verhalten), und korrigiere es nur "
            f"dann. Abweichung: {evidence}"
        )
        status = await self._ensure_reference_model(hint=hint, force=True)
        self._safe_transition_to(DesignStage.STATIC_CHECK)
        await self._save_design_state()
        return AgentResult(
            task_id=self._current_task.id,
            status=AgentStatus.COMPLETED if status.get("status") == "ready" else AgentStatus.FAILED,
            error_message="" if status.get("status") == "ready" else f"Referenzmodell: {status.get('reason', '')}",
            outputs={"reference_model": status},
        )

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

    @staticmethod
    def _failure_key(diag: dict) -> tuple[str, str]:
        return (
            str(diag.get("failure_type") or diag.get("type") or ""),
            str(diag.get("message") or ""),
        )

    def _detect_identical_error(self, result: AgentResult) -> bool:
        """True, wenn derselbe Fehler (Klasse + Meldung) schon einmal auftrat."""
        if not self._design_state or not result.diagnostics:
            return False
        current = self._failure_key(result.diagnostics[0])
        if not current[1]:
            return False
        history = self._design_state.diagnostics.history
        previous = history[:-len(result.diagnostics)] if len(history) >= len(result.diagnostics) else []
        return any(self._failure_key(d) == current for d in previous if d)

    async def _run_repair(self, diagnosis: dict, target: RepairTarget = RepairTarget.HDL) -> AgentResult:
        """Create a fix_hdl RepairTask and delegate to HDLAgent via OpenCode.

        Used for module-level (HDL) and synthesis/timing (FPGA) repairs. The
        contract check runs before and after the patch; a repair that breaks
        a previously satisfied contract is rejected. Afterwards the workflow
        restarts at STATIC_CHECK so contracts, compile, simulation and
        coverage are re-verified.
        """
        workspace = self._fs.workspace_path(self._current_task.project_id)
        suspected_modules = diagnosis.get("suspected_modules", [])
        failure_type = diagnosis.get("failure_type", "unknown")
        recommended_action = diagnosis.get("recommended_action", "")
        evidence = diagnosis.get("evidence", [])
        failed_stage = diagnosis.get("stage") or self._design_state.metadata.get("failed_stage", "simulation")

        before_hashes = self._capture_file_hashes(workspace, suspected_modules)
        contract_before = self._contract_checker.check(
            self._design_state.architecture.model_dump(), workspace,
        )

        affected_files = []
        ws = Path(workspace)
        src_dir = ws / "src"
        if src_dir.exists():
            for module_name in suspected_modules:
                for ext in (".vhd", ".vhdl"):
                    fpath = src_dir / f"{module_name}{ext}"
                    if fpath.exists():
                        affected_files.append(f"src/{module_name}{ext}")

        error_info = {
            "message": "; ".join(evidence[:3]) if evidence else recommended_action,
            "failure_type": failure_type,
            "stage": str(failed_stage).lower(),
            "details": {
                "suspected_modules": suspected_modules,
                "recommended_action": recommended_action,
                "severity": diagnosis.get("severity", "medium"),
                "repair_target": target.value,
            },
        }
        if target == RepairTarget.FPGA:
            error_info["details"]["synthesis"] = {
                "timing": self._design_state.synthesis.timing,
                "resources": self._design_state.synthesis.resources,
                "target_fpga": self._target_fpga(),
            }

        acceptance_criteria = [
            "GHDL compilation succeeds (analyze + elaborate)",
            "GHDL simulation passes (no assertion failures)",
            "Entity ports keep matching the architecture contract",
            f"Affected files modified: {affected_files}" if affected_files else "Files modified correctly",
            "Preserve working modules - do not rewrite unrelated files",
        ]
        if target == RepairTarget.FPGA:
            acceptance_criteria.insert(0, "Timing closure: WNS >= 0 and WHS >= 0 after implementation")

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
                "original_requirement": self._design_state.metadata.get(
                    "request_full",
                    self._current_task.inputs.get("request_full", self._current_task.inputs.get("request", "")),
                ),
                "change_request": self._current_task.inputs.get("change_request", ""),
            },
            acceptance_criteria=acceptance_criteria,
            expected_artifacts=[f"src/{m}.vhd" for m in suspected_modules] if suspected_modules else [],
        )

        logger.info(
            "REPAIR_STARTED task_type=fix_hdl target=%s failed_module=%s failure_type=%s affected_files=%s",
            target.value, suspected_modules, failure_type, affected_files,
        )
        self._emit_event("REPAIR_STARTED", {
            "project_id": self._current_task.project_id,
            "task_type": "fix_hdl",
            "repair_target": target.value,
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
            if self._design_state.metadata.get("uart_required"):
                top_module = self._design_state.architecture.top_module
                integrate_uart = getattr(self._hdl_agent, "_integrate_uart_top", None)
                if top_module and integrate_uart:
                    try:
                        integrate_uart(
                            workspace,
                            self._design_state.architecture.model_dump(),
                            top_module,
                        )
                    except (OSError, ValueError) as exc:
                        return AgentResult(
                            task_id=self._current_task.id,
                            status=AgentStatus.FAILED,
                            error_message=f"UART integration after repair failed: {exc}",
                        )

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

            # Vorher/Nachher-Contract-Check: neue Verletzungen = Regression.
            contract_after = self._contract_checker.check(
                self._design_state.architecture.model_dump(), workspace,
            )
            before_keys = {(v.module, v.check, v.expected) for v in contract_before.errors}
            regressions = [
                v for v in contract_after.errors
                if (v.module, v.check, v.expected) not in before_keys
            ]
            repair_record = {
                "target": target.value,
                "failure_type": failure_type,
                "modules": suspected_modules,
                "contract_errors_before": len(contract_before.errors),
                "contract_errors_after": len(contract_after.errors),
                "contract_regressions": [v.to_dict() for v in regressions],
                "at": datetime.now(timezone.utc).isoformat(),
            }
            self._design_state.metadata.setdefault("repairs", []).append(repair_record)
            if regressions:
                self._emit_event("REPAIR_FAILED", {
                    "project_id": self._current_task.project_id,
                    "error": "repair introduced contract violations",
                    "violations": repair_record["contract_regressions"],
                })
                return AgentResult(
                    task_id=self._current_task.id,
                    status=AgentStatus.FAILED,
                    error_message="Repair rejected: it introduced new contract violations",
                    outputs={"repair": repair_record},
                    diagnostics=[{
                        "type": "contract_violation",
                        "failure_type": "contract_violation",
                        "stage": "repair",
                        "message": "Contract violation after repair: "
                        + "; ".join(f"{v.module}: {v.check} {v.expected}" for v in regressions[:5]),
                        "modules": sorted({v.module for v in regressions}),
                    }],
                )

            modified_files = result.outputs.get("modified_files", affected_files)
            logger.info("REPAIR_COMPLETED modified_files=%s", modified_files)
            self._emit_event("REPAIR_COMPLETED", {
                "project_id": self._current_task.project_id,
                "repair_target": target.value,
                "modified_files": modified_files,
            })

            # Vollständige Re-Verifikation ab dem statischen Check.
            self._safe_transition_to(DesignStage.STATIC_CHECK)
            await self._save_design_state()
        else:
            logger.error("REPAIR_FAILED error=%s", result.error_message)
            self._emit_event("REPAIR_FAILED", {
                "project_id": self._current_task.project_id,
                "error": result.error_message,
            })

        return result

    async def _run_architecture_repair(self, diagnosis: dict) -> AgentResult:
        """Interfacefehler zwischen contract-treuen Modulen: Architektur ändern.

        Der ArchitectureAgent verfeinert den Plan; nur Module, deren Contract
        sich ändert, und ihre Abhängigen werden anschließend neu implementiert.
        """
        if not self._architecture_agent:
            return AgentResult(
                task_id=self._current_task.id,
                status=AgentStatus.FAILED,
                error_message="ArchitectureAgent not configured for repair",
            )
        architecture = self._design_state.architecture
        feedback = (
            "Architekturreparatur: Die Module erfüllen ihre Contracts, passen aber "
            f"nicht zusammen ({diagnosis.get('failure_type')}). Betroffene Module: "
            f"{', '.join(diagnosis.get('suspected_modules', [])) or 'unbekannt'}. "
            f"Evidenz: {' | '.join(str(e)[:500] for e in diagnosis.get('evidence', [])[:3])}. "
            "Korrigiere Ports, Breiten und Verbindungen in der Architektur; "
            "unbeteiligte Module unverändert lassen."
        )
        self._emit_event("REPAIR_STARTED", {
            "project_id": self._current_task.project_id,
            "task_type": "refine_architecture",
            "repair_target": RepairTarget.ARCHITECTURE.value,
            "failure_type": diagnosis.get("failure_type"),
        })
        task = AgentTask(
            id=str(uuid.uuid4()),
            type="refine_architecture",
            project_id=self._current_task.project_id,
            inputs={
                "workspace": self._fs.workspace_path(self._current_task.project_id),
                "request_full": self._design_state.metadata.get("request_full", ""),
                "feedback": feedback,
                "version": architecture.version,
                "architecture": architecture.model_dump(),
            },
        )
        result = await self._architecture_agent.execute(task)
        if result.status != AgentStatus.COMPLETED:
            self._emit_event("REPAIR_FAILED", {
                "project_id": self._current_task.project_id,
                "error": result.error_message,
            })
            return result

        old_modules = {m.name: m.model_dump() for m in architecture.modules}
        new_architecture = ArchitectureInfo(**result.outputs.get("architecture", {}))
        changed = [
            m.name for m in new_architecture.modules
            if {k: v for k, v in m.model_dump().items() if k not in ("status", "files")}
            != {k: v for k, v in (old_modules.get(m.name) or {}).items() if k not in ("status", "files")}
        ]
        new_architecture.version = architecture.version + 1
        new_architecture.status = "completed"
        if not new_architecture.top_module:
            new_architecture.top_module = architecture.top_module
        self._design_state.architecture = new_architecture
        self._design_state.metadata["invalidated_modules"] = changed
        self._design_state.metadata.setdefault("repairs", []).append({
            "target": RepairTarget.ARCHITECTURE.value,
            "failure_type": diagnosis.get("failure_type"),
            "changed_modules": changed,
            "architecture_version": new_architecture.version,
            "at": datetime.now(timezone.utc).isoformat(),
        })
        self._emit_event("REPAIR_COMPLETED", {
            "project_id": self._current_task.project_id,
            "repair_target": RepairTarget.ARCHITECTURE.value,
            "changed_modules": changed,
            "architecture_version": new_architecture.version,
        })
        # UART-Integration erneut anwenden, dann inkrementell implementieren.
        self._safe_transition_to(DesignStage.UART_INTEGRATION)
        await self._save_design_state()
        return result

    async def _run_testbench_repair(self, diagnosis: dict) -> AgentResult:
        if diagnosis.get("regenerate_model"):
            return await self._regenerate_reference_model(diagnosis)
        return await self._run_testbench_repair_impl(diagnosis)

    async def _run_testbench_repair_impl(self, diagnosis: dict) -> AgentResult:
        """Test-/Erwartungs- und Abdeckungsfehler: VerificationAgent erzeugt Testbenches."""
        if not self._verification_agent:
            return AgentResult(
                task_id=self._current_task.id,
                status=AgentStatus.FAILED,
                error_message="VerificationAgent not configured for repair",
            )
        workspace = self._fs.workspace_path(self._current_task.project_id)
        modules = diagnosis.get("suspected_modules") or self._design_state.verification.test_plan.get("uncovered", [])
        if not modules and self._design_state.architecture.top_module:
            modules = [self._design_state.architecture.top_module]
        by_name = {m.name: m.model_dump() for m in self._design_state.architecture.modules}
        self._emit_event("REPAIR_STARTED", {
            "project_id": self._current_task.project_id,
            "task_type": "generate_testbench",
            "repair_target": RepairTarget.VERIFICATION.value,
            "modules": modules,
        })
        results = []
        for name in modules:
            if name not in by_name:
                continue
            results.append(await self._verification_agent.execute(AgentTask(
                id=str(uuid.uuid4()),
                type="generate_testbench",
                project_id=self._current_task.project_id,
                inputs={
                    "module": by_name[name], "workspace": workspace, "domain": "vhdl",
                    "mutation_hints": [
                        s["description"] for s in (self._design_state.metadata.get("mutation") or {}).get("survived", [])
                        if s.get("module") == name
                    ],
                },
            )))
        failed = [r for r in results if r.status != AgentStatus.COMPLETED]
        if not results or failed:
            message = failed[0].error_message if failed else "No module to generate a testbench for"
            self._emit_event("REPAIR_FAILED", {"project_id": self._current_task.project_id, "error": message})
            return AgentResult(task_id=self._current_task.id, status=AgentStatus.FAILED, error_message=message)
        self._design_state.metadata.setdefault("repairs", []).append({
            "target": RepairTarget.VERIFICATION.value,
            "failure_type": diagnosis.get("failure_type"),
            "modules": modules,
            "at": datetime.now(timezone.utc).isoformat(),
        })
        self._emit_event("REPAIR_COMPLETED", {
            "project_id": self._current_task.project_id,
            "repair_target": RepairTarget.VERIFICATION.value,
            "testbenches": [r.outputs.get("testbench_file") for r in results],
        })
        self._safe_transition_to(DesignStage.STATIC_CHECK)
        await self._save_design_state()
        return AgentResult(
            task_id=self._current_task.id,
            status=AgentStatus.COMPLETED,
            outputs={"testbenches": [r.outputs.get("testbench_file") for r in results]},
        )

    def _determine_next_stage(
        self, current: DesignStage | str, result: AgentResult
    ) -> DesignStage:
        """Bestimmt die nächste Phase basierend auf Ergebnis."""
        current = self._normalize_stage(current)
        after_flash = (
            DesignStage.HARDWARE_TESTING
            if getattr(self._hardware_test_agent, "has_real_hardware", False)
            else DesignStage.COMPLETED
        )
        transitions = {
            DesignStage.ANALYZING: DesignStage.ARCHITECTING,
            DesignStage.ARCHITECTING: DesignStage.UART_INTEGRATION,
            DesignStage.UART_INTEGRATION: DesignStage.IMPLEMENTING,
            DesignStage.IMPLEMENTING: DesignStage.STATIC_CHECK,
            DesignStage.STATIC_CHECK: DesignStage.SIMULATING,
            DesignStage.SIMULATING: DesignStage.VALIDATING,
            DesignStage.VALIDATING: (
                DesignStage.SYNTHESIZING
                if self._config.get("synthesis_enabled", True)
                else DesignStage.COMPLETED
            ),
            DesignStage.SYNTHESIZING: DesignStage.FPGA_PROGRAMMING,
            DesignStage.FPGA_PROGRAMMING: after_flash,
            DesignStage.HARDWARE_TESTING: DesignStage.COMPLETED,
            DesignStage.DEBUGGING: self._determine_repair_target(),
        }
        return transitions.get(current, DesignStage.FAILED)

    # Stage-Namen in Diagnosen (Safety-Limits zählen "simulation"/"hardware").
    _FAILURE_STAGE_NAMES = {
        DesignStage.STATIC_CHECK: "static_check",
        DesignStage.SIMULATING: "simulation",
        DesignStage.VALIDATING: "validation",
        DesignStage.SYNTHESIZING: "synthesis",
        DesignStage.FPGA_PROGRAMMING: "flash",
        DesignStage.HARDWARE_TESTING: "hardware",
        DesignStage.IMPLEMENTING: "implementation",
        DesignStage.ARCHITECTING: "architecture",
        DesignStage.ANALYZING: "analysis",
    }

    _TERMINAL_STAGES = {
        DesignStage.FAILED,
        DesignStage.INFRASTRUCTURE_FAILURE,
        DesignStage.AUTONOMOUS_LIMIT_REACHED,
        DesignStage.UNRECOVERABLE_ERROR,
    }

    _TARGET_STAGES = {
        RepairTarget.ARCHITECTURE: DesignStage.ARCHITECTING,
        RepairTarget.HDL: DesignStage.IMPLEMENTING,
        RepairTarget.FPGA: DesignStage.IMPLEMENTING,
        RepairTarget.VERIFICATION: DesignStage.SIMULATING,
    }

    def _determine_repair_target(self) -> DesignStage:
        """Phase, in der nach einer Diagnose weitergearbeitet wird."""
        if not self._design_state.diagnostics.active:
            return DesignStage.IMPLEMENTING
        diagnosis = self._design_state.diagnostics.active[0]
        failure_type = diagnosis.get("failure_type", "")
        if failure_type == "infrastructure":
            return DesignStage.INFRASTRUCTURE_FAILURE
        target = RepairTarget(diagnosis.get("repair_target") or route_repair(failure_type).value)
        if target == RepairTarget.HUMAN:
            return DesignStage.FAILED
        return self._TARGET_STAGES[target]

    async def _handle_failure(self, stage: DesignStage | str, result: AgentResult) -> AgentResult | None:
        """Behandelt Fehler: Diagnose → Reparaturziel → zuständiger Agent.

        Fehlerklassen werden verbindlich zugeordnet (siehe repair_routing):
        Architektur/Interface → ArchitectureAgent, Modul/VHDL → HDLAgent,
        Test/Abdeckung → VerificationAgent, Synthese/Timing → HDL mit
        Synthesekontext, Infrastruktur/Board/Ressourcen → Benutzer.
        """
        normalized_stage = self._normalize_stage(stage)
        stage_name = self._FAILURE_STAGE_NAMES.get(normalized_stage, normalized_stage.value.lower())
        self._design_state.metadata["failed_stage"] = stage_name

        if normalized_stage == DesignStage.SYNTHESIZING and result.outputs.get("synthesis_result"):
            synth = result.outputs["synthesis_result"]
            self._design_state.synthesis.status = "failed"
            self._design_state.synthesis.timing = synth.get("timing", {})
            self._design_state.synthesis.resources = synth.get("resources", {})
            self._design_state.synthesis.errors = synth.get("errors", [])

        diagnostics = [
            self._classify_model_mismatch({**d, "stage": d.get("stage") or stage_name})
            for d in (result.diagnostics or [{
                "type": "stage_failure",
                "message": result.error_message or f"{normalized_stage.value} failed",
            }])
        ]
        self._design_state.diagnostics.active = diagnostics
        self._design_state.diagnostics.history.extend(diagnostics)
        result.diagnostics = diagnostics

        if self._detect_identical_error(result) and not self._persistent:
            logger.warning("IDENTICAL_ERROR detected: same failure repeating")
            self._emit_event("IDENTICAL_ERROR", {
                "project_id": self._current_task.project_id,
                "message": result.error_message,
            })
            self._safe_transition_to(DesignStage.FAILED)
            await self._save_design_state()
            return AgentResult(
                task_id=self._current_task.id,
                status=AgentStatus.FAILED,
                error_message=f"Identical error repeating: {result.error_message}",
            )

        logger.info("DEBUG_STARTED stage=%s", normalized_stage.value)
        self._emit_event("DEBUG_STARTED", {
            "project_id": self._current_task.project_id,
            "failed_stage": normalized_stage.value,
        })

        debug_result = await self._run_debugging()
        if debug_result.status != AgentStatus.COMPLETED:
            return None

        diagnosis = debug_result.outputs.get("diagnosis", {})
        failure_type = diagnosis.get("failure_type", "unknown")
        target = RepairTarget(diagnosis.get("repair_target", RepairTarget.HDL.value))
        if failure_type == "model_mismatch":
            target = self._model_mismatch_target(diagnosis, target)
        action = "repair"
        if self._persistent and failure_type != "infrastructure":
            target, action = self._escalate(failure_type, diagnosis, target)
        logger.info(
            "DEBUG_COMPLETED suspected_modules=%s failure_type=%s repair_target=%s",
            diagnosis.get("suspected_modules", []), failure_type, target.value,
        )
        self._emit_event("REPAIR_ASSIGNED", {
            "project_id": self._current_task.project_id,
            "failure_type": failure_type,
            "repair_target": target.value,
            "modules": diagnosis.get("suspected_modules", []),
            "failed_stage": normalized_stage.value,
        })

        if target == RepairTarget.HUMAN:
            if failure_type == "infrastructure":
                self._safe_transition_to(DesignStage.INFRASTRUCTURE_FAILURE)
            specific_hint = next(
                ((d.get("details") or {}).get("hint") for d in diagnostics if (d.get("details") or {}).get("hint")),
                "",
            )
            reason = (
                f"{failure_type}: {specific_hint or diagnosis.get('recommended_action', '')}\n"
                f"{result.error_message}"
            ).strip()
            self._design_state.add_human_intervention(reason)
            await self._save_design_state()
            self._emit_event("HUMAN_INTERVENTION_REQUESTED", {
                "project_id": self._current_task.project_id,
                "reason": reason,
                "stage": normalized_stage.value,
            })
            return AgentResult(
                task_id=self._current_task.id,
                status=AgentStatus.BLOCKED,
                error_message=(
                    "Infrastructure failure - cannot repair"
                    if failure_type == "infrastructure"
                    else f"Human intervention required: {reason}"
                ),
                outputs={
                    "repair_target": (
                        "INFRASTRUCTURE_FAILURE" if failure_type == "infrastructure" else target.value
                    ),
                    "diagnosis": diagnosis,
                },
            )
        self._design_state.increment_repairs()
        if action == "switch_model":
            self._switch_to_fallback_model()
        if action == "regenerate":
            repair = await self._regenerate_module(diagnosis)
        elif target == RepairTarget.ARCHITECTURE:
            repair = await self._run_architecture_repair(diagnosis)
        elif target == RepairTarget.VERIFICATION:
            repair = await self._run_testbench_repair(diagnosis)
        else:
            repair = await self._run_repair(diagnosis, target)

        # Scheitert die Reparatur an der Infrastruktur (Zeitlimit, Docker,
        # Provider), bringt ein weiterer Versuch nichts: anhalten und melden.
        infra = [d for d in repair.diagnostics or [] if d.get("failure_type") == "infrastructure"]
        if repair.status == AgentStatus.FAILED and infra:
            self._design_state.diagnostics.history.extend(infra)
            self._design_state.add_human_intervention(repair.error_message)
            self._safe_transition_to(DesignStage.INFRASTRUCTURE_FAILURE)
            await self._save_design_state()
            self._emit_event("HUMAN_INTERVENTION_REQUESTED", {
                "project_id": self._current_task.project_id,
                "reason": repair.error_message,
                "stage": normalized_stage.value,
            })
            return AgentResult(
                task_id=self._current_task.id,
                status=AgentStatus.BLOCKED,
                error_message=repair.error_message,
                diagnostics=infra,
                outputs={"repair_target": "INFRASTRUCTURE_FAILURE"},
            )
        return repair

    async def _request_human_intervention(self, result: AgentResult) -> bool:
        """Fragt User um Intervention (Approval, Hardware-Fix, etc.)."""
        self._design_state.add_human_intervention(result.error_message or "Manual intervention required")
        
        self._emit_event("HUMAN_INTERVENTION_REQUESTED", {
            "project_id": self._current_task.project_id,
            "reason": result.error_message,
            "stage": str(self._design_state.current_stage),
        })
        
        # In echter Implementierung würde hier auf User-Input gewartet
        # Für jetzt: False zurückgeben (keine Intervention)
        return False

    def _check_safety_limits(self) -> AgentResult | None:
        """Prüft Safety Limits."""
        iterations = self._design_state.iterations
        
        if iterations["total"] >= self._max_iterations:
            self._safe_transition_to(DesignStage.AUTONOMOUS_LIMIT_REACHED)
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

    def _safe_transition_to(self, target: DesignStage) -> None:
        """Transitioniert sicher; fällt back auf erste erlaubte Transition falls Ziel nicht erreichbar."""
        from src.domain.state_machine import TRANSITIONS
        current = self._design_state.current_stage.value if isinstance(self._design_state.current_stage, DesignStage) else str(self._design_state.current_stage)
        try:
            self._design_state.transition_to(target)
        except Exception:
            allowed = TRANSITIONS.get(current, [])
            if allowed and allowed[0] != current:
                self._design_state.transition_to(allowed[0])

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