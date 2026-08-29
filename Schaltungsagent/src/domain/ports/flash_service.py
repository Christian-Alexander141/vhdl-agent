from abc import ABC, abstractmethod


class FlashResult:
    """Ergebnis eines Flash-Vorgangs (Programmieren des FPGA).

    Enthält Erfolgsstatus, Meldung, Details sowie Informationen über
    erkannte Boards (board_detected, board_count).
    """

    def __init__(
        self,
        passed: bool,
        message: str = "",
        details: dict | None = None,
        board_detected: bool = False,
        board_count: int = 0,
    ):
        self.passed = passed
        self.message = message
        self.details = details or {}
        self.board_detected = board_detected
        self.board_count = board_count

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "message": self.message,
            "details": self.details,
            "board_detected": self.board_detected,
            "board_count": self.board_count,
        }


class FlashService(ABC):
    """Port für das Flashen (Programmieren) eines FPGA-Boards.

    Adapter: OpenFPGALoaderFlashService (openFPGALoader für verschiedene Boards),
    VivadoFlashService (Xilinx Vivado Hardware Manager), etc.
    """

    @abstractmethod
    def flash(self, bitstream_path: str, board: str = "") -> FlashResult:
        ...

    @abstractmethod
    def toolchain_available(self) -> bool:
        ...

    @abstractmethod
    def detect_boards(self) -> list[dict]:
        """Erkennt angeschlossene Boards.
        
        Returns:
            Liste von Board-Informationen (name, id, etc.).
        """
        ...