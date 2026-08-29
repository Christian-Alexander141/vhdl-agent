import logging
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
        default_board: str = "arty_s7",
    ):
        self._binary = binary
        self._timeout_seconds = timeout_seconds
        self._default_board = default_board

    def toolchain_available(self) -> bool:
        return shutil.which(self._binary) is not None

    def detect_boards(self, expected_part: str = "") -> list[dict]:
        """Erkennt angeschlossene Boards via openFPGALoader --detect."""
        cmd = [self._binary, "--detect"]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
            )
            boards = []
            # openFPGALoader --detect gibt Zeilen wie:
            # "Found 1 device(s):"
            # "  0: Arty S7 (serial=210299A5B3E3)"
            for line in (result.stdout or "").splitlines():
                line = line.strip()
                if line.startswith(("0:", "1:", "2:", "3:")):
                    # Format: "0: Arty S7 (serial=210299A5B3E3)"
                    parts = line.split(":", 1)
                    if len(parts) == 2:
                        board_info = parts[1].strip()
                        name = board_info.split("(")[0].strip()
                        boards.append({
                            "index": int(parts[0]),
                            "name": name,
                            "details": board_info,
                            "part": name,  # openFPGALoader liefert keinen expliziten Part
                        })
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

    def flash(self, bitstream_path: str, board: str = "", expected_part: str = "") -> FlashResult:
        """Flasht den Bitstream auf das angegebene Board.

        Args:
            bitstream_path: Pfad zur .bit-Datei
            board: Board-Name für openFPGALoader -b Option (Default: arty_s7)
            expected_part: Wird ignoriert (openFPGALoader verwendet board-Name)

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
            "-b", target_board,
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
