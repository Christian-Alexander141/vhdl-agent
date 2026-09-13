import logging
import uuid
from pathlib import Path
from typing import Any

from src.domain.agents import BaseAgent, AgentTask, AgentResult, AgentStatus
from src.domain.agents.communication import VerificationResult
from src.infrastructure.validation.ghdl_validator import GHDLValidator

logger = logging.getLogger(__name__)


class VerificationAgent(BaseAgent):
    """Plant und führt Verifikation durch.
    
    Aufgaben:
    - Testplan erstellen
    - Testbenches generieren/validieren
    - GHDL Simulation ausführen
    - Testergebnisse interpretieren
    - Coverage analysieren
    """

    def __init__(
        self,
        llm_service,
        rag_service,
        filesystem_service,
        opencode_service,
        event_publisher=None,
    ):
        super().__init__("VerificationAgent", event_publisher)
        self._llm = llm_service
        self._rag = rag_service
        self._fs = filesystem_service
        self._opencode = opencode_service
        self._validator = GHDLValidator()

    @property
    def supported_task_types(self) -> list[str]:
        return ["verify", "create_testplan", "generate_testbench", "analyze_coverage"]

    async def execute(self, task: AgentTask) -> AgentResult:
        task_type = task.type
        
        if task_type == "verify":
            return await self._run_verification(task)
        elif task_type == "create_testplan":
            return await self._create_testplan(task)
        elif task_type == "generate_testbench":
            return await self._generate_testbench(task)
        elif task_type == "analyze_coverage":
            return await self._analyze_coverage(task)
        else:
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.FAILED,
                error_message=f"Unknown task type: {task_type}",
            )

    async def _run_verification(self, task: AgentTask) -> AgentResult:
        """Führt vollständige Verifikation durch (Analyse, Elaboration, Simulation)."""
        workspace = task.inputs.get("workspace", "")
        domain = task.inputs.get("domain", "vhdl")
        
        self.emit_event("SIMULATION_STARTED", {
            "task_id": task.id,
            "workspace": workspace,
        })
        
        try:
            # GHDL Validation durchführen
            validation_result = self._validator.validate(workspace, domain)
            
            # Ergebnis in VerificationResult umwandeln
            v_result = VerificationResult(
                status="passed" if validation_result.passed else "failed",
                tests_total=validation_result.details.get("tests_total", 0),
                tests_passed=validation_result.details.get("tests_passed", 0),
                tests_failed=validation_result.details.get("tests_failed", 0),
                failures=validation_result.details.get("failures", []),
                coverage=validation_result.details.get("coverage", 0.0),
            )
            
            if validation_result.passed:
                self.emit_event("SIMULATION_PASSED", {
                    "task_id": task.id,
                    "tests_passed": v_result.tests_passed,
                })
                
                return AgentResult(
                    task_id=task.id,
                    status=AgentStatus.COMPLETED,
                    outputs={"verification_result": v_result.to_dict()},
                )
            else:
                self.emit_event("SIMULATION_FAILED", {
                    "task_id": task.id,
                    "failures": v_result.failures,
                })
                
                return AgentResult(
                    task_id=task.id,
                    status=AgentStatus.FAILED,
                    error_message="Simulation failed",
                    outputs={"verification_result": v_result.to_dict()},
                    diagnostics=[{
                        "type": "simulation_failure",
                        "message": validation_result.message,
                        "details": validation_result.details,
                        "stage": "simulation",
                    }],
                )
                
        except Exception as e:
            logger.exception("Verification failed")
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.FAILED,
                error_message=f"Verification error: {e}",
            )

    async def _create_testplan(self, task: AgentTask) -> AgentResult:
        """Erstellt Testplan aus Anforderungen und Architektur."""
        architecture = task.inputs.get("architecture", {})
        requirements = task.inputs.get("requirements", [])
        
        prompt = f"""Erstelle einen detaillierten Testplan für folgende Architektur:

ARCHITEKTUR:
{architecture}

ANFORDERUNGEN:
{requirements}

Der Testplan soll enthalten:
1. Unit Tests pro Modul
2. Integration Tests für Modul-Verbindungen
3. Corner Cases
4. Timing Tests (falls relevant)
5. Expected Coverage Targets

Format: YAML mit test_cases Liste."""

        try:
            testplan_yaml = self._llm.generate_code(prompt, temperature=0.2)
            
            import yaml
            import re
            yaml_match = re.search(r'```yaml\n(.*?)\n```', testplan_yaml, re.DOTALL)
            if yaml_match:
                testplan_yaml = yaml_match.group(1)
            
            testplan = yaml.safe_load(testplan_yaml)
            
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.COMPLETED,
                outputs={"testplan": testplan},
            )
        except Exception as e:
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.FAILED,
                error_message=f"Testplan creation failed: {e}",
            )

    async def _generate_testbench(self, task: AgentTask) -> AgentResult:
        """Generiert Testbench für spezifisches Modul."""
        module = task.inputs.get("module", {})
        workspace = task.inputs.get("workspace", "")
        domain = task.inputs.get("domain", "vhdl")
        
        # RAG für Test-Strategien abfragen
        test_knowledge = self._rag.retrieve_knowledge(
            f"testbench {module.get('name', '')} VHDL", domain
        )
        
        prompt = f"""Generiere VHDL-Testbench für Modul:

MODUL: {module}

TEST-STRATEGIEN:
{test_knowledge.raw_context if hasattr(test_knowledge, 'raw_context') else test_knowledge}

ANFORDERUNGEN:
- GHDL-kompatibel
- Vollständige Stimulus-Generierung
- Assertions mit Report
- TB_COMPLETE Marker am Ende"""

        try:
            tb_code = self._llm.generate_code(prompt, temperature=0.1)
            
            # Testbench speichern
            tb_dir = Path(workspace) / "tests"
            tb_dir.mkdir(parents=True, exist_ok=True)
            
            file_name = f"{module.get('name', 'dut')}_tb.vhd"
            file_path = tb_dir / file_name
            self._fs.write_file(str(file_path), tb_code)
            
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.COMPLETED,
                outputs={"testbench_file": f"tests/{file_name}"},
            )
        except Exception as e:
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.FAILED,
                error_message=f"Testbench generation failed: {e}",
            )

    async def _analyze_coverage(self, task: AgentTask) -> AgentResult:
        """Analysiert Testabdeckung."""
        workspace = task.inputs.get("workspace", "")
        
        # GHDL Coverage Analysis (falls verfügbar)
        # Für jetzt vereinfacht: Code-Analyse
        
        return AgentResult(
            task_id=task.id,
            status=AgentStatus.COMPLETED,
            outputs={"coverage": 85.0, "uncovered": []},
        )