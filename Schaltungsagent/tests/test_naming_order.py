"""Tests for naming resolution order (AP4, R5)."""
from unittest.mock import Mock, MagicMock

import pytest

from src.services.name_resolver import NameResolver
from src.services.plan_service import PlanValidator
from src.services.ollama_gateway import CodeGuard


class MockNamingLLM:
    """Mock naming LLM that returns predefined suggestions."""
    def __init__(self, suggestions: dict[str, str]):
        self._suggestions = suggestions
    
    def suggest_names(self, request_full: str, missing: set[str], hints: dict) -> dict[str, str]:
        return {k: v for k, v in self._suggestions.items() if k in missing}


def test_opencode_names_used_directly():
    """Valid names from OpenCode manifest are used without Ollama."""
    resolver = NameResolver(naming_llm=None)
    
    manifest = {
        "project_name": "ampel-steuerung",
        "modules": [
            {"entity": "timer", "file": "src/timer.vhd", "role": "Zeitgeber", "depends_on": []},
            {"entity": "control", "file": "src/control.vhd", "role": "Steuerwerk", "depends_on": ["timer"]},
            {"entity": "ampel", "file": "src/ampel.vhd", "role": "Top-Level", "depends_on": ["control", "timer"]},
        ],
        "top_entity": "ampel",
        "testbenches": [{"entity": "ampel_tb", "file": "tests/ampel_tb.vhd", "dut": "ampel"}],
    }
    
    result = resolver.resolve("any request", manifest)
    
    assert result.project_name == "ampel-steuerung"
    assert result.module_entities == ["timer", "control", "ampel"]
    assert result.unresolved == []


def test_missing_project_name_asks_ollama():
    """Missing project_name triggers Ollama naming."""
    naming_llm = MockNamingLLM({"project_name": "my-ampel"})
    resolver = NameResolver(naming_llm=naming_llm)
    
    manifest = {
        "project_name": "",  # Invalid
        "modules": [
            {"entity": "timer", "file": "src/timer.vhd", "role": "", "depends_on": []},
        ],
        "top_entity": "timer",
    }
    
    result = resolver.resolve("ampel request", manifest)
    
    assert result.project_name == "my-ampel"
    assert result.unresolved == []


def test_ollama_suggestion_invalid_falls_back_to_rules():
    """Invalid Ollama suggestion falls back to rule-based naming."""
    # Ollama returns invalid name (VHDL keyword)
    naming_llm = MockNamingLLM({"project_name": "entity"})  # VHDL keyword
    resolver = NameResolver(naming_llm=naming_llm)
    
    manifest = {
        "project_name": "",
        "modules": [
            {"entity": "timer", "file": "src/timer.vhd", "role": "", "depends_on": []},
        ],
        "top_entity": "timer",
    }
    
    result = resolver.resolve("ampel request", manifest)
    
    # Should fall back to topic-based name
    assert result.project_name == "ampel"
    assert result.unresolved == []


def test_ollama_returns_code_rejected():
    """Ollama returning VHDL code is rejected by CodeGuard."""
    naming_llm = MockNamingLLM({"project_name": "entity test is end;"})  # VHDL code
    resolver = NameResolver(naming_llm=naming_llm)
    
    manifest = {
        "project_name": "",
        "modules": [{"entity": "timer", "file": "src/timer.vhd", "role": "", "depends_on": []}],
        "top_entity": "timer",
    }
    
    result = resolver.resolve("ampel request", manifest)
    
    # CodeGuard rejects, falls back to rules
    assert result.project_name == "ampel"
    assert result.unresolved == []


def test_rules_find_nothing_returns_blocked():
    """When rules find nothing, returns BLOCKED_NEEDS_NAME."""
    # Request with no recognizable topic
    naming_llm = MockNamingLLM({})  # Ollama returns nothing
    resolver = NameResolver(naming_llm=naming_llm)
    
    manifest = {
        "project_name": "",
        "modules": [{"entity": "invalid-name!", "file": "src/x.vhd", "role": "", "depends_on": []}],
        "top_entity": "invalid-name!",
    }
    
    result = resolver.resolve("some completely unknown request xyz", manifest)
    
    assert result.project_name is None
    assert "project_name" in result.unresolved


def test_ampel_prompt_never_generic_names():
    """Ampel prompt never produces 'aufgabe-5-...' or 'fpga' names."""
    naming_llm = MockNamingLLM({})
    resolver = NameResolver(naming_llm=naming_llm)
    
    # Manifest with invalid names from bad OpenCode output
    manifest = {
        "project_name": "aufgabe-5-erstelle-die-vhdl",
        "modules": [
            {"entity": "fpga", "file": "src/fpga.vhd", "role": "", "depends_on": []},
        ],
        "top_entity": "fpga",
    }
    
    result = resolver.resolve(AMP_PROMPT, manifest)
    
    # Should resolve to proper names
    assert result.project_name == "ampel"
    assert result.module_entities == ["ampel"]
    assert "fpga" not in result.module_entities
    assert "aufgabe" not in result.project_name


def test_module_entity_validation():
    """Module entities validated against VHDL keywords and blocklist."""
    resolver = NameResolver(naming_llm=None)
    
    # Test various invalid entity names
    invalid_names = [
        "entity",      # VHDL keyword
        "my_component",  # Blocklist
        "top",         # Blocklist
        "uart",        # Reserved for UART template
        "123invalid",  # Starts with digit
        "UPPERCASE",   # Not lowercase
        "with-dash",   # No dashes in entity
    ]
    
    for name in invalid_names:
        assert not PlanValidator.valid_entity(name), f"'{name}' should be invalid"
    
    # Valid names
    valid_names = ["timer", "control", "ampel", "counter_4bit", "uart_tx", "my_module"]
    for name in valid_names:
        assert PlanValidator.valid_entity(name), f"'{name}' should be valid"


def test_project_name_validation():
    """Project names validated against pattern and forbidden prefixes."""
    valid = ["ampel-steuerung", "counter-4bit", "my-project", "uart-tx"]
    for name in valid:
        assert PlanValidator.valid_project_name(name), f"'{name}' should be valid"
    
    invalid = [
        "aufgabe-5",      # Forbidden prefix
        "task-1",         # Forbidden prefix
        "prompt-xyz",     # Forbidden prefix
        "fpga-design",    # Forbidden prefix
        "vhdl-code",      # Forbidden prefix
        "projekt",        # Forbidden prefix
        "MyProject",      # Not lowercase
        "a",              # Too short
        "a" * 41,         # Too long
    ]
    for name in invalid:
        assert not PlanValidator.valid_project_name(name), f"'{name}' should be invalid"


AMP_PROMPT = """Erstelle eine hierarchische Ampelsteuerung für ein FPGA-Board (Arty S7-50).
Die Ampel soll folgende Funktionen haben:
- Hauptstraße: 30 Sekunden Grün, 4 Sekunden Gelb
- Nebenstraße: 30 Sekunden Grün, 4 Sekunden Gelb
- 6 LEDs: 2x Rot, 2x Gelb, 2x Grün
- Taktfrequenz: 50 MHz
- Asynchroner Reset (active high)

Module:
1. timer: generischer Timer mit Enable
2. control: Moore-Automat für die Ampel-Logik
3. ampel: Top-Level, instanziiert timer und control

Entity-Namen: timer, control, ampel
Dateien: src/timer.vhd, src/control.vhd, src/ampel.vhd
Testbench: tests/ampel_tb.vhd für das Top-Level
"""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])