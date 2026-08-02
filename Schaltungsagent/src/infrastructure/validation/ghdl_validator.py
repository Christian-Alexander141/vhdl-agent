import subprocess
import logging
from pathlib import Path

from src.domain.ports.validation_service import ValidationService, ValidationResult

logger = logging.getLogger(__name__)


class GHDLValidator(ValidationService):
    def __init__(self, ghdl_binary: str = "ghdl"):
        self._ghdl_binary = ghdl_binary

    def validate(self, workspace: str, domain: str = "vhdl") -> ValidationResult:
        logger.info("GHDL validating workspace: %s", workspace)
        ws_path = Path(workspace)
        src_dir = ws_path / "src"
        if not src_dir.exists():
            return ValidationResult(passed=False, message="No src directory found")
        vhd_files = list(src_dir.glob("*.vhd")) + list(src_dir.glob("*.vhdl"))
        if not vhd_files:
            return ValidationResult(passed=False, message="No VHDL files found")
        try:
            for vhd_file in vhd_files:
                result = subprocess.run(
                    [self._ghdl_binary, "-a", str(vhd_file)],
                    capture_output=True, text=True, timeout=60,
                )
                if result.returncode != 0:
                    return ValidationResult(
                        passed=False,
                        message=f"GHDL analysis failed for {vhd_file.name}",
                        details={"file": str(vhd_file), "error": result.stderr},
                    )
            return ValidationResult(
                passed=True,
                message="All VHDL files passed GHDL analysis",
                details={"files_checked": [str(f) for f in vhd_files]},
            )
        except FileNotFoundError:
            return ValidationResult(
                passed=False,
                message=f"GHDL binary '{self._ghdl_binary}' not found",
            )
        except subprocess.TimeoutExpired:
            return ValidationResult(
                passed=False, message="GHDL analysis timed out"
            )
        except Exception as e:
            return ValidationResult(passed=False, message=str(e))

    def validate_file(self, file_path: str, domain: str = "vhdl") -> ValidationResult:
        path = Path(file_path)
        if not path.exists():
            return ValidationResult(passed=False, message=f"File not found: {file_path}")
        try:
            result = subprocess.run(
                [self._ghdl_binary, "-a", str(path)],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode != 0:
                return ValidationResult(
                    passed=False,
                    message=f"GHDL analysis failed",
                    details={"file": file_path, "error": result.stderr},
                )
            return ValidationResult(passed=True, message=f"File {path.name} passed analysis")
        except FileNotFoundError:
            return ValidationResult(
                passed=False,
                message=f"GHDL binary '{self._ghdl_binary}' not found",
            )
        except subprocess.TimeoutExpired:
            return ValidationResult(passed=False, message="GHDL analysis timed out")
        except Exception as e:
            return ValidationResult(passed=False, message=str(e))
