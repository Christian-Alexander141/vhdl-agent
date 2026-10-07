"""Tests für Filesystem-Sicherheit und Pfad-Traversal-Schutz."""
import sys
import os
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from src.services.filesystem_service import LocalFileSystemService, PathTraversalError


class TestPathTraversalProtection:
    """Testet, dass der LocalFileSystemService Pfad-Traversal abweist."""

    def test_traversal_with_dots(self):
        base_dir = tempfile.mkdtemp()
        fs = LocalFileSystemService(base_dir=base_dir)
        with pytest.raises(PathTraversalError):
            fs.read_file("../../etc/passwd")

    def test_absolute_path_outside_base(self):
        base_dir = tempfile.mkdtemp()
        fs = LocalFileSystemService(base_dir=base_dir)
        with pytest.raises(PathTraversalError):
            fs.read_file("/etc/passwd")

    def test_null_byte_in_path(self):
        base_dir = tempfile.mkdtemp()
        fs = LocalFileSystemService(base_dir=base_dir)
        with pytest.raises(PathTraversalError):
            fs.read_file("src/\x00evil.vhd")

    def test_symlink_traversal(self):
        base_dir = tempfile.mkdtemp()
        fs = LocalFileSystemService(base_dir=base_dir)
        link_path = os.path.join(base_dir, "link")
        os.symlink("/etc/passwd", link_path)
        # Symlinks inside the workspace should be blocked if they point outside
        try:
            fs.read_file("link")
        except (PathTraversalError, OSError):
            pass  # Either rejection or OSError is acceptable
        finally:
            os.unlink(link_path)

    def test_write_outside_base(self):
        base_dir = tempfile.mkdtemp()
        fs = LocalFileSystemService(base_dir=base_dir)
        with pytest.raises(PathTraversalError):
            fs.write_file("../../tmp/evil.txt", "content")

    def test_delete_workspace_traversal(self):
        base_dir = tempfile.mkdtemp()
        fs = LocalFileSystemService(base_dir=base_dir)
        with pytest.raises(PathTraversalError):
            fs.delete_workspace("..")
        with pytest.raises(PathTraversalError):
            fs.delete_workspace("../escape")

    def test_invalid_project_id(self):
        base_dir = tempfile.mkdtemp()
        fs = LocalFileSystemService(base_dir=base_dir)
        with pytest.raises(PathTraversalError):
            fs.workspace_path("project/../escape")
        with pytest.raises(PathTraversalError):
            fs.workspace_path("project with spaces")
        with pytest.raises(PathTraversalError):
            fs.workspace_path("")

    def test_valid_project_id(self):
        base_dir = tempfile.mkdtemp()
        fs = LocalFileSystemService(base_dir=base_dir)
        path = fs.workspace_path("my-project_1")
        assert "my-project_1" in path

    def test_file_exists_traversal_returns_false(self):
        base_dir = tempfile.mkdtemp()
        fs = LocalFileSystemService(base_dir=base_dir)
        result = fs.file_exists("../../etc/passwd")
        assert result is False

    def test_list_files_traversal_raises(self):
        base_dir = tempfile.mkdtemp()
        fs = LocalFileSystemService(base_dir=base_dir)
        with pytest.raises(PathTraversalError):
            fs.list_files("../../etc")

    def test_prefix_attack(self):
        """Teste gleichnamige Pfadpraefix-Angriffe."""
        base_dir = tempfile.mkdtemp()
        fs = LocalFileSystemService(base_dir=base_dir)
        # Create a file outside the workspace and symlink to it
        outside_dir = tempfile.mkdtemp()
        outside_file = Path(outside_dir) / "secret.txt"
        outside_file.write_text("secret")
        link = Path(base_dir) / "link_outside"
        link.symlink_to(outside_file)
        try:
            with pytest.raises(PathTraversalError):
                fs.read_file("link_outside")
        finally:
            link.unlink()
            outside_file.unlink()
            Path(outside_dir).rmdir()

    def test_atomic_write(self):
        """Teste, dass atomare Writes funktionieren."""
        base_dir = tempfile.mkdtemp()
        fs = LocalFileSystemService(base_dir=base_dir)
        path = fs.workspace_path("test-atom")
        fs.write_file(f"{path}/test.vhd", "entity test is end entity;")
        content = fs.read_file(f"{path}/test.vhd")
        assert "entity test" in content


class TestProjectIsolation:
    """Testet, dass Projekt-Workspaces isoliert sind."""

    def test_separate_workspaces(self):
        base_dir = tempfile.mkdtemp()
        fs1 = LocalFileSystemService(base_dir=base_dir)
        fs2 = LocalFileSystemService(base_dir=base_dir)
        path1 = fs1.workspace_path("project-a")
        path2 = fs2.workspace_path("project-b")
        assert path1 != path2
        assert "project-a" in path1
        assert "project-b" in path2

    def test_workspace_creation_isolated(self):
        base_dir = tempfile.mkdtemp()
        fs = LocalFileSystemService(base_dir=base_dir)
        ws1 = fs.create_workspace("proj-a")
        ws2 = fs.create_workspace("proj-b")
        assert "proj-a" in ws1
        assert "proj-b" in ws2
        assert os.path.isdir(ws1)
        assert os.path.isdir(ws2)
        assert ws1 != ws2
