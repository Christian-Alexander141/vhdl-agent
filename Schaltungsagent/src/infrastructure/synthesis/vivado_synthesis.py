import logging
import shutil
import subprocess
import re
import os
from pathlib import Path
from typing import Optional

from src.domain.ports.bitstream_service import BitstreamResult, BitstreamService
from src.config import load_fpga_registry

logger = logging.getLogger(__name__)

VHDL_EXTENSIONS = (".vhd", ".vhdl")

# Patterns to exclude testbenches from top-level detection
TB_PATTERNS = ["_tb", "testbench", "_test", "test_"]


class VivadoBitstreamService(BitstreamService):
    """Vivado Bitstream-Erzeugung im Non-Project-Mode.

    Erzeugt ein Vivado Tcl-Skript, das die VHDL-Dateien einliest, synthetisiert,
    implementiert (opt/place/route) und den Bitstream schreibt.
    """

    def __init__(
        self,
        vivado_binary: str = "vivado",
        settings_script: str = "",
        timeout_seconds: int = 600,
        fpga_registry: dict | None = None,
    ):
        self._vivado_binary = vivado_binary
        self._settings_script = settings_script
        self._timeout_seconds = timeout_seconds
        self._fpga_registry = fpga_registry or load_fpga_registry()

    def toolchain_available(self) -> bool:
        if shutil.which(self._vivado_binary) is not None:
            return True
        if self._settings_script and Path(self._settings_script).is_file():
            return True
        return False

    def build_bitstream(
        self, workspace: str, target: str = "", domain: str = "vhdl", top_entity: str = ""
    ) -> BitstreamResult:
        logger.info("Vivado building bitstream for workspace: %s (target: %s)", workspace, target)
        ws_path = Path(workspace)
        src_dir = ws_path / "src"
        steps: list[dict] = []

        if not src_dir.exists():
            return self._fail(
                "No src directory found", steps,
                details={"workspace": str(ws_path)},
            )
        src_files = self._find_vhdl_files(src_dir)
        if not src_files:
            return self._fail(
                "No VHDL files found in src/", steps,
                details=self._attach_artifacts({}, src_dir),
            )

        # Top-Level Entity bestimmen:
        # 1. expliziter top_entity Parameter
        # 2. state.metadata["top_entity"]
        # 3. automatische Erkennung (nur eindeutig, keine Testbenches)
        entities = self._find_entities(src_files)
        if not entities:
            return self._fail(
                "No top-level entity found in src/", steps,
                details=self._attach_artifacts({}, src_dir),
            )

        # Top-Level auswählen
        selected_top = None
        if top_entity:
            # Explizites Top-Level angegeben
            for file_path, entity_name in entities:
                if entity_name == top_entity:
                    selected_top = (file_path, entity_name)
                    break
            if not selected_top:
                available = [e[1] for e in entities]
                return self._fail(
                    f"Specified top entity '{top_entity}' not found. Available: {available}",
                    steps,
                    details=self._attach_artifacts({}, src_dir),
                )
        else:
            # Automatische Erkennung: Nur wenn genau eine Entity (kein Testbench)
            non_tb_entities = [
                (f, e) for f, e in entities
                if not self._is_testbench(f)
            ]
            if len(non_tb_entities) == 1:
                selected_top = non_tb_entities[0]
            elif len(non_tb_entities) > 1:
                available = [e[1] for e in non_tb_entities]
                return self._fail(
                    f"Multiple top-level entities found. Please specify top_entity. Available: {available}",
                    steps,
                    details=self._attach_artifacts({}, src_dir),
                )
            else:
                # Nur Testbenches gefunden
                available = [e[1] for e in entities]
                return self._fail(
                    f"No suitable top-level entity found (only testbenches detected). Available: {available}",
                    steps,
                    details=self._attach_artifacts({}, src_dir),
                )

        top_file, top_name = selected_top

        # Ziel-FPGA bestimmen: target-Parameter > Registry-Default > arty_s7_50
        fpga_name = target or "arty_s7_50"
        fpga_config = self._fpga_registry.get(fpga_name)
        if not fpga_config:
            return self._fail(
                f"Unknown FPGA target: {fpga_name}. Available: {list(self._fpga_registry.keys())}",
                steps,
            )
        part = fpga_config.part
        clock_hz = fpga_config.clock_hz
        board_name = fpga_config.board_name

        # Board-Name für XDC-Auto-Generierung merken
        self._current_board_name = board_name

        build_dir = ws_path / "build" / "bitstream"
        build_dir.mkdir(parents=True, exist_ok=True)

        bitstream_file = build_dir / f"{top_name}.bit"

        # Vivado Tcl-Skript erzeugen
        tcl_script = self._generate_tcl_script(
            src_files=src_files,
            top_entity=top_name,
            part=part,
            bitstream_path=bitstream_file,
            clock_hz=clock_hz,
            workspace=ws_path,
        )
        tcl_file = build_dir / "build_bitstream.tcl"
        tcl_file.write_text(tcl_script)

        # Vivado im Batch-Mode ausführen
        # Logs und Journals in dedizierten Ordner umleiten
        log_dir = build_dir / "vivado_logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"{top_name}.log"
        jou_file = log_dir / f"{top_name}.jou"

        cmd = [
            self._vivado_binary,
            "-mode", "batch",
            "-log", str(log_file),
            "-journal", str(jou_file),
            "-source", str(tcl_file),
        ]
        step = self._run_step("vivado_bitstream", top_name, cmd, build_dir)
        steps.append(step)

        if step["returncode"] != 0:
            return self._fail(
                f"Vivado bitstream generation failed for {top_name}",
                steps,
                details=self._attach_artifacts(
                    {"file": str(top_file), "fpga_part": part, "error": step.get("stderr", "")},
                    src_dir,
                ),
            )

        # Bitstream-Datei prüfen
        if not bitstream_file.exists():
            step["returncode"] = -1
            step["stderr"] = f"Bitstream file not created: {bitstream_file}"
            return self._fail(
                f"Vivado did not produce bitstream file: {bitstream_file}",
                steps,
                details=self._attach_artifacts(
                    {"file": str(top_file), "fpga_part": part},
                    src_dir,
                ),
            )

        # Dateigröße prüfen
        file_size = bitstream_file.stat().st_size
        if file_size == 0:
            step["returncode"] = -1
            step["stderr"] = f"Bitstream file is empty: {bitstream_file}"
            return self._fail(
                f"Vivado produced empty bitstream file: {bitstream_file}",
                steps,
                details=self._attach_artifacts(
                    {"file": str(top_file), "fpga_part": part},
                    src_dir,
                ),
            )

        logger.info(
            "Vivado bitstream generation succeeded for %s (bitstream: %s, size: %d bytes)",
            top_name, bitstream_file, file_size,
        )
        return BitstreamResult(
            passed=True,
            message=(
                f"Bitstream generation succeeded for {top_name} "
                f"(bitstream: {bitstream_file.name}, FPGA: {part}, size: {file_size} bytes)"
            ),
            bitstream_path=str(bitstream_file),
            details={
                "steps": steps,
                "entity": top_name,
                "bitstream": str(bitstream_file),
                "fpga_part": part,
                "clock_hz": clock_hz,
                "bitstream_size": file_size,
                "artifact_dir": str(build_dir),
                "files_checked": [str(f) for f in src_files],
            },
        )

    def _generate_tcl_script(
        self,
        src_files: list[Path],
        top_entity: str,
        part: str,
        bitstream_path: Path,
        clock_hz: int,
        workspace: Path | None = None,
    ) -> str:
        """Erzeugt das Vivado Tcl-Skript im Non-Project-Mode."""
        # Relative Pfade für read_vhdl
        vhdl_reads = "\n".join(
            f'read_vhdl "{f.absolute()}"' for f in src_files
        )

        # XDC Constraints einlesen oder auto-generieren
        xdc_reads = ""
        xdc_generated = False
        if workspace:
            constraints_dir = workspace / "constraints"
            if constraints_dir.exists():
                xdc_files = sorted(constraints_dir.glob("*.xdc"))
                if xdc_files:
                    xdc_reads = "\n".join(
                        f'read_xdc "{f.absolute()}"' for f in xdc_files
                    )
                    xdc_reads = f"\n# Read XDC constraints\n{xdc_reads}\n"

            # Auto-generate XDC from board profile if no constraints found
            if not xdc_reads and workspace:
                # Board-Profil aus self._fpga_registry bestimmen
                # (wird über den Aufrufer via fpga_name gesetzt)
                board_name = getattr(self, "_current_board_name", "")
                generated_xdc = self._generatexdc_for_board(
                    top_entity, src_files, board_name, clock_hz,
                )
                if generated_xdc:
                    # XDC in Datei schreiben
                    xdc_path = constraints_dir / "auto_generated.xdc"
                    constraints_dir.mkdir(parents=True, exist_ok=True)
                    xdc_path.write_text(generated_xdc)
                    xdc_reads = f'\n# Auto-generated XDC constraints for {board_name}\nread_xdc "{xdc_path.absolute()}"\n'
                    xdc_generated = True
                    logger.info("Auto-generated XDC constraints for board %s: %s", board_name, xdc_path)

        return f"""# Vivado Non-Project Mode Bitstream Generation
# Auto-generated by VivadoBitstreamService

# Create in-memory project
create_project -in_memory -part {part}

# Read VHDL sources
{vhdl_reads}
{xdc_reads}
# Set top module
set_property top {top_entity} [current_fileset]

# Synthesis
synth_design -top {top_entity} -part {part}

# Implementation
opt_design
place_design
route_design

# Write bitstream
write_bitstream -force "{bitstream_path.absolute()}"

# Report utilization
report_utilization -file "{bitstream_path.parent}/utilization.rpt"
report_timing_summary -file "{bitstream_path.parent}/timing.rpt"

exit
"""

    def _find_vhdl_files(self, directory: Path) -> list[Path]:
        if not directory.exists():
            return []
        return sorted(
            p for p in directory.iterdir()
            if p.is_file() and p.suffix.lower() in VHDL_EXTENSIONS
        )

    def _find_entities(self, src_files: list[Path]) -> list[tuple[Path, str]]:
        """Findet alle Entities in den VHDL-Dateien."""
        entities = []
        for vhd_file in src_files:
            entity = self._extract_entity_name(vhd_file)
            if entity:
                entities.append((vhd_file, entity))
        return entities

    @staticmethod
    def _extract_entity_name(vhd_file: Path) -> str | None:
        try:
            content = vhd_file.read_text(errors="replace")
        except OSError:
            return None
        match = re.search(r"\bentity\s+(\w+)\s+is", content, re.IGNORECASE)
        return match.group(1) if match else None

    def _is_testbench(self, vhd_file: Path) -> bool:
        """Prüft ob eine VHDL-Datei eine Testbench ist."""
        filename = vhd_file.stem.lower()
        for pattern in TB_PATTERNS:
            if pattern in filename:
                return True
        # Prüfe ob die Datei in tests/ liegt
        if vhd_file.parent.name.lower() in ("tests", "test", "tb"):
            return True
        return False

    @staticmethod
    def _extract_entity_ports(vhd_file: Path) -> dict[str, dict]:
        """Extrahiert Port-Informationen aus einer VHDL-Entity.

        Gibt zurück: {port_name: {"direction": "in"|"out", "width": int, "range": str}}
        """
        try:
            content = vhd_file.read_text(errors="replace")
        except OSError:
            return {}

        ports: dict[str, dict] = {}
        # Find the Port section inside entity
        port_match = re.search(
            r"\bentity\s+\w+\s+is\s+port\s*\((.*?)\)\s*;",
            content,
            re.IGNORECASE | re.DOTALL,
        )
        if not port_match:
            return {}

        port_block = port_match.group(1)
        # Split on semicolons to get individual port declarations
        for decl in port_block.split(";"):
            decl = decl.strip()
            if not decl:
                continue
            # Match: name [range] : direction type
            m = re.match(
                r"(\w+)\s*(?:\(([^)]+)\)\s*)?:\s*(in|out|inout)\s+(\w+)",
                decl,
                re.IGNORECASE,
            )
            if m:
                port_name = m.group(1)
                port_range = m.group(2) or ""
                direction = m.group(3).lower()
                # Calculate width from range
                width = 1
                if port_range:
                    rm = re.match(r"(\d+)\s+downto\s+(\d+)", port_range)
                    if rm:
                        high = int(rm.group(1))
                        low = int(rm.group(2))
                        width = high - low + 1
                ports[port_name] = {
                    "direction": direction,
                    "width": width,
                    "range": port_range,
                }
        return ports

    def _generatexdc_for_board(
        self,
        top_entity: str,
        src_files: list[Path],
        board_name: str,
        clock_hz: int,
    ) -> str | None:
        """Generiert XDC-Constraints für ein bekanntes Board.

        Wenn kein passendes Board-Profil gefunden wird oder die Entity-Ports
        nicht sinnvoll zugeordnet werden können, wird None zurückgegeben
        (dann müssen manuelle XDC-Dateien verwendet werden).
        """
        # Nur für Xilinx-Boards relevant
        if board_name not in ("arty_s7", "arty_s7_50"):
            return None

        # Entity-Ports aus allen src-Dateien sammeln
        all_ports: dict[str, dict] = {}
        for f in src_files:
            all_ports.update(self._extract_entity_ports(f))

        if not all_ports:
            return None

        # Arty S7-50 Pin-Mapping
        clock_period_ns = round(1_000_000_000 / clock_hz, 3)

        # Known pin mappings for Arty S7-50
        arty_clk_pin = "E3"
        arty_leds = ["G6", "F6", "E6", "E5", "H4", "H3", "K1", "J1"]  # LD0..LD7
        arty_buttons = ["D9", "C9", "A8", "C11"]  # BTN0..BTN3

        xdc_lines = []
        mapped_ports = set()

        # Clock zuordnen
        for port_name in all_ports:
            if port_name.upper() in ("CLK", "CLK_100MHZ", "SYS_CLK", "CLOCK"):
                p = all_ports[port_name]
                if p["direction"] == "in" and p["width"] == 1:
                    xdc_lines.append(
                        f"set_property -dict {{ PACKAGE_PIN {arty_clk_pin} "
                        f"IOSTANDARD LVCMOS33 }} [get_ports {port_name}]"
                    )
                    xdc_lines.append(
                        f"create_clock -period {clock_period_ns:.3f} "
                        f"-name sys_clk_pin -waveform {{0.000 {clock_period_ns / 2:.3f}}} "
                        f"-add [get_ports {port_name}]"
                    )
                    mapped_ports.add(port_name)
                    break

        # Reset zuordnen (Button BTN0)
        for port_name in all_ports:
            if port_name.upper() in ("RESET", "RST", "RESET_N", "RST_N"):
                p = all_ports[port_name]
                if p["direction"] == "in" and p["width"] == 1:
                    xdc_lines.append(
                        f"set_property -dict {{ PACKAGE_PIN {arty_buttons[0]} "
                        f"IOSTANDARD LVCMOS33 }} [get_ports {port_name}]"
                    )
                    mapped_ports.add(port_name)
                    break

        # Enable zuordnen (Button BTN1)
        for port_name in all_ports:
            if port_name.upper() in ("ENABLE", "EN"):
                p = all_ports[port_name]
                if p["direction"] == "in" and p["width"] == 1:
                    xdc_lines.append(
                        f"set_property -dict {{ PACKAGE_PIN {arty_buttons[1]} "
                        f"IOSTANDARD LVCMOS33 }} [get_ports {port_name}]"
                    )
                    mapped_ports.add(port_name)
                    break

        # Load zuordnen (Button BTN2)
        for port_name in all_ports:
            if port_name.upper() in ("LOAD", "LD"):
                p = all_ports[port_name]
                if p["direction"] == "in" and p["width"] == 1:
                    xdc_lines.append(
                        f"set_property -dict {{ PACKAGE_PIN {arty_buttons[2]} "
                        f"IOSTANDARD LVCMOS33 }} [get_ports {port_name}]"
                    )
                    mapped_ports.add(port_name)
                    break

        # Output-Vektoren auf LEDs legen
        led_idx = 0
        for port_name in sorted(all_ports.keys()):
            if port_name in mapped_ports:
                continue
            p = all_ports[port_name]
            if p["direction"] == "out" and p["width"] > 0:
                if led_idx >= len(arty_leds):
                    break
                if p["width"] == 1:
                    # Single-bit output -> single LED
                    xdc_lines.append(
                        f"set_property -dict {{ PACKAGE_PIN {arty_leds[led_idx]} "
                        f"IOSTANDARD LVCMOS33 }} [get_ports {port_name}]"
                    )
                    led_idx += 1
                    mapped_ports.add(port_name)
                else:
                    # Vector output -> multiple LEDs
                    for bit in range(p["width"]):
                        if led_idx >= len(arty_leds):
                            break
                        pin = arty_leds[led_idx]
                        port_ref = f"{{{port_name}[{bit}]}}"
                        xdc_lines.append(
                            f"set_property -dict {{ PACKAGE_PIN {pin} "
                            f"IOSTANDARD LVCMOS33 }} [get_ports {port_ref}]"
                        )
                        led_idx += 1
                    mapped_ports.add(port_name)

        if not xdc_lines:
            return None

        return "\n".join(xdc_lines) + "\n"

    def _attach_artifacts(self, details: dict, src_dir: Path) -> dict:
        """Hängt den erzeugten VHDL-Code an die Details an, damit der
        Repair-Agent den fehlerhaften Code direkt vorliegen hat."""
        files = self._find_vhdl_files(src_dir)
        if not files:
            return details
        blocks = []
        for f in files:
            try:
                blocks.append(f"--- {f.name} ---\n{f.read_text(errors='replace')}")
            except OSError:
                continue
        if blocks:
            details["dut_content"] = "\n".join(blocks)
        return details

    def _run_step(
        self, step_name: str, label: str, cmd: list[str], cwd: Path
    ) -> dict:
        """Führt einen Vivado-Befehl aus.

        Wenn settings_script konfiguriert ist, wird die Umgebung davor geladen.
        Keine manuelle LD_LIBRARY_PATH-Konstruktion mehr - settings64.sh setzt alles.
        """
        effective_cmd = cmd

        # Wenn settings_script konfiguriert ist, Umgebung laden
        if self._settings_script and Path(self._settings_script).is_file():
            settings = Path(self._settings_script)
            # Vivado needs LD_LIBRARY_PATH for libncurses.so.5 etc.
            # Find the lib directory relative to settings script (settings is in Vivado/)
            vivado_dir = settings.parent
            lib_dir = vivado_dir / "lib" / "lnx64.o" / "Ubuntu" / "24"
            if lib_dir.exists():
                ld_path = str(lib_dir)
                existing = os.environ.get('LD_LIBRARY_PATH', '')
                if existing:
                    ld_path = f"{ld_path}:{existing}"
            else:
                ld_path = os.environ.get('LD_LIBRARY_PATH', '')
            vivado_cmd = " ".join(f'"{c}"' for c in cmd)
            wrapper = (
                f'source "{settings}" && '
                f'export LD_LIBRARY_PATH="{ld_path}" && '
                + vivado_cmd
            )
            effective_cmd = ["bash", "-c", wrapper]
            logger.info("Wrapping vivado command with settings64.sh: %s (LD_LIBRARY_PATH=%s)", settings, ld_path)

        logger.debug("Vivado %s (%s): %s", step_name, label, " ".join(effective_cmd))
        try:
            result = subprocess.run(
                effective_cmd,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=self._timeout_seconds,
            )
            return {
                "step": step_name,
                "label": label,
                "returncode": result.returncode,
                "stdout": result.stdout or "",
                "stderr": result.stderr or "",
            }
        except FileNotFoundError:
            return {
                "step": step_name,
                "label": label,
                "returncode": -1,
                "stdout": "",
                "stderr": f"Vivado binary '{self._vivado_binary}' not found",
            }
        except subprocess.TimeoutExpired:
            return {
                "step": step_name,
                "label": label,
                "returncode": -1,
                "stdout": "",
                "stderr": f"Vivado {step_name} timed out after {self._timeout_seconds}s",
            }

    def _fail(
        self,
        message: str,
        steps: list[dict],
        details: dict | None = None,
    ) -> BitstreamResult:
        result_details = {"steps": steps}
        if details:
            result_details.update(details)
        return BitstreamResult(passed=False, message=message, details=result_details)
