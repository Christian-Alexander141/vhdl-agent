"""Orchestrator ohne Benutzerfreigabe vor dem Flashen (entfernt 2026-10-11)."""
import inspect

from src.domain.models import EventType
from src.orchestrator.supervisor_orchestrator import SupervisorOrchestrator


def test_orchestrator_has_no_approval_api():
    assert not hasattr(SupervisorOrchestrator, "approve_task")
    assert not hasattr(SupervisorOrchestrator, "reject_task")
    assert "require_approval" not in inspect.signature(SupervisorOrchestrator.__init__).parameters


def test_no_approval_events_remain():
    assert not any(name.startswith("APPROVAL") for name in EventType.__members__)
