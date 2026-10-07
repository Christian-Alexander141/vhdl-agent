"""Board-, Top-Level- und Constraint-Vertrag-Validator.

Prueft vor Synthese und Flash, dass DesignState, FPGA-Registry,
Top-Level-VHDL, XDC/Constraints und Hardwaretest konsistent sind.
"""
import logging
import re
from pathlib import Path
from typing import Any

from src.domain.models import DesignState, DesignStage
from src.domain.exceptions import ConfigurationError

logger = logging.getLogger(__name__)


class ContractViolation(ConfigurationError):
    def __init__(self, field: str, message: str, details: dict | None = None):
        self.field = field
        self.message = message
        self.details = details or {}
        super().__init__(f"Contract violation [{field}]: {message}")


class BoardContract:
    """Prueft den Board-Vertrag: Board-ID, FPGA-Part, Programmer, Clock, Reset."""

    REQUIRED_FIELDS = [
        "board_name", "fpga_part", "programmer",
        "clock_hz", "clock_port", "reset_port",
    ]

    @classmethod
    def validate(cls, fpga_config: dict, design_state: DesignState) -> list[ContractViolation]:
        violations: list[ContractViolation] = []

        if not fpga_config:
            violations.append(ContractViolation(
                "fpga_config", "No FPGA configuration provided"
            ))
            return violations

        for field in cls.REQUIRED_FIELDS:
            if field not in fpga_config or not fpga_config[field]:
                violations.append(ContractViolation(
                    f"fpga_config.{field}",
                    f"Missing required field: {field}",
                    {"config_keys": list(fpga_config.keys())}
                ))

        # Clock-Prüfung
        clock_hz = fpga_config.get("clock_hz")
        if clock_hz is not None:
            try:
                clock_hz = int(clock_hz)
                if clock_hz <= 0:
                    violations.append(ContractViolation(
                        "fpga_config.clock_hz",
                        f"Clock frequency must be positive, got {clock_hz}"
                    ))
            except (TypeError, ValueError):
                violations.append(ContractViolation(
                    "fpga_config.clock_hz",
                    f"Clock frequency must be an integer, got {clock_hz}"
                ))

        # Top-Level-Entity-Prüfung
        top_entity = design_state.architecture.modules[0].name if design_state.architecture.modules else ""
        if not top_entity:
            violations.append(ContractViolation(
                "top_entity",
                "No top-level entity found in architecture"
            ))

        # Clock-Domain-Prüfung
        clock_domain = design_state.architecture.clock_domain
        if not clock_domain:
            violations.append(ContractViolation(
                "architecture.clock_domain",
                "Clock domain not specified in architecture"
            ))

        # Reset-Polaritaet-Prüfung
        reset_concept = design_state.architecture.reset_concept
        if not reset_concept:
            violations.append(ContractViolation(
                "architecture.reset_concept",
                "Reset concept not specified in architecture"
            ))

        return violations

    @classmethod
    def check(cls, fpga_config: dict, design_state: DesignState) -> bool:
        """Return True if contract passes, raise ConfigurationError on violation."""
        violations = cls.validate(fpga_config, design_state)
        if violations:
            msgs = "; ".join(v.message for v in violations)
            raise ConfigurationError(f"Board contract violations: {msgs}")
        return True


class TopLevelContract:
    """Prueft, dass das Top-Level-Entity eindeutig und korrekt definiert ist."""

    TB_PATTERNS = ["_tb", "testbench", "_test", "test_"]

    @classmethod
    def validate(cls, src_dir: Path, fpga_config: dict | None = None) -> list[ContractViolation]:
        violations: list[ContractViolation] = []

        if not src_dir.exists():
            violations.append(ContractViolation(
                "src_dir", f"Source directory does not exist: {src_dir}"
            ))
            return violations

        vhd_files = list(src_dir.glob("*.vhd")) + list(src_dir.glob("*.vhdl"))
        entities: dict[str, Path] = {}
        tb_files: list[Path] = []

        for f in vhd_files:
            content = f.read_text(errors="replace")
            entity_match = re.search(r"\bentity\s+(\w+)\s+is", content, re.IGNORECASE)
            if entity_match:
                entity_name = entity_match.group(1)
                filename = f.stem.lower()
                is_tb = any(p in filename for p in cls.TB_PATTERNS)
                if is_tb:
                    tb_files.append(f)
                elif entity_name in entities:
                    violations.append(ContractViolation(
                        "top_level_entity",
                        f"Ambiguous top-level entity '{entity_name}' found in multiple files",
                        {"files": [str(entities[entity_name]), str(f)]}
                    ))
                else:
                    entities[entity_name] = f

        if not entities:
            violations.append(ContractViolation(
                "top_level_entity",
                "No top-level entity found in source files"
            ))

        if len(entities) > 1 and not fpga_config:
            violations.append(ContractViolation(
                "top_level_entity",
                f"Multiple top-level entities found without explicit target: {list(entities.keys())}"
            ))

        for tb_file in tb_files:
            pass

        return violations

    @classmethod
    def check(cls, src_dir: Path, fpga_config: dict | None = None) -> bool:
        violations = cls.validate(src_dir, fpga_config)
        if violations:
            msgs = "; ".join(v.message for v in violations)
            raise ConfigurationError(f"Top-Level contract violations: {msgs}")
        return True


class ConstraintContract:
    """Prueft, dass XDC/Constraints korrekt und vollständig sind."""

    @classmethod
    def validate(cls, workspace: str, design_state: DesignState) -> list[ContractViolation]:
        violations: list[ContractViolation] = []
        ws_path = Path(workspace)
        constraints_dir = ws_path / "constraints"

        if not constraints_dir.exists():
            violations.append(ContractViolation(
                "constraints",
                f"Constraints directory not found: {constraints_dir}"
            ))
            return violations

        xdc_files = list(constraints_dir.glob("*.xdc"))
        if not xdc_files:
            violations.append(ContractViolation(
                "constraints",
                "No XDC constraint files found in constraints/"
            ))
            return violations

        # Prüfe, ob alle Ports in XDC gemappt sind
        all_ports = cls._extract_ports_from_vhdl(ws_path / "src")
        mapped_pins = cls._extract_pins_from_xdc(constraints_dir)

        for port_name in all_ports:
            if port_name not in mapped_pins and port_name.upper() not in mapped_pins:
                violations.append(ContractViolation(
                    "constraint_mapping",
                    f"Port '{port_name}' is not mapped in any XDC file",
                    {"port": port_name, "xdc_files": [str(f) for f in xdc_files]}
                ))

        return violations

    @classmethod
    def check(cls, workspace: str, design_state: DesignState) -> bool:
        violations = cls.validate(workspace, design_state)
        if violations:
            msgs = "; ".join(v.message for v in violations)
            raise ConfigurationError(f"Constraint contract violations: {msgs}")
        return True

    @staticmethod
    def _extract_ports_from_vhdl(src_dir: Path) -> set[str]:
        ports: set[str] = set()
        if not src_dir.exists():
            return ports
        for f in src_dir.glob("*.vhd"):
            content = f.read_text(errors="replace")
            for match in re.finditer(r"(\w+)\s*:\s*(?:in|out|inout)\s+\w+", content, re.IGNORECASE):
                ports.add(match.group(1))
        return ports

    @staticmethod
    def _extract_pins_from_xdc(constraints_dir: Path) -> set[str]:
        pins: set[str] = set()
        for f in constraints_dir.glob("*.xdc"):
            content = f.read_text(errors="replace")
            for match in re.finditer(r"PACKAGE_PIN\s+(\w+)", content):
                pins.add(match.group(1))
        return pins


class ContractValidator:
    """Zentraler Validator für alle Verträge."""

    @classmethod
    def validate_all(
        cls,
        workspace: str,
        design_state: DesignState,
        fpga_registry: dict | None = None,
        fpga_name: str = "arty_s7_50",
    ) -> list[ContractViolation]:
        """Prüft alle Verträge und gibt alle Verletzungen zurück."""
        violations: list[ContractViolation] = []

        fpga_config = fpga_registry.get(fpga_name) if fpga_registry else None

        violations.extend(BoardContract.validate(fpga_config or {}, design_state))
        violations.extend(TopLevelContract.validate(Path(workspace) / "src", fpga_config))
        violations.extend(ConstraintContract.validate(workspace, design_state))

        return violations

    @classmethod
    def check_all(
        cls,
        workspace: str,
        design_state: DesignState,
        fpga_registry: dict | None = None,
        fpga_name: str = "arty_s7_50",
    ) -> bool:
        """Prüft alle Verträge. Löst ConfigurationError bei Verletzungen aus."""
        violations = cls.validate_all(workspace, design_state, fpga_registry, fpga_name)
        if violations:
            msgs = "; ".join(v.message for v in violations)
            raise ConfigurationError(f"Contract validation failed: {msgs}")
        return True
