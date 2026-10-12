import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import tempfile
import os

from src.infrastructure.synthesis.vivado_synthesis import VivadoBitstreamService
from src.domain.ports.bitstream_service import BitstreamResult


class TestVivadoBitstreamService:
    """Tests für den VivadoBitstreamService."""

    def setup_method(self):
        """Test-Fixture mit temporärem Workspace."""
        self.temp_dir = tempfile.mkdtemp()
        self.workspace = Path(self.temp_dir)
        self.src_dir = self.workspace / "src"
        self.src_dir.mkdir(parents=True)
        
        # Einfache VHDL-Datei erstellen
        self.vhdl_content = """
library IEEE;
use IEEE.STD_LOGIC_1164.ALL;

entity my_counter is
    Port ( clk : in STD_LOGIC;
           rst : in STD_LOGIC;
           data_out : out STD_LOGIC_VECTOR(7 downto 0));
end my_counter;

architecture Behavioral of my_counter is
begin
    process(clk)
    begin
        if rising_edge(clk) then
            if rst = '1' then
                data_out <= (others => '0');
            else
                data_out <= data_out + 1;
            end if;
        end if;
    end process;
end Behavioral;
"""
        (self.src_dir / "my_counter.vhd").write_text(self.vhdl_content)

    def teardown_method(self):
        """Cleanup."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch('shutil.which')
    def test_toolchain_available_true(self, mock_which):
        """Test: toolchain_available gibt True zurück wenn vivado gefunden wird."""
        mock_which.return_value = "/usr/bin/vivado"
        service = VivadoBitstreamService(vivado_binary="vivado")
        assert service.toolchain_available() is True
        mock_which.assert_called_with("vivado")

    @patch('shutil.which')
    def test_toolchain_available_false(self, mock_which):
        """Test: toolchain_available gibt False zurück wenn vivado nicht gefunden wird."""
        mock_which.return_value = None
        service = VivadoBitstreamService(vivado_binary="vivado")
        assert service.toolchain_available() is False

    @patch('subprocess.run')
    @patch('shutil.which')
    def test_build_bitstream_success(self, mock_which, mock_run):
        """Test: Erfolgreicher Bitstream-Build."""
        mock_which.return_value = "/usr/bin/vivado"
        
        # Mock subprocess.run für vivado
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "Vivado synthesis completed"
        mock_result.stderr = ""
        mock_run.return_value = mock_result
        
        service = VivadoBitstreamService(
            vivado_binary="vivado",
            timeout_seconds=60,
        )
        
        # Wir müssen auch das Bitstream-File "erzeugen" für den Test
        bitstream_file = self.workspace / "build" / "bitstream" / "my_counter.bit"
        mock_stat = Mock()
        mock_stat.st_size = 1024

        original_stat = Path.stat

        def mock_stat_fn(self_path, *args, **kwargs):
            if str(self_path) == str(bitstream_file):
                return mock_stat
            return original_stat(self_path, *args, **kwargs)

        with patch.object(Path, 'exists', return_value=True):
            with patch.object(Path, 'write_text'):
                with patch.object(Path, 'stat', mock_stat_fn):
                    result = service.build_bitstream(str(self.workspace), target="arty_s7_50")
        
        assert isinstance(result, BitstreamResult)
        assert result.passed is True
        assert "my_counter" in result.message
        assert "xc7s50csga324-1" in result.details.get("fpga_part", "")
        mock_run.assert_called_once()

    @patch('subprocess.run')
    @patch('shutil.which')
    def test_build_bitstream_failure(self, mock_which, mock_run):
        """Test: Fehlgeschlagener Bitstream-Build."""
        mock_which.return_value = "/usr/bin/vivado"
        
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "ERROR: [Synth 8-327] syntax error"
        mock_run.return_value = mock_result
        
        service = VivadoBitstreamService(
            vivado_binary="vivado",
            timeout_seconds=60,
        )
        
        result = service.build_bitstream(str(self.workspace), target="arty_s7_50")
        
        assert isinstance(result, BitstreamResult)
        assert result.passed is False
        assert "failed" in result.message.lower()
        assert "syntax error" in result.details.get("error", "")

    @patch('subprocess.run')
    @patch('shutil.which')
    def test_build_bitstream_timeout(self, mock_which, mock_run):
        """Test: Bitstream-Build Timeout."""
        import subprocess
        mock_which.return_value = "/usr/bin/vivado"
        mock_run.side_effect = subprocess.TimeoutExpired("vivado", 60)
        
        service = VivadoBitstreamService(
            vivado_binary="vivado",
            timeout_seconds=60,
        )
        
        result = service.build_bitstream(str(self.workspace), target="arty_s7_50")
        
        assert isinstance(result, BitstreamResult)
        assert result.passed is False
        assert any("timed out" in step.get("stderr", "").lower() for step in result.details.get("steps", []))

    @patch('shutil.which')
    def test_build_bitstream_no_src_dir(self, mock_which):
        """Test: Kein src-Verzeichnis vorhanden."""
        mock_which.return_value = "/usr/bin/vivado"
        
        empty_workspace = Path(self.temp_dir) / "empty"
        empty_workspace.mkdir()
        
        service = VivadoBitstreamService(vivado_binary="vivado")
        result = service.build_bitstream(str(empty_workspace))
        
        assert result.passed is False
        assert "No src directory found" in result.message

    @patch('shutil.which')
    def test_build_bitstream_no_vhdl_files(self, mock_which):
        """Test: Keine VHDL-Dateien in src."""
        mock_which.return_value = "/usr/bin/vivado"
        
        empty_src = Path(self.temp_dir) / "empty_src"
        empty_src.mkdir(parents=True)
        (empty_src / "src").mkdir()
        
        service = VivadoBitstreamService(vivado_binary="vivado")
        result = service.build_bitstream(str(empty_src))
        
        assert result.passed is False
        assert "No VHDL files found" in result.message

    def test_build_repair_instruction(self):
        """Test: build_repair_instruction erzeugt sinnvollen Text."""
        service = VivadoBitstreamService()
        
        result = BitstreamResult(
            passed=False,
            message="Vivado synthesis failed",
            bitstream_path="",
            details={
                "steps": [{
                    "step": "synthesize",
                    "label": "test_entity",
                    "returncode": 1,
                    "stdout": "",
                    "stderr": "ERROR: syntax error near 'end'",
                }],
                "file": "/workspace/src/test_entity.vhd",
                "fpga_part": "xc7s50csg324-1",
                "dut_content": "entity test_entity is ...",
            },
        )
        
        instruction = result.build_repair_instruction(
            original_request="Build a counter",
            iteration=1,
        )
        
        assert "Repariere die VHDL-Komponente" in instruction
        assert "Build a counter" in instruction
        assert "Reparatur-Iteration: 1" in instruction
        assert "xc7s50csg324-1" in instruction
        assert "syntax error" in instruction
        assert "entity test_entity is" in instruction
        assert "Regeln für die Reparatur" in instruction


if __name__ == "__main__":
    pytest.main([__file__, "-v"])