from .exceptions import StateMachineError


class WorkflowState:
    """Canonical workflow states of the Schaltungsagent pipeline.

    Primary (spec) flow:
        RECEIVED -> ANALYZING -> PLANNING -> TASK_GRAPH_CREATED ->
        GENERATING -> INTEGRATING -> VERIFYING -> SIMULATION_PASSED ->
        SYNTHESIZING -> SUCCESS

    Repair loop (both verification and synthesis failure paths):
        VERIFYING  -X-> REPAIRING -> VERIFYING
        SYNTHESIZING -X-> REPAIRING -> VERIFYING

    Abort/terminal conditions:
        MAX_REPAIR_ITERATIONS, MAX_WORKER_ATTEMPTS, TIMEOUT,
        UNRECOVERABLE_ERROR, RESOURCE_LIMIT (plus FAILED / INFRASTRUCTURE_FAILURE)

    Legacy stage names (ARCHITECTING, IMPLEMENTING, STATIC_CHECK, ...)
    are retained as aliases so the existing DesignState-driven loop,
    dashboard and tests keep working. RAG_SEARCH was removed.
    """
    # --- Spec (primary) flow ---
    CREATED = "CREATED"
    RECEIVED = "RECEIVED"
    ANALYZING = "ANALYZING"
    PLANNING = "PLANNING"
    TASK_GRAPH_CREATED = "TASK_GRAPH_CREATED"
    GENERATING = "GENERATING"
    INTEGRATING = "INTEGRATING"
    VERIFYING = "VERIFYING"
    REPAIRING = "REPAIRING"
    SIMULATION_PASSED = "SIMULATION_PASSED"
    SYNTHESIZING = "SYNTHESIZING"
    SUCCESS = "SUCCESS"

    # --- Abort / terminal conditions ---
    MAX_REPAIR_ITERATIONS = "MAX_REPAIR_ITERATIONS"
    MAX_WORKER_ATTEMPTS = "MAX_WORKER_ATTEMPTS"
    TIMEOUT = "TIMEOUT"
    UNRECOVERABLE_ERROR = "UNRECOVERABLE_ERROR"
    RESOURCE_LIMIT = "RESOURCE_LIMIT"
    FAILED = "FAILED"
    INFRASTRUCTURE_FAILURE = "INFRASTRUCTURE_FAILURE"
    AUTONOMOUS_LIMIT_REACHED = "AUTONOMOUS_LIMIT_REACHED"

    # --- Legacy / compatibility stage names ---
    ARCHITECTING = "ARCHITECTING"
    UART_INTEGRATION = "UART_INTEGRATION"
    IMPLEMENTING = "IMPLEMENTING"
    GENERATING_ARTIFACTS = "GENERATING_ARTIFACTS"
    WORKSPACE_READY = "WORKSPACE_READY"
    STATIC_CHECK = "STATIC_CHECK"
    SIMULATING = "SIMULATING"
    VALIDATING = "VALIDATING"
    DEBUGGING = "DEBUGGING"
    RUNNING_AGENT = "RUNNING_AGENT"
    TESTING = "TESTING"
    FPGA_PROGRAMMING = "FPGA_PROGRAMMING"
    HARDWARE_TESTING = "HARDWARE_TESTING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    FLASHING = "FLASHING"
    FLASHED = "FLASHED"
    BLOCKED = "BLOCKED"
    SKIPPED = "SKIPPED"
    COMPLETED = "COMPLETED"

    @classmethod
    def all_states(cls) -> list[str]:
        return sorted(
            value
            for name, value in vars(cls).items()
            if isinstance(value, str) and name.isupper()
        )

    @classmethod
    def terminal_states(cls) -> list[str]:
        return [
            cls.SUCCESS, cls.COMPLETED, cls.FAILED, cls.INFRASTRUCTURE_FAILURE,
            cls.AUTONOMOUS_LIMIT_REACHED, cls.MAX_REPAIR_ITERATIONS,
            cls.MAX_WORKER_ATTEMPTS, cls.TIMEOUT, cls.UNRECOVERABLE_ERROR,
            cls.RESOURCE_LIMIT,
        ]


_TRANSITIONS: dict[str, list[str]] = {
    # --- Spec (primary) flow ---
    WorkflowState.CREATED: [
        WorkflowState.RECEIVED, WorkflowState.ANALYZING, WorkflowState.FAILED,
    ],
    WorkflowState.RECEIVED: [
        WorkflowState.ANALYZING, WorkflowState.PLANNING, WorkflowState.FAILED,
    ],
    WorkflowState.ANALYZING: [
        WorkflowState.PLANNING, WorkflowState.ARCHITECTING, WorkflowState.DEBUGGING,
        WorkflowState.FAILED,
    ],
    WorkflowState.PLANNING: [
        WorkflowState.TASK_GRAPH_CREATED, WorkflowState.ARCHITECTING,
        WorkflowState.FAILED,
    ],
    WorkflowState.TASK_GRAPH_CREATED: [
        WorkflowState.GENERATING, WorkflowState.IMPLEMENTING, WorkflowState.FAILED,
    ],
    WorkflowState.GENERATING: [
        WorkflowState.INTEGRATING, WorkflowState.IMPLEMENTING,
        WorkflowState.WORKSPACE_READY, WorkflowState.FAILED,
    ],
    WorkflowState.INTEGRATING: [
        WorkflowState.VERIFYING, WorkflowState.STATIC_CHECK,
        WorkflowState.SIMULATING, WorkflowState.REPAIRING, WorkflowState.FAILED,
    ],
    WorkflowState.VERIFYING: [
        WorkflowState.SIMULATION_PASSED, WorkflowState.SIMULATING,
        WorkflowState.VALIDATING, WorkflowState.REPAIRING, WorkflowState.FAILED,
    ],
    WorkflowState.SIMULATION_PASSED: [
        WorkflowState.SYNTHESIZING, WorkflowState.SUCCESS, WorkflowState.FAILED,
    ],
    WorkflowState.REPAIRING: [
        WorkflowState.VERIFYING, WorkflowState.GENERATING,
        WorkflowState.IMPLEMENTING, WorkflowState.RUNNING_AGENT,
        WorkflowState.TESTING, WorkflowState.FAILED,
    ],
    WorkflowState.SYNTHESIZING: [
        WorkflowState.SUCCESS, WorkflowState.FPGA_PROGRAMMING,
        WorkflowState.REPAIRING, WorkflowState.DEBUGGING, WorkflowState.FAILED,
    ],
    WorkflowState.SUCCESS: [],

    # --- Abort / terminal conditions ---
    WorkflowState.MAX_REPAIR_ITERATIONS: [],
    WorkflowState.MAX_WORKER_ATTEMPTS: [],
    WorkflowState.TIMEOUT: [],
    WorkflowState.UNRECOVERABLE_ERROR: [],
    WorkflowState.RESOURCE_LIMIT: [],
    WorkflowState.FAILED: [],
    WorkflowState.INFRASTRUCTURE_FAILURE: [],
    WorkflowState.AUTONOMOUS_LIMIT_REACHED: [],

    # --- Legacy compatibility transitions ---
    WorkflowState.GENERATING_ARTIFACTS: [
        WorkflowState.WORKSPACE_READY, WorkflowState.FAILED,
    ],
    WorkflowState.WORKSPACE_READY: [
        WorkflowState.GENERATING, WorkflowState.IMPLEMENTING, WorkflowState.FAILED,
    ],
    WorkflowState.ARCHITECTING: [
        WorkflowState.GENERATING, WorkflowState.UART_INTEGRATION,
        WorkflowState.DEBUGGING, WorkflowState.FAILED,
    ],
    WorkflowState.UART_INTEGRATION: [
        WorkflowState.IMPLEMENTING, WorkflowState.FAILED,
    ],
    WorkflowState.IMPLEMENTING: [
        WorkflowState.STATIC_CHECK, WorkflowState.GENERATING,
        WorkflowState.INTEGRATING, WorkflowState.DEBUGGING, WorkflowState.FAILED,
    ],
    WorkflowState.STATIC_CHECK: [
        WorkflowState.SIMULATING, WorkflowState.INTEGRATING,
        WorkflowState.DEBUGGING, WorkflowState.FAILED,
    ],
    WorkflowState.SIMULATING: [
        WorkflowState.VALIDATING, WorkflowState.VERIFYING,
        WorkflowState.REPAIRING, WorkflowState.DEBUGGING, WorkflowState.FAILED,
    ],
    WorkflowState.VALIDATING: [
        WorkflowState.SYNTHESIZING, WorkflowState.SIMULATION_PASSED,
        WorkflowState.DEBUGGING, WorkflowState.FAILED,
    ],
    WorkflowState.DEBUGGING: [
        WorkflowState.ARCHITECTING, WorkflowState.IMPLEMENTING,
        WorkflowState.STATIC_CHECK, WorkflowState.UART_INTEGRATION,
        WorkflowState.GENERATING, WorkflowState.SIMULATING,
        WorkflowState.SYNTHESIZING, WorkflowState.FPGA_PROGRAMMING,
        WorkflowState.HARDWARE_TESTING, WorkflowState.REPAIRING,
        WorkflowState.INFRASTRUCTURE_FAILURE, WorkflowState.FAILED,
    ],
    WorkflowState.RUNNING_AGENT: [
        WorkflowState.TESTING, WorkflowState.VERIFYING, WorkflowState.FAILED,
    ],
    WorkflowState.TESTING: [
        WorkflowState.VALIDATING, WorkflowState.VERIFYING,
        WorkflowState.REPAIRING, WorkflowState.COMPLETED, WorkflowState.FAILED,
    ],
    WorkflowState.FPGA_PROGRAMMING: [
        WorkflowState.COMPLETED, WorkflowState.HARDWARE_TESTING,
        WorkflowState.DEBUGGING, WorkflowState.AWAITING_APPROVAL,
        WorkflowState.FAILED,
    ],
    WorkflowState.HARDWARE_TESTING: [
        WorkflowState.COMPLETED, WorkflowState.SUCCESS, WorkflowState.DEBUGGING,
        WorkflowState.FAILED,
    ],
    WorkflowState.AWAITING_APPROVAL: [
        WorkflowState.FLASHING, WorkflowState.REPAIRING, WorkflowState.FAILED,
    ],
    WorkflowState.FLASHING: [
        WorkflowState.FLASHED, WorkflowState.AWAITING_APPROVAL,
        WorkflowState.FAILED,
    ],
    WorkflowState.FLASHED: [WorkflowState.COMPLETED, WorkflowState.SUCCESS],
    WorkflowState.COMPLETED: [WorkflowState.IMPLEMENTING],
    WorkflowState.BLOCKED: [WorkflowState.FAILED, WorkflowState.REPAIRING],
    WorkflowState.SKIPPED: [WorkflowState.FAILED],
}

TRANSITIONS = _TRANSITIONS


class StateMachine:
    TRANSITIONS = TRANSITIONS

    def __init__(self, initial_state: str = WorkflowState.CREATED):
        self._current = initial_state

    @property
    def current(self) -> str:
        return self._current

    def transition_to(self, new_state: str) -> None:
        if new_state == self._current:
            return
        allowed = self.TRANSITIONS.get(self._current, [])
        if new_state not in allowed:
            raise StateMachineError(
                f"Invalid transition: {self._current} -> {new_state}. "
                f"Allowed: {allowed}"
            )
        self._current = new_state

    def can_transition_to(self, new_state: str) -> bool:
        return new_state in self.TRANSITIONS.get(self._current, [])

    def reset(self, initial_state: str = WorkflowState.CREATED) -> None:
        self._current = initial_state

    def get_allowed_transitions(self) -> list[str]:
        return self.TRANSITIONS.get(self._current, [])

    @classmethod
    def is_valid_transition(cls, from_state: str, to_state: str) -> bool:
        return to_state in cls.TRANSITIONS.get(from_state, []) or from_state == to_state
