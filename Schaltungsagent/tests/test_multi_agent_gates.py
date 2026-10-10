"""Akzeptanztests für die Multi-Agent-Kernlücken (Assessment 2026-09-13).

Abgedeckt:
- Phase 1: paralleler Modul-DAG, Checkpoint/Resume, Invalidation nur abhängiger Tasks
- Phase 2: Contract-, Breiten- und Simulationsfehler werden erkannt und an die
  zuständige Rolle geroutet; Coverage-Gate
- Phase 3: Timing-/Constraint-/Ressourcen-Gates aus Vivado-Reports
- Phase 4: kein Erfolg aus Mock-Hardware; projektspezifische Testvektoren
- Ziel-FPGA-Normalisierung, an den Bitstream gebundene Freigabe, Resume nach Neustart
"""
import asyncio
import hashlib
import json
import threading
import time
from pathlib import Path

import pytest

from src.agents.debug import DebugAgent, classify_error
from src.agents.fpga import FPGAAgent
from src.agents.hardware_test import (
    HardwareTestAgent,
    HardwareTestInterface,
    HardwareTestSpecError,
    UARTHardwareTestInterface,
    normalize_hardware_tests,
)
from src.agents.supervisor import SupervisorAgent
from src.config import load_fpga_registry
from src.domain.agents import AgentResult, AgentStatus, AgentTask, TaskStatus
from src.domain.agents.contract_check import ContractChecker
from src.domain.agents.repair_routing import RepairTarget, route_repair
from src.domain.agents.test_plan import build_test_plan
from src.domain.models import ArchitectureInfo, DesignStage, DesignState, ModuleInfo
from src.orchestrator.supervisor_orchestrator import SupervisorOrchestrator
from src.services.fpga_target import AmbiguousTargetError, resolve_fpga_target


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------

class DiskFS:
    def __init__(self, root: Path):
        self.root = root

    def workspace_path(self, project_id):
        return str(self.root / project_id)

    def file_exists(self, path):
        return Path(path).exists()

    def read_file(self, path):
        return Path(path).read_text()

    def write_file(self, path, content):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(content)
        return path


class EventRecorder:
    def __init__(self):
        self.events = []

    def publish_event(self, event_type, task_id="", payload=None):
        self.events.append((getattr(event_type, "value", event_type), payload or {}))

    def types(self):
        return [e[0] for e in self.events]


def entity(name, ports):
    port_text = ";\n        ".join(ports)
    return f"""library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
entity {name} is
    port (
        {port_text}
    );
end entity;
architecture rtl of {name} is begin
end architecture;
"""


class RecordingHDLAgent:
    """Blockierender Stub wie der echte HDLAgent (OpenCode-Subprozess)."""

    def __init__(self, delay=0.0, fail=()):
        self.delay = delay
        self.fail = set(fail)
        self.calls = []
        self.windows = {}
        self._lock = threading.Lock()

    async def execute(self, task):
        start = time.monotonic()
        with self._lock:
            self.calls.append(task)
        time.sleep(self.delay)
        workspace = Path(task.inputs["workspace"])
        if task.type == "fix_hdl":
            for rel in task.inputs.get("affected_files", []):
                path = workspace / rel
                path.write_text(path.read_text() + "\n-- repaired\n")
            return AgentResult(task_id=task.id, status=AgentStatus.COMPLETED, outputs={"modified_files": task.inputs.get("affected_files", [])})
        name = (task.inputs.get("module") or {}).get("name") or task.inputs["architecture"]["top_module"]
        with self._lock:
            self.windows[task.id] = (start, time.monotonic())
        if name in self.fail:
            return AgentResult(task_id=task.id, status=AgentStatus.FAILED, error_message=f"{name} failed")
        (workspace / "src").mkdir(parents=True, exist_ok=True)
        (workspace / "src" / f"{name}.vhd").write_text(entity(name, ["clk : in std_logic"]))
        return AgentResult(task_id=task.id, status=AgentStatus.COMPLETED, outputs={"files": [f"src/{name}.vhd"]})


def make_supervisor(tmp_path, config=None, **agents):
    fs = DiskFS(tmp_path)
    events = EventRecorder()
    supervisor = SupervisorAgent(
        filesystem_service=fs,
        event_publisher=events,
        project_memory=None,
        config={"max_parallel_workers": 2, **(config or {})},
        fpga_registry=load_fpga_registry(),
        **agents,
    )
    supervisor._current_task = AgentTask(id="run", type="supervise", project_id="proj", inputs={"request": "x"})
    supervisor._design_state = DesignState()
    supervisor._design_state.current_stage = DesignStage.UART_INTEGRATION
    Path(fs.workspace_path("proj")).mkdir(parents=True, exist_ok=True)
    return supervisor, fs, events


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def set_architecture(supervisor, modules, top):
    supervisor._design_state.architecture = ArchitectureInfo(
        status="completed", version=1, top_module=top,
        modules=[ModuleInfo(**m) for m in modules],
    )


THREE_MODULES = [
    {"name": "alu", "type": "combinational", "inputs": ["a"], "outputs": ["y"]},
    {"name": "regfile", "type": "sequential", "inputs": ["clk"], "outputs": ["q"]},
    {"name": "control", "type": "sequential", "inputs": ["clk"], "outputs": ["op"], "dependencies": ["alu"]},
    {"name": "cpu", "type": "structural", "inputs": ["clk"], "outputs": ["led"], "dependencies": ["alu", "regfile", "control"]},
]


# ---------------------------------------------------------------------------
# Phase 1: Multi-Agent-DAG
# ---------------------------------------------------------------------------

def test_independent_modules_run_in_parallel(tmp_path):
    hdl = RecordingHDLAgent(delay=0.3)
    supervisor, _, events = make_supervisor(tmp_path, hdl_agent=hdl)
    set_architecture(supervisor, THREE_MODULES, "cpu")

    result = run(supervisor._run_implementation())

    assert result.status == AgentStatus.COMPLETED
    a_start, a_end = hdl.windows["implement_module_alu"]
    r_start, r_end = hdl.windows["implement_module_regfile"]
    assert r_start < a_end and a_start < r_end, "unabhängige Module müssen überlappen"
    # Abhängige Tasks starten erst nach ihren Abhängigkeiten.
    assert hdl.windows["implement_module_control"][0] >= a_end
    # Das Top-Level steht als Modul im Manifest und läuft nach allen Abhängigkeiten;
    # ein zusätzlicher implement_top-Task würde dieselbe Datei überschreiben.
    assert "implement_top" not in hdl.windows
    assert hdl.windows["implement_module_cpu"][0] >= max(
        w[1] for k, w in hdl.windows.items() if k != "implement_module_cpu"
    )
    assert "PARALLEL_BATCH_STARTED" in events.types()


def test_contract_change_invalidates_only_dependent_tasks(tmp_path):
    hdl = RecordingHDLAgent()
    supervisor, _, events = make_supervisor(tmp_path, hdl_agent=hdl)
    set_architecture(supervisor, THREE_MODULES, "cpu")
    assert run(supervisor._run_implementation()).status == AgentStatus.COMPLETED
    hdl.calls.clear()

    changed = [dict(m) for m in THREE_MODULES]
    changed[0] = {**changed[0], "outputs": ["y", "carry"]}  # ALU-Contract ändert sich
    supervisor._design_state.current_stage = DesignStage.UART_INTEGRATION
    set_architecture(supervisor, changed, "cpu")
    result = run(supervisor._run_implementation())

    assert result.status == AgentStatus.COMPLETED
    executed = {t.id for t in hdl.calls}
    # ALU + alle, die sie instanziieren (control, cpu = Top-Level);
    # das unabhängige Registerfile bleibt unangetastet.
    assert executed == {
        "implement_module_alu", "implement_module_control", "implement_module_cpu",
    }
    graph = json.loads((tmp_path / "proj" / "task_graph.json").read_text())
    assert graph["tasks"]["implement_module_regfile"]["result"]["reused"] is True
    invalidated = [p["task"] for t, p in events.events if t == "TASK_INVALIDATED"]
    assert set(invalidated) == executed


def test_resume_after_crash_reruns_only_open_tasks(tmp_path):
    crashed = RecordingHDLAgent(fail={"regfile"})
    supervisor, _, events = make_supervisor(tmp_path, hdl_agent=crashed)
    set_architecture(supervisor, THREE_MODULES, "cpu")
    first = run(supervisor._run_implementation())
    assert first.status == AgentStatus.FAILED
    graph = json.loads((tmp_path / "proj" / "task_graph.json").read_text())
    assert graph["tasks"]["implement_module_cpu"]["status"] == "BLOCKED"
    assert graph["tasks"]["implement_module_alu"]["status"] == "COMPLETED"

    # Neuer Prozess: frischer Supervisor, gleicher Workspace und Auftrag.
    healthy = RecordingHDLAgent()
    resumed, _, _ = make_supervisor(tmp_path, hdl_agent=healthy)
    set_architecture(resumed, THREE_MODULES, "cpu")
    second = run(resumed._run_implementation())

    assert second.status == AgentStatus.COMPLETED
    assert {t.id for t in healthy.calls} == {"implement_module_regfile", "implement_module_cpu"}


def test_new_run_after_completion_does_not_reuse_previous_tasks(tmp_path):
    hdl = RecordingHDLAgent()
    supervisor, _, _ = make_supervisor(tmp_path, hdl_agent=hdl)
    set_architecture(supervisor, THREE_MODULES, "cpu")
    run(supervisor._run_implementation())
    hdl.calls.clear()

    supervisor._design_state.metadata["completed_runs"] = 1  # Lauf abgeschlossen
    supervisor._design_state.current_stage = DesignStage.UART_INTEGRATION
    run(supervisor._run_implementation())

    assert len(hdl.calls) == 4


# ---------------------------------------------------------------------------
# Phase 2: Contracts, Coverage und Reparaturrouting
# ---------------------------------------------------------------------------

def _contract_workspace(tmp_path, alu_ports):
    src = tmp_path / "src"
    src.mkdir(parents=True, exist_ok=True)
    (src / "alu.vhd").write_text(entity("alu", alu_ports))
    (src / "cpu.vhd").write_text(entity("cpu", ["clk : in std_logic"]))
    return {
        "top_module": "cpu",
        "modules": [
            {"name": "alu", "type": "combinational",
             "inputs": ["a"], "outputs": ["y"],
             "ports": {"a": {"direction": "in", "type": "std_logic_vector(7 downto 0)"},
                       "y": {"direction": "out", "type": "std_logic_vector(WIDTH-1 downto 0)"}},
             "parameters": {"WIDTH": 8}},
            {"name": "cpu", "type": "structural", "inputs": ["clk"], "outputs": [], "dependencies": ["alu"]},
        ],
    }


def test_manifest_ports_become_typed_contracts():
    from src.agents.architecture import module_from_manifest

    module = module_from_manifest({
        "entity": "alu", "file": "src/alu.vhd",
        "inputs": ["clk", "a: std_logic_vector(7 downto 0)"],
        "outputs": [{"name": "y", "type": "unsigned(7 downto 0)"}],
    })
    assert module.inputs == ["clk", "a"] and module.outputs == ["y"]
    assert module.ports == {
        "a": {"direction": "in", "type": "std_logic_vector(7 downto 0)"},
        "y": {"direction": "out", "type": "unsigned(7 downto 0)"},
    }


def test_contract_checker_accepts_matching_entity(tmp_path):
    arch = _contract_workspace(tmp_path, [
        "a : in std_logic_vector(7 downto 0)", "y : out std_logic_vector(7 downto 0)",
    ])
    result = ContractChecker().check(arch, str(tmp_path))
    assert result.passed, result.summary()


@pytest.mark.parametrize("ports,check", [
    (["a : in std_logic_vector(7 downto 0)"], "port_exists"),
    (["a : in std_logic_vector(7 downto 0)", "y : out std_logic_vector(3 downto 0)"], "port_width"),
    (["a : out std_logic_vector(7 downto 0)", "y : out std_logic_vector(7 downto 0)"], "port_direction"),
    (["a : in unsigned(7 downto 0)", "y : out std_logic_vector(7 downto 0)"], "port_type"),
])
def test_contract_checker_detects_port_errors(tmp_path, ports, check):
    arch = _contract_workspace(tmp_path, ports)
    result = ContractChecker().check(arch, str(tmp_path))
    assert not result.passed
    assert check in {v.check for v in result.errors}
    assert {v.module for v in result.errors} == {"alu"}


def test_static_check_blocks_wrong_width_and_routes_to_hdl(tmp_path):
    hdl = RecordingHDLAgent()
    supervisor, fs, events = make_supervisor(tmp_path, hdl_agent=hdl, debug_agent=DebugAgent())
    arch = _contract_workspace(tmp_path / "proj", [
        "a : in std_logic_vector(7 downto 0)", "y : out std_logic_vector(3 downto 0)",
    ])
    supervisor._design_state.architecture = ArchitectureInfo(
        version=1, top_module="cpu", modules=[ModuleInfo(**m) for m in arch["modules"]],
    )
    supervisor._design_state.current_stage = DesignStage.IMPLEMENTING

    result = run(supervisor._run_static_check())
    assert result.status == AgentStatus.FAILED
    assert result.diagnostics[0]["failure_type"] == "contract_violation"
    assert "port_width" in result.error_message

    run(supervisor._handle_failure(DesignStage.STATIC_CHECK, result))
    fix = [t for t in hdl.calls if t.type == "fix_hdl"]
    assert len(fix) == 1 and fix[0].inputs["failed_module"] == "alu"
    assigned = [p for t, p in events.events if t == "REPAIR_ASSIGNED"]
    assert assigned[0]["repair_target"] == "hdl"
    # Nach der Reparatur wird ab dem statischen Check neu verifiziert.
    assert supervisor._design_state.current_stage == DesignStage.STATIC_CHECK


def test_wrong_simulation_result_routes_to_hdl(tmp_path):
    hdl = RecordingHDLAgent()
    supervisor, _, events = make_supervisor(tmp_path, hdl_agent=hdl, debug_agent=DebugAgent())
    _contract_workspace(tmp_path / "proj", [
        "a : in std_logic_vector(7 downto 0)", "y : out std_logic_vector(7 downto 0)",
    ])
    set_architecture(supervisor, [{"name": "alu"}, {"name": "cpu", "dependencies": ["alu"]}], "cpu")
    supervisor._design_state.current_stage = DesignStage.SIMULATING
    failure = AgentResult(
        task_id="sim", status=AgentStatus.FAILED, error_message="Simulation failed",
        diagnostics=[{
            "type": "simulation_failure",
            "stage": "simulation",
            "message": "alu_tb.vhd:42:9:@30ns:(assertion error): simulation failed: y mismatch in alu",
        }],
    )

    run(supervisor._handle_failure(DesignStage.SIMULATING, failure))

    assert [t.type for t in hdl.calls] == ["fix_hdl"]
    assert hdl.calls[0].inputs["error_info"]["stage"] == "simulation"
    assert [p for t, p in events.events if t == "REPAIR_ASSIGNED"][0]["repair_target"] == "hdl"


class StubArchitectureAgent:
    def __init__(self, architecture):
        self.architecture = architecture
        self.calls = []

    async def execute(self, task):
        self.calls.append(task)
        return AgentResult(task_id=task.id, status=AgentStatus.COMPLETED, outputs={"architecture": self.architecture})


def test_interface_mismatch_between_valid_modules_routes_to_architecture(tmp_path):
    hdl = RecordingHDLAgent()
    new_arch = ArchitectureInfo(
        version=2, top_module="cpu",
        modules=[
            ModuleInfo(name="alu", inputs=["a"], outputs=["y", "carry"]),
            ModuleInfo(name="regfile", inputs=["clk"], outputs=["q"]),
            ModuleInfo(name="cpu", inputs=["clk"], outputs=["led"], dependencies=["alu", "regfile"]),
        ],
    ).model_dump()
    arch_agent = StubArchitectureAgent(new_arch)
    supervisor, _, events = make_supervisor(
        tmp_path, hdl_agent=hdl, debug_agent=DebugAgent(), architecture_agent=arch_agent,
    )
    set_architecture(supervisor, [
        {"name": "alu", "inputs": ["a"], "outputs": ["y"]},
        {"name": "regfile", "inputs": ["clk"], "outputs": ["q"]},
        {"name": "cpu", "inputs": ["clk"], "outputs": ["led"], "dependencies": ["alu", "regfile"]},
    ], "cpu")
    supervisor._design_state.verification.contract_check = {"passed": True, "architecture_version": 1}
    supervisor._design_state.current_stage = DesignStage.SIMULATING
    failure = AgentResult(
        task_id="sim", status=AgentStatus.FAILED,
        diagnostics=[{"type": "elab", "stage": "simulation",
                      "message": "cpu.vhd:12: port map mismatch: actual port is too wide for alu"}],
    )

    run(supervisor._handle_failure(DesignStage.SIMULATING, failure))

    assert len(arch_agent.calls) == 1 and arch_agent.calls[0].type == "refine_architecture"
    assert hdl.calls == []
    assert supervisor._design_state.architecture.version == 2
    assert supervisor._design_state.metadata["invalidated_modules"] == ["alu"]
    assert supervisor._design_state.current_stage == DesignStage.UART_INTEGRATION


def test_interface_mismatch_with_contract_violation_stays_with_hdl():
    assert route_repair("interface_mismatch", contracts_ok=False) == RepairTarget.HDL
    assert route_repair("interface_mismatch", contracts_ok=True) == RepairTarget.ARCHITECTURE


@pytest.mark.parametrize("message,failure_type,target", [
    ("Contract violation: alu: port_width", "contract_violation", RepairTarget.HDL),
    ("Coverage gap: not covered by any simulated testbench: alu", "coverage_gap", RepairTarget.VERIFICATION),
    ("no testbench found in tests/", "testbench_error", RepairTarget.VERIFICATION),
    ("Timing violation: WNS=-1.2 ns", "timing_error", RepairTarget.FPGA),
    # Seit der Eskalation (Doku #24) im Code behebbar, nicht mehr beim Benutzer.
    ("There are no user specified timing constraints", "constraint_error", RepairTarget.FPGA),
    ("Resource limit exceeded: LUT 140%", "resource_error", RepairTarget.HUMAN),
    ("Flash failed: no cable found", "flash_error", RepairTarget.HUMAN),
    ("ghdl: command not found", "infrastructure", RepairTarget.HUMAN),
    ("hardware test diverged from passed simulation: uart_loopback expected 1f got 2a",
     "simulation_hardware_divergence", RepairTarget.FPGA),
])
def test_failure_classes_route_to_responsible_role(message, failure_type, target):
    assert classify_error(message)[0] == failure_type
    assert route_repair(failure_type) == target


def test_resource_error_requests_human_instead_of_hdl_patch(tmp_path):
    hdl = RecordingHDLAgent()
    supervisor, _, events = make_supervisor(tmp_path, hdl_agent=hdl, debug_agent=DebugAgent())
    set_architecture(supervisor, [{"name": "cpu"}], "cpu")
    supervisor._design_state.current_stage = DesignStage.SYNTHESIZING
    failure = AgentResult(task_id="s", status=AgentStatus.FAILED, diagnostics=[{
        "failure_type": "resource_error", "message": "Resource limit exceeded: LUT 140%",
    }])

    result = run(supervisor._handle_failure(DesignStage.SYNTHESIZING, failure))

    assert result.status == AgentStatus.BLOCKED
    assert hdl.calls == []
    assert "HUMAN_INTERVENTION_REQUESTED" in events.types()


def test_testbench_coverage_follows_instantiation_hierarchy(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "alu.vhd").write_text(entity("alu", ["a : in std_logic"]))
    (tmp_path / "src" / "unused.vhd").write_text(entity("unused", ["a : in std_logic"]))
    (tmp_path / "src" / "cpu.vhd").write_text(
        entity("cpu", ["clk : in std_logic"]).replace(
            "architecture rtl of cpu is begin",
            "architecture rtl of cpu is\n  component alu port (a : in std_logic); end component;\nbegin\n  u_alu : alu\n    port map (a => clk);",
        )
    )
    (tmp_path / "tests" / "cpu_tb.vhd").write_text(
        "entity cpu_tb is end entity;\narchitecture sim of cpu_tb is begin\n"
        "  dut: entity work.cpu port map (clk => open);\nend architecture;\n"
    )
    plan = build_test_plan(
        {"modules": [{"name": "alu"}, {"name": "cpu"}, {"name": "unused"}]},
        str(tmp_path),
        [{"id": "r1", "description": "ALU", "satisfied_by": ["alu"]},
         {"id": "r2", "description": "X", "satisfied_by": ["unused"]}],
    )
    assert plan["covered"] == ["alu", "cpu"]
    assert plan["uncovered"] == ["unused"]
    assert plan["requirements"]["r1"]["covered"] is True
    assert plan["requirements"]["r2"]["covered"] is False


def test_golden_vectors_are_informational_and_do_not_block_coverage(tmp_path):
    """Golden-Vektoren aus dem Manifest blockieren die Abdeckung nicht mehr.

    Im Benchmark (Lauf 20261008-161755) waren vom Planer erzeugte Vektoren
    widersprüchlich und verwarfen einen korrekten Entwurf. Funktionale
    Prüfung übernimmt jetzt das Referenzmodell, die Testgüte die Mutationsanalyse.
    """
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "adder.vhd").write_text(entity("adder", ["a : in std_logic_vector(3 downto 0)"]))
    (tmp_path / "tests" / "adder_tb.vhd").write_text(
        "entity adder_tb is end entity;\narchitecture sim of adder_tb is begin\n"
        "  dut: entity work.adder port map (a => (others => '0'));\n"
        "end architecture;\n"
    )
    architecture = {"modules": [{
        "name": "adder",
        "simulation_vectors": [{"inputs": {"a": "0001"}, "expected": {"sum": "0010"}}],
    }]}

    plan = build_test_plan(architecture, str(tmp_path))
    assert plan["covered"] == ["adder"]
    assert plan["modules"]["adder"]["simulation_vectors"] == 1
    assert plan["modules"]["adder"]["vectors_referenced"] == 0


def test_format_simulation_vectors_renders_requirement_and_empty_list():
    from src.domain.agents.test_plan import format_simulation_vectors

    assert format_simulation_vectors([]) == ""

    text = format_simulation_vectors([{
        "inputs": {"a": "0001", "b": "0001"}, "expected": {"sum": "0010"},
        "after_clocks": 1, "requirement": "addiert korrekt",
    }])
    assert "GOLDEN-MODEL-VEKTOREN" in text
    assert "0001" in text and "0010" in text
    assert "addiert korrekt" in text


def test_validation_gate_blocks_uncovered_modules(tmp_path):
    supervisor, _, _ = make_supervisor(tmp_path)
    set_architecture(supervisor, [{"name": "alu"}, {"name": "cpu"}], "cpu")
    v = supervisor._design_state.verification
    v.status, v.architecture_version, v.coverage = "passed", 1, 0.5
    v.test_plan = {"uncovered": ["alu"]}
    v.contract_check = {"passed": True, "architecture_version": 1}
    supervisor._design_state.current_stage = DesignStage.SIMULATING

    result = run(supervisor._run_validation())

    assert result.status == AgentStatus.FAILED
    assert result.diagnostics[0]["failure_type"] == "coverage_gap"
    assert result.diagnostics[0]["modules"] == ["alu"]


def test_validation_gate_rejects_stale_simulation(tmp_path):
    supervisor, _, _ = make_supervisor(tmp_path)
    set_architecture(supervisor, [{"name": "cpu"}], "cpu")
    supervisor._design_state.architecture.version = 3
    v = supervisor._design_state.verification
    v.status, v.architecture_version, v.coverage = "passed", 2, 1.0
    v.contract_check = {"passed": True, "architecture_version": 3}
    supervisor._design_state.current_stage = DesignStage.SIMULATING

    result = run(supervisor._run_validation())

    assert result.status == AgentStatus.FAILED
    assert "architecture v2" in result.error_message


# ---------------------------------------------------------------------------
# Phase 3: Synthese-Gates aus Vivado-Reports
# ---------------------------------------------------------------------------

TIMING_RPT = """| Design Timing Summary
| ---------------------

    WNS(ns)      TNS(ns)  TNS Failing Endpoints  TNS Total Endpoints      WHS(ns)      THS(ns)  THS Failing Endpoints  THS Total Endpoints     WPWS(ns)     TPWS(ns)  TPWS Failing Endpoints  TPWS Total Endpoints
    -------      -------  ---------------------  -------------------      -------      -------  ---------------------  -------------------     --------     --------  ----------------------  --------------------
     {wns}      -10.500                     12                  100        0.050        0.000                      0                  100        4.500        0.000                       0                    40

{note}

Clock        Waveform(ns)       Period(ns)      Frequency(MHz)
-----        ------------       ----------      --------------
sys_clk_pin  {{0.000 5.000}}      10.000          100.000
"""

UTIL_RPT = """+-------------------------+------+-------+------------+-----------+-------+
|        Site Type        | Used | Fixed | Prohibited | Available | Util% |
+-------------------------+------+-------+------------+-----------+-------+
| Slice LUTs*             |   {lut} |     0 |          0 |     32600 |  {pct} |
| Slice Registers         |   30 |     0 |          0 |     65200 |  0.05 |
| Block RAM Tile          |    0 |     0 |          0 |        75 |  0.00 |
| DSPs                    |    0 |     0 |          0 |       120 |  0.00 |
"""


def _reports(tmp_path, wns="1.234", note="All user specified timing constraints are met.", lut=42, pct="0.13"):
    bit_dir = tmp_path / "build" / "bitstream"
    bit_dir.mkdir(parents=True, exist_ok=True)
    (bit_dir / "timing.rpt").write_text(TIMING_RPT.format(wns=wns, note=note))
    (bit_dir / "utilization.rpt").write_text(UTIL_RPT.format(lut=lut, pct=pct))
    return str(bit_dir / "top.bit")


def _fpga_agent():
    return FPGAAgent.__new__(FPGAAgent)


def test_reports_parsed_and_gates_pass(tmp_path):
    agent = _fpga_agent()
    bit = _reports(tmp_path)
    timing = agent._parse_timing_report(str(tmp_path), bit)
    resources = agent._parse_utilization_report(str(tmp_path), bit)
    assert timing["wns_ns"] == 1.234 and timing["whs_ns"] == 0.05 and timing["met"]
    assert timing["fmax_mhz"] == round(1000 / (10 - 1.234), 2)
    assert resources["lut"] == 42 and resources["ff"] == 30 and resources["lut_pct"] == 0.13
    assert FPGAAgent.evaluate_gates(timing, resources) == []


def test_timing_violation_blocks_success(tmp_path):
    agent = _fpga_agent()
    bit = _reports(tmp_path, wns="-1.234", note="Timing constraints are not met.")
    failures = FPGAAgent.evaluate_gates(
        agent._parse_timing_report(str(tmp_path), bit),
        agent._parse_utilization_report(str(tmp_path), bit),
    )
    assert [f["failure_type"] for f in failures] == ["timing_error"]
    assert classify_error(failures[0]["message"])[0] == "timing_error"


def test_missing_clock_constraint_blocks_success(tmp_path):
    agent = _fpga_agent()
    bit = _reports(tmp_path, wns="NA", note="There are no user specified timing constraints.")
    failures = FPGAAgent.evaluate_gates(
        agent._parse_timing_report(str(tmp_path), bit),
        agent._parse_utilization_report(str(tmp_path), bit),
    )
    assert [f["failure_type"] for f in failures] == ["constraint_error"]


def test_missing_reports_and_overuse_block_success(tmp_path):
    agent = _fpga_agent()
    timing = agent._parse_timing_report(str(tmp_path), "")
    resources = agent._parse_utilization_report(str(tmp_path), "")
    assert timing["wns_ns"] is None and resources["lut"] is None  # keine Platzhalterwerte
    assert {f["failure_type"] for f in FPGAAgent.evaluate_gates(timing, resources)} == {"infrastructure"}

    bit = _reports(tmp_path, lut=40000, pct="122.70")
    failures = FPGAAgent.evaluate_gates(
        agent._parse_timing_report(str(tmp_path), bit),
        agent._parse_utilization_report(str(tmp_path), bit),
    )
    assert [f["failure_type"] for f in failures] == ["resource_error"]


# ---------------------------------------------------------------------------
# Phase 4: Hardwaretests
# ---------------------------------------------------------------------------

class FakeSerial(HardwareTestInterface):
    """Echte (nicht-Mock) Schnittstelle mit simuliertem Board."""

    def __init__(self, responder):
        self.responder = responder
        self.sent = []

    async def reset(self):
        return True

    async def send_command(self, command):
        self.sent.append(command)
        return True

    async def send_program(self, program):
        self.sent.append(program)
        return True

    async def start(self):
        return True

    async def read_output(self, length=1024, timeout=5.0):
        return b""

    async def run_test(self, test):
        payload = test.get("program", test.get("send", b""))
        response = self.responder(test["type"], payload)
        return {"passed": response == test["expected"], "output": response.hex(), "expected": test["expected"].hex()}

    async def close(self):
        pass


CPU_TESTS = [{
    "name": "cpu_add",
    "type": "cpu_program",
    "program": "01 05 02 03 0A FF",  # LDI 5; ADDI 3; OUT; HALT
    "expected": "08",
    "requirement": "R1",
}]


def hw_task(**inputs):
    return AgentTask(id="hw", type="hardware_test", project_id="p", inputs=inputs)


def test_mock_hardware_never_reports_success():
    agent = HardwareTestAgent(filesystem_service=None)
    result = run(agent.execute(hw_task(architecture={"hardware_tests": CPU_TESTS})))
    assert result.status == AgentStatus.SKIPPED
    assert result.outputs["hardware_result"]["test_mode"] == "MOCK"


def test_cpu_program_vectors_pass_and_fail_on_real_interface():
    good = HardwareTestAgent(None, hardware_interface=FakeSerial(lambda kind, p: bytes([p[1] + p[3]])))
    passed = run(good.execute(hw_task(architecture={"hardware_tests": CPU_TESTS})))
    assert passed.status == AgentStatus.COMPLETED
    assert passed.outputs["hardware_result"]["test_mode"] == "REAL_HARDWARE"
    assert passed.outputs["hardware_result"]["tests"][0]["requirement"] == "R1"

    broken = HardwareTestAgent(None, hardware_interface=FakeSerial(lambda kind, p: b"\x07"))
    failed = run(broken.execute(hw_task(architecture={"hardware_tests": CPU_TESTS})))
    assert failed.status == AgentStatus.FAILED
    assert failed.diagnostics[0]["failure_type"] == "hardware_error"


def test_hardware_mismatch_after_passed_simulation_is_a_divergence_not_hardware_error():
    """FPGAgent-Paper Punkt 2: simuliert grün, Board antwortet falsch -> eigene
    Fehlerklasse (Software/Hardware-Diskrepanz), nicht die generische
    hardware_error (die weiterhin Infrastruktur-/Board-Probleme meint)."""
    wrong_value = HardwareTestAgent(None, hardware_interface=FakeSerial(lambda kind, p: b"\x07"))
    result = run(wrong_value.execute(
        hw_task(architecture={"hardware_tests": CPU_TESTS}, verification_passed=True)
    ))
    assert result.status == AgentStatus.FAILED
    assert result.diagnostics[0]["failure_type"] == "simulation_hardware_divergence"
    assert "diverged" in result.diagnostics[0]["message"]

    # Ohne vorher bestandene Simulation bleibt es die generische Klasse.
    same_board = HardwareTestAgent(None, hardware_interface=FakeSerial(lambda kind, p: b"\x07"))
    without_verification = run(same_board.execute(
        hw_task(architecture={"hardware_tests": CPU_TESTS}, verification_passed=False)
    ))
    assert without_verification.diagnostics[0]["failure_type"] == "hardware_error"


def test_hardware_connection_error_stays_hardware_error_even_after_passed_simulation():
    """Eine Infrastruktur-/Verbindungsstörung (Exception im Interface, keine
    echte Antwort) ist auch nach bestandener Simulation kein Divergenzfund."""
    class RaisingInterface(HardwareTestInterface):
        async def reset(self):
            return True

        async def send_command(self, command):
            return True

        async def send_program(self, program):
            return True

        async def start(self):
            return True

        async def read_output(self, length=1024, timeout=5.0):
            return b""

        async def run_test(self, test):
            return {"passed": False, "error": "serial port disconnected"}

        async def close(self):
            pass

    agent = HardwareTestAgent(None, hardware_interface=RaisingInterface())
    result = run(agent.execute(
        hw_task(architecture={"hardware_tests": CPU_TESTS}, verification_passed=True)
    ))
    assert result.status == AgentStatus.FAILED
    assert result.diagnostics[0]["failure_type"] == "hardware_error"


def test_real_hardware_without_project_tests_is_blocked(tmp_path):
    agent = HardwareTestAgent(None, hardware_interface=FakeSerial(lambda kind, p: p))
    result = run(agent.execute(hw_task(architecture={"modules": [{"name": "cpu"}]}, workspace=str(tmp_path))))
    assert result.status == AgentStatus.BLOCKED


def test_hardware_tests_load_from_workspace_file(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "hardware_tests.yaml").write_text(
        "tests:\n  - name: decode\n    type: uart_exchange\n    send: '3A 1F'\n    expected: '1F'\n"
    )
    agent = HardwareTestAgent(None, hardware_interface=FakeSerial(lambda kind, p: p[1:]))
    result = run(agent.execute(hw_task(architecture={}, workspace=str(tmp_path))))
    assert result.status == AgentStatus.COMPLETED


def test_invalid_hardware_spec_is_rejected():
    with pytest.raises(HardwareTestSpecError):
        normalize_hardware_tests([{"name": "x", "type": "cpu_program", "program": "", "expected": "00"}])
    with pytest.raises(HardwareTestSpecError):
        normalize_hardware_tests([{"name": "x", "type": "uart_exchange", "send": "zz", "expected": "00"}])
    with pytest.raises(HardwareTestSpecError):
        normalize_hardware_tests([{"name": "x", "type": "gpio_magic", "expected": "00"}])


def test_uart_interface_does_not_pass_unknown_test_types():
    interface = UARTHardwareTestInterface("/dev/null")
    interface._serial = object()  # keine echte Verbindung nötig
    result = run(interface.run_test({"name": "x", "type": "custom"}))
    assert result["passed"] is False


def test_supervisor_completion_without_real_hardware_is_explicit(tmp_path):
    supervisor, _, _ = make_supervisor(tmp_path, hardware_test_agent=HardwareTestAgent(None))
    assert supervisor._determine_next_stage(DesignStage.FPGA_PROGRAMMING, None) == DesignStage.COMPLETED
    assert "KEIN automatischer Hardwaretest" in supervisor._completion_message()

    real, _, _ = make_supervisor(
        tmp_path, hardware_test_agent=HardwareTestAgent(None, hardware_interface=FakeSerial(lambda k, p: p)),
    )
    assert real._determine_next_stage(DesignStage.FPGA_PROGRAMMING, None) == DesignStage.HARDWARE_TESTING


def test_supervisor_tells_hardware_test_whether_simulation_already_passed(tmp_path):
    """Voraussetzung für Punkt 2 (Divergenzklasse): der HardwareTestAgent muss
    wissen, ob die Golden-Model-Simulation bereits bestanden wurde."""
    captured = {}

    class CapturingHardwareTestAgent:
        async def execute(self, task):
            captured.update(task.inputs)
            return AgentResult(
                task_id=task.id, status=AgentStatus.COMPLETED,
                outputs={"hardware_result": {"status": "passed", "test_mode": "REAL_HARDWARE"}},
            )

    supervisor, _, _ = make_supervisor(tmp_path, hardware_test_agent=CapturingHardwareTestAgent())
    set_architecture(supervisor, [{"name": "cpu"}], "cpu")
    supervisor._design_state.verification.status = "passed"
    supervisor._design_state.current_stage = DesignStage.FPGA_PROGRAMMING

    result = run(supervisor._run_hardware_test())

    assert result.status == AgentStatus.COMPLETED
    assert captured["verification_passed"] is True

    supervisor._design_state.verification.status = "failed"
    supervisor._design_state.current_stage = DesignStage.FPGA_PROGRAMMING
    run(supervisor._run_hardware_test())
    assert captured["verification_passed"] is False


# ---------------------------------------------------------------------------
# Ziel-FPGA
# ---------------------------------------------------------------------------

KEYS = ["gatemate_a1", "arty_s7_50"]


@pytest.mark.parametrize("request_text,expected,source", [
    ("Baue eine 8-Bit-CPU für das GateMate A1 Board", "gatemate_a1", "request"),
    ("Hamming-Decoder für Arty S7-50", "arty_s7_50", "request"),
    ("Zähler auf dem xc7s50", "arty_s7_50", "request"),
    ("Ein Lauflicht", "arty_s7_50", "default"),
])
def test_fpga_target_extracted_from_request(request_text, expected, source):
    target = resolve_fpga_target(request_text, KEYS)
    assert (target.key, target.source) == (expected, source)


def test_conflicting_fpga_targets_require_question(tmp_path):
    with pytest.raises(AmbiguousTargetError):
        resolve_fpga_target("CPU für GateMate oder Arty S7", KEYS)
    with pytest.raises(AmbiguousTargetError):
        resolve_fpga_target("CPU für GateMate", KEYS, explicit="arty_s7_50")

    supervisor, _, _ = make_supervisor(tmp_path)
    supervisor._design_state.current_stage = DesignStage.ANALYZING
    supervisor._design_state.metadata["request_full"] = "CPU für GateMate oder Arty S7"
    result = run(supervisor._run_analysis())
    assert result.status == AgentStatus.BLOCKED
    assert supervisor._design_state.metadata["open_questions"]


def test_resolved_target_is_stored_and_used(tmp_path):
    supervisor, _, _ = make_supervisor(tmp_path)
    supervisor._design_state.current_stage = DesignStage.ANALYZING
    supervisor._design_state.metadata["request_full"] = "Decoder für GateMate A1"
    result = run(supervisor._run_analysis())
    assert result.status == AgentStatus.COMPLETED
    assert supervisor._design_state.fpga.target == "gatemate_a1"
    assert supervisor._design_state.fpga.programmer == "openfpgaloader"
    assert supervisor._target_fpga() == "gatemate_a1"


# ---------------------------------------------------------------------------
# Freigabe und Wiederaufnahme
# ---------------------------------------------------------------------------

def make_orchestrator(tmp_path):
    orchestrator = SupervisorOrchestrator.__new__(SupervisorOrchestrator)
    orchestrator._fs = DiskFS(tmp_path)
    orchestrator._approval_events = {}
    orchestrator._approval_results = {}
    orchestrator._approval_lock = threading.Lock()
    orchestrator._events = EventRecorder()
    (tmp_path / "proj").mkdir(exist_ok=True)
    return orchestrator


def _wait_in_thread(orchestrator, bitstream):
    result = {}
    worker = threading.Thread(
        target=lambda: result.setdefault("value", orchestrator._wait_for_approval("proj", bitstream)),
        daemon=True,
    )
    worker.start()
    for _ in range(200):
        if "proj" in orchestrator._approval_events:
            break
        time.sleep(0.005)
    return worker, result


def test_approval_is_bound_to_bitstream_content(tmp_path):
    orchestrator = make_orchestrator(tmp_path)
    bitstream = tmp_path / "proj" / "top.bit"
    bitstream.write_bytes(b"v1")

    worker, result = _wait_in_thread(orchestrator, str(bitstream))
    assert orchestrator.approve_task("proj", "ok")
    worker.join(1)
    assert result["value"] == (True, "ok")
    # Gleicher Bitstream: gespeicherte Freigabe gilt (z. B. nach Neustart).
    assert orchestrator._wait_for_approval("proj", str(bitstream)) == (True, "ok")

    # Neuer Bitstream-Inhalt braucht eine neue Freigabe.
    bitstream.write_bytes(b"v2")
    worker, result = _wait_in_thread(orchestrator, str(bitstream))
    assert worker.is_alive(), "geänderter Bitstream darf nicht automatisch freigegeben sein"
    assert orchestrator.reject_task("proj", "nein")
    worker.join(1)
    assert result["value"] == (False, "nein")
    stored = json.loads((tmp_path / "proj" / "state.json").read_text())["approval"]
    assert stored["bitstream_sha256"] == hashlib.sha256(b"v2").hexdigest()


def test_pending_approval_resumes_workflow_after_restart(tmp_path):
    orchestrator = make_orchestrator(tmp_path)
    orchestrator._write_approval("proj", {"status": "pending", "bitstream_path": "/x.bit", "bitstream_sha256": ""})
    resumed = []
    orchestrator._supervisor = object()
    orchestrator.resume_project = lambda project_id: resumed.append(project_id)

    assert orchestrator.approve_task("proj", "ok") is True
    assert resumed == ["proj"]
    assert orchestrator._read_approval("proj")["status"] == "approved"


def test_manifest_port_list_and_validator():
    from src.agents.architecture import module_from_manifest
    from src.services.plan_service import PlanValidator

    item = {
        "entity": "decoder", "file": "src/decoder.vhd", "depends_on": [],
        "ports": [
            {"name": "clk", "direction": "in", "type": "std_logic"},
            {"name": "codeword", "direction": "in", "type": "std_logic_vector(6 downto 0)"},
            {"name": "data", "direction": "out", "type": "std_logic_vector(3 downto 0)"},
        ],
    }
    module = module_from_manifest(item)
    assert module.inputs == ["clk", "codeword"] and module.outputs == ["data"]
    assert module.ports["data"] == {"direction": "out", "type": "std_logic_vector(3 downto 0)"}

    manifest = {"project_name": "hamming-decoder", "top_entity": "decoder", "modules": [item]}
    assert PlanValidator.validate(manifest) == []
    bad = {**manifest, "modules": [{**item, "ports": [{"name": "x", "direction": "sideways"}]}]}
    assert any("Invalid direction" in e for e in PlanValidator.validate(bad))


def test_manifest_simulation_vectors_become_module_field_and_validated():
    """Golden-Model-Vektoren (FPGAgent-Paper, Punkt 1) aus dem Manifest."""
    from src.agents.architecture import module_from_manifest
    from src.services.plan_service import PlanValidator

    item = {
        "entity": "adder", "file": "src/adder.vhd",
        "simulation_vectors": [{
            "inputs": {"a": "0001", "b": "0001"}, "expected": {"sum": "0010"},
            "after_clocks": 1, "requirement": "R1: addiert korrekt",
        }],
    }
    module = module_from_manifest(item)
    assert module.simulation_vectors == item["simulation_vectors"]

    manifest = {"project_name": "adder-test", "top_entity": "adder", "modules": [item]}
    assert PlanValidator.validate(manifest) == []

    missing_expected = {**manifest, "modules": [{**item, "simulation_vectors": [{"inputs": {"a": "1"}}]}]}
    assert any("simulation_vector" in e for e in PlanValidator.validate(missing_expected))

    wrong_shape = {**manifest, "modules": [{**item, "simulation_vectors": "not-a-list"}]}
    assert any(
        "simulation_vectors" in e and "must be a list" in e
        for e in PlanValidator.validate(wrong_shape)
    )
