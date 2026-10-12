"""End-to-end test for the new Supervisor-based workflow.

This test demonstrates the new multi-agent architecture with:
1. SupervisorAgent for task decomposition
2. Specialized agents for each phase
3. Task graph with dependencies
4. Comprehensive OpenCode context
"""
import pytest
from pathlib import Path
import tempfile

from src.domain.agents import AgentTask, TaskGraph, TaskStatus




class MockFileSystemService:
    """Mock filesystem service for testing."""
    
    def __init__(self):
        self.workspaces = {}
        self.base_dir = Path(tempfile.mkdtemp())
    
    def create_workspace(self, task_id: str, domain: str) -> str:
        ws = self.base_dir / task_id
        ws.mkdir(parents=True)
        (ws / "src").mkdir()
        (ws / "tests").mkdir()
        self.workspaces[task_id] = str(ws)
        return str(ws)
    
    def workspace_path(self, task_id: str) -> str:
        return self.workspaces.get(task_id, str(self.base_dir / task_id))
    
    def write_file(self, file_path: str, content: str) -> str:
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)
        Path(file_path).write_text(content)
        return file_path
    
    def read_file(self, file_path: str) -> str:
        return Path(file_path).read_text()
    
    def file_exists(self, file_path: str) -> bool:
        return Path(file_path).exists()
    
    def list_files(self, workspace_path: str, pattern: str = "**/*") -> list[str]:
        ws = Path(workspace_path)
        if not ws.exists():
            return []
        return [str(f.relative_to(ws)) for f in ws.glob(pattern) if f.is_file()]




class MockOpenCodeService:
    """Mock OpenCode service for testing."""
    
    def execute(self, workspace: str, instruction: str, timeout_seconds: int | None = None):
        class Result:
            success = True
            returncode = 0
            stdout = "OpenCode executed successfully"
            stderr = ""
            
            def to_dict(self):
                return {
                    "success": self.success,
                    "returncode": self.returncode,
                    "stdout": self.stdout,
                    "stderr": self.stderr,
                }
        return Result()


class MockValidationService:
    """Mock validation service for testing."""
    
    def validate(self, workspace: str, domain: str):
        class ValidationResult:
            passed = True
            message = "All tests passed"
            details = {
                "tests_total": 1,
                "tests_passed": 1,
                "tests_failed": 0,
                "failures": [],
            }
            
            def build_repair_instruction(self, original_request: str, iteration: int) -> str:
                return f"Repair iteration {iteration}: Fix the errors"
        return ValidationResult()


class MockEventPublisher:
    """Mock event publisher for testing."""
    
    def publish_event(self, event_type, task_id, payload):
        pass


@pytest.fixture
def mock_services():
    """Create mock services for testing."""
    return {
        "fs": MockFileSystemService(),
        "opencode": MockOpenCodeService(),
        "validation": MockValidationService(),
        "event_publisher": MockEventPublisher(),
    }




class TestTaskGraph:
    """Test the TaskGraph implementation."""
    
    def test_task_graph_creation(self):
        """Test creating a task graph."""
        graph = TaskGraph()
        
        task1 = AgentTask(
            id="task-1",
            type="architecture",
            project_id="test-project",
            depends_on=[],
        )
        
        task2 = AgentTask(
            id="task-2",
            type="implement_hdl",
            project_id="test-project",
            depends_on=["task-1"],
        )
        
        graph.add_task(task1)
        graph.add_task(task2)
        
        assert len(graph.get_all_tasks()) == 2
    
    def test_task_graph_ready_tasks(self):
        """Test getting ready tasks."""
        graph = TaskGraph()
        
        task1 = AgentTask(
            id="task-1",
            type="architecture",
            project_id="test-project",
            depends_on=[],
        )
        
        task2 = AgentTask(
            id="task-2",
            type="implement_hdl",
            project_id="test-project",
            depends_on=["task-1"],
        )
        
        graph.add_task(task1)
        graph.add_task(task2)
        
        # Initially, only task-1 should be ready
        ready = graph.get_ready_tasks()
        assert len(ready) == 1
        assert ready[0].id == "task-1"
        
        # Mark task-1 as passed
        graph.update_task_status("task-1", TaskStatus.PASSED)
        
        # Now task-2 should be ready
        ready = graph.get_ready_tasks()
        assert len(ready) == 1
        assert ready[0].id == "task-2"


class TestSupervisorOrchestrator:
    """Test the SupervisorOrchestrator."""
    
    
    
    def test_context_builder(self, mock_services):
        """Test the context builder."""
        from src.services.opencode_context import OpenCodeContextBuilder
        
        builder = OpenCodeContextBuilder(mock_services["fs"])
        
        context = builder.build_context(
            workspace="/tmp/test-project",
            task={
                "id": "test-task",
                "type": "implement_hdl",
                "project_id": "test-project",
                "inputs": {"request": "Create a counter"},
            },
            architecture={
                "modules": [
                    {
                        "name": "counter",
                        "type": "sequential",
                        "inputs": ["clk", "rst", "enable"],
                        "outputs": ["count"],
                    }
                ],
                "clock_domain": "clk",
                "reset_concept": "async_active_high",
            },
        )
        
        assert "PROJECT" in context
        assert "ARCHITECTURE" in context
        assert "counter" in context


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
