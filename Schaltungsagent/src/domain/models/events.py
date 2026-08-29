import uuid
from enum import Enum
from datetime import datetime, timezone
from dataclasses import dataclass, field


class EventType(str, Enum):
    TASK_CREATED = "TASK_CREATED"
    TASK_STARTED = "TASK_STARTED"
    ANALYSIS_STARTED = "ANALYSIS_STARTED"
    ANALYSIS_FINISHED = "ANALYSIS_FINISHED"
    RAG_STARTED = "RAG_STARTED"
    RAG_FINISHED = "RAG_FINISHED"
    ARTIFACT_GENERATION_STARTED = "ARTIFACT_GENERATION_STARTED"
    ARTIFACT_GENERATION_FINISHED = "ARTIFACT_GENERATION_FINISHED"
    FILES_CREATED = "FILES_CREATED"
    WORKSPACE_READY = "WORKSPACE_READY"
    AGENT_STARTED = "AGENT_STARTED"
    AGENT_FINISHED = "AGENT_FINISHED"
    TEST_STARTED = "TEST_STARTED"
    TEST_PASSED = "TEST_PASSED"
    TEST_FAILED = "TEST_FAILED"
    REPAIR_STARTED = "REPAIR_STARTED"
    REPAIR_FINISHED = "REPAIR_FINISHED"
    VALIDATION_STARTED = "VALIDATION_STARTED"
    VALIDATION_FINISHED = "VALIDATION_FINISHED"
    SYNTHESIS_STARTED = "SYNTHESIS_STARTED"
    SYNTHESIS_FINISHED = "SYNTHESIS_FINISHED"
    APPROVAL_REQUESTED = "APPROVAL_REQUESTED"
    APPROVAL_GRANTED = "APPROVAL_GRANTED"
    APPROVAL_REJECTED = "APPROVAL_REJECTED"
    FLASH_STARTED = "FLASH_STARTED"
    FLASH_FINISHED = "FLASH_FINISHED"
    TASK_COMPLETED = "TASK_COMPLETED"
    TASK_FAILED = "TASK_FAILED"
    STATE_CHANGED = "STATE_CHANGED"
    LOG_MESSAGE = "LOG_MESSAGE"


@dataclass
class Event:
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    event_type: EventType = EventType.LOG_MESSAGE
    payload: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "task_id": self.task_id,
            "timestamp": self.timestamp,
            "event_type": self.event_type.value,
            "payload": self.payload,
        }
