import os
import subprocess

import pytest

from src.config import load_config
from src.domain.exceptions import AgentExecutionError, OpenCodeTimeoutError, OpenCodeUnavailableError
import src.services.opencode_service as opencode_service_module
from src.services.opencode_service import (
    DockerOpenCodeService,
    SubprocessOpenCodeService,
    create_opencode_service,
)


def _settings(tmp_path, text: str):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(text)
    return load_config(str(config_path))


def test_test_mode_forces_local_opencode(tmp_path):
    settings = _settings(tmp_path, "opencode:\n  test_mode: true\n  binary: opencode\n")

    service = create_opencode_service(settings)

    assert isinstance(service, SubprocessOpenCodeService)
    assert not isinstance(service, DockerOpenCodeService)


def test_environment_test_mode_overrides_docker(tmp_path, monkeypatch):
    monkeypatch.setenv("VHDL_AGENT_TEST_MODE", "1")
    settings = _settings(tmp_path, "opencode:\n  use_docker: true\n")

    assert settings.opencode.test_mode is True
    assert isinstance(create_opencode_service(settings), SubprocessOpenCodeService)


def test_outside_test_mode_docker_is_mandatory_even_if_use_docker_false(tmp_path, monkeypatch):
    monkeypatch.delenv("VHDL_AGENT_TEST_MODE", raising=False)
    settings = _settings(tmp_path, "opencode:\n  use_docker: false\n  test_mode: false\n")

    assert isinstance(create_opencode_service(settings), DockerOpenCodeService)


def _per_task_service(tmp_path, **kwargs):
    projects = tmp_path / "projects"
    (projects / "counter").mkdir(parents=True)
    return DockerOpenCodeService(
        host_workspace=str(projects), model="m/x", image="img:1", **kwargs,
    ), projects


def test_per_task_container_mounts_only_the_project(tmp_path):
    service, projects = _per_task_service(
        tmp_path, memory="4g", cpus="2", auth_dir="/home/u/.local/share/opencode", network="none",
    )

    cmd = service.build_command(str(projects / "counter"), "do it")

    assert cmd[:3] == ["docker", "run", "--rm"]
    mounts = [cmd[i + 1] for i, part in enumerate(cmd) if part == "-v"]
    assert mounts == [
        f"{(projects / 'counter').resolve()}:/workspace:rw",
        f"/home/u/.local/share/opencode:{DockerOpenCodeService.CONTAINER_HOME}/.local/share/opencode:ro",
    ]
    assert ["--cap-drop", "ALL"] == cmd[cmd.index("--cap-drop"):cmd.index("--cap-drop") + 2]
    assert "no-new-privileges" in cmd
    assert cmd[cmd.index("--user") + 1] == f"{os.getuid()}:{os.getgid()}"
    assert cmd[cmd.index("--network") + 1] == "none"
    assert cmd[cmd.index("--memory") + 1] == "4g" and cmd[cmd.index("--cpus") + 1] == "2"
    assert cmd[-7:] == ["--entrypoint", "opencode", "img:1", "run", "--model", "m/x", "do it"]


def test_per_task_refuses_paths_outside_projects(tmp_path):
    service, _ = _per_task_service(tmp_path)
    with pytest.raises(AgentExecutionError):
        service.build_command(str(tmp_path), "x")


def test_shared_container_uses_exec_into_project_path(tmp_path):
    service, projects = _per_task_service(tmp_path, isolation="shared", container="oc")
    cmd = service.build_command(str(projects / "counter"), "do it")
    assert cmd[:5] == ["docker", "exec", "-w", "/workspace/counter", "oc"]


@pytest.mark.parametrize("stderr", [
    "permission denied while trying to connect to the Docker daemon socket",
    "Cannot connect to the Docker daemon at unix:///var/run/docker.sock",
    "Unable to find image 'img:1' locally",
])
def test_docker_failures_never_fall_back_to_host(tmp_path, monkeypatch, stderr):
    service, projects = _per_task_service(tmp_path)
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 125, "", stderr)

    monkeypatch.setattr(opencode_service_module, "_run_via_pty", fake_run)
    with pytest.raises(AgentExecutionError, match="No fallback to the host"):
        service.execute(str(projects / "counter"), "x")
    assert all(cmd[0] == "docker" for cmd in calls)


def test_missing_docker_binary_raises_instead_of_running_natively(tmp_path, monkeypatch):
    service, projects = _per_task_service(tmp_path)

    def missing(cmd, **kwargs):
        raise FileNotFoundError("docker")

    monkeypatch.setattr(opencode_service_module, "_run_via_pty", missing)
    with pytest.raises(AgentExecutionError, match="docker: command not found"):
        service.execute(str(projects / "counter"), "x")


def test_switching_test_mode_reaches_components_created_earlier(tmp_path, monkeypatch):
    """Regression: Planer/Task-Runner hielten nach dem Umschalten den alten Docker-Runner."""
    from src.services.opencode_service import ReconfigurableOpenCodeService
    from src.services.opencode_task_runner import OpenCodeTaskRunner
    from src.services.plan_service import PlanService

    monkeypatch.delenv("VHDL_AGENT_TEST_MODE", raising=False)
    settings = _settings(tmp_path, "opencode:\n  test_mode: false\n")
    service = ReconfigurableOpenCodeService(settings)
    planner = PlanService(OpenCodeTaskRunner(service))  # wie beim Serverstart
    assert isinstance(service.delegate, DockerOpenCodeService)

    executed = []
    monkeypatch.setattr(
        SubprocessOpenCodeService, "execute",
        lambda self, path, instruction, timeout_seconds=None: executed.append(path) or __import__(
            "src.domain.ports", fromlist=["OpenCodeResult"]).OpenCodeResult(returncode=1, stderr="stub"),
    )
    monkeypatch.setattr(
        DockerOpenCodeService, "execute",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("Docker must not be used in test mode")),
    )

    settings.opencode.test_mode = True
    service.reconfigure(settings)

    assert isinstance(service.delegate, SubprocessOpenCodeService)
    assert planner._runner._opencode is service
    service.execute(str(tmp_path), "plan")
    assert executed == [str(tmp_path)]


# ---------------------------------------------------------------------------
# Modell-Liste (Settings-Picker) – siehe docs/known_limitations.md:
# "opencode/nemotron-3.5-lightning" statt "...-lightning-free" ist ein
# real aufgetretener Fall: kostenpflichtiges statt kostenloses Modell,
# die vom Provider gemeldete Ursache war ein generischer Serverfehler
# statt "model not found". Der Picker soll genau das verhindern.
# ---------------------------------------------------------------------------

REAL_OPENCODE_MODELS = (
    "opencode/big-pickle\n"
    "opencode/exo-free\n"
    "opencode/mimo-v2.6-flash-free\n"
    "opencode/nemotron-3.5-lightning-free\n"
    "opencode/space-bunny-free\n"
)


def test_group_models_by_provider():
    from src.services.opencode_service import group_models_by_provider

    grouped = group_models_by_provider([
        "opencode/mimo-v2.6-flash-free", "opencode/nemotron-3.5-lightning-free",
        "ollama-cloud/glm-5.1", "no-slash-entry",
    ])

    assert grouped["opencode"] == ["opencode/mimo-v2.6-flash-free", "opencode/nemotron-3.5-lightning-free"]
    assert grouped["ollama-cloud"] == ["ollama-cloud/glm-5.1"]
    assert grouped[""] == ["no-slash-entry"]


def test_subprocess_list_models_parses_one_model_per_line(monkeypatch):
    service = SubprocessOpenCodeService(binary="opencode")
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, REAL_OPENCODE_MODELS, "")

    monkeypatch.setattr(opencode_service_module, "_run_via_pty", fake_run)
    models = service.list_models("opencode")

    assert calls[0] == ["opencode", "models", "opencode"]
    assert models == [
        "opencode/big-pickle", "opencode/exo-free", "opencode/mimo-v2.6-flash-free",
        "opencode/nemotron-3.5-lightning-free", "opencode/space-bunny-free",
    ]
    # Genau der Eintrag, der das reale Problem (fehlendes "-free") aufdeckt:
    assert "opencode/nemotron-3.5-lightning-free" in models
    assert "opencode/nemotron-3.5-lightning" not in models


def test_subprocess_list_models_without_provider_omits_filter_arg(monkeypatch):
    service = SubprocessOpenCodeService(binary="opencode")
    calls = []
    monkeypatch.setattr(opencode_service_module, "_run_via_pty", lambda cmd, **k: calls.append(cmd) or
                         subprocess.CompletedProcess(cmd, 0, "opencode/big-pickle\n", ""))
    service.list_models()
    assert calls[0] == ["opencode", "models"]


def test_subprocess_list_models_raises_on_missing_binary(monkeypatch):
    service = SubprocessOpenCodeService(binary="opencode")
    monkeypatch.setattr(opencode_service_module, "_run_via_pty", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError()))
    with pytest.raises(OpenCodeUnavailableError, match="command not found"):
        service.list_models()


def test_subprocess_list_models_raises_on_timeout(monkeypatch):
    service = SubprocessOpenCodeService(binary="opencode")
    monkeypatch.setattr(
        opencode_service_module, "_run_via_pty",
        lambda *a, **k: (_ for _ in ()).throw(subprocess.TimeoutExpired(cmd="opencode", timeout=60)),
    )
    with pytest.raises(OpenCodeTimeoutError, match="timed out"):
        service.list_models()


def test_subprocess_list_models_raises_with_cause_on_nonzero_exit(monkeypatch):
    service = SubprocessOpenCodeService(binary="opencode")
    monkeypatch.setattr(
        opencode_service_module, "_run_via_pty",
        lambda cmd, **k: subprocess.CompletedProcess(cmd, 1, "", "429 rate limit exceeded"),
    )
    with pytest.raises(AgentExecutionError) as info:
        service.list_models()
    assert "Kontingent" in str(info.value)


def test_docker_build_models_command_per_task_has_no_project_mount(tmp_path):
    service = DockerOpenCodeService(
        isolation="per_task", image="img:1", host_workspace=str(tmp_path),
        auth_dir="/home/u/.local/share/opencode",
    )
    cmd = service.build_models_command("opencode")

    assert cmd[:4] == ["docker", "run", "--rm", "-t"]  # -t: Container-Prozess braucht ein TTY
    assert "-w" not in cmd  # kein Projekt-Workdir, da kein Projekt-Mount noetig
    mounts = [cmd[i + 1] for i, part in enumerate(cmd) if part == "-v"]
    assert mounts == [f"/home/u/.local/share/opencode:{DockerOpenCodeService.CONTAINER_HOME}/.local/share/opencode:ro"]
    assert cmd[-5:] == ["--entrypoint", "opencode", "img:1", "models", "opencode"]


def test_docker_build_models_command_shared_execs_into_running_container():
    service = DockerOpenCodeService(isolation="shared", container="oc-agent")
    assert service.build_models_command("opencode") == ["docker", "exec", "-t", "oc-agent", "opencode", "models", "opencode"]
    assert service.build_models_command() == ["docker", "exec", "-t", "oc-agent", "opencode", "models"]


def test_docker_list_models_reuses_existing_infra_error_handling(tmp_path, monkeypatch):
    """Zeigt: Docker-Modell-Listing nutzt denselben Fehlerweg (kein Host-Fallback)."""
    service = DockerOpenCodeService(isolation="per_task", image="img:1", host_workspace=str(tmp_path))
    monkeypatch.setattr(
        opencode_service_module, "_run_via_pty",
        lambda cmd, **k: subprocess.CompletedProcess(cmd, 125, "", "Cannot connect to the Docker daemon"),
    )
    with pytest.raises(OpenCodeUnavailableError, match="Docker daemon not running"):
        service.list_models()


def test_docker_build_command_output_unchanged_by_refactor(tmp_path):
    """Die build_command()-Refaktorierung (gemeinsame _base_run_args) darf den
    bestehenden 'run'-Befehl nur um "-t" (TTY fuer den Container-Prozess,
    siehe test_opencode_pty_execution.py) veraendern - sonst nicht."""
    (tmp_path / "proj").mkdir()
    service = DockerOpenCodeService(
        isolation="per_task", image="img:1", model="m/x", host_workspace=str(tmp_path),
        memory="4g", cpus="2", auth_dir="/auth", network="none",
    )
    cmd = service.build_command(str(tmp_path / "proj"), "do it")
    assert cmd == [
        "docker", "run", "--rm", "-t", "--network", "none", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "--user", f"{os.getuid()}:{os.getgid()}",
        "-e", f"HOME={DockerOpenCodeService.CONTAINER_HOME}",
        "-v", f"{(tmp_path / 'proj').resolve()}:/workspace:rw", "-w", "/workspace",
        "-v", f"/auth:{DockerOpenCodeService.CONTAINER_HOME}/.local/share/opencode:ro",
        "--memory", "4g", "--cpus", "2",
        "--entrypoint", "opencode", "img:1", "run", "--model", "m/x", "do it",
    ]


def test_reconfigurable_service_exposes_list_models(tmp_path):
    settings = _settings(tmp_path, "opencode:\n  test_mode: true\n  binary: opencode\n")
    from src.services.opencode_service import ReconfigurableOpenCodeService

    wrapper = ReconfigurableOpenCodeService(settings)
    assert hasattr(wrapper.delegate, "list_models")
    assert callable(wrapper.list_models)
