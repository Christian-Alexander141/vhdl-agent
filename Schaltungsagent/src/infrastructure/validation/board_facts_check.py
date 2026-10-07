"""Board facts validation for generated XDC constraints."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


@dataclass
class Finding:
    rule: str
    line: int
    text: str
    severity: str = "warning"


def load_board_facts(board_id: str) -> dict[str, Any]:
    """Load board facts from knowledge directory."""
    knowledge_dir = Path(__file__).resolve().parents[2] / "knowledge" / "boards"
    board_file = knowledge_dir / f"{board_id}.yaml"
    if not board_file.is_file():
        logger.warning("Board facts not found for %s", board_id)
        return {}
    with open(board_file, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def check(xdc_text: str, board: dict[str, Any]) -> list[Finding]:
    """Check XDC content against board facts. Returns list of findings (warnings)."""
    findings: list[Finding] = []
    lines = xdc_text.splitlines()

    # Rule 1: Clock on R2 with IOSTANDARD != SSTL135
    findings.extend(_check_ddr3_clock(lines, board))

    # Rule 2: Missing create_clock for clock ports
    findings.extend(_check_missing_create_clock(lines, board))

    # Rule 3: Duplicate pin assignments
    findings.extend(_check_duplicate_pins(lines))

    # Rule 4: Output on non-LED pin when port looks like LED
    findings.extend(_check_output_on_non_led(lines, board))

    # Rule 5: NSTD-1 or UCIO-1 downgraded via set_property SEVERITY
    findings.extend(_check_downgraded_drc(lines))

    return findings


def _check_ddr3_clock(lines: list[str], board: dict[str, Any]) -> list[Finding]:
    """Rule 1: Detect R2 used with non-SSTL135 IOSTANDARD."""
    findings: list[Finding] = []
    # Pattern: set_property PACKAGE_PIN R2 ... IOSTANDARD <something>
    for i, line in enumerate(lines, 1):
        if "R2" in line and "PACKAGE_PIN" in line and "IOSTANDARD" in line:
            # Check if IOSTANDARD is not SSTL135
            if "SSTL135" not in line:
                m = re.search(r"IOSTANDARD\s+(\w+)", line)
                std = m.group(1) if m else "unknown"
                findings.append(Finding(
                    rule="DDR3_CLOCK_WRONG_IOSTANDARD",
                    line=i,
                    text=f"Pin R2 has IOSTANDARD {std}; board fact says R2 is DDR3 clock (SSTL135). "
                         "Using R2 as general user clock requires MMCM/Clocking Wizard.",
                ))
    return findings


def _check_missing_create_clock(lines: list[str], board: dict[str, Any]) -> list[Finding]:
    """Rule 2: Check for create_clock on clock ports."""
    findings: list[Finding] = []
    clock_ports = set()
    # Find clock ports from set_property PACKAGE_PIN ... on clock-like ports
    clock_patterns = ["CLK", "CLK_100MHZ", "SYS_CLK", "CLOCK"]
    for i, line in enumerate(lines, 1):
        for pat in clock_patterns:
            if re.search(rf"get_ports\s+.*\b{pat}\b", line, re.IGNORECASE):
                clock_ports.add(pat.lower())
    # Check if create_clock exists for each
    for port in clock_ports:
        has_create = any(f"create_clock" in l and port in l.lower() for l in lines)
        if not has_create:
            findings.append(Finding(
                rule="MISSING_CREATE_CLOCK",
                line=0,
                text=f"Clock port matching '{port}' has no create_clock constraint.",
            ))
    return findings


def _check_duplicate_pins(lines: list[str]) -> list[Finding]:
    """Rule 3: Detect duplicate PACKAGE_PIN assignments."""
    findings: list[Finding] = []
    pin_map: dict[str, list[int]] = {}
    for i, line in enumerate(lines, 1):
        m = re.search(r"PACKAGE_PIN\s+(\w+)", line)
        if m:
            pin = m.group(1)
            pin_map.setdefault(pin, []).append(i)
    for pin, line_nos in pin_map.items():
        if len(line_nos) > 1:
            findings.append(Finding(
                rule="DUPLICATE_PIN_ASSIGNMENT",
                line=line_nos[0],
                text=f"Pin {pin} assigned multiple times (lines: {line_nos}).",
            ))
    return findings


def _check_output_on_non_led(lines: list[str], board: dict[str, Any]) -> list[Finding]:
    """Rule 4: Output on non-LED pin when port name suggests LED."""
    findings: list[Finding] = []
    led_pins = {led["pin"] for led in board.get("leds", [])}
    pmod_pins = set()
    for pmod in board.get("pmods", []):
        pmod_pins.update(pmod.get("pins", []))
    non_led_output_pins = pmod_pins  # Pmod pins are not LEDs

    for i, line in enumerate(lines, 1):
        # Match: set_property PACKAGE_PIN <pin> ... [get_ports <port>]
        m = re.search(r"PACKAGE_PIN\s+(\w+).*get_ports\s+\{?([^}\s]+)", line)
        if m:
            pin = m.group(1)
            port = m.group(2).strip("{}")
            if pin in non_led_output_pins and re.search(r"led|LED", port, re.IGNORECASE):
                findings.append(Finding(
                    rule="OUTPUT_ON_NON_LED_PIN",
                    line=i,
                    text=f"Port '{port}' mapped to pin {pin} (Pmod), but port name suggests LED. "
                         "User LEDs are only: E18, F13, E13, H15.",
                ))
    return findings


def _check_downgraded_drc(lines: list[str]) -> list[Finding]:
    """Rule 5: Detect NSTD-1 or UCIO-1 severity downgrade workaround."""
    findings: list[Finding] = []
    for i, line in enumerate(lines, 1):
        if "SEVERITY" in line and ("NSTD-1" in line or "UCIO-1" in line):
            findings.append(Finding(
                rule="DRC_SEVERITY_DOWNGRADE",
                line=i,
                text="NSTD-1 or UCIO-1 severity downgraded. This is a workaround; "
                     "proper constraints (IOSTANDARD, PACKAGE_PIN) should be used instead.",
            ))
    return findings


def write_findings_report(findings: list[Finding], workspace: str) -> None:
    """Write findings to reports/board_facts.md."""
    if not findings:
        return
    ws = Path(workspace)
    report_dir = ws / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "board_facts.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# Board Facts Validation Report\n\n")
        for finding in findings:
            f.write(f"- **{finding.rule}** (line {finding.line}): {finding.text}\n")
    logger.info("Board facts report written to %s", report_path)