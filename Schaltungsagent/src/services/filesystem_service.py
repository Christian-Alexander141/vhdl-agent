import os
import shutil
import time
import logging
from pathlib import Path
from src.domain.ports import FileSystemService
from src.domain.exceptions import WorkspaceError

logger = logging.getLogger(__name__)


class LocalFileSystemService(FileSystemService):
    def __init__(
        self,
        base_dir: str = "./projects",
        cleanup_ttl_hours: int = 72,
        max_workspaces: int = 100,
    ):
        self._base_dir = Path(base_dir).resolve()
        self._cleanup_ttl = cleanup_ttl_hours * 3600
        self._max_workspaces = max_workspaces

    def create_workspace(self, task_id: str, domain: str = "vhdl") -> str:
        self._enforce_limits()
        workspace = self._base_dir / task_id
        try:
            workspace.mkdir(parents=True, exist_ok=True)
            for subdir in ["src", "tests", "docs", "build", "logs", "reports"]:
                (workspace / subdir).mkdir(parents=True, exist_ok=True)
            logger.info("Workspace created: %s", workspace)
            return str(workspace)
        except OSError as e:
            raise WorkspaceError(f"Failed to create workspace {workspace}: {e}") from e

    def write_file(self, path: str, content: str) -> str:
        file_path = Path(path)
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")
            logger.info("File written: %s", file_path)
            return str(file_path)
        except OSError as e:
            raise WorkspaceError(f"Failed to write file {path}: {e}") from e

    def read_file(self, path: str) -> str:
        file_path = Path(path)
        if not file_path.exists():
            raise WorkspaceError(f"File not found: {path}")
        try:
            return file_path.read_text(encoding="utf-8")
        except OSError as e:
            raise WorkspaceError(f"Failed to read file {path}: {e}") from e

    def file_exists(self, path: str) -> bool:
        return Path(path).exists()

    def list_files(self, workspace_path: str, pattern: str = "**/*") -> list[str]:
        base = Path(workspace_path)
        if not base.exists():
            return []
        return [str(p.relative_to(base)) for p in base.glob(pattern) if p.is_file()]

    def delete_workspace(self, task_id: str) -> None:
        workspace = self._base_dir / task_id
        if workspace.exists():
            try:
                shutil.rmtree(workspace)
                logger.info("Workspace deleted: %s", workspace)
            except OSError as e:
                raise WorkspaceError(f"Failed to delete workspace {workspace}: {e}") from e

    def workspace_path(self, task_id: str) -> str:
        return str(self._base_dir / task_id)

    def cleanup_expired(self, force: bool = False) -> int:
        if not self._base_dir.exists():
            return 0
        now = time.time()
        removed = 0
        for entry in self._base_dir.iterdir():
            if not entry.is_dir():
                continue
            if force:
                try:
                    shutil.rmtree(entry)
                    removed += 1
                except OSError:
                    continue
            else:
                mtime = entry.stat().st_mtime
                if now - mtime > self._cleanup_ttl:
                    try:
                        shutil.rmtree(entry)
                        removed += 1
                        logger.info("Cleaned up expired workspace: %s", entry.name)
                    except OSError:
                        continue
        if removed:
            logger.info("Cleanup removed %d expired workspaces", removed)
        return removed

    def workspace_count(self) -> int:
        if not self._base_dir.exists():
            return 0
        return sum(1 for e in self._base_dir.iterdir() if e.is_dir())

    def _enforce_limits(self) -> None:
        count = self.workspace_count()
        if count >= self._max_workspaces:
            logger.warning(
                "Workspace limit reached (%d/%d), cleaning up oldest",
                count, self._max_workspaces,
            )
            self.cleanup_expired()

        self.cleanup_expired()
