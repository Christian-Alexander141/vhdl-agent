import os
import re
import shutil
import time
import logging
from pathlib import Path, PurePosixPath
from src.domain.ports import FileSystemService
from src.domain.exceptions import WorkspaceError

logger = logging.getLogger(__name__)

_PROJECT_ID_PATTERN = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_-]*$')

class PathTraversalError(WorkspaceError):
    pass


def _safe_resolve(base: Path, target: Path) -> Path:
    """Resolve path and verify it stays within base. Raises PathTraversalError on violation."""
    try:
        resolved = target.resolve()
    except (OSError, RuntimeError) as e:
        raise PathTraversalError(f"Cannot resolve path: {e}") from e
    try:
        base_resolved = base.resolve()
    except (OSError, RuntimeError) as e:
        raise PathTraversalError(f"Cannot resolve base directory: {e}") from e
    try:
        resolved.relative_to(base_resolved)
    except ValueError:
        raise PathTraversalError(
            f"Path traversal detected: {resolved} is outside {base_resolved}"
        )
    return resolved


def _validate_project_id(task_id: str) -> None:
    """Validate project ID is a safe name without traversal characters."""
    if not task_id or not _PROJECT_ID_PATTERN.match(task_id):
        raise PathTraversalError(
            f"Invalid project ID: '{task_id}'. Must match {_PROJECT_ID_PATTERN.pattern}"
        )


def _check_null_bytes(path: str) -> None:
    if '\x00' in path:
        raise PathTraversalError(f"Null byte detected in path: {path}")


class LocalFileSystemService(FileSystemService):
    def __init__(
        self,
        base_dir: str = "./projects",
        cleanup_ttl_hours: int = 72,
        max_workspaces: int = 100,
    ):
        self._base_dir = Path(base_dir).resolve()
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._cleanup_ttl = cleanup_ttl_hours * 3600
        self._max_workspaces = max_workspaces

    def create_workspace(self, task_id: str, domain: str = "vhdl") -> str:
        _validate_project_id(task_id)
        _check_null_bytes(task_id)
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
        _check_null_bytes(path)
        file_path = self._resolve(path)
        try:
            # Atomar: parallele Worker lesen u. a. design_state.yaml, während sie geschrieben wird.
            from src.services.opencode_task_runner import atomic_write_text
            atomic_write_text(file_path, content)
            logger.info("File written: %s", file_path)
            return str(file_path)
        except OSError as e:
            raise WorkspaceError(f"Failed to write file {path}: {e}") from e

    def read_file(self, path: str) -> str:
        _check_null_bytes(path)
        file_path = self._resolve(path)
        if not file_path.exists():
            raise WorkspaceError(f"File not found: {path}")
        try:
            return file_path.read_text(encoding="utf-8")
        except OSError as e:
            raise WorkspaceError(f"Failed to read file {path}: {e}") from e

    def file_exists(self, path: str) -> bool:
        _check_null_bytes(path)
        try:
            return self._resolve(path).exists()
        except PathTraversalError:
            return False

    def list_files(self, workspace_path: str, pattern: str = "**/*") -> list[str]:
        _check_null_bytes(workspace_path)
        base = self._resolve(workspace_path)
        if not base.exists():
            return []
        return [str(p.relative_to(base)) for p in base.glob(pattern) if p.is_file()]

    def delete_workspace(self, task_id: str) -> None:
        _validate_project_id(task_id)
        workspace = self._base_dir / task_id
        if workspace.exists():
            try:
                shutil.rmtree(workspace)
                logger.info("Workspace deleted: %s", workspace)
            except OSError as e:
                raise WorkspaceError(f"Failed to delete workspace {workspace}: {e}") from e

    def rename_workspace(self, source_id: str, target_id: str) -> str:
        _validate_project_id(source_id)
        _validate_project_id(target_id)
        source = self._resolve_project_path(source_id)
        target = self._resolve_project_path(target_id)
        if not source.is_dir():
            raise WorkspaceError(f"Workspace not found: {source_id}")
        if target.exists():
            raise WorkspaceError(f"Workspace already exists: {target_id}")
        source.rename(target)
        return str(target)

    def workspace_path(self, task_id: str) -> str:
        _validate_project_id(task_id)
        return str(self._base_dir / task_id)

    def _resolve(self, path: str) -> Path:
        """Resolve a path relative to _base_dir, verifying no traversal occurs."""
        target = Path(path)
        if target.is_absolute():
            resolved = target.resolve()
        else:
            resolved = (self._base_dir / target).resolve()
        return _safe_resolve(self._base_dir, resolved)

    def _resolve_project_path(self, project_id: str) -> Path:
        """Resolve a project workspace path with validation."""
        _validate_project_id(project_id)
        return _safe_resolve(self._base_dir, self._base_dir / project_id)

    def list_workspaces(self) -> list[str]:
        if not self._base_dir.is_dir():
            return []
        return sorted(e.name for e in self._base_dir.iterdir() if e.is_dir())

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
