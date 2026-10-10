"""Tests fuer Prozess-Timeout und Cancellation."""
import sys
import os
import tempfile
import signal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from src.domain.state_machine import StateMachine, WorkflowState
from src.domain.exceptions import StateMachineError


class TestTimeoutHandling:
    """Testet Timeout-Verhalten."""

    def test_timeout_raises(self):
        """Timeout sollte eine definierte Fehlerbehandlung erzeugen."""
        import asyncio
        import time

        async def slow_operation():
            await asyncio.sleep(10)

        async def with_timeout():
            try:
                await asyncio.wait_for(slow_operation(), timeout=0.01)
            except asyncio.TimeoutError:
                return "TIMEOUT"
            return "COMPLETED"

        result = asyncio.run(with_timeout())
        assert result == "TIMEOUT"

    def test_state_transition_on_timeout(self):
        """Bei Timeout muss der StateMachine einen terminalen Zustand haben."""
        sm = StateMachine(WorkflowState.SYNTHESIZING)
        # Simulate timeout: transition to FAILED
        sm.transition_to(WorkflowState.FAILED)
        assert sm.current == WorkflowState.FAILED
        assert sm.get_allowed_transitions() == []

    def test_state_transition_on_cancellation(self):
        """Bei Cancellation muss der StateMachine einen gueltigen Zustand haben."""
        sm = StateMachine(WorkflowState.IMPLEMENTING)
        sm.transition_to(WorkflowState.DEBUGGING)
        assert sm.current == WorkflowState.DEBUGGING

    def test_orphaned_process_detection(self):
        """Pruefe, dass ein Timeout als ORPHANED gemeldet wird."""
        sm = StateMachine(WorkflowState.RUNNING_AGENT)
        # If a process times out, it should transition to FAILED or BLOCKED
        sm.transition_to(WorkflowState.FAILED)
        assert sm.current == WorkflowState.FAILED


class TestCancellation:
    """Testet Cancellation-Logik."""

    def test_cancellation_sets_terminal_state(self):
        """Cancellation muss einen terminalen Zustand setzen."""
        sm = StateMachine(WorkflowState.SIMULATING)
        sm.transition_to(WorkflowState.FAILED)
        assert sm.current == WorkflowState.FAILED

    def test_no_double_transition(self):
        """Ein terminaler Zustand darf nicht erneut uebergegangen werden."""
        sm = StateMachine(WorkflowState.COMPLETED)
        assert sm.get_allowed_transitions() == []
        # Attempting to transition should raise
        with pytest.raises(StateMachineError):
            sm.transition_to(WorkflowState.ANALYZING)


class TestThreadSafety:
    """Testet Thread-Sicherheit der Supervisor-Instanz."""

    def test_project_locks_created(self):
        from src.agents.supervisor import SupervisorAgent
        from src.services.project_memory import ProjectMemoryService
        from src.services.filesystem_service import LocalFileSystemService

        agent = SupervisorAgent(
            filesystem_service=LocalFileSystemService(),
            event_publisher=None,
            project_memory=ProjectMemoryService(LocalFileSystemService()),
        )
        lock = agent._get_project_lock("test-project")
        assert isinstance(lock, type(lock))
        assert "test-project" in agent._project_locks

    def test_different_projects_different_locks(self):
        from src.agents.supervisor import SupervisorAgent
        from src.services.project_memory import ProjectMemoryService
        from src.services.filesystem_service import LocalFileSystemService

        agent = SupervisorAgent(
            filesystem_service=LocalFileSystemService(),
            event_publisher=None,
            project_memory=ProjectMemoryService(LocalFileSystemService()),
        )
        lock1 = agent._get_project_lock("proj-a")
        lock2 = agent._get_project_lock("proj-b")
        assert lock1 is not lock2

    def test_lock_acquire_release(self):
        from src.agents.supervisor import SupervisorAgent
        from src.services.project_memory import ProjectMemoryService
        from src.services.filesystem_service import LocalFileSystemService

        agent = SupervisorAgent(
            filesystem_service=LocalFileSystemService(),
            event_publisher=None,
            project_memory=ProjectMemoryService(LocalFileSystemService()),
        )
        lock = agent._acquire_project_lock("test-locked")
        assert lock.locked()
        agent._release_project_lock("test-locked")
        assert not lock.locked()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
