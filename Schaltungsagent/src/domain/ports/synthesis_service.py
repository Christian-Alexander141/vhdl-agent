from abc import ABC, abstractmethod


class SynthesisResult:
    """Ergebnis eines Synthese-Laufs (analog zum ValidationResult).

    Ein Projekt ist erst dann erfolgreich abgeschlossen, wenn sowohl die
    Validierung (Analyse/Elaboration/Simulation) als auch die Synthese
    bestanden sind. Bei FAIL enthält details die fehlgeschlagenen Schritte
    samt Tool-Ausgabe und den erzeugten VHDL-Code für den Repair-Agenten.
    """

    def __init__(
        self,
        passed: bool,
        message: str = "",
        target: str = "",
        details: dict | None = None,
    ):
        self.passed = passed
        self.message = message
        self.target = target
        self.details = details or {}

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "message": self.message,
            "target": self.target,
            "details": self.details,
        }

    def build_repair_instruction(
        self,
        original_request: str = "",
        iteration: int = 0,
    ) -> str:
        """Erzeugt einen detaillierten Reparatur-Auftrag für den OpenCode-Agenten.

        Enthält den ursprünglichen Auftrag, die fehlgeschlagenen Synthese-
        Schritte mit Tool-Ausgabe, den erzeugten VHDL-Code sowie Schutzregeln,
        damit die bereits bestandene Verifikation nicht durch die Reparatur
        zerstört wird.
        """
        details = self.details or {}
        steps = details.get("steps", [])
        affected_file = details.get("file", "")
        dut_content = details.get("dut_content", "")

        lines = [
            "Repariere die VHDL-Komponente. Die Synthese ist fehlgeschlagen.",
            "",
            f"Ursprüngliche Anforderung: {original_request}",
            f"Reparatur-Iteration: {iteration}",
            "",
            f"Syntheseergebnis: {'PASS' if self.passed else 'FAIL'}",
        ]
        if self.target:
            lines.append(f"Ziel-FPGA: {self.target}")
        lines.append(f"Meldung: {self.message}")
        if affected_file:
            lines.append(f"Betroffene Datei: {affected_file}")
        for step in steps:
            lines.append("")
            step_name = step.get("step", "?")
            step_file = step.get("label", "")
            lines.append(f"[{step_name.upper()}] {step_file}")
            lines.append(f"  Returncode: {step.get('returncode', '')}")
            out = (step.get("stdout") or "").strip()
            err = (step.get("stderr") or "").strip()
            if out:
                lines.append(f"  Synthese-Ausgabe: {out[:2000]}")
            if err:
                lines.append(f"  Synthese-Fehler: {err[:2000]}")
        if dut_content:
            lines.append("")
            lines.append("Erzeugter VHDL-Code (DUT):")
            lines.append(dut_content[:10000])
        lines.append("")
        lines.append("Regeln für die Reparatur:")
        lines.append(
            "- Ändere nur den notwendigen VHDL-Code des DUT bzw. die notwendigen Artefakte."
        )
        lines.append(
            "- Verändere die Schnittstelle (Ports, Datenbreiten, Namen) NICHT, "
            "wenn die Testbench davon abhängt - die bestandene Verifikation "
            "muss weiterhin bestehen."
        )
        lines.append(
            "- Der Code muss sowohl simulations- als auch synthesetauglich "
            "bleiben: keine wait- oder after-Anweisungen, keine dynamischen "
            "Allokationen, keine ungebundenen Loops im Kombinatorik-Pfad."
        )
        lines.append(
            "- Erst wenn Analyse, Elaboration, Simulation UND Synthese "
            "erfolgreich sind, ist das Projekt abgeschlossen."
        )
        return "\n".join(lines)


class SynthesisService(ABC):
    """Port für die FPGA-Synthese (analog zum ValidationService).

    Adapter: GHDLSynthesisService (Stufe 1, universell), später
    GateMateSynthesisService und VivadoSynthesisService (Stufe 2).
    """

    @abstractmethod
    def synthesize(
        self, workspace: str, target: str = "", domain: str = "vhdl", top_entity: str = ""
    ) -> SynthesisResult:
        ...

    @abstractmethod
    def toolchain_available(self) -> bool:
        ...