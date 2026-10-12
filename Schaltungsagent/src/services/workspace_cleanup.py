"""Aufräumen nach erfolgreichem Lauf: Zwischenstände der Werkzeuge entfernen.

Bleiben: Bitstream (.bit/.mcs/.prm), Berichte (*.rpt), das letzte Build-Log
(build/bitstream/vivado_logs), das Build-Skript und synthesis_cache.json (ein
Cache-Treffer braucht nur den Bitstream). Entfernt werden GHDL-Arbeitsbibliotheken,
die Netzliste der GHDL-Synthese, archivierte Vivado-Logs und Vivado-Hilfsdateien.
Alles davon entsteht beim nächsten Lauf neu.
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

_DIRS = ("build/ghdl", "build/synthesis", "build/bitstream/vivado_logs_archive", ".Xil", "build/bitstream/.Xil")
_FILE_GLOBS = ("work-obj*.cf", "*.jou", "vivado*.log", "build/bitstream/*.jou", "build/bitstream/vivado*.log")


def cleanup_build_intermediates(workspace: str | Path) -> list[str]:
    """Löscht Zwischenstände im Workspace und gibt die entfernten Pfade (relativ) zurück."""
    root = Path(workspace)
    removed: list[str] = []
    for rel in _DIRS:
        path = root / rel
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path, ignore_errors=True)
            removed.append(rel + "/")
    for pattern in _FILE_GLOBS:
        for path in root.glob(pattern):
            if path.is_file():
                try:
                    path.unlink()
                    removed.append(str(path.relative_to(root)))
                except OSError as exc:
                    logger.warning("Konnte %s nicht löschen: %s", path, exc)
    return removed
