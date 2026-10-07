import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import tempfile
import subprocess
import os

from src.infrastructure.synthesis.vivado_flash import VivadoFlashService
from src.domain.ports.flash_service import FlashResult


class TestVivadoFlashService:
    """Tests für den VivadoFlashService."""

    def setup_method(self):
        """Test-Fixture."""
        self.temp_dir = tempfile.mkdtemp()
        self.bitstream_path = Path(self.temp_dir) / "test.bit"
        self.bitstream_path.write_bytes(b"fake bitstream data")

    def teardown_method(self):
        """Cleanup."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch('shutil.which')
    def test_toolchain_available_true(self, mock_which):
        """Test: toolchain_available gibt True zurück wenn vivado gefunden wird."""
        mock_which.return_value = "/usr/bin/vivado"
        service = VivadoFlashService(vivado_binary="vivado")
        assert service.toolchain_available() is True
        mock_which.assert_called_with("vivado")

    @patch('shutil.which')
    def test_toolchain_available_false(self, mock_which):
        """Test: toolchain_available gibt False zurück wenn vivado nicht gefunden wird."""
        mock_which.return_value = None
        service = VivadoFlashService(vivado_binary="vivado")
        assert service.toolchain_available() is False

    @patch('shutil.which')
    def test_toolchain_available_with_settings_script(self, mock_which):
        """Test: toolchain_available gibt True zurück wenn settings_script existiert."""
        mock_which.return_value = None
        settings_file = Path(self.temp_dir) / "settings64.sh"
        settings_file.write_text("#!/bin/bash\n")
        service = VivadoFlashService(vivado_binary="vivado", settings_script=str(settings_file))
        assert service.toolchain_available() is True

    @patch.object(VivadoFlashService, '_run_vivado', return_value={"returncode": 0, "stdout": "Programming completed successfully\nSPI flash programming completed successfully", "stderr": ""})
    @patch.object(VivadoFlashService, 'detect_boards', return_value=[{"index": 0, "name": "xc7s50", "part": "xc7s50csga324-1", "device": "xc7s50_0", "details": "xc7s50csga324-1 (xc7s50_0)"}])
    @patch('shutil.which')
    def test_flash_success(self, mock_which, mock_detect, mock_run_vivado):
        """Test: Erfolgreiches Flashen."""
        mock_which.return_value = "/usr/bin/vivado"

        service = VivadoFlashService(vivado_binary="vivado")

        result = service.flash(str(self.bitstream_path), expected_part="xc7s50csga324-1")

        assert isinstance(result, FlashResult)
        assert result.passed is True
        assert "programmiert" in result.message.lower()
        assert result.board_detected is True
        assert result.board_count == 1

    @patch.object(VivadoFlashService, '_run_vivado', return_value={"returncode": 1, "stdout": "", "stderr": "ERROR: Failed to program device"})
    @patch.object(VivadoFlashService, 'detect_boards', return_value=[{"index": 0, "name": "xc7s50", "part": "xc7s50csga324-1", "device": "xc7s50_0", "details": "xc7s50csga324-1 (xc7s50_0)"}])
    @patch('shutil.which')
    def test_flash_failure(self, mock_which, mock_detect, mock_run_vivado):
        """Test: Fehlgeschlagenes Flashen."""
        mock_which.return_value = "/usr/bin/vivado"

        service = VivadoFlashService(vivado_binary="vivado")

        with patch.object(service, 'detect_boards', return_value=[
            {"index": 0, "name": "xc7s50", "part": "xc7s50csga324-1", "device": "xc7s50_0", "details": "xc7s50csga324-1 (xc7s50_0)"}
        ]):
            result = service.flash(str(self.bitstream_path), expected_part="xc7s50csga324-1")

        assert result.passed is False
        assert "failed" in result.message.lower()

    @patch.object(VivadoFlashService, 'detect_boards')
    @patch('shutil.which')
    def test_flash_no_board_detected(self, mock_which, mock_detect):
        """Test: Flash fehlschlägt wenn kein Board erkannt wird."""
        mock_which.return_value = "/usr/bin/vivado"
        mock_detect.return_value = []
        
        service = VivadoFlashService(vivado_binary="vivado")
        result = service.flash(str(self.bitstream_path), expected_part="xc7s50csga324-1")
        
        assert result.passed is False
        assert "kein passendes" in result.message.lower()

    @patch.object(VivadoFlashService, 'detect_boards')
    @patch('shutil.which')
    def test_flash_multiple_boards(self, mock_which, mock_detect):
        """Test: Flash fehlschlägt bei mehreren passenden Boards."""
        mock_which.return_value = "/usr/bin/vivado"
        mock_detect.return_value = [
            {"index": 0, "name": "xc7s50", "part": "xc7s50csga324-1", "device": "xc7s50_0", "details": "xc7s50csga324-1 (xc7s50_0)"},
            {"index": 1, "name": "xc7s50", "part": "xc7s50csga324-1", "device": "xc7s50_1", "details": "xc7s50csga324-1 (xc7s50_1)"},
        ]
        
        service = VivadoFlashService(vivado_binary="vivado")
        result = service.flash(str(self.bitstream_path), expected_part="xc7s50csga324-1")
        
        assert result.passed is False
        assert "mehrere" in result.message.lower()

    @patch('shutil.which')
    def test_flash_bitstream_not_found(self, mock_which):
        """Test: Flash fehlschlägt wenn Bitstream-Datei nicht existiert."""
        mock_which.return_value = "/usr/bin/vivado"
        
        service = VivadoFlashService(vivado_binary="vivado")
        result = service.flash("/nonexistent/path/test.bit", expected_part="xc7s50csga324-1")
        
        assert result.passed is False
        assert "not found" in result.message.lower()

    def test_flash_uses_source_not_tclargs(self):
        """Test: Vivado wird mit -source gestartet, nicht mit -tclargs."""
        service = VivadoFlashService(vivado_binary="vivado")
        script = service._generate_program_script("/path/to/test.bit", "xc7s50_0")
        assert "-source" not in script  # -source wird in _run_vivado verwendet, nicht im TCL-Skript
        assert "-tclargs" not in script

    @patch.object(VivadoFlashService, '_run_vivado', return_value={"returncode": -1, "stdout": "", "stderr": "Vivado timed out after 60s"})
    @patch('shutil.which')
    def test_flash_timeout(self, mock_which, mock_run_vivado):
        """Test: Flash Timeout."""
        mock_which.return_value = "/usr/bin/vivado"

        service = VivadoFlashService(vivado_binary="vivado", timeout_seconds=60)

        with patch.object(service, 'detect_boards', return_value=[
            {"index": 0, "name": "xc7s50", "part": "xc7s50csga324-1", "device": "xc7s50_0", "details": "xc7s50csga324-1 (xc7s50_0)"}
        ]):
            result = service.flash(str(self.bitstream_path), expected_part="xc7s50csga324-1")

        assert result.passed is False
        assert "timed out" in result.message.lower()

    def test_generate_detect_script(self):
        """Test: Detect-Script wird korrekt generiert."""
        service = VivadoFlashService(vivado_binary="vivado")
        script = service._generate_detect_script("xc7s50csga324-1")
        
        assert "open_hw_manager" in script
        assert "connect_hw_server" in script
        assert "get_hw_devices" in script
        assert "BOARD:" in script
        assert "-tclargs" not in script

    def test_generate_program_script(self):
        """Test: Program-Script wird korrekt generiert."""
        service = VivadoFlashService(vivado_binary="vivado")
        script = service._generate_program_script("/path/to/test.bit", "xc7s50_0")
        
        assert "open_hw_manager" in script
        assert "connect_hw_server" in script
        assert "get_hw_devices" in script
        assert "set_property PROGRAM.FILE" in script
        assert "program_hw_devices" in script
        assert "/path/to/test.bit" in script
        assert "target_device" in script
        assert "-tclargs" not in script


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
