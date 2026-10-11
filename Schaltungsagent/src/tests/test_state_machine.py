"""Tests für die verbindliche Zustandsmaschine und DesignState-Konsistenz."""
import sys
import os
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from src.domain.state_machine import StateMachine, WorkflowState, TRANSITIONS
from src.domain.models import DesignState, DesignStage
from src.domain.exceptions import StateMachineError


class TestStateMachine:
    """Testet die StateMachine mit validierten Uebergängen."""

    def test_initial_state(self):
        sm = StateMachine(WorkflowState.CREATED)
        assert sm.current == WorkflowState.CREATED

    def test_valid_transition(self):
        sm = StateMachine(WorkflowState.CREATED)
        sm.transition_to(WorkflowState.ANALYZING)
        assert sm.current == WorkflowState.ANALYZING

    def test_invalid_transition_raises(self):
        sm = StateMachine(WorkflowState.CREATED)
        with pytest.raises(StateMachineError):
            sm.transition_to(WorkflowState.COMPLETED)

    def test_can_transition_to(self):
        sm = StateMachine(WorkflowState.ANALYZING)
        assert sm.can_transition_to(WorkflowState.ARCHITECTING)
        assert not sm.can_transition_to(WorkflowState.COMPLETED)

    def test_infrastructure_failure_in_debugging(self):
        sm = StateMachine(WorkflowState.DEBUGGING)
        assert WorkflowState.INFRASTRUCTURE_FAILURE in sm.get_allowed_transitions()

    def test_flash_failure_goes_to_debugging_without_approval(self):
        # Benutzerfreigabe vor dem Flashen entfernt (2026-10-11).
        sm = StateMachine(WorkflowState.FPGA_PROGRAMMING)
        assert WorkflowState.DEBUGGING in sm.get_allowed_transitions()
        assert not hasattr(WorkflowState, "AWAITING_APPROVAL")

    def test_same_state_no_error(self):
        sm = StateMachine(WorkflowState.COMPLETED)
        sm.transition_to(WorkflowState.COMPLETED)
        assert sm.current == WorkflowState.COMPLETED

    def test_get_allowed_transitions(self):
        sm = StateMachine(WorkflowState.DEBUGGING)
        allowed = sm.get_allowed_transitions()
        assert WorkflowState.ARCHITECTING in allowed
        assert WorkflowState.IMPLEMENTING in allowed
        assert WorkflowState.FAILED in allowed

    def test_is_valid_transition_classmethod(self):
        assert StateMachine.is_valid_transition(WorkflowState.CREATED, WorkflowState.ANALYZING)
        assert StateMachine.is_valid_transition(WorkflowState.CREATED, WorkflowState.FAILED)
        assert not StateMachine.is_valid_transition(WorkflowState.COMPLETED, WorkflowState.ANALYZING)

    def test_all_new_states_have_transitions(self):
        new_states = [
            WorkflowState.ARCHITECTING, WorkflowState.UART_INTEGRATION,
            WorkflowState.IMPLEMENTING,
            WorkflowState.STATIC_CHECK, WorkflowState.SIMULATING,
            WorkflowState.DEBUGGING, WorkflowState.FPGA_PROGRAMMING,
            WorkflowState.HARDWARE_TESTING, WorkflowState.AUTONOMOUS_LIMIT_REACHED,
            WorkflowState.INFRASTRUCTURE_FAILURE, WorkflowState.BLOCKED, WorkflowState.SKIPPED,
        ]
        for state in new_states:
            assert state in TRANSITIONS, f"{state} missing from TRANSITIONS"

    def test_terminal_states_have_no_outgoing(self):
        for terminal in [WorkflowState.FAILED, WorkflowState.AUTONOMOUS_LIMIT_REACHED, WorkflowState.INFRASTRUCTURE_FAILURE]:
            sm = StateMachine(terminal)
            assert sm.get_allowed_transitions() == []

    def test_completed_can_resume_for_hardware_revision(self):
        sm = StateMachine(WorkflowState.COMPLETED)
        assert sm.can_transition_to(WorkflowState.IMPLEMENTING)


class TestDesignStateConsistency:
    """Testet DesignState.transition_to() mit StateMachine-Validierung."""

    def test_design_state_valid_transition(self):
        ds = DesignState()
        ds.project["id"] = "test-project"
        ds.transition_to(DesignStage.ANALYZING)
        assert ds.current_stage == DesignStage.ANALYZING
        ds.transition_to(DesignStage.ARCHITECTING)
        assert ds.current_stage == DesignStage.ARCHITECTING
        ds.transition_to(DesignStage.UART_INTEGRATION)
        assert ds.current_stage == DesignStage.UART_INTEGRATION
        ds.transition_to(DesignStage.IMPLEMENTING)
        assert ds.current_stage == DesignStage.IMPLEMENTING

    def test_design_state_invalid_transition_raises(self):
        ds = DesignState()
        ds.project["id"] = "test-project"
        with pytest.raises(StateMachineError):
            ds.transition_to(DesignStage.COMPLETED)

    def test_design_state_machine_sync(self):
        ds = DesignState()
        ds.project["id"] = "test-project"
        sm = StateMachine(ds.current_stage.value)
        ds.transition_to(DesignStage.ANALYZING)
        assert ds.current_stage == DesignStage.ANALYZING
        ds.transition_to(DesignStage.ARCHITECTING)
        assert ds.current_stage == DesignStage.ARCHITECTING

    def test_design_state_persists_updated_at(self):
        ds = DesignState()
        ds.project["id"] = "test-project"
        ds.transition_to(DesignStage.ANALYZING)
        ds.transition_to(DesignStage.ARCHITECTING)
        assert ds.project["updated_at"] != ""

    def test_design_state_cannot_skip_stage(self):
        ds = DesignState()
        ds.project["id"] = "test-project"
        with pytest.raises(StateMachineError):
            ds.transition_to(DesignStage.FPGA_PROGRAMMING)
        ds.current_stage = DesignStage.ARCHITECTING
        with pytest.raises(StateMachineError):
            ds.transition_to(DesignStage.IMPLEMENTING)


class TestStateMachineResume:
    """Testet die Resume-Logik nach Prozessneustart."""

    def test_resume_from_persisted_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ds = DesignState()
            ds.project["id"] = "resume-test"
            ds.transition_to(DesignStage.ANALYZING)
            yaml_str = ds.to_yaml()
            ds2 = DesignState.from_yaml(yaml_str)
            assert ds2.current_stage == DesignStage.ANALYZING
            assert ds2.project["id"] == "resume-test"

    def test_resume_with_state_machine(self):
        ds = DesignState()
        ds.project["id"] = "resume-test-2"
        ds.transition_to(DesignStage.ANALYZING)
        ds.transition_to(DesignStage.ARCHITECTING)
        ds.transition_to(DesignStage.UART_INTEGRATION)
        ds.transition_to(DesignStage.IMPLEMENTING)
        ds.transition_to(DesignStage.STATIC_CHECK)
        ds.transition_to(DesignStage.SIMULATING)
        sm = StateMachine(ds.current_stage.value)
        assert sm.current == WorkflowState.SIMULATING
        assert sm.can_transition_to(WorkflowState.VALIDATING)
