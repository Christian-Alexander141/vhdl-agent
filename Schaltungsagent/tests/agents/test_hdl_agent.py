import pytest
import sys
import os
import re
from pathlib import Path
from unittest.mock import Mock, AsyncMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../Schaltungsagent"))

from src.agents.hdl import HDLAgent
from src.domain.agents import AgentTask, AgentResult, AgentStatus
from src.domain.models import ModuleInfo


class MockLLMService:
    def __init__(self):
        self.generate_text_calls = 0

    def generate_text(self, prompt, context="", temperature=0.1):
        self.generate_text_calls += 1
        return ""


class MockOpenCodeService:
    def __init__(self):
        self.instructions = []

    def execute(self, workspace, instruction, timeout_seconds=None):
        self.instructions.append(instruction)
        task_path = re.search(r"\.opencode_tasks/([\w.-]+)", instruction)
        task_text = (
            Path(workspace, ".opencode_tasks", task_path.group(1)).read_text()
            if task_path else instruction
        )
        target = re.search(r"direkt in ([^\s]+\.vhd)", task_text)
        relative_path = target.group(1) if target else "tests/counter_tb.vhd"
        name = Path(relative_path).stem
        if name.endswith("_tb"):
            content = f"""library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
entity {name} is end entity;
architecture sim of {name} is begin
    assert false report "TB_COMPLETE" severity note;
end architecture;
"""
        else:
            content = f"""library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
entity {name} is
    port (clk : in std_logic; rst : in std_logic; enable : in std_logic;
          count : out std_logic_vector(7 downto 0));
end entity;
architecture rtl of {name} is begin
    count <= (others => '0');
end architecture;
"""
        Path(workspace, relative_path).parent.mkdir(parents=True, exist_ok=True)
        Path(workspace, relative_path).write_text(content)

        class Result:
            success = True
            returncode = 0
            stderr = ""
            stdout = "File written"
        return Result()


class MockFileSystemService:
    def __init__(self):
        self.files = {}
    
    def file_exists(self, path):
        return path in self.files
    
    def write_file(self, path, content):
        self.files[path] = content
        return path
    
    def read_file(self, path):
        return self.files.get(path, "")
    
    def workspace_path(self, project_id):
        return f"/tmp/{project_id}"


@pytest.fixture
def hdl_agent():
    opencode = MockOpenCodeService()
    fs = MockFileSystemService()
    event_bus = Mock()
    
    return HDLAgent(
        opencode_service=opencode,
        filesystem_service=fs,
        event_publisher=event_bus,
    )


@pytest.mark.asyncio
async def test_hdl_agent_creation(hdl_agent):
    assert hdl_agent.agent_name == "HDLAgent"
    assert "implement_hdl" in hdl_agent.supported_task_types


@pytest.mark.asyncio
async def test_implement_hdl(hdl_agent):
    task = AgentTask(
        id="test-1",
        type="implement_hdl",
        project_id="proj-1",
        inputs={
            "architecture": {
                "modules": [
                    {
                        "name": "counter",
                        "type": "sequential",
                        "inputs": ["clk", "rst", "enable"],
                        "outputs": ["count"],
                        "parameters": {"width": 8},
                        "description": "8-bit counter",
                        "dependencies": [],
                    }
                ],
                "clock_domain": "clk",
                "reset_concept": "async_active_high",
            },
            "workspace": "/tmp/proj-1",
            "domain": "vhdl",
        },
    )
    
    result = await hdl_agent.execute(task)
    
    assert result.status == AgentStatus.COMPLETED
    assert "files" in result.outputs
    assert len(result.outputs["files"]) > 0
    assert not hasattr(hdl_agent, "_llm")
    assert len(hdl_agent._opencode.instructions) == 2
    assert "entity counter" in hdl_agent._fs.files["/tmp/proj-1/src/counter.vhd"]


class _DiskFileSystem:
    def write_file(self, path, content):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(content)
        return path


class _StdoutOpenCode:
    def __init__(self, stdout):
        self.stdout = stdout
        self.instructions = []

    def execute(self, workspace, instruction, timeout_seconds=None):
        self.instructions.append(instruction)

        class Result:
            success = True
            stderr = ""
        Result.stdout = self.stdout
        return Result()


class _FileWritingOpenCode:
    """Wie echtes OpenCode: schreibt die Testbench-Datei selbst; stdout ist nur Log."""

    def __init__(self, testbench, stdout="\x1b[0m> build · some-model\x1b[0m"):
        self.testbench = testbench
        self.stdout = stdout
        self.instructions = []

    def execute(self, workspace, instruction, timeout_seconds=None):
        self.instructions.append(instruction)
        if self.testbench is not None:
            target = Path(workspace) / "tests" / "counter_tb.vhd"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(self.testbench)

        class Result:
            success = True
            returncode = 0
            stderr = ""
        Result.stdout = self.stdout
        return Result()


_COUNTER_SRC = """library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
entity counter is
    port (clk : in std_logic; count : out std_logic_vector(7 downto 0));
end entity;
architecture rtl of counter is begin
    count <= (others => '0');
end architecture;
"""

_COUNTER_TB = """library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
entity counter_tb is end entity;
architecture sim of counter_tb is
    signal clk : std_logic := '0';
    signal count : std_logic_vector(7 downto 0);
begin
    dut: entity work.counter port map (clk => clk, count => count);
    process begin
        wait for 10 ns;
        assert count = x"00" report "count must be zero" severity error;
        report "TB_COMPLETE" severity note;
        wait;
    end process;
end architecture;
"""


def _counter_workspace(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "counter.vhd").write_text(_COUNTER_SRC)
    return str(tmp_path)


@pytest.mark.asyncio
async def test_verification_testbench_uses_opencode(tmp_path):
    import shutil
    from src.agents.verification import VerificationAgent

    if not shutil.which("ghdl"):
        pytest.skip("GHDL is not installed")
    opencode = _FileWritingOpenCode(_COUNTER_TB)
    agent = VerificationAgent(filesystem_service=_DiskFileSystem(), opencode_service=opencode)
    task = AgentTask(
        id="test-tb",
        type="generate_testbench",
        project_id="proj-1",
        inputs={"module": {"name": "counter"}, "workspace": _counter_workspace(tmp_path)},
    )

    result = await agent.execute(task)

    assert result.status == AgentStatus.COMPLETED, result.error_message
    assert not hasattr(agent, "_llm")
    assert len(opencode.instructions) == 1
    assert (tmp_path / "tests" / "counter_tb.vhd").read_text().strip() == _COUNTER_TB.strip()


@pytest.mark.asyncio
async def test_verification_rejects_testbench_without_dut_and_keeps_previous(tmp_path):
    from src.agents.verification import VerificationAgent

    workspace = _counter_workspace(tmp_path)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "counter_tb.vhd").write_text(_COUNTER_TB)
    fake_tb = """entity counter_tb is end entity;
architecture sim of counter_tb is begin
    assert false report "TB_COMPLETE" severity note;
end architecture;"""
    agent = VerificationAgent(
        filesystem_service=_DiskFileSystem(), opencode_service=_FileWritingOpenCode(fake_tb),
    )

    result = await agent.execute(AgentTask(
        id="test-tb-fake",
        type="generate_testbench",
        project_id="proj-1",
        inputs={"module": {"name": "counter"}, "workspace": workspace},
    ))

    assert result.status == AgentStatus.FAILED
    assert "does not instantiate DUT" in result.error_message
    assert (tmp_path / "tests" / "counter_tb.vhd").read_text() == _COUNTER_TB


@pytest.mark.asyncio
async def test_review_hdl_no_issues(hdl_agent):
    hdl_agent._fs.files["/tmp/proj-1/src/counter.vhd"] = """
library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
entity counter is port (clk: in std_logic; count: out std_logic_vector(7 downto 0)); end entity;
architecture rtl of counter is begin process(clk) begin end process; end architecture;
"""
    
    task = AgentTask(
        id="test-2",
        type="review_hdl",
        project_id="proj-1",
        inputs={
            "workspace": "/tmp/proj-1",
            "files": ["src/counter.vhd"],
        },
    )
    
    result = await hdl_agent.execute(task)
    
    assert result.status == AgentStatus.COMPLETED
    assert result.outputs["issues"] == 0


@pytest.mark.asyncio
async def test_review_hdl_with_wait(hdl_agent):
    hdl_agent._fs.files["/tmp/proj-1/src/bad.vhd"] = """
library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
entity bad is port (clk: in std_logic; q: out std_logic); end entity;
architecture rtl of bad is begin process begin wait for 10 ns; end process; end architecture;
"""
    
    task = AgentTask(
        id="test-3",
        type="review_hdl",
        project_id="proj-1",
        inputs={
            "workspace": "/tmp/proj-1",
            "files": ["src/bad.vhd"],
        },
    )
    
    result = await hdl_agent.execute(task)
    
    assert result.status == AgentStatus.FAILED
    assert len(result.diagnostics) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

@pytest.mark.asyncio
async def test_verification_never_takes_testbench_code_from_console_output(tmp_path):
    """Lauf gray-countdown 2026-10-11: ANSI-Codes und Kopfzeile aus stdout landeten
    als Testbench im Projekt. Nur die von OpenCode geschriebene Datei zählt."""
    from src.agents.verification import VerificationAgent

    workspace = _counter_workspace(tmp_path)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "counter_tb.vhd").write_text(_COUNTER_TB)
    agent = VerificationAgent(
        filesystem_service=_DiskFileSystem(),
        opencode_service=_FileWritingOpenCode(None, stdout="\x1b[0m> build · longcat\x1b[0m\n" + _COUNTER_TB),
    )
    result = await agent.execute(AgentTask(
        id="test-tb-stdout", type="generate_testbench", project_id="proj-1",
        inputs={"module": {"name": "counter"}, "workspace": workspace},
    ))
    assert result.status == AgentStatus.FAILED
    assert (tmp_path / "tests" / "counter_tb.vhd").read_text() == _COUNTER_TB
