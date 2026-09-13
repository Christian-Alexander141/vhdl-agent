#!/usr/bin/env python3
"""Test: Build & Flash des 4-Bit-Komparator auf Arty S7-50.

Dieses Skript nutzt die VivadoBitstreamService- und VivadoFlashService-Klassen
aus dem Schaltungsagenten, um:
1. Den Bitstream zu erzeugen
2. Vivado-Artefakte sauber aufzuräumen
3. Den Bitstream auf das Board zu flashen

Voraussetzung:
- Vivado muss via setup_vivado_env.sh geladen sein
- Board muss per JTAG angeschlossen sein
"""

import sys
import logging
from pathlib import Path

# Pfad zum Schaltungsagenten hinzufügen
AGENT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AGENT_ROOT / "Schaltungsagent"))

from src.config import load_config, load_fpga_registry
from src.infrastructure.synthesis.vivado_synthesis import VivadoBitstreamService
from src.infrastructure.synthesis.vivado_flash import VivadoFlashService

# Logging aktivieren
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("test_flash")

# Pfade
PROJECT_DIR = AGENT_ROOT / "projects" / "vierbit-komparator-64061a"
WORKSPACE = str(PROJECT_DIR)


def main():
    print("=" * 60)
    print("  Test: 4-Bit-Komparator Build & Flash")
    print("=" * 60)

    # Config laden
    settings = load_config()
    fpga_registry = load_fpga_registry()

    print(f"\nProjekt:   {PROJECT_DIR}")
    print(f"FPGA:      arty_s7_50")
    print(f"Part:      {fpga_registry['arty_s7_50'].part}")

    # ---- SCHRITT 1: Bitstream erzeugen ----
    print("\n--- Schritt 1: Bitstream erzeugen ---")
    bitstream_service = VivadoBitstreamService(
        vivado_binary=settings.vivado.binary,
        settings_script=settings.vivado.settings_script,
        timeout_seconds=settings.vivado.timeout_seconds,
        fpga_registry=fpga_registry,
    )

    if not bitstream_service.toolchain_available():
        print("ERROR: Vivado nicht verfügbar!")
        sys.exit(1)

    result = bitstream_service.build_bitstream(
        workspace=WORKSPACE,
        target="arty_s7_50",
        domain="vhdl",
    )

    if not result.passed:
        print(f"FAILED: {result.message}")
        sys.exit(1)

    print(f"OK: {result.message}")
    print(f"Bitstream: {result.bitstream_path}")

    # Prüfen ob Artefakte in vivado_logs landen
    vivado_logs = Path(PROJECT_DIR) / "build" / "bitstream" / "vivado_logs"
    if vivado_logs.exists():
        log_files = list(vivado_logs.iterdir())
        print(f"vivado_logs/ ({len(log_files)} Dateien): {[f.name for f in log_files]}")

    # Prüfen ob Repo-Root sauber ist
    repo_root_files = list(AGENT_ROOT.glob("vivado*.jou")) + \
                      list(AGENT_ROOT.glob("vivado*.log")) + \
                      list(AGENT_ROOT.glob("vivado*.backup.*")) + \
                      list(AGENT_ROOT.glob("clockInfo.txt"))
    if repo_root_files:
        print(f"WARN: Artefakte im Repo-Root: {[f.name for f in repo_root_files]}")
    else:
        print("OK: Repo-Root ist sauber (keine Vivado-Artefakte)")

    # ---- SCHRITT 2: Board flashen ----
    print("\n--- Schritt 2: Board flashen ---")
    flash_service = VivadoFlashService(
        vivado_binary=settings.vivado.binary,
        settings_script=settings.vivado.settings_script,
        timeout_seconds=settings.flash.timeout_seconds,
    )

    if not flash_service.toolchain_available():
        print("ERROR: Vivado Flash-Toolchain nicht verfügbar!")
        sys.exit(1)

    # Board erkennen
    boards = flash_service.detect_boards("xc7s50")
    if not boards:
        print("ERROR: Kein Arty S7-50 Board erkannt!")
        print("Prüfe JTAG-Verbindung und ob Board eingeschaltet ist.")
        sys.exit(1)

    print(f"Board erkannt: {boards[0]['part']} ({boards[0]['device']})")

    # Flashen
    flash_result = flash_service.flash(
        bitstream_path=result.bitstream_path,
        board="arty_s7",
        expected_part="xc7s50csga324-1",
        workspace=WORKSPACE,
    )

    if not flash_result.passed:
        print(f"FAILED: {flash_result.message}")
        sys.exit(1)

    print(f"OK: {flash_result.message}")

    # Prüfen ob Flash-Logs sauber abgelegt wurden
    flash_logs = list((Path(WORKSPACE) / "build" / "bitstream" / "vivado_logs").glob("flash.*"))
    if flash_logs:
        print(f"Flash-Logs: {[f.name for f in flash_logs]}")

    # ---- ERGEBNIS ----
    print("\n" + "=" * 60)
    print("  ERFOLGREICH: Build & Flash abgeschlossen!")
    print("=" * 60)
    print("\nDie RGB-LEDs sollten jetzt:")
    print(f"  - BLAU leuchten wenn BUTTONS == SWITCHES")
    print(f"  - ROT leuchten wenn BUTTONS != SWITCHES")


if __name__ == "__main__":
    main()
