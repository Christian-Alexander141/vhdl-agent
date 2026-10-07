import pytest
import sys
import os
from unittest.mock import Mock, AsyncMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../Schaltungsagent"))

from src.agents.architecture import ArchitectureAgent
from src.domain.agents import AgentTask, AgentResult, AgentStatus


@pytest.fixture
def architecture_agent():
    event_bus = Mock()
    return ArchitectureAgent(plan_service=None, event_publisher=event_bus)


@pytest.mark.asyncio
async def test_architecture_agent_creation(architecture_agent):
    assert architecture_agent.agent_name == "ArchitectureAgent"
    assert "create_architecture" in architecture_agent.supported_task_types


@pytest.mark.asyncio
async def test_create_architecture(architecture_agent):
    task = AgentTask(
        id="test-1",
        type="create_architecture",
        project_id="proj-1",
        inputs={
            "request": "8-bit CPU with ALU and register file",
            "analysis": "Requires ALU and register file",
            "knowledge": {"coding_rules": [], "reference_designs": []},
            "domain": "vhdl",
            "manifest": {
                "project_name": "cpu-design",
                "top_entity": "alu",
                "modules": [
                    {"entity": "alu", "file": "src/alu.vhd", "role": "Arithmetic Logic Unit", "type": "combinational", "inputs": ["a", "b", "operation"], "outputs": ["result", "flags"], "parameters": {"width": 8}, "depends_on": []},
                    {"entity": "register_file", "file": "src/register_file.vhd", "role": "Register File", "type": "sequential", "inputs": ["clk", "rst"], "outputs": ["data"], "parameters": {"width": 8, "depth": 16}, "depends_on": []},
                ],
                "testbenches": [],
                "open_questions": [],
            },
        },
    )
    
    result = await architecture_agent.execute(task)
    
    assert result.status == AgentStatus.COMPLETED
    assert "architecture" in result.outputs
    arch = result.outputs["architecture"]
    assert "modules" in arch
    assert len(arch["modules"]) == 2
    assert arch["modules"][0]["name"] == "alu"
    assert arch["modules"][1]["name"] == "register_file"


@pytest.mark.asyncio
async def test_validate_architecture(architecture_agent):
    task = AgentTask(
        id="test-2",
        type="validate_architecture",
        project_id="proj-1",
        inputs={
            "architecture": {
                "modules": [
                    {"name": "top", "dependencies": []},
                    {"name": "sub", "dependencies": ["top"]},
                ]
            }
        },
    )
    
    result = await architecture_agent.execute(task)
    
    assert result.status == AgentStatus.COMPLETED
    assert result.outputs.get("valid") is True


@pytest.mark.asyncio
async def test_validate_architecture_missing_dependency(architecture_agent):
    task = AgentTask(
        id="test-3",
        type="validate_architecture",
        project_id="proj-1",
        inputs={
            "architecture": {
                "modules": [
                    {"name": "sub", "dependencies": ["missing_module"]},
                ]
            }
        },
    )
    
    result = await architecture_agent.execute(task)
    
    assert result.status == AgentStatus.FAILED
    assert "validation_error" in str(result.diagnostics)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])