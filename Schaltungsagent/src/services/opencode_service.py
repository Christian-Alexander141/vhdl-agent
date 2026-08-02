import subprocess
import logging
from src.domain.ports import OpenCodeService, OpenCodeResult
from src.domain.exceptions import AgentExecutionError

logger = logging.getLogger(__name__)


class SubprocessOpenCodeService(OpenCodeService):
    def __init__(self, binary: str = "opencode", default_timeout: int = 300):
        self._binary = binary
        self._default_timeout = default_timeout

    def execute(
        self,
        project_path: str,
        instruction: str,
        timeout_seconds: int | None = None,
    ) -> OpenCodeResult:
        timeout = timeout_seconds or self._default_timeout
        logger.info(
            "OpenCode executing: binary=%s, project=%s, timeout=%d",
            self._binary, project_path, timeout,
        )

        cmd = [self._binary, "run", instruction]

        try:
            result = subprocess.run(
                cmd,
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            logger.info(
                "OpenCode finished: returncode=%d",
                result.returncode,
            )
            return OpenCodeResult(
                returncode=result.returncode,
                stdout=result.stdout or "",
                stderr=result.stderr or "",
            )

        except FileNotFoundError:
            logger.error("OpenCode binary not found: %s", self._binary)
            raise AgentExecutionError(
                f"OpenCode binary '{self._binary}' not found. "
                f"Please install opencode CLI."
            ) from None

        except subprocess.TimeoutExpired:
            logger.error("OpenCode timed out after %ds", timeout)
            raise AgentExecutionError(
                f"OpenCode execution timed out after {timeout}s"
            ) from None
