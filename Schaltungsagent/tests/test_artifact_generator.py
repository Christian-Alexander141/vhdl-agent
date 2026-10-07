from src.services.artifact_generator import VHDLArtifactGenerator


def test_counter_fallback_creates_source_and_testbench():
    result = VHDLArtifactGenerator().generate("Create an 8-bit counter", "")

    assert result.status == "fallback"
    assert len(result.files) == 2

    source = next(file for file in result.files if file.path.startswith("src/"))
    testbench = next(file for file in result.files if file.path.startswith("tests/"))

    assert "entity counter" in source.content.lower()
    assert "architecture" in source.content.lower()
    assert "TB_COMPLETE" in testbench.content


def test_unknown_request_fallback_still_returns_artifacts():
    result = VHDLArtifactGenerator().generate("Build a custom SPI master", "")

    assert result.status == "fallback"
    assert len(result.files) == 2
    assert all(file.content.strip() for file in result.files)
