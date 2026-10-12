"""Vorfilter, Weitergabe und Kontrollfluss (docs/doku.html, #30-#37).

Anlass: Lauf gray-countdown 2026-10-11 (über 5 h ohne Ergebnis). Ein
Vivado-Konfigurationsfehler beim Flashen wurde als "unknown" diagnostiziert,
an die HDL-Reparatur gegeben, das Modul neu geschrieben und die Architektur
überarbeitet; nach jedem ergebnislosen Versuch lief die ganze Pipeline samt
Synthese erneut.
"""
import asyncio
import json
import shutil
from pathlib import Path

import pytest

from src.agents.debug import DebugAgent
from src.domain.agents import AgentResult, AgentStatus, AgentTask
from src.domain.agents.repair_routing import RepairTarget
from src.domain.agents.triage import key_lines, triage
from src.domain.models import DesignStage

from tests.test_multi_agent_gates import THREE_MODULES, make_supervisor, run, set_architecture

GRAY_FLASH_ERROR = (
    'Vivado JTAG programming failed: ERROR: [Writecfgmem 68-20] SPI_BUSWIDTH property is set to "1" on bitfile '
    "/home/alex/Dokumente/Github/vhdl-agent/projects/gray-countdown-5ace9d/build/bitstream/gray_countdown.bit. "
    'This property has to be set to "4" to generate a configuration memory file for the SPIX4 interface.'
)


# --- Vorfilter -------------------------------------------------------------------

def test_flash_config_error_is_toolchain_not_design_and_names_no_module():
    """Genau der Fall aus dem Lauf: früher 'unknown' + Modul aus dem .bit-Pfad."""
    result = triage([{"type": "flash_failure", "message": GRAY_FLASH_ERROR, "board_detected": True}],
                    "flash", ["gray_countdown"])
    assert result["failure_type"] == "bitstream_config_error"
    assert result["origin"] == "toolchain" and result["repair_target"] == "fpga"
    assert result["modules"] == []


def test_missing_board_is_a_hardware_problem():
    result = triage([{"message": "Kein passendes FPGA-Board via JTAG erkannt. Erwartet: xc7s50"}], "flash", ["top"])
    assert result["failure_type"] == "flash_error" and result["repair_target"] == "human"


def test_ghdl_error_lines_come_from_details_and_name_the_module():
    diagnostic = {
        "type": "validation_failure", "stage": "static_check",
        "message": "GHDL analysis failed for alu.vhd",
        "details": {"error": "src/alu.vhd:12:5:error: no declaration for \"foo\"\n\x1b[0m"},
    }
    result = triage([diagnostic], "static_check", ["alu", "regfile"])
    assert any("no declaration for" in line for line in result["key_lines"])
    assert result["modules"] == ["alu"]
    assert result["origin"] == "design"
    assert not any("\x1b" in line for line in result["key_lines"])


def test_failed_assertion_from_simulation_output_reaches_the_diagnosis():
    diagnostic = {
        "message": "GHDL simulation failed for alu_tb (runtime error or failed assertion)",
        "details": {"error": "../../src/ieee2008/numeric_std-body.vhdl:1873:7:@0ms:(assertion warning): "
                             "NUMERIC_STD.\"=\": metavalue detected, returning FALSE\n"
                             "tests/alu_tb.vhd:40:7:@20ns:(assertion error): FAIL y expected 3 got 2\n"},
    }
    lines = key_lines(diagnostic)
    assert any("FAIL y expected 3 got 2" in line for line in lines)
    assert not any("metavalue" in line for line in lines)
    assert triage([diagnostic], "simulation", ["alu"])["modules"] == ["alu"]


def test_explicit_failure_type_of_the_producer_wins():
    result = triage([{"failure_type": "requirement_gap", "message": "x", "modules": ["top"]}], "validation", ["top"])
    assert result["failure_type"] == "requirement_gap" and result["modules"] == ["top"]


def test_debug_agent_uses_the_prefilter():
    task = AgentTask(id="d", type="diagnose", project_id="p", inputs={
        "diagnostics": [{"type": "flash_failure", "message": GRAY_FLASH_ERROR, "board_detected": True}],
        "current_stage": "flash", "architecture": {"modules": [{"name": "gray_countdown"}]},
    })
    diagnosis = asyncio.new_event_loop().run_until_complete(DebugAgent().execute(task)).outputs["diagnosis"]
    assert diagnosis["failure_type"] == "bitstream_config_error"
    assert diagnosis["origin"] == "toolchain" and diagnosis["suspected_modules"] == []
    assert "not an HDL problem" in diagnosis["recommended_action"]


def test_fpga_agent_classifies_flash_failures_and_keeps_vivado_output(tmp_path):
    from src.agents.fpga import FPGAAgent
    from src.domain.ports.flash_service import FlashResult

    class _Flash:
        def toolchain_available(self):
            return True

        def flash(self, *a, **k):
            return FlashResult(passed=False, message=GRAY_FLASH_ERROR[:120], board_detected=True, board_count=1,
                               details={"stderr": GRAY_FLASH_ERROR, "stdout": "INFO ..."})

    agent = FPGAAgent(filesystem_service=None)
    agent._vivado_flash = agent._openfpgaloader_flash = _Flash()
    bit = tmp_path / "top.bit"
    bit.write_bytes(b"x")
    task = AgentTask(id="f", type="flash", project_id="p",
                     inputs={"bitstream_path": str(bit), "target_fpga": "arty_s7_50", "workspace": str(tmp_path)})
    result = asyncio.new_event_loop().run_until_complete(agent.execute(task))
    diagnostic = result.diagnostics[0]
    assert diagnostic["failure_type"] == "bitstream_config_error"
    assert "SPI_BUSWIDTH" in diagnostic["details"]["stderr"]


# --- Board-Konfiguration und Synthese-Cache --------------------------------------------

def test_build_script_sets_board_config_even_with_a_project_xdc(tmp_path):
    from src.infrastructure.synthesis.vivado_synthesis import VivadoBitstreamService

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "top.vhd").write_text("entity top is end;")
    (tmp_path / "constraints").mkdir()
    (tmp_path / "constraints" / "top.xdc").write_text("set_property -dict {PACKAGE_PIN F14 IOSTANDARD LVCMOS33} [get_ports clk]\n")
    tcl = VivadoBitstreamService()._generate_tcl_script(
        src_files=[tmp_path / "src" / "top.vhd"], top_entity="top", part="xc7s50csga324-1",
        bitstream_path=tmp_path / "build" / "top.bit", clock_hz=12_000_000, workspace=tmp_path,
        board_name="arty_s7_50",
    )
    assert "top.xdc" in tcl and "auto_generated" not in tcl
    synth, config, bitstream = (tcl.index("synth_design"), tcl.index("SPI_BUSWIDTH 4"), tcl.index("write_bitstream"))
    assert synth < config < bitstream and "CONFIG_MODE SPIx4" in tcl


def test_synthesis_cache_depends_on_sources_and_constraints(tmp_path):
    from src.agents.fpga import read_synthesis_cache, synthesis_digest, write_synthesis_cache

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "top.vhd").write_text("entity top is end;")
    (tmp_path / "constraints").mkdir()
    (tmp_path / "constraints" / "top.xdc").write_text("# pins")
    bit = tmp_path / "build" / "bitstream" / "top.bit"
    bit.parent.mkdir(parents=True)
    bit.write_bytes(b"bit")
    digest = synthesis_digest(str(tmp_path), "arty_s7_50", True)
    write_synthesis_cache(str(tmp_path), digest, {"bitstream_path": str(bit), "synthesis_result": {"status": "passed"}})
    assert read_synthesis_cache(str(tmp_path), synthesis_digest(str(tmp_path), "arty_s7_50", True))
    (tmp_path / "constraints" / "auto_generated.xdc").write_text("# abgeleitet")
    assert read_synthesis_cache(str(tmp_path), synthesis_digest(str(tmp_path), "arty_s7_50", True))
    (tmp_path / "constraints" / "top.xdc").write_text("# pins geändert")
    assert read_synthesis_cache(str(tmp_path), synthesis_digest(str(tmp_path), "arty_s7_50", True)) is None


# --- Eskalation und Weitergabe --------------------------------------------------------------

def test_toolchain_failures_never_rewrite_modules_or_the_architecture(tmp_path):
    supervisor, _, _ = make_supervisor(tmp_path, config={"repair_policy": "persistent"})
    actions = [
        supervisor._escalate("bitstream_config_error", {"origin": "toolchain"}, RepairTarget.FPGA)[1]
        for _ in range(6)
    ]
    assert "regenerate" not in actions and "rearchitect" not in actions
    assert actions[-1] == "human"


def test_each_attempt_knows_the_previous_attempts_and_their_outcome(tmp_path):
    supervisor, _, _ = make_supervisor(tmp_path, config={"repair_policy": "persistent"})
    first = {"suspected_modules": ["alu"]}
    supervisor._escalate("syntax_error", first, RepairTarget.HDL)
    supervisor._record_attempt_outcome("Zeitlimit (keine Änderung)")
    second = {"suspected_modules": ["alu"]}
    supervisor._escalate("syntax_error", second, RepairTarget.HDL)
    assert second["attempt"] == 2
    assert second["previous_attempts"] == [{"attempt": 1, "action": "repair", "outcome": "Zeitlimit (keine Änderung)"}]


class _NoChangeHDL:
    """Liefert nie etwas (z. B. abgelehnte Lieferung), ändert keine Datei."""

    def __init__(self):
        self.calls = []

    async def execute(self, task):
        self.calls.append(task)
        return AgentResult(task_id=task.id, status=AgentStatus.FAILED, error_message="Lieferung abgelehnt")


def _failing_static_check(supervisor, fs):
    src = Path(fs.workspace_path("proj")) / "src"
    src.mkdir(parents=True, exist_ok=True)
    (src / "alu.vhd").write_text("-- alu\n")
    supervisor._design_state.architecture.modules[0].files = ["src/alu.vhd"]
    supervisor._design_state.current_stage = DesignStage.STATIC_CHECK
    return AgentResult(task_id="s", status=AgentStatus.FAILED, error_message="x", diagnostics=[
        {"message": "GHDL analysis failed for alu.vhd", "details": {"error": "src/alu.vhd:3:1:error: syntax error"}}])


def test_unchanged_failed_repair_escalates_without_rerunning_the_pipeline(tmp_path):
    hdl = _NoChangeHDL()
    supervisor, fs, events = make_supervisor(tmp_path, hdl_agent=hdl, debug_agent=DebugAgent(),
                                             config={"repair_policy": "persistent"})
    set_architecture(supervisor, THREE_MODULES, "cpu")
    failure = _failing_static_check(supervisor, fs)
    result = run(supervisor._handle_failure(DesignStage.STATIC_CHECK, failure))
    # Alle Stufen in einem Aufruf, am Ende der Mensch mit Zusammenfassung
    assert len(hdl.calls) >= 3 and result.status == AgentStatus.BLOCKED
    assert "REPAIR_RETRY" in events.types()
    outcomes = [e.get("outcome", "") for e in supervisor._design_state.metadata["escalation_log"] if e["action"] != "human"]
    assert outcomes and all("keine Änderung" in o for o in outcomes)


def test_repair_with_changes_returns_to_the_pipeline_immediately(tmp_path):
    from tests.test_multi_agent_gates import RecordingHDLAgent

    hdl = RecordingHDLAgent()
    supervisor, fs, _ = make_supervisor(tmp_path, hdl_agent=hdl, debug_agent=DebugAgent(),
                                        config={"repair_policy": "persistent"})
    set_architecture(supervisor, THREE_MODULES, "cpu")
    failure = _failing_static_check(supervisor, fs)
    result = run(supervisor._handle_failure(DesignStage.STATIC_CHECK, failure))
    assert result.status == AgentStatus.COMPLETED and len(hdl.calls) == 1
    assert supervisor._design_state.current_stage == DesignStage.STATIC_CHECK


def test_bitstream_config_error_is_first_rebuilt_without_a_language_model(tmp_path):
    from src.agents.fpga import SYNTHESIS_CACHE

    hdl = _NoChangeHDL()
    supervisor, fs, _ = make_supervisor(tmp_path, hdl_agent=hdl, debug_agent=DebugAgent(),
                                        config={"repair_policy": "persistent"})
    set_architecture(supervisor, [{"name": "gray_countdown", "type": "sequential"}], "gray_countdown")
    cache = Path(fs.workspace_path("proj")) / SYNTHESIS_CACHE
    cache.parent.mkdir(parents=True)
    cache.write_text("{}")
    supervisor._design_state.current_stage = DesignStage.FPGA_PROGRAMMING
    failure = AgentResult(task_id="f", status=AgentStatus.FAILED, error_message="Flash failed", diagnostics=[
        {"type": "flash_failure", "stage": "flash", "message": GRAY_FLASH_ERROR, "board_detected": True}])
    result = run(supervisor._handle_failure(DesignStage.FPGA_PROGRAMMING, failure))
    assert result.status == AgentStatus.COMPLETED and result.outputs["action"] == "rebuild_bitstream"
    assert hdl.calls == [] and not cache.exists()
    assert supervisor._design_state.current_stage == DesignStage.SYNTHESIZING


def test_stage_change_never_jumps_to_another_phase(tmp_path):
    """Früher VALIDATING -> SYNTHESIZING, wenn STATIC_CHECK nicht direkt erlaubt war."""
    supervisor, _, _ = make_supervisor(tmp_path)
    supervisor._design_state.current_stage = DesignStage.VALIDATING
    supervisor._safe_transition_to(DesignStage.STATIC_CHECK)
    assert supervisor._design_state.current_stage == DesignStage.STATIC_CHECK


def test_architecture_repair_brief_matches_the_failure_class(tmp_path):
    supervisor, _, _ = make_supervisor(tmp_path)
    missing = supervisor._architecture_feedback({"failure_type": "requirement_missing", "evidence": ["RGB rot bei 0"]})
    assert "fehlen im Plan" in missing and "passen aber nicht zusammen" not in missing and "RGB rot bei 0" in missing
    design = supervisor._architecture_feedback({"failure_type": "functional_simulation_error", "suspected_modules": ["alu"]})
    assert "gescheitert" in design and "passen aber nicht zusammen" not in design


# --- Aufträge an die Agenten ------------------------------------------------------------

def test_repair_prompt_carries_attempt_history_and_toolchain_context(tmp_path):
    from src.agents.hdl import HDLAgent

    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "repair_notes.md").write_text("Ursache liegt in der XDC")
    info = {"stage": "flash", "origin": "toolchain",
            "previous_attempts": [{"attempt": 1, "action": "repair", "outcome": "Zeitlimit (keine Änderung)"}]}
    history = HDLAgent._repair_history_block(str(tmp_path), info)
    assert "attempt 1: repair -> Zeitlimit" in history and "Ursache liegt in der XDC" in history
    toolchain = HDLAgent._toolchain_block(info)
    assert "constraints/*.xdc" in toolchain and "Do NOT run Vivado" in toolchain
    assert HDLAgent._toolchain_block({"stage": "simulation", "origin": "design"}) == ""
    # Notizen nur, wenn sie zu einem vorherigen Versuch dieses Fehlers gehören
    assert HDLAgent._repair_history_block(str(tmp_path), {"stage": "simulation"}) == ""


class _TbRunner:
    def __init__(self, content):
        self.content = content
        self.calls = []

    def run(self, **kw):
        from src.services.opencode_task_runner import OpenCodeDelivery

        self.calls.append(kw)
        path = Path(kw["workspace"]) / kw["expected_files"][0]
        path.write_text(self.content)
        return OpenCodeDelivery(ok=True, stage=kw["stage"], files={kw["expected_files"][0]: self.content})


class _Validator:
    def __init__(self, passed):
        self.passed = passed

    def validate(self, workspace, domain="vhdl"):
        from src.domain.ports.validation_service import ValidationResult

        return ValidationResult(passed=self.passed, message="ok" if self.passed else "GHDL analysis failed",
                                details={"error": "tests/top_tb.vhd:1:1:error: bad"})


def _verification_agent(tmp_path, content, passed):
    from src.agents.verification import VerificationAgent
    from src.services.filesystem_service import LocalFileSystemService

    agent = VerificationAgent(filesystem_service=LocalFileSystemService(base_dir=str(tmp_path)), opencode_service=None,
                              task_runner=_TbRunner(content))
    agent._validator = _Validator(passed)
    (tmp_path / "src").mkdir(exist_ok=True)
    (tmp_path / "src" / "top.vhd").write_text("entity top is port (a : in bit); end;\narchitecture r of top is begin end;")
    (tmp_path / "tests").mkdir(exist_ok=True)
    (tmp_path / "tests" / "top_tb.vhd").write_text("-- alte testbench mit REQ R1\n")
    (tmp_path / "PROMPT.md").write_bytes("Zähler".encode())
    return agent


def _tb_task(tmp_path):
    return AgentTask(id="t", type="generate_testbench", project_id="p", inputs={
        "module": {"name": "top"}, "workspace": str(tmp_path), "domain": "vhdl",
        "requirement_hints": ["R2: Bei 0 leuchtet RGB rot"],
    })


def test_testbench_repair_lets_opencode_write_the_file(tmp_path):
    """Früher wurde die Konsolenausgabe (mit ANSI-Codes) als Code übernommen."""
    good = "entity top_tb is end;\narchitecture t of top_tb is begin\n  dut: entity work.top port map (a => '0');\nend;\n"
    agent = _verification_agent(tmp_path, good, passed=True)
    result = asyncio.new_event_loop().run_until_complete(agent.execute(_tb_task(tmp_path)))
    assert result.status == AgentStatus.COMPLETED
    call = agent._task_runner.calls[0]
    assert call["stage"] == "repair_testbench" and call["expected_files"] == ["tests/top_tb.vhd"]
    assert "Behalte alle bestehenden Prüfungen" in call["task_instruction"]
    assert "R2: Bei 0 leuchtet RGB rot" in call["task_instruction"]
    assert call["request_full"] == "Zähler"


def test_rejected_testbench_restores_the_previous_one(tmp_path):
    bad = "entity top_tb is end;\narchitecture t of top_tb is begin\n  dut: entity work.top port map (a => '0');\nend;\n"
    agent = _verification_agent(tmp_path, bad, passed=False)
    result = asyncio.new_event_loop().run_until_complete(agent.execute(_tb_task(tmp_path)))
    assert result.status == AgentStatus.FAILED
    assert (tmp_path / "tests" / "top_tb.vhd").read_text() == "-- alte testbench mit REQ R1\n"


def test_reset_concept_from_the_plan_is_normalized():
    from src.services.plan_service import PlanService

    manifest = {"reset_concept": "SYNC_ACTIVE_HIGH", "modules": []}
    PlanService._autofix(manifest)
    assert manifest["reset_concept"] == "sync_active_high"
    invalid = {"reset_concept": "sync_active_high|async_active_high", "modules": []}
    PlanService._autofix(invalid)
    assert "reset_concept" not in invalid


# --- Vorzeitiges Ende bei vollständigem Ergebnis ------------------------------------

def test_opencode_call_ends_when_the_result_is_complete(tmp_path, monkeypatch):
    """Lauf gray-countdown: Urteil nach 1,5 min geschrieben, Aufruf lief 900 s."""
    import time
    from src.services import opencode_service

    monkeypatch.setattr(opencode_service, "STOP_WHEN_GRACE_SECONDS", 0.5)
    result_file = tmp_path / "review.json"
    started = time.monotonic()
    completed = opencode_service._run_via_pty(
        ["bash", "-c", f"echo '{{}}' > {result_file}; sleep 60"], cwd=str(tmp_path), timeout=30,
        stop_when=result_file.is_file,
    )
    assert time.monotonic() - started < 25
    assert completed.returncode == 0 and "vorzeitig beendet" in completed.stdout


def test_review_counts_as_complete_only_when_every_requirement_is_rated(tmp_path):
    from src.domain.agents.requirements import review_complete

    reqs = [{"id": "R1"}, {"id": "R2"}, {"id": "R0"}]
    path = tmp_path / "review.json"
    path.write_text('{"requirements": [{"id": "R1", "status": "met"}]')  # unvollständiges JSON
    assert not review_complete(path, reqs)
    path.write_text(json.dumps({"requirements": [{"id": "R1", "status": "met"}]}))
    assert not review_complete(path, reqs)
    path.write_text(json.dumps({"requirements": [{"id": "R1", "status": "met"}, {"id": "R2", "status": "not_met"}]}))
    assert review_complete(path, reqs)


def test_runner_passes_stop_when_only_to_services_that_accept_it(tmp_path):
    from src.services.opencode_task_runner import _accepts

    class Old:
        def execute(self, project_path, instruction, timeout_seconds=300):
            pass

    class New:
        def execute(self, project_path, instruction, timeout_seconds=None, stop_when=None):
            pass

    assert not _accepts(Old().execute, "stop_when") and _accepts(New().execute, "stop_when")


def test_xdc_generator_never_assigns_a_pin_twice(tmp_path):
    """rst liegt auf BTN0 (G15); btn[0] bekam früher denselben Pin."""
    import re
    from src.infrastructure.synthesis.vivado_synthesis import VivadoBitstreamService

    top = tmp_path / "top.vhd"
    top.write_text(
        "library ieee; use ieee.std_logic_1164.all;\n"
        "entity top is port (clk : in std_logic; rst : in std_logic; en : in std_logic;\n"
        "  btn : in std_logic_vector(3 downto 0); sw : in std_logic_vector(3 downto 0);\n"
        "  led : out std_logic_vector(3 downto 0)); end entity;\n"
    )
    xdc = VivadoBitstreamService()._generatexdc_for_board("top", [top], "arty_s7_50", 100_000_000)
    pins = re.findall(r"PACKAGE_PIN (\w+)", xdc)
    assert len(pins) == len(set(pins)), pins
    assert re.search(r"PACKAGE_PIN G15 .*\[get_ports rst\]", xdc)
    # btn bekommt die übrigen Taster (BTN1-BTN3), nicht noch einmal G15
    assert re.findall(r"PACKAGE_PIN (\w+) .*\{btn\[\d\]\}", xdc) == ["K16", "J16", "H13"]


# --- Top-Level in der Synthese (Lauf led-pattern-display-8a297c) ---------------------

_TWO_LEVELS = {
    "child.vhd": "library ieee; use ieee.std_logic_1164.all;\n"
                 "entity child is port (a : in std_logic; y : out std_logic); end entity;\n"
                 "architecture rtl of child is begin y <= not a; end architecture;\n",
    "top.vhd": "library ieee; use ieee.std_logic_1164.all;\n"
               "entity top is port (a : in std_logic; y : out std_logic); end entity;\n"
               "architecture rtl of top is begin u: entity work.child port map (a => a, y => y); end architecture;\n",
}


def _two_level_workspace(tmp_path):
    (tmp_path / "src").mkdir()
    for name, text in _TWO_LEVELS.items():
        (tmp_path / "src" / name).write_text(text)
    return tmp_path


def test_vivado_picks_the_hierarchy_root_when_no_top_is_given(tmp_path):
    """Früher: 'Multiple top-level entities found' bei jedem Entwurf mit mehreren Modulen."""
    from src.infrastructure.synthesis.vivado_synthesis import VivadoBitstreamService

    ws = _two_level_workspace(tmp_path)
    svc = VivadoBitstreamService()
    entities = svc._find_entities(svc._find_vhdl_files(ws / "src"))
    assert [e for _, e in svc._hierarchy_roots(ws / "src", entities)] == ["top"]


@pytest.mark.skipif(shutil.which("ghdl") is None, reason="GHDL nicht installiert")
def test_ghdl_synthesis_checks_the_top_level_not_the_first_file(tmp_path):
    from src.infrastructure.synthesis.ghdl_synthesis import GHDLSynthesisService

    ws = _two_level_workspace(tmp_path)
    result = GHDLSynthesisService().synthesize(str(ws), top_entity="top")
    assert result.passed and "for top" in result.message
    missing = GHDLSynthesisService().synthesize(str(ws), top_entity="nope")
    assert not missing.passed and "'nope' not found" in missing.message


def test_supervisor_passes_the_top_level_to_synthesis(tmp_path):
    captured = {}

    class _FPGA:
        async def execute(self, task):
            captured.update(task.inputs)
            return AgentResult(task_id=task.id, status=AgentStatus.FAILED, error_message="stop")

    supervisor, _, _ = make_supervisor(tmp_path, fpga_agent=_FPGA())
    set_architecture(supervisor, THREE_MODULES, "cpu")
    supervisor._design_state.current_stage = DesignStage.VALIDATING
    run(supervisor._run_synthesis())
    assert captured["top_entity"] == "cpu"


# --- Vivado-Build: VHDL-2008, XDC nur aus dem Top-Level, keine veraltete auto-XDC ------

_TOP_WITH_CHILD = {
    "child.vhd": "library ieee; use ieee.std_logic_1164.all;\n"
                 "entity child is port (clk : in std_logic; enable : in std_logic;\n"
                 "  data_out : out std_logic_vector(3 downto 0)); end entity;\n"
                 "architecture rtl of child is begin data_out <= (others => enable); end architecture;\n",
    "board_top.vhd": "library ieee; use ieee.std_logic_1164.all;\n"
                     "entity board_top is port (clk : in std_logic; rst : in std_logic;\n"
                     "  sw : in std_logic_vector(3 downto 0); led : out std_logic_vector(3 downto 0)); end entity;\n"
                     "architecture rtl of board_top is begin\n"
                     "  u: entity work.child port map (clk => clk, enable => sw(0), data_out => led);\n"
                     "end architecture;\n",
}


def _board_workspace(tmp_path):
    (tmp_path / "src").mkdir()
    for name, text in _TOP_WITH_CHILD.items():
        (tmp_path / "src" / name).write_text(text)
    return tmp_path


def _tcl(ws):
    from src.infrastructure.synthesis.vivado_synthesis import VivadoBitstreamService

    svc = VivadoBitstreamService()
    files = svc._find_vhdl_files(ws / "src")
    return svc._generate_tcl_script(
        src_files=files, top_entity="board_top", part="xc7s50csga324-1",
        bitstream_path=ws / "build" / "board_top.bit", clock_hz=100_000_000, workspace=ws,
        board_name="arty_s7_50",
    )


def test_vivado_reads_sources_as_vhdl_2008(tmp_path):
    """Ohne -vhdl2008 lehnte Vivado VHDL-2008-Code ab ([Synth 8-2757])."""
    tcl = _tcl(_board_workspace(tmp_path))
    assert "read_vhdl -vhdl2008" in tcl and 'read_vhdl "' not in tcl


def test_generated_xdc_maps_only_top_level_ports(tmp_path):
    """Früher: enable eines Untermoduls auf SW0, data_out auf Pmod-Pins, sw[3] ohne Pin."""
    ws = _board_workspace(tmp_path)
    _tcl(ws)
    xdc = (ws / "constraints" / "auto_generated.xdc").read_text()
    assert "enable" not in xdc and "data_out" not in xdc
    for pin, port in (("H14", "{sw[0]}"), ("H18", "{sw[1]}"), ("G18", "{sw[2]}"), ("M5", "{sw[3]}"),
                      ("G15", "rst"), ("E18", "{led[0]}"), ("H15", "{led[3]}")):
        assert f"PACKAGE_PIN {pin} " in xdc and f"[get_ports {port}]" in xdc, (pin, port)


def test_stale_auto_xdc_is_regenerated_and_project_xdc_wins(tmp_path):
    ws = _board_workspace(tmp_path)
    (ws / "constraints").mkdir()
    (ws / "constraints" / "auto_generated.xdc").write_text("# veraltet: enable auf SW0\n")
    tcl = _tcl(ws)
    assert "veraltet" not in (ws / "constraints" / "auto_generated.xdc").read_text()
    assert "auto_generated.xdc" in tcl
    (ws / "constraints" / "board.xdc").write_text("# Projekt-XDC\n")
    tcl = _tcl(ws)
    assert "board.xdc" in tcl and "auto_generated.xdc" not in tcl
    assert not (ws / "constraints" / "auto_generated.xdc").exists()
