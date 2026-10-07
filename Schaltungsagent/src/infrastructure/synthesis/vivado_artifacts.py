"""Utility for cleaning up Vivado artifacts.

Vivado creates several side-effect files in its working directory:
- vivado.jou (journal)
- vivado.log
- vivado_<PID>.backup.jou / .backup.log
- .Xil/ (temp directory)
- clockInfo.txt

This module provides functions to move these files to a dedicated
vivado_logs/ directory and archive old logs.
"""

import glob
import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

# Patterns for Vivado side-effect files
_VIVADO_ARTIFACT_PATTERNS = [
    "vivado.jou",
    "vivado.log",
    "vivado_*.backup.jou",
    "vivado_*.backup.log",
    "clockInfo.txt",
    ".Xil",
]

# Patterns for GHDL side-effect files
_GHDL_ARTIFACT_PATTERNS = [
    "work-obj*.cf",
]


def collect_vivado_artifacts(directory: Path) -> list[Path]:
    """Sammelt alle Vivado-Artefakte aus einem Verzeichnis."""
    found = []
    for pattern in _VIVADO_ARTIFACT_PATTERNS:
        if "*" in pattern:
            found.extend(directory.glob(pattern))
        else:
            p = directory / pattern
            if p.exists():
                found.append(p)
    return found


def collect_ghdl_artifacts(directory: Path) -> list[Path]:
    """Sammelt alle GHDL-Artefakte aus einem Verzeichnis."""
    found = []
    for pattern in _GHDL_ARTIFACT_PATTERNS:
        found.extend(directory.glob(pattern))
    return found


def move_artifacts_to_logs(
    source_dir: Path,
    log_dir: Path,
    prefix: str = "",
) -> list[Path]:
    """Verschiebt Vivado- und GHDL-Artefakte nach log_dir.

    Args:
        source_dir: Quellverzeichnis (z.B. Repo-Root oder build/)
        log_dir: Zielverzeichnis (z.B. vivado_logs/)
        prefix: Optionaler Prefix für die Dateinamen (z.B. Entity-Name)

    Returns:
        Liste der verschobenen Dateien.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    moved = []

    artifacts = collect_vivado_artifacts(source_dir) + collect_ghdl_artifacts(source_dir)

    for artifact in artifacts:
        if not artifact.exists():
            continue

        # Zielname mit optionalem Prefix
        if prefix and not artifact.name.startswith(prefix):
            target_name = f"{prefix}_{artifact.name}"
        else:
            target_name = artifact.name

        target = log_dir / target_name

        # Bei Verzeichnissen (.Xil) -> verschieben
        if artifact.is_dir():
            try:
                if target.exists():
                    shutil.rmtree(target)
                shutil.move(str(artifact), str(target))
                logger.info("Moved directory %s -> %s", artifact, target)
                moved.append(target)
            except OSError as e:
                logger.warning("Failed to move directory %s: %s", artifact, e)
        else:
            # Bei Dateien -> verschieben (überschreiben falls nötig)
            try:
                if target.exists():
                    target.unlink()
                shutil.move(str(artifact), str(target))
                logger.info("Moved file %s -> %s", artifact, target)
                moved.append(target)
            except OSError as e:
                logger.warning("Failed to move file %s: %s", artifact, e)

    return moved


def archive_logs(log_dir: Path, archive_dir: Path) -> int:
    """Archiviert alte vivado_logs nach vivado_logs_archive.

    Verschiebt den gesamten Inhalt von log_dir nach archive_dir
    (mit Zeitstempel-Unterverzeichnis).

    Returns:
        Anzahl der archivierten Dateien/Verzeichnisse.
    """
    if not log_dir.exists():
        return 0

    # Prüfen ob es etwas zu archivieren gibt
    contents = list(log_dir.iterdir())
    if not contents:
        return 0

    archive_dir.mkdir(parents=True, exist_ok=True)

    # Zeitstempel für Unterverzeichnis
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_dir = archive_dir / timestamp
    session_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for item in contents:
        target = session_dir / item.name
        try:
            shutil.move(str(item), str(target))
            count += 1
        except OSError as e:
            logger.warning("Failed to archive %s: %s", item, e)

    if count:
        logger.info("Archived %d items from %s to %s", count, log_dir, session_dir)

    return count


def cleanup_repo_root(repo_root: Path, log_dir: Path) -> list[Path]:
    """Räumt Vivado-Artefakte aus dem Repo-Root auf.

    Verschiebt alle Vivado-Seiteneffekt-Dateien aus repo_root nach log_dir.
    """
    return move_artifacts_to_logs(repo_root, log_dir, prefix="vivado")


def cleanup_workspace_artifacts(workspace: Path) -> int:
    """Löscht temporäre GHDL- und Vivado-Artefakte aus einem Workspace.

    Entfernt work-obj*.cf aus build/, src/ und Projekt-Root.
    Verschiebt Vivado-Logs nach build/vivado_logs/.

    Returns:
        Anzahl der entfernten Dateien.
    """
    removed = 0

    # GHDL-Artefakte aus build/ löschen (nicht verschieben, da Build-Verzeichnis)
    build_dir = workspace / "build"
    if build_dir.exists():
        for cf in collect_ghdl_artifacts(build_dir):
            try:
                cf.unlink()
                logger.debug("Removed GHDL artifact: %s", cf)
                removed += 1
            except OSError as e:
                logger.warning("Failed to remove %s: %s", cf, e)

    # GHDL-Artefakte aus src/ löschen (leaked)
    src_dir = workspace / "src"
    if src_dir.exists():
        for cf in collect_ghdl_artifacts(src_dir):
            try:
                cf.unlink()
                logger.debug("Removed leaked GHDL artifact from src/: %s", cf)
                removed += 1
            except OSError as e:
                logger.warning("Failed to remove %s: %s", cf, e)

    # GHDL-Artefakte aus Projekt-Root (leaked)
    for cf in collect_ghdl_artifacts(workspace):
        try:
            cf.unlink()
            logger.debug("Removed leaked GHDL artifact from workspace root: %s", cf)
            removed += 1
        except OSError as e:
            logger.warning("Failed to remove %s: %s", cf, e)

    # Vivado-Artefakte aus Projekt-Root in build/vivado_logs verschieben
    vivado_artifacts = collect_vivado_artifacts(workspace)
    if vivado_artifacts:
        log_dir = build_dir / "vivado_logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        for artifact in vivado_artifacts:
            target = log_dir / artifact.name
            try:
                if artifact.is_dir():
                    if target.exists():
                        shutil.rmtree(target)
                    shutil.move(str(artifact), str(target))
                else:
                    if target.exists():
                        target.unlink()
                    shutil.move(str(artifact), str(target))
                logger.debug("Moved Vivado artifact to %s: %s", log_dir, artifact)
                removed += 1
            except OSError as e:
                logger.warning("Failed to move %s: %s", artifact, e)

    return removed


def cleanup_repo_root_comprehensive(repo_root: Path) -> int:
    """Räumt alle temporären Artefakte aus dem Repo-Root auf.

    Löscht work-obj*.cf und verschiebt Vivado-Artefakte.
    Wird nach Workflow-Ende aufgerufen.

    Returns:
        Anzahl der entfernten/verschobenen Dateien.
    """
    removed = 0

    # GHDL-Artefakte aus Repo-Root löschen
    for cf in collect_ghdl_artifacts(repo_root):
        try:
            cf.unlink()
            logger.debug("Removed GHDL artifact from repo root: %s", cf)
            removed += 1
        except OSError as e:
            logger.warning("Failed to remove %s: %s", cf, e)

    # GHDL-Artefakte aus Schaltungsagent-Verzeichnis (leaked)
    sa_dir = repo_root / "Schaltungsagent"
    if sa_dir.exists():
        for cf in collect_ghdl_artifacts(sa_dir):
            try:
                cf.unlink()
                logger.debug("Removed GHDL artifact from Schaltungsagent/: %s", cf)
                removed += 1
            except OSError as e:
                logger.warning("Failed to remove %s: %s", cf, e)

    # Vivado-Artefakte aus Repo-Root verschieben
    vivado_artifacts = collect_vivado_artifacts(repo_root)
    if vivado_artifacts:
        log_dir = repo_root / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        for artifact in vivado_artifacts:
            target = log_dir / artifact.name
            try:
                if artifact.is_dir():
                    if target.exists():
                        shutil.rmtree(target)
                    shutil.move(str(artifact), str(target))
                else:
                    if target.exists():
                        target.unlink()
                    shutil.move(str(artifact), str(target))
                logger.debug("Moved Vivado artifact from repo root: %s", artifact)
                removed += 1
            except OSError as e:
                logger.warning("Failed to move %s: %s", artifact, e)

    # GHDL-Artefakte aus allen Projekt-Roots (leaked)
    projects_dir = repo_root / "projects"
    if projects_dir.exists():
        for project_dir in projects_dir.iterdir():
            if not project_dir.is_dir() or project_dir.name.startswith("_"):
                continue
            for cf in collect_ghdl_artifacts(project_dir):
                try:
                    cf.unlink()
                    logger.debug("Removed leaked GHDL artifact from project: %s", cf)
                    removed += 1
                except OSError as e:
                    logger.warning("Failed to remove %s: %s", cf, e)

    return removed
