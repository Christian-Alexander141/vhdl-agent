from abc import ABC, abstractmethod
from typing import Any

# Beschriftungen für die strukturierten Felder des fehlgeschlagenen Testfalls
# (failed_case), wie ihn der GHDLValidator aus der Simulationsausgabe extrahiert.
FAILED_CASE_LABELS: dict[str, str] = {
    "testbench": "Testbench",
    "test_case": "Testfall",
    "data": "Datenwort",
    "bit": "Verfälschtes Bit",
    "input_codeword": "Eingabecodewort",
    "expected_data_out": "Erwarteter DATA_OUT",
    "actual_data_out": "Tatsächlicher DATA_OUT",
    "expected_error_detect": "Erwarteter ERROR_DETECT",
    "actual_error_detect": "Tatsächlicher ERROR_DETECT",
    "expected_error_correct": "Erwarteter ERROR_CORRECT",
    "actual_error_correct": "Tatsächlicher ERROR_CORRECT",
}


class ValidationResult:
    def __init__(self, passed: bool, message: str = "", details: dict | None = None):
        self.passed = passed
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "message": self.message,
            "details": self.details,
        }

    def build_repair_instruction(
        self,
        original_request: str = "",
        iteration: int = 0,
    ) -> str:
        """Erzeugt einen detaillierten Reparatur-Auftrag fuer den OpenCode-Agenten.

        Enthaelt den ursprünglichen Auftrag, die fehlgeschlagenen Validierungs-
        schritte mit GHDL-Ausgabe sowie Schutzregeln gegen Testbench-Manipulation.
        """
        details = self.details or {}
        steps = details.get("steps", [])
        testbench = details.get("testbench", "")
        failed_case = details.get("failed_case", {})
        affected_file = details.get("file", "")
        dut_content = details.get("dut_content", "")
        testbench_content = details.get("testbench_content", "")

        lines = [
            "Repariere die VHDL-Komponente. Die Validierung ist fehlgeschlagen.",
            "",
            f"Ursprüngliche Anforderung: {original_request}",
            f"Reparatur-Iteration: {iteration}",
            "",
            f"Validierungsergebnis: {'PASS' if self.passed else 'FAIL'}",
            f"Meldung: {self.message}",
        ]
        if testbench:
            lines.append(f"Testbench: {testbench}")
        if affected_file:
            lines.append(f"Betroffene Datei: {affected_file}")
        if failed_case:
            lines.append("")
            lines.append("Fehlgeschlagener Testfall:")
            for key, value in failed_case.items():
                lines.append(f"  {FAILED_CASE_LABELS.get(key, key)}: {value}")
        for step in steps:
            lines.append("")
            step_name = step.get("step", "?")
            step_file = step.get("label", "")
            lines.append(f"[{step_name.upper()}] {step_file}")
            lines.append(f"  Returncode: {step.get('returncode', '')}")
            out = (step.get("stdout") or "").strip()
            err = (step.get("stderr") or "").strip()
            if out:
                lines.append(f"  GHDL-Ausgabe: {out[:2000]}")
            if err:
                lines.append(f"  GHDL-Fehler: {err[:2000]}")
        if dut_content:
            lines.append("")
            lines.append("Erzeugter VHDL-Code (DUT):")
            lines.append(dut_content[:10000])
        if testbench_content:
            lines.append("")
            lines.append("Erzeugte Testbench:")
            lines.append(testbench_content[:10000])
        lines.append("")
        lines.append("Regeln für die Reparatur:")
        lines.append(
            "- Ändere nur den notwendigen VHDL-Code des DUT bzw. die notwendigen Artefakte."
        )
        lines.append(
            "- Verändere die Testbench NICHT so, dass ein eigentlich fehlerhafter "
            "DUT den Test besteht."
        )
        lines.append(
            "- Erwartungswerte stammen aus der Spezifikation bzw. einer unabhängigen "
            "Referenz - niemals aus dem DUT-Ergebnis."
        )
        lines.append(
            "- Erst wenn Analyse, Elaboration UND Simulation mit allen Assertions "
            "bestehen, ist das Projekt erfolgreich validiert."
        )
        return "\n".join(lines)


class ValidationService(ABC):
    @abstractmethod
    def validate(self, workspace: str, domain: str = "vhdl") -> ValidationResult:
        ...

    @abstractmethod
    def validate_file(self, file_path: str, domain: str = "vhdl") -> ValidationResult:
        ...
