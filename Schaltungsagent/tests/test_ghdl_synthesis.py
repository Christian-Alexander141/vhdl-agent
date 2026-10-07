"""Regressionstests für die Stufe-1-Synthese (GHDL) und die FPGA-Registry.

Voraussetzung: GHDL ist auf dem Host installiert (ghdl in PATH).
Die Tests beweisen, dass der Synthese-Dienst `ghdl synth` ausführt,
Netlist-Artefakte erzeugt und nicht-synthesierbaren Code erkennt.
"""

import shutil
import tempfile
from pathlib import Path

import pytest

from src.config import load_config, load_fpga_registry
from src.domain_plugins.vhdl.templates import VHDLTemplates
from src.infrastructure.synthesis.ghdl_synthesis import GHDLSynthesisService

pytestmark = pytest.mark.skipif(
    shutil.which("ghdl") is None,
    reason="GHDL ist auf dem Host nicht installiert",
)

SYNTH = GHDLSynthesisService()

# Nicht-synthesierbar: wait for im Prozess (ghdl synth: "expect wait condition").
UNSYNTHESIZABLE_DUT = """\
library IEEE;
use IEEE.STD_LOGIC_1164.ALL;

entity blinker is
    Port ( CLK : in STD_LOGIC; Q : out STD_LOGIC);
end blinker;

architecture Behavioral of blinker is
    signal s_q : STD_LOGIC := '0';
begin
    process
    begin
        wait for 10 ns;
        s_q <= not s_q;
    end process;
    Q <= s_q;
end Behavioral;
"""


def _make_workspace(dut_content: str, dut_name: str = "hamming_decoder") -> str:
    tmp = tempfile.mkdtemp(prefix="vhdl_synth_")
    src = Path(tmp) / "src"
    src.mkdir()
    (src / f"{dut_name}.vhd").write_text(dut_content)
    return tmp


def test_synthesierbarer_dut_erzeugt_netlist():
    ws = _make_workspace(VHDLTemplates.render("hamming", "decoder"))
    result = SYNTH.synthesize(ws, target="gatemate_a2")
    assert result.passed is True
    assert result.target == "gatemate_a2"
    assert "synthesis succeeded" in result.message.lower()
    assert result.details["entity"] == "hamming_decoder"
    netlist = Path(result.details["netlist"])
    assert netlist.exists()
    assert "module hamming_decoder" in netlist.read_text()
    steps = result.details.get("steps", [])
    assert any(
        s["step"] == "synthesize" and s["returncode"] == 0 for s in steps
    )


def test_nicht_synthesierbarer_dut_schlaegt_fehlt():
    ws = _make_workspace(UNSYNTHESIZABLE_DUT, dut_name="blinker")
    result = SYNTH.synthesize(ws)
    assert result.passed is False
    assert "synthesis failed" in result.message.lower()
    steps = result.details.get("steps", [])
    assert any(s["step"] == "synthesize" and s["returncode"] != 0 for s in steps)
    assert "entity blinker is" in result.details.get("dut_content", "")


def test_repair_instruction_enthaelt_synthese_details():
    ws = _make_workspace(UNSYNTHESIZABLE_DUT, dut_name="blinker")
    result = SYNTH.synthesize(ws)
    instruction = result.build_repair_instruction(
        original_request="Blinker bauen", iteration=2
    )
    assert "Ursprüngliche Anforderung: Blinker bauen" in instruction
    assert "Reparatur-Iteration: 2" in instruction
    assert "SYNTHESIZE" in instruction
    assert "Erzeugter VHDL-Code (DUT):" in instruction
    assert "sowohl simulations- als auch synthesetauglich" in instruction
    assert "Verändere die Schnittstelle" in instruction


def test_toolchain_verfuegbarkeit():
    assert SYNTH.toolchain_available() is True


def test_fpga_registry_enthaelt_ziel_fpgas():
    registry = load_fpga_registry()
    assert "gatemate_a1" in registry
    assert "arty_s7_50" in registry
    assert registry["gatemate_a1"].part == "CCGM1A1"
    assert registry["gatemate_a1"].toolchain == "oss-cad-suite"
    assert registry["gatemate_a1"].wiki == "fpga_gatemate"
    assert registry["gatemate_a1"].programmer == "openfpgaloader"
    assert registry["arty_s7_50"].part == "xc7s50csga324-1"
    assert registry["arty_s7_50"].toolchain == "vivado"
    assert registry["arty_s7_50"].wiki == "fpga_xilinx_7series"
    assert registry["arty_s7_50"].programmer == "vivado"
    assert registry["gatemate_a1"].clock_hz == 100_000_000
    assert registry["arty_s7_50"].clock_hz == 100_000_000


def test_synthesis_config_default_fpga():
    settings = load_config()
    assert settings.synthesis.enabled is True
    assert settings.synthesis.default_fpga == "arty_s7_50"
    assert settings.synthesis.timeout_seconds == 120