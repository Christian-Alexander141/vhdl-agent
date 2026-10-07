import sys
import os
import json
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.domain.models import Workspace, Command, RunTaskCommand, TaskState
from src.domain.ports import (
    PlannerService,
    ValidationService,
    ValidationResult,
    Tool,
    ToolRegistry,
    ToolExecutor,
    ToolResult,
    EventPublisher,
)
from src.domain.workflow.workflow import Workflow
from src.domain.state_machine import StateMachine, WorkflowState
from src.domain.event_bus import EventBus
from src.domain.models import EventType, Event
from src.domain.domain_registry import DomainRegistry
from src.infrastructure.opencode.tool_registry import (
    DefaultToolRegistry,
    DefaultToolExecutor,
)
from src.infrastructure.opencode.tool_adapter import (
    ReadFileToolAdapter,
    WriteFileToolAdapter,
)
from src.infrastructure.validation.ghdl_validator import GHDLValidator


class MockTool(Tool):
    def __init__(self, name: str = "mock_tool"):
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return "Mock tool for testing"

    def execute(self, **kwargs) -> ToolResult:
        return ToolResult(success=True, output=f"Mock executed: {kwargs}")

    def to_langchain_tool(self):
        return None


class MockValidationService(ValidationService):
    def __init__(self, should_pass: bool = True):
        self._should_pass = should_pass

    def validate(self, workspace: str, domain: str = "vhdl") -> ValidationResult:
        return ValidationResult(
            passed=self._should_pass,
            message="Mock validation",
            details={"workspace": workspace, "domain": domain},
        )

    def validate_file(self, file_path: str, domain: str = "vhdl") -> ValidationResult:
        return ValidationResult(
            passed=self._should_pass,
            message="Mock file validation",
            details={"file": file_path},
        )


class MockPlannerService(PlannerService):
    def analyze_task(self, task: str, context: dict | None = None) -> dict:
        return {"status": "completed", "task": task, "analysis": f"Analyzed: {task}"}

    def create_plan(self, task: str, context: dict | None = None) -> list[dict]:
        return [{"description": "Step 1", "needs_tool": False}]

    def execute_plan(self, plan: list[dict], tools=None) -> dict:
        return {"status": "completed", "steps": [], "summary": "Plan executed"}


def test_workspace_model():
    ws = Workspace(id="test-1", root="/tmp/test")
    assert ws.id == "test-1"
    assert ws.root == "/tmp/test"
    assert ws.source_files == []
    data = ws.to_dict()
    assert data["id"] == "test-1"


def test_workspace_with_artifacts():
    ws = Workspace(
        id="test-2",
        root="/tmp/test",
        source_files=["src/main.vhd"],
        artifacts=[{"name": "main.vhd"}],
        test_results={"passed": True},
    )
    assert len(ws.source_files) == 1
    assert ws.test_results["passed"] is True


def test_run_task_command():
    cmd = RunTaskCommand(request="8-bit counter", domain="vhdl")
    assert cmd.request == "8-bit counter"
    assert cmd.domain == "vhdl"
    assert isinstance(cmd, Command)


def test_command_inheritance():
    cmd = RunTaskCommand(request="test", domain="vhdl")
    assert hasattr(cmd, "command_id")
    assert hasattr(cmd, "task_id")
    assert hasattr(cmd, "payload")


def test_tool_interface():
    tool = MockTool("test_tool")
    assert tool.name == "test_tool"
    result = tool.execute(test_arg="value")
    assert result.success is True
    assert "Mock executed" in result.output


def test_tool_result():
    result = ToolResult(success=True, output="done", data={"key": "val"})
    assert result.success is True
    assert result.output == "done"
    data = result.to_dict()
    assert data["success"] is True
    assert data["data"]["key"] == "val"


def test_tool_result_error():
    result = ToolResult(success=False, error="Something failed")
    assert result.success is False
    assert result.error == "Something failed"


def test_tool_registry():
    registry = DefaultToolRegistry()
    tool = MockTool("tool_a")
    registry.register(tool)
    assert registry.get_tool("tool_a") is tool
    assert len(registry.list_tools()) == 1
    registry.unregister("tool_a")
    assert registry.get_tool("tool_a") is None


def test_tool_registry_multiple():
    registry = DefaultToolRegistry()
    registry.register(MockTool("tool_a"))
    registry.register(MockTool("tool_b"))
    assert len(registry.list_tools()) == 2
    names = [t.name for t in registry.list_tools()]
    assert "tool_a" in names
    assert "tool_b" in names


def test_tool_executor():
    registry = DefaultToolRegistry()
    registry.register(MockTool("greet"))
    executor = DefaultToolExecutor(registry)
    result = executor.execute("greet", name="World")
    assert result.success is True
    assert "World" in result.output


def test_tool_executor_not_found():
    registry = DefaultToolRegistry()
    executor = DefaultToolExecutor(registry)
    result = executor.execute("nonexistent")
    assert result.success is False
    assert "not available" in result.error


def test_tool_executor_plan_step():
    registry = DefaultToolRegistry()
    registry.register(MockTool("echo"))
    executor = DefaultToolExecutor(registry)
    step = {"tool_name": "echo", "arguments": {"msg": "hello"}, "description": "Echo"}
    result = executor.execute_plan_step(step)
    assert "Mock executed" in result


def test_validation_service_interface():
    v = MockValidationService(should_pass=True)
    result = v.validate("/tmp/test", "vhdl")
    assert result.passed is True
    assert "Mock validation" in result.message


def test_validation_service_fail():
    v = MockValidationService(should_pass=False)
    result = v.validate("/tmp/test")
    assert result.passed is False


def test_validation_result():
    vr = ValidationResult(passed=True, message="OK", details={"count": 1})
    assert vr.passed is True
    data = vr.to_dict()
    assert data["passed"] is True
    assert data["details"]["count"] == 1


def test_planner_service_interface():
    p = MockPlannerService()
    analysis = p.analyze_task("Build a counter")
    assert analysis["status"] == "completed"
    plan = p.create_plan("Build a counter")
    assert len(plan) == 1
    result = p.execute_plan(plan)
    assert result["status"] == "completed"


def test_event_publisher_interface():
    bus = EventBus()
    assert isinstance(bus, EventPublisher)
    event = bus.publish_event(EventType.TASK_CREATED, "test-1", {"key": "val"})
    assert isinstance(event, Event)
    assert event.event_type == EventType.TASK_CREATED


def test_workflow_creates_valid_state():
    from src.services.filesystem_service import LocalFileSystemService

    wf = Workflow(
        artifact_generator=None,
        filesystem_service=LocalFileSystemService(base_dir="/tmp/test_workflow"),
        opencode_service=None,
    )
    assert wf is not None


def test_domain_registry_get_all():
    from src.config import load_config
    settings = load_config()
    domains = DomainRegistry.discover(settings.domains.search_paths)
    assert "vhdl" in domains
    info = DomainRegistry.get_all_domain_info("vhdl")
    assert info["name"] == "vhdl"
    assert "templates" in info
    assert "prompts" in info


def test_domain_registry_get_components():
    from src.config import load_config
    settings = load_config()
    DomainRegistry.discover(settings.domains.search_paths)
    templates = DomainRegistry.get_templates("vhdl")
    assert templates is not None
    prompts = DomainRegistry.get_prompts("vhdl")
    assert prompts is not None


def test_state_machine_with_validation_port():
    sm = StateMachine()
    sm.transition_to(WorkflowState.ANALYZING)
    assert sm.can_transition_to(WorkflowState.PLANNING) is True
    assert sm.can_transition_to(WorkflowState.COMPLETED) is False


def test_validator_not_available_graceful():
    v = MockValidationService(should_pass=True)
    result = v.validate("/nonexistent")
    assert result.passed is True


def test_run_task_command_serialization():
    cmd = RunTaskCommand(request="8-bit counter", domain="vhdl", task_id="t1")
    data = {"request": cmd.request, "domain": cmd.domain, "task_id": cmd.task_id}
    assert data["request"] == "8-bit counter"
    assert data["domain"] == "vhdl"
    assert data["task_id"] == "t1"


def test_tool_executor_with_plan_no_tool():
    registry = DefaultToolRegistry()
    executor = DefaultToolExecutor(registry)
    step = {"description": "Think about solution", "needs_tool": False}
    result = executor.execute_plan_step(step)
    assert "No tool for step" in result


def test_tool_langchain_conversion():
    tool = MockTool("mock")
    lc = tool.to_langchain_tool()
    assert lc is None


def test_read_file_tool_adapter():
    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = os.path.join(tmpdir, "test.txt")
        with open(file_path, "w") as f:
            f.write("hello world")
        adapter = ReadFileToolAdapter()
        result = adapter.execute(path=file_path)
        assert result.success is True
        assert result.output == "hello world"


def test_read_file_tool_adapter_not_found():
    adapter = ReadFileToolAdapter()
    result = adapter.execute(path="/tmp/nonexistent_file_xyz.txt")
    assert result.success is False
    assert "not found" in result.error


def test_write_file_tool_adapter():
    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = os.path.join(tmpdir, "new_file.txt")
        adapter = WriteFileToolAdapter()
        result = adapter.execute(path=file_path, content="test content")
        assert result.success is True
        assert os.path.exists(file_path)
        with open(file_path) as f:
            assert f.read() == "test content"


def test_tool_registry_get_langchain_tools():
    registry = DefaultToolRegistry()
    registry.register(MockTool("mock"))
    tools = registry.get_langchain_tools()
    assert tools == []


def test_workspace_defaults():
    ws = Workspace()
    assert ws.id == ""
    assert ws.root == ""
    assert ws.source_files == []
    assert ws.artifacts == []
    assert ws.test_results == {}
    assert ws.logs == []
    assert ws.metadata == {}


def test_domain_registry_list():
    from src.config import load_config
    settings = load_config()
    DomainRegistry.discover(settings.domains.search_paths)
    domains = DomainRegistry.list_domains()
    assert "vhdl" in domains
    assert DomainRegistry.has_domain("vhdl") is True


def test_domain_registry_nonexistent():
    from src.config import load_config
    settings = load_config()
    DomainRegistry.discover(settings.domains.search_paths)
    assert DomainRegistry.has_domain("nonexistent") is False
    assert DomainRegistry.get_domain("nonexistent") is None


def test_event_bus_as_publisher():
    bus = EventBus()
    assert isinstance(bus, EventPublisher)
    received = []
    bus.on_event(lambda e: received.append(e))
    bus.publish_event(EventType.TASK_STARTED, "t1")
    assert len(received) == 1


def test_pytest_raises():
    with pytest_raises(ValueError):
        raise ValueError("expected")


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
        test_workspace_model,
        test_workspace_with_artifacts,
        test_workspace_defaults,
        test_run_task_command,
        test_command_inheritance,
        test_run_task_command_serialization,
        test_tool_interface,
        test_tool_result,
        test_tool_result_error,
        test_tool_registry,
        test_tool_registry_multiple,
        test_tool_executor,
        test_tool_executor_not_found,
        test_tool_executor_plan_step,
        test_tool_executor_with_plan_no_tool,
        test_tool_langchain_conversion,
        test_tool_registry_get_langchain_tools,
        test_validation_service_interface,
        test_validation_service_fail,
        test_validation_result,
        test_planner_service_interface,
        test_event_publisher_interface,
        test_event_bus_as_publisher,
        test_workflow_creates_valid_state,
        test_domain_registry_get_all,
        test_domain_registry_get_components,
        test_domain_registry_list,
        test_domain_registry_nonexistent,
        test_state_machine_with_validation_port,
        test_validator_not_available_graceful,
        test_read_file_tool_adapter,
        test_read_file_tool_adapter_not_found,
        test_write_file_tool_adapter,
        test_pytest_raises,
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
