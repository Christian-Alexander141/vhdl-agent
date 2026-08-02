from .exceptions import StateMachineError


class WorkflowState:
    CREATED = "CREATED"
    ANALYZING = "ANALYZING"
    RAG_SEARCH = "RAG_SEARCH"
    GENERATING_ARTIFACTS = "GENERATING_ARTIFACTS"
    WORKSPACE_READY = "WORKSPACE_READY"
    RUNNING_AGENT = "RUNNING_AGENT"
    TESTING = "TESTING"
    REPAIRING = "REPAIRING"
    VALIDATING = "VALIDATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


TRANSITIONS = {
    WorkflowState.CREATED: [WorkflowState.ANALYZING, WorkflowState.FAILED],
    WorkflowState.ANALYZING: [WorkflowState.RAG_SEARCH, WorkflowState.FAILED],
    WorkflowState.RAG_SEARCH: [WorkflowState.GENERATING_ARTIFACTS, WorkflowState.FAILED],
    WorkflowState.GENERATING_ARTIFACTS: [WorkflowState.WORKSPACE_READY, WorkflowState.FAILED],
    WorkflowState.WORKSPACE_READY: [WorkflowState.RUNNING_AGENT, WorkflowState.FAILED],
    WorkflowState.RUNNING_AGENT: [WorkflowState.TESTING, WorkflowState.FAILED],
    WorkflowState.TESTING: [
        WorkflowState.VALIDATING,
        WorkflowState.COMPLETED,
        WorkflowState.REPAIRING,
        WorkflowState.FAILED,
    ],
    WorkflowState.REPAIRING: [
        WorkflowState.RUNNING_AGENT,
        WorkflowState.FAILED,
    ],
    WorkflowState.VALIDATING: [
        WorkflowState.COMPLETED,
        WorkflowState.FAILED,
    ],
    WorkflowState.COMPLETED: [],
    WorkflowState.FAILED: [],
}


class StateMachine:
    def __init__(self, initial_state: str = WorkflowState.CREATED):
        self._current = initial_state

    @property
    def current(self) -> str:
        return self._current

    def transition_to(self, new_state: str) -> None:
        if new_state == self._current:
            return
        allowed = TRANSITIONS.get(self._current, [])
        if new_state not in allowed:
            raise StateMachineError(
                f"Invalid transition: {self._current} -> {new_state}. "
                f"Allowed: {allowed}"
            )
        self._current = new_state

    def can_transition_to(self, new_state: str) -> bool:
        return new_state in TRANSITIONS.get(self._current, [])

    def reset(self, initial_state: str = WorkflowState.CREATED) -> None:
        self._current = initial_state
