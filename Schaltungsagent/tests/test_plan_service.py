from src.services.plan_service import PlanValidationError, PlanValidator


def test_plan_validator_accepts_consistent_manifest():
    manifest = {
        "project_name": "ampel-steuerung",
        "top_entity": "ampel",
        "modules": [
            {"entity": "timer", "file": "src/timer.vhd", "depends_on": []},
            {"entity": "ampel", "file": "src/ampel.vhd", "depends_on": ["timer"]},
        ],
        "testbenches": [{"entity": "ampel_tb", "file": "tests/ampel_tb.vhd", "dut": "ampel"}],
    }

    assert PlanValidator.validate(manifest) == []


def test_plan_validator_rejects_bad_path_and_dependency_cycle():
    manifest = {
        "project_name": "ampel-steuerung",
        "top_entity": "ampel",
        "modules": [
            {"entity": "timer", "file": "src/wrong.vhd", "depends_on": ["ampel"]},
            {"entity": "ampel", "file": "src/ampel.vhd", "depends_on": ["timer"]},
        ],
        "testbenches": [],
    }

    errors = PlanValidator.validate(manifest)

    assert any("file" in error.lower() for error in errors)
    assert any("cycle" in error.lower() for error in errors)


def test_plan_validator_rejects_missing_top_and_too_many_modules():
    manifest = {
        "project_name": "ampel-steuerung",
        "top_entity": "missing",
        "modules": [
            {"entity": f"module_{index}", "file": f"src/module_{index}.vhd", "depends_on": []}
            for index in range(13)
        ],
        "testbenches": [],
    }

    errors = PlanValidator.validate(manifest)

    assert any("top_entity" in error for error in errors)
    assert any("12" in error for error in errors)