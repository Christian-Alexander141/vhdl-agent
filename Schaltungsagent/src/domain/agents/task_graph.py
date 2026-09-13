"""Enhanced Task Graph for multi-agent task orchestration.

This module provides a DAG-based task graph with:
- READY/RUNNING/COMPLETED scheduling states
- File ownership tracking per task
- Task invalidation when upstream artifacts change
- Parallel batch execution support
- Dependency-aware scheduling
"""
import logging
from typing import Optional
from datetime import datetime, timezone
from .base import AgentTask, TaskStatus

logger = logging.getLogger(__name__)


class FileOwnershipRegistry:
    """Tracks file ownership per task to prevent conflicts.
    
    Each task claims ownership over specific files. A task may not
    modify files owned by another running task without explicit permission.
    """
    
    def __init__(self):
        self._ownerships: dict[str, set[str]] = {}  # task_id -> set of file paths
        self._file_to_task: dict[str, str] = {}      # file_path -> task_id
        self._lock_until: dict[str, str] = {}        # file_path -> task_id (locking task)
    
    def claim(self, task_id: str, file_paths: list[str]) -> list[str]:
        """Claim ownership of files for a task.
        
        Only non-conflicting files are registered. Conflicting files are
        reported but NOT registered for the claiming task.
        
        Returns list of files that were already owned (potential conflicts).
        """
        conflicts = []
        for fp in file_paths:
            if fp in self._file_to_task and self._file_to_task[fp] != task_id:
                conflicts.append(fp)
            else:
                self._file_to_task[fp] = task_id
                if task_id not in self._ownerships:
                    self._ownerships[task_id] = set()
                self._ownerships[task_id].add(fp)
        return conflicts
    
    def release(self, task_id: str) -> None:
        """Release all file ownerships for a task."""
        files = self._ownerships.pop(task_id, set())
        for fp in files:
            if self._file_to_task.get(fp) == task_id:
                del self._file_to_task[fp]
    
    def check_access(self, task_id: str, file_path: str) -> bool:
        """Check if a task is allowed to access a file.
        
        Returns True if the file is unowned or owned by this task.
        """
        owner = self._file_to_task.get(file_path)
        return owner is None or owner == task_id
    
    def get_owner(self, file_path: str) -> str | None:
        """Get the owner task of a file."""
        return self._file_to_task.get(file_path)
    
    def get_files(self, task_id: str) -> set[str]:
        """Get all files owned by a task."""
        return self._ownerships.get(task_id, set()).copy()
    
    def get_all(self) -> dict[str, set[str]]:
        """Get all ownership mappings."""
        return {k: v.copy() for k, v in self._ownerships.items()}
    
    def to_dict(self) -> dict:
        return {k: list(v) for k, v in self._ownerships.items()}
    
    @classmethod
    def from_dict(cls, data: dict) -> 'FileOwnershipRegistry':
        reg = cls()
        for task_id, files in data.items():
            reg.claim(task_id, files)
        return reg


class TaskGraph:
    """Enhanced directed acyclic graph for task orchestration.
    
    Manages task dependencies, execution order, status tracking,
    file ownership, and task invalidation.
    """
    
    def __init__(self):
        self._tasks: dict[str, AgentTask] = {}
        self._dependency_map: dict[str, set[str]] = {}  # task_id -> set of dependency task_ids
        self._ownership = FileOwnershipRegistry()
        self._invalidated: set[str] = set()  # task_ids that need re-verification
        self._completed_at: dict[str, str] = {}  # task_id -> completion timestamp
    
    def add_task(self, task: AgentTask, owned_files: list[str] | None = None) -> None:
        """Add a task to the graph, optionally claiming file ownership."""
        if task.id in self._tasks:
            raise ValueError(f"Task {task.id} already exists in graph")
        
        self._tasks[task.id] = task
        self._dependency_map[task.id] = set(task.depends_on)
        
        if owned_files:
            conflicts = self._ownership.claim(task.id, owned_files)
            if conflicts:
                logger.warning("Task %s has ownership conflicts: %s", task.id, conflicts)
        
        logger.debug("Added task %s (deps: %s, owns: %s)", task.id, task.depends_on, owned_files)
    
    def get_task(self, task_id: str) -> Optional[AgentTask]:
        return self._tasks.get(task_id)
    
    def get_all_tasks(self) -> list[AgentTask]:
        return list(self._tasks.values())
    
    def get_ready_tasks(self) -> list[AgentTask]:
        """Get tasks whose dependencies are all satisfied and are not invalidated."""
        ready = []
        for task_id, task in self._tasks.items():
            if task.status not in (TaskStatus.CREATED, TaskStatus.QUEUED):
                continue
            if task_id in self._invalidated:
                continue
            
            deps = self._dependency_map.get(task_id, set())
            all_deps_satisfied = all(
                self._tasks.get(dep_id, AgentTask(id=dep_id, type="", project_id="")).status
                in (TaskStatus.PASSED, TaskStatus.COMPLETED)
                for dep_id in deps
            )
            
            if all_deps_satisfied:
                ready.append(task)
        
        return ready
    
    def get_parallel_batches(self) -> list[list[AgentTask]]:
        """Compute batches of tasks that can run in parallel.
        
        Returns a list of batches. Each batch contains tasks whose
        dependencies are all COMPLETED (not just in the same batch).
        Tasks within a batch have no mutual dependencies.
        """
        batches = []
        # Start with already completed tasks
        completed: set[str] = {
            tid for tid, t in self._tasks.items()
            if t.status in (TaskStatus.PASSED, TaskStatus.COMPLETED)
        }
        remaining = {tid for tid, t in self._tasks.items()
                     if t.status in (TaskStatus.CREATED, TaskStatus.QUEUED)}
        
        while remaining:
            batch = []
            for task_id in list(remaining):
                task = self._tasks[task_id]
                deps = self._dependency_map.get(task_id, set())
                # All deps must be completed (not in same batch)
                deps_met = all(d in completed for d in deps)
                if deps_met:
                    batch.append(task)
            
            if not batch:
                break  # Safety: avoid infinite loop on circular deps
            
            batches.append(batch)
            completed |= {t.id for t in batch}
            remaining -= {t.id for t in batch}
        
        return batches
    
    def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        result: dict | None = None,
        error: str = "",
    ) -> None:
        """Update the status of a task."""
        task = self._tasks.get(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found in graph")
        
        task.status = status
        if result:
            task.result = result
        if error:
            task.error = error
        
        if status in (TaskStatus.COMPLETED, TaskStatus.PASSED):
            self._completed_at[task_id] = datetime.now(timezone.utc).isoformat()
            # Release file ownership on completion
            self._ownership.release(task_id)
            # Invalidate dependent tasks that need re-verification
            self._invalidate_dependents(task_id)
        
        logger.info("Task %s status updated to %s", task_id, status.value)
    
    def mark_running(self, task_id: str, worker_id: str = "") -> None:
        """Mark a task as running, optionally assigning a worker."""
        task = self._tasks.get(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found in graph")
        task.status = TaskStatus.RUNNING
        if worker_id:
            task.assigned_agent = worker_id
        logger.info("Task %s started on worker %s", task_id, worker_id or "unknown")
    
    def mark_completed(self, task_id: str, result: dict | None = None) -> None:
        """Mark a task as completed and release ownership."""
        self.update_task_status(task_id, TaskStatus.COMPLETED, result)
    
    def mark_failed(self, task_id: str, error: str = "") -> None:
        """Mark a task as failed."""
        self.update_task_status(task_id, TaskStatus.FAILED, error=error)
    
    def _invalidate_dependents(self, task_id: str) -> None:
        """Invalidate tasks that depend on the given task.
        
        When a task completes, its dependents may need re-verification
        if the completed task changed its output artifacts.
        """
        for dependent in self.get_dependents(task_id):
            if dependent.status in (TaskStatus.COMPLETED, TaskStatus.PASSED):
                self._invalidated.add(dependent.id)
                logger.info("Task %s invalidated due to change in %s", dependent.id, task_id)
    
    def invalidate_task(self, task_id: str) -> None:
        """Manually invalidate a task (mark as needing re-verification)."""
        self._invalidated.add(task_id)
        task = self._tasks.get(task_id)
        if task and task.status in (TaskStatus.COMPLETED, TaskStatus.PASSED):
            task.status = TaskStatus.QUEUED  # Reset to re-queue
        logger.info("Task %s manually invalidated", task_id)
    
    def clear_invalidated(self) -> None:
        """Clear all invalidation flags."""
        self._invalidated.clear()
    
    def is_invalidated(self, task_id: str) -> bool:
        """Check if a task is invalidated."""
        return task_id in self._invalidated
    
    def get_invalidated_tasks(self) -> list[AgentTask]:
        """Get all invalidated tasks."""
        return [self._tasks[tid] for tid in self._invalidated if tid in self._tasks]
    
    def get_dependents(self, task_id: str) -> list[AgentTask]:
        """Get tasks that depend on the given task."""
        dependents = []
        for tid, deps in self._dependency_map.items():
            if task_id in deps:
                dependents.append(self._tasks[tid])
        return dependents
    
    def get_dependencies(self, task_id: str) -> list[AgentTask]:
        """Get tasks that the given task depends on."""
        deps = self._dependency_map.get(task_id, set())
        return [self._tasks[d] for d in deps if d in self._tasks]
    
    def is_complete(self) -> bool:
        terminal_states = {TaskStatus.PASSED, TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.BLOCKED}
        return all(task.status in terminal_states for task in self._tasks.values())
    
    def has_failures(self) -> bool:
        return any(task.status == TaskStatus.FAILED for task in self._tasks.values())
    
    def get_failed_tasks(self) -> list[AgentTask]:
        return [task for task in self._tasks.values() if task.status == TaskStatus.FAILED]
    
    def get_running_tasks(self) -> list[AgentTask]:
        return [task for task in self._tasks.values() if task.status == TaskStatus.RUNNING]
    
    def get_stats(self) -> dict:
        stats = {
            "total": len(self._tasks),
            "created": 0,
            "queued": 0,
            "running": 0,
            "passed": 0,
            "completed": 0,
            "failed": 0,
            "blocked": 0,
            "invalidated": len(self._invalidated),
        }
        for task in self._tasks.values():
            status = task.status if isinstance(task.status, TaskStatus) else TaskStatus(task.status)
            if status == TaskStatus.CREATED:
                stats["created"] += 1
            elif status == TaskStatus.QUEUED:
                stats["queued"] += 1
            elif status == TaskStatus.RUNNING:
                stats["running"] += 1
            elif status == TaskStatus.PASSED:
                stats["passed"] += 1
            elif status == TaskStatus.COMPLETED:
                stats["completed"] += 1
            elif status == TaskStatus.FAILED:
                stats["failed"] += 1
            elif status == TaskStatus.BLOCKED:
                stats["blocked"] += 1
        return stats
    
    @property
    def ownership(self) -> FileOwnershipRegistry:
        return self._ownership
    
    def to_dict(self) -> dict:
        return {
            "tasks": {task_id: task.to_dict() for task_id, task in self._tasks.items()},
            "dependencies": {task_id: list(deps) for task_id, deps in self._dependency_map.items()},
            "ownership": self._ownership.to_dict(),
            "invalidated": list(self._invalidated),
            "completed_at": self._completed_at,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'TaskGraph':
        graph = cls()
        for task_id, task_data in data.get("tasks", {}).items():
            task = AgentTask(
                id=task_data["id"],
                type=task_data["type"],
                project_id=task_data["project_id"],
                inputs=task_data.get("inputs", {}),
                constraints=task_data.get("constraints", {}),
                context=task_data.get("context", {}),
                created_at=task_data.get("created_at", ""),
                assigned_agent=task_data.get("assigned_agent", ""),
                parent_task_id=task_data.get("parent_task_id"),
                depends_on=task_data.get("depends_on", []),
                acceptance_criteria=task_data.get("acceptance_criteria", []),
                expected_artifacts=task_data.get("expected_artifacts", []),
                status=TaskStatus(task_data.get("status", "CREATED")),
                result=task_data.get("result", {}),
                error=task_data.get("error", ""),
            )
            graph.add_task(task)
        
        if "ownership" in data:
            graph._ownership = FileOwnershipRegistry.from_dict(data["ownership"])
        if "invalidated" in data:
            graph._invalidated = set(data["invalidated"])
        if "completed_at" in data:
            graph._completed_at = data["completed_at"]
        
        return graph
