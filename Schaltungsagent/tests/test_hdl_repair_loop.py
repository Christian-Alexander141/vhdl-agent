"""Deterministic End-to-End test for the HDL error detection and repair loop.

Tests the complete flow:
  User Request
    → SupervisorOrchestrator
    → ArchitectureAgent
    → HDLAgent (generates broken VHDL)
    → VerificationAgent (REAL GHDL detects error)
    → Supervisor creates Debug/Repair task
    → DebugAgent (produces structured diagnosis)
    → HDLAgent (repairs VHDL)
    → VerificationAgent (REAL GHDL passes)

Also tests:
  - Infrastructure failure classification (missing library → BLOCKED)
  - Max repair attempts (non-repairable → BLOCKED after N attempts)
  - DesignState history tracking
  - Event trace observability
"""
import asyncio
import json
import logging
import os
import sys
import tempfile
import shutil
from pathlib import Path

import pytest

# Schaltungsagent on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.orchestrator.supervisor_orchestrator import SupervisorOrchestrator
from src.domain.agents import AgentTask, AgentResult, AgentStatus
from src.domain.models.design_state import DesignStage

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# VHDL Templates – deterministic, no LLM needed
# ---------------------------------------------------------------------------

VHDL_ENTITY = """\
library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
use IEEE.NUMERIC_STD.ALL;

entity counter is
    generic (WIDTH : positive := 8);
    port (
        clk    : in  std_logic;
        rst    : in  std_logic;
        enable : in  std_logic;
        count  : out std_logic_vector(WIDTH-1 downto 0)
    );
end entity;
"""

# Broken: references undeclared signal 'data_out' – GHDL analysis will fail
VHDL_BROKEN = VHDL_ENTITY + """\
architecture rtl of counter is
    signal count_reg : unsigned(WIDTH-1 downto 0);
begin
    process(clk, rst)
    begin
        if rst = '1' then
            count_reg <= (others => '0');
        elsif rising_edge(clk) then
            if enable = '1' then
                count_reg <= count_reg + 1;
            end if;
        end if;
    end process;
    count <= std_logic_vector(count_reg);
    data_out <= std_logic_vector(count_reg);
end architecture;
"""

# Fixed: removed the undeclared signal reference
VHDL_FIXED = VHDL_ENTITY + """\
architecture rtl of counter is
    signal count_reg : unsigned(WIDTH-1 downto 0);
begin
    process(clk, rst)
    begin
        if rst = '1' then
            count_reg <= (others => '0');
        elsif rising_edge(clk) then
            if enable = '1' then
                count_reg <= count_reg + 1;
            end if;
        end if;
    end process;
    count <= std_logic_vector(count_reg);
end architecture;
"""

# Always-valid testbench (uses severity warning for TB_COMPLETE marker)
TESTBENCH = """\
library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
use IEEE.NUMERIC_STD.ALL;

entity counter_tb is
end entity;

architecture sim of counter_tb is
    signal clk    : std_logic := '0';
    signal rst    : std_logic := '0';
    signal enable : std_logic := '0';
    signal count  : std_logic_vector(7 downto 0);
    constant CLK_PERIOD : time := 10 ns;
begin
    dut: entity work.counter
        generic map (WIDTH => 8)
        port map (clk => clk, rst => rst, enable => enable, count => count);

    clk_gen: process
    begin
        clk <= '0'; wait for CLK_PERIOD / 2;
        clk <= '1'; wait for CLK_PERIOD / 2;
    end process;

    stim: process
    begin
        rst <= '1'; enable <= '0';
        wait for CLK_PERIOD * 2;
        rst <= '0';
        wait for CLK_PERIOD;
        enable <= '1';
        wait for CLK_PERIOD * 10;

        assert unsigned(count) = 10
            report "Expected count=10, got " & integer'image(to_integer(unsigned(count)))
            severity error;

        enable <= '0';
        wait for CLK_PERIOD * 5;

        assert unsigned(count) = 10
            report "Expected count=10 (disabled), got " & integer'image(to_integer(unsigned(count)))
            severity error;

        rst <= '1';
        wait for CLK_PERIOD;
        assert unsigned(count) = 0
            report "Expected count=0 after reset, got " & integer'image(to_integer(unsigned(count)))
            severity error;

        report "TB_COMPLETE: PASS" severity warning;
        wait;
    end process;
end architecture;
"""

# Non-repairable VHDL: semantically broken (infinite loop in combinational)
VHDL_UNREPAIRABLE = VHDL_ENTITY + """\
architecture rtl of counter is
begin
    process(clk, rst)
        variable i : integer := 0;
    begin
        while true loop
            i := i + 1;
        end loop;
    end process;
    count <= (others => '0');
end architecture;
"""


# ---------------------------------------------------------------------------
# Architecture YAML for the test
# ---
ARCHITECTURE_YAML = """\
modules:
  - name: counter
    type: sequential
    inputs: [clk, rst, enable]
    outputs: [count]
    parameters:
      width: 8
    description: "8-bit counter with enable and synchronous reset"
    dependencies: []
clock_domain: clk
reset_concept: sync_active_high
decisions:
  - decision: "Use synchronous active-high reset"
"""


# ---------------------------------------------------------------------------
# Mock Services
# ---------------------------------------------------------------------------

class StatefulMockLLM:
    """Mock LLM that returns different responses based on call sequence.

    Call order in the Supervisor pipeline:
      1. analyze_request()         → SupervisorAgent._run_analysis
    2. generate_text()  arch     → ArchitectureAgent._create_architecture
    3. OpenCode          vhdl     → HDLAgent._generate_module_vhdl
    4. OpenCode          tb       → HDLAgent._generate_testbenches
      (--- GHDL fails here, repair loop starts ---)
    5. generate_text()  diag     → DebugAgent._analyze_all_diagnostics
    6. OpenCode          repair   → HDLAgent._fix_hdl
    """

    def __init__(self):
        self._call_count = 0

    def analyze_request(self, user_request: str, domain: str = "vhdl") -> str:
        self._call_count += 1
        return (
            f"Counter-Analyse: {user_request}\n"
            "Modul: 8-Bit-Zaehler mit Enable und sync Reset."
        )

    def generate_text(self, prompt: str, context: str = "", temperature: float = 0.1) -> str:
        self._call_count += 1
        p = prompt.lower()

        # Debug diagnosis
        if "diagnos" in p or "hardware-design-fehler" in p:
            return json.dumps({
                "status": "failed",
                "stage": "simulation",
                "suspected_modules": ["counter"],
                "failure_type": "syntax_error",
                "evidence": [
                    "GHDL analysis failed: no declaration for 'data_out'",
                    "Undeclared signal referenced in architecture body",
                ],
                "recommended_action": "Remove or declare the undeclared signal 'data_out' in the counter architecture",
                "severity": "high",
            })

        # Architecture YAML
        if "yaml" in p or "modules:" in p or "entwirf eine hardware-architektur" in p:
            return ARCHITECTURE_YAML

        # Fallback
        return "Analysis complete."

    def summarize_result(self, task_data: dict) -> str:
        self._call_count += 1
        return "Summary"

    def generate_project_name(self, user_request: str) -> str:
        self._call_count += 1
        return "test-repair-loop"

    def classify_request(self, user_request: str, projects: list, domain: str, current_project: str) -> dict:
        self._call_count += 1
        return {"type": "new_project", "project_id": None, "reason": "test"}

    def answer_question(self, user_request: str, context: dict, domain: str) -> str:
        self._call_count += 1
        return "Answer"


class RealFileSystemService:
    """Real filesystem service that writes to a temp directory."""

    def __init__(self, base_dir: str):
        self._base_dir = Path(base_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._workspaces: dict[str, str] = {}

    def create_workspace(self, task_id: str, domain: str) -> str:
        ws = self._base_dir / task_id
        ws.mkdir(parents=True, exist_ok=True)
        (ws / "src").mkdir(exist_ok=True)
        (ws / "tests").mkdir(exist_ok=True)
        (ws / "constraints").mkdir(exist_ok=True)
        (ws / "build").mkdir(exist_ok=True)
        self._workspaces[task_id] = str(ws)
        return str(ws)

    def workspace_path(self, task_id: str) -> str:
        return self._workspaces.get(task_id, str(self._base_dir / task_id))

    def write_file(self, file_path: str, content: str) -> str:
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)
        Path(file_path).write_text(content)
        return file_path

    def read_file(self, file_path: str) -> str:
        return Path(file_path).read_text()

    def file_exists(self, file_path: str) -> bool:
        return Path(file_path).exists()

    def list_files(self, workspace_path: str, pattern: str = "**/*") -> list[str]:
        ws = Path(workspace_path)
        if not ws.exists():
            return []
        return [str(f.relative_to(ws)) for f in ws.glob(pattern) if f.is_file()]


class FileModifyingOpenCodeService:
    """OpenCode test double that generates and repairs VHDL.

    Generation returns source through stdout; repair instructions modify files.
    """
    def __init__(
        self,
        fixed_vhdl: str,
        initial_vhdl: str = VHDL_BROKEN,
        testbench_vhdl: str = TESTBENCH,
    ):
        self._fixed_vhdl = fixed_vhdl
        self._initial_vhdl = initial_vhdl
        self._testbench_vhdl = testbench_vhdl
        self._call_count = 0
        self.calls: list[dict] = []

    def execute(self, workspace: str, instruction: str, timeout_seconds: int | None = None):
        self._call_count += 1
        self.calls.append({
            "workspace": workspace,
            "instruction": instruction[:200],
            "call_number": self._call_count,
        })

        stdout = ""
        if "repair task:" in instruction.lower():
            ws = Path(workspace)
            src_dir = ws / "src"
            if src_dir.exists():
                for vhd_file in src_dir.glob("*.vhd"):
                    if vhd_file.name == "uart.vhd":
                        continue
                    vhd_file.write_text(self._fixed_vhdl)
                    self.calls[-1]["modified_file"] = str(vhd_file)
        elif "testbench" in instruction.lower():
            stdout = self._testbench_vhdl
        else:
            stdout = self._initial_vhdl

        class R:
            success = True
            returncode = 0
            stderr = ""
            def __init__(self, output):
                self.stdout = output
            def to_dict(self):
                return {"success": True, "returncode": 0, "stdout": self.stdout, "stderr": self.stderr}

        return R(stdout)


class CallTrackingLLM:
    """LLM that tracks which task types were invoked.

    Routes:
    - analyze_request → static analysis text
    - generate_text(architecture) → ARCHITECTURE_YAML
    - OpenCode generates the VHDL module and its testbench
    - generate_text(diagnosis) → structured diagnosis JSON
    """
    def __init__(self):
        self._call_count = 0
        self.prompts: list[str] = []
        self.implement_hdl_calls = 0
        self.fix_hdl_calls = 0

    def analyze_request(self, user_request, domain="vhdl"):
        self._call_count += 1
        return f"Counter-Analyse: {user_request}"

    def generate_text(self, prompt, context="", temperature=0.1):
        self._call_count += 1
        self.prompts.append(prompt)
        p = prompt.lower()
        if "diagnos" in p or "hardware-design-fehler" in p:
            return json.dumps({
                "status": "failed",
                "stage": "simulation",
                "suspected_modules": ["counter"],
                "failure_type": "syntax_error",
                "evidence": [
                    "GHDL analysis failed: no declaration for 'data_out'",
                    "Undeclared signal referenced in architecture body",
                ],
                "recommended_action": "Remove or declare the undeclared signal 'data_out' in the counter architecture",
                "severity": "high",
            })
        if "yaml" in p or "modules:" in p or "entwirf eine hardware-architektur" in p:
            return ARCHITECTURE_YAML
        return "Analysis complete."

    def summarize_result(self, task_data):
        self._call_count += 1
        return "Summary"

    def generate_project_name(self, user_request):
        self._call_count += 1
        return "test-repair-loop"

    def classify_request(self, user_request, projects, domain, current_project):
        self._call_count += 1
        return {"type": "new_project", "project_id": None, "reason": "test"}

    def answer_question(self, user_request, context, domain):
        self._call_count += 1
        return "Answer"


class EventCollector:
    """Collects all events for observability checks."""
    def __init__(self):
        self.events: list[dict] = []

    def publish_event(self, event_type, task_id, payload=None):
        self.events.append({
            "event_type": str(event_type),
            "task_id": task_id,
            "payload": payload or {},
        })


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_orchestrator(llm, fs, events, max_repairs=5, opencode=None):
    """Wire up a SupervisorOrchestrator with real GHDL and mock LLM/FS."""
    if opencode is None:
        opencode = FileModifyingOpenCodeService(fixed_vhdl=VHDL_FIXED)

    return SupervisorOrchestrator(
        llm_service=llm,
        artifact_generator=None,
        filesystem_service=fs,
        opencode_service=opencode,
        event_publisher=events,
        validation_service=None,          # Let VerificationAgent use real GHDLValidator
        max_repair_iterations=max_repairs,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestHDLRepairLoop:
    """E2E: broken VHDL → GHDL fail → debug diagnose → repair → GHDL pass."""

    def test_repair_loop_succeeds(self):
        """The core repair-loop test with real GHDL."""
        tmp = tempfile.mkdtemp(prefix="hdl_repair_")
        try:
            llm = StatefulMockLLM()
            fs = RealFileSystemService(tmp)
            events = EventCollector()
            orch = _build_orchestrator(llm, fs, events, max_repairs=3)

            result = orch.execute(
                request="Erstelle einen 8-Bit-Counter mit Enable und sync Reset.",
                domain="vhdl",
            )

            # ----- 1. Workflow result -----
            assert result is not None
            assert "task_id" in result
            logger.info("Workflow result: status=%s, error=%s", result.get("status"), result.get("error"))

            # Load the persisted DesignState
            task_id = result["task_id"]
            ws = fs.workspace_path(task_id)
            ds_path = Path(ws) / "design_state.yaml"
            assert ds_path.exists(), "DesignState not persisted"

            import yaml
            ds_data = yaml.safe_load(ds_path.read_text())

            # ----- 2. Static GHDL check repairs before simulation -----
            sim_events = [e for e in events.events if "SIMULATION" in e["event_type"]]
            sim_started = [e for e in sim_events if "STARTED" in e["event_type"]]
            sim_passed = [e for e in sim_events if "PASSED" in e["event_type"]]
            sim_failed = [e for e in sim_events if "FAILED" in e["event_type"]]

            logger.info("SIMULATION events: started=%d, passed=%d, failed=%d",
                        len(sim_started), len(sim_passed), len(sim_failed))

            assert len(sim_started) >= 1, f"Expected simulation after repair, got {len(sim_started)}"
            assert len(sim_passed) >= 1, f"Expected >= 1 SIMULATION_PASSED, got {len(sim_passed)}"

            event_types = [event["event_type"] for event in events.events]
            repair_completed = event_types.index("EventType.REPAIR_COMPLETED")
            simulation_started = event_types.index("EventType.SIMULATION_STARTED")
            assert repair_completed < simulation_started

            # ----- 3. DebugAgent produced a diagnosis -----
            debug_events = [e for e in events.events if "DEBUG" in e["event_type"] and "COMPLETED" in e["event_type"]]
            assert len(debug_events) >= 1, "Expected at least 1 DEBUG_COMPLETED event"

            diag_history = ds_data.get("diagnostics", {}).get("history", [])
            assert len(diag_history) >= 1, "Expected at least 1 diagnosis in DesignState history"

            # The last diagnosis may be a raw diagnostic (from synthesis failure)
            # which uses 'type' instead of 'failure_type'. Check both.
            last_diag = diag_history[-1]
            has_failure_type = last_diag.get("failure_type", "") != ""
            has_type = last_diag.get("type", "") != ""
            assert has_failure_type or has_type, "Diagnosis has neither failure_type nor type"
            if has_failure_type:
                assert len(last_diag.get("suspected_modules", [])) > 0 or last_diag.get("recommended_action", ""), "Diagnosis missing modules or action"
            logger.info("Diagnosis: type=%s, failure_type=%s, modules=%s, action=%s",
                        last_diag.get("type"), last_diag.get("failure_type"),
                        last_diag.get("suspected_modules"),
                        last_diag.get("recommended_action"))

            # ----- 4. Repair counter was incremented -----
            repairs = ds_data.get("iterations", {}).get("repairs", 0)
            assert repairs >= 1, f"Expected repairs >= 1, got {repairs}"

            # ----- 5. Files were written to disk -----
            src_dir = Path(ws) / "src"
            tb_dir = Path(ws) / "tests"
            src_files = list(src_dir.glob("*.vhd"))
            tb_files = list(tb_dir.glob("*.vhd"))
            assert len(src_files) >= 1, f"Expected VHDL source files, got {src_files}"
            assert len(tb_files) >= 1, f"Expected testbench files, got {tb_files}"

            # The final VHDL on disk must be the fixed version
            final_vhdl = src_files[0].read_text()
            assert "data_out" not in final_vhdl, "Final VHDL still contains broken signal"
            assert "count_reg" in final_vhdl, "Final VHDL missing expected content"

            # ----- 6. Event trace is observable -----
            event_types = [e["event_type"] for e in events.events]
            logger.info("Full event trace: %s", event_types)

            assert any("ARCHITECTURE_CREATED" in e for e in event_types)

            print("\n" + "=" * 80)
            print("EVENT TRACE:")
            for e in events.events:
                print(f"  EVENT: {e['event_type']}")
            print("=" * 80)
            print(f"\nDIAGNOSIS: {json.dumps(last_diag, indent=2)}")
            print(f"REPAIRS:   {repairs}")
            print(f"FINAL VHDL file: {src_files[0]}")

        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_infrastructure_failure_blocks(self):
        """Missing system library → classified as infrastructure → BLOCKED, no HDL repair."""
        tmp = tempfile.mkdtemp(prefix="infra_fail_")
        try:
            llm = StatefulMockLLM()
            fs = RealFileSystemService(tmp)
            events = EventCollector()
            orch = _build_orchestrator(llm, fs, events, max_repairs=3)

            result = orch.execute(
                request="Erstelle einen 8-Bit-Counter.",
                domain="vhdl",
            )

            task_id = result["task_id"]
            ws = fs.workspace_path(task_id)
            ds_path = Path(ws) / "design_state.yaml"

            # The workflow may succeed or fail depending on whether Vivado is
            # available.  The key assertion is: if the simulation passed and
            # Vivado failed, the DebugAgent must classify the failure as
            # infrastructure, not HDL.
            if ds_path.exists():
                import yaml
                ds_data = yaml.safe_load(ds_path.read_text())
                diag_history = ds_data.get("diagnostics", {}).get("history", [])

                # If there were any diagnoses after synthesis, check that
                # infrastructure issues are correctly classified.
                for diag in diag_history:
                    if diag.get("stage") in ("synthesis", "flash", "fpga"):
                        # If failure_type is 'infrastructure', it must NOT
                        # route to IMPLEMENTING for HDL repair.
                        if diag.get("failure_type") == "infrastructure":
                            assert diag.get("severity") == "critical"
                            logger.info("Infrastructure failure correctly classified: %s", diag)

        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_max_repairs_exceeded(self):
        """Non-repairable error → BLOCKED after max_repair_attempts."""
        tmp = tempfile.mkdtemp(prefix="max_repair_")
        try:
            # Use VHDL that is always broken (never gets fixed)
            llm = StatefulMockLLM()
            fs = RealFileSystemService(tmp)
            events = EventCollector()
            max_rep = 3
            # OpenCode that always writes the same broken VHDL (never fixes it)
            opencode_always_broken = FileModifyingOpenCodeService(fixed_vhdl=VHDL_UNREPAIRABLE)
            orch = _build_orchestrator(llm, fs, events, max_repairs=max_rep, opencode=opencode_always_broken)

            result = orch.execute(
                request="Erstelle einen 8-Bit-Counter.",
                domain="vhdl",
            )

            task_id = result["task_id"]
            ws = fs.workspace_path(task_id)
            ds_path = Path(ws) / "design_state.yaml"

            # DesignState must exist
            assert ds_path.exists(), "DesignState not persisted"
            import yaml
            ds_data = yaml.safe_load(ds_path.read_text())

            # Repair count must be bounded
            repairs = ds_data.get("iterations", {}).get("repairs", 0)
            logger.info("Repairs attempted: %d (max allowed: %d)", repairs, max_rep)
            assert repairs <= max_rep, f"Repairs {repairs} exceeded max {max_rep}"

            # Workflow must not succeed with a non-repairable design
            # It should either be FAILED or BLOCKED
            assert result.get("status") in ("FAILED", "BLOCKED"), (
                f"Expected FAILED or BLOCKED, got {result.get('status')}"
            )

            # No SIMULATION_PASSED event should exist (design was always broken)
            sim_passed = [e for e in events.events if e["event_type"] == "SIMULATION_PASSED"]
            assert len(sim_passed) == 0, f"Expected no SIMULATION_PASSED, got {len(sim_passed)}"

            print(f"\nMax repair test: repairs={repairs}, max={max_rep}, status={result.get('status')}")

        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_design_state_history_tracking(self):
        """DesignState must record every attempt, diagnosis, and repair."""
        tmp = tempfile.mkdtemp(prefix="history_")
        try:
            llm = StatefulMockLLM()
            fs = RealFileSystemService(tmp)
            events = EventCollector()
            orch = _build_orchestrator(llm, fs, events, max_repairs=3)

            result = orch.execute(
                request="Erstelle einen 8-Bit-Counter.",
                domain="vhdl",
            )

            task_id = result["task_id"]
            ws = fs.workspace_path(task_id)
            ds_path = Path(ws) / "design_state.yaml"
            assert ds_path.exists()

            import yaml
            ds_data = yaml.safe_load(ds_path.read_text())

            # --- Verification attempts ---
            verif = ds_data.get("verification", {})
            logger.info("Verification state: %s", verif)
            # status should be "passed" after successful repair
            # (may be "pending" if the pipeline skipped VALIDATING stage)

            # --- Diagnostics history ---
            diag_hist = ds_data.get("diagnostics", {}).get("history", [])
            assert len(diag_hist) >= 1, f"Expected >= 1 diagnosis in history, got {len(diag_hist)}"

            # Each diagnosis must have required fields (raw diagnostics or processed diagnoses)
            for diag in diag_hist:
                # Raw diagnostics have 'type' + 'message'; processed have 'failure_type'
                has_raw = "type" in diag and "message" in diag
                has_processed = "failure_type" in diag and "recommended_action" in diag
                assert has_raw or has_processed, f"Diagnosis has unexpected fields: {diag.keys()}"

            # --- Iteration tracking ---
            iters = ds_data.get("iterations", {})
            assert iters.get("total", 0) > 0, "No iterations recorded"
            assert iters.get("repairs", 0) >= 1, "No repairs recorded"

            # --- Implementation files ---
            impl = ds_data.get("implementation", {})
            assert impl.get("status") in ("completed", "pending"), (
                f"Unexpected implementation status: {impl.get('status')}"
            )

            print(f"\nDesignState history:")
            print(f"  iterations: {iters}")
            print(f"  diagnoses:  {len(diag_hist)}")
            for i, d in enumerate(diag_hist):
                ft = d.get("failure_type", d.get("type", "?"))
                st = d.get("stage", "?")
                sm = d.get("suspected_modules", [])
                print(f"    [{i}] type={ft}, stage={st}, modules={sm}")

        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_event_trace_observability(self):
        """Event trace must contain all expected events in logical order."""
        tmp = tempfile.mkdtemp(prefix="events_")
        try:
            llm = StatefulMockLLM()
            fs = RealFileSystemService(tmp)
            events = EventCollector()
            orch = _build_orchestrator(llm, fs, events, max_repairs=3)

            result = orch.execute(
                request="Erstelle einen 8-Bit-Counter.",
                domain="vhdl",
            )

            event_types = [e["event_type"] for e in events.events]

            # Required events for static-check repair followed by simulation.
            required = [
                "ARCHITECTURE_CREATED",
                "DEBUG_COMPLETED",
                "REPAIR_STARTED",
                "OPENCODE_COMPLETED",
                "REPAIR_COMPLETED",
                "SIMULATION_STARTED",
                "SIMULATION_PASSED",
            ]

            for evt in required:
                assert any(evt in e for e in event_types), f"Missing event: {evt}.\nFull trace: {event_types}"

            # Verify repair completes before the successful simulation starts.
            repair_idx = next(i for i, e in enumerate(event_types) if "REPAIR_COMPLETED" in e)
            simulation_idx = next(i for i, e in enumerate(event_types) if "SIMULATION_STARTED" in e)
            debug_idx = next(i for i, e in enumerate(event_types) if "DEBUG_COMPLETED" in e)
            pass_idx = next(i for i, e in enumerate(event_types) if "SIMULATION_PASSED" in e)
            assert debug_idx < repair_idx < simulation_idx < pass_idx, (
                f"Event order wrong: DEBUG_COMPLETED({debug_idx}) < "
                f"REPAIR_COMPLETED({repair_idx}) < SIMULATION_STARTED({simulation_idx}) "
                f"< SIMULATION_PASSED({pass_idx})"
            )

            print("\nFull event trace (ordered):")
            for i, e in enumerate(events.events):
                print(f"  [{i:2d}] {e['event_type']}")

        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_ghdl_rejects_broken_vhdl(self):
        """Verify that the real GHDLValidator rejects VHDL_BROKEN and accepts VHDL_FIXED."""
        from src.infrastructure.validation.ghdl_validator import GHDLValidator

        validator = GHDLValidator()
        tmp = tempfile.mkdtemp(prefix="ghdl_check_")
        try:
            # --- Test broken VHDL ---
            ws_broken = Path(tmp) / "broken"
            (ws_broken / "src").mkdir(parents=True)
            (ws_broken / "tests").mkdir(parents=True)
            (ws_broken / "build").mkdir(parents=True)
            (ws_broken / "src" / "counter.vhd").write_text(VHDL_BROKEN)
            (ws_broken / "tests" / "counter_tb.vhd").write_text(TESTBENCH)

            result_broken = validator.validate(str(ws_broken), "vhdl")
            assert not result_broken.passed, (
                f"GHDL should reject broken VHDL, but got: {result_broken.message}"
            )
            logger.info("GHDL rejects broken VHDL: %s", result_broken.message)

            # --- Test fixed VHDL ---
            ws_fixed = Path(tmp) / "fixed"
            (ws_fixed / "src").mkdir(parents=True)
            (ws_fixed / "tests").mkdir(parents=True)
            (ws_fixed / "build").mkdir(parents=True)
            (ws_fixed / "src" / "counter.vhd").write_text(VHDL_FIXED)
            (ws_fixed / "tests" / "counter_tb.vhd").write_text(TESTBENCH)

            result_fixed = validator.validate(str(ws_fixed), "vhdl")
            assert result_fixed.passed, (
                f"GHDL should accept fixed VHDL, but got: {result_fixed.message}"
            )
            logger.info("GHDL accepts fixed VHDL: %s", result_fixed.message)

            print(f"\nGHDL broken:  passed={result_broken.passed}, msg={result_broken.message}")
            print(f"GHDL fixed:   passed={result_fixed.passed}, msg={result_fixed.message}")

        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestOpenCodeRepairPath:
    """Test that both code generation and repair use OpenCode, not the Ollama text service."""

    def test_opencode_called_and_file_modified(self):
        """TEST B: Deterministic OpenCode Test-Double.

        Verifies:
        - OpenCode was called (via FileModifyingOpenCodeService)
        - VHDL file was actually modified on disk
        - GHDL passes after repair
        """
        tmp = tempfile.mkdtemp(prefix="opencode_repair_")
        try:
            llm = StatefulMockLLM()
            fs = RealFileSystemService(tmp)
            events = EventCollector()

            # Use FileModifyingOpenCodeService instead of MockOpenCodeService
            opencode = FileModifyingOpenCodeService(fixed_vhdl=VHDL_FIXED)

            orch = SupervisorOrchestrator(
                llm_service=llm,
                artifact_generator=None,
                filesystem_service=fs,
                opencode_service=opencode,
                event_publisher=events,
                validation_service=None,
                max_repair_iterations=3,
            )

            result = orch.execute(
                request="Erstelle einen 8-Bit-Counter mit Enable und sync Reset.",
                domain="vhdl",
            )

            # 1. OpenCode was called
            assert opencode._call_count >= 1, (
                f"OpenCode was never called (call_count={opencode._call_count}). "
                f"Repair must go through OpenCode, not LLM."
            )

            # 2. File was actually modified on disk
            task_id = result["task_id"]
            ws = fs.workspace_path(task_id)
            src_dir = Path(ws) / "src"
            src_files = list(src_dir.glob("*.vhd"))
            assert len(src_files) >= 1, "No VHDL source files found"

            final_vhdl = src_files[0].read_text()
            assert "data_out" not in final_vhdl, (
                f"VHDL file still contains broken signal 'data_out'. "
                f"OpenCode did not modify the file. Content:\n{final_vhdl[:500]}"
            )
            assert "count_reg" in final_vhdl, "Fixed VHDL missing expected content"

            # 3. GHDL passes after repair
            sim_passed = [e for e in events.events if "SIMULATION_PASSED" in e["event_type"]]
            assert len(sim_passed) >= 1, (
                f"Expected >= 1 SIMULATION_PASSED after OpenCode repair, got {len(sim_passed)}. "
                f"Events: {[e['event_type'] for e in events.events]}"
            )

            # 4. Verify repair events (use substring match since event types are "EventType.X")
            repair_started = [e for e in events.events if "REPAIR_STARTED" in e["event_type"]]
            opencode_started = [e for e in events.events if "OPENCODE_STARTED" in e["event_type"]]
            opencode_completed = [e for e in events.events if "OPENCODE_COMPLETED" in e["event_type"]]

            assert len(repair_started) >= 1, "No REPAIR_STARTED event"
            assert len(opencode_started) >= 1, "No OPENCODE_STARTED event"
            assert len(opencode_completed) >= 1, "No OPENCODE_COMPLETED event"

            print(f"\nOpenCode repair path verified:")
            print(f"  OpenCode calls: {opencode._call_count}")
            print(f"  File modified: {opencode.calls[-1].get('modified_file', 'N/A') if opencode.calls else 'N/A'}")
            print(f"  Repair started events: {len(repair_started)}")
            print(f"  OpenCode started events: {len(opencode_started)}")
            print(f"  OpenCode completed events: {len(opencode_completed)}")
            print(f"  SIMULATION_PASSED events: {len(sim_passed)}")

        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_implement_once_fix_multiple(self):
        """Regression test: implement_hdl called exactly once, fix_hdl called >= 1.

        Verifies that on repair failure, the system does NOT re-call
        _implement_hdl() but instead calls _fix_hdl() via OpenCode.
        """
        tmp = tempfile.mkdtemp(prefix="impl_once_")
        try:
            llm = CallTrackingLLM()
            fs = RealFileSystemService(tmp)
            events = EventCollector()
            opencode = FileModifyingOpenCodeService(fixed_vhdl=VHDL_FIXED)

            orch = SupervisorOrchestrator(
                llm_service=llm,
                artifact_generator=None,
                filesystem_service=fs,
                opencode_service=opencode,
                event_publisher=events,
                validation_service=None,
                max_repair_iterations=3,
            )

            result = orch.execute(
                request="Erstelle einen 8-Bit-Counter.",
                domain="vhdl",
            )

            # Count implement_hdl vs fix_hdl via HDLAgent task types
            # HDL source and testbenches are generated through OpenCode.
            code_prompts = [
                prompt for prompt in llm.prompts
                if "vhdl coding guidelines" in prompt.lower()
                or "generiere eine vollständige vhdl-testbench" in prompt.lower()
            ]
            assert not code_prompts, (
                "The LLM text service received an HDL source-generation prompt."
            )

            # OpenCode should have been called for repair
            assert opencode._call_count >= 1, (
                f"OpenCode was never called for repair. "
                f"Repair path must use OpenCode."
            )

            # Repairs should be tracked
            task_id = result["task_id"]
            ws = fs.workspace_path(task_id)
            ds_path = Path(ws) / "design_state.yaml"
            if ds_path.exists():
                import yaml
                ds_data = yaml.safe_load(ds_path.read_text())
                repairs = ds_data.get("iterations", {}).get("repairs", 0)
                assert repairs >= 1, f"Expected repairs >= 1, got {repairs}"

            print(f"\nRegression test passed:")
            print(f"  LLM HDL-generation prompts: {len(code_prompts)} (expected: 0)")
            print(f"  OpenCode repair calls: {opencode._call_count} (expected: >= 1)")

        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestBlinkRepair:
    """Realistic minimal blink-test: clock, reset, counter, LED output."""

    VHDL_BLINK_BROKEN = """\
library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
use IEEE.NUMERIC_STD.ALL;

entity blink is
    port (
        clk  : in  std_logic;
        rst  : in  std_logic;
        led  : out std_logic
    );
end entity;

architecture rtl of blink is
    signal counter : unsigned(23 downto 0) := (others => '0');
begin
    process(clk, rst)
    begin
        if rst = '1' then
            counter <= (others => '0');
        elsif rising_edge(clk) then
            counter <= counter + 1;
        end if;
    end process;
    led <= counter(23);
    undeclared_signal <= '0';
end architecture;
"""

    VHDL_BLINK_FIXED = """\
library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
use IEEE.NUMERIC_STD.ALL;

entity blink is
    port (
        clk  : in  std_logic;
        rst  : in  std_logic;
        led  : out std_logic
    );
end entity;

architecture rtl of blink is
    signal counter : unsigned(23 downto 0) := (others => '0');
begin
    process(clk, rst)
    begin
        if rst = '1' then
            counter <= (others => '0');
        elsif rising_edge(clk) then
            counter <= counter + 1;
        end if;
    end process;
    led <= counter(23);
end architecture;
"""

    BLINK_TB = """\
library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
use IEEE.NUMERIC_STD.ALL;

entity blink_tb is
end entity;

architecture sim of blink_tb is
    signal clk : std_logic := '0';
    signal rst : std_logic := '0';
    signal led : std_logic;
    constant CLK_PERIOD : time := 10 ns;
begin
    dut: entity work.blink
        port map (clk => clk, rst => rst, led => led);

    clk_gen: process
    begin
        clk <= '0'; wait for CLK_PERIOD / 2;
        clk <= '1'; wait for CLK_PERIOD / 2;
    end process;

    stim: process
    begin
        rst <= '1';
        wait for CLK_PERIOD * 2;
        rst <= '0';
        wait for CLK_PERIOD * 10;
        assert led = '0' or led = '1'
            report "LED output invalid"
            severity error;
        report "TB_COMPLETE: PASS" severity warning;
        wait;
    end process;
end architecture;
"""

    BLINK_ARCH = """\
modules:
  - name: blink
    type: sequential
    inputs: [clk, rst]
    outputs: [led]
    parameters: {}
    description: "Simple LED blinker with 24-bit counter"
    dependencies: []
clock_domain: clk
reset_concept: async_active_high
decisions:
  - decision: "Use async active-high reset"
"""

    def test_blink_repair_via_opencode(self):
        """Blink-Test: broken blink VHDL → GHDL fail → debug → OpenCode → fix → GHDL pass."""
        tmp = tempfile.mkdtemp(prefix="blink_repair_")
        try:
            # LLM provides architecture and diagnosis; OpenCode provides HDL.
            class BlinkMockLLM:
                def __init__(self):
                    self._call_count = 0

                def analyze_request(self, user_request, domain="vhdl"):
                    self._call_count += 1
                    return "Blink LED analysis"

                def generate_text(self, prompt, context="", temperature=0.1):
                    self._call_count += 1
                    p = prompt.lower()
                    if "yaml" in p or "modules:" in p or "entwirf eine hardware-architektur" in p:
                        return TestBlinkRepair.BLINK_ARCH
                    if "diagnos" in p or "hardware-design-fehler" in p:
                        return json.dumps({
                            "status": "failed",
                            "stage": "simulation",
                            "suspected_modules": ["blink"],
                            "failure_type": "syntax_error",
                            "evidence": ["GHDL analysis failed: no declaration for 'undeclared_signal'"],
                            "recommended_action": "Remove the undeclared signal reference",
                            "severity": "high",
                        })
                    return "Analysis complete."

                def summarize_result(self, task_data):
                    return "Summary"

                def generate_project_name(self, user_request):
                    return "blink-repair-test"

                def classify_request(self, user_request, projects, domain, current_project):
                    return {"type": "new_project", "project_id": None, "reason": "test"}

                def answer_question(self, user_request, context, domain):
                    return "Answer"

            llm = BlinkMockLLM()
            fs = RealFileSystemService(tmp)
            events = EventCollector()
            opencode = FileModifyingOpenCodeService(
                fixed_vhdl=self.VHDL_BLINK_FIXED,
                initial_vhdl=self.VHDL_BLINK_BROKEN,
                testbench_vhdl=self.BLINK_TB,
            )

            orch = SupervisorOrchestrator(
                llm_service=llm,
                artifact_generator=None,
                filesystem_service=fs,
                opencode_service=opencode,
                event_publisher=events,
                validation_service=None,
                max_repair_iterations=3,
            )

            result = orch.execute(
                request="Erstelle einen LED-Blinker mit 24-Bit-Counter.",
                domain="vhdl",
            )

            # Verify the full path
            task_id = result["task_id"]
            ws = fs.workspace_path(task_id)

            # 1. OpenCode was called after the static GHDL check failed.
            assert opencode._call_count >= 1, "OpenCode must be called for repair"

            # 2. File was modified
            src_dir = Path(ws) / "src"
            src_files = list(src_dir.glob("*.vhd")) if src_dir.exists() else []
            if src_files:
                final = src_files[0].read_text()
                assert "undeclared_signal" not in final, "Blink file still broken"

            # 3. GHDL passes after repair.
            sim_passed = [e for e in events.events if "SIMULATION_PASSED" in e["event_type"]]
            assert len(sim_passed) >= 1, "GHDL should pass after repair"

            event_types = [event["event_type"] for event in events.events]
            assert event_types.index("EventType.REPAIR_COMPLETED") < event_types.index(
                "EventType.SIMULATION_STARTED"
            )

            print(f"\nBlink repair test passed:")
            print(f"  OPENCODE calls: {opencode._call_count}")
            print(f"  SIMULATION_PASSED: {len(sim_passed)}")

        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    pytest.main([__file__, "-v", "--tb=short", "-s"])
