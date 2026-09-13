"""OpenCode Worker abstraction for multi-worker execution.

Each worker wraps an OpenCode CLI instance with a unique worker_id.
Workers execute tasks in isolation while sharing the same project workspace.
File ownership is enforced to prevent concurrent modification conflicts.
"""
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from src.domain.ports.opencode_service import OpenCodeService, OpenCodeResult
from src.domain.agents.task_graph import FileOwnershipRegistry

logger = logging.getLogger(__name__)


@dataclass
class WorkerTask:
    """A task assigned to a specific worker."""
    task_id: str
    task_type: str
    instruction: str
    owned_files: list[str] = field(default_factory=list)
    workspace: str = ""
    timeout_seconds: int = 600
    context: dict = field(default_factory=dict)


@dataclass
class WorkerResult:
    """Result from a worker execution."""
    task_id: str
    worker_id: str
    success: bool
    output: str = ""
    error: str = ""
    files_written: list[str] = field(default_factory=list)
    completed_at: str = ""
    duration_seconds: float = 0.0


class OpenCodeWorker:
    """Wraps an OpenCode CLI instance with a unique worker identity.
    
    Workers execute tasks against a shared project workspace while
    file ownership is enforced to prevent conflicts.
    """
    
    def __init__(
        self,
        worker_id: str | None = None,
        opencode_service: OpenCodeService | None = None,
        ownership_registry: FileOwnershipRegistry | None = None,
    ):
        self.worker_id = worker_id or f"worker-{uuid.uuid4().hex[:8]}"
        self._opencode = opencode_service
        self._ownership = ownership_registry
        self._assigned_files: set[str] = set()
        self._current_task: Optional[WorkerTask] = None
        self._completed_tasks: list[WorkerResult] = []
    
    def assign_files(self, file_paths: list[str]) -> list[str]:
        """Assign files to this worker via the ownership registry.
        
        Returns list of conflicting files (owned by other workers).
        """
        if not self._ownership:
            return []
        conflicts = self._ownership.claim(self.worker_id, file_paths)
        self._assigned_files.update(file_paths)
        return conflicts
    
    def release_files(self) -> None:
        """Release all file ownerships for this worker."""
        if self._ownership:
            self._ownership.release(self.worker_id)
        self._assigned_files.clear()
    
    def can_access_file(self, file_path: str) -> bool:
        """Check if this worker can access a file."""
        if not self._ownership:
            return True
        return self._ownership.check_access(self.worker_id, file_path)
    
    def execute_task(self, task: WorkerTask) -> WorkerResult:
        """Execute a task using the OpenCode service.
        
        Before execution, validates file ownership to prevent conflicts.
        """
        self._current_task = task
        start_time = datetime.now(timezone.utc)
        
        # Validate file ownership
        for fp in task.owned_files:
            if not self.can_access_file(fp):
                return WorkerResult(
                    task_id=task.task_id,
                    worker_id=self.worker_id,
                    success=False,
                    error=f"Scope violation: {fp} is owned by another worker",
                    completed_at=datetime.now(timezone.utc).isoformat(),
                )
        
        # Claim ownership
        self.assign_files(task.owned_files)
        
        if not self._opencode:
            result = WorkerResult(
                task_id=task.task_id,
                worker_id=self.worker_id,
                success=False,
                error="No OpenCode service configured",
                completed_at=datetime.now(timezone.utc).isoformat(),
            )
            self._completed_tasks.append(result)
            return result
        
        # Execute via OpenCode
        try:
            oc_result: OpenCodeResult = self._opencode.execute(
                project_path=task.workspace,
                instruction=task.instruction,
                timeout_seconds=task.timeout_seconds,
            )
            
            end_time = datetime.now(timezone.utc)
            duration = (end_time - start_time).total_seconds()
            
            result = WorkerResult(
                task_id=task.task_id,
                worker_id=self.worker_id,
                success=oc_result.success,
                output=oc_result.stdout,
                error=oc_result.stderr if not oc_result.success else "",
                files_written=task.owned_files,
                completed_at=end_time.isoformat(),
                duration_seconds=duration,
            )
            
        except Exception as e:
            end_time = datetime.now(timezone.utc)
            result = WorkerResult(
                task_id=task.task_id,
                worker_id=self.worker_id,
                success=False,
                error=str(e),
                completed_at=end_time.isoformat(),
            )
        
        self._completed_tasks.append(result)
        self._current_task = None
        
        # Release ownership after completion
        self.release_files()
        
        return result
    
    def get_status(self) -> dict:
        return {
            "worker_id": self.worker_id,
            "current_task": self._current_task.task_id if self._current_task else None,
            "assigned_files": list(self._assigned_files),
            "completed_count": len(self._completed_tasks),
            "success_count": sum(1 for r in self._completed_tasks if r.success),
        }
    
    def to_dict(self) -> dict:
        return {
            "worker_id": self.worker_id,
            "status": self.get_status(),
        }
    
    def __repr__(self) -> str:
        return f"OpenCodeWorker(id={self.worker_id}, tasks={len(self._completed_tasks)})"


class WorkerPool:
    """Manages a pool of OpenCode workers for parallel task execution.
    
    Assigns tasks to available workers, respecting file ownership constraints.
    """
    
    def __init__(self, ownership_registry: FileOwnershipRegistry | None = None):
        self._workers: dict[str, OpenCodeWorker] = {}
        self._ownership = ownership_registry
        self._task_worker_map: dict[str, str] = {}  # task_id -> worker_id
    
    def create_worker(
        self,
        worker_id: str | None = None,
        opencode_service: OpenCodeService | None = None,
    ) -> OpenCodeWorker:
        """Create and register a new worker."""
        worker = OpenCodeWorker(
            worker_id=worker_id,
            opencode_service=opencode_service,
            ownership_registry=self._ownership,
        )
        self._workers[worker.worker_id] = worker
        logger.info("Created worker %s", worker.worker_id)
        return worker
    
    def get_worker(self, worker_id: str) -> OpenCodeWorker | None:
        return self._workers.get(worker_id)
    
    def get_available_worker(self) -> OpenCodeWorker | None:
        """Find a worker that is not currently executing a task."""
        for worker in self._workers.values():
            if worker._current_task is None:
                return worker
        return None
    
    def assign_task(self, task: WorkerTask) -> OpenCodeWorker | None:
        """Assign a task to an available worker.
        
        Returns the worker if assignment was successful, None otherwise.
        Tries to distribute tasks across workers.
        """
        # First, try to find a worker that isn't busy
        for worker in self._workers.values():
            if worker._current_task is None:
                # Check file ownership conflicts
                has_conflict = False
                for fp in task.owned_files:
                    if not worker.can_access_file(fp):
                        has_conflict = True
                        break
                if not has_conflict:
                    self._task_worker_map[task.task_id] = worker.worker_id
                    return worker
        
        logger.warning("No available workers for task %s", task.task_id)
        return None
    
    def get_worker_for_task(self, task_id: str) -> OpenCodeWorker | None:
        """Get the worker assigned to a task."""
        worker_id = self._task_worker_map.get(task_id)
        if worker_id:
            return self._workers.get(worker_id)
        return None
    
    def get_all_workers(self) -> list[OpenCodeWorker]:
        return list(self._workers.values())
    
    def get_stats(self) -> dict:
        return {
            "total_workers": len(self._workers),
            "idle_workers": sum(1 for w in self._workers.values() if w._current_task is None),
            "busy_workers": sum(1 for w in self._workers.values() if w._current_task is not None),
            "total_completed": sum(len(w._completed_tasks) for w in self._workers.values()),
        }
    
    def to_dict(self) -> dict:
        return {
            "workers": {wid: w.to_dict() for wid, w in self._workers.items()},
            "task_worker_map": self._task_worker_map,
            "stats": self.get_stats(),
        }
