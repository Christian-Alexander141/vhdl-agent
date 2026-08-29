from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class OpenCodeResult:
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""

    @property
    def success(self) -> bool:
        return self.returncode == 0

    def to_dict(self) -> dict:
        return {
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }


class OpenCodeService(ABC):
    @abstractmethod
    def execute(
        self,
        project_path: str,
        instruction: str,
        timeout_seconds: int = 600,
    ) -> OpenCodeResult:
        ...
