import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from src.domain.ports.flash_service import FlashResult, FlashService

logger = logging.getLogger(__name__)


class OpenFPGALoaderFlashService(FlashService):
    """Flash-Service mittels openFPGALoader.

    WICHTIG: Wenn opencode.use_docker=True ist, darf dieser Service NICHT
    im opencode-agent-Container laufen, sondern muss im Host-Prozess des
    API-Servers ausgeführt werden (dort, wo subprocess bereits für GHDL/Vivado
    läuft), da USB/JTAG-Passthrough in den Code-Agent-Container zusätzliche
    Angriffsfläche und Komplexität ohne Nutzen wäre.

    Der Host benötigt udev-Regeln für den Zugriff auf das Arty-S7 JTAG/UART
    Interface ohne root, z. B.:
    - /etc/udev/rules.d/99-digilent-arty.rules:
      SUBSYSTEM=="usb", ATTR{idVendor}=="0403", ATTR{idProduct}=="6010", MODE="0666", GROUP="plugdev"
      SUBSYSTEM=="usb", ATTR{idVendor}=="0403", ATTR{idProduct}=="6014", MODE="0666", GROUP="plugdev"
    (Vendor/Product IDs für Digilent Arty S7 FTDI JTAG/UART)
    Dann: `sudo udevadm control --reload-rules && sudo udevadm trigger`
    Nutzer muss in Gruppe 'plugdev' sein (oder 'dialout' je nach Distro).
    """

    def __init__(
        self,
        binary: str = "openFPGALoader",
        timeout_seconds: int = 60,
        default_board: str = "arty_s7_50",
        cable: str = "digilent",
    ):
        self._binary = binary
        self._timeout_seconds = timeout_seconds
        self._default_board = default_board
        self._cable = cable

    def toolchain_available(self) -> bool:
        return shutil.which(self._binary) is not None

    def detect_boards(self, expected_part: str = "") -> list[dict]:
        """Erkennt angeschlossene Boards via openFPGALoader --detect."""
        cmd = [self._binary, "-c", self._cable, "--detect"]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
            )
            output = "\n".join(
                part for part in (result.stdout or "", result.stderr or "") if part
            )
            self._last_detect_output = output[-2000:]
            if result.returncode != 0:
                logger.warning(
                    "openFPGALoader --detect returned %d: %s",
                    result.returncode,
                    output[-1000:],
                )
            boards = []
            current = None
            # openFPGALoader verwendet je nach Version entweder
            # "0: Arty S7 (...)" oder "index 0:" mit model/idcode-Feldern.
            for raw_line in output.splitlines():
                line = raw_line.strip()
                legacy = re.match(r"^(\d+):\s*(.+)$", line)
                indexed = re.match(r"^index\s+(\d+):$", line, re.IGNORECASE)
                if legacy:
                    board_info = legacy.group(2).strip()
                    name = board_info.split("(")[0].strip()
                    boards.append({
                        "index": int(legacy.group(1)),
                        "name": name,
                        "details": board_info,
                        "part": name,
                    })
                elif indexed:
                    if current:
                        boards.append(current)
                    current = {
                        "index": int(indexed.group(1)),
                        "name": "FPGA",
                        "details": "",
                        "part": "",
                    }
                elif current and line:
                    field = re.match(r"^(model|family|idcode|manufacturer)\s+(.+)$", line)
                    if field:
                        key, value = field.groups()
                        current[key] = value.strip()
                        if key == "model":
                            current["name"] = value.strip()
                            current["part"] = value.strip()
                    current["details"] = (current["details"] + " " + line).strip()
            if current:
                boards.append(current)
            return boards
        except FileNotFoundError:
            logger.error("openFPGALoader binary not found: %s", self._binary)
            return []
        except subprocess.TimeoutExpired:
            logger.error("openFPGALoader --detect timed out")
            return []
        except Exception as e:
            logger.error("openFPGALoader --detect failed: %s", e)
            return []

    def flash(self, bitstream_path: str, board: str = "", expected_part: str = "", workspace: str = "") -> FlashResult:
        """Flasht den Bitstream auf das angegebene Board.

        Args:
            bitstream_path: Pfad zur .bit-Datei
            board: Board-Name für openFPGALoader -b Option (Default: arty_s7)
            expected_part: Wird ignoriert (openFPGALoader verwendet board-Name)
            workspace: Wird ignoriert (openFPGALoader erzeugt keine Vivado-Artefakte)

        Returns:
            FlashResult mit Erfolgsstatus und Board-Informationen.
        """
        target_board = board or self._default_board
        bitstream_file = Path(bitstream_path)

        if not bitstream_file.exists():
            return FlashResult(
                passed=False,
                message=f"Bitstream file not found: {bitstream_path}",
                details={"bitstream_path": bitstream_path, "expected_part": expected_part, "board": target_board},
                board_detected=False,
                board_count=0,
            )

        # Vor dem Flashen Boards erkennen
        boards = self.detect_boards()
        board_count = len(boards)

        if board_count == 0:
            return FlashResult(
                passed=False,
                message="Kein FPGA-Board erkannt. Bitte Board anschließen und prüfen (openFPGALoader --detect).",
                details={
                    "bitstream_path": bitstream_path,
                    "target_board": target_board,
                    "expected_part": expected_part,
                    "error": "no_board_detected",
                    "detect_output": getattr(self, "_last_detect_output", ""),
                },
                board_detected=False,
                board_count=0,
            )

        if board_count > 1:
            board_names = ", ".join(b.get("name", "unknown") for b in boards)
            return FlashResult(
                passed=False,
                message=(
                    f"Mehrere FPGA-Boards erkannt ({board_count}): {board_names}. "
                    f"Bitte nur ein Board anschließen oder Board explizit angeben."
                ),
                details={
                    "bitstream_path": bitstream_path,
                    "target_board": target_board,
                    "expected_part": expected_part,
                    "error": "multiple_boards_detected",
                    "detected_devices": boards,
                },
                board_detected=True,
                board_count=board_count,
            )

        # Genau ein Board erkannt -> flashen
        logger.info("Flashing bitstream %s to board %s", bitstream_path, target_board)
        cmd = [
            self._binary,
            "-c", self._cable,
            "-b", target_board,
            "-f",
            str(bitstream_file),
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self._timeout_seconds,
            )

            if result.returncode != 0:
                error_msg = result.stderr or result.stdout or "Unknown error"
                return FlashResult(
                    passed=False,
                    message=f"Flash fehlgeschlagen: {error_msg[:500]}",
                    details={
                        "bitstream_path": bitstream_path,
                        "target_board": target_board,
                        "expected_part": expected_part,
                        "returncode": result.returncode,
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                        "detected_devices": boards,
                    },
                    board_detected=True,
                    board_count=board_count,
                )

            logger.info("Flash successful for %s", bitstream_path)
            return FlashResult(
                passed=True,
                message=f"Bitstream erfolgreich auf {target_board} geflasht",
                details={
                    "bitstream_path": bitstream_path,
                    "target_board": target_board,
                    "expected_part": expected_part,
                    "stdout": result.stdout,
                    "detected_devices": boards,
                },
                board_detected=True,
                board_count=board_count,
            )

        except FileNotFoundError:
            logger.error("openFPGALoader binary not found: %s", self._binary)
            return FlashResult(
                passed=False,
                message=f"openFPGALoader binary '{self._binary}' not found. Please install openFPGALoader.",
                details={"bitstream_path": bitstream_path, "error": "binary_not_found", "expected_part": expected_part},
                board_detected=board_count > 0,
                board_count=board_count,
            )
        except subprocess.TimeoutExpired:
            logger.error("openFPGALoader flash timed out after %ds", self._timeout_seconds)
            return FlashResult(
                passed=False,
                message=f"Flash timed out after {self._timeout_seconds}s",
                details={
                    "bitstream_path": bitstream_path,
                    "target_board": target_board,
                    "expected_part": expected_part,
                    "error": "timeout",
                },
                board_detected=board_count > 0,
                board_count=board_count,
            )
        except Exception as e:
            logger.exception("Flash failed with exception")
            return FlashResult(
                passed=False,
                message=f"Flash failed: {e}",
                details={
                    "bitstream_path": bitstream_path,
                    "target_board": target_board,
                    "expected_part": expected_part,
                    "error": str(e),
                },
                board_detected=board_count > 0,
                board_count=board_count,
            )
