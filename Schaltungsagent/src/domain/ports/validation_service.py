from abc import ABC, abstractmethod
from typing import Any


class ValidationResult:
    def __init__(self, passed: bool, message: str = "", details: dict | None = None):
        self.passed = passed
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "message": self.message,
            "details": self.details,
        }


class ValidationService(ABC):
    @abstractmethod
    def validate(self, workspace: str, domain: str = "vhdl") -> ValidationResult:
        ...

    @abstractmethod
    def validate_file(self, file_path: str, domain: str = "vhdl") -> ValidationResult:
        ...
