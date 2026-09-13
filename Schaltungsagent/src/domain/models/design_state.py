from pydantic import BaseModel, Field
from typing import Any
from datetime import datetime, timezone
from enum import Enum
import uuid


class DesignStage(str, Enum):
    CREATED = "CREATED"
    ANALYZING = "ANALYZING"
    ARCHITECTING = "ARCHITECTING"
    IMPLEMENTING = "IMPLEMENTING"
    STATIC_CHECK = "STATIC_CHECK"
    SIMULATING = "SIMULATING"
    VALIDATING = "VALIDATING"
    DEBUGGING = "DEBUGGING"
    SYNTHESIZING = "SYNTHESIZING"
    FPGA_PROGRAMMING = "FPGA_PROGRAMMING"
    HARDWARE_TESTING = "HARDWARE_TESTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    AUTONOMOUS_LIMIT_REACHED = "AUTONOMOUS_LIMIT_REACHED"
    INFRASTRUCTURE_FAILURE = "INFRASTRUCTURE_FAILURE"


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


class ArchitectureInfo(BaseModel):
    status: str = "pending"
    version: int = 0
    modules: list[ModuleInfo] = Field(default_factory=list)
    interfaces: dict = Field(default_factory=dict)
    clock_domain: str = "clk"
    reset_concept: str = "async_active_high"
    decisions: list[dict] = Field(default_factory=list)
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

    def increment_iteration(self, stage: str) -> None:
        self.iterations["total"] += 1
        self.iterations["by_stage"][stage] = self.iterations["by_stage"].get(stage, 0) + 1

    def increment_repairs(self) -> None:
        self.iterations["repairs"] += 1

    def add_human_intervention(self, reason: str) -> None:
        self.human_interventions.count += 1
        self.human_interventions.reasons.append(reason)
        self.human_interventions.last_intervention = datetime.now(timezone.utc).isoformat()

    def transition_to(self, new_stage: DesignStage) -> None:
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