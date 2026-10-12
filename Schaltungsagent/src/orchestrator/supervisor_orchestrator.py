"""Supervisor-based Orchestrator for the multi-agent system.

This module provides a new orchestrator that uses the SupervisorAgent
and specialized agents for the production workflow.
"""
import asyncio
import json
import logging
import os
import threading
import uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Callable

from src.domain import yaml_io
from src.domain.ports import (
    ArtifactGenerator,
    FileSystemService,
    OpenCodeService,
    EventPublisher,
    ValidationService,
    BitstreamService,
    FlashService,
)
from src.domain.models import TaskState, EventType, Event
from src.domain.state_machine import StateMachine, WorkflowState
from src.domain.exceptions import AgentExecutionError, WorkflowError
from src.domain.agents import AgentTask, AgentResult, AgentStatus, TaskGraph
from src.orchestrator.agent_factory import build_supervisor_agent
from src.services.project_namer import make_unique
from src.services.opencode_task_runner import OpenCodeTaskRunner
from src.services.plan_service import PlanService
from src.services.knowledge_provisioner import KnowledgeProvisioner
from src.config import Settings

logger = logging.getLogger(__name__)


class SupervisorOrchestrator:
    """Orchestrator that delegates to SupervisorAgent for multi-agent workflow.
    
    This orchestrator provides a clean interface while using the SupervisorAgent
    internally for task decomposition and agent coordination.
    """
    
    def __init__(
        self,
        artifact_generator: ArtifactGenerator,
        filesystem_service: FileSystemService,
        opencode_service: OpenCodeService,
        event_publisher: EventPublisher,
        validation_service: ValidationService | None = None,
        bitstream_service: BitstreamService | None = None,
        flash_service: FlashService | None = None,
        flash_services: dict[str, FlashService] | None = None,
        fpga_registry: dict | None = None,
        max_repair_iterations: int = 5,
        cleanup_on_failure: bool = False,
        cleanup_temp_files: bool = True,
        name_resolver=None,
        plan_timeout_seconds: int = 180,
        max_prompt_bytes: int = 200_000,
        settings: Settings | None = None,
    ):
        self._artifact_generator = artifact_generator
        self._fs = filesystem_service
        self._opencode = opencode_service
        self._events = event_publisher
        self._validation_service = validation_service
        self._bitstream_service = bitstream_service
        self._flash_service = flash_service
        self._flash_services = flash_services or {}
        self._fpga_registry = fpga_registry or {}
        self._max_repair_iterations = max_repair_iterations
        self._cleanup_on_failure = cleanup_on_failure
        self._cleanup_temp_files = cleanup_temp_files
        self._name_resolver = name_resolver
        self._plan_service = PlanService(
            OpenCodeTaskRunner(
                opencode_service,
                event_publisher=event_publisher,
                max_prompt_bytes=max_prompt_bytes,
            ),
            timeout_seconds=plan_timeout_seconds,
            name_resolver=name_resolver,
            max_attempts=3 if getattr(getattr(settings, "opencode", None), "repair_policy", "standard") == "persistent" else 1,
        )
        self._settings = settings or Settings()
        self._knowledge_provisioner = KnowledgeProvisioner(self._settings)
        
        self._supervisor = build_supervisor_agent(
            filesystem_service=filesystem_service,
            event_publisher=event_publisher,
            opencode_service=opencode_service,
            fpga_registry=fpga_registry,
            max_repair_iterations=max_repair_iterations,
            validation_service=validation_service,
            name_resolver=name_resolver,
            plan_timeout_seconds=plan_timeout_seconds,
            max_prompt_bytes=max_prompt_bytes,
            skills_dir=self._settings.opencode.skills_dir,
            settings=self._settings,
        )
        
        self._running_tasks: dict[str, dict] = {}

    def _bootstrap_new_project(self, request_full: str, domain: str) -> tuple[str, dict]:
        scratch_id = f"bootstrap-{uuid.uuid4().hex[:12]}"
        scratch = self._fs.create_workspace(scratch_id, domain)
        try:
            # AP10: Provision knowledge before planning
            self._knowledge_provisioner.provision(scratch, board_id=self._settings.synthesis.default_fpga)
            
            manifest = self._plan_service.plan(
                scratch,
                request_full,
                task_id=scratch_id,
            )
            project_id = make_unique(manifest["project_name"])
            if hasattr(self._fs, "rename_workspace"):
                self._fs.rename_workspace(scratch_id, project_id)
            else:
                Path(scratch).rename(self._fs.workspace_path(project_id))
            # Re-provision after rename to update paths
            self._knowledge_provisioner.provision(
                self._fs.workspace_path(project_id),
                board_id=self._settings.synthesis.default_fpga,
            )
            return project_id, manifest
        except Exception:
            try:
                self._fs.delete_workspace(scratch_id)
            except Exception:
                logger.exception("Could not remove failed bootstrap workspace %s", scratch_id)
            raise
        
    
    def execute(
        self,
        request: str,
        domain: str = "vhdl",
        task_id: str | None = None,
        extra_inputs: dict | None = None,
    ) -> dict:
        """Execute a request using the SupervisorAgent.
        
        This is the main entry point for the production workflow.
        """
        # Generate task ID if not provided
        extra_inputs = dict(extra_inputs or {})
        if not task_id:
            task_id, manifest = self._bootstrap_new_project(request, domain)
            extra_inputs["plan_manifest"] = manifest
        
        # Create initial task for Supervisor
        initial_task = AgentTask(
            id=task_id,
            type="supervise",
            project_id=task_id,
            inputs={
                "request": request,
                "request_full": request,
                "domain": domain,
                **extra_inputs,
            },
            context={
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        
        # Run SupervisorAgent asynchronously.
        # Python 3.12 can raise RuntimeError when no loop is set in the current thread,
        # so we create one explicitly instead of assuming get_event_loop() is always valid.
        try:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop is not None and loop.is_running():
                # If loop is already running, create a new thread
                result_holder = {}

                def run_in_thread():
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        result = new_loop.run_until_complete(
                            self._supervisor.execute(initial_task)
                        )
                        result_holder["result"] = result
                    finally:
                        new_loop.close()
                        asyncio.set_event_loop(None)

                thread = threading.Thread(target=run_in_thread, daemon=True)
                thread.start()
                thread.join(timeout=300)  # 5 minute timeout

                if "result" not in result_holder:
                    raise AgentExecutionError("Supervisor execution timed out")

                result = result_holder["result"]
            else:
                if loop is None:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                try:
                    result = loop.run_until_complete(
                        self._supervisor.execute(initial_task)
                    )
                finally:
                    if not loop.is_running():
                        loop.close()
                        asyncio.set_event_loop(None)
        except Exception as e:
            logger.exception("Supervisor execution failed")
            result = AgentResult(
                task_id=task_id,
                status=AgentStatus.FAILED,
                error_message=str(e),
            )
        
        # Convert to legacy format for compatibility and publish a terminal
        # event so dashboard clients do not depend on an individual stage event.
        result_dict = self._convert_result_to_dict(result, task_id)
        terminal_event = (
            EventType.TASK_COMPLETED
            if result.status == AgentStatus.COMPLETED
            else EventType.TASK_FAILED
        )
        # Ohne Projektzustand: das Dashboard nutzt davon nichts, er machte aber
        # 101 von 163 KB Ereignisverkehr eines Laufs aus (Lauf mini_cpu). Der
        # vollständige Zustand bleibt im Ergebnis (/api/tasks) und in design_state.yaml.
        self._events.publish_event(
            terminal_event,
            task_id,
            {
                "task_id": task_id,
                "status": result_dict["status"],
                "error": result.error_message,
                "outputs": {
                    key: value for key, value in (result.outputs or {}).items()
                    if key not in ("design_state", "task_graph")
                },
            },
        )
        return result_dict
    
    def execute_async(
        self,
        request: str,
        domain: str = "vhdl",
        callback: Callable[[dict], None] | None = None,
    ) -> str:
        """Execute a request asynchronously."""
        task_id, manifest = self._bootstrap_new_project(request, domain)
        
        def run():
            result = self.execute(
                request,
                domain,
                task_id=task_id,
                extra_inputs={"plan_manifest": manifest},
            )
            if callback:
                try:
                    callback(result)
                except Exception:
                    logger.exception("Async callback failed")
        
        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        
        self._running_tasks[task_id] = {
            "thread": thread,
            "status": "running",
            "request": request,
            "domain": domain,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        
        return task_id
    
    def handle_chat(
        self,
        request: str,
        domain: str = "vhdl",
        current_project: str | None = None,
    ) -> dict:
        """Handle chat messages (simplified for now)."""
        if current_project:
            return self._continue_project(current_project, request)
        return self.execute(request, domain)

    async def handle_chat_async(
        self,
        request: str,
        domain: str = "vhdl",
        current_project: str | None = None,
        upload_dir: str | None = None,
        callback: Callable[[dict], None] | None = None,
    ) -> dict:
        """Handle chat messages asynchronously, supporting project continuation.
        
        If current_project is set, continues the existing project; otherwise
        starts a new project. Uploads are passed to the supervisor context.
        """
        if current_project:
            result = await self._continue_project_async(current_project, request, upload_dir)
        else:
            try:
                task_id, manifest = await asyncio.to_thread(
                    self._bootstrap_new_project, request, domain
                )
            except Exception as exc:
                logger.exception("OpenCode project planning failed")
                return {
                    "type": "error",
                    "status": "BLOCKED",
                    "answer": f"OpenCode konnte keinen sicheren Projektplan erstellen: {exc}",
                }
            extra_inputs = {"plan_manifest": manifest}
            if upload_dir:
                extra_inputs["upload_dir"] = upload_dir
            
            def run():
                r = self.execute(
                    request,
                    domain,
                    task_id=task_id,
                    extra_inputs=extra_inputs,
                )
                if callback:
                    try:
                        callback(r)
                    except Exception:
                        logger.exception("Async callback failed")
            
            thread = threading.Thread(target=run, daemon=True)
            thread.start()
            self._running_tasks[task_id] = {
                "thread": thread,
                "status": "running",
                "request": request,
                "domain": domain,
                "started_at": datetime.now(timezone.utc).isoformat(),
            }
            result = {"task_id": task_id, "status": "QUEUED"}
        
        if callback and "task_id" in result:
            try:
                callback(result)
            except Exception:
                logger.exception("Async callback failed")
        return result

    def _continue_project(self, project_id: str, request: str) -> dict:
        """Continue an existing project with a new request."""
        workspace = Path(self._fs.workspace_path(project_id))
        prompt_path = workspace / "PROMPT.md"
        request_full = prompt_path.read_bytes().decode("utf-8") if prompt_path.is_file() else request
        state_path = workspace / "design_state.yaml"
        state = {}
        if state_path.is_file():
            import yaml

            state = yaml_io.load(state_path.read_text(encoding="utf-8")) or {}
        return self.execute(
            request_full,
            task_id=project_id,
            extra_inputs={
                "change_request": request,
                "plan_manifest": (state.get("metadata") or {}).get("plan_manifest", {}),
            },
        )

    async def _continue_project_async(
        self, project_id: str, request: str, upload_dir: str | None = None
    ) -> dict:
        """Continue an existing project asynchronously."""
        workspace = Path(self._fs.workspace_path(project_id))
        prompt_path = workspace / "PROMPT.md"
        request_full = prompt_path.read_bytes().decode("utf-8") if prompt_path.is_file() else request
        state_path = workspace / "design_state.yaml"
        state = {}
        if state_path.is_file():
            import yaml

            state = yaml_io.load(state_path.read_text(encoding="utf-8")) or {}
        # AP10: Re-provision knowledge for existing projects (updated skills)
        self._knowledge_provisioner.provision(
            str(workspace), board_id=self._settings.synthesis.default_fpga
        )
        extra_inputs = {
            "change_request": request,
            "plan_manifest": (state.get("metadata") or {}).get("plan_manifest", {}),
        }
        if upload_dir:
            extra_inputs["upload_dir"] = upload_dir

        def run():
            r = self.execute(
                request_full,
                task_id=project_id,
                extra_inputs=extra_inputs,
            )
            return r
        
        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        self._running_tasks[project_id] = {
            "thread": thread,
            "status": "running",
            "request": request,
            "domain": "vhdl",
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        return {"task_id": project_id, "status": "QUEUED"}
    
    def get_task_status(self, task_id: str) -> dict | None:
        """Get status of a running task."""
        return self._running_tasks.get(task_id)

    def list_tasks(self) -> list[dict]:
        """List all running tasks."""
        return list(self._running_tasks.values())

    def load_task_graph(self, task_id: str) -> TaskGraph | None:
        """Load the task graph the supervisor persisted for a project."""
        path = self._task_graph_path(task_id)
        if not self._fs.file_exists(path):
            return None
        try:
            return TaskGraph.from_dict(json.loads(self._fs.read_file(path)))
        except (OSError, TypeError, ValueError, KeyError):
            return None

    def _task_graph_path(self, task_id: str) -> str:
        return os.path.join(self._fs.workspace_path(task_id), "task_graph.json")

    def _convert_result_to_dict(self, result: AgentResult, task_id: str) -> dict:
        """Convert AgentResult to legacy dictionary format."""
        status_map = {
            AgentStatus.COMPLETED: "COMPLETED",
            AgentStatus.FAILED: "FAILED",
            AgentStatus.RUNNING: "RUNNING",
            AgentStatus.PENDING: "PENDING",
            AgentStatus.BLOCKED: "BLOCKED",
        }
        
        return {
            "task_id": task_id,
            "status": status_map.get(result.status, "UNKNOWN"),
            "generated_files": result.outputs.get("files", []),
            "iterations": result.iterations,
            "error_message": result.error_message,
            "outputs": result.outputs,
        }
    # --- Delegierungs-Methoden für LangGraph-Orchestrator ---

    def _run_analysis(self) -> Any:
        """Delegiert an den internen SupervisorAgent."""
        return self._supervisor._run_analysis()

    def _run_architecture(self) -> Any:
        """Delegiert an den internen SupervisorAgent."""
        return self._supervisor._run_architecture()

    def _run_implementation(self) -> Any:
        """Delegiert an den internen SupervisorAgent."""
        return self._supervisor._run_implementation()

    def _run_static_check(self) -> Any:
        """Delegiert an den internen SupervisorAgent."""
        return self._supervisor._run_static_check()

    def _run_simulation(self) -> Any:
        """Delegiert an den internen SupervisorAgent."""
        return self._supervisor._run_simulation()

    def _run_debugging(self) -> Any:
        """Delegiert an den internen SupervisorAgent."""
        return self._supervisor._run_debugging()

    def _run_synthesis(self) -> Any:
        """Delegiert an den internen SupervisorAgent."""
        return self._supervisor._run_synthesis()

    def _run_fpga_programming(self) -> Any:
        """Delegiert an den internen SupervisorAgent."""
        return self._supervisor._run_fpga_programming()

    def _run_hardware_test(self) -> Any:
        """Delegiert an den internen SupervisorAgent."""
        return self._supervisor._run_hardware_test()

    
    def resume_project(self, project_id: str) -> str:
        """Setzt einen unterbrochenen Workflow aus dem persistierten Zustand fort.

        Der Supervisor lädt design_state.yaml und task_graph.json und macht in
        der gespeicherten Phase weiter; abgeschlossene Tasks werden nicht
        wiederholt. Kein Änderungswunsch, daher keine Neuplanung.
        """
        workspace = Path(self._fs.workspace_path(project_id))
        prompt_path = workspace / "PROMPT.md"
        state_path = workspace / "design_state.yaml"
        state: dict = {}
        if state_path.is_file():
            import yaml

            state = yaml_io.load(state_path.read_text(encoding="utf-8")) or {}
        metadata = state.get("metadata") or {}
        request_full = (
            prompt_path.read_bytes().decode("utf-8")
            if prompt_path.is_file()
            else metadata.get("request_full", "")
        )

        def run():
            self.execute(
                request_full,
                task_id=project_id,
                extra_inputs={"plan_manifest": metadata.get("plan_manifest", {})},
            )

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        self._running_tasks[project_id] = {
            "thread": thread,
            "status": "running",
            "request": "resume",
            "domain": "vhdl",
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        return project_id
