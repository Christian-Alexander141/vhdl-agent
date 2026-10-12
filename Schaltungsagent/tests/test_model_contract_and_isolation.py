"""Lauf led-pattern-display (2026-10-11, Abbruch nach 7 Reparaturen): docs/doku.html #39-#42.

- Die Vergleichs-Testbench instanziierte den Entwurf ohne generic map
  (TICK_CYCLES=25_000_000), das Referenzmodell rechnete mit 4.
- Fünf Agentenläufe erkannten das und schrieben es in reports/*.md; der
  Supervisor las es nie, die erzeugte Testbench wurde jedes Mal neu geschrieben.
- OpenCode arbeitete im System-Repo (Workspace liegt in vhdl-agent/projects/).
- design_state.yaml wuchs auf 1,27 MB (6,7 s je Laden/Speichern).
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from src.domain.agents import AgentResult, AgentStatus, reference_model as refmodel
from src.domain.models import DesignStage

from tests.test_multi_agent_gates import make_supervisor, run, set_architecture

COUNTER_VHDL = """library ieee; use ieee.std_logic_1164.all; use ieee.numeric_std.all;
entity blinker is
  generic (TICK_CYCLES : positive := 25000000);
  port (clk : in std_logic; rst : in std_logic; led : out std_logic);
end entity;
architecture rtl of blinker is
  signal cnt : natural range 0 to TICK_CYCLES - 1 := 0;
  signal q : std_logic := '0';
begin
  process(clk) begin
    if rising_edge(clk) then
      if rst = '1' then cnt <= 0; q <= '0';
      elsif cnt = TICK_CYCLES - 1 then cnt <= 0; q <= not q;
      else cnt <= cnt + 1; end if;
    end if;
  end process;
  led <= q;
end architecture;
"""

MODEL_CONSTRUCTOR = """
class ReferenceModel:
    SUGGESTED_CYCLES = 60
    def __init__(self, tick_cycles: int = 4):
        self.n = tick_cycles
        self.reset()
    def reset(self):
        self.cnt, self.q = 0, 0
    def step(self, inputs):
        if inputs.get("rst", 0):
            self.cnt, self.q = 0, 0
        elif self.cnt == self.n - 1:
            self.cnt, self.q = 0, 1 - self.q
        else:
            self.cnt += 1
        return {"led": self.q}
"""

MODEL_TEST = """
from reference_model import ReferenceModel
def test_toggles():
    m = ReferenceModel()
    outs = [m.step({"rst": 0})["led"] for _ in range(8)]
    assert outs[3] == 1 and outs[7] == 0
"""


def _workspace(tmp_path, model=MODEL_CONSTRUCTOR):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "blinker.vhd").write_text(COUNTER_VHDL)
    (tmp_path / "model").mkdir()
    (tmp_path / "model" / "reference_model.py").write_text(model)
    (tmp_path / "model" / "test_reference_model.py").write_text(MODEL_TEST)
    return str(tmp_path)


# --- Generic-Vertrag Modell <-> Vergleichs-Testbench --------------------------------

def test_generic_values_come_from_the_model_constructor(tmp_path):
    status = refmodel.write_model_testbench(_workspace(tmp_path), "blinker")
    assert status["status"] == "written"
    assert status["generics"] == {"tick_cycles": 4} and status["generics_source"] == "constructor"
    assert "generic map (\n            tick_cycles => 4" in (tmp_path / "tests" / "blinker_model_tb.vhd").read_text()


def test_explicit_generics_attribute_wins_and_unknown_names_are_ignored(tmp_path):
    model = MODEL_CONSTRUCTOR.replace("SUGGESTED_CYCLES = 60",
                                      'SUGGESTED_CYCLES = 60\n    GENERICS = {"TICK_CYCLES": 4, "NOT_A_GENERIC": 3}')
    status = refmodel.write_model_testbench(_workspace(tmp_path, model), "blinker")
    assert status["generics"] == {"tick_cycles": 4} and status["generics_ignored"] == ["NOT_A_GENERIC"]


def test_missing_generic_values_are_reported(tmp_path):
    model = MODEL_CONSTRUCTOR.replace("def __init__(self, tick_cycles: int = 4):\n        self.n = tick_cycles",
                                      "def __init__(self):\n        self.n = 4")
    status = refmodel.write_model_testbench(_workspace(tmp_path, model), "blinker")
    assert status["generics"] == {} and status["generics_default"] == ["tick_cycles"]


@pytest.mark.skipif(shutil.which("ghdl") is None, reason="GHDL nicht installiert")
def test_model_testbench_with_generic_map_passes_in_ghdl(tmp_path):
    """Ohne generic map lief der Entwurf mit 25 Mio. Takten pro Tick und wich ab."""
    workspace = _workspace(tmp_path)
    refmodel.write_model_testbench(workspace, "blinker")
    work = tmp_path / "w"
    work.mkdir()
    for args in (["-a", "--std=08", f"--workdir={work}", "src/blinker.vhd", "tests/blinker_model_tb.vhd"],
                 ["-r", "--std=08", f"--workdir={work}", "blinker_model_tb", "--stop-time=1ms", "--assert-level=error"]):
        result = subprocess.run(["ghdl", *args], cwd=workspace, capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr
    assert "TB_COMPLETE" in result.stdout + result.stderr


def test_model_brief_names_the_top_level_generics(tmp_path):
    from src.agents.verification import VerificationAgent
    from src.domain.agents import AgentTask

    captured = {}

    class Runner:
        def run(self, **kw):
            from src.services.opencode_task_runner import OpenCodeDelivery
            captured.update(kw)
            return OpenCodeDelivery(ok=False, stage=kw["stage"], reason="test")

    agent = VerificationAgent(filesystem_service=None, opencode_service=None, task_runner=Runner())
    architecture = {"top_module": "blinker", "modules": [{
        "name": "blinker", "parameters": {"TICK_CYCLES": 25000000},
        "ports": {"clk": {"direction": "in", "type": "std_logic"}, "rst": {"direction": "in", "type": "std_logic"},
                  "led": {"direction": "out", "type": "std_logic"}},
    }]}
    run(agent.execute(AgentTask(id="m", type="reference_model", project_id="p", inputs={
        "workspace": str(tmp_path), "architecture": architecture, "request_full": "x"})))
    assert "TICK_CYCLES = 25000000" in captured["task_instruction"]
    assert "GENERICS" in captured["task_instruction"]


# --- Rückkanal: strukturierter Befund der Reparatur ----------------------------------

class _VerdictHDL:
    """Hält den Entwurf für richtig: ändert src/ nicht, meldet generated_check."""

    def __init__(self):
        self.calls = []

    async def execute(self, task):
        self.calls.append(task)
        workspace = Path(task.inputs["workspace"])
        tb = workspace / "tests" / "top_model_tb.vhd"
        if tb.is_file():
            tb.write_text(tb.read_text() + "\n-- von Hand korrigiert\n")  # zählt nicht als Änderung
        (workspace / "reports").mkdir(exist_ok=True)
        (workspace / "reports" / "repair_verdict.json").write_text(json.dumps({
            "cause": "generated_check", "reason": "Vergleichs-Testbench ohne generic map (TICK_CYCLES=4)"}))
        return AgentResult(task_id=task.id, status=AgentStatus.COMPLETED, outputs={})


class _ModelAgent:
    supported_task_types = ["reference_model"]

    def __init__(self):
        self.hints = []

    async def execute(self, task):
        self.hints.append(task.inputs.get("hint", ""))
        return AgentResult(task_id=task.id, status=AgentStatus.COMPLETED,
                           outputs={"reference_model": {"status": "ready", "reason": "ok"}})


def _mismatch_case(tmp_path):
    from src.agents.debug import DebugAgent

    hdl, model = _VerdictHDL(), _ModelAgent()
    supervisor, fs, events = make_supervisor(tmp_path, hdl_agent=hdl, debug_agent=DebugAgent(),
                                             verification_agent=model, config={"repair_policy": "persistent"})
    set_architecture(supervisor, [{"name": "top", "type": "sequential"}], "top")
    workspace = Path(fs.workspace_path("proj"))
    (workspace / "src").mkdir(parents=True, exist_ok=True)
    (workspace / "src" / "top.vhd").write_text("-- korrekt\n")
    (workspace / "tests").mkdir(exist_ok=True)
    (workspace / "tests" / "top_model_tb.vhd").write_text("-- erzeugt\n")
    supervisor._design_state.architecture.modules[0].files = ["src/top.vhd"]
    supervisor._design_state.current_stage = DesignStage.STATIC_CHECK
    failure = AgentResult(task_id="s", status=AgentStatus.FAILED, error_message="x", diagnostics=[{
        "message": "GHDL simulation failed for top_model_tb",
        "details": {"error": "MODEL_MISMATCH cycle=18 port=led expected=0010 got=0001"}}])
    return supervisor, events, hdl, model, workspace, failure


def test_first_dispute_regenerates_the_model_with_the_repair_finding(tmp_path):
    supervisor, _, hdl, model, workspace, failure = _mismatch_case(tmp_path)
    result = run(supervisor._handle_failure(DesignStage.STATIC_CHECK, failure))
    assert len(hdl.calls) == 1 and result.status == AgentStatus.COMPLETED
    assert model.hints and "generic map" in model.hints[0]
    assert supervisor._design_state.metadata["model_regenerated"] is True
    assert supervisor._design_state.metadata["repair_verdicts"][0]["cause"] == "generated_check"


def test_persisting_dispute_disables_the_differential_test_instead_of_rewriting_the_design(tmp_path):
    supervisor, events, hdl, model, workspace, failure = _mismatch_case(tmp_path)
    supervisor._design_state.metadata["model_regenerated"] = True
    result = run(supervisor._handle_failure(DesignStage.STATIC_CHECK, failure))
    assert result.outputs["action"] == "reference_model_disabled"
    assert len(hdl.calls) == 1 and model.hints == []  # kein Neuschreiben, keine Architektur
    assert supervisor._design_state.metadata["reference_model"]["status"] == "disputed"
    assert not (workspace / "tests" / "top_model_tb.vhd").exists()
    assert "REFERENCE_MODEL_DISPUTED" in events.types()
    assert supervisor._design_state.current_stage == DesignStage.STATIC_CHECK
    # der nächste statische Check erzeugt die Vergleichs-Testbench nicht wieder
    (workspace / "model").mkdir(exist_ok=True)
    (workspace / "model" / "reference_model.py").write_text("x")
    supervisor._refresh_model_testbench(str(workspace))
    assert not (workspace / "tests" / "top_model_tb.vhd").exists()
    assert "abgeschaltet" in supervisor._completion_message()


def test_edits_to_generated_checks_are_not_repair_progress(tmp_path):
    supervisor, _, _, _, workspace, _ = _mismatch_case(tmp_path)
    before = supervisor._sources_digest()
    (workspace / "tests" / "top_model_tb.vhd").write_text("-- anders\n")
    assert supervisor._sources_digest() == before
    (workspace / "src" / "top.vhd").write_text("-- geändert\n")
    assert supervisor._sources_digest() != before


def test_agent_notes_in_review_md_are_surfaced_once(tmp_path):
    supervisor, events, _, _, workspace, _ = _mismatch_case(tmp_path)
    (workspace / "reports").mkdir(exist_ok=True)
    (workspace / "reports" / "review.md").write_text("- Widerspruch: Generator setzt kein generic map\n")
    supervisor._collect_agent_notes()
    supervisor._collect_agent_notes()
    assert events.types().count("AGENT_NOTE") == 1
    assert "generic map" in supervisor._design_state.metadata["agent_notes"][0]


def test_repair_prompt_asks_for_a_verdict_and_names_generated_files():
    import inspect
    from src.agents.hdl import HDLAgent

    source = inspect.getsource(HDLAgent._fix_hdl)
    assert "reports/repair_verdict.json" in source and "tests/*_model_tb.vhd" in source
    assert '{{"cause"' in source  # f-String: wörtliche Klammern


# --- Workspace-Isolation für OpenCode ------------------------------------------------

def _git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


@pytest.mark.skipif(shutil.which("git") is None, reason="git nicht installiert")
def test_workspace_inside_a_foreign_repo_gets_its_own_repository(tmp_path):
    from src.services.opencode_service import isolate_workspace_repo

    _git("init", "-q", cwd=tmp_path)
    workspace = tmp_path / "projects" / "demo"
    workspace.mkdir(parents=True)
    isolate_workspace_repo(str(workspace))
    top = _git("rev-parse", "--show-toplevel", cwd=workspace).stdout.strip()
    assert Path(top).resolve() == workspace.resolve()
    assert _git("rev-list", "--max-parents=0", "HEAD", cwd=workspace).stdout.strip()  # Start-Commit
    isolate_workspace_repo(str(workspace))  # zweiter Aufruf ändert nichts


@pytest.mark.skipif(shutil.which("git") is None, reason="git nicht installiert")
def test_workspace_outside_any_repo_is_left_alone(tmp_path):
    from src.services.opencode_service import isolate_workspace_repo

    workspace = tmp_path / "standalone"
    workspace.mkdir()
    if _git("rev-parse", "--show-toplevel", cwd=workspace).returncode == 0:
        pytest.skip("tmp liegt selbst in einem Git-Repo")
    isolate_workspace_repo(str(workspace))
    assert not (workspace / ".git").exists()


# --- Projektzustand klein und schnell ---------------------------------------------------

def test_stored_diagnostics_keep_key_lines_but_drop_source_dumps():
    from src.domain.agents.triage import compact, key_lines

    diagnostic = {
        "message": "GHDL simulation failed for top_tb",
        "details": {"error": "tests/top_tb.vhd:9:1:(assertion error): FAIL q expected 1 got 0\n" + "x" * 20000,
                    "dut_content": "--- top.vhd ---\n" + "signal s;\n" * 5000, "testbench": "top_tb"},
    }
    small = compact(diagnostic)
    assert "dut_content" not in small["details"] and small["details"]["testbench"] == "top_tb"
    assert len(small["details"]["error"]) < 5000
    assert any("FAIL q expected 1 got 0" in line for line in small["key_lines"])
    assert any("FAIL q expected 1 got 0" in line for line in key_lines(small))


def test_design_state_yaml_round_trip_uses_the_fast_parser():
    from src.domain import yaml_io
    from src.domain.models import DesignState

    state = DesignState()
    state.metadata["umlaut"] = "Zähler – Prüfung"
    again = DesignState.from_yaml(state.to_yaml())
    assert again.metadata["umlaut"] == "Zähler – Prüfung"
    assert yaml_io._Loader.__name__ in ("CSafeLoader", "SafeLoader")


def test_opencode_call_events_reach_the_dashboard_serializer():
    """OPENCODE_CALL wurde als Text veröffentlicht; Event.to_dict() scheiterte daran,
    das Dashboard bekam das Ereignis nie (Traceback bei jedem OpenCode-Aufruf)."""
    from src.domain.event_bus import EventBus
    from src.domain.models.events import Event, EventType
    from src.services.opencode_task_runner import OpenCodeTaskRunner

    seen = []
    bus = EventBus()
    bus.on_event(lambda event: seen.append(event.to_dict()))
    OpenCodeTaskRunner(opencode_service=None, event_publisher=bus)._emit(
        "plan", "t1", "abc", {"prompt_length": 3617, "request_length": 7516}, True, "", 158.94)
    assert seen and seen[0]["event_type"] == "OPENCODE_CALL"
    payload = seen[0]["payload"]
    assert (payload["prompt_length"], payload["request_length"], payload["duration_s"]) == (3617, 7516, 158.9)
    assert Event(event_type="FREITEXT").to_dict()["event_type"] == "FREITEXT"
    assert EventType.OPENCODE_CALL.value == "OPENCODE_CALL"


# --- Trajektorien, Suchausschluss, Aufräumen (#46) ---------------------------------------

def test_repair_trajectory_is_written_outside_the_workspace_and_scrubbed(tmp_path):
    supervisor, _, _, _, workspace, failure = _mismatch_case(tmp_path)
    runs = tmp_path / "runs"
    supervisor._runs_dir = str(runs)
    supervisor._design_state.metadata["request_full"] = f"Lauflicht, Pfad {workspace}/PROMPT.md"
    supervisor._start_trajectory()
    path = supervisor._trajectory.path
    run(supervisor._handle_failure(DesignStage.STATIC_CHECK, failure))
    supervisor._finish_trajectory(AgentResult(task_id="s", status=AgentStatus.COMPLETED, outputs={"message": "ok"}))

    assert path.parent == runs / "proj" and not str(path).startswith(str(workspace))
    entries = [json.loads(line) for line in path.read_text().splitlines()]
    assert [e["kind"] for e in entries] == ["run_started", "repair", "run_finished"]
    assert "<workspace>/PROMPT.md" in entries[0]["request"] and str(workspace) not in path.read_text()
    repair = entries[1]
    assert repair["failure_type"] == "model_mismatch" and repair["origin"]
    assert repair["verdict"]["cause"] == "generated_check"
    assert repair["diff"] == ""  # erzeugte Vergleichs-Testbench zählt nicht


def test_trajectory_diff_contains_changed_sources():
    from src.services.trajectory import unified_diff

    diff = unified_diff({"src/a.vhd": "x <= '0';\n"}, {"src/a.vhd": "x <= '1';\n", "src/b.vhd": "neu\n"})
    assert "-x <= '0';" in diff and "+x <= '1';" in diff and "+++ b/src/b.vhd" in diff


def test_no_trajectory_without_runs_dir(tmp_path):
    supervisor, _, _, _, _, _ = _mismatch_case(tmp_path)
    supervisor._runs_dir = ""
    supervisor._start_trajectory()
    assert supervisor._trajectory is None


def test_workspace_ignore_hides_tool_artifacts_from_search(tmp_path):
    from src.services.opencode_service import WORKSPACE_IGNORE, ensure_workspace_ignore

    ensure_workspace_ignore(str(tmp_path))  # ohne eigenes Repo: nichts schreiben
    assert not (tmp_path / ".gitignore").exists()
    (tmp_path / ".git").mkdir()
    (tmp_path / ".gitignore").write_text("eigene_regel\n")
    ensure_workspace_ignore(str(tmp_path))
    ensure_workspace_ignore(str(tmp_path))
    lines = (tmp_path / ".gitignore").read_text().splitlines()
    assert lines[0] == "eigene_regel" and all(lines.count(e) == 1 for e in WORKSPACE_IGNORE)
    assert "build/" in lines and ".opencode/node_modules/" in lines


def test_cleanup_keeps_bitstream_reports_and_last_log(tmp_path):
    from src.services.workspace_cleanup import cleanup_build_intermediates

    files = [
        "build/ghdl/top/work-obj08.cf", "build/synthesis/top.v", "work-obj08.cf", "vivado.jou",
        "build/bitstream/vivado_logs_archive/1/vivado.log", "build/bitstream/top.bit",
        "build/bitstream/top.mcs", "build/bitstream/timing.rpt", "build/bitstream/synthesis_cache.json",
        "build/bitstream/vivado_logs/vivado.log", "src/top.vhd",
    ]
    for rel in files:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("x")
    removed = cleanup_build_intermediates(tmp_path)
    assert {"build/ghdl/", "build/synthesis/", "work-obj08.cf", "vivado.jou"} <= set(removed)
    for kept in files[5:]:
        assert (tmp_path / kept).is_file(), kept
    assert not (tmp_path / "build/ghdl").exists() and not (tmp_path / "build/bitstream/vivado_logs_archive").exists()


def test_scrubber_replaces_the_full_hostname_before_the_user_name(tmp_path, monkeypatch):
    from src.services import trajectory

    monkeypatch.setattr(trajectory.socket, "gethostname", lambda: "anna-Laptop-15")
    monkeypatch.setenv("USER", "anna")
    scrub = trajectory.Scrubber(tmp_path)
    assert scrub.text(f"Host: anna-Laptop-15, user anna, {tmp_path}/src") == "Host: <host>, user <host>, <workspace>/src"


def test_trajectory_records_model_plan_and_final_sources(tmp_path):
    supervisor, _, _, _, workspace, _ = _mismatch_case(tmp_path)
    supervisor._runs_dir = str(tmp_path / "runs")
    supervisor._config.update({"opencode_model": "opencode/muse-spark", "fallback_model": "opencode/mimo"})
    supervisor._current_task.inputs["plan_manifest"] = {
        "top_entity": "top", "modules": [{"entity": "top", "type": "sequential", "depends_on": [], "ports": []}],
        "requirements": [{"id": "R1"}], "plan_attempts": {"count": 2, "problems": [["cycle"]]},
        "board_checks": [{"setup": "BTN0", "expected": "LED an"}],
    }
    supervisor._start_trajectory()
    path = supervisor._trajectory.path
    supervisor._finish_trajectory(AgentResult(task_id="s", status=AgentStatus.COMPLETED, outputs={"message": "ok"}))

    entries = {e["kind"]: e for e in map(json.loads, path.read_text().splitlines())}
    assert entries["run_started"]["model"] == "opencode/muse-spark"
    plan = entries["plan"]
    assert plan["modules"] == [{"entity": "top", "type": "sequential", "depends_on": []}]
    assert plan["attempts"]["count"] == 2 and plan["requirements"] == 1 and plan["board_checks"]
    assert entries["run_finished"]["sources"]["src/top.vhd"] == "-- korrekt\n"
