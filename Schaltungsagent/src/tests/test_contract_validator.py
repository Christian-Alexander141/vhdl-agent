"""Tests für Board-, Top-Level- und Constraint-Vertrag-Validierung."""
import sys
import os
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from pathlib import Path
from src.infrastructure.validation.contract_validator import (
    BoardContract,
    TopLevelContract,
    ConstraintContract,
    ContractValidator,
    ContractViolation,
)
from src.domain.models import DesignState, DesignStage, ArchitectureInfo, FPGAInfo, ModuleInfo


def make_design_state(fpga_name="arty_s7_50"):
    ds = DesignState()
    ds.project["id"] = "contract-test"
    ds.current_stage = DesignStage.SYNTHESIZING
    ds.architecture.clock_domain = "clk"
    ds.architecture.reset_concept = "async_active_high"
    ds.synthesis.fpga_part = fpga_name
    ds.architecture.modules.append(ModuleInfo(name="top", type="module"))
    return ds


def make_fpga_registry():
    return {
        "arty_s7_50": {
            "board_name": "Arty S7-50",
            "fpga_part": "XC7S50-1CSGA324C",
            "programmer": "vivado",
            "clock_hz": 100000000,
            "clock_port": "clk",
            "reset_port": "reset",
        }
    }


class TestBoardContract:
    """Testet den Board-Vertrag."""

    def test_valid_config_passes(self):
        fpga_config = make_fpga_registry()["arty_s7_50"]
        ds = make_design_state()
        assert BoardContract.check(fpga_config, ds) is True

    def test_missing_clock_hz_fails(self):
        fpga_config = make_fpga_registry()["arty_s7_50"].copy()
        del fpga_config["clock_hz"]
        ds = make_design_state()
        with pytest.raises(Exception):
            BoardContract.check(fpga_config, ds)

    def test_missing_fpga_part_fails(self):
        fpga_config = make_fpga_registry()["arty_s7_50"].copy()
        del fpga_config["fpga_part"]
        ds = make_design_state()
        with pytest.raises(Exception):
            BoardContract.check(fpga_config, ds)

    def test_invalid_clock_hz_fails(self):
        fpga_config = make_fpga_registry()["arty_s7_50"].copy()
        fpga_config["clock_hz"] = -1
        ds = make_design_state()
        with pytest.raises(Exception):
            BoardContract.check(fpga_config, ds)

    def test_missing_config_raises(self):
        ds = make_design_state()
        with pytest.raises(Exception):
            BoardContract.check({}, ds)

    def test_no_clock_domain_fails(self):
        fpga_config = make_fpga_registry()["arty_s7_50"]
        ds = make_design_state()
        ds.architecture.clock_domain = ""
        with pytest.raises(Exception):
            BoardContract.check(fpga_config, ds)

    def test_no_reset_concept_fails(self):
        fpga_config = make_fpga_registry()["arty_s7_50"]
        ds = make_design_state()
        ds.architecture.reset_concept = ""
        with pytest.raises(Exception):
            BoardContract.check(fpga_config, ds)


class TestTopLevelContract:
    """Testet die Top-Level-Entity-Validierung."""

    def test_single_top_entity_passes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir = Path(tmpdir) / "src"
            src_dir.mkdir()
            (src_dir / "top.vhd").write_text(
                "entity top is port (clk: in std_logic); end entity;"
            )
            assert TopLevelContract.validate(src_dir) == []

    def test_no_top_entity_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir = Path(tmpdir) / "src"
            src_dir.mkdir()
            # No VHDL files at all
            violations = TopLevelContract.validate(src_dir)
            assert len(violations) > 0

    def test_ambiguous_top_entity_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir = Path(tmpdir) / "src"
            src_dir.mkdir()
            (src_dir / "top1.vhd").write_text(
                "entity top is end entity;"
            )
            (src_dir / "top2.vhd").write_text(
                "entity top is end entity;"
            )
            violations = TopLevelContract.validate(src_dir)
            assert len(violations) > 0


class TestConstraintContract:
    """Testet die Constraint-Validierung."""

    def test_missing_constraints_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ds = make_design_state()
            with pytest.raises(Exception):
                ConstraintContract.check(tmpdir, ds)

    def test_missing_xdc_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            constraints_dir = Path(tmpdir) / "constraints"
            constraints_dir.mkdir()
            ds = make_design_state()
            with pytest.raises(Exception):
                ConstraintContract.check(tmpdir, ds)


class TestContractValidator:
    """Testet den zentralen ContractValidator."""

    def test_validate_all_with_valid_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir = Path(tmpdir) / "src"
            src_dir.mkdir()
            (src_dir / "top.vhd").write_text(
                "entity top is port (clk: in std_logic); end entity;"
            )
            constraints_dir = Path(tmpdir) / "constraints"
            constraints_dir.mkdir()
            (constraints_dir / "auto.xdc").write_text(
                'set_property -dict { PACKAGE_PIN R2 } [get_ports clk]'
            )
            ds = make_design_state()
            registry = make_fpga_registry()
            result = ContractValidator.validate_all(tmpdir, ds, registry, "arty_s7_50")
            assert isinstance(result, list)

    def test_validate_all_returns_violations(self):
        ds = make_design_state()
        violations = ContractValidator.validate_all(
            "/nonexistent", ds, {}, "arty_s7_50"
        )
        assert isinstance(violations, list)

    def test_check_all_raises_on_violation(self):
        ds = make_design_state()
        with pytest.raises(Exception):
            ContractValidator.check_all("/nonexistent", ds, {}, "arty_s7_50")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
