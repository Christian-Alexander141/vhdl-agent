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
