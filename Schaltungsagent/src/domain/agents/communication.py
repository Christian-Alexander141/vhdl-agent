from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from enum import Enum
import uuid


class MessageType(str, Enum):
    TASK_REQUEST = "TASK_REQUEST"
    TASK_RESPONSE = "TASK_RESPONSE"
    STATUS_UPDATE = "STATUS_UPDATE"
    ERROR = "ERROR"
    DIAGNOSTIC = "DIAGNOSTIC"
    REPAIR_REQUEST = "REPAIR_REQUEST"
    ARCHITECTURE_DECISION = "ARCHITECTURE_DECISION"
    VERIFICATION_RESULT = "VERIFICATION_RESULT"
    SYNTHESIS_RESULT = "SYNTHESIS_RESULT"
    HARDWARE_TEST_RESULT = "HARDWARE_TEST_RESULT"


@dataclass
class AgentMessage:
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    message_type: MessageType = MessageType.TASK_REQUEST
    sender: str = ""
    recipient: str = ""
    payload: dict = field(default_factory=dict)
    task_id: str = ""
    correlation_id: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "message_id": self.message_id,
            "message_type": self.message_type.value,
            "sender": self.sender,
            "recipient": self.recipient,
            "payload": self.payload,
            "task_id": self.task_id,
            "correlation_id": self.correlation_id,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AgentMessage":
        return cls(
            message_id=data.get("message_id", str(uuid.uuid4())),
            message_type=MessageType(data.get("message_type", "TASK_REQUEST")),
            sender=data.get("sender", ""),
            recipient=data.get("recipient", ""),
            payload=data.get("payload", {}),
            task_id=data.get("task_id", ""),
            correlation_id=data.get("correlation_id", ""),
            timestamp=data.get("timestamp", datetime.now(timezone.utc).isoformat()),
        )


@dataclass
class TaskResult:
    task_id: str
    status: str
    outputs: dict = field(default_factory=dict)
    diagnostics: list[dict] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)
    error_message: str = ""
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "status": self.status,
            "outputs": self.outputs,
            "diagnostics": self.diagnostics,
            "next_actions": self.next_actions,
            "error_message": self.error_message,
            "metadata": self.metadata,
        }


@dataclass
class VerificationResult:
    status: str
    tests_total: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    failures: list[dict] = field(default_factory=list)
    coverage: float = 0.0

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "tests_total": self.tests_total,
            "tests_passed": self.tests_passed,
            "tests_failed": self.tests_failed,
            "failures": self.failures,
            "coverage": self.coverage,
        }


@dataclass
class DebugDiagnosis:
    status: str
    stage: str
    suspected_modules: list[str] = field(default_factory=list)
    failure_type: str = ""
    evidence: list[str] = field(default_factory=list)
    recommended_action: str = ""
    severity: str = "medium"
    # Herkunft aus dem Vorfilter (domain/agents/triage.py): design,
    # verification, requirements, toolchain, hardware, infrastructure.
    origin: str = ""

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "stage": self.stage,
            "suspected_modules": self.suspected_modules,
            "failure_type": self.failure_type,
            "evidence": self.evidence,
            "recommended_action": self.recommended_action,
            "severity": self.severity,
            "origin": self.origin,
        }