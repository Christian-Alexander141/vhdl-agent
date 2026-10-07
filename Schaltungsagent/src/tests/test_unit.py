import sys
import os
import json
import time
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.domain.state_machine import StateMachine, WorkflowState, StateMachineError
from src.domain.event_bus import EventBus
from src.domain.models import EventType, Event, TaskState, ArtifactBundle, FileArtifact
from src.services.filesystem_service import LocalFileSystemService


def test_state_machine_initial_state():
    sm = StateMachine()
    assert sm.current == WorkflowState.CREATED


def test_state_machine_valid_transitions():
    sm = StateMachine()
    sm.transition_to(WorkflowState.ANALYZING)
    assert sm.current == WorkflowState.ANALYZING
    sm.transition_to(WorkflowState.ARCHITECTING)
    assert sm.current == WorkflowState.ARCHITECTING
    sm.transition_to(WorkflowState.IMPLEMENTING)
    assert sm.current == WorkflowState.IMPLEMENTING


def test_state_machine_invalid_transition():
    sm = StateMachine()
    with pytest_raises(StateMachineError):
        sm.transition_to(WorkflowState.COMPLETED)


def test_state_machine_can_transition():
    sm = StateMachine()
    assert sm.can_transition_to(WorkflowState.ANALYZING) is True
    assert sm.can_transition_to(WorkflowState.COMPLETED) is False


def test_state_machine_completed_has_no_transitions():
    sm = StateMachine(WorkflowState.COMPLETED)
    assert sm.can_transition_to(WorkflowState.ANALYZING) is False
    assert sm.can_transition_to(WorkflowState.FAILED) is False


def test_state_machine_full_workflow():
    sm = StateMachine()
    states = [
        WorkflowState.ANALYZING,
        WorkflowState.ARCHITECTING,
        WorkflowState.IMPLEMENTING,
        WorkflowState.STATIC_CHECK,
        WorkflowState.SIMULATING,
        WorkflowState.VALIDATING,
        WorkflowState.SYNTHESIZING,
        WorkflowState.FPGA_PROGRAMMING,
        WorkflowState.HARDWARE_TESTING,
        WorkflowState.COMPLETED,
    ]
    for state in states:
        sm.transition_to(state)
    assert sm.current == WorkflowState.COMPLETED


def test_state_machine_repair_loop():
    sm = StateMachine()
    sm.transition_to(WorkflowState.ANALYZING)
    sm.transition_to(WorkflowState.ARCHITECTING)
    sm.transition_to(WorkflowState.IMPLEMENTING)
    sm.transition_to(WorkflowState.STATIC_CHECK)
    sm.transition_to(WorkflowState.SIMULATING)
    sm.transition_to(WorkflowState.DEBUGGING)
    sm.transition_to(WorkflowState.IMPLEMENTING)
    sm.transition_to(WorkflowState.STATIC_CHECK)
    sm.transition_to(WorkflowState.SIMULATING)
    sm.transition_to(WorkflowState.VALIDATING)
    sm.transition_to(WorkflowState.SYNTHESIZING)
    sm.transition_to(WorkflowState.FPGA_PROGRAMMING)
    sm.transition_to(WorkflowState.HARDWARE_TESTING)
    sm.transition_to(WorkflowState.COMPLETED)
    assert sm.current == WorkflowState.COMPLETED


def test_event_bus_emit():
    bus = EventBus()
    received = []

    def listener(event):
        received.append(event)

    bus.on_event(listener)
    event = bus.emit_event(EventType.TASK_CREATED, "test-1", {"key": "val"})
    assert len(received) == 1
    assert received[0].event_type == EventType.TASK_CREATED
    assert received[0].task_id == "test-1"


def test_event_bus_multiple_subscribers():
    bus = EventBus()
    received1 = []
    received2 = []

    bus.on_event(lambda e: received1.append(e))
    bus.on_event(lambda e: received2.append(e))

    bus.emit_event(EventType.TASK_STARTED, "test-2")
    assert len(received1) == 1
    assert len(received2) == 1


def test_event_bus_remove_listener():
    bus = EventBus()
    received = []

    def listener(event):
        received.append(event)

    bus.on_event(listener)
    bus.emit_event(EventType.TASK_CREATED, "t1")
    bus.remove_listener(listener)
    bus.emit_event(EventType.TASK_CREATED, "t2")
    assert len(received) == 1


def test_event_bus_get_events():
    bus = EventBus()
    bus.emit_event(EventType.TASK_CREATED, "t1")
    bus.emit_event(EventType.TASK_STARTED, "t1")
    events = bus.get_events()
    assert len(events) == 2
    assert events[0].event_type == EventType.TASK_CREATED


def test_event_bus_get_events_since():
    bus = EventBus()
    bus.emit_event(EventType.TASK_CREATED, "t1")
    bus.emit_event(EventType.TASK_STARTED, "t1")
    bus.emit_event(EventType.TASK_COMPLETED, "t1")
    recent = bus.get_events(since_index=1)
    assert len(recent) == 2
    assert recent[0].event_type == EventType.TASK_STARTED


def test_event_serialization():
    event = Event(
        task_id="test-1",
        event_type=EventType.TASK_CREATED,
        payload={"request": "8-bit counter"},
    )
    data = event.to_dict()
    assert data["event_type"] == "TASK_CREATED"
    assert data["task_id"] == "test-1"
    assert data["payload"]["request"] == "8-bit counter"
    json_str = json.dumps(data)
    assert EventType.TASK_CREATED.value in json_str


def test_task_state_defaults():
    state = TaskState(request="test request", domain="vhdl")
    assert state.status == "CREATED"
    assert state.request == "test request"
    assert state.domain == "vhdl"
    assert state.generated_files == []
    assert state.error_message == ""


def test_task_state_add_log():
    state = TaskState(request="test")
    state.add_log("Test message")
    assert len(state.history) == 1
    assert state.history[0]["message"] == "Test message"
    assert "timestamp" in state.history[0]


def test_task_state_set_status():
    state = TaskState(request="test")
    state.set_status("ANALYZING")
    assert state.status == "ANALYZING"


def test_task_state_to_dict():
    state = TaskState(request="test", task_id="abc-123")
    data = state.to_dict()
    assert data["task_id"] == "abc-123"
    assert data["request"] == "test"
    assert data["status"] == "CREATED"


def test_task_state_to_json():
    state = TaskState(request="test", task_id="abc-123")
    json_str = state.to_json()
    data = json.loads(json_str)
    assert data["task_id"] == "abc-123"


def test_task_state_serialization_roundtrip():
    state = TaskState(
        request="8-bit counter",
        domain="vhdl",
        status="COMPLETED",
        generated_files=["src/counter.vhd", "tests/counter_tb.vhd"],
    )
    json_str = state.to_json()
    restored = TaskState.model_validate_json(json_str)
    assert restored.request == "8-bit counter"
    assert restored.status == "COMPLETED"
    assert len(restored.generated_files) == 2


def test_artifact_bundle():
    bundle = ArtifactBundle(
        files=[FileArtifact(name="test.vhd", content="-- VHDL", path="src/test.vhd")],
        status="generated",
    )
    assert len(bundle.files) == 1
    assert bundle.files[0].name == "test.vhd"


def test_artifact_bundle_to_dict():
    bundle = ArtifactBundle(
        files=[FileArtifact(name="test.vhd", content="-- VHDL", path="src/test.vhd")],
    )
    data = bundle.to_dict()
    assert len(data["files"]) == 1
    assert data["files"][0]["name"] == "test.vhd"


def test_file_artifact_to_dict():
    fa = FileArtifact(name="test.vhd", content="code", path="src/test.vhd")
    data = fa.to_dict()
    assert data["name"] == "test.vhd"
    assert data["content"] == "code"


def test_filesystem_create_workspace():
    with tempfile.TemporaryDirectory() as tmpdir:
        fs = LocalFileSystemService(base_dir=tmpdir)
        ws = fs.create_workspace("test-task")
        assert os.path.isdir(ws)
        for sub in ["src", "tests", "docs", "build", "logs", "reports"]:
            assert os.path.isdir(os.path.join(ws, sub))


def test_filesystem_write_and_read():
    with tempfile.TemporaryDirectory() as tmpdir:
        fs = LocalFileSystemService(base_dir=tmpdir)
        ws = fs.create_workspace("test-read")
        file_path = os.path.join(ws, "src", "test.vhd")
        fs.write_file(file_path, "-- test content")
        assert fs.file_exists(file_path)
        content = fs.read_file(file_path)
        assert content == "-- test content"


def test_filesystem_list_files():
    with tempfile.TemporaryDirectory() as tmpdir:
        fs = LocalFileSystemService(base_dir=tmpdir)
        ws = fs.create_workspace("test-list")
        fs.write_file(os.path.join(ws, "src", "a.vhd"), "a")
        fs.write_file(os.path.join(ws, "tests", "b.vhd"), "b")
        files = fs.list_files(ws)
        assert len(files) == 2
        assert "src/a.vhd" in files
        assert "tests/b.vhd" in files


def test_filesystem_delete_workspace():
    with tempfile.TemporaryDirectory() as tmpdir:
        fs = LocalFileSystemService(base_dir=tmpdir)
        fs.create_workspace("test-del")
        assert os.path.isdir(os.path.join(tmpdir, "test-del"))
        fs.delete_workspace("test-del")
        assert not os.path.exists(os.path.join(tmpdir, "test-del"))


def test_filesystem_cleanup_expired():
    with tempfile.TemporaryDirectory() as tmpdir:
        fs = LocalFileSystemService(base_dir=tmpdir, cleanup_ttl_hours=0)
        fs.create_workspace("old-task")
        removed = fs.cleanup_expired()
        assert removed == 1
        assert not os.path.exists(os.path.join(tmpdir, "old-task"))


def test_filesystem_workspace_count():
    with tempfile.TemporaryDirectory() as tmpdir:
        fs = LocalFileSystemService(base_dir=tmpdir)
        fs.create_workspace("ws-1")
        fs.create_workspace("ws-2")
        assert fs.workspace_count() == 2


def test_state_machine_transition_logging():
    sm = StateMachine()
    transitions = [
        (WorkflowState.CREATED, WorkflowState.ANALYZING, True),
        (WorkflowState.ANALYZING, WorkflowState.ARCHITECTING, True),
        (WorkflowState.ARCHITECTING, WorkflowState.FAILED, True),
        (WorkflowState.TESTING, WorkflowState.CREATED, False),
        (WorkflowState.FAILED, WorkflowState.CREATED, False),
    ]
    for from_state, to_state, should_succeed in transitions:
        sm = StateMachine(from_state)
        if should_succeed:
            sm.transition_to(to_state)
            assert sm.current == to_state
        else:
            try:
                sm.transition_to(to_state)
                assert False, f"Should have failed: {from_state} -> {to_state}"
            except StateMachineError:
                pass


def test_event_bus_listener_exception_handling():
    bus = EventBus()
    errors = []

    def failing_listener(event):
        raise ValueError("test error")

    def error_catcher(event):
        errors.append(event)

    bus.on_event(failing_listener)
    bus.on_event(error_catcher)
    bus.emit_event(EventType.TASK_CREATED, "t1")
    assert len(errors) == 1


def test_event_bus_clear():
    bus = EventBus()
    bus.emit_event(EventType.TASK_CREATED, "t1")
    bus.clear()
    assert len(bus.get_events()) == 0


def test_event_default_task_id():
    event = Event(event_type=EventType.TASK_CREATED)
    assert event.task_id == ""


def test_event_publish_event_return_value():
    bus = EventBus()
    event = bus.emit_event(EventType.TASK_CREATED, "test-123", {"key": "value"})
    assert isinstance(event, Event)
    assert event.event_type == EventType.TASK_CREATED
    assert event.task_id == "test-123"
    assert event.payload["key"] == "value"


def test_pydantic_serialization():
    state = TaskState(
        request="test",
        generated_files=["a.vhd"],
        metadata={"analysis": "test analysis", "knowledge": {"rules": []}},
    )
    data = state.to_dict()
    assert data["request"] == "test"
    assert data["metadata"]["analysis"] == "test analysis"
    assert data["metadata"]["knowledge"]["rules"] == []


def pytest_raises(exc_class):
    return _PytestRaisesContext(exc_class)


class _PytestRaisesContext:
    def __init__(self, exc_class):
        self.exc_class = exc_class

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            raise AssertionError(f"Expected {self.exc_class.__name__} but no exception was raised")
        if issubclass(exc_type, self.exc_class):
            return True
        raise AssertionError(f"Expected {self.exc_class.__name__} but got {exc_type.__name__}")


if __name__ == "__main__":
    tests = [
        test_state_machine_initial_state,
        test_state_machine_valid_transitions,
        test_state_machine_invalid_transition,
        test_state_machine_can_transition,
        test_state_machine_completed_has_no_transitions,
        test_state_machine_full_workflow,
        test_state_machine_repair_loop,
        test_event_bus_emit,
        test_event_bus_multiple_subscribers,
        test_event_bus_remove_listener,
        test_event_bus_get_events,
        test_event_bus_get_events_since,
        test_event_serialization,
        test_task_state_defaults,
        test_task_state_add_log,
        test_task_state_set_status,
        test_task_state_to_dict,
        test_task_state_to_json,
        test_task_state_serialization_roundtrip,
        test_artifact_bundle,
        test_artifact_bundle_to_dict,
        test_file_artifact_to_dict,
        test_filesystem_create_workspace,
        test_filesystem_write_and_read,
        test_filesystem_list_files,
        test_filesystem_delete_workspace,
        test_filesystem_cleanup_expired,
        test_filesystem_workspace_count,
        test_state_machine_transition_logging,
        test_event_bus_listener_exception_handling,
        test_event_bus_clear,
        test_event_default_task_id,
        test_event_publish_event_return_value,
        test_pydantic_serialization,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            print(f"  [PASS] {test.__name__}")
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {test.__name__}: {e}")
            failed += 1

    print(f"\n{'='*50}")
    print(f"  {passed} passed, {failed} failed, {len(tests)} total")
    print(f"{'='*50}")
    sys.exit(0 if failed == 0 else 1)
