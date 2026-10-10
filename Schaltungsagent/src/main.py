import argparse
import json
import sys
import logging
import os

from src.config import load_config, load_fpga_registry
from src.domain.event_bus import EventBus
from src.domain.models import EventType, Event, TaskState
from src.domain.domain_registry import DomainRegistry
from src.services.name_resolver import NameResolver
from src.services.artifact_generator import VHDLArtifactGenerator
from src.services.filesystem_service import LocalFileSystemService
from src.services.opencode_service import ReconfigurableOpenCodeService
from src.infrastructure.validation.ghdl_validator import GHDLValidator
from src.infrastructure.synthesis import VivadoBitstreamService, VivadoFlashService
from src.orchestrator import SupervisorOrchestrator


def setup_logging(settings) -> None:
    logging.basicConfig(
        level=getattr(logging, settings.logging.level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def create_orchestrator(settings) -> SupervisorOrchestrator:
    """Create the SupervisorOrchestrator for the multi-agent workflow."""
    DomainRegistry.discover(settings.domains.search_paths)

    event_bus = EventBus()
    artifact_gen = VHDLArtifactGenerator()
    fs = LocalFileSystemService(
        base_dir=settings.resolve_path(settings.workspace.base_dir),
        cleanup_ttl_hours=settings.workspace.cleanup_ttl_hours,
        max_workspaces=settings.workspace.max_workspaces,
    )
    opencode = ReconfigurableOpenCodeService(settings)

    validator = GHDLValidator(
        ghdl_binary=settings.ghdl.binary,
        timeout_seconds=settings.ghdl.timeout_seconds,
    )
    
    # Bitstream-Service (Vivado)
    fpga_registry = load_fpga_registry()
    bitstream_service = VivadoBitstreamService(
        vivado_binary=settings.vivado.binary,
        settings_script=settings.vivado.settings_script,
        timeout_seconds=settings.vivado.timeout_seconds,
        fpga_registry=fpga_registry,
    )
    
    # Flash-Services erstellen (basierend auf Board-Profil)
    from src.services.flash_service import OpenFPGALoaderFlashService
    
    vivado_flash = VivadoFlashService(
        vivado_binary=settings.vivado.binary,
        settings_script=settings.vivado.settings_script,
        timeout_seconds=settings.flash.timeout_seconds,
    )
    openfpgaloader_flash = OpenFPGALoaderFlashService(
        binary="openFPGALoader",
        timeout_seconds=settings.flash.timeout_seconds,
        default_board="arty_s7_50",
        cable="digilent",
    )
    
    # Default Flash-Service basierend auf konfiguriertem FPGA
    default_fpga = settings.synthesis.default_fpga
    fpga_config = fpga_registry.get(default_fpga)
    if fpga_config and fpga_config.programmer == "openfpgaloader":
        flash_service = openfpgaloader_flash
    else:
        flash_service = vivado_flash
    
    # Flash-Services als Dict für den Orchestrator
    flash_services = {
        "vivado": vivado_flash,
        "openfpgaloader": openfpgaloader_flash,
    }
    
    # Create SupervisorOrchestrator (new production path)
    orchestrator = SupervisorOrchestrator(
        artifact_generator=artifact_gen,
        filesystem_service=fs,
        opencode_service=opencode,
        event_publisher=event_bus,
        validation_service=validator,
        bitstream_service=bitstream_service,
        flash_service=flash_service,
        flash_services=flash_services,
        fpga_registry=fpga_registry,
        max_repair_iterations=settings.opencode.max_repair_iterations,
        name_resolver=NameResolver(),
        plan_timeout_seconds=settings.opencode.plan_timeout_seconds,
        max_prompt_bytes=settings.limits.max_prompt_bytes,
        settings=settings,
    )
    return orchestrator


def cmd_run(args, orchestrator: SupervisorOrchestrator) -> None:
    result = orchestrator.execute(args.request, args.domain)
    print("\n=== Task Result ===")
    print(f"Task ID: {result['task_id']}")
    print(f"Status: {result['status']}")
    print(f"Files: {result['generated_files']}")
    print(f"Iterations: {result['iterations']}")
    if result.get("error_message"):
        print(f"Error: {result['error_message']}")
    print("==================\n")


def cmd_list(args) -> None:
    import os
    from src.config import load_config
    settings = load_config()
    projects_dir = settings.resolve_path(settings.workspace.base_dir)
    if not os.path.isdir(projects_dir):
        print("No projects directory found.")
        return
    for item in sorted(os.listdir(projects_dir)):
        item_path = os.path.join(projects_dir, item)
        if os.path.isdir(item_path) and item.startswith("_"):
            continue
        if os.path.isdir(item_path):
            state_file = os.path.join(item_path, "state.json")
            if os.path.exists(state_file):
                with open(state_file) as f:
                    data = json.load(f)
                print(f"  {item:40} | {data.get('status', '?'):15} | {data.get('request', '')[:50]}")
            else:
                print(f"  {item:40} | NO STATE")


def cmd_show(args) -> None:
    from src.config import load_config
    settings = load_config()
    state_file = f"{settings.resolve_path(settings.workspace.base_dir)}/{args.task_id}/state.json"
    import os
    if not os.path.exists(state_file):
        print(f"Task {args.task_id} not found.")
        return
    with open(state_file) as f:
        data = json.load(f)
    print(json.dumps(data, indent=2, ensure_ascii=False))


def cmd_file(args) -> None:
    from src.config import load_config
    settings = load_config()
    file_path = f"{settings.resolve_path(settings.workspace.base_dir)}/{args.task_id}/{args.filename}"
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return
    with open(file_path) as f:
        print(f.read())


def cmd_serve(args) -> None:
    import uvicorn
    uvicorn.run(
        "src.api_server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


def main():
    settings = load_config()
    setup_logging(settings)

    parser = argparse.ArgumentParser(description="AI Engineer Platform")
    parser.add_argument("--domain", default=settings.domains.default,
                        help=f"Domain (default: {settings.domains.default})")
    parser.add_argument(
        "--test-mode",
        action="store_true",
        help="Use the local OpenCode CLI and never start OpenCode in Docker",
    )
    parser.set_defaults(
        command="serve",
        host=settings.dashboard.host,
        port=settings.dashboard.port,
        reload=False,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    run_parser = subparsers.add_parser("run", help="Execute a new task")
    run_parser.add_argument("request", help="Task description")

    subparsers.add_parser("list", help="List all tasks")

    show_parser = subparsers.add_parser("show", help="Show task details")
    show_parser.add_argument("task_id", help="Task ID")

    file_parser = subparsers.add_parser("file", help="Show a generated file")
    file_parser.add_argument("task_id", help="Task ID")
    file_parser.add_argument("filename", help="File path relative to workspace")

    subparsers.add_parser("discover", help="Discover available domains")

    serve_parser = subparsers.add_parser("serve", help="Start the API server (dashboard)")
    serve_parser.add_argument("--host", default=settings.dashboard.host,
                              help=f"Host (default: {settings.dashboard.host})")
    serve_parser.add_argument("--port", type=int, default=settings.dashboard.port,
                              help=f"Port (default: {settings.dashboard.port})")
    serve_parser.add_argument("--reload", action="store_true", default=False,
                              help="Enable auto-reload")

    args = parser.parse_args()

    if args.test_mode:
        settings.opencode.test_mode = True
        os.environ["VHDL_AGENT_TEST_MODE"] = "1"

    if args.command is None:
        args.command = "serve"
        args.host = settings.dashboard.host
        args.port = settings.dashboard.port
        args.reload = False

    if args.command == "run":
        orch = create_orchestrator(settings)
        cmd_run(args, orch)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "show":
        cmd_show(args)
    elif args.command == "file":
        cmd_file(args)
    elif args.command == "discover":
        DomainRegistry.discover(settings.domains.search_paths)
        domains = DomainRegistry.list_domains()
        print(f"Discovered domains: {', '.join(domains) if domains else 'none'}")
    elif args.command == "serve":
        cmd_serve(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
