import logging
import re
import uuid
from pathlib import Path
from typing import Any
from src.domain.agents import BaseAgent, AgentTask, AgentResult, AgentStatus
from src.infrastructure.synthesis.vivado_synthesis import VivadoBitstreamService
from src.infrastructure.synthesis.vivado_flash import VivadoFlashService
from src.services.flash_service import OpenFPGALoaderFlashService
from src.config import load_fpga_registry
from src.domain.agents.triage import classify_flash_output

logger = logging.getLogger(__name__)


SYNTHESIS_CACHE = "build/bitstream/synthesis_cache.json"


def synthesis_digest(workspace: str, target_fpga: str, timing_gate: bool, top_entity: str = "") -> str:
    """Prüfsumme über alles, was den Bitstream bestimmt."""
    import hashlib
    from src.infrastructure.synthesis.vivado_synthesis import BUILD_SCRIPT_VERSION

    root = Path(workspace)
    digest = hashlib.sha256(f"{BUILD_SCRIPT_VERSION}|{target_fpga}|{timing_gate}|{top_entity}".encode())
    for folder, pattern in (("src", "*.vhd*"), ("constraints", "*.xdc")):
        for path in sorted((root / folder).glob(pattern)) if (root / folder).is_dir() else []:
            if path.name == "auto_generated.xdc":  # wird aus src und Board abgeleitet
                continue
            digest.update(f"{folder}/{path.name}".encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def read_synthesis_cache(workspace: str, digest: str) -> dict | None:
    import json

    path = Path(workspace) / SYNTHESIS_CACHE
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    outputs = data.get("outputs") or {}
    if data.get("digest") != digest or not Path(outputs.get("bitstream_path") or "/nonexistent").is_file():
        return None
    return outputs


def write_synthesis_cache(workspace: str, digest: str, outputs: dict) -> None:
    import json

    path = Path(workspace) / SYNTHESIS_CACHE
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"digest": digest, "outputs": outputs}, default=str))
    except OSError:
        logger.warning("Could not write synthesis cache %s", path)


def invalidate_synthesis_cache(workspace: str) -> None:
    (Path(workspace) / SYNTHESIS_CACHE).unlink(missing_ok=True)


class FPGAAgent(BaseAgent):
    """Verantwortlich für FPGA-Synthese, Bitstream-Erzeugung und Flash.
    
    Verwendet deterministische Tools:
    - Vivado für Synthese, Place & Route, Bitstream
    - Vivado Hardware Manager / openFPGALoader für Flash
    """

    def __init__(
        self,
        filesystem_service,
        event_publisher=None,
        vivado_binary: str = "vivado",
        vivado_settings: str = "",
        require_timing_closure: bool = True,
        vivado_timeout: int = 600,
    ):
        super().__init__("FPGAAgent", event_publisher)
        self._fs = filesystem_service
        self._require_timing_closure = require_timing_closure
        
        # Services initialisieren
        self._bitstream_service = VivadoBitstreamService(
            vivado_binary=vivado_binary,
            settings_script=vivado_settings,
            timeout_seconds=vivado_timeout,
        )
        self._vivado_flash = VivadoFlashService(
            vivado_binary=vivado_binary,
            settings_script=vivado_settings,
        )
        self._openfpgaloader_flash = OpenFPGALoaderFlashService()
        
        # FPGA Registry
        self._fpga_registry = load_fpga_registry()

    @property
    def supported_task_types(self) -> list[str]:
        return ["synthesize", "build_bitstream", "flash", "analyze_timing", "check_resources"]

    async def execute(self, task: AgentTask) -> AgentResult:
        task_type = task.type
        
        if task_type == "synthesize":
            return await self._run_synthesis(task)
        elif task_type == "build_bitstream":
            return await self._build_bitstream(task)
        elif task_type == "flash":
            return await self._flash_fpga(task)
        elif task_type == "analyze_timing":
            return await self._analyze_timing(task)
        elif task_type == "check_resources":
            return await self._check_resources(task)
        else:
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.FAILED,
                error_message=f"Unknown task type: {task_type}",
            )

    async def _run_synthesis(self, task: AgentTask) -> AgentResult:
        """Führt vollständige Synthese durch (GHDL + Vivado)."""
        workspace = task.inputs.get("workspace", "")
        target_fpga = task.inputs.get("target_fpga", "arty_s7_50")
        domain = task.inputs.get("domain", "vhdl")
        # Top-Level aus der Architektur: ohne Angabe scheiterte Vivado an jedem
        # Entwurf mit mehreren Modulen ("Multiple top-level entities found").
        top_entity = task.inputs.get("top_entity", "")
        
        self.emit_event("SYNTHESIS_STARTED", {
            "task_id": task.id,
            "target_fpga": target_fpga,
        })

        digest = synthesis_digest(workspace, target_fpga, self._require_timing_closure, top_entity)
        cached = read_synthesis_cache(workspace, digest)
        if cached:
            # Lauf gray-countdown 2026-10-11: Nach jeder (ergebnislosen)
            # Reparatur wurde der unveränderte Entwurf erneut 5-8 min
            # synthetisiert. Gleiche Quellen + Constraints + Build-Skript
            # ergeben denselben Bitstream.
            self.emit_event("SYNTHESIS_FINISHED", {
                "task_id": task.id, "passed": True, "cached": True,
                "bitstream_path": cached["bitstream_path"],
                "message": "Synthese übersprungen: Quellen, Constraints und Build-Skript unverändert",
            })
            return AgentResult(task_id=task.id, status=AgentStatus.COMPLETED, outputs=cached)

        # 1. GHDL Synthese-Prüfung (Stufe 1)
        from src.infrastructure.synthesis.ghdl_synthesis import GHDLSynthesisService
        ghdl_synth = GHDLSynthesisService()
        
        ghdl_result = ghdl_synth.synthesize(workspace, target_fpga, domain, top_entity=top_entity)
        
        if not ghdl_result.passed:
            self.emit_event("SYNTHESIS_FINISHED", {
                "task_id": task.id,
                "passed": False,
                "stage": "ghdl_synthesis",
                "message": ghdl_result.message,
            })
            
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.FAILED,
                error_message=f"GHDL synthesis failed: {ghdl_result.message}",
                diagnostics=[{
                    "type": "synthesis_failure",
                    "stage": "ghdl_synthesis",
                    # Sonst "unknown" ohne Modul: die Reparatur änderte dann
                    # ziellos den ganzen Entwurf.
                    "failure_type": "synthesis_error",
                    "message": ghdl_result.message,
                    "details": ghdl_result.details,
                }],
            )
        
        # 2. Vivado Bitstream-Erzeugung (Stufe 2)
        bitstream_result = self._bitstream_service.build_bitstream(
            workspace, target=target_fpga, domain=domain, top_entity=task.inputs.get("top_entity", "")
        )
        
        if not bitstream_result.passed:
            self.emit_event("SYNTHESIS_FINISHED", {
                "task_id": task.id,
                "passed": False,
                "stage": "vivado_bitstream",
                "message": bitstream_result.message,
            })
            
            cause, infrastructure = vivado_failure_cause(bitstream_result)
            message = f"{bitstream_result.message}: {cause}" if cause else bitstream_result.message
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.FAILED,
                error_message=f"Vivado bitstream generation failed: {message}",
                diagnostics=[{
                    "type": "synthesis_failure",
                    "stage": "vivado_bitstream",
                    "message": message,
                    "details": bitstream_result.details,
                    **({"failure_type": "infrastructure"} if infrastructure else {}),
                }],
            )
        
        bitstream_path = bitstream_result.bitstream_path

        # 3. Report-Gates: Ein Bitstream allein ist kein Erfolg. Timing und
        # Ressourcen stammen ausschließlich aus den Vivado-Reports.
        timing = self._parse_timing_report(workspace, bitstream_path)
        resources = self._parse_utilization_report(workspace, bitstream_path)
        synthesis_result = {
            **bitstream_result.to_dict(),
            "timing": timing,
            "resources": resources,
            "fpga_part": getattr(self._fpga_registry.get(target_fpga), "part", ""),
        }
        gate_failures = self.evaluate_gates(timing, resources) if self._require_timing_closure else []
        if gate_failures:
            message = "; ".join(f["message"] for f in gate_failures)
            synthesis_result["status"] = "failed"
            synthesis_result["errors"] = [f["message"] for f in gate_failures]
            self.emit_event("SYNTHESIS_FINISHED", {
                "task_id": task.id,
                "passed": False,
                "stage": "report_gates",
                "message": message,
                "timing": timing,
                "resources": resources,
            })
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.FAILED,
                error_message=f"Synthesis gates failed: {message}",
                outputs={"synthesis_result": synthesis_result, "bitstream_path": ""},
                diagnostics=[
                    {"type": "synthesis_gate", "stage": "synthesis", **failure}
                    for failure in gate_failures
                ],
            )

        synthesis_result["status"] = "passed"
        write_synthesis_cache(workspace, digest, {"bitstream_path": bitstream_path, "synthesis_result": synthesis_result})
        self.emit_event("SYNTHESIS_FINISHED", {
            "task_id": task.id,
            "passed": True,
            "bitstream_path": bitstream_path,
            "timing": timing,
            "resources": resources,
        })

        return AgentResult(
            task_id=task.id,
            status=AgentStatus.COMPLETED,
            outputs={
                "bitstream_path": bitstream_path,
                "synthesis_result": synthesis_result,
            },
        )

    async def _build_bitstream(self, task: AgentTask) -> AgentResult:
        """Erzeugt Bitstream (Vivado Non-Project Mode)."""
        workspace = task.inputs.get("workspace", "")
        target_fpga = task.inputs.get("target_fpga", "arty_s7_50")
        domain = task.inputs.get("domain", "vhdl")
        
        bitstream_result = self._bitstream_service.build_bitstream(
            workspace, target=target_fpga, domain=domain, top_entity=task.inputs.get("top_entity", "")
        )
        
        if bitstream_result.passed:
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.COMPLETED,
                outputs={
                    "bitstream_path": bitstream_result.bitstream_path,
                    "synthesis_result": bitstream_result.to_dict(),
                },
            )
        else:
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.FAILED,
                error_message=bitstream_result.message,
                diagnostics=[{
                    "type": "bitstream_failure",
                    "message": bitstream_result.message,
                    "details": bitstream_result.details,
                }],
            )

    async def _flash_fpga(self, task: AgentTask) -> AgentResult:
        """Flasht Bitstream auf FPGA."""
        bitstream_path = task.inputs.get("bitstream_path", "")
        target_fpga = task.inputs.get("target_fpga", "arty_s7_50")
        workspace = task.inputs.get("workspace", "")
        
        if not bitstream_path:
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.FAILED,
                error_message="No bitstream path provided",
            )
        
        # FPGA Config aus Registry
        fpga_config = self._fpga_registry.get(target_fpga)
        if not fpga_config:
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.FAILED,
                error_message=f"Unknown FPGA target: {target_fpga}",
            )
        
        expected_part = fpga_config.part
        board_name = fpga_config.board_name
        programmer = fpga_config.programmer
        
        self.emit_event("FLASH_STARTED", {
            "task_id": task.id,
            "bitstream": bitstream_path,
            "programmer": programmer,
        })
        
        # Richtigen Flash-Service wählen
        if programmer == "openfpgaloader":
            flash_service = self._openfpgaloader_flash
        else:
            flash_service = self._vivado_flash
        
        # Toolchain prüfen
        if not flash_service.toolchain_available():
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.FAILED,
                error_message=f"Flash toolchain not available: {programmer}",
                diagnostics=[{
                    "type": "flash_failure", "stage": "flash", "failure_type": "infrastructure",
                    "message": f"Flash toolchain not available: {programmer}",
                }],
            )
        
        # Flash durchführen
        flash_result = flash_service.flash(
            bitstream_path,
            board=board_name,
            expected_part=expected_part,
            workspace=workspace,
        )
        
        if flash_result.passed:
            self.emit_event("FLASH_FINISHED", {
                "task_id": task.id,
                "passed": True,
                "board_detected": flash_result.board_detected,
            })
            
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.COMPLETED,
                outputs={
                    "board_detected": flash_result.board_detected,
                    "flash_result": flash_result.to_dict(),
                },
            )
        else:
            self.emit_event("FLASH_FINISHED", {
                "task_id": task.id,
                "passed": False,
                "message": flash_result.message,
                "board_detected": flash_result.board_detected,
                "board_count": flash_result.board_count,
            })
            
            # Fehlerklasse und Vivado-Ausgabe mitgeben: früher nur die ersten
            # 500 Zeichen der Meldung, ohne Klasse -> "unknown" -> HDL-Reparatur.
            details = dict(flash_result.details or {})
            output = f"{details.get('stdout', '')}\n{details.get('stderr', '')}\n{flash_result.message}"
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.FAILED,
                error_message=f"Flash failed: {flash_result.message}",
                diagnostics=[{
                    "type": "flash_failure",
                    "stage": "flash",
                    "failure_type": classify_flash_output(output, flash_result.board_detected),
                    "message": flash_result.message,
                    "board_detected": flash_result.board_detected,
                    "board_count": flash_result.board_count,
                    "details": {k: details.get(k) for k in ("stdout", "stderr", "error", "detected_devices") if details.get(k)},
                }],
            )

    def _find_report_dir(self, workspace: str, bitstream_path: str = "") -> Path | None:
        if bitstream_path:
            candidate = Path(bitstream_path).parent
            if list(candidate.glob("*.rpt")):
                return candidate
        ws_path = Path(workspace)
        for candidate in [ws_path / "build" / "bitstream", ws_path / "build"]:
            if candidate.exists():
                rpt_files = list(candidate.glob("*.rpt"))
                if rpt_files:
                    return candidate
        return None

    @staticmethod
    def _to_float(token: str) -> float | None:
        try:
            return float(token)
        except (TypeError, ValueError):
            return None

    def _parse_timing_report(self, workspace: str, bitstream_path: str = "") -> dict:
        """Liest WNS/TNS/WHS/THS und Fmax aus Vivados report_timing_summary.

        Fehlende Werte bleiben ``None``; sie werden nie durch Annahmen ersetzt.
        """
        result = {
            "available": False, "constrained": False, "met": False,
            "wns_ns": None, "tns_ns": None, "whs_ns": None, "ths_ns": None,
            "clock_period_ns": None, "fmax_mhz": None,
        }
        report_dir = self._find_report_dir(workspace, bitstream_path)
        timing_path = report_dir / "timing.rpt" if report_dir else None
        if not timing_path or not timing_path.exists():
            return result
        content = timing_path.read_text(errors="replace")
        result["available"] = True
        lines = content.splitlines()

        for index, line in enumerate(lines):
            if "WNS(ns)" in line and "WHS(ns)" in line:
                for value_line in lines[index + 1:index + 4]:
                    tokens = value_line.split()
                    if not tokens or set(value_line.strip()) <= {"-", " "}:
                        continue
                    if len(tokens) >= 6:
                        result["wns_ns"] = self._to_float(tokens[0])
                        result["tns_ns"] = self._to_float(tokens[1])
                        result["whs_ns"] = self._to_float(tokens[4])
                        result["ths_ns"] = self._to_float(tokens[5])
                    break
                break

        # Erste Zeile der Clock Summary: "<name> {0.000 5.000} <period> <freq>"
        clock_match = re.search(
            r"^\s*(\S+)\s+\{[\d.\s]+\}\s+([\d.]+)\s+([\d.]+)\s*$",
            content,
            re.MULTILINE,
        )
        if clock_match:
            result["clock_period_ns"] = float(clock_match.group(2))

        no_constraints = "no user specified timing constraints" in content.lower()
        result["constrained"] = not no_constraints and result["wns_ns"] is not None
        result["met"] = bool(
            result["constrained"]
            and result["wns_ns"] >= 0
            and (result["whs_ns"] is None or result["whs_ns"] >= 0)
        )
        if result["clock_period_ns"] and result["wns_ns"] is not None:
            critical = result["clock_period_ns"] - result["wns_ns"]
            if critical > 0:
                result["fmax_mhz"] = round(1000.0 / critical, 2)
        return result

    _RESOURCE_ROWS = {
        "lut": ("slice luts", "clb luts"),
        "ff": ("slice registers", "clb registers"),
        "bram": ("block ram tile",),
        "dsp": ("dsps",),
    }

    def _parse_utilization_report(self, workspace: str, bitstream_path: str = "") -> dict:
        """Liest belegte Ressourcen und Auslastung aus report_utilization."""
        result: dict = {"available": False}
        for key in self._RESOURCE_ROWS:
            result[key] = None
            result[f"{key}_pct"] = None
        report_dir = self._find_report_dir(workspace, bitstream_path)
        util_path = report_dir / "utilization.rpt" if report_dir else None
        if not util_path or not util_path.exists():
            return result
        result["available"] = True
        for line in util_path.read_text(errors="replace").splitlines():
            if not line.strip().startswith("|"):
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 3:
                continue
            name = cells[0].rstrip("*").strip().lower()
            for key, names in self._RESOURCE_ROWS.items():
                if name in names and result[key] is None:
                    used = self._to_float(cells[1])
                    result[key] = int(used) if used is not None else None
                    result[f"{key}_pct"] = self._to_float(cells[-1])
        return result

    @staticmethod
    def evaluate_gates(timing: dict, resources: dict) -> list[dict]:
        """Harte Synthese-Gates. Leere Liste = alle Gates bestanden."""
        failures = []
        if not timing.get("available"):
            failures.append({
                "failure_type": "infrastructure",
                "message": "Timing report missing: timing closure could not be verified",
            })
        elif not timing.get("constrained"):
            failures.append({
                "failure_type": "constraint_error",
                "message": "There are no user specified timing constraints (missing clock constraint)",
            })
        elif not timing.get("met"):
            failures.append({
                "failure_type": "timing_error",
                "message": (
                    f"Timing violation: WNS={timing.get('wns_ns')} ns, "
                    f"WHS={timing.get('whs_ns')} ns"
                ),
            })
        if not resources.get("available"):
            failures.append({
                "failure_type": "infrastructure",
                "message": "Utilization report missing: resource usage could not be verified",
            })
        else:
            over = [
                f"{key.upper()} {resources[f'{key}_pct']}%"
                for key in ("lut", "ff", "bram", "dsp")
                if (resources.get(f"{key}_pct") or 0) > 100
            ]
            if over:
                failures.append({
                    "failure_type": "resource_error",
                    "message": "Resource limit exceeded: " + ", ".join(over),
                })
        return failures

    async def _analyze_timing(self, task: AgentTask) -> AgentResult:
        """Analysiert Timing-Ergebnisse aus Vivado Reports."""
        workspace = task.inputs.get("workspace", "")
        timing = self._parse_timing_report(workspace)
        return AgentResult(
            task_id=task.id,
            status=AgentStatus.COMPLETED,
            outputs=timing,
        )

    async def _check_resources(self, task: AgentTask) -> AgentResult:
        """Prüft FPGA-Ressourcen-Verbrauch."""
        workspace = task.inputs.get("workspace", "")
        util = self._parse_utilization_report(workspace)
        return AgentResult(
            task_id=task.id,
            status=AgentStatus.COMPLETED,
            outputs=util,
        )

def vivado_failure_cause(result) -> tuple[str, bool]:
    """Eigentliche Ursache eines Vivado-Fehlschlags und ob es ein Werkzeugproblem ist.

    Früher stand nur "bitstream generation failed" in der Meldung; die Ursache
    (z. B. "Vivado binary 'vivado' not found") lag ungelesen in den Details,
    und die Diagnose machte daraus einen Designfehler.
    """
    steps = (result.details or {}).get("steps", []) if isinstance(result.details, dict) else []
    text = "\n".join(f"{s.get('stdout', '')}\n{s.get('stderr', '')}" for s in steps)
    text += "\n" + str((result.details or {}).get("error", "") if isinstance(result.details, dict) else "")
    if re.search(r"binary '.*' not found|command not found|No such file or directory: '.*vivado", text, re.I):
        return "Vivado wurde nicht gefunden (vivado.binary in config.yaml prüfen)", True
    if re.search(r"timed out after", text, re.I):
        return "Vivado hat das Zeitlimit überschritten (vivado.timeout_seconds)", False
    errors = [line.strip() for line in text.splitlines() if line.strip().startswith(("ERROR:", "CRITICAL WARNING:"))]
    return "; ".join(dict.fromkeys(errors))[:1500], False
