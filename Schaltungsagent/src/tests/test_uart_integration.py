"""Regression tests for the mandatory UART integration stage."""
import asyncio
import shutil
import subprocess
from pathlib import Path

import pytest

from src.agents.architecture import ArchitectureAgent
from src.agents.hdl import HDLAgent
from src.agents.hardware_test import HardwareTestAgent
from src.agents.supervisor import SupervisorAgent
from src.domain.agents import AgentResult, AgentStatus, AgentTask
from src.domain.models import ArchitectureInfo, DesignStage, DesignState, ModuleInfo
from src.domain.state_machine import StateMachine, WorkflowState
from src.domain_plugins.vhdl.templates import VHDLTemplates
from src.services.deterministic_design import DeterministicDesignService


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


class CapturingHDLAgent:
    def __init__(self):
        self.tasks = []

    async def execute(self, task):
        self.tasks.append(task)
        files = [f"src/{task.inputs['module']['name']}.vhd"] if task.type == "implement_module" else []
        return AgentResult(
            task_id=task.id,
            status=AgentStatus.COMPLETED,
            outputs={"files": files},
        )


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


def test_missing_uart_is_added_once_and_persisted_with_original_top(tmp_path):
    supervisor = make_supervisor(
        tmp_path,
        [ModuleInfo(name="counter", type="sequential", inputs=["clk", "rst"], outputs=["count"])],
    )

    result = asyncio.run(supervisor._run_uart_integration())
    asyncio.run(supervisor._run_uart_integration())

    state = supervisor._design_state
    assert result.status == AgentStatus.COMPLETED
    assert state.architecture.top_module == "counter"
    assert [module.name for module in state.architecture.modules].count("uart") == 1
    assert state.architecture.interfaces["uart"]["ports"]["uart_rx"]["type"] == "std_logic"
    assert state.architecture.interfaces["uart"]["ports"]["uart_tx"]["type"] == "std_logic"
    assert state.metadata["uart_required"] is True
    assert state.metadata["uart_module"] == "uart"
    assert state.metadata["uart_integration_status"] == "integrated"
    restored = DesignState.from_yaml((tmp_path / "design_state.yaml").read_text())
    assert restored.architecture.top_module == "counter"
    assert restored.metadata["uart_required"] is True
    assert [module.name for module in restored.architecture.modules].count("uart") == 1


def test_existing_uart_is_normalized_not_duplicated_and_top_is_preserved(tmp_path):
    supervisor = make_supervisor(
        tmp_path,
        [
            ModuleInfo(name="counter", outputs=["count"]),
            ModuleInfo(name="UART", inputs=["clk", "rst"]),
        ],
    )

    asyncio.run(supervisor._run_uart_integration())

    names = [module.name for module in supervisor._design_state.architecture.modules]
    assert names.count("uart") == 1
    assert "UART" not in names
    assert supervisor._design_state.architecture.top_module == "counter"


def test_implementation_tasks_receive_uart_template_and_create_src_file(tmp_path):
    hdl_agent = CapturingHDLAgent()
    supervisor = make_supervisor(
        tmp_path,
        [ModuleInfo(name="counter", type="sequential"),],
        hdl_agent=hdl_agent,
    )
    asyncio.run(supervisor._run_uart_integration())

    result = asyncio.run(supervisor._run_implementation())

    uart_task = next(task for task in hdl_agent.tasks if task.inputs["module"]["name"] == "uart")
    assert result.status == AgentStatus.COMPLETED
    assert uart_task.inputs["uart_required"] is True
    assert uart_task.inputs["uart_module"] == "uart"
    assert uart_task.inputs["uart_template_path"].endswith("domain_plugins/vhdl/templates.py")
    assert "entity uart is" in uart_task.inputs["uart_template"]
    assert uart_task.inputs["uart_interface"]["uart_rx"]["type"] == "std_logic"
    assert uart_task.inputs["uart_adaptation_required"] is True
    assert "uart_tb is" in uart_task.inputs["uart_testbench"]

    agent = HDLAgent(None, None, FileSystem(tmp_path))
    generated = asyncio.run(agent.execute(AgentTask(
        id="uart-implementation",
        type="implement_module",
        project_id="uart-test-project",
        inputs={
            **uart_task.inputs,
            "workspace": str(tmp_path),
            "module": uart_task.inputs["module"],
        },
    )))
    assert generated.status == AgentStatus.COMPLETED
    assert (tmp_path / "src" / "uart.vhd").is_file()
    assert (tmp_path / "tests" / "uart_tb.vhd").is_file()
    assert "uart_rx  : in  std_logic" in (tmp_path / "src" / "uart.vhd").read_text()
    assert "uart_tx  : out std_logic" in (tmp_path / "src" / "uart.vhd").read_text()


def test_deterministic_architecture_always_gets_uart_without_llm(tmp_path):
    architecture_data = DeterministicDesignService().build_architecture("8-bit counter", "")
    original_top = architecture_data["top_module"]
    supervisor = make_supervisor(
        tmp_path,
        architecture_data["modules"],
        top_module=original_top,
    )

    asyncio.run(supervisor._run_uart_integration())

    assert supervisor._design_state.architecture.top_module == original_top
    assert [module.name for module in supervisor._design_state.architecture.modules].count("uart") == 1


def test_hardware_test_agent_selects_uart_loopback_by_exact_module_name():
    agent = HardwareTestAgent(None, None)
    suite = agent._define_test_suite({"modules": [{"name": "uart"}]}, {})
    assert any(test["name"] == "uart_loopback" for test in suite)
    other_suite = agent._define_test_suite({"modules": [{"name": "UART"}]}, {})
    assert not any(test["name"] == "uart_loopback" for test in other_suite)


def test_uart_template_and_integrated_original_top_pass_ghdl(tmp_path):
    ghdl = shutil.which("ghdl")
    if not ghdl:
        pytest.skip("GHDL is not installed")

    src = tmp_path / "src"
    src.mkdir()
    top_path = src / "counter.vhd"
    original = """library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
entity counter is
    port (clk : in std_logic; rst : in std_logic; count : out std_logic_vector(7 downto 0));
end entity;
architecture rtl of counter is
begin
    count <= (others => rst);
end architecture;
"""
    top_path.write_text(original)
    (src / "uart.vhd").write_text(VHDLTemplates.render("uart", "vhdl"))
    agent = HDLAgent(None, None, FileSystem(tmp_path))
    architecture = {"modules": [{"name": "uart", "parameters": {}}]}
    agent._integrate_uart_top(str(tmp_path), architecture, "counter")
    agent._integrate_uart_top(str(tmp_path), architecture, "counter")

    assert "entity counter is" in top_path.read_text()
    assert "count <= (others => rst)" in top_path.read_text()
    assert top_path.read_text().count("uart_bridge:") == 1
    for command in (
        [ghdl, "-a", "--std=08", "uart.vhd", "counter.vhd"],
        [ghdl, "-e", "--std=08", "counter"],
    ):
        subprocess.run(command, cwd=src, check=True, capture_output=True, text=True)


def test_existing_top_testbench_is_adapted_for_uart_ports_and_passes_ghdl(tmp_path):
    ghdl = shutil.which("ghdl")
    if not ghdl:
        pytest.skip("GHDL is not installed")

    src = tmp_path / "src"
    tests = tmp_path / "tests"
    src.mkdir()
    tests.mkdir()
    (src / "counter.vhd").write_text("""library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
entity counter is
    port (clk : in std_logic; rst : in std_logic; count : out std_logic);
end entity;
architecture rtl of counter is
begin
    count <= rst;
end architecture;
""")
    (src / "uart.vhd").write_text(VHDLTemplates.render("uart", "vhdl"))
    testbench = """library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
entity counter_tb is end entity;
architecture sim of counter_tb is
    signal clk : std_logic := '0';
    signal rst : std_logic := '0';
    signal count : std_logic;
begin
    dut: entity work.counter port map (clk => clk, rst => rst, count => count);
    process begin
        assert count = '0' severity error;
        assert false report "TB_COMPLETE" severity note;
        wait;
    end process;
end architecture;
"""
    agent = HDLAgent(None, None, FileSystem(tmp_path))
    architecture = {"modules": [{"name": "uart", "parameters": {}}]}
    agent._integrate_uart_top(str(tmp_path), architecture, "counter")
    adapted = agent._adapt_uart_testbench(testbench, str(tmp_path), "counter")
    (tests / "counter_tb.vhd").write_text(adapted)

    assert "uart_rx => uart_rx" in adapted
    assert "uart_tx => uart_tx" in adapted
    for command in (
        [ghdl, "-a", "--std=08", "src/uart.vhd", "src/counter.vhd", "tests/counter_tb.vhd"],
        [ghdl, "-e", "--std=08", "counter_tb"],
        [ghdl, "-r", "--std=08", "counter_tb", "--stop-time=1us"],
    ):
        subprocess.run(command, cwd=tmp_path, check=True, capture_output=True, text=True)


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
