"""Contract checking between architecture handoff and implementation.

Validates that implemented VHDL entities match the architecture specification:
- Entity ports exist with the contracted direction
- Port base types and bit widths match where the contract specifies a type
- Sequential modules expose the architecture clock port
- Interface endpoints refer to existing modules/ports
- The architecture top-level module is implemented

Port contracts may be given as plain names (``"data_in"``), as typed strings
(``"data_in: std_logic_vector(7 downto 0)"``), as dicts
(``{"name": "data_in", "type": "..."}``), as a module-level ``ports`` mapping,
or through an architecture interface with ``module`` + ``ports`` (UART style).
"""
import re
import logging
from pathlib import Path
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_CLOCK_EXEMPT_PORTS = {"clk", "rst", "clk_out"}
_SAFE_EXPR = re.compile(r"^[\d\s+\-*/()]+$")
_RANGE = re.compile(r"\(\s*(.+?)\s+(downto|to)\s+(.+?)\s*\)\s*$", re.IGNORECASE)


@dataclass
class ContractViolation:
    """A single contract violation."""
    module: str
    check: str
    expected: str
    actual: str
    severity: str = "error"  # "error" or "warning"

    def to_dict(self) -> dict:
        return {
            "module": self.module,
            "check": self.check,
            "expected": self.expected,
            "actual": self.actual,
            "severity": self.severity,
        }


@dataclass
class ContractCheckResult:
    """Result of a contract check."""
    passed: bool
    violations: list[ContractViolation] = field(default_factory=list)
    checked_modules: list[str] = field(default_factory=list)

    @property
    def errors(self) -> list[ContractViolation]:
        return [v for v in self.violations if v.severity == "error"]

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "violations": [v.to_dict() for v in self.violations],
            "checked_modules": self.checked_modules,
        }

    def summary(self, limit: int = 10) -> str:
        lines = [
            f"{v.module}: {v.check} expected '{v.expected}', got '{v.actual}'"
            for v in self.errors[:limit]
        ]
        return "; ".join(lines)


def _field(module, key, default=None):
    if isinstance(module, dict):
        return module.get(key, default)
    return getattr(module, key, default)


class ContractChecker:
    """Validates that VHDL implementations match architecture contracts."""

    def check(
        self,
        architecture: dict,
        workspace: str,
    ) -> ContractCheckResult:
        """Run contract checks against the architecture specification."""
        violations: list[ContractViolation] = []
        checked_modules: list[str] = []

        modules = architecture.get("modules", [])
        interfaces = architecture.get("interfaces", {}) or {}
        clock_name = (architecture.get("clock_domain") or "clk").lower()
        entities: dict[str, dict] = {}

        for module_data in modules:
            module_name = _field(module_data, "name", "")
            checked_modules.append(module_name)

            vhdl_path = Path(workspace) / "src" / f"{module_name}.vhd"
            if not vhdl_path.exists():
                violations.append(ContractViolation(
                    module=module_name,
                    check="file_exists",
                    expected=f"src/{module_name}.vhd",
                    actual="file not found",
                ))
                continue

            entity_info = self._parse_entity(vhdl_path)
            if not entity_info:
                violations.append(ContractViolation(
                    module=module_name,
                    check="entity_parse",
                    expected="valid entity declaration",
                    actual="could not parse entity",
                ))
                continue
            entities[module_name] = entity_info

            if entity_info["name"].lower() != module_name.lower():
                violations.append(ContractViolation(
                    module=module_name,
                    check="entity_name",
                    expected=module_name,
                    actual=entity_info["name"],
                ))

            expected_ports = self._expected_ports(module_data, interfaces)
            parameters = _field(module_data, "parameters", {}) or {}
            generics = {**entity_info.get("generics", {}), **{
                str(k).lower(): v for k, v in parameters.items()
            }}
            violations.extend(self._check_ports(
                module_name, expected_ports, entity_info.get("ports", []), generics,
            ))

            if str(_field(module_data, "type", "")).lower() == "sequential":
                port_names = {p["name"].lower() for p in entity_info.get("ports", [])}
                if clock_name not in port_names and not any(
                    "clk" in name or "clock" in name for name in port_names
                ):
                    violations.append(ContractViolation(
                        module=module_name,
                        check="clock_port",
                        expected=f"clock port '{clock_name}'",
                        actual="no clock port in entity",
                        severity="warning",
                    ))

        violations.extend(self._check_interfaces(modules, interfaces, entities))
        violations.extend(self._check_top_level(
            modules, workspace, architecture.get("top_module", ""),
        ))

        return ContractCheckResult(
            passed=all(v.severity == "warning" for v in violations),
            violations=violations,
            checked_modules=checked_modules,
        )

    # ------------------------------------------------------------------
    # Contract extraction
    # ------------------------------------------------------------------

    def _expected_ports(self, module_data, interfaces: dict) -> dict[str, dict]:
        """Collect {port_lower: {name, direction, type}} for a module."""
        expected: dict[str, dict] = {}

        def add(entry, direction: str | None):
            name, port_type = None, None
            if isinstance(entry, dict):
                name = entry.get("name")
                port_type = entry.get("type")
                direction = entry.get("direction", direction)
            elif isinstance(entry, str):
                if ":" in entry:
                    name, port_type = (part.strip() for part in entry.split(":", 1))
                else:
                    name = entry.strip()
            if not name:
                return
            current = expected.setdefault(name.lower(), {"name": name})
            if direction:
                current["direction"] = direction.lower()
            if port_type:
                current["type"] = port_type

        for entry in _field(module_data, "inputs", []) or []:
            add(entry, "in")
        for entry in _field(module_data, "outputs", []) or []:
            add(entry, "out")
        ports = _field(module_data, "ports", {}) or {}
        if isinstance(ports, dict):
            for name, spec in ports.items():
                add({"name": name, **(spec if isinstance(spec, dict) else {"type": spec})}, None)

        module_name = _field(module_data, "name", "")
        for iface in interfaces.values():
            if isinstance(iface, dict) and iface.get("module") == module_name:
                for name, spec in (iface.get("ports") or {}).items():
                    add({"name": name, **(spec if isinstance(spec, dict) else {"type": spec})}, None)
        return expected

    # ------------------------------------------------------------------
    # VHDL parsing
    # ------------------------------------------------------------------

    def _parse_entity(self, vhdl_path: Path) -> dict | None:
        """Parse entity name, generics and ports from a VHDL file."""
        try:
            content = vhdl_path.read_text(errors="replace")
        except OSError:
            return None
        content = re.sub(r"--[^\n]*", "", content)

        entity_match = re.search(r'\bentity\s+(\w+)\s+is\b', content, re.IGNORECASE)
        if not entity_match:
            return None
        entity_name = entity_match.group(1)
        header = content[entity_match.end():]
        # Nur den Entity-Kopf betrachten (bis zur Architecture), damit
        # Komponenten-Deklarationen nicht als Ports gelesen werden.
        arch_match = re.search(r"\barchitecture\b", header, re.IGNORECASE)
        if arch_match:
            header = header[:arch_match.start()]

        generics = {}
        generic_text = self._paren_block(header, r"\bgeneric\s*\(")
        if generic_text:
            for decl in generic_text.split(";"):
                match = re.match(r"\s*([\w\s,]+?)\s*:\s*[^:=]+(?::=\s*(.+))?$", decl.strip(), re.DOTALL)
                if match and match.group(2):
                    for name in match.group(1).split(","):
                        generics[name.strip().lower()] = match.group(2).strip()

        ports = []
        port_text = self._paren_block(header, r"\bport\s*\(")
        if port_text:
            for decl in port_text.split(";"):
                decl = " ".join(decl.split())
                if not decl:
                    continue
                port_match = re.match(
                    r'([\w\s,]+?)\s*:\s*(in|out|inout|buffer)\s+(.+)',
                    decl,
                    re.IGNORECASE,
                )
                if not port_match:
                    continue
                port_type = re.sub(r"\s*:=.*$", "", port_match.group(3)).strip()
                for name in port_match.group(1).split(","):
                    ports.append({
                        "name": name.strip(),
                        "direction": port_match.group(2).lower(),
                        "type": port_type,
                    })

        return {"name": entity_name, "ports": ports, "generics": generics}

    @staticmethod
    def _paren_block(text: str, opener: str) -> str:
        start = re.search(opener, text, re.IGNORECASE)
        if not start:
            return ""
        idx = start.end()
        depth = 1
        while idx < len(text) and depth > 0:
            if text[idx] == "(":
                depth += 1
            elif text[idx] == ")":
                depth -= 1
            idx += 1
        return text[start.end():idx - 1]

    # ------------------------------------------------------------------
    # Type/width helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _base_type(port_type: str) -> str:
        return re.split(r"[\s(]", port_type.strip().lower(), maxsplit=1)[0]

    @classmethod
    def _width(cls, port_type: str, generics: dict) -> int | None:
        """Bit width of a vector type, 1 for scalar std_logic, None if unknown."""
        base = cls._base_type(port_type)
        if base in ("std_logic", "std_ulogic", "bit"):
            return 1
        match = _RANGE.search(port_type)
        if not match:
            return None
        left = cls._evaluate(match.group(1), generics)
        right = cls._evaluate(match.group(3), generics)
        if left is None or right is None:
            return None
        return abs(left - right) + 1

    @staticmethod
    def _evaluate(expr: str, generics: dict) -> int | None:
        def substitute(match):
            value = generics.get(match.group(0).lower())
            return str(value) if value is not None else match.group(0)

        resolved = re.sub(r"[A-Za-z_]\w*", substitute, expr)
        if not _SAFE_EXPR.match(resolved):
            return None
        try:
            return int(eval(resolved, {"__builtins__": {}}, {}))  # noqa: S307 - arithmetic only
        except Exception:
            return None

    def _check_ports(
        self,
        module_name: str,
        expected_ports,
        entity_ports: list[dict],
        generics: dict | None = None,
    ) -> list[ContractViolation]:
        """Check existence, direction, base type and width of contracted ports."""
        violations = []
        generics = generics or {}
        if isinstance(expected_ports, list):
            expected_ports = {
                str(p).lower(): {"name": str(p)} for p in expected_ports
            }
        entity_by_name = {p["name"].lower(): p for p in entity_ports}

        for key, spec in expected_ports.items():
            actual = entity_by_name.get(key)
            if actual is None:
                if key in _CLOCK_EXEMPT_PORTS:
                    continue
                violations.append(ContractViolation(
                    module=module_name,
                    check="port_exists",
                    expected=spec["name"],
                    actual="not found in entity",
                ))
                continue

            direction = spec.get("direction")
            if direction and actual["direction"] not in (direction, "inout") and not (
                direction == "out" and actual["direction"] == "buffer"
            ):
                violations.append(ContractViolation(
                    module=module_name,
                    check="port_direction",
                    expected=f"{spec['name']}: {direction}",
                    actual=f"{actual['name']}: {actual['direction']}",
                ))

            expected_type = spec.get("type")
            if not expected_type:
                continue
            if self._base_type(expected_type) != self._base_type(actual["type"]):
                violations.append(ContractViolation(
                    module=module_name,
                    check="port_type",
                    expected=f"{spec['name']}: {expected_type}",
                    actual=f"{actual['name']}: {actual['type']}",
                ))
                continue
            expected_width = self._width(expected_type, generics)
            actual_width = self._width(actual["type"], generics)
            if expected_width is None or actual_width is None:
                if expected_type.replace(" ", "").lower() != actual["type"].replace(" ", "").lower():
                    violations.append(ContractViolation(
                        module=module_name,
                        check="port_width",
                        expected=f"{spec['name']}: {expected_type}",
                        actual=f"{actual['name']}: {actual['type']} (width not evaluable)",
                        severity="warning",
                    ))
            elif expected_width != actual_width:
                violations.append(ContractViolation(
                    module=module_name,
                    check="port_width",
                    expected=f"{spec['name']}: {expected_width} bit",
                    actual=f"{actual['name']}: {actual_width} bit",
                ))
        return violations

    def _check_interfaces(
        self,
        modules: list,
        interfaces: dict,
        entities: dict[str, dict] | None = None,
    ) -> list[ContractViolation]:
        """Check that interface endpoints exist."""
        violations = []
        entities = entities or {}
        module_names = {_field(m, "name", "") for m in modules}

        for iface_data in interfaces.values():
            if not isinstance(iface_data, dict):
                continue
            source = iface_data.get("from", "")
            target = iface_data.get("to", "")
            for role, name in (("interface_source", source), ("interface_target", target)):
                if name and name not in module_names:
                    violations.append(ContractViolation(
                        module=name,
                        check=role,
                        expected=f"module '{name}' exists",
                        actual="module not found",
                        severity="warning",
                    ))
            for signal in iface_data.get("signals", []) or []:
                for name, direction in ((source, "out"), (target, "in")):
                    entity = entities.get(name)
                    if not entity:
                        continue
                    port = next(
                        (p for p in entity["ports"] if p["name"].lower() == str(signal).lower()),
                        None,
                    )
                    if port and port["direction"] not in (direction, "inout", "buffer"):
                        violations.append(ContractViolation(
                            module=name,
                            check="interface_direction",
                            expected=f"{signal}: {direction}",
                            actual=f"{signal}: {port['direction']}",
                        ))
        return violations

    def _check_top_level(
        self,
        modules: list,
        workspace: str,
        top_module: str = "",
    ) -> list[ContractViolation]:
        """Check that the architecture top-level module is implemented."""
        names = [_field(m, "name", "") for m in modules]
        if top_module:
            candidates = [top_module]
        else:
            depended_on = {
                dep for m in modules for dep in (_field(m, "dependencies", []) or [])
            }
            candidates = [n for n in names if n.lower() == "top"] or [
                n for n in names if n not in depended_on
            ]
        if not candidates:
            return [ContractViolation(
                module="top",
                check="top_level_exists",
                expected="a top-level module",
                actual="no top-level module found",
                severity="warning",
            )]

        violations = []
        for top_name in candidates[:1] if top_module else candidates:
            if top_module and top_name not in names:
                violations.append(ContractViolation(
                    module=top_name,
                    check="top_level_declared",
                    expected=f"top module '{top_name}' in architecture modules",
                    actual="not declared",
                ))
            if not (Path(workspace) / "src" / f"{top_name}.vhd").exists():
                violations.append(ContractViolation(
                    module=top_name,
                    check="top_level_file",
                    expected=f"src/{top_name}.vhd",
                    actual="file not found",
                ))
        return violations
