import json
import logging
import re
import uuid
from pathlib import Path
from typing import Any

from src.domain.agents import BaseAgent, AgentTask, AgentResult, AgentStatus
from src.domain.models import DesignState, ArchitectureInfo, ModuleInfo
from src.services.deterministic_design import DeterministicDesignService
from src.services.design_fallback import RuleBasedFallback
from src.services.opencode_task_runner import OpenCodeTaskRunner
from src.services.opencode_service import describe_opencode_failure
from src.domain.agents.requirements import task_instruction_suffix as requirements_suffix
from src.domain.exceptions import OpenCodeDeliveryError, WorkflowError
from src.domain.agents.test_plan import _instantiations, format_simulation_vectors
from src.domain.agents.worker_instructions import (
    TESTBENCH_RULES, entity_declarations, ghdl_selfcheck,
)
from src.domain_plugins.vhdl.templates import VHDLTemplates

logger = logging.getLogger(__name__)


class HDLAgent(BaseAgent):
    """Implementiert VHDL-Code basierend auf der Architektur.
    
    Aufgaben:
    - VHDL-Entities und Architectures erstellen
    - Interfaces gemäß Architektur einhalten
    - Synthesizable VHDL erzeugen
    - Coding Guidelines einhalten
    - Bei Architektur-Problemen strukturiert melden
    """

    def __init__(
        self,
        opencode_service,
        filesystem_service,
        event_publisher=None,
        task_runner=None,
        skills_dir: str = ".opencode/skills",
    ):
        super().__init__("HDLAgent", event_publisher)
        self._opencode = opencode_service
        self._fs = filesystem_service
        self._deterministic = DeterministicDesignService()
        self._fallback = RuleBasedFallback(self._deterministic)
        self._task_runner = task_runner or OpenCodeTaskRunner(
            opencode_service, event_publisher=event_publisher
        )
        self._skills_dir = skills_dir

    @property
    def supported_task_types(self) -> list[str]:
        return [
            "implement_hdl", "implement_module", "implement_top", "implement_project",
            "modify_hdl", "fix_hdl", "review_hdl",
        ]

    async def execute(self, task: AgentTask) -> AgentResult:
        task_type = task.type
        
        if task_type == "implement_hdl":
            return await self._implement_hdl(task)
        elif task_type == "implement_module":
            return await self._implement_module(task)
        elif task_type == "implement_project":
            return await self._implement_project(task)
        elif task_type == "implement_top":
            return await self._implement_top(task)
        elif task_type == "modify_hdl":
            return await self._modify_hdl(task)
        elif task_type == "fix_hdl":
            return await self._fix_hdl(task)
        elif task_type == "review_hdl":
            return await self._review_hdl(task)
        else:
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.FAILED,
                error_message=f"Unknown task type: {task_type}",
            )

    async def _implement_hdl(self, task: AgentTask) -> AgentResult:
        """Implementiert VHDL für alle Module der Architektur."""
        architecture = task.inputs.get("architecture", {})
        workspace = task.inputs.get("workspace", "")
        domain = task.inputs.get("domain", "vhdl")
        request = task.inputs.get("request_full", task.inputs.get("request", ""))
        change_request = task.inputs.get("change_request", "")
        analysis = task.inputs.get("analysis", "")
        
        modules = architecture.get("modules", [])
        if not modules:
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.FAILED,
                error_message="No modules in architecture",
            )
        
        # Workspace vorbereiten
        workspace_path = Path(workspace)
        src_dir = workspace_path / "src"
        src_dir.mkdir(parents=True, exist_ok=True)
        
        generated_files = []
        all_errors = []
        
        # Für jedes Modul VHDL generieren
        for module_data in modules:
            module = ModuleInfo(**module_data) if isinstance(module_data, dict) else module_data
            
            try:
                vhdl_code = await self._generate_module_vhdl(
                    module, architecture, domain,
                    request=request, analysis=analysis, workspace=workspace,
                    change_request=change_request,
                )
                
                # Datei schreiben
                file_name = f"{module.name}.vhd"
                file_path = src_dir / file_name
                self._fs.write_file(str(file_path), vhdl_code)
                generated_files.append(f"src/{file_name}")
                
                self.emit_event("MODULE_IMPLEMENTED", {
                    "task_id": task.id,
                    "module": module.name,
                    "file": file_name,
                })
                
            except Exception as e:
                logger.exception(f"Failed to generate module {module.name}")
                all_errors.append({"module": module.name, "error": str(e)})
        
        # Testbenches generieren
        tb_files = await self._generate_testbenches(
            modules, workspace, domain, request=request, analysis=analysis,
            change_request=change_request,
        )
        generated_files.extend(tb_files)
        
        if all_errors:
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.FAILED,
                error_message=f"Failed to generate {len(all_errors)} modules",
                outputs={"files": generated_files, "errors": all_errors},
            )
        
        return AgentResult(
            task_id=task.id,
            status=AgentStatus.COMPLETED,
            outputs={
                "files": generated_files,
                "generated_files": generated_files,
            },
        )

    async def _implement_module(self, task: AgentTask) -> AgentResult:
        """Implementiert VHDL + Testbench für genau ein Modul (Graph-Task)."""
        module_data = task.inputs.get("module", {})
        architecture = task.inputs.get("architecture", {})
        workspace = task.inputs.get("workspace", "")
        domain = task.inputs.get("domain", "vhdl")
        request = task.inputs.get("request_full", task.inputs.get("request", ""))
        analysis = task.inputs.get("analysis", "")
        change_request = task.inputs.get("change_request", "")

        module = ModuleInfo(**module_data) if isinstance(module_data, dict) else module_data

        src_dir = Path(workspace) / "src"
        src_dir.mkdir(parents=True, exist_ok=True)

        try:
            if module.name == "uart":
                vhdl_code = task.inputs.get("uart_template") or VHDLTemplates.render("uart", "vhdl")
            else:
                vhdl_code = await self._generate_module_vhdl(
                    module, architecture, domain, request=request, analysis=analysis,
                    workspace=workspace, change_request=change_request,
                )
            if not vhdl_code:
                return AgentResult(
                    task_id=task.id,
                    status=AgentStatus.FAILED,
                    error_message=f"Module generation produced no code for {module.name}",
                )

            file_name = f"{module.name}.vhd"
            file_path = src_dir / file_name
            self._fs.write_file(str(file_path), vhdl_code)
            files = [f"src/{file_name}"]
            if (
                task.inputs.get("uart_required")
                and module.name == architecture.get("top_module")
            ):
                files = self._integrate_uart_top(workspace, architecture, module.name)

            self.emit_event("MODULE_IMPLEMENTED", {
                "task_id": task.id,
                "module": module.name,
                "file": file_name,
            })

            # Testbench für Leaf-/Top-Module
            if (
                module.type == "combinational"
                or not module.dependencies
                or module.name == architecture.get("top_module")
            ):
                if module.name == "uart":
                    tb_code = task.inputs.get("uart_testbench") or VHDLTemplates.render(
                        "uart", "testbench"
                    )
                else:
                    tb_code = await self._generate_testbench(
                        module, workspace, domain, request=request, analysis=analysis,
                        change_request=change_request,
                    )
                if tb_code and task.inputs.get("uart_required") and module.name == architecture.get("top_module"):
                    tb_code = self._adapt_uart_testbench(tb_code, workspace, module.name)
                if tb_code:
                    tb_dir = Path(workspace) / "tests"
                    tb_dir.mkdir(parents=True, exist_ok=True)
                    tb_name = f"{module.name}_tb.vhd"
                    self._fs.write_file(str(tb_dir / tb_name), tb_code)
                    files.append(f"tests/{tb_name}")

            return AgentResult(
                task_id=task.id,
                status=AgentStatus.COMPLETED,
                outputs={
                    "module": module.name,
                    "files": files,
                    "generated_files": files,
                    "expected_artifacts": [f"src/{file_name}"],
                },
            )
        except Exception as e:
            logger.exception("Failed to implement module %s", module.name)
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.FAILED,
                error_message=f"Module {module.name} implementation failed: {e}",
                diagnostics=[{
                    "type": "implementation_failure",
                    "module": module.name,
                    "message": str(e),
                    **({"failure_type": e.failure_type} if getattr(e, "failure_type", "") else {}),
                    **({"details": e.to_dict()} if hasattr(e, "to_dict") else {}),
                }],
            )

    @staticmethod
    def _module_order(modules: list[ModuleInfo]) -> list[ModuleInfo]:
        """Abhängigkeiten vor ihren Nutzern (für Kompilierreihenfolge und Prompt)."""
        by_name = {m.name: m for m in modules}
        ordered: list[ModuleInfo] = []

        def visit(module: ModuleInfo, seen: set[str]) -> None:
            if module.name in seen:
                return
            seen.add(module.name)
            for dep in module.dependencies:
                if dep in by_name:
                    visit(by_name[dep], seen)
            ordered.append(module)

        seen: set[str] = set()
        for module in modules:
            visit(module, seen)
        return ordered

    async def _implement_project(self, task: AgentTask) -> AgentResult:
        """Implementiert alle Module, Top-Level und Testbench in EINER OpenCode-Sitzung.

        Gegenstück zum modularen TaskGraph: gleicher Kontext für alle Module
        wie bei einem einzelnen OpenCode-Lauf, aber weiterhin mit den Gates,
        der Reparatur und den Hardware-Stufen des MAS.
        """
        architecture = task.inputs.get("architecture", {})
        workspace = task.inputs.get("workspace", "")
        request = task.inputs.get("request_full", task.inputs.get("request", ""))
        change_request = task.inputs.get("change_request", "")
        modules = self._module_order([
            ModuleInfo(**m) if isinstance(m, dict) else m
            for m in architecture.get("modules", [])
        ])
        top = architecture.get("top_module") or (modules[-1].name if modules else "")
        if not modules or not top:
            return AgentResult(task_id=task.id, status=AgentStatus.FAILED,
                               error_message="No modules/top_module for single-session implementation")

        uart_required = bool(task.inputs.get("uart_required"))
        ws = Path(workspace)
        (ws / "src").mkdir(parents=True, exist_ok=True)
        (ws / "tests").mkdir(parents=True, exist_ok=True)
        fixed: list[str] = []
        if uart_required and any(m.name == "uart" for m in modules):
            # Die UART-Vorlage ist vorgegeben und wird nicht vom Modell geschrieben.
            self._fs.write_file(str(ws / "src" / "uart.vhd"),
                                task.inputs.get("uart_template") or VHDLTemplates.render("uart", "vhdl"))
            self._fs.write_file(str(ws / "tests" / "uart_tb.vhd"),
                                task.inputs.get("uart_testbench") or VHDLTemplates.render("uart", "testbench"))
            fixed = ["src/uart.vhd", "tests/uart_tb.vhd"]

        lines = []
        for m in modules:
            if m.name == "uart" and fixed:
                lines.append("- uart: src/uart.vhd ist vorgegeben (nicht ändern).")
                continue
            entry = (
                f"- {m.name}: src/{m.name}.vhd; Rolle: {m.description or '-'}; "
                f"instanziiert: {', '.join(m.dependencies) or '-'}\n"
                f"  Ports (verbindlich): {self._build_port_list(m)}"
            )
            generics = self._build_generic_list(m)
            if generics:
                entry += f"\n  Generics: {generics}"
            vectors = format_simulation_vectors(m.simulation_vectors)
            if vectors:
                entry += "\n  " + vectors.replace("\n", "\n  ")
            lines.append(entry)

        src_files = [f"src/{m.name}.vhd" for m in modules]
        tb_file = f"tests/{top}_tb.vhd"
        instruction = (
            "Implementiere das GESAMTE Projekt in dieser Sitzung. Lies PROMPT.md vollständig; "
            "er ist maßgeblich.\n"
            f"Top-Level: {top}. Module in Abhängigkeitsreihenfolge:\n" + "\n".join(lines) + "\n"
            "Jede Entity heißt exakt wie angegeben und hat genau die angegebenen Ports. "
            f"Schreibe außerdem die Testbench {tb_file} (Entity {top}_tb), die das Top-Level "
            "und damit alle Module prüft; für Module mit eigener Logik zusätzlich "
            "tests/<modul>_tb.vhd.\n"
            f"{TESTBENCH_RULES}\n"
            + ghdl_selfcheck([*src_files, tb_file], "build/ghdl/project", tb_entity=f"{top}_tb")
        )
        if change_request:
            instruction += f"\nZusätzlicher Änderungswunsch:\n{change_request}"

        expected = [f for f in src_files if f not in fixed] + [tb_file]
        delivery = self._task_runner.run(
            workspace=workspace,
            request_full=request,
            stage="implement_project",
            task_instruction=instruction,
            expected_files=expected,
            task_id=f"project_{uuid.uuid4().hex[:8]}",
            skills_dir=self._skills_dir,
        )
        if not delivery.ok:
            error = delivery.error("Projekt (Single-Session)")
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.FAILED,
                error_message=str(error),
                diagnostics=[{
                    "type": "implementation_failure",
                    "message": str(error),
                    **({"failure_type": error.failure_type} if getattr(error, "failure_type", "") else {}),
                }],
            )

        files = sorted({*expected, *fixed, *(
            f"tests/{p.name}" for p in (ws / "tests").glob("*_tb.vhd")
        )})
        if uart_required and top != "uart":
            files = sorted({*files, *self._integrate_uart_top(workspace, architecture, top)})
            tb_path = ws / tb_file
            if tb_path.is_file():
                self._fs.write_file(
                    str(tb_path), self._adapt_uart_testbench(tb_path.read_text(errors="replace"), workspace, top),
                )
        self.emit_event("PROJECT_IMPLEMENTED", {"task_id": task.id, "files": files})
        return AgentResult(
            task_id=task.id,
            status=AgentStatus.COMPLETED,
            outputs={"files": files, "generated_files": files, "expected_artifacts": expected},
        )

    async def _implement_top(self, task: AgentTask) -> AgentResult:
        """Erzeugt den Top-Level-Wrapper, der alle Module instanziiert."""
        architecture = task.inputs.get("architecture", {})
        workspace = task.inputs.get("workspace", "")
        request = task.inputs.get("request_full", task.inputs.get("request", ""))
        change_request = task.inputs.get("change_request", "")
        analysis = task.inputs.get("analysis", "")
        modules = architecture.get("modules", [])
        non_uart_modules = [
            module for module in modules
            if (module.get("name", "") if isinstance(module, dict) else module.name).lower() != "uart"
        ]
        top_module = architecture.get("top_module") or (
            non_uart_modules[-1].get("name") if non_uart_modules and isinstance(non_uart_modules[-1], dict)
            else getattr(non_uart_modules[-1], "name", "") if non_uart_modules else ""
        )

        if not modules or not top_module:
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.FAILED,
                error_message="No modules/top_module for integration",
            )

        if any(
            (module.get("name", "") if isinstance(module, dict) else module.name) == "uart"
            for module in modules
        ):
            try:
                files = self._integrate_uart_top(workspace, architecture, top_module)
            except (OSError, ValueError) as exc:
                return AgentResult(
                    task_id=task.id,
                    status=AgentStatus.FAILED,
                    error_message=f"UART top-level integration failed: {exc}",
                )
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.COMPLETED,
                outputs={
                    "top_module": top_module,
                    "files": files,
                    "generated_files": files,
                    "expected_artifacts": files,
                },
            )

        file_name = f"{top_module}.vhd"
        relative_path = f"src/{file_name}"
        request_full = task.inputs.get("request_full", request)
        instruction = (
            f"Schreibe das Top-Level direkt in {relative_path}.\n"
            f"Top-Entity: {top_module}\nArchitektur/Manifest: {architecture}\n"
            "Lies PROMPT.md vollständig. Verbinde alle Module anhand ihrer Interfaces, "
            "erzeuge eine gültige VHDL-2008 Entity und Architecture und schreibe sie "
            "direkt in die Zieldatei. stdout ist nur ein Log."
        )
        module_names = [
            m.get("name", "") if isinstance(m, dict) else m.name
            for m in modules
        ]
        declarations = entity_declarations(workspace, [n for n in module_names if n != top_module])
        if declarations:
            instruction += (
                "\nTatsächliche Entities der bereits implementierten Module (verbindlich "
                f"für die Instanziierung, Ports exakt so verwenden):\n{declarations}"
            )
        src_files = [
            f"src/{n}.vhd" for n in module_names
            if n != top_module and (Path(workspace) / "src" / f"{n}.vhd").is_file()
        ]
        instruction += "\n" + ghdl_selfcheck([*src_files, relative_path], "build/ghdl/top")
        if change_request:
            instruction += f"\nZusätzlicher Änderungswunsch:\n{change_request}"
        delivery = self._task_runner.run(
            workspace=workspace,
            request_full=request_full,
            stage="implement_top",
            task_instruction=instruction,
            expected_files=[relative_path],
            task_id=f"top_{uuid.uuid4().hex[:8]}",
            skills_dir=self._skills_dir,
        )
        wrapper = delivery.files.get(relative_path, "") if delivery.ok else ""
        if not wrapper:
            plan = task.inputs.get("plan_manifest", architecture)
            wrapper = self._fallback.top_vhdl(request_full, plan) or ""
            if wrapper:
                self.emit_event("FALLBACK_USED", {
                    "stage": "implement_top",
                    "module": top_module,
                    "reason": delivery.reason,
                })
        if not wrapper:
            error = delivery.error(f"Top-Level '{top_module}'")
            logger.error("%s", error)
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.FAILED,
                error_message=str(error),
                diagnostics=[{
                    "type": "implementation_failure",
                    "module": top_module,
                    "message": str(error),
                    "details": error.to_dict(),
                }],
            )
        self._fs.write_file(str(Path(workspace) / relative_path), wrapper)

        self.emit_event("TOP_INTEGRATED", {
            "task_id": task.id,
            "top_module": top_module,
            "file": file_name,
            "module_count": len(modules),
        })

        return AgentResult(
            task_id=task.id,
            status=AgentStatus.COMPLETED,
            outputs={
                "top_module": top_module,
                "files": [f"src/{file_name}"],
                "generated_files": [f"src/{file_name}"],
                "expected_artifacts": [f"src/{file_name}"],
            },
        )

    def _integrate_uart_top(self, workspace: str, architecture: dict, top_module: str) -> list[str]:
        """Add an idempotent UART echo bridge without replacing the design entity."""
        import re

        if not top_module or top_module.lower() == "uart":
            raise ValueError("UART cannot be used as the design top module")
        top_path = Path(workspace) / "src" / f"{top_module}.vhd"
        if not top_path.is_file():
            raise ValueError(f"Original top-level source not found: {top_path.name}")
        code = top_path.read_text()
        entity_end = re.compile(
            rf"entity\s+{re.escape(top_module)}\s+is.*?end\s+(?:(?:entity\s+)?{re.escape(top_module)}|entity)\s*;",
            re.IGNORECASE | re.DOTALL,
        )
        entity_match = entity_end.search(code)
        if not entity_match:
            raise ValueError(f"Could not parse entity {top_module}")
        entity = entity_match.group(0)
        port_start = re.search(r"\bport\s*\(", entity, re.IGNORECASE)
        port_open = entity.find("(", port_start.start()) if port_start else -1
        port_close = -1
        if port_open >= 0:
            depth = 0
            for index in range(port_open, len(entity)):
                if entity[index] == "(":
                    depth += 1
                elif entity[index] == ")":
                    depth -= 1
                    if depth == 0:
                        port_close = index
                        break
        port_text = entity[port_open + 1:port_close] if port_close >= 0 else ""
        port_declarations = [
            item.strip() for item in re.sub(r"--[^\n]*", "", port_text).split(";") if item.strip()
        ]
        ports: dict[str, tuple[str, str, str]] = {}
        for declaration in port_declarations:
            parsed = re.match(
                r"([\w\s,]+?)\s*:\s*(in|out|inout)\s+(.+)",
                declaration, re.IGNORECASE | re.DOTALL,
            )
            if parsed:
                for port_name in parsed.group(1).split(","):
                    actual_name = port_name.strip()
                    ports[actual_name.lower()] = (
                        actual_name, parsed.group(2).lower(), parsed.group(3).strip().lower()
                    )

        additions = []
        for name, direction in (("uart_rx", "in"), ("uart_tx", "out")):
            existing = ports.get(name)
            if existing and (
                existing[1] != direction or "std_logic" not in existing[2]
                or "vector" in existing[2]
            ):
                raise ValueError(f"Existing {name} must be scalar std_logic {direction}")
            if not existing:
                additions.append(f"{name} : {direction} std_logic")

        clock = next(
            (ports[name][0] for name in ("clk", "clock", "sys_clk", "clk_in")
             if name in ports and ports[name][1] == "in"),
            "",
        )
        reset = next(
            (ports[name][0] for name in ("rst", "reset", "reset_n", "rst_n")
             if name in ports and ports[name][1] == "in"),
            "",
        )
        if not clock:
            clock = "clk"
            additions.append("clk : in std_logic")
        if not reset:
            reset = "rst"
            additions.append("rst : in std_logic")

        combined_ports = port_text.strip()
        if additions and combined_ports and not combined_ports.endswith(";"):
            combined_ports += ";"
        if additions:
            combined_ports += ("\n        " if combined_ports else "") + ";\n        ".join(additions)
        if port_close >= 0:
            entity = entity[:port_open + 1] + combined_ports + entity[port_close:]
        else:
            entity = re.sub(
                rf"(end\s+(?:entity\s+)?{re.escape(top_module)}\s*;)",
                f"port (\n        {combined_ports}\n    );\n\\1",
                entity, count=1, flags=re.IGNORECASE,
            )
        code = code[:entity_match.start()] + entity + code[entity_match.end():]

        uart_module = next(
            item for item in architecture.get("modules", [])
            if (item.get("name", "") if isinstance(item, dict) else item.name) == "uart"
        )
        params = uart_module.get("parameters", {}) if isinstance(uart_module, dict) else uart_module.parameters
        reset_expr = f"not {reset}" if reset.lower() in {"reset_n", "rst_n"} else reset
        architecture_pattern = re.compile(
            rf"(architecture\s+\w+\s+of\s+{re.escape(top_module)}\s+is)(.*?)(\bbegin\b)",
            re.IGNORECASE | re.DOTALL,
        )
        architecture_match = architecture_pattern.search(code)
        if not architecture_match:
            raise ValueError(f"Could not find architecture body for {top_module}")
        declarations = architecture_match.group(2)
        if "uart_rx_data" not in declarations.lower():
            declarations += "\n    signal uart_rx_data : std_logic_vector(7 downto 0);\n    signal uart_rx_valid : std_logic;\n"
        code = (
            code[:architecture_match.start()]
            + architecture_match.group(1) + declarations + architecture_match.group(3)
            + code[architecture_match.end():]
        )
        if "uart_bridge:" not in code.lower():
            insertion = architecture_match.start() + len(architecture_match.group(1) + declarations + architecture_match.group(3))
            bridge = (
                "\n    uart_bridge: entity work.uart\n"
                f"        generic map (CLOCK_FREQ_HZ => {params.get('CLOCK_FREQ_HZ', 100_000_000)}, "
                f"BAUD_RATE => {params.get('BAUD_RATE', 115_200)})\n"
                "        port map (\n"
                f"            clk => {clock}, rst => {reset_expr},\n"
                "            uart_rx => uart_rx, uart_tx => uart_tx,\n"
                "            rx_data => uart_rx_data, rx_valid => uart_rx_valid,\n"
                "            tx_data => uart_rx_data, tx_valid => uart_rx_valid, tx_ready => open\n"
                "        );\n"
            )
            code = code[:insertion] + bridge + code[insertion:]
        self._fs.write_file(str(top_path), code)
        return [f"src/{top_module}.vhd"]

    def _adapt_uart_testbench(self, testbench: str, workspace: str, top_module: str) -> str:
        """Connect added UART and clock/reset ports in an existing top-level testbench."""
        import re

        top_code = (Path(workspace) / "src" / f"{top_module}.vhd").read_text()
        entity = re.search(
            rf"entity\s+{re.escape(top_module)}\s+is.*?end\s+(?:(?:entity\s+)?{re.escape(top_module)}|entity)\s*;",
            top_code, re.IGNORECASE | re.DOTALL,
        )
        if not entity:
            return testbench
        port_start = re.search(r"\bport\s*\(", entity.group(0), re.IGNORECASE)
        if not port_start:
            return testbench
        entity_text = entity.group(0)
        opening = entity_text.find("(", port_start.start())
        depth = 0
        closing = -1
        for index in range(opening, len(entity_text)):
            if entity_text[index] == "(":
                depth += 1
            elif entity_text[index] == ")":
                depth -= 1
                if depth == 0:
                    closing = index
                    break
        if closing < 0:
            return testbench

        port_text = re.sub(r"--[^\n]*", "", entity_text[opening + 1:closing])
        top_ports = []
        for declaration in port_text.split(";"):
            parsed = re.match(
                r"([\w\s,]+?)\s*:\s*(in|out|inout)\s+(.+)",
                declaration.strip(), re.IGNORECASE | re.DOTALL,
            )
            if parsed:
                for formal in parsed.group(1).split(","):
                    name = formal.strip()
                    if name.lower() in {"uart_rx", "uart_tx", "clk", "rst", "clock", "reset"}:
                        top_ports.append((name, parsed.group(2).lower()))

        port_map = re.search(r"port\s+map\s*\(", testbench, re.IGNORECASE)
        if not port_map:
            return testbench
        map_open = testbench.find("(", port_map.start())
        depth = 0
        map_close = -1
        for index in range(map_open, len(testbench)):
            if testbench[index] == "(":
                depth += 1
            elif testbench[index] == ")":
                depth -= 1
                if depth == 0:
                    map_close = index
                    break
        if map_close < 0:
            return testbench

        mapped_text = testbench[map_open + 1:map_close]
        mapped = {name.lower() for name in re.findall(r"\b([\w]+)\s*=>", mapped_text)}
        new_maps = [(name, direction) for name, direction in top_ports if name.lower() not in mapped]
        if not new_maps:
            return testbench

        declarations = []
        for name, direction in new_maps:
            if not re.search(rf"\bsignal\s+{re.escape(name)}\s*:", testbench, re.IGNORECASE):
                initial = " := '1'" if name.lower() == "uart_rx" else " := '0'" if name.lower() in {"clk", "clock", "rst", "reset"} else ""
                declarations.append(f"    signal {name} : std_logic{initial};")
        if declarations:
            architecture = re.search(r"architecture\s+\w+\s+of\s+\w+\s+is.*?\bbegin\b", testbench, re.IGNORECASE | re.DOTALL)
            if architecture:
                insertion = architecture.end() - len("begin")
                testbench = (
                    testbench[:insertion] + "\n" + "\n".join(declarations)
                    + "\n" + testbench[insertion:]
                )
                port_map = re.search(r"port\s+map\s*\(", testbench, re.IGNORECASE)
                map_open = testbench.find("(", port_map.start())
                depth = 0
                for index in range(map_open, len(testbench)):
                    if testbench[index] == "(":
                        depth += 1
                    elif testbench[index] == ")":
                        depth -= 1
                        if depth == 0:
                            map_close = index
                            break
                mapped_text = testbench[map_open + 1:map_close]
        additions = ",\n            ".join(f"{name} => {name}" for name, _ in new_maps)
        separator = ",\n            " if mapped_text.strip() else "\n            "
        return testbench[:map_close] + separator + additions + testbench[map_close:]

    async def _generate_module_vhdl(
        self, module: ModuleInfo, architecture: dict, domain: str,
        request: str = "", analysis: str = "", workspace: str = "",
        change_request: str = "",
    ) -> str:
        """Ask OpenCode to write one module; use a safe template only on delivery failure."""
        ports = self._build_port_list(module)
        generics = self._build_generic_list(module)
        target_file = f"src/{module.name}.vhd"
        request_full = request
        instruction = (
            f"Schreibe die VHDL-Implementierung direkt in {target_file}.\n"
            f"Modul: {module.model_dump()}\nInterface: {ports}\nGenerics: {generics}\n"
            f"Architektur: clock_domain={architecture.get('clock_domain', 'clk')}; "
            f"reset={architecture.get('reset_concept', 'async_active_high')}\n"
            "Lies den vollständigen Originalprompt. Er ist maßgeblich und darf nicht "
            "gekürzt oder ersetzt werden. Erzeuge VHDL-2008; die Entity muss exakt "
            f"{module.name} heißen und genau die Ports aus 'Interface' haben (keine "
            "zusätzlichen, keine umbenannten). Schreibe die Datei selbst, stdout ist nur ein Log."
        )
        instruction += self._dependency_context(module, workspace)
        dep_files = [f"src/{dep}.vhd" for dep in module.dependencies if (Path(workspace) / "src" / f"{dep}.vhd").is_file()]
        instruction += "\n" + ghdl_selfcheck(
            [*dep_files, target_file], f"build/ghdl/{module.name}",
        )
        if change_request:
            instruction += f"\nZusätzlicher Änderungswunsch:\n{change_request}"
        delivery = self._task_runner.run(
            workspace=workspace,
            request_full=request_full,
            stage="implement_module",
            task_instruction=instruction,
            expected_files=[target_file],
            task_id=f"{module.name}_{uuid.uuid4().hex[:8]}",
            skills_dir=self._skills_dir,
        )
        vhdl_code = delivery.files.get(target_file, "") if delivery.ok else ""
        if not vhdl_code:
            vhdl_code = self._fallback.module_vhdl(request_full, module.name) or ""
            if vhdl_code and not self._matches_contract(vhdl_code, module):
                # Eine Vorlage mit anderem Interface erzeugt nur Folgefehler
                # in späteren Gates; dann lieber den echten Lieferfehler melden.
                logger.warning("Fallback template for %s does not match its port contract; discarded", module.name)
                vhdl_code = ""
            if vhdl_code:
                self.emit_event("FALLBACK_USED", {
                    "stage": "implement_module",
                    "module": module.name,
                    "reason": delivery.reason,
                })
        if not vhdl_code:
            error = delivery.error(f"Modul '{module.name}'")
            if not error.hint:
                error.hint = "Für dieses Modul gibt es keine sichere Vorlage als Ersatz."
            raise error
        return self._clean_vhdl_code(vhdl_code)

    @staticmethod
    def _matches_contract(vhdl_code: str, module: ModuleInfo) -> bool:
        """Entity-Name stimmt und alle Contract-Ports kommen in der Entity vor."""
        match = re.search(
            rf"\bentity\s+{re.escape(module.name)}\s+is\b(.*?)\bend\b",
            vhdl_code, re.IGNORECASE | re.DOTALL,
        )
        if not match:
            return False
        declared = match.group(1).lower()
        return all(re.search(rf"\b{re.escape(p.lower())}\b", declared) for p in (module.ports or {}))

    @staticmethod
    def _compile_order(module: ModuleInfo, workspace: str) -> list[str]:
        """Quelldateien des Moduls und seiner (transitiven) Abhängigkeiten, Abhängigkeiten zuerst."""
        src = Path(workspace) / "src"
        order: list[str] = []

        def visit(name: str, seen: set[str]) -> None:
            if name in seen:
                return
            seen.add(name)
            path = src / f"{name}.vhd"
            if not path.is_file():
                return
            for child in sorted(_instantiations(path.read_text(errors="replace"))):
                if (src / f"{child}.vhd").is_file():
                    visit(child, seen)
            rel = f"src/{name}.vhd"
            if rel not in order:
                order.append(rel)

        visit(module.name, set())
        return order

    @staticmethod
    def _dependency_context(module: ModuleInfo, workspace: str) -> str:
        """Tatsächliche Entities der Abhängigkeiten statt nur Manifest-Einträge.

        Der TaskGraph implementiert Abhängigkeiten vorher; ihre Dateien
        existieren also bereits und sind die verbindliche Instanziierungs-
        vorlage (ein einzelner OpenCode-Lauf sieht sie ebenfalls).
        """
        if not module.dependencies or not workspace:
            return ""
        declarations = entity_declarations(workspace, list(module.dependencies))
        if not declarations:
            return ""
        return (
            f"\nDieses Modul instanziiert: {', '.join(module.dependencies)}. Tatsächliche "
            "Entities (verbindlich, Ports exakt so verwenden, Dateien nicht ändern):\n"
            f"{declarations}"
        )

    def _build_port_list(self, module: ModuleInfo) -> str:
        """Erstellt Port-Liste als String.

        Ein typisierter Contract (``module.ports``) wird unverändert
        übernommen. Früher kamen für sequenzielle Module immer ``clk``/``rst``
        dazu – auch wenn der Contract z. B. ``clk_i``/``reset_n`` vorsah; der
        Worker bekam damit zwei widersprüchliche Interfaces.
        """
        if module.ports:
            return "; ".join(
                f"{name} : {str((spec or {}).get('direction', 'in')).lower()} "
                f"{(spec or {}).get('type') or 'std_logic'}"
                for name, spec in module.ports.items()
            )
        ports = []
        
        width = module.parameters.get("width", None)
        if width is not None and isinstance(width, int):
            vector_type = f"std_logic_vector({width - 1} downto 0)"
        else:
            vector_type = "std_logic_vector"
        
        # Clock/Reset nur ergänzen, wenn das Modul noch keinen Takteingang nennt.
        has_clock = any("clk" in n.lower() or "clock" in n.lower() for n in module.inputs)
        injected = module.type in ["sequential", "fsm"] and not has_clock
        if injected:
            ports.append("clk : in std_logic")
            ports.append("rst : in std_logic")
        
        # Typisierter Contract (module.ports) hat Vorrang vor geratenen Typen.
        contract = {name.lower(): spec for name, spec in (module.ports or {}).items()}

        def port_type(name: str) -> str:
            spec = contract.get(name.lower())
            return spec.get("type", vector_type) if isinstance(spec, dict) else vector_type

        for inp in module.inputs:
            if not (injected and inp in ["clk", "rst"]):
                ports.append(f"{inp} : in {port_type(inp)}")
        
        # Outputs
        for out in module.outputs:
            ports.append(f"{out} : out {port_type(out)}")
        
        return "; ".join(ports)

    def _build_generic_list(self, module: ModuleInfo) -> str:
        """Erstellt Generic-Liste als String."""
        generics = []
        for name, value in module.parameters.items():
            # bool vor int prüfen (bool ist eine int-Unterklasse); "positive"
            # schloss 0 aus, "string" machte z. B. PARITY="none" zum String-Generic.
            if isinstance(value, bool):
                generics.append(f"{name} : boolean := {str(value).lower()}")
            elif isinstance(value, int):
                generics.append(f"{name} : integer := {value}")
            elif isinstance(value, float):
                generics.append(f"{name} : real := {value}")
            else:
                generics.append(f"{name} : string := \"{value}\"")
        return "; ".join(generics)

    def _clean_vhdl_code(self, code: str) -> str:
        """Bereinigt VHDL-Code von Markdown-Artefakten."""
        import re
        
        # Code-Block Marker entfernen
        code = re.sub(r'^```vhdl\s*', '', code, flags=re.MULTILINE)
        code = re.sub(r'^```\s*', '', code, flags=re.MULTILINE)
        code = code.strip()
        
        return code

    async def _generate_testbenches(
        self, modules: list, workspace: str, domain: str,
        request: str = "", analysis: str = "", change_request: str = "",
    ) -> list[str]:
        """Generiert Testbenches für alle Module."""
        workspace_path = Path(workspace)
        tb_dir = workspace_path / "tests"
        tb_dir.mkdir(parents=True, exist_ok=True)
        
        tb_files = []
        
        for module_data in modules:
            module = ModuleInfo(**module_data) if isinstance(module_data, dict) else module_data
            
            # Nur für Leaf-Module oder Haupt-Module Testbenches
            if module.type == "combinational" or not module.dependencies:
                try:
                    tb_code = await self._generate_testbench(
                        module, workspace, domain,
                        request=request, analysis=analysis,
                        change_request=change_request,
                    )

                    if not tb_code:
                        continue
                    
                    file_name = f"{module.name}_tb.vhd"
                    file_path = tb_dir / file_name
                    self._fs.write_file(str(file_path), tb_code)
                    tb_files.append(f"tests/{file_name}")
                    
                except Exception as e:
                    logger.warning(f"Failed to generate testbench for {module.name}: {e}")
        
        return tb_files

    async def _generate_testbench(
        self, module: ModuleInfo, workspace: str, domain: str,
        request: str = "", analysis: str = "", change_request: str = "",
    ) -> str:
        """Ask OpenCode to write a testbench file and use only a safe fallback."""
        ports = self._build_port_list(module)
        target_file = f"tests/{module.name}_tb.vhd"
        instruction = (
            f"Schreibe die VHDL-2008-Testbench direkt in {target_file}.\n"
            f"DUT-Entity: {module.name}\nTyp: {module.type}\nPorts: {ports}\n"
            "Lies PROMPT.md vollständig und prüfe alle darin beschriebenen Funktionen. "
            "Die Testbench muss die Entity exakt als <DUT>_tb benennen, Assertions "
            "enthalten und mit GHDL ausführbar sein. Schreibe das Ergebnis in die Datei; "
            "stdout ist nur ein Log."
        )
        instruction += f"\n{TESTBENCH_RULES}"
        vector_block = format_simulation_vectors(module.simulation_vectors)
        if vector_block:
            instruction += f"\n{vector_block}"
        src_files = self._compile_order(module, workspace)
        instruction += "\n" + ghdl_selfcheck(
            [*src_files, target_file], f"build/ghdl/{module.name}_tb", tb_entity=f"{module.name}_tb",
        )
        if change_request:
            instruction += f"\nZusätzlicher Änderungswunsch:\n{change_request}"
        delivery = self._task_runner.run(
            workspace=workspace,
            request_full=request,
            stage="implement_testbench",
            task_instruction=instruction,
            expected_files=[target_file],
            task_id=f"{module.name}_{uuid.uuid4().hex[:8]}",
            skills_dir=self._skills_dir,
        )
        testbench = delivery.files.get(target_file, "") if delivery.ok else ""
        if not testbench:
            # Kein Abbruch: fehlende Testbenches fängt das Coverage-Gate ab.
            logger.warning("%s", delivery.error(f"Testbench für '{module.name}'"))
            testbench = self._fallback.testbench_vhdl(request, module.name) or ""
            if testbench:
                self.emit_event("FALLBACK_USED", {
                    "stage": "implement_testbench",
                    "module": module.name,
                    "reason": delivery.reason,
                })
        return self._clean_vhdl_code(testbench) if testbench else ""

    def _opencode_call_failed(
        self, task: AgentTask, subject: str, exc: WorkflowError, module: str = "",
    ) -> AgentResult:
        """OpenCode-Aufruf scheiterte (Zeitlimit, Docker, Programm fehlt).

        Ergebnis statt Ausnahme: Der Supervisor kann den Fehler klassifizieren
        und weiterleiten, statt dass der ganze Workflow abbricht.
        """
        exc.message = f"{subject}: {exc.message}"
        logger.error("OPENCODE_FAILED %s", exc)
        self.emit_event("OPENCODE_FAILED", {
            "task_id": task.id,
            "module": module,
            "error": str(exc),
        })
        return AgentResult(
            task_id=task.id,
            status=AgentStatus.FAILED,
            error_message=str(exc),
            diagnostics=[{
                "type": "opencode_failure",
                "message": str(exc),
                "modules": [module] if module else [],
                **({"failure_type": exc.failure_type} if exc.failure_type else {}),
                "details": exc.to_dict(),
            }],
        )

    async def _modify_hdl(self, task: AgentTask) -> AgentResult:
        """Modifiziert existierenden VHDL-Code."""
        workspace = task.inputs.get("workspace", "")
        file_path = task.inputs.get("file_path", "")
        instruction = task.inputs.get("instruction", "")
        
        if not file_path:
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.FAILED,
                error_message="No file path provided",
            )
        
        full_path = Path(workspace) / file_path
        if not self._fs.file_exists(str(full_path)):
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.FAILED,
                error_message=f"File not found: {file_path}",
            )
        
        # Aktuellen Code lesen
        current_code = self._fs.read_file(str(full_path))
        
        # Modifikation via OpenCode
        try:
            result = self._opencode.execute(
                workspace,
                f"Modifiziere {file_path} gemäß: {instruction}\n\nAktueller Code:\n{current_code}",
            )
        except WorkflowError as exc:
            return self._opencode_call_failed(task, f"Änderung an {file_path}", exc)
        
        if result.success:
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.COMPLETED,
                outputs={"modified_file": file_path},
            )
        else:
            cause, hint = describe_opencode_failure(result.returncode, result.stdout, result.stderr)
            error = OpenCodeDeliveryError(
                f"Änderung an {file_path} fehlgeschlagen",
                cause=cause, hint=hint,
                context={"Exit-Code": result.returncode, "stderr (Ende)": (result.stderr or "")[-2000:]},
            )
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.FAILED,
                error_message=str(error),
            )

    @staticmethod
    def _repair_history_block(workspace: str, error_info: dict) -> str:
        """Bisherige Versuche für denselben Fehler und die Notizen des letzten
        Versuchs: ohne sie wiederholte jede Stufe dieselben Ansätze."""
        lines = []
        for attempt in error_info.get("previous_attempts") or []:
            lines.append(
                f"- attempt {attempt.get('attempt')}: {attempt.get('action')} -> {attempt.get('outcome', 'unknown outcome')}"
            )
        notes_path = Path(workspace) / "reports" / "repair_notes.md"
        # Notizen nur, wenn sie zu diesem Fehler gehören (vorheriger Versuch).
        notes = notes_path.read_text(errors="replace")[:3000] if lines and notes_path.is_file() else ""
        if not lines and not notes:
            return ""
        block = "\nPREVIOUS ATTEMPTS FOR THIS FAILURE (do not repeat what did not work):\n" + "\n".join(lines) + "\n"
        if notes:
            block += f"\nNotes of the previous attempt (reports/repair_notes.md):\n{notes}\n"
        return block

    @staticmethod
    def _toolchain_block(error_info: dict) -> str:
        """Synthese-/Flash-Fehler: Vivado-Kontext statt reinem GHDL-Auftrag."""
        if error_info.get("stage") not in ("synthesis", "flash") and error_info.get("origin") != "toolchain":
            return ""
        return (
            "\nTOOLCHAIN CONTEXT: This failure comes from Vivado (synthesis/implementation/bitstream/flash), "
            "not from GHDL. You may change src/*.vhd and constraints/*.xdc. Do NOT run Vivado or program "
            "the board yourself (that takes minutes and the pipeline does it after your change); keep the GHDL "
            "checks below green. If the cause is outside the project files (tool installation, cable, board), "
            "change nothing and explain it in reports/repair_notes.md.\n"
        )

    def _repair_verification(self, workspace: str, architecture: dict, failed_module: str) -> str:
        """GHDL-Befehle für die Reparatur: alle Quellen, dann jede Testbench simulieren."""
        modules = self._module_order([
            ModuleInfo(**m) if isinstance(m, dict) else m
            for m in (architecture or {}).get("modules", [])
        ])
        src = [f"src/{m.name}.vhd" for m in modules if (Path(workspace) / "src" / f"{m.name}.vhd").is_file()]
        tbs = sorted((Path(workspace) / "tests").glob("*_tb.vhd")) if workspace else []
        workdir = f"build/ghdl/repair_{failed_module or 'all'}"
        if not tbs:
            return ghdl_selfcheck(src, workdir)
        parts = [ghdl_selfcheck([*src, *(f"tests/{tb.name}" for tb in tbs)], workdir, tb_entity=tbs[0].stem)]
        for tb in tbs[1:]:
            parts.append(
                f"  ghdl -r --std=08 --workdir={workdir} {tb.stem} --stop-time=1ms --assert-level=error"
            )
        return "\n".join(parts) + "\n" + TESTBENCH_RULES

    async def _fix_hdl(self, task: AgentTask) -> AgentResult:
        """Repariert VHDL-Code basierend auf Fehlerinformationen.

        PRODUCTION PATH: Uses OpenCode to patch existing VHDL files.
        Does NOT regenerate all modules from scratch.
        """
        workspace = task.inputs.get("workspace", "")
        error_info = task.inputs.get("error_info", {})
        failed_module = task.inputs.get("failed_module", "")
        architecture = task.inputs.get("architecture", {})
        diagnosis = task.inputs.get("diagnosis", {})
        affected_files = task.inputs.get("affected_files", [])
        original_requirement = task.inputs.get("original_requirement", "")

        # Build comprehensive context for OpenCode
        from src.services.opencode_context import OpenCodeContextBuilder
        context_builder = OpenCodeContextBuilder(self._fs)

        context = context_builder.build_context(
            workspace=workspace,
            task={
                "id": task.id,
                "type": "fix_hdl",
                "project_id": task.project_id,
                "inputs": task.inputs,
                "description": f"Repair VHDL code for module {failed_module}",
            },
            architecture=architecture,
            previous_results=[{
                "passed": False,
                "stage": "simulation",
                "error": error_info.get("message", ""),
                "details": error_info.get("details", {}),
            }],
        )

        verification = self._repair_verification(workspace, architecture, failed_module)
        history = self._repair_history_block(workspace, error_info)
        toolchain = self._toolchain_block(error_info)
        instruction = f"""{context}

=====================================================================
REPAIR TASK: Fix VHDL code for module '{failed_module}'
=====================================================================

ORIGINAL REQUIREMENT:
{original_requirement}

ARCHITECTURE:
{json.dumps(architecture, indent=2) if architecture else 'Not available'}

FAILED MODULE: {failed_module}
AFFECTED FILES: {', '.join(affected_files) if affected_files else 'auto-detect'}

ERROR (key lines from the failing stage '{error_info.get('stage', '')}'):
{error_info.get('message', 'Unknown error')}
{history}{toolchain}
DEBUG DIAGNOSIS:
- failure_type: {diagnosis.get('failure_type', 'unknown')}
- suspected_modules: {diagnosis.get('suspected_modules', [])}
- evidence: {diagnosis.get('evidence', [])}
- recommended_action: {diagnosis.get('recommended_action', 'Investigate error')}

ACCEPTANCE CRITERIA:
- GHDL compilation succeeds (analyze + elaborate)
- GHDL simulation passes (no assertion failures)
- Preserve working modules
- Do not rewrite unrelated files
- Fix the root cause of the reported verification failure
- Run the relevant verification after the modification

INSTRUCTIONS:
1. Read the affected VHDL files listed above
2. Analyze the GHDL error and the debug diagnosis
3. Fix ONLY the root cause in the identified file(s)
4. Preserve all working code - do NOT rewrite unrelated files
5. Verify with exactly the commands below (same checks as the pipeline's validator)
6. Stop when they pass (or at the round limit below)

VERIFICATION:
{verification}

IMPORTANT:
- This is a REPAIR, not a rewrite. Patch the existing code.
- Preserve working modules. Do not rewrite unrelated files.
- Fix the root cause of the reported verification failure.
- Run the relevant verification after the modification.
- If the checks still fail after about five fix-and-verify rounds, stop and write your analysis
  (suspected cause, what you tried) to reports/repair_notes.md instead of looping until the time limit.

GENERATED FILES (do not edit): tests/*_model_tb.vhd is generated from model/reference_model.py and
rewritten before every check, so edits there are lost. If such a generated check or the reference model
is wrong, leave src/ unchanged and report it in the verdict below.

VERDICT (required, last step): write reports/repair_verdict.json as
{{"cause": "<one of: design | testbench | reference_model | generated_check | toolchain | specification>",
 "reason": "<one or two sentences with the concrete evidence>"}}
design = you fixed src/; testbench = you fixed a hand-written testbench; reference_model =
model/reference_model.py interprets PROMPT.md wrongly; generated_check = an automatically generated
check (e.g. tests/*_model_tb.vhd) is wrong; toolchain = the cause is outside the project files;
specification = PROMPT.md is ambiguous or contradictory for this case."""
        testbench_repair = any(str(f).startswith("tests/") for f in affected_files)
        instruction += requirements_suffix(workspace, "repair_testbench" if testbench_repair else "repair")

        logger.info("OPENCODE_STARTED module=%s files=%s", failed_module, affected_files)
        self.emit_event("OPENCODE_STARTED", {
            "task_id": task.id,
            "module": failed_module,
            "affected_files": affected_files,
        })

        try:
            result = self._opencode.execute(workspace, instruction)
        except WorkflowError as exc:
            return self._opencode_call_failed(
                task, f"Reparatur von '{failed_module or 'Design'}'", exc, module=failed_module,
            )

        if result.success:
            logger.info("OPENCODE_COMPLETED module=%s", failed_module)
            self.emit_event("OPENCODE_COMPLETED", {
                "task_id": task.id,
                "module": failed_module,
                "modified_files": affected_files,
                "stdout": result.stdout[-4000:],
                "stderr": result.stderr[-4000:],
            })
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.COMPLETED,
                outputs={
                    "repaired": True,
                    "modified_files": affected_files,
                },
            )
        else:
            cause, hint = describe_opencode_failure(result.returncode, result.stdout, result.stderr)
            error = OpenCodeDeliveryError(
                f"Reparatur von '{failed_module or 'Design'}' fehlgeschlagen",
                cause=cause, hint=hint,
                context={
                    "Exit-Code": result.returncode,
                    "Betroffene Dateien": ", ".join(affected_files),
                    "stderr (Ende)": (result.stderr or "")[-2000:],
                },
            )
            logger.error("OPENCODE_FAILED %s", error)
            self.emit_event("OPENCODE_FAILED", {
                "task_id": task.id,
                "module": failed_module,
                "error": str(error),
                "stdout": result.stdout[-4000:],
                "stderr": result.stderr[-4000:],
            })
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.FAILED,
                error_message=str(error),
            )

    async def _review_hdl(self, task: AgentTask) -> AgentResult:
        """Reviewed VHDL-Code auf Coding Guidelines."""
        workspace = task.inputs.get("workspace", "")
        files = task.inputs.get("files", [])
        
        issues = []
        for file_path in files:
            full_path = Path(workspace) / file_path
            if self._fs.file_exists(str(full_path)):
                code = self._fs.read_file(str(full_path))
                file_issues = self._check_coding_guidelines(code, file_path)
                issues.extend(file_issues)
        
        if issues:
            return AgentResult(
                task_id=task.id,
                status=AgentStatus.FAILED,
                error_message="Coding guideline violations found",
                diagnostics=[{"type": "style_violation", "issues": issues}],
            )
        
        return AgentResult(
            task_id=task.id,
            status=AgentStatus.COMPLETED,
            outputs={"reviewed_files": len(files), "issues": 0},
        )

    def _check_coding_guidelines(self, code: str, file_path: str) -> list[dict]:
        """Prüft VHDL-Code auf Coding Guidelines."""
        issues = []
        lines = code.split('\n')
        
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            
            # Keine wait in synthesizable Code
            if 'wait' in stripped.lower() and 'testbench' not in file_path.lower():
                issues.append({
                    "file": file_path,
                    "line": i,
                    "rule": "no_wait_in_synthesizable",
                    "message": "wait statement in synthesizable code",
                })
            
            # Sensitivity list completeness check (basic)
            if 'process(' in stripped.lower() and 'begin' not in stripped.lower():
                # Could check sensitivity list completeness
                pass
        
        return issues