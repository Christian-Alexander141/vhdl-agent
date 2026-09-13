"""Supervisor-based Orchestrator for the multi-agent system.

This module provides a new orchestrator that uses the SupervisorAgent
and specialized agents for the production workflow.
"""
import asyncio
import logging
import threading
from datetime import datetime, timezone
from typing import Callable

from src.domain.ports import (
    LLMService,
    RAGService,
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
from src.agents.supervisor import SupervisorAgent
from src.agents.architecture import ArchitectureAgent
from src.agents.hdl import HDLAgent
from src.agents.verification import VerificationAgent
from src.agents.debug import DebugAgent
from src.agents.fpga import FPGAAgent
from src.agents.hardware_test import HardwareTestAgent
from src.services.project_memory import ProjectMemoryService
from src.services.project_namer import make_unique

logger = logging.getLogger(__name__)


class SupervisorOrchestrator:
    """Orchestrator that delegates to SupervisorAgent for multi-agent workflow.
    
    This orchestrator provides a clean interface while using the SupervisorAgent
    internally for task decomposition and agent coordination.
    """
    
    def __init__(
        self,
        llm_service: LLMService,
        rag_service: RAGService,
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
    ):
        self._llm = llm_service
        self._rag = rag_service
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
        
        # Create specialized agents
        self._architecture_agent = ArchitectureAgent(
            llm_service=llm_service,
            rag_service=rag_service,
            event_publisher=event_publisher,
        )
        
        self._hdl_agent = HDLAgent(
            llm_service=llm_service,
            rag_service=rag_service,
            opencode_service=opencode_service,
            filesystem_service=filesystem_service,
            event_publisher=event_publisher,
        )
        
        self._verification_agent = VerificationAgent(
            llm_service=llm_service,
            rag_service=rag_service,
            filesystem_service=filesystem_service,
            opencode_service=opencode_service,
            event_publisher=event_publisher,
        )
        
        self._debug_agent = DebugAgent(
            llm_service=llm_service,
            rag_service=rag_service,
            event_publisher=event_publisher,
        )
        
        self._fpga_agent = FPGAAgent(
            llm_service=llm_service,
            rag_service=rag_service,
            filesystem_service=filesystem_service,
            event_publisher=event_publisher,
            vivado_binary=fpga_registry.get("vivado_binary", "vivado") if fpga_registry else "vivado",
            vivado_settings=fpga_registry.get("vivado_settings", "") if fpga_registry else "",
        )
        
        self._hardware_test_agent = HardwareTestAgent(
            llm_service=llm_service,
            rag_service=rag_service,
            filesystem_service=filesystem_service,
            event_publisher=event_publisher,
        )
        
        # Create SupervisorAgent
        self._supervisor = SupervisorAgent(
            llm_service=llm_service,
            rag_service=rag_service,
            filesystem_service=filesystem_service,
            event_publisher=event_publisher,
            project_memory=ProjectMemoryService(filesystem_service),
            architecture_agent=self._architecture_agent,
            hdl_agent=self._hdl_agent,
            verification_agent=self._verification_agent,
            debug_agent=self._debug_agent,
            fpga_agent=self._fpga_agent,
            hardware_test_agent=self._hardware_test_agent,
            config={
                "max_iterations": 20,
                "max_repairs_per_stage": max_repair_iterations,
                "max_simulation_failures": 10,
                "max_hardware_failures": 5,
            },
        )
        
        # Task graph for tracking
        self._task_graph = TaskGraph()
        self._running_tasks: dict[str, dict] = {}
        
        # Approval registry (for future use)
        self._approval_events: dict[str, threading.Event] = {}
        self._approval_results: dict[str, tuple[bool, str]] = {}
        self._approval_lock = threading.Lock()
    
    def execute(
        self,
        request: str,
        domain: str = "vhdl",
        task_id: str | None = None,
    ) -> dict:
        """Execute a request using the SupervisorAgent.
        
        This is the main entry point for the production workflow.
        """
        # Generate task ID if not provided
        if not task_id:
            task_id = make_unique(self._llm.generate_project_name(request))
        
        # Create initial task for Supervisor
        initial_task = AgentTask(
            id=task_id,
            type="supervise",
            project_id=task_id,
            inputs={
                "request": request,
                "domain": domain,
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
        
        # Convert to legacy format for compatibility
        return self._convert_result_to_dict(result, task_id)
    
    def execute_async(
        self,
        request: str,
        domain: str = "vhdl",
        callback: Callable[[dict], None] | None = None,
    ) -> str:
        """Execute a request asynchronously."""
        task_id = make_unique(self._llm.generate_project_name(request))
        
        def run():
            result = self.execute(request, domain, task_id=task_id)
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
        # For now, treat all chat messages as new project requests
        return self.execute(request, domain)
    
    def get_task_status(self, task_id: str) -> dict | None:
        """Get status of a running task."""
        return self._running_tasks.get(task_id)
    
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
    
    # Approval methods (for future use)
    def approve_task(self, task_id: str, feedback: str = "") -> bool:
        """Approve a task (placeholder for future implementation)."""
        return False
    
    def reject_task(self, task_id: str, feedback: str = "") -> bool:
        """Reject a task (placeholder for future implementation)."""
        return False
