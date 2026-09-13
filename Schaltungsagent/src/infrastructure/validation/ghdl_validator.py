import dataclasses
import re
import subprocess
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from src.domain.ports.validation_service import ValidationService, ValidationResult
from src.domain_plugins.vhdl.test_definitions import VHDLTestDefinitions

logger = logging.getLogger(__name__)

# Marker, mit dem eine Testbench ihren erfolgreichen Abschluss meldet.
# Fehlt er in der Simulationsausgabe, wurde die Simulation vorzeitig
# (z. B. durch --stop-time) beendet und gilt NICHT als bestanden.
TB_COMPLETE_MARKER = "TB_COMPLETE"

# Ausdrücke, die auf fehlgeschlagene Assertions in der GHDL-Ausgabe hinweisen.
ASSERTION_FAILURE_PATTERNS = [
    re.compile(r"assertion error"),
    re.compile(r"assertion failure"),
    re.compile(r"assertion failed"),
]

VHDL_EXTENSIONS = (".vhd", ".vhdl")

# Marker, mit dem eine Testbench einen fehlgeschlagenen Testfall strukturiert
# meldet (Format: "FAIL CASE data=<n> bit=<b> code=<bin> ..."). Der Validator
# extrahiert daraus den failed_case fuer den Repair-Agenten.
FAIL_CASE_MARKER = "FAIL CASE"


class GHDLValidator(ValidationService):
    def __init__(
        self,
        ghdl_binary: str = "ghdl",
        test_definition=None,
        timeout_seconds: int = 60,
    ):
        self._ghdl_binary = ghdl_binary
        if test_definition is None:
            test_definition = VHDLTestDefinitions.get_test_definition()
        # Kopie mit dem konfigurierten Binary, damit das geteilte DEFAULT-
        # Objekt aus test_definitions.py nicht mutiert wird.
        self._test_def = dataclasses.replace(
            test_definition, simulator=self._ghdl_binary
        )
        self._timeout_seconds = timeout_seconds

    def validate(self, workspace: str, domain: str = "vhdl") -> ValidationResult:
        logger.info("GHDL validating workspace: %s", workspace)
        ws_path = Path(workspace)
        src_dir = ws_path / "src"
        tests_dir = ws_path / "tests"
        build_dir = ws_path / "build"
        build_dir.mkdir(parents=True, exist_ok=True)
        steps: list[dict] = []

        if not src_dir.exists():
            return self._fail(
                "No src directory found", steps,
                details={"workspace": str(ws_path)},
            )
        src_files = self._find_vhdl_files(src_dir)
        if not src_files:
            return self._fail("No VHDL files found in src/", steps)

        # Sort files by dependency order: entities referenced by others come first
        src_files = self._sort_by_dependency(src_files)

        tb_files = self._find_vhdl_files(tests_dir) if tests_dir.exists() else []

        # --- Schritt A: Analyse aller VHDL-Dateien (DUTs und Testbenches) ---
        for vhd_file in src_files + tb_files:
            step = self._run_step(
                "analyze",
                vhd_file.name,
                self._test_def.analyze_command(str(vhd_file)),
                build_dir,
            )
            steps.append(step)
            if step["returncode"] != 0:
                details = self._attach_artifacts(
                    {"file": str(vhd_file), "error": step["stderr"]},
                    src_dir, tests_dir,
                )
                return self._fail(
                    f"GHDL analysis failed for {vhd_file.name}",
                    steps,
                    details=details,
                )

        # --- Testbench und zugehörige Entity bestimmen ---
        tb_entities: list[tuple[Path, str]] = []
        for tb_file in tb_files:
            entity = self._extract_entity_name(tb_file)
            if entity:
                tb_entities.append((tb_file, entity))

        if not tb_entities:
            return self._fail(
                "No testbench found (expected testbench VHDL files under tests/ "
                "with an entity declaration)",
                steps,
                details=self._attach_artifacts({}, src_dir, tests_dir),
            )

        tb_content = tb_entities[0][0].read_text(errors="replace")
        # Nur Assertions mit severity error/failure sind echte Verifikation;
        # reine note-Meldungen (z. B. der TB_COMPLETE-Marker) zaehlen nicht.
        has_assertions = bool(
            re.search(r"\bassert\b", tb_content, re.IGNORECASE)
            and re.search(r"severity\s+(?:error|failure)", tb_content, re.IGNORECASE)
        )

        # --- Schritt B: Elaborierung der Testbench-Top-Level ---
        for tb_file, tb_entity in tb_entities:
            # Wähle passende Test-Definition basierend auf Testbench-Entity
            test_def = VHDLTestDefinitions.get_test_definition(
                "arty_running_light" if "led_running_light" in tb_entity else "default"
            )
            test_def = dataclasses.replace(test_def, simulator=self._ghdl_binary)
            
            step = self._run_step(
                "elaborate",
                tb_entity,
                test_def.elaborate_command(tb_entity),
                build_dir,
            )
            steps.append(step)
            if step["returncode"] != 0:
                details = self._attach_artifacts(
                    {"file": str(tb_file), "error": step["stderr"]},
                    src_dir, tests_dir,
                )
                return self._fail(
                    f"GHDL elaboration failed for {tb_entity}",
                    steps,
                    details=details,
                )

        # --- Schritt C: Simulation mit Assertions-Auswertung ---
        for tb_file, tb_entity in tb_entities:
            # Wähle passende Test-Definition für Simulation
            test_def = VHDLTestDefinitions.get_test_definition(
                "arty_running_light" if "led_running_light" in tb_entity else "default"
            )
            test_def = dataclasses.replace(test_def, simulator=self._ghdl_binary)
            simulate_cmd = self._ensure_assert_level(test_def.run_command)
            
            step = self._run_step(
                "simulate",
                tb_entity,
                simulate_cmd(tb_entity),
                build_dir,
            )
            steps.append(step)
            combined_output = (step["stdout"] or "") + "\n" + (step["stderr"] or "")

            failure_details = self._attach_artifacts(
                {
                    "file": str(tb_file),
                    "testbench": tb_entity,
                    "error": combined_output,
                },
                src_dir, tests_dir,
            )
            failed_case = self._parse_failed_case(combined_output, tb_entity)
            if failed_case:
                failure_details["failed_case"] = failed_case

            if step["returncode"] != 0:
                return self._fail(
                    f"GHDL simulation failed for {tb_entity} "
                    f"(runtime error or failed assertion)",
                    steps,
                    details=failure_details,
                )

            if ASSERTION_FAILURE_PATTERNS and any(
                pattern.search(combined_output)
                for pattern in ASSERTION_FAILURE_PATTERNS
            ):
                return self._fail(
                    f"Simulation of {tb_entity} reported a failed assertion",
                    steps,
                    details=failure_details,
                )

            if TB_COMPLETE_MARKER not in combined_output:
                return self._fail(
                    f"Simulation of {tb_entity} did not complete "
                    f"(completion marker '{TB_COMPLETE_MARKER}' missing "
                    f"- likely truncated by --stop-time)",
                    steps,
                    details=failure_details,
                )

        # --- Assertions-Pflicht: Exit-Code 0 allein ist kein gültiger PASS ---
        if not has_assertions:
            details = self._attach_artifacts(
                {"testbench": tb_entities[0][1]}, src_dir, tests_dir,
            )
            return self._fail(
                "Testbench contains no assertions; a GHDL exit code 0 alone "
                "does not prove correct behavior",
                steps,
                details=details,
            )

        return ValidationResult(
            passed=True,
            message="All VHDL files analyzed, elaborated and simulated "
                    "successfully with all assertions passing",
            details={
                "steps": steps,
                "files_checked": [str(f) for f in src_files],
                "testbench": tb_entities[0][1],
                "completion_marker": TB_COMPLETE_MARKER,
                "assertions_present": True,
            },
        )

    def validate_file(self, file_path: str, domain: str = "vhdl") -> ValidationResult:
        path = Path(file_path)
        if not path.exists():
            return ValidationResult(passed=False, message=f"File not found: {file_path}")
        try:
            result = subprocess.run(
                self._test_def.analyze_command(str(path)),
                capture_output=True, text=True, timeout=self._timeout_seconds,
            )
            if result.returncode != 0:
                return ValidationResult(
                    passed=False,
                    message="GHDL analysis failed",
                    details={"file": file_path, "error": result.stderr},
                )
            return ValidationResult(passed=True, message=f"File {path.name} passed analysis")
        except FileNotFoundError:
            return ValidationResult(
                passed=False,
                message=f"GHDL binary '{self._ghdl_binary}' not found",
            )
        except subprocess.TimeoutExpired:
            return ValidationResult(passed=False, message="GHDL analysis timed out")
        except Exception as e:
            return ValidationResult(passed=False, message=str(e))

    def _find_vhdl_files(self, directory: Path) -> list[Path]:
        if not directory.exists():
            return []
        return sorted(
            p for p in directory.iterdir()
            if p.is_file() and p.suffix.lower() in VHDL_EXTENSIONS
        )

    def _sort_by_dependency(self, files: list[Path]) -> list[Path]:
        """Sort VHDL files by dependency order.
        
        Files that are referenced by others (via entity instantiation)
        are placed first. This ensures GHDL analysis succeeds.
        """
        # Build entity -> file mapping
        entity_to_file: dict[str, Path] = {}
        file_entities: dict[Path, set[str]] = {}
        
        for f in files:
            try:
                content = f.read_text(errors="replace")
            except OSError:
                continue
            
            # Find entity name
            entity_match = re.search(r'\bentity\s+(\w+)\s+is', content, re.IGNORECASE)
            if entity_match:
                entity_to_file[entity_match.group(1).lower()] = f
                file_entities[f] = {entity_match.group(1).lower()}
            else:
                file_entities[f] = set()
            
            # Find instantiated entities (component or direct entity instantiation)
            instantiated = set()
            for m in re.finditer(r'\bentity\s+work\.(\w+)', content, re.IGNORECASE):
                instantiated.add(m.group(1).lower())
            for m in re.finditer(r'\bcomponent\s+(\w+)\s+is', content, re.IGNORECASE):
                instantiated.add(m.group(1).lower())
            
            if instantiated:
                file_entities[f] = file_entities.get(f, set()) | instantiated
        
        # Topological sort
        visited: set[Path] = set()
        result: list[Path] = []
        
        def visit(f: Path):
            if f in visited:
                return
            visited.add(f)
            # Visit dependencies first
            for dep_entity in file_entities.get(f, set()):
                dep_file = entity_to_file.get(dep_entity)
                if dep_file and dep_file != f:
                    visit(dep_file)
            result.append(f)
        
        for f in files:
            visit(f)
        
        return result

    @staticmethod
    def _extract_entity_name(vhd_file: Path) -> str | None:
        try:
            content = vhd_file.read_text(errors="replace")
        except OSError:
            return None
        match = re.search(r"\bentity\s+(\w+)\s+is", content, re.IGNORECASE)
        return match.group(1) if match else None

    def _parse_failed_case(self, output: str, testbench: str) -> dict:
        """Extrahiert den fehlgeschlagenen Testfall aus der Simulationsausgabe.

        Die Testbench-Templates melden Abweichungen als strukturierte Zeile:
          FAIL CASE data=<n> bit=<b> code=<bin>
                   DATA_OUT expected=<n> actual=<n>
                   ERROR_DETECT expected=<l> actual=<l>
                   ERROR_CORRECT expected=<l> actual=<l>
        bit=-1 bedeutet fehlerfreies Codewort (Clean Case).
        """
        if FAIL_CASE_MARKER not in output:
            return {}
        parsed: dict[str, Any] = {}
        m = re.search(r"data=(-?\d+)", output)
        if m:
            parsed["data"] = int(m.group(1))
        m = re.search(r"bit=(-?\d+)", output)
        if m:
            parsed["bit"] = int(m.group(1))
        m = re.search(r"code=([01]+)", output)
        if m:
            parsed["input_codeword"] = m.group(1)
        for pattern, key in (
            (r"DATA_OUT expected=(\d+) actual=(\d+)", "data_out"),
            (r"ERROR_DETECT expected=('[01]') actual=('[01]')", "error_detect"),
            (r"ERROR_CORRECT expected=('[01]') actual=('[01]')", "error_correct"),
        ):
            m = re.search(pattern, output)
            if m:
                parsed[f"expected_{key}"] = m.group(1)
                parsed[f"actual_{key}"] = m.group(2)
        if not parsed:
            return {}
        case: dict[str, Any] = {"testbench": testbench}
        if "bit" in parsed:
            case["test_case"] = (
                "Einzelbitfehler" if parsed["bit"] >= 0 else "Fehlerfreies Codewort"
            )
        case.update(parsed)
        return case

    def _attach_artifacts(
        self, details: dict, src_dir: Path, tests_dir: Path
    ) -> dict:
        """Hängt den erzeugten VHDL-Code und die Testbench an die Details an,
        damit der Repair-Agent den fehlerhaften Code direkt vorliegen hat."""
        for key, directory in (
            ("dut_content", src_dir),
            ("testbench_content", tests_dir),
        ):
            files = self._find_vhdl_files(directory)
            if not files:
                continue
            blocks = []
            for f in files:
                try:
                    blocks.append(f"--- {f.name} ---\n{f.read_text(errors='replace')}")
                except OSError:
                    continue
            if blocks:
                details[key] = "\n".join(blocks)
        return details

    def _ensure_assert_level(
        self, simulate_command: Callable[[str], list[str]]
    ) -> Callable[[str], list[str]]:
        """GHDL 4.x stops bei severity error nur, wenn --assert-level=error
        gesetzt ist; ohne das Flag endet die Simulation mit Exit-Code 0.
        Der Validator erzwingt daher das Flag, falls es fehlt."""
        if any(flag.startswith("--assert-level") for flag in self._test_def.run_flags):
            return simulate_command
        return lambda entity: simulate_command(entity) + ["--assert-level=error"]

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
    ) -> ValidationResult:
        result_details = {"steps": steps}
        if details:
            result_details.update(details)
        return ValidationResult(passed=False, message=message, details=result_details)
