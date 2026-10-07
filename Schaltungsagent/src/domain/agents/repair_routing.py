"""Verbindliche Zuordnung von Fehlerklassen zu Reparaturzielen.

Der DebugAgent klassifiziert einen Fehler (``failure_type``); dieses Modul
entscheidet, welche Agentenrolle ihn beheben darf. So wird z. B. ein
Interfacefehler zwischen korrekt implementierten Modulen an die Architektur
zurückgegeben statt erneut als HDL-Patch an OpenCode.
"""
from enum import Enum


class RepairTarget(str, Enum):
    ARCHITECTURE = "architecture"   # ArchitectureAgent: Contracts/Module ändern
    HDL = "hdl"                     # HDLAgent: VHDL-Modul reparieren
    VERIFICATION = "verification"   # VerificationAgent: Testbench/Testplan
    FPGA = "fpga"                   # Synthese-/Timing-Reparatur (HDL mit Synthesekontext)
    HUMAN = "human"                 # Infrastruktur, Board, Ressourcen: Benutzer


_ROUTES: dict[str, RepairTarget] = {
    # Architektur-/Interfacefehler
    "architecture_error": RepairTarget.ARCHITECTURE,
    "interface_mismatch": RepairTarget.ARCHITECTURE,
    # Modul-/VHDL-Fehler
    "syntax_error": RepairTarget.HDL,
    "type_error": RepairTarget.HDL,
    "elaboration_error": RepairTarget.HDL,
    "clock_reset_error": RepairTarget.HDL,
    "functional_simulation_error": RepairTarget.HDL,
    "contract_violation": RepairTarget.HDL,
    "logic_error": RepairTarget.HDL,
    # Test-/Erwartungsfehler
    "testbench_error": RepairTarget.VERIFICATION,
    "coverage_gap": RepairTarget.VERIFICATION,
    # Synthese/Timing
    "synthesis_error": RepairTarget.FPGA,
    "timing_error": RepairTarget.FPGA,
    # Nicht durch Code-Agenten reparierbar
    "resource_error": RepairTarget.HUMAN,
    "constraint_error": RepairTarget.HUMAN,
    "bitstream_error": RepairTarget.HUMAN,
    "flash_error": RepairTarget.HUMAN,
    "hardware_error": RepairTarget.HUMAN,
    "infrastructure": RepairTarget.HUMAN,
    "target_ambiguous": RepairTarget.HUMAN,
}


def route_repair(failure_type: str, contracts_ok: bool | None = None) -> RepairTarget:
    """Bestimmt das Reparaturziel für eine Fehlerklasse.

    ``contracts_ok`` verfeinert Interfacefehler: Weicht ein Modul von seinem
    Architektur-Contract ab, ist die Implementierung schuld (HDL). Erfüllen
    alle Module ihre Contracts und passen trotzdem nicht zusammen, ist die
    Architektur inkonsistent.
    """
    target = _ROUTES.get(failure_type or "", RepairTarget.HDL)
    if target == RepairTarget.ARCHITECTURE and contracts_ok is False:
        return RepairTarget.HDL
    return target
