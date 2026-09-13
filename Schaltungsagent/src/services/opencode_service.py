import shutil
import subprocess
import logging
from pathlib import Path
from src.domain.ports import OpenCodeService, OpenCodeResult
from src.domain.exceptions import AgentExecutionError

logger = logging.getLogger(__name__)


def create_opencode_service(settings):
    """Create the configured OpenCode runner."""
    if settings.opencode.use_docker and not settings.opencode.test_mode:
        return DockerOpenCodeService(
            container=settings.opencode.docker_container,
            docker_workspace=settings.opencode.docker_workspace,
            host_workspace=settings.resolve_path(settings.opencode.docker_host_workspace),
            binary=settings.opencode.binary,
            default_timeout=settings.opencode.default_timeout,
        )
    return SubprocessOpenCodeService(
        binary=settings.opencode.binary,
        default_timeout=settings.opencode.default_timeout,
    )


class SubprocessOpenCodeService(OpenCodeService):
    def __init__(self, binary: str = "opencode", default_timeout: int = 600):
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


class DockerOpenCodeService(OpenCodeService):
    def __init__(
        self,
        container: str = "opencode-agent",
        docker_workspace: str = "/workspace",
        host_workspace: str | None = None,
        binary: str = "opencode",
        default_timeout: int = 600,
    ):
        self._container = container
        self._docker_workspace = docker_workspace
        self._host_workspace = Path(host_workspace).resolve() if host_workspace else None
        self._binary = binary
        self._default_timeout = default_timeout

    def execute(
        self,
        project_path: str,
        instruction: str,
        timeout_seconds: int | None = None,
    ) -> OpenCodeResult:
        timeout = timeout_seconds or self._default_timeout
        container_path = self._resolve_container_path(project_path)
        logger.info(
            "OpenCode executing in Docker: container=%s, cwd=%s, timeout=%d",
            self._container,
            container_path,
            timeout,
        )

        cmd = [
            "docker",
            "exec",
            "-w",
            container_path,
            self._container,
            self._binary,
            "run",
            instruction,
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            stderr_lower = (result.stderr or "").lower()
            if result.returncode != 0 and \
               "permission denied while trying to connect to the docker api" in stderr_lower:
                logger.error(
                    "Docker permission denied: unable to access /var/run/docker.sock"
                )
                if shutil.which(self._binary):
                    logger.warning(
                        "Falling back to local OpenCode CLI because Docker socket is unavailable."
                    )
                    return SubprocessOpenCodeService(
                        binary=self._binary,
                        default_timeout=self._default_timeout,
                    ).execute(project_path, instruction, timeout_seconds=timeout)
                result.stderr = (
                    (result.stderr or "") +
                    "\nDocker permission denied. "
                    "Ensure the current user can access /var/run/docker.sock or disable Docker-based OpenCode in the configuration."
                )
            logger.info(
                "Docker OpenCode finished: returncode=%d",
                result.returncode,
            )
            return OpenCodeResult(
                returncode=result.returncode,
                stdout=result.stdout or "",
                stderr=result.stderr or "",
            )

        except FileNotFoundError:
            logger.error("Docker binary not found")
            if shutil.which(self._binary):
                logger.warning(
                    "Docker binary not found; falling back to local OpenCode CLI."
                )
                return SubprocessOpenCodeService(
                    binary=self._binary,
                    default_timeout=self._default_timeout,
                ).execute(project_path, instruction, timeout_seconds=timeout)
            raise AgentExecutionError(
                "Docker executable 'docker' not found. "
                "Please install Docker or ensure it is available in PATH."
            ) from None

        except subprocess.TimeoutExpired:
            logger.error("Docker OpenCode timed out after %ds", timeout)
            raise AgentExecutionError(
                f"OpenCode execution timed out after {timeout}s"
            ) from None

    def _resolve_container_path(self, project_path: str) -> str:
        host_path = Path(project_path).resolve()
        if self._host_workspace and self._host_workspace in host_path.parents:
            relative_path = host_path.relative_to(self._host_workspace)
            return str(Path(self._docker_workspace) / relative_path)
        if self._host_workspace and host_path == self._host_workspace:
            return self._docker_workspace
        logger.error(
            "Project path %s is not under configured host_workspace %s. "
            "This will cause incorrect container paths. "
            "Please ensure opencode.docker_host_workspace matches workspace.base_dir.",
            project_path, self._host_workspace
        )
        return self._docker_workspace
