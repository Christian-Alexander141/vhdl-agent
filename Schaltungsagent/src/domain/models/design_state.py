from pydantic import BaseModel, Field
from typing import Any
from datetime import datetime, timezone
from enum import Enum
import uuid


class DesignStage(str, Enum):
    CREATED = "CREATED"
    RECEIVED = "RECEIVED"
    ANALYZING = "ANALYZING"
    ARCHITECTING = "ARCHITECTING"
    UART_INTEGRATION = "UART_INTEGRATION"
    PLANNING = "PLANNING"
    TASK_GRAPH_CREATED = "TASK_GRAPH_CREATED"
    GENERATING = "GENERATING"
    IMPLEMENTING = "IMPLEMENTING"
    INTEGRATING = "INTEGRATING"
    STATIC_CHECK = "STATIC_CHECK"
    VERIFYING = "VERIFYING"
    SIMULATING = "SIMULATING"
    VALIDATING = "VALIDATING"
    SIMULATION_PASSED = "SIMULATION_PASSED"
    DEBUGGING = "DEBUGGING"
    REPAIRING = "REPAIRING"
    SYNTHESIZING = "SYNTHESIZING"
    FPGA_PROGRAMMING = "FPGA_PROGRAMMING"
    HARDWARE_TESTING = "HARDWARE_TESTING"
    SUCCESS = "SUCCESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    AUTONOMOUS_LIMIT_REACHED = "AUTONOMOUS_LIMIT_REACHED"
    INFRASTRUCTURE_FAILURE = "INFRASTRUCTURE_FAILURE"
    MAX_REPAIR_ITERATIONS = "MAX_REPAIR_ITERATIONS"
    MAX_WORKER_ATTEMPTS = "MAX_WORKER_ATTEMPTS"
    TIMEOUT = "TIMEOUT"
    UNRECOVERABLE_ERROR = "UNRECOVERABLE_ERROR"
    RESOURCE_LIMIT = "RESOURCE_LIMIT"


class RequirementStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    SATISFIED = "SATISFIED"
    FAILED = "FAILED"


class Requirement(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    description: str
    status: RequirementStatus = RequirementStatus.PENDING
    satisfied_by: list[str] = Field(default_factory=list)
    verified: bool = False


class ModuleInfo(BaseModel):
    name: str
    type: str = "module"
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    parameters: dict = Field(default_factory=dict)
    description: str = ""
    status: str = "planned"
    dependencies: list[str] = Field(default_factory=list)
    files: list[str] = Field(default_factory=list)
    # Maschinenprüfbarer Port-Contract: {port: {"direction": "in", "type": "..."}}
    ports: dict = Field(default_factory=dict)


class ArchitectureInfo(BaseModel):
    status: str = "pending"
    version: int = 0
    top_module: str = ""
    modules: list[ModuleInfo] = Field(default_factory=list)
    interfaces: dict = Field(default_factory=dict)
    clock_domain: str = "clk"
    reset_concept: str = "async_active_high"
    decisions: list[dict] = Field(default_factory=list)
    # Projektspezifische Hardware-Testvektoren (siehe HardwareTestAgent).
    hardware_tests: list[dict] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ImplementationInfo(BaseModel):
    status: str = "pending"
    files: list[str] = Field(default_factory=list)
    generated_files: list[str] = Field(default_factory=list)
    modified_files: list[str] = Field(default_factory=list)
    last_modified: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class TestInfo(BaseModel):
    name: str
    type: str = "unit"
    module: str = ""
    status: str = "pending"
    passed: bool = False
    error: str = ""


class VerificationInfo(BaseModel):
    status: str = "pending"
    tests: list[TestInfo] = Field(default_factory=list)
    passed: int = 0
    failed: int = 0
    coverage: float = 0.0
    last_run: str = ""
    # Versionierte Gate-Ergebnisse: Architekturversion, Testplan, Contracts.
    architecture_version: int = 0
    test_plan: dict = Field(default_factory=dict)
    contract_check: dict = Field(default_factory=dict)
    history: list[dict] = Field(default_factory=list)


class SynthesisInfo(BaseModel):
    status: str = "pending"
    timing: dict = Field(default_factory=dict)
    resources: dict = Field(default_factory=dict)
    bitstream_path: str = ""
    fpga_part: str = ""
    errors: list[str] = Field(default_factory=list)


class FPGAInfo(BaseModel):
    target: str = ""
    programmed: bool = False
    bitstream: str = ""
    board_detected: bool = False
    programmer: str = "vivado"


class HardwareTestInfo(BaseModel):
    status: str = "pending"
    # MOCK | REAL_HARDWARE | NONE – Erfolg zählt nur bei REAL_HARDWARE.
    test_mode: str = "NONE"
    tests: list[TestInfo] = Field(default_factory=list)
    passed: int = 0
    failed: int = 0
    last_run: str = ""
    communication_log: list[dict] = Field(default_factory=list)


class DiagnosticInfo(BaseModel):
    active: list[dict] = Field(default_factory=list)
    history: list[dict] = Field(default_factory=list)


class HumanIntervention(BaseModel):
    count: int = 0
    reasons: list[str] = Field(default_factory=list)
    last_intervention: str = ""


class DesignState(BaseModel):
    project: dict = Field(default_factory=lambda: {
        "id": str(uuid.uuid4()),
        "name": "",
        "version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    requirements: list[Requirement] = Field(default_factory=list)
    architecture: ArchitectureInfo = Field(default_factory=ArchitectureInfo)
    implementation: ImplementationInfo = Field(default_factory=ImplementationInfo)
    verification: VerificationInfo = Field(default_factory=VerificationInfo)
    synthesis: SynthesisInfo = Field(default_factory=SynthesisInfo)
    fpga: FPGAInfo = Field(default_factory=FPGAInfo)
    hardware: HardwareTestInfo = Field(default_factory=HardwareTestInfo)
    diagnostics: DiagnosticInfo = Field(default_factory=DiagnosticInfo)
    iterations: dict = Field(default_factory=lambda: {
        "total": 0,
        "by_stage": {},
        "repairs": 0,
    })
    human_interventions: HumanIntervention = Field(default_factory=HumanIntervention)
    current_stage: DesignStage = DesignStage.CREATED
    metadata: dict = Field(default_factory=dict)

    def _stage_name(self, stage: str | DesignStage | None) -> str:
        if isinstance(stage, DesignStage):
            return stage.value
        if stage is None:
            stage = self.current_stage
        if isinstance(stage, DesignStage):
            return stage.value
        return str(stage or DesignStage.CREATED.value)

    def increment_iteration(self, stage: str | DesignStage | None) -> None:
        stage_name = self._stage_name(stage)
        self.iterations["total"] += 1
        self.iterations["by_stage"][stage_name] = self.iterations["by_stage"].get(stage_name, 0) + 1

    def increment_repairs(self) -> None:
        self.iterations["repairs"] += 1

    def add_human_intervention(self, reason: str) -> None:
        self.human_interventions.count += 1
        self.human_interventions.reasons.append(reason)
        self.human_interventions.last_intervention = datetime.now(timezone.utc).isoformat()

    def transition_to(self, new_stage: DesignStage) -> None:
        from src.domain.state_machine import StateMachine, WorkflowState, TRANSITIONS
        from src.domain.exceptions import StateMachineError
        current_val = self.current_stage.value if isinstance(self.current_stage, DesignStage) else str(self.current_stage)
        new_val = new_stage.value if isinstance(new_stage, DesignStage) else str(new_stage)
        allowed = TRANSITIONS.get(current_val, [])
        if new_val not in allowed and new_val != current_val:
            raise StateMachineError(
                f"Invalid transition: {current_val} -> {new_val}. "
                f"Allowed: {allowed}"
            )
        self.current_stage = new_stage
        self.project["updated_at"] = datetime.now(timezone.utc).isoformat()

    def to_yaml(self) -> str:
        import yaml
        return yaml.dump(self.model_dump(mode="json"), default_flow_style=False, sort_keys=False)

    @classmethod
    def from_yaml(cls, yaml_str: str) -> "DesignState":
        import yaml
        data = yaml.safe_load(yaml_str)
        return cls(**data)

    def to_json(self) -> str:
        return self.model_dump_json(indent=2)

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")

    @classmethod
    def from_json(cls, json_str: str) -> "DesignState":
        return cls.model_validate_json(json_str)