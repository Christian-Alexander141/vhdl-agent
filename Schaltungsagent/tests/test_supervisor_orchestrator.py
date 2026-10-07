import threading
import time

from src.domain.models import EventType
from src.orchestrator.supervisor_orchestrator import SupervisorOrchestrator


class EventRecorder:
    def __init__(self):
        self.events = []

    def publish_event(self, event_type, task_id="", payload=None):
        self.events.append((event_type, task_id, payload or {}))


def make_orchestrator():
    orchestrator = SupervisorOrchestrator.__new__(SupervisorOrchestrator)
    orchestrator._approval_events = {}
    orchestrator._approval_results = {}
    orchestrator._approval_lock = threading.Lock()
    orchestrator._events = EventRecorder()
    return orchestrator


def test_approval_can_be_granted_from_another_thread():
    orchestrator = make_orchestrator()
    result = {}

    worker = threading.Thread(
        target=lambda: result.setdefault(
            "value", orchestrator._wait_for_approval("task-1", "/tmp/design.bit")
        )
    )
    worker.start()

    for _ in range(100):
        if "task-1" in orchestrator._approval_events:
            break
        time.sleep(0.001)

    assert orchestrator.approve_task("task-1", "looks good") is True
    worker.join(timeout=1)

    assert result["value"] == (True, "looks good")
    assert orchestrator._events.events[0][0] == EventType.APPROVAL_REQUESTED


def test_unknown_approval_task_is_rejected():
    orchestrator = make_orchestrator()

    assert orchestrator.approve_task("unknown") is False
    assert orchestrator.reject_task("unknown", "needs changes") is False
