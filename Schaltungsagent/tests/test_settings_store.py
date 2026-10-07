import yaml
import pytest

from src.config import load_config
from src.services.settings_store import (
    SettingsValidationError,
    apply_settings_update,
    editable_settings,
    persist_settings_update,
    restart_required,
)

CONFIG = """opencode:
  model: a/b
  skills_dir: .opencode/skills
  test_mode: false
limits:
  max_prompt_bytes: 1234
gates:
  min_module_coverage: 1.0
custom_section:
  keep: me
"""


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.delenv("VHDL_AGENT_TEST_MODE", raising=False)
    path = tmp_path / "config.yaml"
    path.write_text(CONFIG)
    return load_config(str(path)), path


def test_editable_settings_expose_execution_and_gates(setup):
    settings, _ = setup
    data = editable_settings(settings)
    assert data["opencode"]["docker_isolation"] == "per_task"
    assert data["gates"]["min_module_coverage"] == 1.0
    assert "opencode.docker_isolation" in data["_meta"]["choices"]


def test_update_persists_only_changed_fields_and_keeps_rest(setup):
    settings, path = setup
    changes = apply_settings_update(settings, {
        "opencode": {"test_mode": "true", "docker_isolation": "shared", "model": "a/b"},
        "limits": {"max_parallel_workers": "3"},
        "theme": "dark",  # altes Browser-Feld: ignoriert
    })
    persist_settings_update(path, changes)

    assert settings.opencode.test_mode is True
    assert settings.limits.max_parallel_workers == 3
    saved = yaml.safe_load(path.read_text())
    assert saved["opencode"]["test_mode"] is True
    assert saved["opencode"]["docker_isolation"] == "shared"
    assert saved["opencode"]["skills_dir"] == ".opencode/skills"
    assert saved["limits"] == {"max_prompt_bytes": 1234, "max_parallel_workers": 3}
    assert saved["custom_section"] == {"keep": "me"}
    assert restart_required(changes) == ["limits.max_parallel_workers"]


@pytest.mark.parametrize("payload", [
    {"opencode": {"docker_isolation": "everything"}},
    {"gates": {"min_module_coverage": 2}},
    {"limits": {"max_parallel_workers": "viele"}},
    {"opencode": {"no_such_field": 1}},
    {"dashboard": {"port": 1}},
])
def test_invalid_updates_are_rejected_atomically(setup, payload):
    settings, _ = setup
    before = editable_settings(settings)
    with pytest.raises(SettingsValidationError):
        apply_settings_update(settings, {"limits": {"max_parallel_workers": 4}, **payload})
    assert editable_settings(settings) == before


def test_environment_test_mode_is_not_persisted(setup, monkeypatch, tmp_path):
    _, path = setup
    monkeypatch.setenv("VHDL_AGENT_TEST_MODE", "1")
    settings = load_config(str(path))
    changes = apply_settings_update(settings, {"limits": {"max_parallel_workers": 2}})
    persist_settings_update(path, changes)
    assert yaml.safe_load(path.read_text())["opencode"]["test_mode"] is False
