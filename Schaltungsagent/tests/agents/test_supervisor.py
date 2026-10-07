import pytest
import sys
import os
from unittest.mock import Mock, AsyncMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../Schaltungsagent"))

from src.agents.supervisor import SupervisorAgent
from src.domain.agents import AgentTask, AgentResult, AgentStatus
from src.domain.ports.validation_service import ValidationResult
from src.domain.models import DesignState, DesignStage


class MockLLMService:
    def analyze_request(self, request, domain="vhdl"):
        return "Analysis complete: 8-bit counter with enable"
    
    def generate_text(self, prompt, context="", temperature=0.1):
        return """
```yaml
modules:
  - name: counter
    type: sequential
    inputs: [clk, rst, enable]
    outputs: [count]
    parameters: {width: 8}
    description: "8-bit counter with enable"
    dependencies: []
interfaces: {}
clock_domain: "clk"
reset_concept: "async_active_high"
decisions: ["Single clock domain"]
```
"""
    
    def generate_project_name(self, request):
        return "test-project"


class MockFileSystemService:
    def workspace_path(self, project_id):
        return f"/tmp/{project_id}"
    
    def file_exists(self, path):
        return False
    
    def write_file(self, path, content):
        return path
    
    def read_file(self, path):
        return ""


class MockProjectMemoryService:
    def __init__(self, fs):
        pass


@pytest.fixture
def supervisor():
    llm = MockLLMService()
    fs = MockFileSystemService()
    memory = MockProjectMemoryService(fs)
    event_bus = Mock()
    
    return SupervisorAgent(
        llm_service=llm,
        filesystem_service=fs,
        event_publisher=event_bus,
        project_memory=memory,
        config={"max_iterations": 15},
    )


@pytest.mark.asyncio
async def test_supervisor_creation(supervisor):
    assert supervisor.agent_name == "SupervisorAgent"
    assert "supervise" in supervisor.supported_task_types


@pytest.mark.asyncio
async def test_supervisor_execute_creates_design_state(supervisor):
    task = AgentTask(
        id="test-1",
        type="supervise",
        project_id="proj-1",
        inputs={"request": "8-bit counter", "domain": "vhdl"},
    )
    
    # Mock sub-agents
    supervisor._architecture_agent = AsyncMock()
    supervisor._architecture_agent.execute = AsyncMock(return_value=AgentResult(
        task_id="arch-1",
        status=AgentStatus.COMPLETED,
        outputs={"architecture": {"modules": [{"name": "counter", "type": "sequential", "inputs": ["clk"], "outputs": ["count"]}], "interfaces": {}, "version": 1}}
    ))
    
    supervisor._hdl_agent = AsyncMock()
    supervisor._hdl_agent.execute = AsyncMock(return_value=AgentResult(
        task_id="hdl-1",
        status=AgentStatus.COMPLETED,
        outputs={"files": ["src/counter.vhd"]}
    ))
    
    supervisor._validation_service = AsyncMock()
    supervisor._validation_service.validate = AsyncMock(return_value=ValidationResult(passed=True, message="OK"))
    
    supervisor._verification_agent = AsyncMock()
    supervisor._verification_agent.execute = AsyncMock(return_value=AgentResult(
        task_id="ver-1",
        status=AgentStatus.COMPLETED,
        outputs={"verification_result": {"status": "passed", "tests_passed": 1}}
    ))
    
    supervisor._fpga_agent = AsyncMock()
    supervisor._fpga_agent.execute = AsyncMock(return_value=AgentResult(
        task_id="fpga-1",
        status=AgentStatus.COMPLETED,
        outputs={"bitstream_path": "/tmp/proj-1/build/counter.bit"}
    ))
    
    supervisor._hardware_test_agent = AsyncMock()
    supervisor._hardware_test_agent.execute = AsyncMock(return_value=AgentResult(
        task_id="hw-1",
        status=AgentStatus.COMPLETED,
        outputs={"hardware_result": {"status": "passed", "passed": 1, "failed": 0}}
    ))
    
    result = await supervisor.execute(task)
    
    assert result.status == AgentStatus.COMPLETED
    assert "design_state" in result.outputs


if __name__ == "__main__":
    pytest.main([__file__, "-v"])