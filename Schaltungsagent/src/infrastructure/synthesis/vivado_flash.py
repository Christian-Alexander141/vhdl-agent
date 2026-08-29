import logging
import shutil
import subprocess
import tempfile
import os
from pathlib import Path
from typing import Optional

from src.domain.ports.flash_service import FlashResult, FlashService

logger = logging.getLogger(__name__)


class VivadoFlashService(FlashService):
    """Flash-Service mittels Vivado Hardware Manager (JTAG).

    Verwendet Vivado im Batch-Modus, um über den Hardware Manager
    den Bitstream via JTAG auf das FPGA zu programmieren.

    Kein openFPGALoader benötigt — Vivado stellt den kompletten
    Programmierworkflow selbst bereit.
    """

    def __init__(
        self,
        vivado_binary: str = "vivado",
        settings_script: str = "",
        timeout_seconds: int = 120,
    ):
        self._vivado_binary = vivado_binary
        self._settings_script = settings_script
        self._timeout_seconds = timeout_seconds

    def toolchain_available(self) -> bool:
        if shutil.which(self._vivado_binary) is not None:
            return True
        if self._settings_script and Path(self._settings_script).is_file():
            return True
        return False

    def detect_boards(self, expected_part: str = "") -> list[dict]:
        """Erkennt angeschlossene Boards via Vivado Hardware Manager.

        Wenn expected_part angegeben ist, wird nur das Gerät zurückgegeben,
        dessen Part-Name übereinstimmt (exakt oder als Präfix).
        """
        tcl_script = self._generate_detect_script(expected_part)
        result = self._run_vivado(tcl_script)
        if result["returncode"] != 0:
            logger.error("Vivado hw detect failed: %s", result.get("stderr", ""))
            return []

        boards = []
        for line in (result.get("stdout", "")).splitlines():
            line = line.strip()
            if line.startswith("BOARD:"):
                parts = line.split(":", 3)
                if len(parts) >= 4:
                    name = parts[1]
                    part = parts[2]
                    device = parts[3]
                    if expected_part and expected_part not in part:
                        continue
                    boards.append({
                        "index": len(boards),
                        "name": name,
                        "part": part,
                        "device": device,
                        "details": f"{part} ({device})",
                    })
        return boards

    def flash(self, bitstream_path: str, board: str = "", expected_part: str = "") -> FlashResult:
        """Programmiert den Bitstream auf das FPGA via Vivado JTAG.

        Args:
            bitstream_path: Pfad zur .bit-Datei
            board: Board-Name (optional, wird ignoriert, Auswahl über expected_part)
            expected_part: Erwarteter FPGA-Part-Name (z.B. "xc7s50csga324-1" oder "xc7s50")

        Returns:
            FlashResult mit Erfolgsstatus, Board-Informationen und Details.
        """
        bitstream_file = Path(bitstream_path)
        if not bitstream_file.exists():
            return FlashResult(
                passed=False,
                message=f"Bitstream file not found: {bitstream_path}",
                details={"bitstream_path": bitstream_path, "expected_part": expected_part},
                board_detected=False,
                board_count=0,
            )

        # Board-Erkennung mit erwartetem Part
        boards = self.detect_boards(expected_part)
        board_count = len(boards)

        if board_count == 0:
            all_boards = self.detect_boards("")  # Alle Geräte für Fehlermeldung
            return FlashResult(
                passed=False,
                message=(
                    f"Kein passendes FPGA-Board via JTAG erkannt. "
                    f"Erwartet: {expected_part or 'beliebig'}. "
                    f"Erkannte Geräte: {len(all_boards)}"
                ),
                details={
                    "bitstream_path": bitstream_path,
                    "expected_part": expected_part,
                    "error": "no_matching_board_detected",
                    "detected_devices": all_boards,
                },
                board_detected=False,
                board_count=0,
            )

        if board_count > 1:
            board_names = ", ".join(f"{b['part']} ({b['device']})" for b in boards)
            return FlashResult(
                passed=False,
                message=(
                    f"Mehrere passende FPGA-Geräte erkannt ({board_count}): {board_names}. "
                    f"Bitte nur ein passendes Board anschließen."
                ),
                details={
                    "bitstream_path": bitstream_path,
                    "expected_part": expected_part,
                    "error": "multiple_matching_boards_detected",
                    "detected_devices": boards,
                },
                board_detected=True,
                board_count=board_count,
            )

        # Genau ein passendes Gerät -> programmieren
        selected_device = boards[0]["device"]
        selected_part = boards[0]["part"]
        logger.info("Flashing bitstream %s to device %s (part: %s)", bitstream_path, selected_device, selected_part)

        tcl_script = self._generate_program_script(str(bitstream_file.absolute()), selected_device)
        result = self._run_vivado(tcl_script)

        if result["returncode"] != 0:
            error_msg = result.get("stderr", "") or result.get("stdout", "")
            return FlashResult(
                passed=False,
                message=f"Vivado JTAG programming failed: {error_msg[:500]}",
                details={
                    "bitstream_path": bitstream_path,
                    "expected_part": expected_part,
                    "selected_device": selected_device,
                    "selected_part": selected_part,
                    "returncode": result["returncode"],
                    "stdout": result.get("stdout", ""),
                    "stderr": result.get("stderr", ""),
                    "detected_devices": boards,
                },
                board_detected=True,
                board_count=board_count,
            )

        # Erfolg prüfen
        stdout = result.get("stdout", "")
        if "Programming completed successfully" in stdout:
            logger.info("Vivado JTAG programming successful for %s", bitstream_path)
            return FlashResult(
                passed=True,
                message=f"Bitstream erfolgreich via Vivado JTAG auf {selected_part} ({selected_device}) programmiert",
                details={
                    "bitstream_path": bitstream_path,
                    "expected_part": expected_part,
                    "selected_device": selected_device,
                    "selected_part": selected_part,
                    "stdout": stdout,
                    "detected_devices": boards,
                },
                board_detected=True,
                board_count=board_count,
            )

        return FlashResult(
            passed=False,
            message="Vivado JTAG programming completed but success not confirmed",
            details={
                "bitstream_path": bitstream_path,
                "expected_part": expected_part,
                "selected_device": selected_device,
                "selected_part": selected_part,
                "stdout": stdout,
                "stderr": result.get("stderr", ""),
                "detected_devices": boards,
            },
            board_detected=True,
            board_count=board_count,
        )

    def _generate_detect_script(self, expected_part: str = "") -> str:
        filter_clause = ""
        if expected_part:
            filter_clause = f"""
# Filter nach erwartetem Part
set expected_part "{expected_part}"
"""
        return f"""# Auto-generated: detect FPGA boards via JTAG
open_hw_manager
connect_hw_server -allow_non_jtag
open_hw_target

set hw_devices [get_hw_devices]
foreach device $hw_devices {{
    set part [get_property PART $device]
    puts "BOARD:$part:$device"
}}

close_hw_target
disconnect_hw_server
exit
"""

    def _generate_program_script(self, bitstream_path: str, device: str) -> str:
        return f"""# Auto-generated: program FPGA via Vivado JTAG
open_hw_manager
connect_hw_server -allow_non_jtag
open_hw_target

set hw_devices [get_hw_devices]
if {{[llength $hw_devices] == 0}} {{
    puts "ERROR: No hardware devices found"
    close_hw_manager
    disconnect_hw_server
    exit 1
}}

set target_device "{device}"
if {{![lsearch -exact $hw_devices $target_device] >= 0}} {{
    puts "ERROR: Target device $target_device not found in detected devices"
    puts "Available: $hw_devices"
    close_hw_manager
    disconnect_hw_server
    exit 1
}}

puts "Programming device: $target_device"
set_property PROGRAM.FILE "{bitstream_path}" $target_device
program_hw_devices $target_device
puts "Programming completed successfully!"

close_hw_target
disconnect_hw_server
exit
"""

    def _run_vivado(self, tcl_script: str) -> dict:
        """Führt ein Tcl-Skript im Vivado Batch-Modus aus.

        Das Skript wird in eine temporäre Datei geschrieben und mit
        `vivado -mode batch -source <file>` ausgeführt.
        Falls settings_script konfiguriert ist, wird die Umgebung davor geladen.
        """
        # Tcl-Skript in temporäre Datei schreiben
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".tcl", delete=False, prefix="vivado_flash_"
        ) as f:
            f.write(tcl_script)
            tcl_file = f.name

        try:
            effective_cmd = None

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
                wrapper = (
                    f'source "{settings}" && '
                    f'export LD_LIBRARY_PATH="{ld_path}" && '
                    f'{self._vivado_binary} -mode batch -source "{tcl_file}"'
                )
                effective_cmd = ["bash", "-c", wrapper]
                logger.debug("Wrapping vivado command with settings64.sh: %s (LD_LIBRARY_PATH=%s)", settings, ld_path)
            elif shutil.which(self._vivado_binary) is not None:
                effective_cmd = [
                    self._vivado_binary,
                    "-mode", "batch",
                    "-source", tcl_file,
                ]
            else:
                return {
                    "returncode": -1,
                    "stdout": "",
                    "stderr": f"Vivado binary not found: {self._vivado_binary}",
                }

            logger.debug("Vivado flash command: %s", " ".join(effective_cmd))
            result = subprocess.run(
                effective_cmd,
                capture_output=True,
                text=True,
                timeout=self._timeout_seconds,
            )
            return {
                "returncode": result.returncode,
                "stdout": result.stdout or "",
                "stderr": result.stderr or "",
            }
        except FileNotFoundError:
            return {
                "returncode": -1,
                "stdout": "",
                "stderr": f"Vivado binary '{self._vivado_binary}' not found",
            }
        except subprocess.TimeoutExpired:
            return {
                "returncode": -1,
                "stdout": "",
                "stderr": f"Vivado timed out after {self._timeout_seconds}s",
            }
        finally:
            # Temporäre Datei aufräumen
            try:
                Path(tcl_file).unlink(missing_ok=True)
            except Exception:
                pass