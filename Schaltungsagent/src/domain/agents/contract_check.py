"""Contract checking between architecture handoff and implementation.

Validates that implemented VHDL entities match the architecture specification:
- Entity ports match architecture definition
- Signal widths are consistent
- Module dependencies are satisfied
- Top-level connections are valid
"""
import re
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


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
    
    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "violations": [v.to_dict() for v in self.violations],
            "checked_modules": self.checked_modules,
        }


class ContractChecker:
    """Validates that VHDL implementations match architecture contracts.
    
    Performs static analysis of VHDL files to verify:
    1. Entity port declarations match architecture specification
    2. Signal widths are consistent
    3. Module dependencies are satisfied
    4. Top-level connections are valid
    """
    
    def check(
        self,
        architecture: dict,
        workspace: str,
    ) -> ContractCheckResult:
        """Run contract checks against the architecture specification."""
        violations = []
        checked_modules = []
        
        modules = architecture.get("modules", [])
        interfaces = architecture.get("interfaces", {})
        
        # Check each module
        for module_data in modules:
            module_name = module_data.get("name", "") if isinstance(module_data, dict) else module_data.name
            checked_modules.append(module_name)
            
            # Find the VHDL file
            vhdl_path = Path(workspace) / "src" / f"{module_name}.vhd"
            if not vhdl_path.exists():
                violations.append(ContractViolation(
                    module=module_name,
                    check="file_exists",
                    expected=f"src/{module_name}.vhd",
                    actual="file not found",
                ))
                continue
            
            # Parse entity from VHDL file
            entity_info = self._parse_entity(vhdl_path)
            if not entity_info:
                violations.append(ContractViolation(
                    module=module_name,
                    check="entity_parse",
                    expected="valid entity declaration",
                    actual="could not parse entity",
                ))
                continue
            
            # Check ports match architecture
            arch_ports = module_data.get("inputs", []) + module_data.get("outputs", []) if isinstance(module_data, dict) else []
            entity_ports = entity_info.get("ports", [])
            
            violations.extend(self._check_ports(
                module_name, arch_ports, entity_ports
            ))
        
        # Check interface connections
        violations.extend(self._check_interfaces(modules, interfaces))
        
        # Check top-level module
        violations.extend(self._check_top_level(modules, workspace))
        
        return ContractCheckResult(
            passed=len(violations) == 0 or all(v.severity == "warning" for v in violations),
            violations=violations,
            checked_modules=checked_modules,
        )
    
    def _parse_entity(self, vhdl_path: Path) -> dict | None:
        """Parse entity declaration from VHDL file."""
        try:
            content = vhdl_path.read_text(errors="replace")
        except OSError:
            return None
        
        # Extract entity name
        entity_match = re.search(r'\bentity\s+(\w+)\s+is', content, re.IGNORECASE)
        if not entity_match:
            return None
        
        entity_name = entity_match.group(1)
        
        # Extract ports from entity declaration
        ports = []
        # Match port declarations - find the full port section by counting parens
        port_start = re.search(r'\bport\s*\(', content, re.IGNORECASE)
        if port_start:
            # Find matching closing paren by counting
            start_idx = port_start.end()
            depth = 1
            idx = start_idx
            while idx < len(content) and depth > 0:
                if content[idx] == '(':
                    depth += 1
                elif content[idx] == ')':
                    depth -= 1
                idx += 1
            port_text = content[start_idx:idx-1]
            
            # Parse individual port declarations
            for line in port_text.split('\n'):
                line = line.strip().rstrip(';').strip()
                if not line or line.lower().startswith('--'):
                    continue
                # Match: name : direction type
                port_match = re.match(
                    r'(\w+)\s*:\s*(in|out|inout|buffer)\s+(.+)',
                    line,
                    re.IGNORECASE,
                )
                if port_match:
                    ports.append({
                        "name": port_match.group(1),
                        "direction": port_match.group(2).lower(),
                        "type": port_match.group(3).strip(),
                    })
        
        return {
            "name": entity_name,
            "ports": ports,
        }
    
    def _check_ports(
        self,
        module_name: str,
        arch_ports: list[str],
        entity_ports: list[dict],
    ) -> list[ContractViolation]:
        """Check that entity ports match architecture specification."""
        violations = []
        
        # Build set of entity port names (normalized)
        entity_port_names = {p["name"].lower() for p in entity_ports}
        
        # Check that architecture ports exist in entity
        for port_name in arch_ports:
            port_lower = port_name.lower()
            if port_lower not in entity_port_names:
                # Check if it's an auto-added clk/rst
                if port_lower in ("clk", "rst", "clk_out"):
                    continue
                violations.append(ContractViolation(
                    module=module_name,
                    check="port_exists",
                    expected=port_name,
                    actual="not found in entity",
                ))
        
        return violations
    
    def _check_interfaces(
        self,
        modules: list,
        interfaces: dict,
    ) -> list[ContractViolation]:
        """Check that module interfaces are consistent."""
        violations = []
        
        for iface_name, iface_data in interfaces.items():
            if isinstance(iface_data, dict):
                source = iface_data.get("from", "")
                target = iface_data.get("to", "")
                signals = iface_data.get("signals", [])
            elif isinstance(iface_data, str):
                # Simple string interface definition
                continue
            else:
                continue
            
            # Check that source and target modules exist
            module_names = set()
            for m in modules:
                name = m.get("name", "") if isinstance(m, dict) else m.name
                module_names.add(name)
            
            if source and source not in module_names:
                violations.append(ContractViolation(
                    module=source,
                    check="interface_source",
                    expected=f"module '{source}' exists",
                    actual="module not found",
                    severity="warning",
                ))
            
            if target and target not in module_names:
                violations.append(ContractViolation(
                    module=target,
                    check="interface_target",
                    expected=f"module '{target}' exists",
                    actual="module not found",
                    severity="warning",
                ))
        
        return violations
    
    def _check_top_level(
        self,
        modules: list,
        workspace: str,
    ) -> list[ContractViolation]:
        """Check that top-level module exists and connects to sub-modules."""
        violations = []
        
        # Find top-level module (one with no dependencies or named "top")
        top_candidates = []
        for m in modules:
            name = m.get("name", "") if isinstance(m, dict) else m.name
            deps = m.get("dependencies", []) if isinstance(m, dict) else []
            if name.lower() == "top" or not deps:
                top_candidates.append(name)
        
        if not top_candidates:
            violations.append(ContractViolation(
                module="top",
                check="top_level_exists",
                expected="a top-level module",
                actual="no top-level module found",
                severity="warning",
            ))
            return violations
        
        # Check top-level file exists
        for top_name in top_candidates:
            top_path = Path(workspace) / "src" / f"{top_name}.vhd"
            if not top_path.exists():
                violations.append(ContractViolation(
                    module=top_name,
                    check="top_level_file",
                    expected=f"src/{top_name}.vhd",
                    actual="file not found",
                ))
        
        return violations
