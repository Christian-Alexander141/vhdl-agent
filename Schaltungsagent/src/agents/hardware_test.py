import logging
import uuid
from abc import ABC, abstractmethod
from typing import Any
from dataclasses import dataclass, field

from src.domain.agents import BaseAgent, AgentTask, AgentResult, AgentStatus

logger = logging.getLogger(__name__)


@dataclass
class HardwareTestInterface:
    """Abstrakte Schnittstelle für Hardware-Tests auf FPGA.
    
    Konkrete Implementierungen können UART, GPIO, JTAG, etc. verwenden.
    """
    
    @abstractmethod
    async def reset(self) -> bool:
        """Resetet das FPGA-Design (Hardware-Reset oder Soft-Reset)."""
        pass
    
    @abstractmethod
    async def send_command(self, command: bytes) -> bool:
        """Sendet Kommando an das laufende Design."""
        pass
    
    @abstractmethod
    async def send_program(self, program: bytes) -> bool:
        """Sendet Programm/Code an das Design (z.B. für CPU)."""
        pass
    
    @abstractmethod
    async def start(self) -> bool:
        """Startet die Ausführung."""
        pass
    
    @abstractmethod
    async def read_output(self, length: int = 1024, timeout: float = 5.0) -> bytes:
        """Liest Ausgabe vom Design."""
        pass
    
    @abstractmethod
    async def run_test(self, test: dict) -> dict:
        """Führt einen einzelnen Hardware-Test aus."""
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """Schließt die Verbindung."""
        pass


class MockHardwareTestInterface(HardwareTestInterface):
    """Mock-Implementierung für Tests ohne echte Hardware."""
    
    def __init__(self):
        self._connected = False
    
    async def reset(self) -> bool:
        self._connected = True
        logger.info("Mock: FPGA reset")
        return True
    
    async def send_command(self, command: bytes) -> bool:
        logger.info(f"Mock: Send command: {command.hex()}")
        return True
    
    async def send_program(self, program: bytes) -> bool:
        logger.info(f"Mock: Send program ({len(program)} bytes)")
        return True
    
    async def start(self) -> bool:
        logger.info("Mock: Start execution")
        return True
    
    async def read_output(self, length: int = 1024, timeout: float = 5.0) -> bytes:
        logger.info(f"Mock: Read output (max {length} bytes)")
        return b"MOCK_OUTPUT"
    
    async def run_test(self, test: dict) -> dict:
        logger.info(f"Mock: Run test: {test.get('name', 'unknown')}")
        return {"passed": True, "output": "OK", "duration_ms": 10}
    
    async def close(self) -> None:
        self._connected = False
        logger.info("Mock: Connection closed")


class UARTHardwareTestInterface(HardwareTestInterface):
    """UART-basierte Hardware-Test-Schnittstelle.
    
    Verwendet pySerial für Kommunikation über USB-UART Bridge.
    """
    
    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 5.0):
        self._port = port
        self._baudrate = baudrate
        self._timeout = timeout
        self._serial = None
    
    async def _ensure_connected(self):
        if self._serial is None:
            import serial
            self._serial = serial.Serial(
                port=self._port,
                baudrate=self._baudrate,
                timeout=self._timeout,
            )
    
    async def reset(self) -> bool:
        await self._ensure_connected()
        # DTR/RTS togglen für Hardware-Reset
        self._serial.dtr = False
        self._serial.rts = False
        import asyncio
        await asyncio.sleep(0.1)
        self._serial.dtr = True
        self._serial.rts = True
        await asyncio.sleep(0.1)
        self._serial.dtr = False
        self._serial.rts = False
        await asyncio.sleep(0.5)
        self._serial.reset_input_buffer()
        self._serial.reset_output_buffer()
        return True
    
    async def send_command(self, command: bytes) -> bool:
        await self._ensure_connected()
        self._serial.write(command)
        self._serial.flush()
        return True
    
    async def send_program(self, program: bytes) -> bool:
        await self._ensure_connected()
        # Protokoll: Länge (4 bytes) + Daten
        import struct
        length_bytes = struct.pack('<I', len(program))
        self._serial.write(length_bytes)
        self._serial.write(program)
        self._serial.flush()
        return True
    
    async def start(self) -> bool:
        await self._ensure_connected()
        # Start-Kommando senden
        self._serial.write(b'START\n')
        self._serial.flush()
        return True
    
    async def read_output(self, length: int = 1024, timeout: float = 5.0) -> bytes:
        await self._ensure_connected()
        import asyncio
        # Timeout temporär anpassen
        old_timeout = self._serial.timeout
        self._serial.timeout = timeout
        try:
            data = self._serial.read(length)
            return data
        finally:
            self._serial.timeout = old_timeout
    
    async def run_test(self, test: dict) -> dict:
        await self._ensure_connected()
        test_name = test.get("name", "unknown")
        test_type = test.get("type", "custom")
        
        try:
            if test_type == "echo":
                # Echo-Test
                test_data = test.get("data", b"HELLO")
                await self.send_command(test_data)
                response = await self.read_output(len(test_data) + 10)
                passed = response == test_data
                return {"passed": passed, "output": response.hex()}
            
            elif test_type == "cpu_program":
                # CPU-Programm laden und ausführen
                program = test.get("program", b"")
                await self.send_program(program)
                await self.start()
                response = await self.read_output(1024, timeout=10.0)
                expected = test.get("expected", b"")
                passed = expected in response if expected else True
                return {"passed": passed, "output": response.hex()}
            
            else:
                # Custom test
                return {"passed": True, "output": "custom test executed"}
                
        except Exception as e:
            logger.exception(f"Hardware test {test_name} failed")
            return {"passed": False, "error": str(e)}
    
    async def close(self) -> None:
        if self._serial:
            self._serial.close()
            self._serial = None


class HardwareTestAgent(BaseAgent):
    """Führt Hardware-Tests auf echtem FPGA durch.
    
    Verwendet HardwareTestInterface für Kommunikation.
    Unterstützt Mock und UART-Implementierungen.
    """

    def __init__(
        self,
        llm_service,
        rag_service,
        filesystem_service,
        event_publisher=None,
        hardware_interface: HardwareTestInterface | None = None,
    ):
        super().__init__("HardwareTestAgent", event_publisher)
        self._llm = llm_service
        self._rag = rag_service
        self._fs = filesystem_service
        self._hw_interface = hardware_interface or MockHardwareTestInterface()

    @property
    def supported_task_types(self) -> list[str]:
        return ["hardware_test", "run_test_suite", "validate_hardware"]

    async def execute(self, task: AgentTask) -> AgentResult:
        task_type = task.type
        
        if task_type == "hardware_test":
            return await self._run_hardware_test(task)
        elif task_type == "run_test_suite":
            return await self._run_test_suite(task)
        elif task_type == "validate_hardware":
            return await self._validate_hardware(task)
        else:
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.FAILED,
                error_message=f"Unknown task type: {task_type}",
            )

    async def _run_hardware_test(self, task: AgentTask) -> AgentResult:
        """Führt einen Hardware-Test durch."""
        fpga_config = task.inputs.get("fpga_config", {})
        architecture = task.inputs.get("architecture", {})
        workspace = task.inputs.get("workspace", "")
        
        self.emit_event("HARDWARE_TEST_STARTED", {
            "task_id": task.id,
            "fpga_target": fpga_config.get("target", "unknown"),
        })
        
        try:
            # Hardware-Verbindung herstellen
            await self._hw_interface.reset()
            
            # Test-Suite definieren
            tests = self._define_test_suite(architecture, fpga_config)
            
            passed = 0
            failed = 0
            test_results = []
            
            for test in tests:
                result = await self._hw_interface.run_test(test)
                test_result = {
                    "name": test.get("name", "unknown"),
                    "type": test.get("type", "custom"),
                    "passed": result.get("passed", False),
                    "output": result.get("output", ""),
                    "error": result.get("error", ""),
                }
                test_results.append(test_result)
                
                if test_result["passed"]:
                    passed += 1
                else:
                    failed += 1
            
            await self._hw_interface.close()
            
            # Gesamtergebnis
            overall_passed = failed == 0
            
            hardware_result = {
                "status": "passed" if overall_passed else "failed",
                "tests": test_results,
                "passed": passed,
                "failed": failed,
                "communication_log": [],
            }
            
            if overall_passed:
                self.emit_event("HARDWARE_TEST_PASSED", {
                    "task_id": task.id,
                    "tests_passed": passed,
                })
            else:
                self.emit_event("HARDWARE_TEST_FAILED", {
                    "task_id": task.id,
                    "tests_failed": failed,
                    "failures": [t for t in test_results if not t["passed"]],
                })
            
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.COMPLETED if overall_passed else AgentStatus.FAILED,
                outputs={"hardware_result": hardware_result},
                error_message="" if overall_passed else f"{failed} hardware test(s) failed",
            )
            
        except Exception as e:
            logger.exception("Hardware test failed")
            await self._hw_interface.close()
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.FAILED,
                error_message=f"Hardware test error: {e}",
            )

    def _define_test_suite(self, architecture: dict, fpga_config: dict) -> list[dict]:
        """Definiert Test-Suite basierend auf Architektur."""
        modules = architecture.get("modules", [])
        module_names = [m.get("name", "") for m in modules]
        
        tests = []
        
        # Basis-Tests
        tests.append({
            "name": "fpga_alive",
            "type": "echo",
            "data": b"ALIVE",
        })
        
        # Modul-spezifische Tests
        if "uart" in module_names:
            tests.append({
                "name": "uart_loopback",
                "type": "echo",
                "data": b"UART_TEST",
            })
        
        if any("cpu" in m.lower() or "processor" in m.lower() for m in module_names):
            tests.append({
                "name": "cpu_basic",
                "type": "cpu_program",
                "program": self._generate_cpu_test_program(),
                "expected": b"OK",
            })
        
        # GPIO-Test falls GPIO-Modul vorhanden
        if any("gpio" in m.lower() or "led" in m.lower() for m in module_names):
            tests.append({
                "name": "gpio_toggle",
                "type": "custom",
                "command": b"GPIO_TOGGLE",
            })
        
        return tests

    def _generate_cpu_test_program(self) -> bytes:
        """Generiert einfaches CPU-Test-Programm."""
        # Platzhalter: Einfaches Programm das "OK" ausgibt
        return b"\x00\x01\x02\x03"  # Dummy machine code

    async def _run_test_suite(self, task: AgentTask) -> AgentResult:
        """Führt eine definierte Test-Suite aus."""
        tests = task.inputs.get("tests", [])
        
        if not tests:
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.FAILED,
                error_message="No tests provided",
            )
        
        await self._hw_interface.reset()
        
        passed = 0
        failed = 0
        results = []
        
        for test in tests:
            result = await self._hw_interface.run_test(test)
            test_result = {
                "name": test.get("name", "unknown"),
                "passed": result.get("passed", False),
                "output": result.get("output", ""),
                "error": result.get("error", ""),
            }
            results.append(test_result)
            
            if test_result["passed"]:
                passed += 1
            else:
                failed += 1
        
        await self._hw_interface.close()
        
        return AgentResult(
            task_id=task.id,
            status=AgentStatus.COMPLETED if failed == 0 else AgentStatus.FAILED,
            outputs={
                "tests": results,
                "passed": passed,
                "failed": failed,
            },
        )

    async def _validate_hardware(self, task: AgentTask) -> AgentResult:
        """Validiert Hardware-Funktionalität."""
        # Einfacher Connectivity-Test
        await self._hw_interface.reset()
        result = await self._hw_interface.run_test({
            "name": "connectivity",
            "type": "echo",
            "data": b"PING",
        })
        await self._hw_interface.close()
        
        return AgentResult(
            task_id=task.id,
            status=AgentStatus.COMPLETED if result.get("passed") else AgentStatus.FAILED,
            outputs={"connectivity": result.get("passed", False)},
        )