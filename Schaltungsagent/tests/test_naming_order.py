"""Namensvergabe: OpenCode legt Namen im Plan fest, der Resolver bereinigt sie nur.

Früher fragte der Resolver ein separates Ollama-LLM und blockierte den Lauf,
wenn das nicht antwortete (BLOCKED_NEEDS_NAME). Ollama ist entfernt; ein Lauf
scheitert nicht mehr an der Namensvergabe.
"""
from src.services.name_resolver import NameResolver, normalize_entity, normalize_project_name
from src.services.plan_service import PlanValidator

AMPEL_MANIFEST = {
    "project_name": "ampel-steuerung",
    "modules": [
        {"entity": "timer", "file": "src/timer.vhd", "role": "Zeitgeber", "depends_on": []},
        {"entity": "control", "file": "src/control.vhd", "role": "Steuerwerk", "depends_on": ["timer"]},
        {"entity": "ampel", "file": "src/ampel.vhd", "role": "Top-Level", "depends_on": ["control", "timer"]},
    ],
    "top_entity": "ampel",
    "testbenches": [{"entity": "ampel_tb", "file": "tests/ampel_tb.vhd", "dut": "ampel"}],
}


def test_opencode_names_used_directly():
    result = NameResolver().resolve("beliebige Anforderung", AMPEL_MANIFEST)
    assert result.project_name == "ampel-steuerung"
    assert result.module_entities == ["timer", "control", "ampel"]
    assert result.unresolved == []


def test_invalid_project_name_from_opencode_is_cleaned_not_blocked():
    """Benchmark 20261010-091252, Muse/task04: Lauf scheiterte an BLOCKED_NEEDS_NAME."""
    manifest = {**AMPEL_MANIFEST, "project_name": "task04-sram"}
    result = NameResolver().resolve("Aufgabe task04 – SRAM", manifest)
    assert result.project_name == "sram" and result.unresolved == []


def test_unusable_project_name_falls_back_to_top_entity_then_hash():
    manifest = {**AMPEL_MANIFEST, "project_name": "fpga"}
    assert NameResolver().resolve("x", manifest).project_name == "ampel"
    empty = {"project_name": "", "modules": [], "top_entity": ""}
    name = NameResolver().resolve("", empty).project_name
    assert name.startswith("design-") and PlanValidator.valid_project_name(name)


def test_invalid_entities_are_cleaned_and_references_follow():
    manifest = {
        "project_name": "sram-ctrl",
        "top_entity": "SRAM Top",
        "modules": [
            {"entity": "SRAM Top", "depends_on": ["Mem-Cell"]},
            {"entity": "Mem-Cell", "depends_on": []},
        ],
        "testbenches": [{"dut": "SRAM Top"}],
    }
    result = NameResolver().resolve("x", manifest)
    assert result.module_entities == ["sram_top", "mem_cell"]
    assert result.manifest["top_entity"] == "sram_top"
    assert result.manifest["modules"][0]["depends_on"] == ["mem_cell"]
    assert result.manifest["testbenches"][0] == {"dut": "sram_top", "entity": "sram_top_tb", "file": "tests/sram_top_tb.vhd"}


def test_duplicate_entities_after_cleaning_get_unique_names():
    manifest = {"project_name": "dup-test", "modules": [{"entity": "Timer"}, {"entity": "timer!"}], "top_entity": "Timer"}
    assert NameResolver().resolve("x", manifest).module_entities == ["timer", "timer_2"]


def test_normalizers():
    assert normalize_project_name("Aufgabe 5: Ampelsteuerung") == "ampelsteuerung"
    assert normalize_project_name("4bit-adder") == "p-4bit-adder"
    assert normalize_project_name("vhdl-fpga") == ""
    assert normalize_entity("Ampel Steuerung") == "ampel_steuerung"
    assert normalize_entity("entity") == ""          # VHDL-Schlüsselwort
    assert normalize_entity("3er_zaehler") == "m_3er_zaehler"


def test_module_entity_validation():
    for name in ("entity", "signal", "uart", "123invalid", "UPPERCASE", "with-dash"):
        assert not PlanValidator.valid_entity(name), name
    # Gängige Namen, die Prompts verlangen können, sind zulässig (früher gesperrt).
    for name in ("timer", "control", "ampel", "counter_4bit", "uart_tx", "alu", "top", "design"):
        assert PlanValidator.valid_entity(name), name


def test_project_name_validation():
    for name in ("ampel-steuerung", "counter-4bit", "my-project", "uart-tx"):
        assert PlanValidator.valid_project_name(name), name
    for name in ("aufgabe-5", "task-1", "prompt-xyz", "fpga-design", "vhdl-code", "projekt", "MyProject", "a", "a" * 41):
        assert not PlanValidator.valid_project_name(name), name
