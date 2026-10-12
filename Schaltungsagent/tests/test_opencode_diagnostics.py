"""Fehlermeldungen nennen Ursache, Hinweis und Kontext statt nur „nicht geliefert“."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import asyncio
from pathlib import Path

import pytest

from src.agents.hdl import HDLAgent
from src.domain.exceptions import (
    OpenCodeDeliveryError,
    OpenCodeUnavailableError,
    WorkflowError,
)
from src.domain.models import ModuleInfo
from src.domain.ports import OpenCodeResult
from src.services.opencode_task_runner import OpenCodeTaskRunner
from src.services.plan_service import PlanService, PlanValidationError


class FakeOpenCode:
    """Simuliert verschiedene Fehlerbilder eines OpenCode-Laufs."""

    def __init__(self, returncode=0, stdout="", stderr="", writes=None, raises=None):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr
        self.writes = writes or {}
        self.raises = raises

    def execute(self, workspace, instruction, timeout_seconds=None):
        if self.raises:
            raise self.raises
        for relative, content in self.writes.items():
            path = Path(workspace) / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        return OpenCodeResult(self.returncode, self.stdout, self.stderr)


GOOD_CONTROL = "entity control is end entity;\narchitecture rtl of control is begin end architecture;\n"


def deliver(tmp_path, fake, expected="src/control.vhd"):
    runner = OpenCodeTaskRunner(fake)
    return runner.run(
        workspace=str(tmp_path), request_full="Baue eine CPU", stage="implement_module",
        task_instruction="Schreibe src/control.vhd", expected_files=[expected], task_id="control_1",
    )


def test_success_has_no_error(tmp_path):
    delivery = deliver(tmp_path, FakeOpenCode(writes={"src/control.vhd": GOOD_CONTROL}))
    assert delivery.ok and delivery.file_status == {"src/control.vhd": "ok"}


def test_model_answered_without_writing_file(tmp_path):
    delivery = deliver(tmp_path, FakeOpenCode(stdout="Hier ist der Code: ```vhdl ...```"))
    error = delivery.error("Modul 'control'")

    assert isinstance(error, OpenCodeDeliveryError)
    text = str(error)
    assert "src/control.vhd wurde nicht geschrieben" in text
    assert "ohne Fehler, hat aber keine Projektdatei geschrieben" in text
    assert "Hinweis:" in text and "anderes Modell" in text
    assert "Exit-Code: 0" in text
    assert "Auftragsdatei: .opencode_tasks/control_1_implement_module.md" in text
    assert "Hier ist der Code" in text  # stdout-Ende im Kontext


def test_file_written_under_other_name(tmp_path):
    fake = FakeOpenCode(writes={"src/controller.vhd": GOOD_CONTROL.replace("control", "controller")})
    text = str(deliver(tmp_path, fake).error("Modul 'control'"))
    assert "OpenCode hat stattdessen src/controller.vhd geändert" in text
    assert "Ziel-Dateiname weicht ab" in text


@pytest.mark.parametrize("content,expected", [
    ("", "ist leer"),
    ("```vhdl\n" + GOOD_CONTROL + "```", "Markdown-Codeblock"),
    (GOOD_CONTROL.replace("entity control", "entity ctrl").replace("of control", "of ctrl"), "Entity 'ctrl' statt 'control'"),
    ("entity control is end entity;\n", "keine architecture"),
])
def test_invalid_file_content_is_named(tmp_path, content, expected):
    delivery = deliver(tmp_path, FakeOpenCode(writes={"src/control.vhd": content}))
    assert not delivery.ok
    assert expected in str(delivery.error("Modul 'control'"))


@pytest.mark.parametrize("stderr,cause", [
    ("Error: 429 Too Many Requests – rate limit", "Kontingent"),
    ("Error: status 401 Unauthorized", "Anmeldung beim Modell-Provider"),
    ("ProviderModelNotFoundError: model foo/bar", "Modell ist beim Provider nicht verfügbar"),
    ("TypeError: fetch failed ENOTFOUND api.example", "Keine Netzwerkverbindung"),
    ("Segmentation fault", "Exit-Code 1"),
])
def test_process_failure_explains_missing_file(tmp_path, stderr, cause):
    text = str(deliver(tmp_path, FakeOpenCode(returncode=1, stderr=stderr)).error("Modul 'control'"))
    assert cause in text
    assert stderr.split(":")[0] in text  # stderr-Ende im Kontext


def test_infrastructure_error_keeps_its_type_and_hint(tmp_path):
    original = OpenCodeUnavailableError(
        "docker: Docker daemon not running. No fallback to the host (isolation required).",
        cause="Der Docker-Dienst läuft nicht.", hint="Docker starten oder Testmodus wählen.",
    )
    error = deliver(tmp_path, FakeOpenCode(raises=original)).error("Modul 'control'")
    assert error is original
    text = str(error)
    assert text.startswith("Modul 'control': docker: Docker daemon not running")
    assert "Docker starten oder Testmodus wählen." in text
    assert "Phase: implement_module" in text


def test_hdl_agent_raises_diagnostic_error_for_missing_module(tmp_path):
    """Reproduziert: 'OpenCode did not deliver src/control.vhd; no safe template fallback applies'."""
    agent = HDLAgent(opencode_service=None, filesystem_service=None, task_runner=OpenCodeTaskRunner(FakeOpenCode()))
    agent._fallback.module_vhdl = lambda request, name: ""
    with pytest.raises(OpenCodeDeliveryError) as info:
        asyncio.new_event_loop().run_until_complete(agent._generate_module_vhdl(
            ModuleInfo(name="control", type="fsm"), {}, "vhdl",
            request="Baue eine CPU", workspace=str(tmp_path),
        ))
    text = str(info.value)
    assert text.startswith("Modul 'control': OpenCode hat src/control.vhd nicht gültig geliefert")
    assert "Ursache: src/control.vhd wurde nicht geschrieben" in text
    assert "Hinweis:" in text


def test_plan_errors_carry_cause(tmp_path):
    planner = PlanService(OpenCodeTaskRunner(FakeOpenCode(writes={"plan/manifest.json": "```json {}```"})))
    with pytest.raises(PlanValidationError) as info:
        planner.plan(str(tmp_path), "Baue eine CPU", "t1")
    assert isinstance(info.value, WorkflowError) and isinstance(info.value, ValueError)
    assert "kein gültiges JSON" in str(info.value)


def test_provider_failures_route_to_user_not_hdl_repair(tmp_path):
    from src.domain.agents.repair_routing import RepairTarget, route_repair

    quota = deliver(tmp_path, FakeOpenCode(returncode=1, stderr="429 rate limit")).error("Modul 'control'")
    missing = deliver(tmp_path, FakeOpenCode()).error("Modul 'control'")

    assert quota.failure_type == "infrastructure"
    assert route_repair(quota.failure_type) == RepairTarget.HUMAN
    assert missing.failure_type == ""  # Modell hat nur nicht geschrieben: HDL-Retry sinnvoll


def test_supervisor_passes_module_causes_to_diagnosis(tmp_path):
    from test_multi_agent_gates import THREE_MODULES, make_supervisor, run, set_architecture
    from src.domain.agents import AgentResult, AgentStatus

    class FailingHDL:
        async def execute(self, task):
            name = (task.inputs.get("module") or {}).get("name", "top")
            if name == "control":
                return AgentResult(
                    task_id=task.id, status=AgentStatus.FAILED,
                    error_message="Module control implementation failed: Modul 'control': Ursache: Kontingent",
                    diagnostics=[{"type": "implementation_failure", "failure_type": "infrastructure",
                                  "message": "Kontingent erschöpft"}],
                )
            (Path(task.inputs["workspace"]) / "src").mkdir(parents=True, exist_ok=True)
            (Path(task.inputs["workspace"]) / "src" / f"{name}.vhd").write_text("--")
            return AgentResult(task_id=task.id, status=AgentStatus.COMPLETED, outputs={"files": []})

    supervisor, _, _ = make_supervisor(tmp_path, hdl_agent=FailingHDL())
    set_architecture(supervisor, THREE_MODULES, "cpu")
    result = run(supervisor._run_implementation())

    assert "Ursache: Kontingent" in result.error_message
    control = [d for d in result.diagnostics if d["modules"] == ["control"]][0]
    assert control["failure_type"] == "infrastructure"


class TimeoutOpenCode:
    def execute(self, workspace, instruction, timeout_seconds=None):
        from src.domain.exceptions import OpenCodeTimeoutError
        raise OpenCodeTimeoutError(
            "OpenCode execution timed out after 600s",
            cause="OpenCode hat innerhalb von 600 s kein Ergebnis geliefert und wurde abgebrochen.",
            hint="Zeitlimit in Einstellungen → OpenCode-Modelle erhöhen oder die Aufgabe verkleinern.",
        )


def test_repair_timeout_blocks_workflow_with_reason_instead_of_crashing(tmp_path):
    """Reproduziert: Timeout in _fix_hdl ließ 'Supervisor execution failed' entstehen."""
    from test_multi_agent_gates import DiskFS, make_supervisor, run, set_architecture
    from src.agents.debug import DebugAgent
    from src.domain.agents import AgentResult, AgentStatus
    from src.domain.models import DesignStage

    hdl = HDLAgent(opencode_service=TimeoutOpenCode(), filesystem_service=DiskFS(tmp_path),
                   task_runner=OpenCodeTaskRunner(TimeoutOpenCode()))
    supervisor, _, events = make_supervisor(tmp_path, hdl_agent=hdl, debug_agent=DebugAgent())
    set_architecture(supervisor, [{"name": "control"}], "control")
    (tmp_path / "proj" / "src").mkdir(parents=True)
    (tmp_path / "proj" / "src" / "control.vhd").write_text(GOOD_CONTROL)
    supervisor._design_state.current_stage = DesignStage.SIMULATING
    failure = AgentResult(task_id="sim", status=AgentStatus.FAILED, diagnostics=[{
        "type": "simulation_failure", "stage": "simulation",
        "message": "control_tb.vhd:10:5:@20ns:(assertion error): simulation failed in control",
    }])

    result = run(supervisor._handle_failure(DesignStage.SIMULATING, failure))

    assert result.status == AgentStatus.BLOCKED
    assert "Reparatur von 'control'" in result.error_message
    assert "Zeitlimit in Einstellungen" in result.error_message
    assert supervisor._design_state.current_stage == DesignStage.INFRASTRUCTURE_FAILURE
    assert "HUMAN_INTERVENTION_REQUESTED" in events.types()


def test_unexpected_stage_exception_does_not_abort_supervisor(tmp_path):
    from test_multi_agent_gates import make_supervisor, run
    from src.domain.agents import AgentStatus
    from src.domain.models import DesignStage

    supervisor, _, _ = make_supervisor(tmp_path)
    supervisor._design_state.current_stage = DesignStage.SIMULATING

    async def boom(stage):
        raise KeyError("verification_result")

    supervisor._execute_stage = boom
    result = run(supervisor._run_autonomous_loop())

    assert result.status in (AgentStatus.FAILED, AgentStatus.BLOCKED)
    history = supervisor._design_state.diagnostics.history
    assert any("unerwarteter Fehler KeyError" in d.get("message", "") for d in history)


def test_provider_server_error_is_recognized_not_generic(tmp_path):
    """Reproduziert: OpenCode-JSON-Fehler mit 'UnknownError' fiel bisher auf den
    generischen Zweig zurück und zeigte nur '(})' statt der echten Ursache."""
    from src.services.opencode_service import describe_opencode_failure, is_provider_failure

    stderr = (
        'Error: {\n'
        '  "name": "UnknownError",\n'
        '  "data": {\n'
        '    "message": "Unexpected server error. Check server logs for details.",\n'
        '    "ref": "err_ef0e9972"\n'
        '  }\n'
        '}'
    )
    cause, hint = describe_opencode_failure(1, "", stderr)

    assert cause == "Serverfehler beim Modell-Provider (nicht auf unserer Seite behebbar)"
    assert "erneut versuchen" in hint
    assert is_provider_failure(cause)


def test_generic_fallback_extracts_json_message_instead_of_closing_brace(tmp_path):
    from src.services.opencode_service import describe_opencode_failure

    stderr = (
        'Error: {\n'
        '  "name": "WeirdProviderIssue",\n'
        '  "data": {"message": "Something specific broke"}\n'
        '}'
    )
    cause, _ = describe_opencode_failure(1, "", stderr)

    assert cause == "OpenCode wurde mit Exit-Code 1 beendet (WeirdProviderIssue: Something specific broke)"
    assert "(})" not in cause


def test_generic_fallback_skips_brace_only_lines_without_json(tmp_path):
    from src.services.opencode_service import describe_opencode_failure

    stderr = "some real error text\n}\n"
    cause, _ = describe_opencode_failure(1, "", stderr)

    assert "some real error text" in cause
    assert "(})" not in cause


def test_bootstrap_provider_server_error_reaches_user_as_cause(tmp_path):
    """End-to-end wie im Bugreport: Projektplanung bricht mit der echten Ursache ab."""
    stderr = (
        'Error: {\n'
        '  "name": "UnknownError",\n'
        '  "data": {"message": "Unexpected server error. Check server logs for details.", "ref": "err_x"}\n'
        '}'
    )
    planner = PlanService(OpenCodeTaskRunner(FakeOpenCode(returncode=1, stderr=stderr)))
    with pytest.raises(PlanValidationError) as info:
        planner.plan(str(tmp_path), "Baue eine Ampelsteuerung", "t1")

    text = str(info.value)
    assert "Serverfehler beim Modell-Provider" in text
    assert "(})" not in text


def test_architecture_agent_propagates_provider_failure_type(tmp_path):
    """Ein Provider-Serverfehler während (Re-)Architektur darf nicht als
    'unknown' an den HDLAgent geroutet werden."""
    from src.agents.architecture import ArchitectureAgent
    from src.domain.agents import AgentTask, AgentStatus
    from src.domain.agents.repair_routing import RepairTarget, route_repair

    stderr = (
        'Error: {\n'
        '  "name": "UnknownError",\n'
        '  "data": {"message": "Unexpected server error. Check server logs for details.", "ref": "err_x"}\n'
        '}'
    )
    agent = ArchitectureAgent(plan_service=PlanService(OpenCodeTaskRunner(FakeOpenCode(returncode=1, stderr=stderr))))

    result = asyncio.new_event_loop().run_until_complete(agent.execute(AgentTask(
        id="t1", type="create_architecture", project_id="p1",
        inputs={"request": "Baue eine Ampelsteuerung", "workspace": str(tmp_path)},
    )))

    assert result.status == AgentStatus.FAILED
    assert result.diagnostics and result.diagnostics[0]["failure_type"] == "infrastructure"
    assert route_repair(result.diagnostics[0]["failure_type"]) == RepairTarget.HUMAN


@pytest.mark.parametrize("raw,expected", [
    ("opencode/Nemotron-3.5-Lightning", "opencode/Nemotron-3.5-Lightning"),
    ("  opencode / Muse-Spark-1.3-Free  ", "opencode/Muse-Spark-1.3-Free"),
    ("gpt-oss:120b-cloud", "gpt-oss:120b-cloud"),
    ("model_with_underscore", "model_with_underscore"),
    ("", ""),
    ("   ", ""),
    (None, ""),
])
def test_model_normalization_preserves_case_and_underscores(raw, expected):
    """Regression: Modell-IDs sind oft case-sensitiv; frühere Normalisierung
    hat sie force-lowercase gemacht und damit eine gültige, beim Provider
    registrierte ID unbemerkt in eine ungültige verwandeln können."""
    from src.api_server import normalize_open_code_model

    assert normalize_open_code_model(raw) == expected


def test_call_event_reports_task_prompt_size_and_duration(tmp_path):
    class Bus:
        def __init__(self):
            self.payloads = []

        def publish_event(self, event_type, task_id, payload):
            self.payloads.append(payload)

    bus = Bus()
    runner = OpenCodeTaskRunner(FakeOpenCode(writes={"src/control.vhd": GOOD_CONTROL}), event_publisher=bus)
    runner.run(workspace=str(tmp_path), request_full="Baue eine CPU", stage="implement_module",
               task_instruction="Schreibe src/control.vhd", expected_files=["src/control.vhd"], task_id="control_1")

    task_file = next((tmp_path / ".opencode_tasks").glob("control_1_implement_module.md")).read_text()
    payload = bus.payloads[-1]
    assert payload["prompt_length"] == len(task_file) and payload["request_length"] == len("Baue eine CPU")
    assert payload["duration_s"] >= 0 and payload["success"] is True


def test_upstream_credential_failure_counts_as_provider_outage(tmp_path):
    fake = FakeOpenCode(returncode=1, stdout="> build · muse-spark-1.3\nError: Upstream request failed: Invalid credential")
    error = deliver(tmp_path, fake).error("Modul 'control'")
    assert error.failure_type == "infrastructure" and "Anbieter" in error.cause


def test_supervisor_checkpoint_during_a_call_does_not_count_as_opencode_change(tmp_path):
    class EarlyStop(FakeOpenCode):
        calls = 0

        def execute(self, workspace, instruction, timeout_seconds=None):
            EarlyStop.calls += 1
            # Der Supervisor speichert parallel seinen Checkpoint (#48) …
            (Path(workspace) / "task_graph.json").write_text(str(EarlyStop.calls))
            if EarlyStop.calls == 2:  # … und erst der zweite Versuch liefert die Datei.
                (Path(workspace) / "src").mkdir(exist_ok=True)
                (Path(workspace) / "src" / "control.vhd").write_text(GOOD_CONTROL)
            return OpenCodeResult(0, "", "")

    delivery = deliver(tmp_path, EarlyStop())
    assert EarlyStop.calls == 2 and delivery.ok
    assert "task_graph.json" not in delivery.changed_files
