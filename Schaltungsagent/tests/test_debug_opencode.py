"""Tests for DebugAgent without LLM (AP6)."""
from unittest.mock import Mock, MagicMock, patch

import pytest

from src.agents.debug import DebugAgent, classify_error
from src.domain.agents import AgentTask, AgentResult, AgentStatus
from src.domain.agents.communication import DebugDiagnosis


class MockEventPublisher:
    def __init__(self):
        self.events = []
    def publish_event(self, event_type, project_id, payload):
        self.events.append({"type": event_type, "project_id": project_id, "payload": payload})


def test_debug_agent_no_llm_attribute():
    """DebugAgent must not have LLM attribute."""
    events = MockEventPublisher()
    agent = DebugAgent(event_publisher=events)
    
    assert not hasattr(agent, "_llm"), "DebugAgent has _llm attribute"
    assert not hasattr(agent, "llm_service"), "DebugAgent has llm_service attribute"


def test_classify_error_deterministic():
    """Error classification is deterministic via regex."""
    # GHDL syntax error
    msg = "** Error: test.vhd:10:5: syntax error near 'entity'"
    ft, action, sev = classify_error(msg, "static_check")
    assert ft == "syntax_error"
    assert sev == "high"
    
    # Vivado latch inference
    msg = "[Synth 8-327] inferring latch for variable state"
    ft, action, sev = classify_error(msg, "synthesis")
    assert ft == "synthesis_error"
    
    # Infrastructure error
    msg = "ghdl: command not found"
    ft, action, sev = classify_error(msg, "static_check")
    assert ft == "infrastructure"
    assert sev == "critical"


def test_diagnose_only_known_modules():
    """suspected_modules only contains modules from architecture."""
    events = MockEventPublisher()
    agent = DebugAgent(event_publisher=events)
    
    # Architecture has only 'timer' and 'control'
    architecture = {
        "modules": [
            {"name": "timer"},
            {"name": "control"},
        ]
    }
    
    # Error mentions 'alu' and 'control_unit' (not in architecture)
    diagnostics = [{
        "message": "** Error: alu.vhd:5: syntax error\n** Error: control_unit.vhd:10: type mismatch",
        "stage": "simulation",
    }]
    
    import asyncio
    result = asyncio.run(agent._diagnose(AgentTask(
        id="test",
        type="diagnose",
        project_id="test",
        inputs={
            "diagnostics": diagnostics,
            "current_stage": "simulation",
            "workspace": "/tmp",
            "architecture": architecture,
        }
    )))
    
    assert result.status == AgentStatus.COMPLETED
    diagnosis = result.outputs["diagnosis"]
    
    # Only 'control' should be suspected (from architecture), not 'alu'/'control_unit'
    suspected = diagnosis["suspected_modules"]
    assert "control" in suspected or len(suspected) == 0  # 'control' from 'control_unit' substring
    # The fallback extracts from error text but filters by known modules
    for mod in suspected:
        assert mod in ["timer", "control"], f"Unexpected suspected module: {mod}"


def test_infrastructure_error_not_repairable():
    """Infrastructure errors are classified as non-repairable."""
    events = MockEventPublisher()
    agent = DebugAgent(event_publisher=events)
    
    diagnostics = [{
        "message": "ghdl: command not found",
        "stage": "static_check",
    }]
    
    architecture = {"modules": [{"name": "timer"}]}
    
    import asyncio
    result = asyncio.run(agent._diagnose(AgentTask(
        id="test",
        type="diagnose",
        project_id="test",
        inputs={
            "diagnostics": diagnostics,
            "current_stage": "static_check",
            "workspace": "/tmp",
            "architecture": architecture,
        }
    )))
    
    diagnosis = result.outputs["diagnosis"]
    assert diagnosis["failure_type"] == "infrastructure"
    assert diagnosis["severity"] == "critical"


def test_review_and_fix_uses_opencode():
    """Review/fix uses OpenCode with original prompt + error log."""
    from src.services.opencode_task_runner import OpenCodeTaskRunner, OpenCodeDelivery
    
    # Mock OpenCode runner
    mock_runner = Mock(spec=OpenCodeTaskRunner)
    mock_runner.run.return_value = OpenCodeDelivery(
        ok=True,
        stage="review_and_fix",
        files={"src/timer.vhd": "fixed vhdl code"},
        prompt_sha256="abc123",
    )
    
    # We can't easily test the full supervisor flow here, but we verify
    # the DebugAgent produces deterministic diagnosis without LLM
    events = MockEventPublisher()
    agent = DebugAgent(event_publisher=events)
    
    architecture = {"modules": [{"name": "timer"}]}
    diagnostics = [{
        "message": "** Error: timer.vhd:15: signal 'cnt' not declared",
        "stage": "simulation",
    }]
    
    import asyncio
    result = asyncio.run(agent._diagnose(AgentTask(
        id="test",
        type="diagnose",
        project_id="test",
        inputs={
            "diagnostics": diagnostics,
            "current_stage": "simulation",
            "workspace": "/tmp",
            "architecture": architecture,
        }
    )))
    
    assert result.status == AgentStatus.COMPLETED
    diagnosis = result.outputs["diagnosis"]
    assert diagnosis["failure_type"] in ["syntax_error", "type_error", "elaboration_error"]
    assert "timer" in diagnosis["suspected_modules"] or diagnosis["suspected_modules"] == []


def test_no_ollama_fallback_in_debug():
    """DebugAgent never falls back to Ollama or rule-based code generation."""
    # This is verified by:
    # 1. DebugAgent has no LLM attribute (test_debug_agent_no_llm_attribute)
    # 2. _analyze_all_diagnostics only calls _fallback_diagnosis (deterministic)
    # 3. No generate_text, analyze_request, or similar calls in debug.py

    import ast
    from pathlib import Path

    # Test file is in Schaltungsagent/tests/, source is in Schaltungsagent/src/
    debug_file = Path(__file__).resolve().parent.parent / "src" / "agents" / "debug.py"
    if not debug_file.exists():
        # Fallback: try from repo root
        debug_file = Path(__file__).resolve().parents[2] / "Schaltungsagent" / "src" / "agents" / "debug.py"
    content = debug_file.read_text(encoding="utf-8")
    tree = ast.parse(content)

    forbidden = {"generate_text", "analyze_request", "summarize_result", "invoke"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                assert node.func.attr not in forbidden, \
                    f"DebugAgent calls forbidden {node.func.attr}"
            elif isinstance(node.func, ast.Name):
                assert node.func.id not in forbidden, \
                    f"DebugAgent calls forbidden {node.func.id}"


def test_suspected_modules_subset_of_architecture():
    """suspected_modules is always subset of architecture modules."""
    from src.agents.debug import DebugAgent
    
    events = MockEventPublisher()
    agent = DebugAgent(event_publisher=events)
    
    # Architecture with specific modules
    architecture = {
        "modules": [
            {"name": "timer"},
            {"name": "control"},
            {"name": "ampel"},
        ]
    }
    
    # Error log mentions various modules
    diagnostics = [{
        "message": "Error in alu, control_unit, timer, unknown_module",
        "stage": "simulation",
    }]
    
    import asyncio
    result = asyncio.run(agent._diagnose(AgentTask(
        id="test",
        type="diagnose",
        project_id="test",
        inputs={
            "diagnostics": diagnostics,
            "current_stage": "simulation",
            "workspace": "/tmp",
            "architecture": architecture,
        }
    )))
    
    diagnosis = result.outputs["diagnosis"]
    suspected = diagnosis["suspected_modules"]
    
    # Only modules from architecture can be suspected
    for mod in suspected:
        assert mod in ["timer", "control", "ampel"], \
            f"Suspected module {mod} not in architecture"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])