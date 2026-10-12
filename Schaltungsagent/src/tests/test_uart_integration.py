"""Regression tests for the mandatory UART integration stage."""
import shutil
import subprocess
from pathlib import Path

import pytest

from src.agents.architecture import ArchitectureAgent
from src.agents.hardware_test import HardwareTestAgent
from src.agents.supervisor import SupervisorAgent
from src.domain.agents import AgentTask
from src.domain.models import ArchitectureInfo, DesignStage, DesignState
from src.domain.state_machine import StateMachine, WorkflowState
from src.domain_plugins.vhdl.templates import VHDLTemplates


class FileSystem:
    def __init__(self, workspace: Path):
        self.workspace = workspace

    def workspace_path(self, project_id: str) -> str:
        return str(self.workspace)

    def write_file(self, path: str, content: str) -> str:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        return str(target)

    def read_file(self, path: str) -> str:
        return Path(path).read_text()

    def file_exists(self, path: str) -> bool:
        return Path(path).exists()




def make_supervisor(tmp_path, modules, top_module="counter", hdl_agent=None):
    filesystem = FileSystem(tmp_path)
    supervisor = SupervisorAgent(
        filesystem_service=filesystem,
        event_publisher=None,
        project_memory=None,
        hdl_agent=hdl_agent,
    )
    supervisor._design_state = DesignState(
        architecture=ArchitectureInfo(top_module=top_module, modules=modules),
        current_stage=DesignStage.UART_INTEGRATION,
    )
    supervisor._current_task = AgentTask(
        id="uart-test-task",
        type="supervise",
        project_id="uart-test-project",
        inputs={"request": "create counter", "domain": "vhdl"},
    )
    return supervisor


def test_architecting_requires_uart_integration_before_implementation():
    state = DesignState()
    state.transition_to(DesignStage.ANALYZING)
    state.transition_to(DesignStage.ARCHITECTING)
    with pytest.raises(Exception):
        state.transition_to(DesignStage.IMPLEMENTING)
    state.transition_to(DesignStage.UART_INTEGRATION)
    state.transition_to(DesignStage.IMPLEMENTING)

    machine = StateMachine(WorkflowState.ARCHITECTING)
    assert machine.can_transition_to(WorkflowState.UART_INTEGRATION)
    machine.transition_to(WorkflowState.UART_INTEGRATION)
    machine.transition_to(WorkflowState.IMPLEMENTING)


def test_architecture_parser_keeps_explicit_top_module():
        agent = ArchitectureAgent(None)
        parsed = agent._parse_architecture_yaml(
                "modules:\n"
                "  - name: control\n"
                "    type: sequential\n"
                "  - name: display\n"
                "    type: combinational\n"
                "top_module: control\n",
                request="control and display",
        )
        assert parsed["top_module"] == "control"










def test_hardware_test_agent_selects_uart_loopback_by_exact_module_name():
    agent = HardwareTestAgent(None, None)
    suite = agent._define_test_suite({"modules": [{"name": "uart"}]}, {})
    assert any(test["name"] == "uart_loopback" for test in suite)
    other_suite = agent._define_test_suite({"modules": [{"name": "UART"}]}, {})
    assert not any(test["name"] == "uart_loopback" for test in other_suite)






def test_uart_testbench_analyzes_elaborates_and_tests_rx_tx_reset(tmp_path):
    ghdl = shutil.which("ghdl")
    if not ghdl:
        pytest.skip("GHDL is not installed")

    (tmp_path / "uart.vhd").write_text(VHDLTemplates.render("uart", "vhdl"))
    (tmp_path / "uart_tb.vhd").write_text(VHDLTemplates.render("uart", "testbench"))
    for command in (
        [ghdl, "-a", "uart.vhd", "uart_tb.vhd"],
        [ghdl, "-e", "uart_tb"],
        [ghdl, "-r", "uart_tb", "--assert-level=error", "--stop-time=10us"],
    ):
        subprocess.run(command, cwd=tmp_path, check=True, capture_output=True, text=True)
