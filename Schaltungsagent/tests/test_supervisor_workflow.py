"""End-to-end test for the new Supervisor-based workflow.

This test demonstrates the new multi-agent architecture with:
1. SupervisorAgent for task decomposition
2. Specialized agents for each phase
3. Task graph with dependencies
4. Comprehensive OpenCode context
"""
import asyncio
import pytest
from unittest.mock import Mock, AsyncMock, MagicMock
from pathlib import Path
import tempfile
import shutil

from src.orchestrator.supervisor_orchestrator import SupervisorOrchestrator
from src.domain.agents import AgentTask, AgentResult, AgentStatus, TaskGraph, TaskStatus
from src.domain.models import ArtifactBundle


class MockLLMService:
    """Mock LLM service for testing."""
    
    def analyze_request(self, request: str, domain: str) -> str:
        return f"Analysis: {request}"
    
    def generate_text(self, prompt: str, context: str = "", temperature: float = 0.1) -> str:
        # Return valid VHDL based on prompt content
        if "architecture" in prompt.lower() or "entwirf" in prompt.lower():
            return """
modules:
  - name: counter
    type: sequential
    inputs: [clk, rst, enable]
    outputs: [count]
    parameters:
      width: 8
    description: "8-bit counter with enable"
    dependencies: []
clock_domain: clk
reset_concept: async_active_high
decisions:
  - decision: "Use async active-high reset"
"""
        elif "entity" in prompt.lower() or "vhdl" in prompt.lower():
            return """
library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
use IEEE.NUMERIC_STD.ALL;

entity counter is
    generic (WIDTH : positive := 8);
    port (
        clk    : in  std_logic;
        rst    : in  std_logic;
        enable : in  std_logic;
        count  : out std_logic_vector(WIDTH-1 downto 0)
    );
end entity;

architecture rtl of counter is
    signal count_reg : unsigned(WIDTH-1 downto 0);
begin
    process(clk, rst)
    begin
        if rst = '1' then
            count_reg <= (others => '0');
        elsif rising_edge(clk) then
            if enable = '1' then
                count_reg <= count_reg + 1;
            end if;
        end if;
    end process;
    count <= std_logic_vector(count_reg);
end architecture;
"""
        return "generated code"
    
    def generate_project_name(self, request: str) -> str:
        return "test-project"
    
    def summarize_result(self, state_dict: dict) -> str:
        return "Summary"
    
    def classify_request(self, request: str, projects: list, domain: str, current_project: str) -> dict:
        return {"type": "new_project", "project_id": None, "reason": "test"}
    
    def answer_question(self, request: str, context: dict, domain: str) -> str:
        return "Answer"


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


class MockArtifactGenerator:
    """Mock artifact generator for testing."""
    
    def generate(self, request: str, analysis: str, domain: str = "vhdl") -> ArtifactBundle:
        return ArtifactBundle(files=[], status="generated")


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
        "llm": MockLLMService(),
        "fs": MockFileSystemService(),
        "opencode": MockOpenCodeService(),
        "validation": MockValidationService(),
        "event_publisher": MockEventPublisher(),
    }


@pytest.fixture
def orchestrator(mock_services):
    """Create SupervisorOrchestrator with mock services."""
    return SupervisorOrchestrator(
        llm_service=mock_services["llm"],
        artifact_generator=MockArtifactGenerator(),
        filesystem_service=mock_services["fs"],
        opencode_service=mock_services["opencode"],
        event_publisher=mock_services["event_publisher"],
        validation_service=mock_services["validation"],
    )


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
    
    def test_orchestrator_creation(self, orchestrator):
        """Test creating the orchestrator."""
        assert orchestrator is not None
        assert orchestrator._supervisor is not None
        assert orchestrator._supervisor._hdl_agent is not None
        assert orchestrator._supervisor._verification_agent is not None
    
    def test_execute_simple_request(self, orchestrator):
        """Test executing a simple request."""
        result = orchestrator.execute(
            request="Create a simple 8-bit counter",
            domain="vhdl",
        )
        
        assert result is not None
        assert "task_id" in result
        assert "status" in result
    
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
