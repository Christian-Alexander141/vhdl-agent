"""Tests für Artefakt-Integrität und Source-Hash-Validierung."""
import sys
import os
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from pathlib import Path
from src.infrastructure.validation.artifact_integrity import (
    SourceHash,
    ArtifactRegistry,
    ArtifactValidator,
    ArtifactIntegrityError,
)


class TestSourceHash:
    """Testet Source-Hash-Berechnung."""

    def test_compute_file_hash(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "test.vhd"
            f.write_text("entity test is end entity;")
            h1 = SourceHash.compute_file_hash(f)
            h2 = SourceHash.compute_file_hash(f)
            assert h1 == h2
            assert len(h1) == 64  # SHA-256

    def test_different_content_different_hash(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            f1 = Path(tmpdir) / "a.vhd"
            f2 = Path(tmpdir) / "b.vhd"
            f1.write_text("entity a is end entity;")
            f2.write_text("entity b is end entity;")
            assert SourceHash.compute_file_hash(f1) != SourceHash.compute_file_hash(f2)

    def test_compute_workspace_hash(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "src"
            src.mkdir()
            (src / "top.vhd").write_text("entity top is end entity;")
            (src / "module.vhd").write_text("entity mod is end entity;")
            hashes = SourceHash.compute_workspace_hash(tmpdir)
            assert len(hashes) == 2
            assert all(len(h) == 64 for h in hashes.values())

    def test_compute_source_hash(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "src"
            src.mkdir()
            (src / "top.vhd").write_text("entity top is end entity;")
            h1 = SourceHash.compute_source_hash(tmpdir)
            assert len(h1) == 64

    def test_empty_workspace_hash(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            hashes = SourceHash.compute_workspace_hash(tmpdir)
            assert hashes == {}


class TestArtifactRegistry:
    """Testet die Artefakt-Registrierung."""

    def test_register_and_verify(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = ArtifactRegistry(tmpdir)
            test_file = Path(tmpdir) / "test.bit"
            test_file.write_bytes(b"bitstream data")
            source_hash = SourceHash.compute_source_hash(tmpdir)
            registry.register(
                str(test_file), source_hash, "vivado", "2024.1", "synthesis", "synth_design"
            )
            assert registry.verify(str(test_file), source_hash) is True

    def test_verify_wrong_hash_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = ArtifactRegistry(tmpdir)
            test_file = Path(tmpdir) / "test.bit"
            test_file.write_bytes(b"bitstream data")
            registry.register(
                str(test_file), "abc123", "vivado", "2024.1", "synthesis", "synth_design"
            )
            with pytest.raises(ArtifactIntegrityError):
                registry.verify(str(test_file), "wrong_hash")

    def test_verify_unregistered_artifact(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = ArtifactRegistry(tmpdir)
            test_file = Path(tmpdir) / "test.bit"
            test_file.write_bytes(b"bitstream data")
            result = registry.verify(str(test_file), "any_hash")
            assert result is False

    def test_outside_workspace_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = ArtifactRegistry(tmpdir)
            with pytest.raises(ArtifactIntegrityError):
                registry.register("/etc/passwd", "hash", "vivado", "2024.1", "synthesis", "cmd")

    def test_persistence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = ArtifactRegistry(tmpdir)
            test_file = Path(tmpdir) / "test.bit"
            test_file.write_bytes(b"data")
            source_hash = SourceHash.compute_source_hash(tmpdir)
            registry.register(str(test_file), source_hash, "vivado", "2024.1", "synthesis", "cmd")
            # Reload from disk
            registry2 = ArtifactRegistry(tmpdir)
            assert len(registry2.get_all()) == 1


class TestArtifactValidator:
    """Testet Artefakt-Validierung."""

    def test_check_artifact_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "test.bit"
            f.write_bytes(b"data")
            assert ArtifactValidator.check_artifact_exists(str(f)) is True
            assert ArtifactValidator.check_artifact_exists(str(Path(tmpdir) / "missing")) is False

    def test_validate_artifact_scope_inside(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "test.bit"
            f.write_bytes(b"data")
            ArtifactValidator.validate_artifact_scope(str(f), tmpdir)

    def test_validate_artifact_scope_outside_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "test.bit"
            f.write_bytes(b"data")
            # This should raise because /etc/passwd is outside the workspace
            with pytest.raises(ArtifactIntegrityError):
                ArtifactValidator.validate_artifact_scope("/etc/passwd", tmpdir)
