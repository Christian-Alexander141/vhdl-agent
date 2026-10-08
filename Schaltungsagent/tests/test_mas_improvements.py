"""Tests für die Maßnahmen aus der MAS-vs-Einzel-OpenCode-Analyse (docs/doku.html, Abschnitt 15)."""
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


def test_manifest_validator_checks_type_and_parameters():
    base = {"entity": "m", "file": "src/m.vhd"}
    manifest = {"project_name": "type-check", "top_entity": "m", "modules": [{**base, "type": "magic"}]}
    assert any("type for m" in e for e in PlanValidator.validate(manifest))
    manifest["modules"] = [{**base, "parameters": [1, 2]}]
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
