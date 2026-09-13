from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from enum import Enum


class AgentStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    REPAIR_REQUIRED = "REPAIR_REQUIRED"


class TaskStatus(str, Enum):
    CREATED = "CREATED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    VERIFYING = "VERIFYING"
    PASSED = "PASSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REPAIR_REQUIRED = "REPAIR_REQUIRED"
    BLOCKED = "BLOCKED"


class MessageType(str, Enum):
    TASK_REQUEST = "TASK_REQUEST"
    TASK_RESPONSE = "TASK_RESPONSE"
    STATUS_UPDATE = "STATUS_UPDATE"
    ERROR = "ERROR"
    DIAGNOSTIC = "DIAGNOSTIC"
    REPAIR_REQUEST = "REPAIR_REQUEST"
    APPROVAL_REQUEST = "APPROVAL_REQUEST"


@dataclass
class AgentTask:
    id: str
    type: str
    project_id: str
    inputs: dict = field(default_factory=dict)
    constraints: dict = field(default_factory=dict)
    context: dict = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    assigned_agent: str = ""
    parent_task_id: str | None = None
    
    # New fields for task graph
    depends_on: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    expected_artifacts: list[str] = field(default_factory=list)
    status: TaskStatus = TaskStatus.CREATED
    result: dict = field(default_factory=dict)
    error: str = ""
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "project_id": self.project_id,
            "inputs": self.inputs,
            "constraints": self.constraints,
            "context": self.context,
            "created_at": self.created_at,
            "assigned_agent": self.assigned_agent,
            "parent_task_id": self.parent_task_id,
            "depends_on": self.depends_on,
            "acceptance_criteria": self.acceptance_criteria,
            "expected_artifacts": self.expected_artifacts,
            "status": self.status.value if isinstance(self.status, TaskStatus) else self.status,
            "result": self.result,
            "error": self.error,
        }


@dataclass
class AgentResult:
    task_id: str
    status: AgentStatus
    outputs: dict = field(default_factory=dict)
    diagnostics: list[dict] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)
    error_message: str = ""
    completed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    iterations: int = 0


@dataclass
class AgentMessage:
    message_id: str
    message_type: MessageType
    sender: str
    recipient: str
    payload: dict
    task_id: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class BaseAgent(ABC):
    def __init__(self, agent_name: str, event_bus=None):
        self.agent_name = agent_name
        self.event_bus = event_bus
        self._current_task: AgentTask | None = None

    @property
    @abstractmethod
    def supported_task_types(self) -> list[str]:
        pass

    @abstractmethod
    async def execute(self, task: AgentTask) -> AgentResult:
        pass

    def can_handle(self, task_type: str) -> bool:
        return task_type in self.supported_task_types

    def emit_event(self, event_type: str, payload: dict) -> None:
        if self.event_bus:
            from src.domain.models.events import EventType
            try:
                event_payload = dict(payload)
                event_payload.setdefault("agent", self.agent_name)
                self.event_bus.publish_event(
                    EventType(event_type),
                    event_payload.get("task_id", ""),
                    event_payload,
                )
            except ValueError:
                pass