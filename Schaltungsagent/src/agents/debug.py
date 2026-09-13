import logging
import uuid
from typing import Any

from src.domain.agents import BaseAgent, AgentTask, AgentResult, AgentStatus
from src.domain.agents.communication import DebugDiagnosis

logger = logging.getLogger(__name__)


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

    def __init__(self, llm_service, rag_service, event_publisher=None):
        super().__init__("DebugAgent", event_publisher)
        self._llm = llm_service
        self._rag = rag_service

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
        """Analysiert alle Diagnosen und erstellt konsolidierte Diagnose."""
        
        if not diagnostics:
            return DebugDiagnosis(
                status="unknown",
                stage=stage,
                failure_type="no_diagnostics",
                recommended_action="Check logs for errors",
            )
        
        # Fehlertyp klassifizieren
        failure_types = [d.get("type", "") for d in diagnostics]
        stages = [d.get("stage", stage) for d in diagnostics]
        messages = [d.get("message", "") for d in diagnostics]
        
        # RAG für bekannte Fehler-Patterns abfragen
        error_context = "\n".join(messages[:3])
        known_errors = self._rag.retrieve_knowledge(
            f"debug {stage} error {error_context}", "vhdl"
        )
        
        # LLM für detaillierte Analyse
        prompt = f"""Analysiere folgende Hardware-Design-Fehler und erstelle eine strukturierte Diagnose:

FEHLER-STAGE: {stage}
FEHLER-TYPEN: {failure_types}
FEHLER-MELDUNGEN:
{chr(10).join(messages[:5])}

ARCHITEKTUR:
{architecture.get('modules', [])}

BEKANNTE FEHLER-MUSTER:
{known_errors.raw_context if hasattr(known_errors, 'raw_context') else known_errors}

Erstelle eine JSON-Diagnose mit:
- status: "failed" oder "unknown"
- stage: "{stage}"
- suspected_modules: Liste verdächtiger Module
- failure_type: Klassifikation (z.B. "syntax_error", "timing_violation", "logic_error", "interface_mismatch", "synthesis_failure", "flash_failure")
- evidence: Liste konkreter Beweise aus Fehlermeldungen
- recommended_action: Konkret nächste Aktion für Reparatur
- severity: "low" | "medium" | "high" | "critical"

Beispiel:
{{
  "status": "failed",
  "stage": "simulation",
  "suspected_modules": ["alu", "control_unit"],
  "failure_type": "incorrect_result",
  "evidence": ["ADD instruction produced 0x11 instead of 0x0F", "Carry flag not set correctly"],
  "recommended_action": "Inspect ALU carry handling in combinational process",
  "severity": "high"
}}"""

        try:
            import json
            import re
            
            response = self._llm.generate_code(prompt, temperature=0.1)
            
            # JSON aus Response extrahieren
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                diagnosis_data = json.loads(json_match.group(0))
                
                return DebugDiagnosis(
                    status=diagnosis_data.get("status", "failed"),
                    stage=diagnosis_data.get("stage", stage),
                    suspected_modules=diagnosis_data.get("suspected_modules", []),
                    failure_type=diagnosis_data.get("failure_type", "unknown"),
                    evidence=diagnosis_data.get("evidence", []),
                    recommended_action=diagnosis_data.get("recommended_action", "Manual investigation required"),
                    severity=diagnosis_data.get("severity", "medium"),
                )
        except Exception as e:
            logger.warning(f"LLM diagnosis failed: {e}")
        
        # Fallback: Einfache regelbasierte Diagnose
        return self._fallback_diagnosis(diagnostics, stage, architecture)

    def _fallback_diagnosis(
        self, diagnostics: list[dict], stage: str, architecture: dict
    ) -> DebugDiagnosis:
        """Einfache regelbasierte Diagnose als Fallback."""
        
        modules = [m.get("name", "") for m in architecture.get("modules", [])]
        
        # Fehler klassifizieren
        failure_type = "unknown"
        suspected = []
        evidence = []
        recommended = "Manual investigation required"
        severity = "medium"
        
        for d in diagnostics:
            msg = d.get("message", "").lower()
            details_str = str(d.get("details", {})).lower()
            evidence.append(d.get("message", "")[:200])
            
            if "missing" in msg and ("lib" in msg or "system" in msg or "shared object" in msg or "cannot open" in msg):
                failure_type = "infrastructure"
                severity = "critical"
                recommended = "Install missing system dependency or use alternative tool"
            elif "vivado" in msg and ("license" in msg or "limit" in msg or "tool version" in msg):
                failure_type = "infrastructure"
                severity = "critical"
                recommended = "Check Vivado license or use compatible version"
            elif "syntax" in msg or "parse" in msg:
                failure_type = "syntax_error"
                severity = "high"
                recommended = "Fix VHDL syntax errors in reported files"
            elif "elaboration" in msg or "bind" in msg:
                failure_type = "elaboration_error"
                severity = "high"
                recommended = "Check entity/architecture binding and generics"
            elif "assertion" in msg or "tb_complete" in msg or "mismatch" in msg:
                failure_type = "logic_error"
                severity = "high"
                recommended = "Review testbench expectations and DUT logic"
            elif "timing" in msg or "setup" in msg or "hold" in msg:
                failure_type = "timing_violation"
                severity = "critical"
                recommended = "Add pipeline stages or reduce clock frequency"
            elif "synthesis" in msg or "vivado" in msg:
                failure_type = "synthesis_failure"
                severity = "high"
                recommended = "Make code synthesizable (remove wait, dynamic allocation, etc.)"
            elif "flash" in msg or "program" in msg or "jtag" in msg:
                failure_type = "flash_failure"
                severity = "medium"
                recommended = "Check board connection and JTAG chain"
        
        # Verdächtige Module aus Fehlermeldungen extrahieren
        for module in modules:
            if any(module.lower() in e.lower() for e in evidence):
                suspected.append(module)
        
        if not suspected and modules:
            suspected = [modules[0]]  # Erstes Modul als Fallback
        
        return DebugDiagnosis(
            status="failed",
            stage=stage,
            suspected_modules=suspected,
            failure_type=failure_type,
            evidence=evidence,
            recommended_action=recommended,
            severity=severity,
        )

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
            "syntax_error": "Fix VHDL syntax in affected modules",
            "elaboration_error": "Check generics, port maps, and component declarations",
            "logic_error": "Review combinational logic and state machine transitions",
            "timing_violation": "Add pipeline registers or optimize critical path",
            "synthesis_failure": "Remove non-synthesizable constructs (wait, after, file I/O)",
            "interface_mismatch": "Align port definitions between modules",
            "flash_failure": "Verify board connection, JTAG cable, and bitstream format",
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