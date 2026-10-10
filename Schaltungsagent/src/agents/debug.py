import logging
import re
import uuid
from typing import Any

from src.domain.agents import BaseAgent, AgentTask, AgentResult, AgentStatus
from src.domain.agents.communication import DebugDiagnosis

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regex-based error classifier (Section 11: 12 Typen + infrastructure)
# Patterns are ordered by priority – first match wins.
# ---------------------------------------------------------------------------

_ERROR_PATTERNS: list[tuple[str, list[re.Pattern], str, str]] = [
    # (failure_type, patterns, recommended_action, severity)
    (
        "infrastructure",
        [
            re.compile(r"missing\s+(lib|system|shared\s+object|cannot\s+open)", re.I),
            re.compile(r"vivado.*(?:license|limit|tool\s+version)", re.I),
            re.compile(r"(ghdl|vivado|vivado_lab|docker|opencode)[:,]?\s+(?:not\s+found|command not found)", re.I),
            re.compile(r"\bdocker:\s+(?:docker\s+)?(?:permission denied|daemon not running|image not available|container not running)", re.I),
            re.compile(r"serverfehler beim modell-provider|unexpected server error|unknownerror", re.I),
            re.compile(r"keine netzwerkverbindung zum modell-provider|kontingent bzw\. rate-limit", re.I),
            re.compile(r"anmeldung beim modell-provider fehlgeschlagen", re.I),
        ],
        "Install missing system dependency or check tool installation",
        "critical",
    ),
    (
        "constraint_error",
        [
            re.compile(r"no\s+user\s+specified\s+timing\s+constraints", re.I),
            re.compile(r"(?:missing|unconstrained)\s+(?:pin|clock|port|timing)\s*(?:constraint|location)?", re.I),
            re.compile(r"\b(?:UCIO-1|NSTD-1)\b"),
        ],
        "Add missing pin/clock constraints to the board constraint file",
        "critical",
    ),
    (
        "contract_violation",
        [
            re.compile(r"contract\s+violation", re.I),
        ],
        "Align the module entity with its architecture contract",
        "high",
    ),
    (
        "coverage_gap",
        [
            re.compile(r"coverage\s+gap|not\s+covered\s+by\s+any\s+(?:simulated\s+)?testbench", re.I),
        ],
        "Extend the test plan: add or adapt testbenches for uncovered modules",
        "high",
    ),
    (
        "flash_error",
        [
            re.compile(r"flash\s+(?:failed|toolchain\s+not\s+available)", re.I),
            re.compile(r"no\s+(?:cable|device|target)\s+(?:found|detected)", re.I),
        ],
        "Check USB cable, drivers and programmer selection, then retry flashing",
        "medium",
    ),
    (
        "syntax_error",
        [
            re.compile(r"^\s*\*\*\s+Error:\s+.*\.vhd(?:hl)?:\d+:\d+:\s+syntax\s+error", re.M | re.I),
            re.compile(r"parse\s+error|syntax\s+error", re.I),
            re.compile(r"unexpected\s+(token|identifier|keyword|';')", re.I),
            re.compile(r"expected\s+'[^']+'\s+but\s+found", re.I),
        ],
        "Fix VHDL syntax errors in reported files",
        "high",
    ),
    (
        "type_error",
        [
            re.compile(r"type\s+mismatch|cannot\s+associate|incompatible\s+(type|width)", re.I),
            re.compile(r"no\s+declaration\s+for\s+identifier", re.I),
            re.compile(r"not\s+declared", re.I),
            re.compile(r" illegal\s+ expression\s+in\s+ a\s+ (?:signal|variable)\s+ assignment", re.I),
            re.compile(r"must\s+be\s+(?:of\s+type|a\s+subtype)", re.I),
        ],
        "Fix type mismatches and undeclared identifiers",
        "high",
    ),
    (
        "elaboration_error",
        [
            re.compile(r"elaboration\s+error|cannot\s+find\s+entity|no\s+binding\s+for\s+instance", re.I),
            re.compile(r"no\s+architecture\s+found\s+for\s+entity", re.I),
            re.compile(r"generic\s+(?:map|value)\s+(?:mismatch|error)", re.I),
        ],
        "Check entity/architecture binding, generics, and component declarations",
        "high",
    ),
    (
        "interface_mismatch",
        [
            re.compile(r"port\s+(?:map|mismatch)|interface\s+mismatch", re.I),
            re.compile(r"actual\s+(?:parameter|port)\s+(?:is\s+)?(?:too\s+(?:wide|narrow)|mismatch)", re.I),
            re.compile(r"number\s+of\s+(?:ports|associations)\s+(?:do|does)\s+not\s+match", re.I),
        ],
        "Align port definitions and generic maps between instantiated entities",
        "high",
    ),
    (
        "clock_reset_error",
        [
            # Früher "clock|clk.*(...)" bzw. "reset|rst.*(...)": durch die
            # Rangfolge von | traf schon das bloße Wort "clock"/"reset" – jede
            # Meldung mit "Reset" (Prompt-Ausschnitte, "active high") wurde
            # zum clock_reset_error und verdrängte die eigentliche Fehlerklasse.
            re.compile(r"\b(?:clock|clk)\w*\b.{0,40}\b(?:not\s+driven|undriven|multiple\s+drivers|not\s+connected)", re.I),
            re.compile(r"\b(?:reset|rst)\w*\b.{0,40}\b(?:not\s+driven|undriven|multiple\s+drivers|not\s+connected)", re.I),
            re.compile(r"signal\s+\w+\s+is\s+delayed\s+by\s+more\s+than", re.I),
        ],
        "Check clock and reset signal connections and drive strength",
        "high",
    ),
    (
        "testbench_error",
        [
            re.compile(r"no\s+testbench\s+found|testbench\s+(?:contains\s+)?no\s+assertions", re.I),
            re.compile(r"TB_COMPLETE.*missing|completion\s+marker.*missing", re.I),
            re.compile(r"testbench.*(?:entity|architecture)\s+not\s+(?:found|found\s+in)", re.I),
        ],
        "Add assertions to testbench and ensure TB_COMPLETE marker is present",
        "high",
    ),
    (
        # Differentieller Test: Entwurf weicht vom Python-Referenzmodell ab
        # (MODEL_MISMATCH cycle=.. port=.. expected=.. got=..).
        "model_mismatch",
        [
            re.compile(r"MODEL_MISMATCH|model\s+mismatch", re.I),
        ],
        "Align the design with the reference model at the reported cycle and port",
        "high",
    ),
    (
        # Mutationsanalyse: Testbenches erkennen absichtlich fehlerhafte Varianten nicht.
        "weak_testbench",
        [
            re.compile(r"weak\s+testbench|mutation\s+score", re.I),
        ],
        "Strengthen the testbench so it detects the listed surviving mutants",
        "medium",
    ),
    (
        "functional_simulation_error",
        [
            re.compile(r"runtime\s+error|simulation\s+failed|index\s+(?:out\s+of|range)", re.I),
            re.compile(r"delta\s+cycle\s+limit|simulation\s+loop\s+(?:detected|exceeded)", re.I),
            re.compile(r"^\s*\*\*\s+Error:\s+.*(?:range\s+constraint|stack\s+overflow)", re.M | re.I),
        ],
        "Fix runtime errors: check array bounds, loop termination, and signal drivers",
        "high",
    ),
    (
        "synthesis_error",
        [
            re.compile(r"synthesis\s+error|synth\s+(?:error|warning\[ynth-\d+\])", re.I),
            re.compile(r"unsupported\s+(?:construct|expression|operator)", re.I),
            re.compile(r"(?:infer(?:ring|red)|cannot)\s+(?:latch|ram|rom|flip-flop)", re.I),
            re.compile(r"combinational\s+loop|zero\s+repeater", re.I),
        ],
        "Remove non-synthesizable constructs (wait, after, file I/O) and fix inference issues",
        "high",
    ),
    (
        "timing_error",
        [
            re.compile(r"timing\s+(?:violation|error|constraint|unmet)", re.I),
            re.compile(r"(?:setup|hold)\s+(?:time|violation|slack\s+(?:is\s+)?negative)", re.I),
            re.compile(r"maximum\s+frequency\s+(?:not\s+met|exceeded|below)", re.I),
        ],
        "Add pipeline registers, optimize critical path, or reduce clock frequency",
        "critical",
    ),
    (
        "resource_error",
        [
            re.compile(r"resource\s+(?:error|exceeded|limit|overflow)", re.I),
            re.compile(r"(?:LUT|BRAM|DSP|FF)\s+(?:usage|count|limit)\s+(?:exceeded|over)", re.I),
            re.compile(r"not\s+enough\s+(?:resources|logic\s+cells)", re.I),
        ],
        "Reduce resource usage or target a larger FPGA device",
        "critical",
    ),
    (
        "bitstream_error",
        [
            re.compile(r"bitstream\s+(?:error|failed|generation\s+failed)", re.I),
            re.compile(r"(?:write_bitstream|program_bitstream)\s+failed", re.I),
            re.compile(r"(?:invalid|corrupt)\s+bitstream", re.I),
        ],
        "Check design constraints and re-run synthesis/implementation",
        "critical",
    ),
    (
        "hardware_error",
        [
            re.compile(r"hardware\s+(?:test\s+)?(?:error|failed|mismatch)", re.I),
            re.compile(r"(?:JTAG|SPI)\s+(?:error|not\s+found|chain\s+broken)", re.I),
            re.compile(r"FPGA\s+(?:not\s+responding|programming\s+failed)", re.I),
            re.compile(r"board\s+(?:not\s+found|disconnected)", re.I),
        ],
        "Check board connection, JTAG/SPI cable, and re-flash bitstream",
        "medium",
    ),
    (
        # Simulation (inkl. Golden-Model-Vektoren) war grün, die reale Hardware
        # antwortet trotzdem mit einem anderen Wert: kein Infra-/Board-Fehler,
        # sondern eine echte Software/Hardware-Diskrepanz (CDC, Reset-Annahmen,
        # Initialwerte ...), siehe hardware_test.py.
        "simulation_hardware_divergence",
        [
            re.compile(r"diverged\s+from\s+(?:the\s+)?(?:passed\s+)?simulation", re.I),
            re.compile(r"simulation.{0,20}hardware.{0,20}diverg", re.I),
        ],
        "Simulation passed but hardware disagrees: check clock-domain crossings, "
        "reset assumptions, and register initial values that simulation cannot catch",
        "high",
    ),
]


def classify_error(message: str, stage: str = "") -> tuple[str, str, str]:
    """Klassifiziert eine Fehlermeldung anhand von Regex-Patterns.

    Returns:
        (failure_type, recommended_action, severity)
    """
    for failure_type, patterns, action, severity in _ERROR_PATTERNS:
        for pat in patterns:
            if pat.search(message):
                return failure_type, action, severity
    return "unknown", "Manual investigation required", "medium"


class DebugAgent(BaseAgent):
    """Analysiert Fehler und erstellt strukturierte Diagnosen.
    
    Analysiert Fehler aus:
    - VHDL Compiler (GHDL Analyse/Elaboration)
    - GHDL Simulation
    - Vivado Synthese
    - Place & Route
    - Timing Analysis
    - FPGA-Programmierung
    - Hardware-Tests
    
    Erstellt strukturierte Diagnose und empfiehlt Reparatur-Aktionen.
    """

    def __init__(self, event_publisher=None):
        super().__init__("DebugAgent", event_publisher)

    @property
    def supported_task_types(self) -> list[str]:
        return ["diagnose", "analyze_failure", "recommend_repair"]

    async def execute(self, task: AgentTask) -> AgentResult:
        task_type = task.type
        
        if task_type == "diagnose":
            return await self._diagnose(task)
        elif task_type == "analyze_failure":
            return await self._analyze_failure(task)
        elif task_type == "recommend_repair":
            return await self._recommend_repair(task)
        else:
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.FAILED,
                error_message=f"Unknown task type: {task_type}",
            )

    async def _diagnose(self, task: AgentTask) -> AgentResult:
        """Erstellt strukturierte Diagnose aus Fehlerinformationen."""
        diagnostics = task.inputs.get("diagnostics", [])
        current_stage = task.inputs.get("current_stage", "unknown")
        workspace = task.inputs.get("workspace", "")
        architecture = task.inputs.get("architecture", {})
        
        # Alle Diagnostics sammeln und analysieren
        combined_diagnosis = await self._analyze_all_diagnostics(
            diagnostics, current_stage, workspace, architecture
        )
        
        if combined_diagnosis:
            self.emit_event("DEBUG_COMPLETED", {
                "task_id": task.id,
                "suspected_modules": combined_diagnosis.suspected_modules,
                "failure_type": combined_diagnosis.failure_type,
            })
            
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.COMPLETED,
                outputs={"diagnosis": combined_diagnosis.to_dict()},
            )
        else:
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.FAILED,
                error_message="Could not create diagnosis",
            )

    async def _analyze_all_diagnostics(
        self, diagnostics: list[dict], stage: str, workspace: str, architecture: dict
    ) -> DebugDiagnosis | None:
        """Classify only facts present in the supplied logs and architecture."""
        if not diagnostics:
            return DebugDiagnosis(
                status="unknown",
                stage=stage,
                failure_type="no_diagnostics",
                suspected_modules=[],
                evidence=[],
                recommended_action="Check logs for errors",
            )
        return self._fallback_diagnosis(diagnostics, stage, architecture)

    def _fallback_diagnosis(
        self, diagnostics: list[dict], stage: str, architecture: dict
    ) -> DebugDiagnosis:
        """Regex-basierte Diagnose als Fallback (nutzt classify_error)."""

        modules = [
            m.get("name", "") if isinstance(m, dict) else getattr(m, "name", "")
            for m in architecture.get("modules", [])
        ]

        evidence: list[str] = []
        failure_type = "unknown"
        recommended = "Manual investigation required"
        severity = "medium"

        for d in diagnostics:
            msg = d.get("message", "")
            if len(msg.encode("utf-8")) > 200_000:
                half = 100_000
                msg = msg[:half] + "\n...[truncated middle of diagnostic]...\n" + msg[-half:]
            evidence.append(msg)

            ft, rec, sev = classify_error(msg, stage)
            # Strukturierte Fehlerklassen der Gates (Contract, Coverage,
            # Timing ...) sind verlässlicher als Regex auf dem Freitext.
            explicit = d.get("failure_type")
            if explicit:
                ft = explicit
                fallback = classify_error(explicit.replace("_", " "), stage)
                if ft == fallback[0]:
                    rec, sev = fallback[1], fallback[2]
            # Höchste Schwere gewinnt; erster konkreter Treiber gewinnt Typ
            if ft != "unknown" and failure_type == "unknown":
                failure_type = ft
                recommended = rec
                severity = sev
            elif ft != "unknown":
                _SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}
                if _SEVERITY_ORDER.get(sev, 0) > _SEVERITY_ORDER.get(severity, 0):
                    severity = sev
                    recommended = rec

        # Only modules explicitly matched to known architecture names are listed.
        suspected = self._extract_modules_from_errors(evidence, modules)
        for d in diagnostics:
            for module in d.get("modules", []) or []:
                if module in modules and module not in suspected:
                    suspected.insert(0, module)

        return DebugDiagnosis(
            status="failed",
            stage=stage,
            suspected_modules=suspected,
            failure_type=failure_type,
            evidence=evidence,
            recommended_action=recommended,
            severity=severity,
        )

    @staticmethod
    def _extract_modules_from_errors(
        evidence: list[str], known_modules: list[str]
    ) -> list[str]:
        """Extrahiert verdächtige Modulnamen aus Fehlermeldungen.

        Versucht zuerst, ghdl-Ausgabezeilen wie
            path/to/file.vhd:42:3: error: ...
        zu parsen und den Dateinamen auf bekannte Module abzubilden.
        Falls das fehlschlägt, wird nach Modulnamen im Fließtext gesucht.
        """
        suspected: list[str] = []
        # GHDL-/Vivado-Fehlerzeilen: "file:line:col: error: ..."
        ghdl_file_pat = re.compile(
            r"(?:^|\s)(\w[\w./-]*\.vhd(?:hl)?)\s*:\d+", re.M
        )
        for ev in evidence:
            for m in ghdl_file_pat.finditer(ev):
                fname = m.group(1).lower().split("/")[-1].split("\\")[-1]
                fname = re.sub(r"\.vhd(?:hl)?$", "", fname)
                for mod in known_modules:
                    if mod.lower() in fname or fname in mod.lower():
                        if mod not in suspected:
                            suspected.append(mod)
        # Fallback: Modulnamen im Fließtext suchen
        if not suspected:
            for ev in evidence:
                ev_lower = ev.lower()
                for mod in known_modules:
                    if mod.lower() in ev_lower and mod not in suspected:
                        suspected.append(mod)
        return suspected

    async def _analyze_failure(self, task: AgentTask) -> AgentResult:
        """Detaillierte Analyse eines spezifischen Fehlers."""
        error_details = task.inputs.get("error_details", {})
        
        return await self._diagnose(AgentTask(
            id=task.id,
            type="diagnose",
            project_id=task.project_id,
            inputs={
                "diagnostics": [error_details],
                "current_stage": task.inputs.get("stage", "unknown"),
                "workspace": task.inputs.get("workspace", ""),
                "architecture": task.inputs.get("architecture", {}),
            },
        ))

    async def _recommend_repair(self, task: AgentTask) -> AgentResult:
        """Empfiehlt konkrete Reparatur-Schritte."""
        diagnosis = task.inputs.get("diagnosis", {})
        
        if not diagnosis:
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.FAILED,
                error_message="No diagnosis provided",
            )
        
        # Reparatur-Empfehlung basierend auf Diagnose
        failure_type = diagnosis.get("failure_type", "")
        suspected = diagnosis.get("suspected_modules", [])
        
        repair_actions = {
            "infrastructure": "Install missing system dependency or check tool installation",
            "syntax_error": "Fix VHDL syntax in affected modules",
            "type_error": "Fix type mismatches and undeclared identifiers",
            "elaboration_error": "Check generics, port maps, and component declarations",
            "interface_mismatch": "Align port definitions between modules",
            "clock_reset_error": "Check clock and reset signal connections and drive strength",
            "testbench_error": "Add assertions to testbench and ensure TB_COMPLETE marker is present",
            "functional_simulation_error": "Fix runtime errors: check array bounds, loop termination, and signal drivers",
            "synthesis_error": "Remove non-synthesizable constructs (wait, after, file I/O)",
            "timing_error": "Add pipeline registers or optimize critical path",
            "resource_error": "Reduce resource usage or target a larger FPGA device",
            "bitstream_error": "Check design constraints and re-run synthesis/implementation",
            "hardware_error": "Check board connection, JTAG/SPI cable, and re-flash bitstream",
            "simulation_hardware_divergence": (
                "Simulation (incl. golden-model vectors) passed but real hardware returned a "
                "different value: review clock-domain crossings, reset assumptions, and register "
                "initial values that the testbench cannot observe"
            ),
            "logic_error": "Review testbench expectations and DUT logic",
            "constraint_error": "Add missing pin/clock constraints to the board constraint file",
            "contract_violation": "Align the module entity with its architecture contract",
            "coverage_gap": "Add or adapt testbenches for uncovered modules",
            "model_mismatch": (
                "The design differs from the executable reference model: fix the RTL at the reported "
                "cycle/port; if repeated, re-check the model's reading of the specification"
            ),
            "weak_testbench": "Add checks that detect the surviving mutants (listed in the diagnosis)",
            "flash_error": "Check USB cable, drivers and programmer selection",
        }
        
        action = repair_actions.get(failure_type, "Manual investigation required")
        
        return AgentResult(
            task_id=task.id,
            status=AgentStatus.COMPLETED,
            outputs={
                "repair_action": action,
                "target_modules": suspected,
                "priority": diagnosis.get("severity", "medium"),
            },
        )