from src.services.design_fallback import RuleBasedFallback
from src.services.deterministic_design import DeterministicDesignService
from src.services.artifact_generator import VHDLArtifactGenerator


def test_long_ampel_request_has_no_rule_fallback():
    fallback = RuleBasedFallback()
    request = "Ampelsteuerung mit timer und control " + "Zählerwerte " * 100

    assert fallback.module_vhdl(request, "fpga") is None
    assert fallback.testbench_vhdl(request, "fpga") is None


def test_ambiguous_patterns_have_no_rule_fallback():
    fallback = RuleBasedFallback()

    assert fallback.module_vhdl("Lauflicht und Zähler", "counter") is None


def test_single_template_must_match_requested_entity():
    design = DeterministicDesignService()

    assert design.module_vhdl("4-bit counter", "", "wrong_entity") is None


def test_entity_name_extractor_does_not_take_fpga_from_board_phrase():
    name = VHDLArtifactGenerator._extract_entity_name(
        "Erstelle die Schaltung für mein FPGA-Board Digilent Arty S7",
        "my_component",
    )

    assert name != "fpga"