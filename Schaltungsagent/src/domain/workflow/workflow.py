import logging

from ..state_machine import StateMachine, WorkflowState
from ..ports import (
    ArtifactGenerator,
    FileSystemService,
    OpenCodeService,
    EventPublisher,
    ValidationService,
    PlannerService,
)
from ..models import TaskState, ArtifactBundle, EventType
from ..exceptions import (
    WorkflowError,
    LLMError,
    ArtifactError,
    WorkspaceError,
    AgentExecutionError,
)
from src.services.project_namer import make_unique
from src.services.project_namer import derive_project_name

logger = logging.getLogger(__name__)


class Workflow:
    def __init__(
        self,
        artifact_generator: ArtifactGenerator,
        filesystem_service: FileSystemService,
        opencode_service: OpenCodeService,
        event_publisher: EventPublisher | None = None,
        validation_service: ValidationService | None = None,
        planner_service: PlannerService | None = None,
        max_repair_iterations: int = 5,
    ):
        self._artifact_generator = artifact_generator
        self._fs = filesystem_service
        self._opencode = opencode_service
        self._events = event_publisher
        self._validation_service = validation_service
        self._planner_service = planner_service
        self._max_repair_iterations = max_repair_iterations

    def run(
        self,
        request: str,
        domain: str = "vhdl",
        task_id: str | None = None,
    ) -> dict:
        state = TaskState(request=request, domain=domain)
        if task_id:
            state.task_id = task_id
        else:
            state.task_id = make_unique(derive_project_name(request))
        sm = StateMachine(WorkflowState.CREATED)

        self._emit(state, EventType.TASK_CREATED, {"request": request, "domain": domain})

        try:
            self._analyze(state, sm)
            artifacts = self._generate_artifacts(state, sm)
            workspace_root = self._prepare_workspace(state, sm, artifacts)
            if self._planner_service:
                self._execute_planned(state, sm, workspace_root)
            else:
                self._run_agent(state, sm, workspace_root)
            self._test_and_repair(state, sm, workspace_root)
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
        return state.to_dict()

    def _emit(
        self, state: TaskState, event_type: EventType, payload: dict | None = None
    ) -> None:
        p = payload or {}
        p.setdefault("task_id", state.task_id)
        p.setdefault("status", state.status)
        if self._events:
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
        state.add_log("Analyzing request...")
        analysis = "Original request preserved for OpenCode planning and implementation."
        state.metadata["analysis"] = analysis
        state.add_log(f"Analysis complete: {analysis}")
        return analysis

    def _generate_artifacts(
        self,
        state: TaskState,
        sm: StateMachine,
    ) -> ArtifactBundle:
        self._transition(state, sm, WorkflowState.GENERATING_ARTIFACTS)
        state.add_log("Generating artifacts...")
        analysis = state.metadata.get("analysis", "")
        try:
            artifacts = self._artifact_generator.generate(
                state.request, analysis, state.domain
            )
        except Exception as e:
            raise ArtifactError(f"Artifact generation failed: {e}") from e
        state.artifacts = [f.to_dict() for f in artifacts.files]
        state.add_log(f"Generated {len(artifacts.files)} file(s)")
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
            workspace_root = self._fs.create_workspace(state.task_id, state.domain)
        except Exception as e:
            raise WorkspaceError(f"Workspace creation failed: {e}") from e
        state.workspace = workspace_root
        written_files = []
        for file_artifact in artifacts.files:
            file_path = f"{workspace_root}/{file_artifact.path}"
            try:
                actual_path = self._fs.write_file(file_path, file_artifact.content)
                written_files.append(actual_path)
            except Exception as e:
                raise WorkspaceError(
                    f"Failed to write {file_artifact.name}: {e}"
                ) from e
        state.generated_files = written_files
        state.add_log(f"Workspace ready at {workspace_root}")
        return workspace_root

    def _execute_planned(
        self,
        state: TaskState,
        sm: StateMachine,
        workspace_root: str,
    ) -> None:
        self._transition(state, sm, WorkflowState.RUNNING_AGENT)
        state.add_log("Executing planned workflow...")
        context = {
            "workspace": workspace_root,
            "domain": state.domain,
            "request": state.request,
        }
        plan = self._planner_service.create_plan(state.request, context)
        result = self._planner_service.execute_plan(plan)
        state.metadata["plan_result"] = result
        state.add_log(f"Planned execution complete: {result.get('status', 'unknown')}")

    def _run_agent(
        self,
        state: TaskState,
        sm: StateMachine,
        workspace_root: str,
    ) -> None:
        self._transition(state, sm, WorkflowState.RUNNING_AGENT)
        state.add_log("Running OpenCode agent...")
        instruction = (
            f"Implementiere die Komponente im Projekt {workspace_root}. "
            f"Anforderung: {state.request}"
        )
        try:
            result = self._opencode.execute(
                workspace_root, instruction
            )
        except AgentExecutionError:
            raise
        except Exception as e:
            raise AgentExecutionError(f"OpenCode execution failed: {e}") from e
        state.opencode_result = result.to_dict()
        state.add_log(f"OpenCode finished: returncode={result.returncode}")

    def _test_and_repair(
        self,
        state: TaskState,
        sm: StateMachine,
        workspace_root: str,
    ) -> None:
        iteration = 0
        while iteration < self._max_repair_iterations:
            self._transition(state, sm, WorkflowState.TESTING)
            state.add_log(f"Testing (iteration {iteration + 1})...")

            if self._validation_service:
                validation = self._validation_service.validate(
                    workspace_root, state.domain
                )
                test_passed = validation.passed
                state.test_results = {
                    "passed": test_passed,
                    "message": validation.message,
                    "details": validation.details,
                    "iteration": iteration + 1,
                }
            else:
                result = self._opencode.execute(
                    workspace_root,
                    f"Teste und verifiziere die Komponente. "
                    f"Anforderung: {state.request}",
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
                state.add_log("Tests passed!")
                return

            state.add_log(f"Tests failed (iteration {iteration + 1})")

            iteration += 1
            if iteration >= self._max_repair_iterations:
                state.add_log("Max repair iterations reached")
                self._transition(state, sm, WorkflowState.FAILED)
                return

            self._transition(state, sm, WorkflowState.REPAIRING)
            state.add_log(f"Repairing (iteration {iteration})...")

            if self._validation_service:
                repair_instruction = validation.build_repair_instruction(
                    original_request=state.request,
                    iteration=iteration,
                )
            else:
                error_detail = state.test_results.get("stderr") or state.test_results.get("message", "")
                repair_instruction = (
                    f"Repariere die Komponente. Fehler: {error_detail[:500]}"
                )
            repair_result = self._opencode.execute(
                workspace_root, repair_instruction,
            )
            state.iterations = iteration

        self._transition(state, sm, WorkflowState.FAILED)

    def _complete(self, state: TaskState, sm: StateMachine) -> None:
        self._transition(state, sm, WorkflowState.VALIDATING)
        state.add_log("Validating final result...")
        summary = (
            f"Task {state.task_id} completed with status {state.status}; "
            f"generated {len(state.generated_files)} file(s)."
        )
        state.metadata["summary"] = summary
        self._transition(state, sm, WorkflowState.COMPLETED)
        state.add_log("Task completed successfully")

    def _handle_failure(
        self, state: TaskState, sm: StateMachine, error_message: str
    ) -> None:
        state.error_message = error_message
        state.add_log(f"Workflow failed: {error_message}")
        sm.transition_to(WorkflowState.FAILED)
        state.set_status(WorkflowState.FAILED)

    def _save_state(self, state: TaskState) -> None:
        import os
        import json
        if not state.workspace:
            return
        try:
            state_path = os.path.join(state.workspace, "state.json")
            with open(state_path, "w") as f:
                json.dump(state.to_dict(), f, indent=2, ensure_ascii=False)
        except OSError as e:
            logger.warning("Failed to save state: %s", e)
