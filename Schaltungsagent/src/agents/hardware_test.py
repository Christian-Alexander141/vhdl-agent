import json
import logging
from abc import abstractmethod
from dataclasses import dataclass
from pathlib import Path

import yaml

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
        test_type = test.get("type", "")
        timeout = float(test.get("timeout_s", 5.0))
        expected: bytes = test.get("expected", b"")

        try:
            if test_type in ("echo", "uart_exchange"):
                send: bytes = test.get("send", b"")
                await self.send_command(send)
                response = await self.read_output(max(len(expected), 1), timeout=timeout)
            elif test_type == "cpu_program":
                await self.send_program(test.get("program", b""))
                await self.start()
                response = await self.read_output(max(len(expected), 1), timeout=timeout)
            else:
                return {
                    "passed": False,
                    "error": f"Test type '{test_type}' is not executable on UART",
                }
            if test.get("match") == "contains":
                passed = expected in response
            else:
                passed = response == expected
            return {
                "passed": passed,
                "output": response.hex(),
                "expected": expected.hex(),
            }
        except Exception as e:
            logger.exception(f"Hardware test {test_name} failed")
            return {"passed": False, "error": str(e)}

    async def close(self) -> None:
        if self._serial:
            self._serial.close()
            self._serial = None


class HardwareTestSpecError(ValueError):
    """Projektspezifische Hardwaretest-Spezifikation ist ungültig."""


def _as_bytes(value, field_name: str, test_name: str) -> bytes:
    """Akzeptiert bytes, Hex-Strings ("48 49") oder {"ascii": "..."}."""
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    if isinstance(value, dict) and "ascii" in value:
        return str(value["ascii"]).encode("ascii")
    if isinstance(value, list):
        return bytes(int(v) & 0xFF for v in value)
    if isinstance(value, str):
        try:
            return bytes.fromhex(value.replace("0x", "").replace(",", " "))
        except ValueError as exc:
            raise HardwareTestSpecError(
                f"{test_name}: field '{field_name}' is not valid hex: {value!r}"
            ) from exc
    raise HardwareTestSpecError(f"{test_name}: field '{field_name}' is missing or invalid")


def normalize_hardware_tests(raw_tests: list[dict]) -> list[dict]:
    """Validiert projektspezifische Testvektoren.

    Format je Test:
      name: str
      type: echo | uart_exchange | cpu_program
      send / program: Hex-String, Byte-Liste oder {"ascii": "..."}
      expected: erwartete UART-Antwort (Pflicht)
      match: exact (Default) | contains
      timeout_s: float
    """
    tests = []
    for index, raw in enumerate(raw_tests or []):
        if not isinstance(raw, dict):
            raise HardwareTestSpecError(f"Hardware test {index} must be a mapping")
        name = str(raw.get("name") or f"hw_test_{index}")
        test_type = raw.get("type", "uart_exchange")
        if test_type not in ("echo", "uart_exchange", "cpu_program"):
            raise HardwareTestSpecError(f"{name}: unsupported test type '{test_type}'")
        test = {
            "name": name,
            "type": test_type,
            "match": raw.get("match", "exact"),
            "timeout_s": float(raw.get("timeout_s", 5.0)),
            "requirement": raw.get("requirement", ""),
        }
        if test_type == "cpu_program":
            test["program"] = _as_bytes(raw.get("program"), "program", name)
            if not test["program"]:
                raise HardwareTestSpecError(f"{name}: cpu_program needs a non-empty program")
        else:
            test["send"] = _as_bytes(raw.get("send", raw.get("data")), "send", name)
        if test_type == "echo" and "expected" not in raw:
            test["expected"] = test["send"]
        else:
            test["expected"] = _as_bytes(raw.get("expected"), "expected", name)
        if not test["expected"]:
            raise HardwareTestSpecError(f"{name}: expected output must not be empty")
        tests.append(test)
    return tests


class HardwareTestAgent(BaseAgent):
    """Führt Hardware-Tests auf echtem FPGA durch.

    Ohne echte Schnittstelle (Mock) wird kein Test ausgeführt und kein Erfolg
    gemeldet (``SKIPPED``). Mit echter Schnittstelle laufen ausschließlich
    projektspezifische Testvektoren aus Architektur oder
    ``tests/hardware_tests.yaml``; fehlen sie, ist das Ergebnis ``BLOCKED``.
    """

    TEST_SPEC_FILES = ("hardware_tests.yaml", "hardware_tests.yml", "hardware_tests.json")

    def __init__(
        self,
        filesystem_service,
        event_publisher=None,
        hardware_interface: HardwareTestInterface | None = None,
    ):
        super().__init__("HardwareTestAgent", event_publisher)
        self._fs = filesystem_service
        self._hw_interface = hardware_interface or MockHardwareTestInterface()

    @property
    def supported_task_types(self) -> list[str]:
        return ["hardware_test", "run_test_suite", "validate_hardware"]

    @property
    def test_mode(self) -> str:
        return "MOCK" if isinstance(self._hw_interface, MockHardwareTestInterface) else "REAL_HARDWARE"

    @property
    def has_real_hardware(self) -> bool:
        return self.test_mode == "REAL_HARDWARE"

    async def execute(self, task: AgentTask) -> AgentResult:
        task_type = task.type

        if task_type in ("hardware_test", "run_test_suite", "validate_hardware") and not self.has_real_hardware:
            return self._skipped(task)
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

    def _skipped(self, task: AgentTask) -> AgentResult:
        return AgentResult(
            task_id=task.id,
            status=AgentStatus.SKIPPED,
            outputs={"hardware_result": {
                "status": "skipped",
                "test_mode": "MOCK",
                "reason": "No real hardware interface configured; no hardware test was executed",
            }},
            error_message="Hardware test skipped: no real hardware interface (MOCK)",
        )

    def _define_test_suite(self, architecture: dict, fpga_config: dict) -> list[dict]:
        """Aus der Architektur ableitbare Tests (ohne Projektspezifikation).

        Die UART-Integration fügt dem Top-Level eine Echo-Brücke hinzu; ein
        Modul namens exakt ``uart`` belegt diesen Vertrag, daher ist ein
        Loopback mit festem Vektor überprüfbar. Weitere Funktionen (CPU,
        Decoder ...) brauchen projektspezifische Vektoren.
        """
        module_names = [m.get("name", "") for m in architecture.get("modules", [])]
        if "uart" in module_names:
            return normalize_hardware_tests([{
                "name": "uart_loopback",
                "type": "echo",
                "send": {"ascii": "UART_TEST"},
            }])
        return []

    def load_test_spec(self, task: AgentTask) -> list[dict]:
        """Testvektoren: Task-Input > Architektur > Workspace-Datei, plus abgeleitete Tests."""
        return self._load_project_tests(task) + self._define_test_suite(
            task.inputs.get("architecture") or {}, task.inputs.get("fpga_config") or {},
        )

    def _load_project_tests(self, task: AgentTask) -> list[dict]:
        raw = task.inputs.get("hardware_tests")
        if not raw:
            raw = (task.inputs.get("architecture") or {}).get("hardware_tests")
        if not raw:
            workspace = task.inputs.get("workspace", "")
            for name in self.TEST_SPEC_FILES:
                path = Path(workspace) / "tests" / name if workspace else None
                if path and path.is_file():
                    text = path.read_text(encoding="utf-8")
                    data = json.loads(text) if path.suffix == ".json" else yaml.safe_load(text)
                    raw = data.get("tests", []) if isinstance(data, dict) else data
                    break
        return normalize_hardware_tests(raw or [])

    async def _run_tests(self, tests: list[dict]) -> list[dict]:
        await self._hw_interface.reset()
        results = []
        try:
            for test in tests:
                result = await self._hw_interface.run_test(test)
                results.append({
                    "name": test.get("name", "unknown"),
                    "type": test.get("type", ""),
                    "requirement": test.get("requirement", ""),
                    "passed": bool(result.get("passed", False)),
                    "output": result.get("output", ""),
                    "expected": result.get("expected", ""),
                    "error": result.get("error", ""),
                    "test_mode": self.test_mode,
                })
        finally:
            await self._hw_interface.close()
        return results

    async def _run_hardware_test(self, task: AgentTask) -> AgentResult:
        """Führt die projektspezifische Hardware-Testsuite aus."""
        fpga_config = task.inputs.get("fpga_config", {})

        self.emit_event("HARDWARE_TEST_STARTED", {
            "task_id": task.id,
            "fpga_target": fpga_config.get("target", "unknown"),
            "test_mode": self.test_mode,
        })

        try:
            tests = self.load_test_spec(task)
        except (HardwareTestSpecError, OSError, ValueError, yaml.YAMLError) as exc:
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.FAILED,
                outputs={"hardware_result": {"status": "invalid_spec", "test_mode": self.test_mode}},
                error_message=f"Hardware test specification invalid: {exc}",
                diagnostics=[{"type": "hardware_test_spec", "message": str(exc), "stage": "hardware"}],
            )
        if not tests:
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.BLOCKED,
                outputs={"hardware_result": {"status": "no_tests", "test_mode": self.test_mode}},
                error_message=(
                    "Kein projektspezifischer Hardwaretest definiert "
                    "(architecture.hardware_tests oder tests/hardware_tests.yaml)"
                ),
            )

        try:
            test_results = await self._run_tests(tests)
        except Exception as e:
            logger.exception("Hardware test failed")
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.FAILED,
                error_message=f"Hardware test error: {e}",
                diagnostics=[{"type": "hardware_error", "message": f"hardware test error: {e}", "stage": "hardware"}],
            )

        passed = sum(1 for t in test_results if t["passed"])
        failed = len(test_results) - passed
        overall_passed = failed == 0
        hardware_result = {
            "status": "passed" if overall_passed else "failed",
            "test_mode": self.test_mode,
            "tests": test_results,
            "passed": passed,
            "failed": failed,
            "communication_log": [],
        }

        self.emit_event("HARDWARE_TEST_PASSED" if overall_passed else "HARDWARE_TEST_FAILED", {
            "task_id": task.id,
            "tests_passed": passed,
            "tests_failed": failed,
            "failures": [t for t in test_results if not t["passed"]],
            "test_mode": self.test_mode,
        })

        failures = [t for t in test_results if not t["passed"]]
        return AgentResult(
            task_id=task.id,
            status=AgentStatus.COMPLETED if overall_passed else AgentStatus.FAILED,
            outputs={"hardware_result": hardware_result},
            error_message="" if overall_passed else f"{failed} hardware test(s) failed",
            diagnostics=[{
                "type": "hardware_test_failure",
                "failure_type": "hardware_error",
                "stage": "hardware",
                "message": "hardware test failed: " + "; ".join(
                    f"{t['name']} expected {t['expected']} got {t['output'] or t['error']}"
                    for t in failures
                ),
            }] if failures else [],
        )

    async def _run_test_suite(self, task: AgentTask) -> AgentResult:
        """Führt eine explizit übergebene Test-Suite aus."""
        try:
            tests = normalize_hardware_tests(task.inputs.get("tests", []))
        except HardwareTestSpecError as exc:
            return AgentResult(task_id=task.id, status=AgentStatus.FAILED, error_message=str(exc))
        if not tests:
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.FAILED,
                error_message="No tests provided",
            )

        results = await self._run_tests(tests)
        passed = sum(1 for t in results if t["passed"])
        failed = len(results) - passed
        return AgentResult(
            task_id=task.id,
            status=AgentStatus.COMPLETED if failed == 0 else AgentStatus.FAILED,
            outputs={
                "tests": results,
                "passed": passed,
                "failed": failed,
                "test_mode": self.test_mode,
            },
        )

    async def _validate_hardware(self, task: AgentTask) -> AgentResult:
        """Connectivity-Test mit einem vom Projekt definierten Echo-Vektor."""
        probe = task.inputs.get("probe") or {"name": "connectivity", "type": "echo", "send": "50494e47"}
        try:
            tests = normalize_hardware_tests([probe])
        except HardwareTestSpecError as exc:
            return AgentResult(task_id=task.id, status=AgentStatus.FAILED, error_message=str(exc))
        results = await self._run_tests(tests)
        return AgentResult(
            task_id=task.id,
            status=AgentStatus.COMPLETED if results[0]["passed"] else AgentStatus.FAILED,
            outputs={"connectivity": results[0]["passed"], "test_mode": self.test_mode},
        )
