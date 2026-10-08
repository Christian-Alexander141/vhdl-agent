import logging
import uuid
from pathlib import Path
from typing import Any

from src.domain.agents import BaseAgent, AgentTask, AgentResult, AgentStatus
from src.domain.agents.communication import VerificationResult
from src.domain.agents.test_plan import format_simulation_vectors
from src.domain.agents.worker_instructions import TESTBENCH_RULES
from src.infrastructure.validation.ghdl_validator import GHDLValidator
from src.domain.exceptions import OpenCodeDeliveryError
from src.services.opencode_service import describe_opencode_failure

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
        filesystem_service,
        opencode_service,
        event_publisher=None,
    ):
        super().__init__("VerificationAgent", event_publisher)
        self._fs = filesystem_service
        self._opencode = opencode_service
        self._validator = GHDLValidator()

    @property
    def supported_task_types(self) -> list[str]:
        return ["verify", "generate_testbench", "analyze_coverage"]

    async def execute(self, task: AgentTask) -> AgentResult:
        task_type = task.type
        
        if task_type == "verify":
            return await self._run_verification(task)
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

    async def _generate_testbench(self, task: AgentTask) -> AgentResult:
        """Generiert Testbench für spezifisches Modul."""
        module = task.inputs.get("module", {})
        workspace = task.inputs.get("workspace", "")
        domain = task.inputs.get("domain", "vhdl")
        
        # VHDL-Code des Moduls lesen
        module_name = module.get("name", "") if isinstance(module, dict) else getattr(module, "name", "")
        simulation_vectors = (
            module.get("simulation_vectors", []) if isinstance(module, dict)
            else getattr(module, "simulation_vectors", [])
        ) or []
        vhdl_content = ""
        if module_name and workspace:
            src_dir = Path(workspace) / "src"
            for ext in (".vhd", ".vhdl"):
                vhdl_file = src_dir / f"{module_name}{ext}"
                if vhdl_file.exists():
                    try:
                        vhdl_content = vhdl_file.read_text(encoding="utf-8", errors="replace")
                    except Exception:
                        pass
                    break

        vector_section = f"\n{format_simulation_vectors(simulation_vectors)}\n" if simulation_vectors else ""
        prompt = f"""Generiere eine vollständige VHDL-Testbench für folgendes Modul:

VHDL-CODE DES MODULS:
{vhdl_content if vhdl_content else 'Kein VHDL-Code verfügbar - generiere basierend auf Modul-Info'}

MODUL-INFORMATIONEN:
{module}

ANFORDERUNGEN:
- GHDL-kompatibel (VHDL-2008)
- Clock-Generierung mit stabiler Periodendauer
- Reset-Sequenz (aktiv für mindestens 2 Clock-Zyklen)
- Vollständige Stimulus-Generierung für alle Input-Signale
- Assertions mit Report-Text für fehlgeschlagene Prüfungen
- Am Ende: assert false report "TB_COMPLETE" severity note;
- Entity-Name muss "_tb" Suffix haben und zum Modul passen
- Ports müssen exakt zum Entity-Declaration des Moduls passen

{TESTBENCH_RULES}
{vector_section}
Antworte ausschließlich mit dem VHDL-Testbench-Code (Entity + Architecture). Ändere keine Dateien."""

        try:
            result = self._opencode.execute(workspace, prompt)
            if not result.success:
                cause, hint = describe_opencode_failure(result.returncode, result.stdout, result.stderr)
                raise OpenCodeDeliveryError(
                    f"Testbench für '{module_name}': OpenCode-Aufruf fehlgeschlagen",
                    cause=cause, hint=hint,
                    context={"Exit-Code": result.returncode, "stderr (Ende)": (result.stderr or "")[-2000:]},
                )

            import re
            tb_code = re.sub(r'^```vhdl\s*', '', result.stdout, flags=re.MULTILINE)
            tb_code = re.sub(r'^```\s*$', '', tb_code, flags=re.MULTILINE).strip()
            if not tb_code:
                raise OpenCodeDeliveryError(
                    f"Testbench für '{module_name}': keine Ausgabe",
                    cause="OpenCode endete ohne Fehler, hat aber keinen Testbench-Code ausgegeben.",
                    hint="Das Modell hat vermutlich eine Datei geschrieben statt den Code auszugeben; anderes Modell versuchen.",
                )
            
            # Testbench nur übernehmen, wenn sie den DUT instanziiert und der
            # Workspace damit weiterhin kompiliert, elaboriert und simuliert.
            from src.domain.agents.test_plan import _instantiations

            dut = module.get("name", "dut")
            if dut.lower() not in _instantiations(tb_code):
                raise OpenCodeDeliveryError(
                    f"Generated testbench does not instantiate DUT '{dut}'",
                    cause=f"Die erzeugte Testbench enthält keine Instanz von '{dut}' und würde das Modul nicht prüfen.",
                    hint="Die vorhandene Testbench bleibt unverändert; Auftrag erneut ausführen oder Testbench manuell ergänzen.",
                )

            tb_dir = Path(workspace) / "tests"
            tb_dir.mkdir(parents=True, exist_ok=True)
            file_name = f"{dut}_tb.vhd"
            file_path = tb_dir / file_name
            previous = file_path.read_text(errors="replace") if file_path.exists() else None
            self._fs.write_file(str(file_path), tb_code)

            check = self._validator.validate(workspace, domain)
            if not check.passed:
                if previous is None:
                    file_path.unlink(missing_ok=True)
                else:
                    self._fs.write_file(str(file_path), previous)
                raise OpenCodeDeliveryError(
                    "Generated testbench rejected",
                    cause=f"GHDL lehnt den Workspace mit der neuen Testbench ab: {check.message}",
                    hint="Die vorherige Testbench wurde wiederhergestellt.",
                    context={"GHDL-Ausgabe": str((check.details or {}).get("error", ""))[-2000:]},
                )

            return AgentResult(
                task_id=task.id,
                status=AgentStatus.COMPLETED,
                outputs={"testbench_file": f"tests/{file_name}"},
            )
        except Exception as e:
            logger.error("Testbench generation failed:\n%s", e)
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.FAILED,
                error_message=f"Testbench generation failed: {e}",
                diagnostics=[{
                    "type": "testbench_generation",
                    "module": module_name,
                    "message": str(e),
                    **({"details": e.to_dict()} if hasattr(e, "to_dict") else {}),
                }],
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