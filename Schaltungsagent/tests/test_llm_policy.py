"""Tests for LLM policy enforcement (AP1, R1-R2)."""
import ast
import os
from pathlib import Path

import pytest


def test_no_llm_in_pipeline_agents():
    """Pipeline agents must not import or use LLM services."""
    forbidden_imports = {
        "llm_service",
        "LLMService",
        "OllamaGateway",
        "create_llm_clients",
    }
    forbidden_calls = {
        "generate_text",
        "analyze_request",
        "summarize_result",
    }
    
    pipeline_agent_files = [
        "src/agents/architecture.py",
        "src/agents/hdl.py",
        "src/agents/verification.py",
        "src/agents/debug.py",
        "src/agents/fpga.py",
        "src/agents/hardware_test.py",
        "src/agents/supervisor.py",
        "src/orchestrator/agent_factory.py",
        "src/orchestrator/supervisor_orchestrator.py",
    ]
    
    base = Path(__file__).resolve().parents[1] / "Schaltungsagent"
    
    for rel_path in pipeline_agent_files:
        file_path = base / rel_path
        if not file_path.exists():
            continue
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content)
        
        for node in ast.walk(tree):
            # Check imports
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name not in forbidden_imports, \
                        f"{rel_path}: forbidden import {alias.name}"
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    assert node.module not in forbidden_imports, \
                        f"{rel_path}: forbidden import from {node.module}"
            
            # Check calls
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    assert node.func.attr not in forbidden_calls, \
                        f"{rel_path}: forbidden call {node.func.attr}"
                elif isinstance(node.func, ast.Name):
                    assert node.func.id not in forbidden_calls, \
                        f"{rel_path}: forbidden call {node.func.id}"


def test_ollama_gateway_forbidden_purpose():
    """OllamaGateway.invoke must reject purposes other than CHAT/NAMING."""
    from src.services.ollama_gateway import OllamaGateway, ForbiddenLLMUseError, LLMPurpose
    
    gateway = OllamaGateway(
        primary=None,  # Use mock
        fallback=None,
        event_publisher=None,
    )
    
    # Valid purposes should not raise ForbiddenLLMUseError at validation time
    # (they'll fail at invoke time due to missing client, but that's OK)
    for purpose in [LLMPurpose.CHAT, LLMPurpose.NAMING]:
        try:
            gateway.invoke(purpose, "test prompt", task_id="test")
        except ForbiddenLLMUseError:
            pytest.fail(f"Valid purpose {purpose} raised ForbiddenLLMUseError")
        except Exception:
            pass  # Expected: client not configured
    
    # Invalid purpose must raise ForbiddenLLMUseError immediately
    with pytest.raises(ForbiddenLLMUseError):
        gateway.invoke("CODE_GENERATION", "test prompt", task_id="test")
    with pytest.raises(ForbiddenLLMUseError):
        gateway.invoke("ARCHITECTURE", "test prompt", task_id="test")
    with pytest.raises(ForbiddenLLMUseError):
        gateway.invoke("DEBUG", "test prompt", task_id="test")


def test_code_guard_rejects_vhdl_in_chat():
    """CodeGuard must detect VHDL in Ollama responses."""
    from src.services.ollama_gateway import CodeGuard
    
    vhdl_responses = [
        "```vhdl\nentity test is\nend;\n```",
        "entity my_entity is\n  port (clk: in std_logic);\nend entity;",
        "architecture rtl of my_entity is\nbegin\nend architecture;",
        "library ieee;\nuse ieee.std_logic_1164.all;",
    ]
    
    for resp in vhdl_responses:
        assert CodeGuard.is_code(resp), f"Failed to detect VHDL in: {resp[:50]}"
    
    non_code = [
        "This is a chat response about the project.",
        "The module should have a clock and reset.",
        "No code here, just explanation.",
    ]
    
    for resp in non_code:
        assert not CodeGuard.is_code(resp), f"False positive for: {resp}"


def test_supervisor_no_llm_attribute():
    """SupervisorAgent must not have an LLM attribute."""
    from src.agents.supervisor import SupervisorAgent
    from src.domain.event_bus import EventBus
    
    class MockFS:
        def workspace_path(self, pid): return f"/tmp/{pid}"
        def file_exists(self, p): return False
        def read_file(self, p): return ""
        def write_file(self, p, c): pass
    
    supervisor = SupervisorAgent(
        filesystem_service=MockFS(),
        event_publisher=EventBus(),
        project_memory=None,
        architecture_agent=None,
        hdl_agent=None,
        verification_agent=None,
        debug_agent=None,
        fpga_agent=None,
        hardware_test_agent=None,
    )
    
    # Should not have llm_service or similar
    assert not hasattr(supervisor, "_llm"), "SupervisorAgent has _llm attribute"
    assert not hasattr(supervisor, "llm_service"), "SupervisorAgent has llm_service attribute"


def test_agent_factory_no_llm_passed():
    """agent_factory.build_supervisor_agent must not pass llm_service to agents."""
    import inspect
    from src.orchestrator.agent_factory import build_supervisor_agent
    
    sig = inspect.signature(build_supervisor_agent)
    params = list(sig.parameters.keys())
    
    # Should not have llm_service parameter
    assert "llm_service" not in params, "build_supervisor_agent has llm_service parameter"
    
    # Check source for llm_service usage
    source = inspect.getsource(build_supervisor_agent)
    assert "llm_service" not in source, "build_supervisor_agent uses llm_service internally"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])