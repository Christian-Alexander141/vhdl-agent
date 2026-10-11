import uuid
from datetime import datetime, timezone
from typing import Any
from pydantic import BaseModel, Field


class WorkflowStatus(str):
    CREATED = "CREATED"
    ANALYZING = "ANALYZING"
    GENERATING_ARTIFACTS = "GENERATING_ARTIFACTS"
    WORKSPACE_READY = "WORKSPACE_READY"
    RUNNING_AGENT = "RUNNING_AGENT"
    TESTING = "TESTING"
    REPAIRING = "REPAIRING"
    VALIDATING = "VALIDATING"
    SYNTHESIZING = "SYNTHESIZING"
    FLASHING = "FLASHING"
    FLASHED = "FLASHED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

    # New multi-agent states
    ARCHITECTING = "ARCHITECTING"
    IMPLEMENTING = "IMPLEMENTING"
    STATIC_CHECK = "STATIC_CHECK"
    SIMULATING = "SIMULATING"
    DEBUGGING = "DEBUGGING"
    FPGA_PROGRAMMING = "FPGA_PROGRAMMING"
    HARDWARE_TESTING = "HARDWARE_TESTING"
    AUTONOMOUS_LIMIT_REACHED = "AUTONOMOUS_LIMIT_REACHED"


class TaskState(BaseModel):
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    status: str = WorkflowStatus.CREATED
    request: str = ""
    domain: str = "vhdl"
    workspace: str = ""
    generated_files: list[str] = Field(default_factory=list)
    artifacts: list[dict] = Field(default_factory=list)
    opencode_result: dict = Field(default_factory=dict)
    test_results: dict = Field(default_factory=dict)
    history: list[dict] = Field(default_factory=list)
    iterations: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
    error_message: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def add_log(self, message: str) -> None:
        timestamp = datetime.now(timezone.utc).isoformat()
        self.history.append({"timestamp": timestamp, "message": message})
        self.updated_at = timestamp

    def set_status(self, new_status: str) -> None:
        self.status = new_status
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")

    def to_json(self) -> str:
        return self.model_dump_json(indent=2)
