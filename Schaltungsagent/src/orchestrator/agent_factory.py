"""Factories for constructing the production supervisor and its agents."""

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
    validation_service=None,
    settings=None,
) -> SupervisorAgent:
    """Build the supervisor and all specialized agents with shared services."""
    registry = fpga_registry or {}
    gates = getattr(settings, "gates", None)
    hardware = getattr(settings, "hardware_test", None)
    limits = getattr(settings, "limits", None)
    synthesis = getattr(settings, "synthesis", None)
    policy = getattr(getattr(settings, "opencode", None), "repair_policy", "standard")
    persistent = policy == "persistent"
    vivado = getattr(settings, "vivado", None)
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
            max_attempts=3 if persistent else 1,
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
        # Früher registry.get("vivado_binary", "vivado"): die FPGA-Registry
        # enthält nur Board-Profile, der Pfad aus config.yaml kam nie an und
        # die Synthese scheiterte sofort ("vivado" nicht im PATH).
        vivado_binary=getattr(vivado, "binary", "") or registry.get("vivado_binary", "vivado"),
        vivado_settings=getattr(vivado, "settings_script", "") or registry.get("vivado_settings", ""),
        vivado_timeout=getattr(vivado, "timeout_seconds", 600),
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
        validation_service=validation_service,
        fpga_registry=registry or None,
        model_switcher=_model_switcher(opencode_service, settings),
        config={
            "repair_policy": policy,
            # Persistent: genug Spielraum für alle Eskalationsstufen mehrerer
            # Fehler; das eigentliche Ende setzt die Eskalationsleiter (Mensch
            # mit Zusammenfassung), nicht diese Sicherheitsgrenzen.
            "max_iterations": 150 if persistent else 20,
            "max_repairs_per_stage": max(max_repair_iterations, 40) if persistent else max_repair_iterations,
            "max_simulation_failures": 40 if persistent else 10,
            "max_hardware_failures": 5,
            "min_module_coverage": getattr(gates, "min_module_coverage", 1.0),
            "enforce_contracts": getattr(gates, "enforce_contracts", True),
            "min_mutation_score": getattr(gates, "min_mutation_score", 0.6),
            "max_mutants": getattr(gates, "max_mutants", 10),
            "requirements_review": getattr(gates, "requirements_review", True),
            "max_parallel_workers": getattr(limits, "max_parallel_workers", 2),
            "default_fpga": getattr(synthesis, "default_fpga", "arty_s7_50"),
            "synthesis_enabled": getattr(synthesis, "enabled", True),
            "uart_integration": getattr(hardware, "uart_integration", "auto"),
            "implementation_mode": getattr(getattr(settings, "opencode", None), "implementation_mode", "modular"),
            "runs_dir": getattr(getattr(settings, "workspace", None), "runs_dir", ""),
            "opencode_model": getattr(getattr(settings, "opencode", None), "model", ""),
            "fallback_model": getattr(getattr(settings, "opencode", None), "fallback_model", ""),
            "cleanup_after_success": getattr(getattr(settings, "workspace", None), "cleanup_after_success", False),
        },
    )


def _model_switcher(opencode_service, settings):
    """Schaltet für einen Lauf auf das Fallback-Modell um (True) bzw. zurück (False).

    Nur mit umschaltbarem OpenCode-Dienst (ReconfigurableOpenCodeService); sonst None.
    """
    if settings is None or not hasattr(opencode_service, "reconfigure"):
        return None

    def switch(use_fallback: bool) -> str:
        import copy

        cfg = copy.deepcopy(settings)
        if use_fallback:
            cfg.opencode.model = settings.opencode.fallback_model or settings.opencode.model
        opencode_service.reconfigure(cfg)
        return cfg.opencode.model

    return switch
