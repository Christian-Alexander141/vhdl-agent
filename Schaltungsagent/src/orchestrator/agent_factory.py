"""Factories for constructing the production supervisor and its agents."""
from collections.abc import Callable

from src.agents.architecture import ArchitectureAgent
from src.agents.debug import DebugAgent
from src.agents.fpga import FPGAAgent
from src.agents.hardware_test import HardwareTestAgent, UARTHardwareTestInterface
from src.agents.hdl import HDLAgent
from src.agents.supervisor import SupervisorAgent
from src.agents.verification import VerificationAgent
from src.services.project_memory import ProjectMemoryService
from src.services.opencode_task_runner import OpenCodeTaskRunner
from src.services.plan_service import PlanService


def build_supervisor_agent(
    *,
    filesystem_service,
    opencode_service,
    event_publisher,
    name_resolver=None,
    fpga_registry: dict | None = None,
    max_repair_iterations: int = 5,
    plan_timeout_seconds: int = 180,
    max_prompt_bytes: int = 200_000,
    skills_dir: str = ".opencode/skills",
    approval_handler: Callable[[str, str], tuple[bool, str]] | None = None,
    validation_service=None,
    settings=None,
) -> SupervisorAgent:
    """Build the supervisor and all specialized agents with shared services."""
    registry = fpga_registry or {}
    gates = getattr(settings, "gates", None)
    hardware = getattr(settings, "hardware_test", None)
    limits = getattr(settings, "limits", None)
    synthesis = getattr(settings, "synthesis", None)
    task_runner = OpenCodeTaskRunner(
        opencode_service,
        event_publisher=event_publisher,
        max_prompt_bytes=max_prompt_bytes,
    )
    architecture_agent = ArchitectureAgent(
        plan_service=PlanService(
            task_runner,
            timeout_seconds=plan_timeout_seconds,
            name_resolver=name_resolver,
        ),
        event_publisher=event_publisher,
    )
    hdl_agent = HDLAgent(
        opencode_service=opencode_service,
        filesystem_service=filesystem_service,
        event_publisher=event_publisher,
        task_runner=task_runner,
        skills_dir=skills_dir,
    )
    verification_agent = VerificationAgent(
        filesystem_service=filesystem_service,
        opencode_service=opencode_service,
        event_publisher=event_publisher,
        task_runner=task_runner,
        skills_dir=skills_dir,
    )
    debug_agent = DebugAgent(
        event_publisher=event_publisher,
    )
    fpga_agent = FPGAAgent(
        filesystem_service=filesystem_service,
        event_publisher=event_publisher,
        vivado_binary=registry.get("vivado_binary", "vivado"),
        vivado_settings=registry.get("vivado_settings", ""),
        require_timing_closure=getattr(gates, "require_timing_closure", True),
    )
    # Echte Hardwaretests nur mit konfiguriertem UART-Port; sonst Mock, der
    # keine Tests ausführt und nie Erfolg meldet.
    hardware_interface = None
    if getattr(hardware, "uart_port", ""):
        hardware_interface = UARTHardwareTestInterface(
            port=hardware.uart_port,
            baudrate=hardware.baudrate,
            timeout=hardware.timeout_seconds,
        )
    hardware_test_agent = HardwareTestAgent(
        filesystem_service=filesystem_service,
        event_publisher=event_publisher,
        hardware_interface=hardware_interface,
    )
    return SupervisorAgent(
        filesystem_service=filesystem_service,
        event_publisher=event_publisher,
        project_memory=ProjectMemoryService(filesystem_service),
        architecture_agent=architecture_agent,
        hdl_agent=hdl_agent,
        verification_agent=verification_agent,
        debug_agent=debug_agent,
        fpga_agent=fpga_agent,
        hardware_test_agent=hardware_test_agent,
        approval_handler=approval_handler,
        validation_service=validation_service,
        fpga_registry=registry or None,
        config={
            "max_iterations": 20,
            "max_repairs_per_stage": max_repair_iterations,
            "max_simulation_failures": 10,
            "max_hardware_failures": 5,
            "min_module_coverage": getattr(gates, "min_module_coverage", 1.0),
            "enforce_contracts": getattr(gates, "enforce_contracts", True),
            "min_mutation_score": getattr(gates, "min_mutation_score", 0.6),
            "max_mutants": getattr(gates, "max_mutants", 10),
            "max_parallel_workers": getattr(limits, "max_parallel_workers", 2),
            "default_fpga": getattr(synthesis, "default_fpga", "arty_s7_50"),
            "synthesis_enabled": getattr(synthesis, "enabled", True),
            "uart_integration": getattr(hardware, "uart_integration", "auto"),
            "implementation_mode": getattr(getattr(settings, "opencode", None), "implementation_mode", "modular"),
        },
    )
