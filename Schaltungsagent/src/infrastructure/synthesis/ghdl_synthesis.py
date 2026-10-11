import logging
import re
import shutil
import subprocess
from pathlib import Path

from src.domain.ports.synthesis_service import SynthesisResult, SynthesisService

logger = logging.getLogger(__name__)

VHDL_EXTENSIONS = (".vhd", ".vhdl")

# Basis-Flags für die VHDL-Synthese mit GHDL (vgl. CologneChip-GateMate-Quickstart:
# explizite IEEE-Auflösung und Synopsys-Konstrukte für bessere Synthesefähigkeit).
# --std=08: Planung, Worker und Simulation arbeiten mit VHDL-2008. Ohne den
# Schalter lehnte die Synthese z. B. process(all) ab, obwohl die Simulation
# bestanden hatte (Lauf traffic-light 2026-10-10).
SYNTH_FLAGS = ["--std=08", "-fexplicit", "-fsynopsys"]

# GHDL schreibt die Netlist (--out=verilog) auf stdout; Diagnose geht auf stderr.
NETLIST_EXTENSION = ".v"


class GHDLSynthesisService(SynthesisService):
    """Stufe-1-Synthese: prüft Synthesizierbarkeit mit `ghdl synth`.

    Erzeugt pro erfolgreicher Entity eine Verilog-Netlist unter
    <workspace>/build/synthesis/<entity>.v. Das ist die Grundlage für die
    späteren Vendor-Adapter (GateMate: yosys, Xilinx: Vivado).
    """

    def __init__(
        self,
        ghdl_binary: str = "ghdl",
        timeout_seconds: int = 120,
    ):
        self._ghdl_binary = ghdl_binary
        self._timeout_seconds = timeout_seconds

    def toolchain_available(self) -> bool:
        return shutil.which(self._ghdl_binary) is not None

    def synthesize(
        self, workspace: str, target: str = "", domain: str = "vhdl"
    ) -> SynthesisResult:
        logger.info("GHDL synthesizing workspace: %s (target: %s)", workspace, target)
        ws_path = Path(workspace)
        src_dir = ws_path / "src"
        steps: list[dict] = []

        if not src_dir.exists():
            return self._fail(
                "No src directory found", steps,
                details={"workspace": str(ws_path)},
            )
        src_files = self._find_vhdl_files(src_dir)
        if not src_files:
            return self._fail(
                "No VHDL files found in src/", steps,
                details=self._attach_artifacts({}, src_dir),
            )

        entities: list[tuple[Path, str]] = []
        for vhd_file in src_files:
            entity = self._extract_entity_name(vhd_file)
            if entity:
                entities.append((vhd_file, entity))
        if not entities:
            return self._fail(
                "No top-level entity found in src/", steps,
                details=self._attach_artifacts({}, src_dir),
            )

        build_dir = ws_path / "build" / "synthesis"
        build_dir.mkdir(parents=True, exist_ok=True)

        # --- Synthese pro Entity; die erste erfolgreiche Entity gewinnt ---
        for vhd_file, entity in entities:
            cmd = [
                self._ghdl_binary,
                "synth",
                *SYNTH_FLAGS,
                "--out=verilog",
                *(str(f) for f in src_files),
                "-e",
                entity,
            ]
            step = self._run_step("synthesize", entity, cmd, build_dir)
            steps.append(step)
            if step["returncode"] != 0:
                continue

            netlist = (step["stdout"] or "").strip()
            if not netlist:
                step["returncode"] = -1
                step["stderr"] = "GHDL synth produced no netlist output"
                return self._fail(
                    f"GHDL synthesis produced no netlist for {entity}",
                    steps,
                    details=self._attach_artifacts(
                        {"file": str(vhd_file)}, src_dir
                    ),
                )
            netlist_file = build_dir / f"{entity}{NETLIST_EXTENSION}"
            netlist_file.write_text(netlist, errors="replace")
            logger.info(
                "GHDL synthesis succeeded for %s (netlist: %s)",
                entity, netlist_file,
            )
            return SynthesisResult(
                passed=True,
                message=(
                    f"Synthesis succeeded for {entity} "
                    f"(netlist: {netlist_file.name})"
                ),
                target=target,
                details={
                    "steps": steps,
                    "entity": entity,
                    "netlist": str(netlist_file),
                    "artifact_dir": str(build_dir),
                    "files_checked": [str(f) for f in src_files],
                },
            )

        # --- Keine Entity synthetisierbar ---
        last_step = steps[-1] if steps else {}
        errors = list(dict.fromkeys(
            line.strip()
            for step in steps
            for line in (step.get("stderr") or "").splitlines()
            if ":error:" in line or "error:" in line.lower()
        ))
        return self._fail(
            "GHDL synthesis failed for all entities"
            + (": " + " | ".join(errors[:8]) if errors else ""),
            steps,
            details=self._attach_artifacts(
                {
                    "file": str(entities[-1][0]),
                    "error": last_step.get("stderr", ""),
                },
                src_dir,
            ),
        )

    def _find_vhdl_files(self, directory: Path) -> list[Path]:
        if not directory.exists():
            return []
        return sorted(
            p for p in directory.iterdir()
            if p.is_file() and p.suffix.lower() in VHDL_EXTENSIONS
        )

    @staticmethod
    def _extract_entity_name(vhd_file: Path) -> str | None:
        try:
            content = vhd_file.read_text(errors="replace")
        except OSError:
            return None
        match = re.search(r"\bentity\s+(\w+)\s+is", content, re.IGNORECASE)
        return match.group(1) if match else None

    def _attach_artifacts(self, details: dict, src_dir: Path) -> dict:
        """Hängt den erzeugten VHDL-Code an die Details an, damit der
        Repair-Agent den fehlerhaften Code direkt vorliegen hat."""
        files = self._find_vhdl_files(src_dir)
        if not files:
            return details
        blocks = []
        for f in files:
            try:
                blocks.append(f"--- {f.name} ---\n{f.read_text(errors='replace')}")
            except OSError:
                continue
        if blocks:
            details["dut_content"] = "\n".join(blocks)
        return details

    def _run_step(
        self, step_name: str, label: str, cmd: list[str], cwd: Path
    ) -> dict:
        logger.debug("GHDL %s (%s): %s", step_name, label, " ".join(cmd))
        try:
            result = subprocess.run(
                cmd,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=self._timeout_seconds,
            )
            return {
                "step": step_name,
                "label": label,
                "returncode": result.returncode,
                "stdout": result.stdout or "",
                "stderr": result.stderr or "",
            }
        except FileNotFoundError:
            return {
                "step": step_name,
                "label": label,
                "returncode": -1,
                "stdout": "",
                "stderr": f"GHDL binary '{self._ghdl_binary}' not found",
            }
        except subprocess.TimeoutExpired:
            return {
                "step": step_name,
                "label": label,
                "returncode": -1,
                "stdout": "",
                "stderr": f"GHDL {step_name} timed out after {self._timeout_seconds}s",
            }

    def _fail(
        self,
        message: str,
        steps: list[dict],
        details: dict | None = None,
    ) -> SynthesisResult:
        result_details = {"steps": steps}
        if details:
            result_details.update(details)
        return SynthesisResult(passed=False, message=message, details=result_details)