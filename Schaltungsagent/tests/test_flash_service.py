import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import tempfile
import subprocess

from src.services.flash_service import OpenFPGALoaderFlashService
from src.domain.ports.flash_service import FlashResult


class TestOpenFPGALoaderFlashService:
    """Tests für den OpenFPGALoaderFlashService."""

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
        """Test: toolchain_available gibt True zurück wenn openFPGALoader gefunden wird."""
        mock_which.return_value = "/usr/bin/openFPGALoader"
        service = OpenFPGALoaderFlashService(binary="openFPGALoader")
        assert service.toolchain_available() is True
        mock_which.assert_called_with("openFPGALoader")

    @patch('shutil.which')
    def test_toolchain_available_false(self, mock_which):
        """Test: toolchain_available gibt False zurück wenn openFPGALoader nicht gefunden wird."""
        mock_which.return_value = None
        service = OpenFPGALoaderFlashService(binary="openFPGALoader")
        assert service.toolchain_available() is False

    @patch('subprocess.run')
    @patch('shutil.which')
    def test_detect_boards_single(self, mock_which, mock_run):
        """Test: Erkennung eines einzelnen Boards."""
        mock_which.return_value = "/usr/bin/openFPGALoader"
        
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "Found 1 device(s):\n  0: Arty S7 (serial=210299A5B3E3)\n"
        mock_result.stderr = ""
        mock_run.return_value = mock_result
        
        service = OpenFPGALoaderFlashService()
        boards = service.detect_boards()
        
        assert len(boards) == 1
        assert boards[0]["index"] == 0
        assert "Arty S7" in boards[0]["name"]
        assert boards[0]["details"] == "Arty S7 (serial=210299A5B3E3)"

    @patch('subprocess.run')
    @patch('shutil.which')
    def test_detect_boards_multiple(self, mock_which, mock_run):
        """Test: Erkennung mehrerer Boards."""
        mock_which.return_value = "/usr/bin/openFPGALoader"
        
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = (
            "Found 2 device(s):\n"
            "  0: Arty S7 (serial=210299A5B3E3)\n"
            "  1: Nexys A7 (serial=123456789ABC)\n"
        )
        mock_result.stderr = ""
        mock_run.return_value = mock_result
        
        service = OpenFPGALoaderFlashService()
        boards = service.detect_boards()
        
        assert len(boards) == 2
        assert boards[0]["index"] == 0
        assert boards[1]["index"] == 1

    @patch('subprocess.run')
    def test_detect_boards_current_openfpgaloader_format(self, mock_run):
        """Test: aktuelle openFPGALoader-Ausgabe mit index/model wird erkannt."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = (
            "index 0:\n"
            "        idcode 0x362f093\n"
            "        manufacturer xilinx\n"
            "        family spartan7\n"
            "        model  xc7s50\n"
        )
        mock_run.return_value = mock_result

        boards = OpenFPGALoaderFlashService().detect_boards()

        assert len(boards) == 1
        assert boards[0]["index"] == 0
        assert boards[0]["model"] == "xc7s50"
        assert boards[0]["family"] == "spartan7"

    @patch('subprocess.run')
    @patch('shutil.which')
    def test_detect_boards_none(self, mock_which, mock_run):
        """Test: Keine Boards erkannt."""
        mock_which.return_value = "/usr/bin/openFPGALoader"
        
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "Found 0 device(s):\n"
        mock_result.stderr = ""
        mock_run.return_value = mock_result
        
        service = OpenFPGALoaderFlashService()
        boards = service.detect_boards()
        
        assert len(boards) == 0

    @patch('subprocess.run')
    @patch('shutil.which')
    def test_detect_boards_error(self, mock_which, mock_run):
        """Test: Fehler bei Board-Erkennung."""
        mock_which.return_value = "/usr/bin/openFPGALoader"
        mock_run.side_effect = FileNotFoundError("openFPGALoader not found")
        
        service = OpenFPGALoaderFlashService()
        boards = service.detect_boards()
        
        assert len(boards) == 0

    @patch('subprocess.run')
    @patch.object(OpenFPGALoaderFlashService, 'detect_boards')
    @patch('shutil.which')
    def test_flash_success(self, mock_which, mock_detect, mock_run):
        """Test: Erfolgreiches Flashen."""
        mock_which.return_value = "/usr/bin/openFPGALoader"
        mock_detect.return_value = [
            {"index": 0, "name": "Arty S7", "details": "Arty S7 (serial=123)"}
        ]
        
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "Programming successful"
        mock_result.stderr = ""
        mock_run.return_value = mock_result
        
        service = OpenFPGALoaderFlashService()
        result = service.flash(str(self.bitstream_path), board="arty_s7")
        
        assert isinstance(result, FlashResult)
        assert result.passed is True
        assert "erfolgreich" in result.message.lower()
        assert result.board_detected is True
        assert result.board_count == 1
        mock_run.assert_called_once()

    @patch('subprocess.run')
    @patch.object(OpenFPGALoaderFlashService, 'detect_boards')
    @patch('shutil.which')
    def test_flash_failure(self, mock_which, mock_detect, mock_run):
        """Test: Fehlgeschlagenes Flashen."""
        mock_which.return_value = "/usr/bin/openFPGALoader"
        mock_detect.return_value = [
            {"index": 0, "name": "Arty S7", "details": "Arty S7 (serial=123)"}
        ]
        
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "ERROR: Failed to program device"
        mock_run.return_value = mock_result
        
        service = OpenFPGALoaderFlashService()
        result = service.flash(str(self.bitstream_path), board="arty_s7")
        
        assert result.passed is False
        assert "fehlgeschlagen" in result.message.lower()
        assert result.board_detected is True

    @patch.object(OpenFPGALoaderFlashService, 'detect_boards')
    @patch('shutil.which')
    def test_flash_no_board_detected(self, mock_which, mock_detect):
        """Test: Flash fehlschlägt wenn kein Board erkannt wird."""
        mock_which.return_value = "/usr/bin/openFPGALoader"
        mock_detect.return_value = []
        
        service = OpenFPGALoaderFlashService()
        result = service.flash(str(self.bitstream_path), board="arty_s7")
        
        assert result.passed is False
        assert "Kein FPGA-Board erkannt" in result.message
        assert result.board_detected is False
        assert result.board_count == 0

    @patch.object(OpenFPGALoaderFlashService, 'detect_boards')
    @patch('shutil.which')
    def test_flash_multiple_boards(self, mock_which, mock_detect):
        """Test: Flash fehlschlägt bei mehreren Boards."""
        mock_which.return_value = "/usr/bin/openFPGALoader"
        mock_detect.return_value = [
            {"index": 0, "name": "Arty S7", "details": "Arty S7 (serial=123)"},
            {"index": 1, "name": "Nexys A7", "details": "Nexys A7 (serial=456)"},
        ]
        
        service = OpenFPGALoaderFlashService()
        result = service.flash(str(self.bitstream_path), board="arty_s7")
        
        assert result.passed is False
        assert "Mehrere FPGA-Boards erkannt" in result.message
        assert result.board_detected is True
        assert result.board_count == 2

    @patch('shutil.which')
    def test_flash_bitstream_not_found(self, mock_which):
        """Test: Flash fehlschlägt wenn Bitstream-Datei nicht existiert."""
        mock_which.return_value = "/usr/bin/openFPGALoader"
        
        service = OpenFPGALoaderFlashService()
        result = service.flash("/nonexistent/path/test.bit", board="arty_s7")
        
        assert result.passed is False
        assert "not found" in result.message.lower()

    @patch('subprocess.run')
    @patch.object(OpenFPGALoaderFlashService, 'detect_boards')
    @patch('shutil.which')
    def test_flash_timeout(self, mock_which, mock_detect, mock_run):
        """Test: Flash Timeout."""
        mock_which.return_value = "/usr/bin/openFPGALoader"
        mock_detect.return_value = [
            {"index": 0, "name": "Arty S7", "details": "Arty S7 (serial=123)"}
        ]
        mock_run.side_effect = subprocess.TimeoutExpired("openFPGALoader", 60)
        
        service = OpenFPGALoaderFlashService(timeout_seconds=60)
        result = service.flash(str(self.bitstream_path), board="arty_s7")
        
        assert result.passed is False
        assert "timed out" in result.message.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])