"""Tests für Maßnahme A (Referenzmodell, differentieller Test) und B (Mutationsanalyse).

Herkunft der Ideen und Abgrenzung des Eigenanteils: docs/doku.html, Abschnitt 16.
"""
import asyncio
import shutil
from pathlib import Path

import pytest

from src.domain.agents import reference_model as rm
from src.domain.agents.mutation import generate_mutants, run_mutation_analysis
from src.domain.agents.repair_routing import RepairTarget
from src.domain.models import ArchitectureInfo, ModuleInfo
from src.infrastructure.validation.ghdl_validator import GHDLValidator
from tests.test_multi_agent_gates import make_supervisor, run

pytestmark = pytest.mark.skipif(shutil.which("ghdl") is None, reason="GHDL nicht installiert")

COUNTER = """library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
entity counter4 is
    port (clk : in std_logic; rst : in std_logic; en : in std_logic; count : out std_logic_vector(3 downto 0));
end entity;
architecture rtl of counter4 is
    signal q : unsigned(3 downto 0) := (others => '0');
begin
    process (clk)
    begin
        if rising_edge(clk) then
            if rst = '1' then
                q <= (others => '0');
            elsif en = '1' then
                q <= q + 1;
            end if;
        end if;
    end process;
    count <= std_logic_vector(q);
end architecture;
"""

COUNTER_MODEL = """
class ReferenceModel:
    SUGGESTED_CYCLES = 120
    def reset(self):
        self.count = 0
    def step(self, inputs):
        if inputs["rst"]:
            self.count = 0
        elif inputs["en"]:
            self.count = (self.count + 1) % 16
        return {"count": self.count}
"""

COUNTER_MODEL_TEST = """
from reference_model import ReferenceModel
def test_counts():
    m = ReferenceModel(); m.reset()
    m.step({"rst": 1, "en": 1})
    assert m.step({"rst": 0, "en": 1})["count"] == 1
"""

XOR_GATE = """library ieee;
use ieee.std_logic_1164.all;
entity parity is
    port (a : in std_logic_vector(2 downto 0); p : out std_logic);
end entity;
architecture rtl of parity is
begin
    p <= a(0) xor a(1) xor a(2);
end architecture;
"""

WEAK_TB = """library ieee;
use ieee.std_logic_1164.all;
entity counter4_tb is end entity;
architecture sim of counter4_tb is
    signal clk, rst, en : std_logic := '0';
    signal count : std_logic_vector(3 downto 0);
begin
    dut: entity work.counter4 port map (clk => clk, rst => rst, en => en, count => count);
    process
    begin
        rst <= '1';
        clk <= '0'; wait for 5 ns; clk <= '1'; wait for 5 ns;
        assert true report "nur ein Alibi-Check" severity error;
        report "TB_COMPLETE" severity note;
        wait;
    end process;
end architecture;
"""


def _workspace(tmp_path, design: str, top: str, model: str | None = COUNTER_MODEL, model_test: str | None = COUNTER_MODEL_TEST):
    (tmp_path / "src").mkdir(parents=True)
    (tmp_path / "src" / f"{top}.vhd").write_text(design)
    if model is not None:
        (tmp_path / "model").mkdir()
        (tmp_path / "model" / "reference_model.py").write_text(model)
        if model_test is not None:
            (tmp_path / "model" / "test_reference_model.py").write_text(model_test)
    return str(tmp_path)


# --- A: Stimulus und Ports ---------------------------------------------------

def test_reset_polarity_and_clock_detection():
    assert rm.is_clock("clk") and rm.is_clock("sys_clk") and rm.is_clock("clk_i")
    assert not rm.is_clock("clk_div_en") and not rm.is_clock("clk_en")
    assert rm.is_reset("rst") and rm.is_reset("reset_n") and rm.is_reset("rst_n")
    assert rm.reset_active_low("rst_n") and rm.reset_active_low("resetn") and not rm.reset_active_low("rst")


def test_stimulus_is_deterministic_and_resets_at_start():
    ports = [rm.ModelPort("clk", "in", 1, "std_logic"), rm.ModelPort("rst_n", "in", 1, "std_logic"),
             rm.ModelPort("d", "in", 8, "std_logic_vector"), rm.ModelPort("q", "out", 8, "std_logic_vector")]
    first = rm.generate_stimulus(ports, 50, seed=3)
    assert first == rm.generate_stimulus(ports, 50, seed=3)
    assert [row["rst_n"] for row in first[:2]] == [0, 0]  # active low im Reset
    assert all("clk" not in row for row in first)


def test_combinational_stimulus_is_exhaustive_for_small_inputs():
    ports = [rm.ModelPort("a", "in", 3, "std_logic_vector"), rm.ModelPort("p", "out", 1, "std_logic")]
    vectors = rm.generate_stimulus(ports, 10)
    assert sorted(v["a"] for v in vectors) == list(range(8))


def test_entity_ports_resolve_generic_widths(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "reg.vhd").write_text(
        "entity reg is generic (W : integer := 6); port (clk : in std_logic; d : in unsigned(W-1 downto 0); "
        "q : out unsigned(W-1 downto 0)); end entity;\narchitecture rtl of reg is begin end architecture;\n"
    )
    ports, reason = rm.entity_ports(str(tmp_path), "reg")
    assert reason == "" and [(p.name, p.width, p.base) for p in ports] == [
        ("clk", 1, "std_logic"), ("d", 6, "unsigned"), ("q", 6, "unsigned"),
    ]


# --- A: Vergleichs-Testbench mit echtem GHDL ----------------------------------

def test_model_testbench_passes_correct_design(tmp_path):
    ws = _workspace(tmp_path, COUNTER, "counter4")
    status = rm.write_model_testbench(ws, "counter4")
    assert status["status"] == "written" and status["cycles"] == 120
    assert GHDLValidator().validate(ws).passed


def test_model_testbench_reports_cycle_port_and_values_for_wrong_design(tmp_path):
    wrong = COUNTER.replace("q <= q + 1;", "q <= q + 2;")
    ws = _workspace(tmp_path, wrong, "counter4")
    rm.write_model_testbench(ws, "counter4")
    result = GHDLValidator().validate(ws)
    assert not result.passed
    line = rm.mismatch_line(result.details.get("error", ""))
    assert line.startswith("MODEL_MISMATCH cycle=") and "port=count" in line and "expected=" in line and "got=" in line


def test_model_testbench_for_combinational_design(tmp_path):
    model = "class ReferenceModel:\n    def reset(self): pass\n    def step(self, i):\n        a = i['a']\n        return {'p': bin(a).count('1') % 2}\n"
    test = "from reference_model import ReferenceModel\ndef test_p():\n    assert ReferenceModel().step({'a': 3})['p'] == 0\n"
    ws = _workspace(tmp_path, XOR_GATE, "parity", model, test)
    assert rm.write_model_testbench(ws, "parity")["status"] == "written"
    assert GHDLValidator().validate(ws).passed


def test_invalid_model_never_produces_a_testbench(tmp_path):
    broken = COUNTER_MODEL.replace('return {"count": self.count}', 'return {"zaehler": self.count}')
    ws = _workspace(tmp_path, COUNTER, "counter4", broken)
    status = rm.write_model_testbench(ws, "counter4")
    assert status["status"] == "model_error" and "count" in status["reason"]
    assert not (tmp_path / "tests" / "counter4_model_tb.vhd").exists()


def test_failing_model_selftest_blocks_the_model(tmp_path):
    ws = _workspace(tmp_path, COUNTER, "counter4", model_test="def test_wrong():\n    assert 1 == 2\n")
    status = rm.write_model_testbench(ws, "counter4")
    assert status["status"] == "model_error" and "Selbsttest" in status["reason"]


def test_missing_model_is_skipped(tmp_path):
    ws = _workspace(tmp_path, COUNTER, "counter4", model=None)
    assert rm.write_model_testbench(ws, "counter4")["status"] == "skipped"


# --- A: Einbindung in den Supervisor -----------------------------------------

def _set_top(supervisor, name="counter4"):
    supervisor._design_state.architecture = ArchitectureInfo(
        version=1, top_module=name, modules=[ModuleInfo(name=name)],
    )


def test_model_mismatch_is_classified_with_cycle_details(tmp_path):
    supervisor, _, _ = make_supervisor(tmp_path)
    _set_top(supervisor)
    diag = supervisor._classify_model_mismatch({
        "message": "GHDL simulation failed for counter4_model_tb",
        "details": {"error": "x.vhd:1:@40ns:(assertion error): MODEL_MISMATCH cycle=3 port=count expected=0011 got=0110"},
    })
    assert diag["failure_type"] == "model_mismatch"
    assert "cycle=3 port=count" in diag["message"] and diag["modules"] == ["counter4"]


def test_repeated_model_mismatch_escalates_to_model_review_once(tmp_path):
    supervisor, _, _ = make_supervisor(tmp_path)
    targets = []
    for _ in range(4):
        diagnosis = {}
        targets.append(supervisor._model_mismatch_target(diagnosis, RepairTarget.HDL))
        if targets[-1] == RepairTarget.VERIFICATION:
            assert diagnosis["regenerate_model"] is True
            supervisor._design_state.metadata["model_regenerated"] = True
    assert targets == [RepairTarget.HDL, RepairTarget.HDL, RepairTarget.VERIFICATION, RepairTarget.HDL]


def test_static_check_writes_and_runs_the_model_testbench(tmp_path):
    supervisor, fs, _ = make_supervisor(tmp_path, config={"enforce_contracts": False})
    _set_top(supervisor)
    ws = Path(fs.workspace_path("proj"))
    _workspace(ws, COUNTER.replace("q <= q + 1;", "q <= q + 3;"), "counter4")
    supervisor._design_state.current_stage = supervisor._design_state.current_stage.IMPLEMENTING
    result = run(supervisor._run_static_check())
    assert supervisor._design_state.metadata["model_testbench"]["status"] == "written"
    assert result.status.value == "FAILED"
    assert "MODEL_MISMATCH" in result.diagnostics[0]["details"]["error"]


def test_no_model_agent_means_no_model_and_no_failure(tmp_path):
    supervisor, _, _ = make_supervisor(tmp_path)
    _set_top(supervisor)
    status = run(supervisor._ensure_reference_model())
    assert status["status"] == "skipped"


def test_contract_ports_for_model_instruction():
    from src.agents.verification import VerificationAgent

    ports = VerificationAgent._contract_ports({
        "parameters": {"W": 8},
        "ports": {"clk": {"direction": "in", "type": "std_logic"},
                  "d": {"direction": "in", "type": "std_logic_vector(W-1 downto 0)"},
                  "q": {"direction": "out", "type": "signed(3 downto 0)"}},
    })
    assert [(p.name, p.width, p.base) for p in ports] == [("clk", 1, "std_logic"), ("d", 8, "std_logic_vector"), ("q", 4, "signed")]
    text = rm.model_interface_text(ports)
    assert "Takt – NICHT in inputs" in text and "mit Vorzeichen" in text


# --- B: Mutationsanalyse -----------------------------------------------------

def test_mutants_are_deterministic_single_changes_outside_comments_and_declarations():
    source = COUNTER.replace("q <= q + 1;", "q <= q + 1; -- if a = b then")
    mutants = generate_mutants({"src/counter4.vhd": source}, max_mutants=10)
    assert mutants == generate_mutants({"src/counter4.vhd": source}, max_mutants=10)
    assert {m.operator for m in mutants} >= {"change_constant", "negate_condition"}
    for m in mutants:
        diff = [(a, b) for a, b in zip(source.splitlines(), m.text.splitlines()) if a != b]
        assert len(diff) == 1                                 # genau eine Änderung
        assert "-- if a = b then" in m.text                    # Kommentar unverändert
        assert "rising_edge" not in m.after or m.operator == "change_constant"
        assert m.line > source.splitlines().index("architecture rtl of counter4 is")


def test_strong_suite_kills_mutants_weak_suite_does_not(tmp_path):
    strong = tmp_path / "strong"
    _workspace(strong, COUNTER, "counter4")
    rm.write_model_testbench(str(strong), "counter4")
    report = run_mutation_analysis(str(strong), GHDLValidator(), max_mutants=6)
    assert report["score"] == 1.0 and not report["survived"]

    weak = tmp_path / "weak"
    _workspace(weak, COUNTER, "counter4", model=None)
    (weak / "tests").mkdir()
    (weak / "tests" / "counter4_tb.vhd").write_text(WEAK_TB)
    report = run_mutation_analysis(str(weak), GHDLValidator(), max_mutants=6)
    assert report["score"] is not None and report["score"] < 0.5
    assert all(s["description"].startswith("src/counter4.vhd:") for s in report["survived"])


def _weak_supervisor(tmp_path):
    supervisor, fs, _ = make_supervisor(tmp_path, config={"min_mutation_score": 0.6, "max_mutants": 6})
    _set_top(supervisor)
    ws = Path(fs.workspace_path("proj"))
    _workspace(ws, COUNTER, "counter4", model=None)
    (ws / "tests").mkdir()
    (ws / "tests" / "counter4_tb.vhd").write_text(WEAK_TB)
    return supervisor


def test_mutation_gate_requests_one_testbench_repair_then_only_warns(tmp_path):
    supervisor = _weak_supervisor(tmp_path)
    first = asyncio.new_event_loop().run_until_complete(supervisor._mutation_gate())
    assert first["failure_type"] == "weak_testbench" and first["modules"] == ["counter4"]
    assert "undetected mutants" in first["message"]

    second = asyncio.new_event_loop().run_until_complete(supervisor._mutation_gate())
    assert second is None
    assert "Mutationsquote" in supervisor._design_state.metadata["mutation_warning"]


def test_mutation_gate_is_off_by_default_in_supervisor(tmp_path):
    supervisor, _, _ = make_supervisor(tmp_path)
    assert asyncio.new_event_loop().run_until_complete(supervisor._mutation_gate()) is None


def test_model_files_written_before_timeout_are_accepted_if_selftest_passes(tmp_path):
    """Im Probelauf schrieb das Modell beide Dateien und lief dann ins Zeitlimit."""
    from src.agents.verification import VerificationAgent
    from src.domain.agents import AgentTask
    from src.services.opencode_task_runner import OpenCodeDelivery

    class TimeoutRunner:
        def run(self, **kw):
            model = Path(kw["workspace"]) / "model"
            model.mkdir(exist_ok=True)
            (model / "reference_model.py").write_text(COUNTER_MODEL)
            (model / "test_reference_model.py").write_text(COUNTER_MODEL_TEST)
            return OpenCodeDelivery(ok=False, stage="reference_model", reason="timeout")

    agent = VerificationAgent(filesystem_service=None, opencode_service=None, task_runner=TimeoutRunner())
    arch = {"top_module": "counter4", "modules": [{"name": "counter4", "ports": {
        "clk": {"direction": "in", "type": "std_logic"}, "rst": {"direction": "in", "type": "std_logic"},
        "en": {"direction": "in", "type": "std_logic"}, "count": {"direction": "out", "type": "std_logic_vector(3 downto 0)"},
    }}]}
    result = run(agent.execute(AgentTask(id="m", type="reference_model", project_id="p",
                                         inputs={"workspace": str(tmp_path), "architecture": arch, "request_full": "x"})))
    assert result.outputs["reference_model"]["status"] == "ready"
