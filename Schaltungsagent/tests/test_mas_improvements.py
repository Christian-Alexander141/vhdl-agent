"""Tests für die Maßnahmen aus der MAS-vs-Einzel-OpenCode-Analyse (docs/doku.html, Abschnitt 15)."""
import shutil
import pytest
import json
from pathlib import Path

from src.agents.architecture import module_from_manifest
from src.agents.hdl import HDLAgent
from src.domain.agents import AgentResult, AgentStatus
from src.domain.agents.worker_instructions import (
    SIM_STOP_TIME, TESTBENCH_RULES, entity_declarations, ghdl_selfcheck,
)
from src.domain.models import DesignStage, ModuleInfo
from src.domain_plugins.vhdl.test_definitions import VHDLTestDefinitions
from src.infrastructure.validation.ghdl_validator import TB_COMPLETE_MARKER
from src.services.plan_service import PlanValidator
from tests.test_multi_agent_gates import (
    THREE_MODULES, RecordingHDLAgent, entity, make_supervisor, run, set_architecture,
)


def _hdl_agent():
    return HDLAgent(opencode_service=None, filesystem_service=None, task_runner=object())


# --- Interface-Contract statt geratener Ports -------------------------------

def test_module_type_follows_ports_when_manifest_has_none():
    decoder = module_from_manifest({
        "entity": "decoder", "file": "src/decoder.vhd",
        "ports": [{"name": "code", "direction": "in", "type": "std_logic_vector(6 downto 0)"},
                  {"name": "data", "direction": "out", "type": "std_logic_vector(3 downto 0)"}],
    })
    counter = module_from_manifest({
        "entity": "counter", "file": "src/counter.vhd",
        "ports": [{"name": "clk_i", "direction": "in", "type": "std_logic"}],
    })
    assert decoder.type == "combinational"
    assert counter.type == "sequential"


def test_port_list_is_exactly_the_contract():
    module = ModuleInfo(
        name="counter", type="sequential", inputs=["clk_i", "reset_n"], outputs=["q"],
        ports={"clk_i": {"direction": "in", "type": "std_logic"},
               "reset_n": {"direction": "in", "type": "std_logic"},
               "q": {"direction": "out", "type": "unsigned(3 downto 0)"}},
    )
    ports = _hdl_agent()._build_port_list(module)
    assert ports == "clk_i : in std_logic; reset_n : in std_logic; q : out unsigned(3 downto 0)"
    assert "rst" not in ports.replace("reset_n", "")


def test_heuristic_ports_do_not_duplicate_an_existing_clock():
    module = ModuleInfo(name="m", type="sequential", inputs=["clock", "en"], outputs=["y"])
    ports = _hdl_agent()._build_port_list(module)
    assert "clk : in" not in ports and "clock : in" in ports


def test_generics_get_vhdl_types_that_accept_their_values():
    module = ModuleInfo(name="m", parameters={"WIDTH": 0, "ENABLE": True, "PARITY": "none"})
    generics = _hdl_agent()._build_generic_list(module)
    assert "WIDTH : integer := 0" in generics
    assert "ENABLE : boolean := true" in generics


def test_unknown_module_type_is_inferred_not_rejected():
    """Benchmark 20261009-133223, Lightning/task03: Typ 'top' ließ den ganzen Plan scheitern."""
    base = {"entity": "m", "file": "src/m.vhd"}
    manifest = {"project_name": "type-check", "top_entity": "m", "modules": [{**base, "type": "top"}]}
    assert PlanValidator.validate(manifest) == []
    clocked = module_from_manifest({**base, "type": "top", "ports": [{"name": "clk", "direction": "in", "type": "std_logic"}]})
    combinational = module_from_manifest({**base, "type": "magic"})
    assert clocked.type == "sequential" and combinational.type == "combinational"
    assert module_from_manifest({**base, "type": "FSM"}).type == "fsm"


def test_manifest_validator_checks_parameters():
    base = {"entity": "m", "file": "src/m.vhd"}
    manifest = {"project_name": "type-check", "top_entity": "m", "modules": [{**base, "parameters": [1, 2]}]}
    assert any("parameters for m" in e for e in PlanValidator.validate(manifest))


def test_fallback_template_must_match_contract():
    module = ModuleInfo(name="counter", ports={"en": {"direction": "in"}, "q": {"direction": "out"}})
    good = "entity counter is port (clk : in std_logic; en : in std_logic; q : out std_logic); end entity;"
    bad = "entity counter is port (clk : in std_logic; count : out std_logic); end entity;"
    assert HDLAgent._matches_contract(good, module)
    assert not HDLAgent._matches_contract(bad, module)


# --- Worker-Kontext: GHDL-Selbstprüfung, echte Entities, Validator-Regeln ---

def test_testbench_rules_match_the_validator():
    stop_flags = [f for f in VHDLTestDefinitions.DEFAULT.run_flags if f.startswith("--stop-time")]
    assert stop_flags == [f"--stop-time={SIM_STOP_TIME}"]
    assert TB_COMPLETE_MARKER in TESTBENCH_RULES and SIM_STOP_TIME in TESTBENCH_RULES


def test_ghdl_selfcheck_uses_private_workdir_and_runs_the_testbench():
    text = ghdl_selfcheck(["src/a.vhd", "tests/a_tb.vhd"], "build/ghdl/a_tb", tb_entity="a_tb")
    assert "--workdir=build/ghdl/a_tb src/a.vhd tests/a_tb.vhd" in text
    assert "ghdl -r --std=08 --workdir=build/ghdl/a_tb a_tb" in text
    assert "--assert-level=error" in text


def test_dependency_context_contains_the_real_entity(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "alu.vhd").write_text(
        "-- entity fake is\n" + entity("alu", ["a : in std_logic_vector(7 downto 0)", "y : out std_logic"])
    )
    declared = entity_declarations(str(tmp_path), ["alu", "missing"])
    assert declared.startswith("entity alu is") and "y : out std_logic" in declared
    module = ModuleInfo(name="cpu", dependencies=["alu"])
    context = HDLAgent._dependency_context(module, str(tmp_path))
    assert "instanziiert: alu" in context and "a : in std_logic_vector(7 downto 0)" in context


def test_compile_order_puts_dependencies_first(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "alu.vhd").write_text(entity("alu", ["a : in std_logic"]))
    (tmp_path / "src" / "cpu.vhd").write_text(
        entity("cpu", ["clk : in std_logic"]).replace(
            "architecture rtl of cpu is begin", "architecture rtl of cpu is begin\n  u: entity work.alu port map (a => clk);",
        )
    )
    assert HDLAgent._compile_order(ModuleInfo(name="cpu"), str(tmp_path)) == ["src/alu.vhd", "src/cpu.vhd"]


# --- UART nur bei Bedarf, keine unnötigen Versionssprünge -------------------

def test_uart_is_not_integrated_without_need(tmp_path):
    supervisor, _, _ = make_supervisor(tmp_path)
    set_architecture(supervisor, THREE_MODULES, "cpu")
    supervisor._design_state.metadata["request_full"] = "Eine kleine CPU"
    result = run(supervisor._run_uart_integration())
    assert result.outputs["uart_required"] is False
    assert [m.name for m in supervisor._design_state.architecture.modules] == ["alu", "regfile", "control", "cpu"]
    assert supervisor._design_state.architecture.version == 1


def test_uart_is_integrated_when_requested_and_only_bumps_version_once(tmp_path):
    supervisor, _, _ = make_supervisor(tmp_path)
    set_architecture(supervisor, THREE_MODULES, "cpu")
    supervisor._design_state.metadata["request_full"] = "CPU mit UART-Ausgabe"
    run(supervisor._run_uart_integration())
    version = supervisor._design_state.architecture.version
    assert "uart" in [m.name for m in supervisor._design_state.architecture.modules]
    run(supervisor._run_uart_integration())  # z. B. nach Architektur-Reparatur erneut
    assert supervisor._design_state.architecture.version == version


def test_uart_integration_mode_always_and_off(tmp_path):
    forced, _, _ = make_supervisor(tmp_path, config={"uart_integration": "always"})
    set_architecture(forced, THREE_MODULES, "cpu")
    forced._design_state.metadata["request_full"] = "CPU"
    assert run(forced._run_uart_integration()).outputs["uart_required"] is True

    off, _, _ = make_supervisor(tmp_path / "off", config={"uart_integration": "off"})
    set_architecture(off, THREE_MODULES, "cpu")
    off._design_state.metadata["request_full"] = "CPU mit UART"
    assert run(off._run_uart_integration()).outputs["uart_required"] is False


# --- Ablauf: Synthese abschaltbar, Single-Session-Implementierung -----------

def test_disabled_synthesis_completes_after_validation(tmp_path):
    supervisor, _, _ = make_supervisor(tmp_path, config={"synthesis_enabled": False})
    assert supervisor._determine_next_stage(DesignStage.VALIDATING, None) == DesignStage.COMPLETED
    supervisor._design_state.current_stage = DesignStage.VALIDATING
    supervisor._design_state.transition_to(DesignStage.COMPLETED)

    default, _, _ = make_supervisor(tmp_path / "d")
    assert default._determine_next_stage(DesignStage.VALIDATING, None) == DesignStage.SYNTHESIZING


class ProjectHDLAgent(RecordingHDLAgent):
    async def execute(self, task):
        self.calls.append(task)
        workspace = Path(task.inputs["workspace"])
        (workspace / "src").mkdir(parents=True, exist_ok=True)
        files = []
        for module in task.inputs["architecture"]["modules"]:
            (workspace / "src" / f"{module['name']}.vhd").write_text(entity(module["name"], ["clk : in std_logic"]))
            files.append(f"src/{module['name']}.vhd")
        return AgentResult(task_id=task.id, status=AgentStatus.COMPLETED, outputs={"files": files})


def test_single_session_mode_runs_one_task_for_the_whole_project(tmp_path):
    hdl = ProjectHDLAgent()
    supervisor, _, events = make_supervisor(
        tmp_path, hdl_agent=hdl, config={"implementation_mode": "single_session"},
    )
    set_architecture(supervisor, THREE_MODULES, "cpu")

    result = run(supervisor._run_implementation())

    assert result.status == AgentStatus.COMPLETED
    assert [t.type for t in hdl.calls] == ["implement_project"]
    assert sorted(result.outputs["files"]) == ["src/alu.vhd", "src/control.vhd", "src/cpu.vhd", "src/regfile.vhd"]
    graph = json.loads((tmp_path / "proj" / "task_graph.json").read_text())
    assert list(graph["tasks"]) == ["implement_project"]


def test_hdl_module_order_for_single_session():
    modules = [ModuleInfo(**m) for m in THREE_MODULES][::-1]
    order = [m.name for m in HDLAgent._module_order(modules)]
    assert order.index("alu") < order.index("control") < order.index("cpu")
    assert order.index("regfile") < order.index("cpu")


# --- Native Ausführung: Zugriff außerhalb des Workspaces sperren -------------

def test_native_guard_is_written_once_and_respects_existing_config(tmp_path):
    from src.services.opencode_service import NATIVE_GUARD_FILE, ensure_native_guard

    ensure_native_guard(str(tmp_path))
    config = json.loads((tmp_path / NATIVE_GUARD_FILE).read_text())
    assert config["permission"]["external_directory"] == "deny"

    own = tmp_path / "own"
    own.mkdir()
    (own / NATIVE_GUARD_FILE).write_text('{"model": "x"}')
    ensure_native_guard(str(own))
    assert json.loads((own / NATIVE_GUARD_FILE).read_text()) == {"model": "x"}


def test_native_run_writes_guard_before_starting_opencode(tmp_path, monkeypatch):
    import src.services.opencode_service as svc

    seen = {}

    def fake_pty(cmd, cwd, timeout):
        seen["guard"] = (Path(cwd) / svc.NATIVE_GUARD_FILE).exists()
        import subprocess
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(svc, "_run_via_pty", fake_pty)
    svc.SubprocessOpenCodeService(binary="opencode", model="m").execute(str(tmp_path), "x")
    assert seen["guard"] is True


def test_guard_file_is_not_reported_as_delivery_change(tmp_path):
    from src.services.opencode_task_runner import _snapshot

    (tmp_path / "opencode.json").write_text("{}")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.vhd").write_text("x")
    assert list(_snapshot(tmp_path)) == ["src/a.vhd"]


# --- Fehlerklassifikation ---------------------------------------------------

def test_reset_or_clock_words_alone_are_not_a_clock_reset_error():
    from src.agents.debug import classify_error

    assert classify_error("OpenCode hat src/x.vhd nicht gültig geliefert: synchroner Reset, active high")[0] != "clock_reset_error"
    assert classify_error("Simulation failed for counter_tb at clock cycle 12")[0] == "functional_simulation_error"
    assert classify_error("signal clk is undriven in counter")[0] == "clock_reset_error"
    assert classify_error("port rst_n not connected in top")[0] == "clock_reset_error"


# --- Vorzeitiger Modellabbruch: einmal wiederholen ---------------------------

class _ScriptedOpenCode:
    def __init__(self, actions):
        self.actions = list(actions)
        self.calls = 0

    def execute(self, workspace, instruction, timeout_seconds=None):
        from src.domain.ports import OpenCodeResult
        self.calls += 1
        action = self.actions.pop(0)
        if action == "write":
            (Path(workspace) / "src").mkdir(exist_ok=True)
            (Path(workspace) / "src" / "m.vhd").write_text(
                "library ieee; use ieee.std_logic_1164.all;\nentity m is port (a : in std_logic); end entity;\n"
                "architecture rtl of m is begin end architecture;\n"
            )
            return OpenCodeResult(0, "done", "")
        if action == "ratelimit":
            return OpenCodeResult(0, "Error: Rate limit exceeded. Please try again later.", "")
        return OpenCodeResult(0, "Let me first", "")


def _run(tmp_path, service):
    from src.services.opencode_task_runner import OpenCodeTaskRunner
    return OpenCodeTaskRunner(service).run(
        workspace=str(tmp_path), request_full="x", stage="implement_module",
        task_instruction="schreibe src/m.vhd", expected_files=["src/m.vhd"], task_id="t",
    )


def test_premature_stop_is_retried_once_and_can_succeed(tmp_path):
    service = _ScriptedOpenCode(["stop", "write"])
    delivery = _run(tmp_path, service)
    assert service.calls == 2 and delivery.ok


def test_premature_stop_is_retried_only_once(tmp_path):
    service = _ScriptedOpenCode(["stop", "stop", "write"])
    delivery = _run(tmp_path, service)
    assert service.calls == 2 and not delivery.ok


def test_rate_limit_is_not_retried(tmp_path):
    service = _ScriptedOpenCode(["ratelimit", "write"])
    _run(tmp_path, service)
    assert service.calls == 1



def test_generated_xdc_uses_sstl135_for_bank_34_pins(tmp_path):
    """Offizielle Arty-S7-XDC: CLK100MHZ (R2) und sw[3] (M5) sind SSTL135."""
    from src.infrastructure.synthesis.vivado_synthesis import VivadoBitstreamService

    src = tmp_path / "top.vhd"
    src.write_text(
        "library ieee; use ieee.std_logic_1164.all;\n"
        "entity top is port (clk : in std_logic; sw : in std_logic_vector(3 downto 0); "
        "led : out std_logic_vector(3 downto 0)); end entity;\n"
        "architecture rtl of top is begin led <= sw; end architecture;\n"
    )
    xdc = VivadoBitstreamService(vivado_binary="vivado")._generatexdc_for_board("top", [src], "arty_s7_50", 100_000_000)
    lines = xdc.splitlines()
    for pin in ("R2", "M5"):
        pin_lines = [l for l in lines if f"PACKAGE_PIN {pin} " in l]
        assert pin_lines and all("SSTL135" in l for l in pin_lines), pin
    assert all("LVCMOS33" in l for l in lines if "PACKAGE_PIN E18 " in l)
    assert "set_property INTERNAL_VREF 0.675 [get_iobanks 34]" in lines
    # Board-Namen bitweise auf die offiziellen Pins (Benchmark 20261009: sw/led fehlten ganz)
    for pin, port in (("H14", "sw[0]"), ("M5", "sw[3]"), ("E18", "led[0]"), ("H15", "led[3]")):
        assert any(f"PACKAGE_PIN {pin} " in l and port in l for l in lines), port


def test_port_extraction_survives_vector_ports_and_generics(tmp_path):
    from src.infrastructure.synthesis.vivado_synthesis import VivadoBitstreamService

    src = tmp_path / "top.vhd"
    src.write_text(
        "entity top is generic (W : natural := 4); port (clk : in std_logic; "
        "a : in std_logic_vector(W-1 downto 0); b : in std_logic_vector(3 downto 0); "
        "y : out std_logic_vector(4 downto 0)); end entity;\narchitecture r of top is begin end;\n"
    )
    ports = VivadoBitstreamService._extract_entity_ports(src)
    assert {n: (p["direction"], p["width"]) for n, p in ports.items()} == {
        "clk": ("in", 1), "a": ("in", 4), "b": ("in", 4), "y": ("out", 5),
    }


# --- design_state.yaml: parallele Leser und Schreiber --------------------------

def test_parallel_prompt_checks_never_see_a_half_written_state(tmp_path):
    """Benchmark 20261010-091252: parallele Worker lasen ein halb geschriebenes
    design_state.yaml (PromptIntegrityError: Could not read state metadata)."""
    import threading
    import yaml
    from src.services.filesystem_service import LocalFileSystemService
    from src.services.opencode_task_runner import PromptStore

    store = PromptStore()
    store.save(str(tmp_path), "Baue einen Zähler")
    fs = LocalFileSystemService(base_dir=str(tmp_path))
    big_state = {"metadata": {"prompt_sha256": store.verify(str(tmp_path))},
                 "history": [{"step": i, "text": "x" * 200} for i in range(150)]}
    errors = []

    def writer():
        for _ in range(40):
            fs.write_file(str(tmp_path / "design_state.yaml"), yaml.safe_dump(big_state))

    def checker():
        try:
            for _ in range(40):
                store.save(str(tmp_path), "Baue einen Zähler")
                store.verify(str(tmp_path))
        except Exception as exc:  # pragma: no cover - genau das darf nicht passieren
            errors.append(exc)

    threads = [threading.Thread(target=writer)] + [threading.Thread(target=checker) for _ in range(3)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert errors == []
    assert not list(tmp_path.glob(".*.tmp"))


# --- Vivado: Pfad aus der Konfiguration, Ursache in der Meldung ----------------

def test_fpga_agent_gets_vivado_path_from_settings(tmp_path):
    """Lauf gray-countdown 2026-10-10: die FPGA-Registry enthält keinen Vivado-Pfad,
    der Agent rief den nackten Befehl 'vivado' auf und scheiterte sofort."""
    from src.config import load_config
    from src.orchestrator.agent_factory import build_supervisor_agent

    settings = load_config()
    settings.vivado.binary = "/opt/test/vivado"
    supervisor = build_supervisor_agent(
        filesystem_service=None, opencode_service=None, event_publisher=None, settings=settings,
    )
    assert supervisor._fpga_agent._bitstream_service._vivado_binary == "/opt/test/vivado"


def test_vivado_failure_cause_is_reported_and_missing_binary_is_infrastructure():
    from types import SimpleNamespace
    from src.agents.fpga import vivado_failure_cause

    missing = SimpleNamespace(details={"steps": [{"stdout": "", "stderr": "Vivado binary 'vivado' not found"}]})
    cause, infra = vivado_failure_cause(missing)
    assert infra and "nicht gefunden" in cause

    design = SimpleNamespace(details={"steps": [{"stdout": "INFO: x\nERROR: [Place 30-58] IO placement is infeasible\n", "stderr": ""}]})
    cause, infra = vivado_failure_cause(design)
    assert not infra and "Place 30-58" in cause


def test_missing_vivado_is_announced_at_the_start(tmp_path):
    from types import SimpleNamespace
    supervisor, _, events = make_supervisor(tmp_path)
    supervisor._fpga_agent = SimpleNamespace(_bitstream_service=SimpleNamespace(
        toolchain_available=lambda: False, _vivado_binary="vivado"))
    supervisor._check_toolchain()
    assert "TOOLCHAIN_WARNING" in events.types()
    assert "Vivado nicht gefunden" in supervisor._design_state.metadata["toolchain_warning"]


def test_all_events_emitted_by_supervisor_and_agents_exist_in_the_enum():
    """_emit_event verwirft unbekannte Namen still; neue Ereignisse fehlten so im Dashboard."""
    import re
    from pathlib import Path
    from src.domain.models.events import EventType

    known = {e.value for e in EventType}
    used = set()
    for path in Path("src/agents").glob("*.py"):
        used |= set(re.findall(r'(?:_emit_event|emit_event)\(\s*"([A-Z_]+)"', path.read_text()))
    assert used - known == set()


# --- Planung: korrigieren statt abbrechen ------------------------------------

class _PlanRunner:
    """Liefert nacheinander die vorgegebenen Manifeste und merkt sich die Aufträge."""

    def __init__(self, manifests):
        self.manifests = list(manifests)
        self.instructions = []

    def run(self, **kw):
        from src.services.opencode_task_runner import OpenCodeDelivery
        self.instructions.append(kw["task_instruction"])
        text = json.dumps(self.manifests.pop(0))
        plan = Path(kw["workspace"]) / "plan"
        plan.mkdir(parents=True, exist_ok=True)
        (plan / "manifest.json").write_text(text)
        return OpenCodeDelivery(ok=True, stage="plan", files={"plan/manifest.json": text})


def _manifest(deps_a, deps_b):
    return {"project_name": "zyklus-test", "top_entity": "a", "modules": [
        {"entity": "a", "file": "src/a.vhd", "depends_on": deps_a},
        {"entity": "b", "file": "src/b.vhd", "depends_on": deps_b},
    ], "requirements": [{"id": "R1", "text": "x", "quote": "x", "modules": ["a"], "check": "structure"}]}


def test_cyclic_plan_is_sent_back_for_correction_with_the_cycle(tmp_path):
    from src.services.plan_service import PlanService

    runner = _PlanRunner([_manifest(["b"], ["a"]), _manifest(["b"], [])])
    manifest = PlanService(runner, name_resolver=None).plan(str(tmp_path), "x", task_id="t")
    assert manifest["modules"][1]["depends_on"] == []
    assert len(runner.instructions) == 2
    assert "a -> b -> a" in runner.instructions[1] and "fix exactly these problems" in runner.instructions[1]


def test_self_dependency_is_fixed_without_another_call(tmp_path):
    from src.services.plan_service import PlanService

    runner = _PlanRunner([_manifest(["a", "b", "b"], [])])
    manifest = PlanService(runner, name_resolver=None).plan(str(tmp_path), "x", task_id="t")
    assert manifest["modules"][0]["depends_on"] == ["b"] and len(runner.instructions) == 1


def test_plan_gives_up_after_max_attempts_with_the_last_plan_in_the_error(tmp_path):
    import pytest
    from src.services.plan_service import PlanService, PlanValidationError

    runner = _PlanRunner([_manifest(["b"], ["a"])] * 3)
    with pytest.raises(PlanValidationError) as info:
        PlanService(runner, name_resolver=None, max_attempts=3).plan(str(tmp_path), "x", task_id="t")
    assert len(runner.instructions) == 3 and "a -> b -> a" in info.value.cause
    assert "zyklus-test" in info.value.context["Letzter Plan (Auszug)"]


# --- Eskalation statt Aufgeben (repair_policy = persistent) --------------------

def test_escalation_ladder_for_a_repeating_failure(tmp_path):
    from src.domain.agents.repair_routing import RepairTarget

    switched = []
    supervisor, _, events = make_supervisor(tmp_path, config={"repair_policy": "persistent"})
    supervisor._model_switcher = lambda use: switched.append(use) or "fallback"
    set_architecture(supervisor, THREE_MODULES, "cpu")
    steps = []
    for _ in range(9):
        diagnosis = {"suspected_modules": ["alu"]}
        target, action = supervisor._escalate("functional_simulation_error", diagnosis, RepairTarget.HDL)
        if action == "switch_model":
            supervisor._switch_to_fallback_model()
        steps.append((action, target))
    assert [a for a, _ in steps] == [
        "repair", "repair", "regenerate", "regenerate", "rearchitect",
        "switch_model", "repair", "human", "human",
    ]
    assert steps[4][1] == RepairTarget.ARCHITECTURE and steps[7][1] == RepairTarget.HUMAN
    assert switched == [True]
    assert "ESCALATION" in events.types()
    summary = diagnosis["recommended_action"]
    assert "Nach 8 Versuchen" in summary and "Eingriff" not in summary
    assert "Modul wird neu geschrieben" in summary and "Fallback-Modell" in summary


def test_escalation_counts_each_failure_separately_and_keeps_human_targets(tmp_path):
    from src.domain.agents.repair_routing import RepairTarget

    supervisor, _, _ = make_supervisor(tmp_path, config={"repair_policy": "persistent"})
    set_architecture(supervisor, THREE_MODULES, "cpu")
    for _ in range(2):
        supervisor._escalate("syntax_error", {"suspected_modules": ["alu"]}, RepairTarget.HDL)
    assert supervisor._escalate("syntax_error", {"suspected_modules": ["regfile"]}, RepairTarget.HDL)[1] == "repair"
    assert supervisor._escalate("flash_error", {}, RepairTarget.HUMAN) == (RepairTarget.HUMAN, "human")


def test_regenerate_rewrites_the_module_via_implement_module(tmp_path):
    hdl = RecordingHDLAgent()
    supervisor, _, _ = make_supervisor(tmp_path, hdl_agent=hdl, config={"repair_policy": "persistent"})
    set_architecture(supervisor, THREE_MODULES, "cpu")
    supervisor._design_state.current_stage = DesignStage.DEBUGGING
    result = run(supervisor._regenerate_module({
        "suspected_modules": ["alu"], "failure_type": "functional_simulation_error", "evidence": ["y falsch"],
    }))
    assert result.status == AgentStatus.COMPLETED
    task = hdl.calls[-1]
    assert task.type == "implement_module" and task.inputs["module"]["name"] == "alu"
    assert "vollständig neu" in task.inputs["change_request"] and "y falsch" in task.inputs["change_request"]
    assert supervisor._design_state.current_stage == DesignStage.STATIC_CHECK


def test_identical_error_stops_only_in_standard_mode(tmp_path):
    failure = AgentResult(task_id="s", status=AgentStatus.FAILED, error_message="boom", diagnostics=[
        {"failure_type": "syntax_error", "message": "alu.vhd:3: syntax error"}])
    standard, _, _ = make_supervisor(tmp_path / "s")
    set_architecture(standard, THREE_MODULES, "cpu")
    standard._design_state.diagnostics.history.append({"failure_type": "syntax_error", "message": "alu.vhd:3: syntax error"})
    standard._design_state.current_stage = DesignStage.STATIC_CHECK
    assert "Identical error" in run(standard._handle_failure(DesignStage.STATIC_CHECK, failure)).error_message

    hdl = RecordingHDLAgent()
    persistent, _, _ = make_supervisor(tmp_path / "p", hdl_agent=hdl, debug_agent=__import__("src.agents.debug", fromlist=["DebugAgent"]).DebugAgent(),
                                       config={"repair_policy": "persistent"})
    set_architecture(persistent, THREE_MODULES, "cpu")
    persistent._design_state.diagnostics.history.append({"failure_type": "syntax_error", "message": "alu.vhd:3: syntax error"})
    persistent._design_state.current_stage = DesignStage.STATIC_CHECK
    result = run(persistent._handle_failure(DesignStage.STATIC_CHECK, failure))
    assert "Identical error" not in (result.error_message or "")
    assert any(t.type == "fix_hdl" for t in hdl.calls)


def test_fallback_model_is_restored_after_the_run(tmp_path):
    calls = []
    supervisor, _, _ = make_supervisor(tmp_path, config={"repair_policy": "persistent"})
    supervisor._model_switcher = lambda use: calls.append(use) or "m"
    supervisor._switch_to_fallback_model()
    supervisor._restore_model()
    assert calls == [True, False] and "fallback_model_active" not in supervisor._design_state.metadata


# --- Lauf traffic-light 2026-10-10: Synthese, Regression, Zeitlimit ------------

@pytest.mark.skipif(shutil.which("ghdl") is None, reason="GHDL nicht installiert")
def test_ghdl_synthesis_accepts_vhdl_2008(tmp_path):
    """process(all) ist VHDL-2008; die Synthese lief ohne --std=08 und scheiterte,
    obwohl Simulation und Mutationsanalyse bestanden hatten."""
    from src.infrastructure.synthesis.ghdl_synthesis import GHDLSynthesisService

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "inv.vhd").write_text(
        "library ieee; use ieee.std_logic_1164.all;\n"
        "entity inv is port (a : in std_logic; y : out std_logic); end entity;\n"
        "architecture rtl of inv is begin\n"
        "  p : process(all) begin y <= not a; end process;\n"
        "end architecture;\n"
    )
    result = GHDLSynthesisService().synthesize(str(tmp_path))
    assert result.passed, result.details


def test_ghdl_synthesis_failure_names_the_error_and_the_class(tmp_path):
    from src.agents.debug import DebugAgent
    from src.infrastructure.synthesis.ghdl_synthesis import GHDLSynthesisService

    service = GHDLSynthesisService(ghdl_binary="ghdl")
    service._run_step = lambda *a, **k: {"step": "synthesize", "label": "x", "returncode": 1, "stdout": "",
                                         "stderr": "src/control.vhd:56:20:error: bad thing\n  p : process\n"}
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "control.vhd").write_text("entity control is end entity;")
    result = service.synthesize(str(tmp_path))
    assert "src/control.vhd:56:20:error: bad thing" in result.message
    diagnosis = DebugAgent()._fallback_diagnosis(
        [{"message": result.message, "failure_type": "synthesis_error"}], "synthesis",
        {"modules": [{"name": "control"}]})
    assert diagnosis.failure_type == "synthesis_error" and diagnosis.suspected_modules == ["control"]


def _workspace_with_alu(supervisor, fs):
    src = Path(fs.workspace_path("proj")) / "src"
    src.mkdir(parents=True, exist_ok=True)
    (src / "alu.vhd").write_text("-- gruen\n")
    return src


def test_repair_that_breaks_an_earlier_stage_is_rolled_back(tmp_path):
    supervisor, fs, events = make_supervisor(tmp_path, config={"repair_policy": "persistent"})
    set_architecture(supervisor, THREE_MODULES, "cpu")
    src = _workspace_with_alu(supervisor, fs)
    supervisor._take_repair_snapshot(DesignStage.SYNTHESIZING)
    (src / "alu.vhd").write_text("-- kaputt repariert\n")
    (src / "extra.vhd").write_text("-- neu\n")
    supervisor._design_state.current_stage = DesignStage.STATIC_CHECK

    failure = AgentResult(task_id="s", status=AgentStatus.FAILED, error_message="MODEL_MISMATCH")
    result = run(supervisor._handle_failure(DesignStage.STATIC_CHECK, failure))
    assert "rolled back" in result.error_message
    assert (src / "alu.vhd").read_text() == "-- gruen\n" and not (src / "extra.vhd").exists()
    assert "REPAIR_ROLLED_BACK" in events.types()
    assert supervisor._design_state.current_stage == DesignStage.STATIC_CHECK
    assert supervisor._design_state.metadata["rollbacks"][0]["restored_to_stage"] == "SYNTHESIZING"


def test_failure_at_the_same_stage_is_not_rolled_back(tmp_path):
    supervisor, fs, _ = make_supervisor(tmp_path, config={"repair_policy": "persistent"})
    src = _workspace_with_alu(supervisor, fs)
    supervisor._take_repair_snapshot(DesignStage.SYNTHESIZING)
    (src / "alu.vhd").write_text("-- anders\n")
    assert supervisor._rollback_regression(DesignStage.SYNTHESIZING) is False
    assert (src / "alu.vhd").read_text() == "-- anders\n"


class _HangingHDLAgent:
    """Ändert eine Datei und läuft dann ins OpenCode-Zeitlimit."""

    def __init__(self):
        self.calls = []

    async def execute(self, task):
        self.calls.append(task)
        for rel in task.inputs.get("affected_files", []):
            (Path(task.inputs["workspace"]) / rel).write_text("-- halb fertig\n")
        message = "Reparatur von 'alu': OpenCode execution timed out after 3000s"
        return AgentResult(task_id=task.id, status=AgentStatus.FAILED, error_message=message,
                           diagnostics=[{"failure_type": "infrastructure", "message": message}])


def _timeout_case(tmp_path, policy):
    from src.agents.debug import DebugAgent

    hdl = _HangingHDLAgent()
    supervisor, fs, _ = make_supervisor(tmp_path, hdl_agent=hdl, debug_agent=DebugAgent(),
                                        config={"repair_policy": policy})
    set_architecture(supervisor, THREE_MODULES, "cpu")
    supervisor._design_state.architecture.modules[0].files = ["src/alu.vhd"]
    src = _workspace_with_alu(supervisor, fs)
    supervisor._design_state.current_stage = DesignStage.STATIC_CHECK
    failure = AgentResult(task_id="s", status=AgentStatus.FAILED, error_message="x", diagnostics=[
        {"failure_type": "syntax_error", "message": "src/alu.vhd:3: syntax error", "modules": ["alu"]}])
    return run(supervisor._handle_failure(DesignStage.STATIC_CHECK, failure)), src, hdl


def test_repair_timeout_escalates_in_persistent_mode_and_discards_partial_edits(tmp_path):
    """Zeitlimit beendet den Lauf nicht; ohne Änderung folgt sofort die nächste
    Stufe (keine erneute Pipeline/Synthese), am Ende der Mensch mit Zusammenfassung."""
    result, src, hdl = _timeout_case(tmp_path, "persistent")
    assert len(hdl.calls) >= 2, "nach einem Zeitlimit muss die nächste Stufe folgen"
    assert result.status == AgentStatus.BLOCKED and "Nach" in result.error_message
    assert (src / "alu.vhd").read_text() == "-- gruen\n"


def test_repair_timeout_still_stops_in_standard_mode(tmp_path):
    result, _, _ = _timeout_case(tmp_path, "standard")
    assert result.status == AgentStatus.BLOCKED


# --- Testbenches für Zwischenmodule mit eigener Logik (#52) -----------------

CORE_WITH_REGISTERS = """architecture rtl of cpu_core is
begin
    u_alu: entity work.alu port map (a => acc, b => b, op => op, result => res);
    process(clk) begin
        if rising_edge(clk) then acc <= res; end if;
    end process;
end architecture;"""

WIRING_ONLY = """architecture rtl of board_top is
begin
    -- process: nur ein Kommentar
    u_core: entity work.core port map (clk => clk, q => q_int);
    led <= q_int;
end architecture;"""


def test_own_logic_is_detected_but_plain_wiring_is_not():
    from src.agents.hdl import has_own_logic

    assert has_own_logic(CORE_WITH_REGISTERS)
    assert has_own_logic("y <= a when sel = '1' else b;")
    assert not has_own_logic(WIRING_ONLY)


@pytest.mark.parametrize("code, expect_tb", [(CORE_WITH_REGISTERS, True), (WIRING_ONLY, False)])
def test_intermediate_module_gets_a_testbench_only_with_own_logic(tmp_path, code, expect_tb):
    from src.agents.hdl import HDLAgent as Agent

    class FS:
        def write_file(self, path, content):
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text(content)

    agent = Agent(opencode_service=None, filesystem_service=FS(), task_runner=object())
    calls = []

    async def module_vhdl(*args, **kwargs):
        return code

    async def testbench(module, *args, **kwargs):
        calls.append(module.name)
        return "-- tb"

    agent._generate_module_vhdl, agent._generate_testbench = module_vhdl, testbench
    agent.emit_event = lambda *args, **kwargs: None
    from src.domain.agents import AgentTask
    task = AgentTask(id="t", type="implement_module", project_id="p", inputs={
        "module": {"name": "cpu_core", "type": "structural", "dependencies": ["alu"]},
        "architecture": {"top_module": "mini_cpu"}, "workspace": str(tmp_path)})
    result = run(agent._implement_module(task))
    assert result.status == AgentStatus.COMPLETED
    assert (calls == ["cpu_core"]) is expect_tb


# --- Prüfanleitung fürs Board und Verlauf der Planung (#55, #54) -------------

def test_plan_records_attempt_history_and_keeps_only_complete_board_checks(tmp_path):
    from src.services.plan_service import PlanService

    good = _manifest(["b"], [])
    good["board_checks"] = [
        {"setup": "alle Schalter unten, BTN0", "expected": "LEDs 0001, 0010, 0011", "requirements": ["R1"]},
        {"setup": "nur Aufbau"},
        "kein Objekt",
    ]
    runner = _PlanRunner([_manifest(["b"], ["a"]), good])
    manifest = PlanService(runner, name_resolver=None).plan(str(tmp_path), "x", task_id="t")

    assert manifest["plan_attempts"]["count"] == 2
    assert "a -> b -> a" in " ".join(manifest["plan_attempts"]["problems"][0])
    assert manifest["board_checks"] == [
        {"setup": "alle Schalter unten, BTN0", "expected": "LEDs 0001, 0010, 0011", "requirements": ["R1"]}]
    assert "board_checks" in runner.instructions[0]


def test_completion_message_contains_the_board_checklist(tmp_path):
    supervisor, _, _ = make_supervisor(tmp_path)
    assert "Bitte teste die Hardware" in supervisor._completion_message()

    supervisor._design_state.metadata["plan_manifest"] = {"board_checks": [
        {"setup": "alle Schalter unten, BTN0 drücken", "expected": "LEDs 0001, 0010, …, 1101, dann Halt"},
        {"setup": "SW1–SW0 = 01", "expected": "Akkumulator"},
    ]}
    message = supervisor._completion_message()
    assert "nicht validiert" in message and "Bitte am Board prüfen:" in message
    assert "1. alle Schalter unten, BTN0 drücken → LEDs 0001" in message and "\n2. SW1–SW0 = 01 → Akkumulator" in message
