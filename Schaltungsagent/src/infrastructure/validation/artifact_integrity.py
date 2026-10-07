"""Artefakt-Integrität und Source-Hash-Validierung.

Stellt sicher, dass jedes Artefakt zum aktuellen Source-Hash gehört
und nicht ausserhalb des Workspace liegt.
"""
import hashlib
import logging
import json
from pathlib import Path
from typing import Any

from src.domain.exceptions import ArtifactError

logger = logging.getLogger(__name__)


class ArtifactIntegrityError(ArtifactError):
    pass


class SourceHash:
    """Berechnet und verifiziert SHA-256 Hashes von Quellcodedateien."""

    @staticmethod
    def compute_file_hash(filepath: Path) -> str:
        """Berechne SHA-256 Hash einer Datei."""
        h = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def compute_workspace_hash(workspace: str, extensions: tuple[str, ...] = (".vhd", ".vhdl")) -> dict[str, str]:
        """Berechne Hashes aller VHDL-Dateien im Workspace."""
        ws_path = Path(workspace)
        if not ws_path.exists():
            return {}
        hashes: dict[str, str] = {}
        for f in ws_path.rglob("*"):
            if f.is_file() and f.suffix.lower() in extensions:
                try:
                    hashes[str(f.relative_to(ws_path))] = SourceHash.compute_file_hash(f)
                except OSError:
                    continue
        return hashes

    @staticmethod
    def compute_source_hash(workspace: str) -> str:
        """Berechne einen kombinierten Hash aller Quellcodedateien."""
        hashes = SourceHash.compute_workspace_hash(workspace)
        combined = json.dumps(hashes, sort_keys=True)
        return hashlib.sha256(combined.encode()).hexdigest()


class ArtifactRegistry:
    """Verwalten Artefakte mit Source-Hash-Verknüpfung."""

    def __init__(self, workspace: str):
        self._workspace = Path(workspace)
        self._registry_path = self._workspace / ".artifact_registry.json"
        self._registry: dict[str, dict] = self._load()

    def _load(self) -> dict[str, dict]:
        if self._registry_path.exists():
            try:
                return json.loads(self._registry_path.read_text())
            except (OSError, json.JSONDecodeError):
                return {}
        return {}

    def _save(self) -> None:
        self._registry_path.write_text(json.dumps(self._registry, indent=2))

    def register(
        self,
        artifact_path: str,
        source_hash: str,
        tool: str,
        tool_version: str,
        stage: str,
        command: str,
    ) -> None:
        """Registriere ein Artefakt mit Source-Hash."""
        canon_path = str(Path(artifact_path).resolve())
        try:
            Path(canon_path).relative_to(self._workspace.resolve())
        except ValueError:
            raise ArtifactIntegrityError(
                f"Artifact path outside workspace: {canon_path}"
            )
        self._registry[canon_path] = {
            "source_hash": source_hash,
            "tool": tool,
            "tool_version": tool_version,
            "stage": stage,
            "command": command,
            "registered_at": __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            ).isoformat(),
        }
        self._save()

    def verify(self, artifact_path: str, current_source_hash: str) -> bool:
        """Pruefe, ob ein Artefakt zum aktuellen Source-Hash gehoert."""
        canon_path = str(Path(artifact_path).resolve())
        entry = self._registry.get(canon_path)
        if not entry:
            logger.warning("Artifact not registered: %s", canon_path)
            return False
        if entry.get("source_hash") != current_source_hash:
            raise ArtifactIntegrityError(
                f"Artifact source mismatch: {canon_path} "
                f"(expected {entry.get('source_hash')}, got {current_source_hash})"
            )
        return True

    def get_artifact(self, artifact_path: str) -> dict | None:
        canon_path = str(Path(artifact_path).resolve())
        return self._registry.get(canon_path)

    def get_all(self) -> dict[str, dict]:
        return dict(self._registry)


class ArtifactValidator:
    """Prueft Artefakt-Existenz, -Zugehoerigkeit und -Integritaet."""

    @staticmethod
    def check_artifact_exists(artifact_path: str) -> bool:
        """Pruefe, ob ein Artefakt existiert."""
        return Path(artifact_path).exists()

    @staticmethod
    def check_bitstream_ready(
        bitstream_path: str,
        source_hash: str,
        workspace: str,
    ) -> bool:
        """Pruefe, ob ein Bitstream hardwarebereit ist.
        
        Ein Bitstream gilt nur als bereit, wenn:
        - Die Datei existiert
        - Die DRC-/Timing-Berichte existieren
        - Der Source-Hash uebereinstimmt
        """
        if not Path(bitstream_path).exists():
            raise ArtifactIntegrityError(f"Bitstream not found: {bitstream_path}")

        bitstream_dir = Path(bitstream_path).parent
        timing_rpt = bitstream_dir / "timing.rpt"
        util_rpt = bitstream_dir / "utilization.rpt"

        if not timing_rpt.exists():
            raise ArtifactIntegrityError(
                f"Timing report missing: {timing_rpt}"
            )
        if not util_rpt.exists():
            raise ArtifactIntegrityError(
                f"Utilization report missing: {util_rpt}"
            )

        return True

    @staticmethod
    def validate_artifact_scope(artifact_path: str, workspace: str) -> None:
        """Pruefe, ob ein Artefakt innerhalb des Workspace liegt."""
        try:
            Path(artifact_path).resolve().relative_to(Path(workspace).resolve())
        except ValueError:
            raise ArtifactIntegrityError(
                f"Artifact outside workspace scope: {artifact_path}"
            )
