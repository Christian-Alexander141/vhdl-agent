"""Regressionstests für den GHDLValidator.

Voraussetzung: GHDL ist auf dem Host installiert (ghdl in PATH).
Die Tests beweisen, dass der Validator nicht nur `ghdl -a` ausführt,
sondern einen vollständigen Analyse-/Elaborations-/Simulationszyklus
mit Assertions-Auswertung durchführt.
"""

import shutil
import tempfile
from pathlib import Path

import pytest

from src.domain_plugins.vhdl.templates import VHDLTemplates
from src.infrastructure.validation.ghdl_validator import GHDLValidator

pytestmark = pytest.mark.skipif(
    shutil.which("ghdl") is None,
    reason="GHDL ist auf dem Host nicht installiert",
)

VALIDATOR = GHDLValidator()


def _make_workspace(dut_content: str, tb_content: str, dut_name: str = "hamming_decoder") -> str:
    tmp = tempfile.mkdtemp(prefix="vhdl_val_")
    src = Path(tmp) / "src"
    tests = Path(tmp) / "tests"
    src.mkdir()
    tests.mkdir()
    (src / f"{dut_name}.vhd").write_text(dut_content)
    (tests / f"{dut_name}_tb.vhd").write_text(tb_content)
    return tmp


def _hamming_dut() -> str:
    return VHDLTemplates.render("hamming", "decoder")


def _hamming_tb() -> str:
    return VHDLTemplates.render("hamming", "testbench")


def test_syntactisch_und_funktional_korrekter_dut_passt():
    ws = _make_workspace(_hamming_dut(), _hamming_tb())
    result = VALIDATOR.validate(ws)
    assert result.passed is True


def test_syntaktisch_falscher_dut_schlaegt_fehlt():
    bad_dut = _hamming_dut().replace("begin", "begen", 1)
    ws = _make_workspace(bad_dut, _hamming_tb())
    result = VALIDATOR.validate(ws)
    assert result.passed is False
    assert "analysis failed" in result.message.lower()
    steps = result.details.get("steps", [])
    assert any(s["returncode"] != 0 and s["step"] == "analyze" for s in steps)


def test_syntaktisch_korrekter_aber_funktional_falscher_dut_schlaegt_fehlt():
    # Fehlererkennung invertiert: syntaktisch gültig, funktional falsch.
    bad_dut = _hamming_dut().replace(
        'if syndrome /= "000" then', 'if syndrome = "000" then'
    )
    ws = _make_workspace(bad_dut, _hamming_tb())
    result = VALIDATOR.validate(ws)
    assert result.passed is False
    assert "simulation failed" in result.message.lower()
    assert "assertion" in result.message.lower()


def test_korrekter_dut_mit_fehlerhafter_testbench_schlaegt_fehlt():
    # Testbench erwartet im fehlerfreien Fall faelschlich ERROR_DETECT='1'.
    bad_tb = _hamming_tb().replace(
        "check_case(data_val, -1, expected_data, '0');",
        "check_case(data_val, -1, expected_data, '1');",
    )
    ws = _make_workspace(_hamming_dut(), bad_tb)
    result = VALIDATOR.validate(ws)
    assert result.passed is False


def test_testbench_ohne_assertions_gilt_nicht_als_pass():
    # Exit-Code 0 allein ist kein gültiger PASS.
    tb = """\
library IEEE;
use IEEE.STD_LOGIC_1164.ALL;

entity hamming_decoder_tb is
end hamming_decoder_tb;

architecture Behavioral of hamming_decoder_tb is
    signal CLK        : STD_LOGIC := '0';
    signal RESET      : STD_LOGIC := '0';
    signal DATA_IN    : STD_LOGIC_VECTOR(6 downto 0) := (others => '0');
    signal DATA_OUT   : STD_LOGIC_VECTOR(3 downto 0);
    signal ERROR_DETECT : STD_LOGIC;
    signal ERROR_CORRECT : STD_LOGIC;
begin
    uut: entity work.hamming_decoder
        port map (
            CLK => CLK, RESET => RESET, DATA_IN => DATA_IN,
            DATA_OUT => DATA_OUT,
            ERROR_DETECT => ERROR_DETECT,
            ERROR_CORRECT => ERROR_CORRECT
        );

    clk_process: process
    begin
        CLK <= '0';
        wait for 5 ns;
        CLK <= '1';
        wait for 5 ns;
    end process;

    stim_proc: process
    begin
        DATA_IN <= "0000000";
        wait for 200 ns;
        assert false report "TB_COMPLETE" severity note;
        wait;
    end process;
end Behavioral;
"""
    ws = _make_workspace(_hamming_dut(), tb)
    result = VALIDATOR.validate(ws)
    assert result.passed is False
    assert "no assertions" in result.message.lower()


def test_testbench_ohne_abschluss_marker_schlaegt_fehlt():
    # TB läuft nicht bis zum Ende (Marker fehlt) -> kein PASS.
    tb = _hamming_tb().replace(
        'assert false report "TB_COMPLETE" severity note;', ""
    )
    ws = _make_workspace(_hamming_dut(), tb)
    result = VALIDATOR.validate(ws)
    assert result.passed is False
    assert "did not complete" in result.message.lower()


def test_keine_testbench_vorhanden_schlaegt_fehlt():
    tmp = tempfile.mkdtemp(prefix="vhdl_val_")
    src = Path(tmp) / "src"
    src.mkdir()
    (src / "hamming_decoder.vhd").write_text(_hamming_dut())
    result = VALIDATOR.validate(tmp)
    assert result.passed is False
    assert "testbench" in result.message.lower()


def test_repair_instruction_enthaelt_detaillierte_informationen():
    bad_dut = _hamming_dut().replace(
        'if syndrome /= "000" then', 'if syndrome = "000" then'
    )
    ws = _make_workspace(bad_dut, _hamming_tb())
    result = VALIDATOR.validate(ws)
    instruction = result.build_repair_instruction(
        original_request="Hamming-Decoder bauen", iteration=3
    )
    assert "Ursprüngliche Anforderung: Hamming-Decoder bauen" in instruction
    assert "Reparatur-Iteration: 3" in instruction
    assert "Testbench: hamming_decoder_tb" in instruction
    assert "SIMULATE" in instruction
    assert "Verändere die Testbench NICHT" in instruction


def test_failed_case_wird_aus_simulationsausgabe_extrahiert():
    # Funktional falscher DUT: Fehlererkennung invertiert. Das erste
    # fehlschlagende Assertion ist der Clean Case (data=0, bit=-1), bei dem
    # der DUT faelschlich ERROR_DETECT='1' meldet.
    bad_dut = _hamming_dut().replace(
        'if syndrome /= "000" then', 'if syndrome = "000" then'
    )
    ws = _make_workspace(bad_dut, _hamming_tb())
    result = VALIDATOR.validate(ws)
    assert result.passed is False
    failed_case = result.details.get("failed_case", {})
    assert failed_case, "failed_case muss aus der Simulationsausgabe extrahiert werden"
    assert failed_case["testbench"] == "hamming_decoder_tb"
    assert failed_case["test_case"] == "Fehlerfreies Codewort"
    assert failed_case["data"] == 0
    assert failed_case["bit"] == -1
    assert failed_case["input_codeword"] == "0000000"
    assert failed_case["expected_error_detect"] == "'0'"
    assert failed_case["actual_error_detect"] == "'1'"


def test_repair_instruction_enthaelt_generierten_code_und_testbench():
    bad_dut = _hamming_dut().replace(
        'if syndrome /= "000" then', 'if syndrome = "000" then'
    )
    ws = _make_workspace(bad_dut, _hamming_tb())
    result = VALIDATOR.validate(ws)
    instruction = result.build_repair_instruction(
        original_request="Hamming-Decoder bauen", iteration=1
    )
    assert "Betroffene Datei:" in instruction
    assert "Erzeugter VHDL-Code (DUT):" in instruction
    assert "Erzeugte Testbench:" in instruction
    assert "entity hamming_decoder is" in instruction
    assert "entity hamming_decoder_tb is" in instruction
    assert "Fehlgeschlagener Testfall:" in instruction
    assert "Verfälschtes Bit: -1" in instruction
    assert "Erwarteter ERROR_DETECT: '0'" in instruction
    assert "Tatsächlicher ERROR_DETECT: '1'" in instruction