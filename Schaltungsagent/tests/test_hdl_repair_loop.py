"""Deterministic End-to-End test for the HDL error detection and repair loop.

Tests the complete flow:
  User Request
    → SupervisorOrchestrator
    → ArchitectureAgent
    → HDLAgent (generates broken VHDL)
    → VerificationAgent (REAL GHDL detects error)
    → Supervisor creates Debug/Repair task
    → DebugAgent (produces structured diagnosis)
    → HDLAgent (repairs VHDL)
    → VerificationAgent (REAL GHDL passes)

Also tests:
  - Infrastructure failure classification (missing library → BLOCKED)
  - Max repair attempts (non-repairable → BLOCKED after N attempts)
  - DesignState history tracking
  - Event trace observability
"""
import logging
import os
import sys
import tempfile
import shutil
from pathlib import Path

import pytest

# Schaltungsagent on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# VHDL Templates – deterministic, no LLM needed
# ---------------------------------------------------------------------------

VHDL_ENTITY = """\
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
"""

# Broken: references undeclared signal 'data_out' – GHDL analysis will fail
VHDL_BROKEN = VHDL_ENTITY + """\
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
    data_out <= std_logic_vector(count_reg);
end architecture;
"""

# Fixed: removed the undeclared signal reference
VHDL_FIXED = VHDL_ENTITY + """\
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

# Always-valid testbench (uses severity warning for TB_COMPLETE marker)
TESTBENCH = """\
library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
use IEEE.NUMERIC_STD.ALL;

entity counter_tb is
end entity;

architecture sim of counter_tb is
    signal clk    : std_logic := '0';
    signal rst    : std_logic := '0';
    signal enable : std_logic := '0';
    signal count  : std_logic_vector(7 downto 0);
    constant CLK_PERIOD : time := 10 ns;
begin
    dut: entity work.counter
        generic map (WIDTH => 8)
        port map (clk => clk, rst => rst, enable => enable, count => count);

    clk_gen: process
    begin
        clk <= '0'; wait for CLK_PERIOD / 2;
        clk <= '1'; wait for CLK_PERIOD / 2;
    end process;

    stim: process
    begin
        rst <= '1'; enable <= '0';
        wait for CLK_PERIOD * 2;
        rst <= '0';
        wait for CLK_PERIOD;
        enable <= '1';
        wait for CLK_PERIOD * 10;

        assert unsigned(count) = 10
            report "Expected count=10, got " & integer'image(to_integer(unsigned(count)))
            severity error;

        enable <= '0';
        wait for CLK_PERIOD * 5;

        assert unsigned(count) = 10
            report "Expected count=10 (disabled), got " & integer'image(to_integer(unsigned(count)))
            severity error;

        rst <= '1';
        wait for CLK_PERIOD;
        assert unsigned(count) = 0
            report "Expected count=0 after reset, got " & integer'image(to_integer(unsigned(count)))
            severity error;

        report "TB_COMPLETE: PASS" severity warning;
        wait;
    end process;
end architecture;
"""

# Non-repairable VHDL: semantically broken (infinite loop in combinational)
VHDL_UNREPAIRABLE = VHDL_ENTITY + """\
architecture rtl of counter is
begin
    process(clk, rst)
        variable i : integer := 0;
    begin
        while true loop
            i := i + 1;
        end loop;
    end process;
    count <= (others => '0');
end architecture;
"""


# ---------------------------------------------------------------------------
# Architecture YAML for the test
# ---
ARCHITECTURE_YAML = """\
modules:
  - name: counter
    type: sequential
    inputs: [clk, rst, enable]
    outputs: [count]
    parameters:
      width: 8
    description: "8-bit counter with enable and synchronous reset"
    dependencies: []
clock_domain: clk
reset_concept: sync_active_high
decisions:
  - decision: "Use synchronous active-high reset"
"""


# ---------------------------------------------------------------------------
# Mock Services
# ---------------------------------------------------------------------------











# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestHDLRepairLoop:
    """E2E: broken VHDL → GHDL fail → debug diagnose → repair → GHDL pass."""






    def test_ghdl_rejects_broken_vhdl(self):
        """Verify that the real GHDLValidator rejects VHDL_BROKEN and accepts VHDL_FIXED."""
        from src.infrastructure.validation.ghdl_validator import GHDLValidator

        validator = GHDLValidator()
        tmp = tempfile.mkdtemp(prefix="ghdl_check_")
        try:
            # --- Test broken VHDL ---
            ws_broken = Path(tmp) / "broken"
            (ws_broken / "src").mkdir(parents=True)
            (ws_broken / "tests").mkdir(parents=True)
            (ws_broken / "build").mkdir(parents=True)
            (ws_broken / "src" / "counter.vhd").write_text(VHDL_BROKEN)
            (ws_broken / "tests" / "counter_tb.vhd").write_text(TESTBENCH)

            result_broken = validator.validate(str(ws_broken), "vhdl")
            assert not result_broken.passed, (
                f"GHDL should reject broken VHDL, but got: {result_broken.message}"
            )
            logger.info("GHDL rejects broken VHDL: %s", result_broken.message)

            # --- Test fixed VHDL ---
            ws_fixed = Path(tmp) / "fixed"
            (ws_fixed / "src").mkdir(parents=True)
            (ws_fixed / "tests").mkdir(parents=True)
            (ws_fixed / "build").mkdir(parents=True)
            (ws_fixed / "src" / "counter.vhd").write_text(VHDL_FIXED)
            (ws_fixed / "tests" / "counter_tb.vhd").write_text(TESTBENCH)

            result_fixed = validator.validate(str(ws_fixed), "vhdl")
            assert result_fixed.passed, (
                f"GHDL should accept fixed VHDL, but got: {result_fixed.message}"
            )
            logger.info("GHDL accepts fixed VHDL: %s", result_fixed.message)

            print(f"\nGHDL broken:  passed={result_broken.passed}, msg={result_broken.message}")
            print(f"GHDL fixed:   passed={result_fixed.passed}, msg={result_fixed.message}")

        finally:
            shutil.rmtree(tmp, ignore_errors=True)






if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    pytest.main([__file__, "-v", "--tb=short", "-s"])
