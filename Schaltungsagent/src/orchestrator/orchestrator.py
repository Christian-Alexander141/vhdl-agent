import os
import json
import asyncio
import logging
import threading
import time
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
    PlannerService,
)
from src.domain.models import (
    TaskState,
    EventType,
    Event,
    KnowledgeBundle,
    ArtifactBundle,
)
from src.domain.state_machine import StateMachine, WorkflowState
from src.domain.exceptions import (
    WorkflowError,
    RAGError,
    LLMError,
    ArtifactError,
    WorkspaceError,
    AgentExecutionError,
)
from src.domain.workflow.workflow import Workflow

logger = logging.getLogger(__name__)


class AsyncAgentOrchestrator:
    def __init__(
        self,
        llm_service: LLMService,
        rag_service: RAGService,
        artifact_generator: ArtifactGenerator,
        filesystem_service: FileSystemService,
        opencode_service: OpenCodeService,
        event_publisher: EventPublisher,
        validation_service: ValidationService | None = None,
        planner_service: PlannerService | None = None,
        max_repair_iterations: int = 5,
    ):
        self._llm = llm_service
        self._rag = rag_service
        self._artifact_generator = artifact_generator
        self._fs = filesystem_service
        self._opencode = opencode_service
        self._events = event_publisher
        self._validation_service = validation_service
        self._planner_service = planner_service
        self._max_repair_iterations = max_repair_iterations

        self._workflow = Workflow(
            llm_service=llm_service,
            rag_service=rag_service,
            artifact_generator=artifact_generator,
            filesystem_service=filesystem_service,
            opencode_service=opencode_service,
            validation_service=validation_service,
            planner_service=planner_service,
            max_repair_iterations=max_repair_iterations,
        )

        self._running_tasks: dict[str, dict] = {}

    def execute(self, request: str, domain: str = "vhdl") -> dict:
        state = TaskState(request=request, domain=domain)
        sm = StateMachine(WorkflowState.CREATED)

        self._emit(state, EventType.TASK_CREATED, {"request": request, "domain": domain})

        try:
            self._analyze(state, sm)
            knowledge = self._search_rag(state, sm)
            artifacts = self._generate_artifacts(state, sm, knowledge)
            workspace = self._prepare_workspace(state, sm, artifacts)
            self._run_agent(state, sm, workspace)
            self._test_and_repair(state, sm, workspace)
            if state.status != WorkflowState.FAILED:
                self._complete(state, sm)

        except WorkflowError as e:
            self._handle_failure(state, sm, str(e))
        except Exception as e:
            logger.exception("Unexpected error in workflow")
            self._handle_failure(state, sm, f"Unexpected error: {e}")

        self._emit(state, EventType.LOG_MESSAGE, {
            "message": f"Workflow finished with status {state.status}",
            "files": state.generated_files,
        })

        self._save_state(state)
        self._running_tasks.pop(state.task_id, None)

        return state.to_dict()

    def execute_async(
        self,
        request: str,
        domain: str = "vhdl",
        callback: Callable[[dict], None] | None = None,
    ) -> str:
        task_id = ""
        result_holder: dict = {}

        def run():
            nonlocal task_id
            result = self.execute(request, domain)
            task_id = result.get("task_id", "")
            result_holder["result"] = result
            if callback:
                try:
                    callback(result)
                except Exception:
                    logger.exception("Async callback failed")

        thread = threading.Thread(target=run, daemon=True)
        thread.start()

        import uuid
        task_id = str(uuid.uuid4())
        self._running_tasks[task_id] = {
            "thread": thread,
            "status": "running",
            "request": request,
            "domain": domain,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        return task_id

    def get_task_status(self, task_id: str) -> dict | None:
        return self._running_tasks.get(task_id)

    def list_tasks(self) -> list[dict]:
        return [
            {"task_id": tid, **info}
            for tid, info in self._running_tasks.items()
        ]

    def _emit(
        self,
        state: TaskState,
        event_type: EventType,
        payload: dict | None = None,
    ) -> None:
        p = payload or {}
        p.setdefault("task_id", state.task_id)
        p.setdefault("status", state.status)
        self._events.publish_event(event_type, state.task_id, p)

    def _transition(
        self, state: TaskState, sm: StateMachine, new_state: str
    ) -> None:
        old_status = state.status
        sm.transition_to(new_state)
        state.set_status(new_state)
        self._emit(state, EventType.STATE_CHANGED, {
            "from": old_status,
            "to": new_state,
        })

    def _analyze(self, state: TaskState, sm: StateMachine) -> str:
        self._transition(state, sm, WorkflowState.ANALYZING)
        self._emit(state, EventType.ANALYSIS_STARTED)

        state.add_log("Analyzing request...")
        try:
            analysis = self._llm.analyze_request(state.request, state.domain)
        except Exception as e:
            raise LLMError(f"Analysis failed: {e}") from e

        state.metadata["analysis"] = analysis
        state.add_log(f"Analysis complete: {analysis}")
        self._emit(state, EventType.ANALYSIS_FINISHED, {"analysis": analysis})
        return analysis

    def _search_rag(self, state: TaskState, sm: StateMachine) -> KnowledgeBundle:
        self._transition(state, sm, WorkflowState.RAG_SEARCH)
        self._emit(state, EventType.RAG_STARTED)

        state.add_log("Searching RAG knowledge base...")
        try:
            knowledge = self._rag.retrieve_knowledge(state.request, state.domain)
        except Exception as e:
            raise RAGError(f"RAG search failed: {e}") from e

        state.metadata["knowledge"] = knowledge.to_dict()
        state.add_log(
            f"RAG found {len(knowledge.coding_rules)} rules, "
            f"{len(knowledge.reference_designs)} designs"
        )
        self._emit(state, EventType.RAG_FINISHED, {
            "rule_count": len(knowledge.coding_rules),
            "design_count": len(knowledge.reference_designs),
        })
        return knowledge

    def _generate_artifacts(
        self,
        state: TaskState,
        sm: StateMachine,
        knowledge: KnowledgeBundle,
    ) -> ArtifactBundle:
        self._transition(state, sm, WorkflowState.GENERATING_ARTIFACTS)
        self._emit(state, EventType.ARTIFACT_GENERATION_STARTED)

        state.add_log("Generating artifacts...")
        analysis = state.metadata.get("analysis", "")

        try:
            artifacts = self._artifact_generator.generate(
                state.request, analysis, knowledge, state.domain
            )
        except Exception as e:
            raise ArtifactError(f"Artifact generation failed: {e}") from e

        state.artifacts = [f.to_dict() for f in artifacts.files]
        state.add_log(f"Generated {len(artifacts.files)} file(s)")
        self._emit(state, EventType.ARTIFACT_GENERATION_FINISHED, {
            "file_count": len(artifacts.files),
        })
        return artifacts

    def _prepare_workspace(
        self,
        state: TaskState,
        sm: StateMachine,
        artifacts: ArtifactBundle,
    ) -> str:
        self._transition(state, sm, WorkflowState.WORKSPACE_READY)

        state.add_log("Preparing workspace...")
        try:
            workspace = self._fs.create_workspace(state.task_id, state.domain)
        except Exception as e:
            raise WorkspaceError(f"Workspace creation failed: {e}") from e

        state.workspace = workspace
        written_files = []

        for file_artifact in artifacts.files:
            file_path = f"{workspace}/{file_artifact.path}"
            try:
                actual_path = self._fs.write_file(file_path, file_artifact.content)
                written_files.append(actual_path)
            except Exception as e:
                raise WorkspaceError(
                    f"Failed to write {file_artifact.name}: {e}"
                ) from e

        state.generated_files = written_files
        state.add_log(f"Workspace ready at {workspace}")
        self._emit(state, EventType.FILES_CREATED, {
            "workspace": workspace,
            "files": written_files,
        })
        return workspace

    def _run_agent(
        self,
        state: TaskState,
        sm: StateMachine,
        workspace: str,
    ) -> None:
        self._transition(state, sm, WorkflowState.RUNNING_AGENT)
        self._emit(state, EventType.AGENT_STARTED)

        state.add_log("Running OpenCode agent...")
        instruction = (
            f"Implementiere die VHDL-Komponente im Projekt {workspace}. "
            f"Anforderung: {state.request}"
        )

        try:
            result = self._opencode.execute(
                workspace, instruction, timeout_seconds=300
            )
        except AgentExecutionError:
            raise
        except Exception as e:
            raise AgentExecutionError(f"OpenCode execution failed: {e}") from e

        state.opencode_result = result.to_dict()
        state.add_log(
            f"OpenCode finished: returncode={result.returncode}"
        )
        self._emit(state, EventType.AGENT_FINISHED, {
            "returncode": result.returncode,
            "stdout": result.stdout[:500],
            "stderr": result.stderr[:500],
        })

    def _test_and_repair(
        self,
        state: TaskState,
        sm: StateMachine,
        workspace: str,
    ) -> None:
        iteration = 0
        while iteration < self._max_repair_iterations:
            self._transition(state, sm, WorkflowState.TESTING)
            self._emit(state, EventType.TEST_STARTED,
                       {"iteration": iteration + 1})

            state.add_log(f"Testing (iteration {iteration + 1})...")

            if self._validation_service:
                validation = self._validation_service.validate(workspace, state.domain)
                test_passed = validation.passed
                state.test_results = {
                    "passed": test_passed,
                    "message": validation.message,
                    "details": validation.details,
                    "iteration": iteration + 1,
                }
            else:
                result = self._opencode.execute(
                    workspace,
                    f"Teste und verifiziere die VHDL-Komponente. "
                    f"Anforderung: {state.request}",
                    timeout_seconds=300,
                )
                test_passed = result.success
                state.test_results = {
                    "passed": test_passed,
                    "returncode": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "iteration": iteration + 1,
                }

            if test_passed:
                self._emit(state, EventType.TEST_PASSED,
                           {"iteration": iteration + 1})
                state.add_log("Tests passed!")
                return

            self._emit(state, EventType.TEST_FAILED,
                       {"iteration": iteration + 1,
                        "error": state.test_results.get("stderr", "")[:500]})
            state.add_log(f"Tests failed: {state.test_results.get('stderr', '')[:200]}")

            iteration += 1
            if iteration >= self._max_repair_iterations:
                state.add_log("Max repair iterations reached")
                self._transition(state, sm, WorkflowState.FAILED)
                return

            self._transition(state, sm, WorkflowState.REPAIRING)
            self._emit(state, EventType.REPAIR_STARTED,
                       {"iteration": iteration})

            state.add_log(f"Repairing (iteration {iteration})...")
            error_detail = state.test_results.get("stderr") or state.test_results.get("message", "")
            repair_result = self._opencode.execute(
                workspace,
                f"Repariere die VHDL-Komponente. Fehler: {error_detail[:500]}",
                timeout_seconds=300,
            )

            state.iterations = iteration
            self._emit(state, EventType.REPAIR_FINISHED,
                       {"iteration": iteration,
                        "returncode": repair_result.returncode})

        self._transition(state, sm, WorkflowState.FAILED)

    def _complete(self, state: TaskState, sm: StateMachine) -> None:
        self._transition(state, sm, WorkflowState.VALIDATING)
        self._emit(state, EventType.VALIDATION_STARTED)

        state.add_log("Validating final result...")
        summary = self._llm.summarize_result(state.to_dict())
        state.metadata["summary"] = summary

        self._emit(state, EventType.VALIDATION_FINISHED, {"summary": summary})
        self._transition(state, sm, WorkflowState.COMPLETED)
        self._emit(state, EventType.TASK_COMPLETED, {
            "task_id": state.task_id,
            "summary": summary,
        })
        state.add_log("Task completed successfully")

    def _handle_failure(
        self, state: TaskState, sm: StateMachine, error_message: str
    ) -> None:
        state.error_message = error_message
        state.add_log(f"Workflow failed: {error_message}")
        sm.transition_to(WorkflowState.FAILED)
        state.set_status(WorkflowState.FAILED)
        self._emit(state, EventType.TASK_FAILED, {"error": error_message})

    def _save_state(self, state: TaskState) -> None:
        if not state.workspace:
            return
        try:
            state_path = os.path.join(state.workspace, "state.json")
            with open(state_path, "w") as f:
                json.dump(state.to_dict(), f, indent=2, ensure_ascii=False)
        except OSError as e:
            logger.warning("Failed to save state: %s", e)


AgentOrchestrator = AsyncAgentOrchestrator
