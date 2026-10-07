"""Deterministic (LLM-free) design generation.

Die Produktionsphasen Architektur, HDL-Generierung und Testbench dürfen
nicht hart von einem LLM abhängen. Dieser Service liefert für diese Phasen
einen deterministischen, prüfbaren Fallback: Er leitet Module, Interfaces
und Clock-/Reset-Konzept aus der Anforderung ab und nutzt für den VHDL-Code
den GHDL-verifizierten Template-Generator (VHDLArtifactGenerator).

Wichtig: Das erzeugte VHDL ist echtes, synthetisierbares RTL und keine
Platzhalter-Dummy. Wiley Modulname, Ports und Testbench stammen aus derselben
Quelle, bleibt der deterministische Pfad intern konsistent (Entity-Name und
Testbench-Referenz stimmen immer überein).
"""
import logging
import re
from typing import Any

from src.domain.models import ArtifactBundle, ModuleInfo
from src.services.artifact_generator import VHDLArtifactGenerator

logger = logging.getLogger(__name__)

_LAUFLICHT_KEYWORDS = [
    "lauflicht", "running light", "running_light", "shift register",
    "laufschrittmotor", "led shift", "led lauf", "chaser",
]
_COMPARATOR_KEYWORDS = ["vergleich", "compare", "equal"]
_COUNTER_KEYWORDS = ["counter", "zähler", "zaehler", "count"]

_ENTITY_RE = re.compile(r"\bentity\s+(\w+)\s+is", re.IGNORECASE)
_PORT_RE = re.compile(
    r"Port\s*\((.*?)\)\s*;", re.IGNORECASE | re.DOTALL
)


def _entity_of(content: str) -> str | None:
    match = _ENTITY_RE.search(content or "")
    return match.group(1) if match else None


class DeterministicDesignService:
    """Deterministischer Ersatz für LLM-basierte Design-/Generierungsphasen."""

    def __init__(self):
        self._generator = VHDLArtifactGenerator()
        self._bundle: ArtifactBundle | None = None
        self._bundle_key: tuple[str, str] | None = None

    # ------------------------------------------------------------------
    # Erkennung
    # ------------------------------------------------------------------
    def detect_pattern(self, request: str) -> str:
        """Erkennt den Implementierungs-Typ aus der Anforderung.

        Reihenfolge entspricht exakt der Template-Auswahl in
        VHDLArtifactGenerator, damit Modul-VHDL und Ports zusammenpassen.
        """
        lowered = request.lower()
        if any(w in lowered for w in _LAUFLICHT_KEYWORDS):
            return "lauflicht"
        if any(w in lowered for w in _COMPARATOR_KEYWORDS):
            return "comparator"
        if any(w in lowered for w in _COUNTER_KEYWORDS):
            return "counter"
        return "register"

    def generate_bundle(self, request: str, analysis: str) -> ArtifactBundle:
        """Generiert (gecacht) das VHDL-Bundle für eine Anforderung."""
        key = (request, analysis)
        if self._bundle is None or self._bundle_key != key:
            self._bundle = self._generator.generate(request, analysis)
            self._bundle_key = key
        return self._bundle

    def entity_name(self, request: str, analysis: str) -> str:
        """Name der Top-Level-Entity des deterministischen Designs."""
        bundle = self.generate_bundle(request, analysis)
        for file_artifact in bundle.files:
            if file_artifact.path.startswith("src/"):
                entity = _entity_of(file_artifact.content)
                if entity:
                    return entity
        return VHDLArtifactGenerator._extract_entity_name(request, "my_component")

    def module_width(self, request: str) -> int:
        return VHDLArtifactGenerator._extract_width(request, 8)

    # ------------------------------------------------------------------
    # Architektur
    # ------------------------------------------------------------------
    def build_architecture(self, request: str, analysis: str) -> dict:
        """Baut eine vollständige Architektur-Struktur deterministisch.

        Rückgabe entspricht dem Schema von
        ArchitectureAgent._parse_architecture_yaml (modules als ModuleInfo).
        """
        pattern = self.detect_pattern(request)
        name = self.entity_name(request, analysis)
        width = self.module_width(request)

        module = self._module_for(pattern, name, width, request)

        return {
            "modules": [module],
            "interfaces": {},
            "clock_domain": "clk",
            "reset_concept": "async_active_high",
            "decisions": [
                {
                    "decision": (
                        f"Deterministische Ein-Modul-Architektur ({pattern}) "
                        f"aus Anforderung abgeleitet"
                    ),
                    "reason": (
                        "LLM nicht verfügbar; Architektur wird aus der "
                        "Anforderung und dem Template-Generator abgeleitet"
                    ),
                },
            ],
            "top_module": name,
            "deterministic": True,
        }

    def _module_for(self, pattern: str, name: str, width: int, request: str) -> ModuleInfo:
        if pattern == "lauflicht":
            return ModuleInfo(
                name=name,
                type="sequential",
                inputs=["clk", "rst"],
                outputs=["leds"],
                parameters={
                    "clk_freq_hz": 100000000,
                    "led_count": 4,
                    "blink_hz": 2,
                },
                description="LED-Lauflicht mit Clock-Teilung (deterministisch)",
                dependencies=[],
            )
        if pattern == "comparator":
            return ModuleInfo(
                name=name,
                type="sequential",
                inputs=["clk", "rst", "a", "b"],
                outputs=["eq", "gt", "lt"],
                parameters={"width": width},
                description="Vergleicher mit EQ/GT/LT Ausgängen (deterministisch)",
                dependencies=[],
            )
        if pattern == "counter":
            return ModuleInfo(
                name=name,
                type="sequential",
                inputs=["clk", "rst", "enable"],
                outputs=["count"],
                parameters={"width": width},
                description="Binärzähler mit Enable (deterministisch)",
                dependencies=[],
            )
        return ModuleInfo(
            name=name,
            type="sequential",
            inputs=["clk", "rst", "data_in"],
            outputs=["data_out"],
            parameters={"width": width},
            description="Register mit Datenübernahme (deterministisch)",
            dependencies=[],
        )

    # ------------------------------------------------------------------
    # Modul-VHDL + Testbench
    # ------------------------------------------------------------------
    def module_vhdl(self, request: str, analysis: str, module_name: str) -> str | None:
        """Liefert den VHDL-Code (Entity + Architecture) für ein Modul."""
        bundle = self.generate_bundle(request, analysis)
        candidates = [f for f in bundle.files if f.path.startswith("src/")]
        for file_artifact in candidates:
            if _entity_of(file_artifact.content) == module_name:
                return file_artifact.content
        return None

    def testbench_vhdl(self, request: str, analysis: str, module_name: str) -> str | None:
        """Liefert die Testbench für ein Modul (falls verfügbar)."""
        bundle = self.generate_bundle(request, analysis)
        tb_files = [f for f in bundle.files if f.path.startswith("tests/")]
        for file_artifact in tb_files:
            if file_artifact.name == f"{module_name}_tb.vhd":
                return file_artifact.content
            if _entity_of(file_artifact.content) == f"{module_name}_tb":
                return file_artifact.content
        # Kompatible Testbench mit gleichem generierten Design verwenden.
        for file_artifact in tb_files:
            entity = _entity_of(file_artifact.content)
            if entity and entity.endswith("_tb"):
                module_entity = entity[:-3]
                if self.module_vhdl(request, analysis, module_entity):
                    return file_artifact.content
        return None

    # ------------------------------------------------------------------
    # Top-Level-Integration (mehrere Module)
    # ------------------------------------------------------------------
    def top_module_vhdl(
        self,
        request: str,
        analysis: str,
        modules: list[dict],
        top_module: str,
    ) -> str | None:
        """Erzeugt ein Top-Level-Wrapper-Modul, das alle Module instanziiert.

        Ports der Sub-Module werden über gleichnamige interne Signale
        verbunden; nicht intern getriebene Eingänge und nicht konsumierte
        Ausgänge werden als Top-Level-Ports der Entity herausgeführt.
        """
        module_ports: dict[str, list[tuple[str, str, str]]] = {}

        for module in modules:
            module_name = module.get("name") if isinstance(module, dict) else module.name
            content = self.module_vhdl(request, analysis, module_name)
            if content is None:
                return None
            module_ports[module_name] = self._parse_entity_ports(content)

        consumed: set[str] = set()
        produced: set[str] = set()
        declarations: dict[str, list[str]] = {}
        for ports in module_ports.values():
            for port, port_mode, port_type in ports:
                normalized = port.lower()
                kind = "vector" if "vector" in (port_type or "").lower() else "scalar"
                declarations.setdefault(normalized, []).append(kind)
                if normalized in {"clk", "rst", "reset"}:
                    continue
                if port_mode == "in":
                    consumed.add(normalized)
                elif port_mode == "out":
                    produced.add(normalized)

        def sig_type_for(port: str, width: int) -> str:
            # Skalar, sofern alle Deklarationen skalar sind (z. B. enable, eq).
            if "vector" not in declarations.get(port, ["vector"]):
                return "std_logic"
            return f"std_logic_vector({width - 1} downto 0)"

        top_inputs = sorted(consumed - produced)
        top_outputs = sorted(produced - consumed)
        internal = sorted(consumed | produced)
        width = self.module_width(request)

        lines = [
            "library IEEE;",
            "use IEEE.STD_LOGIC_1164.ALL;",
            "",
            f"entity {top_module} is",
            "    Port (",
            "        clk : in  std_logic;",
            "        rst : in  std_logic;",
        ]
        for port in top_inputs:
            lines.append(f"        {port} : in  {sig_type_for(port, width)};")
        for port in top_outputs:
            lines.append(f"        {port} : out {sig_type_for(port, width)};")

        # Letztes Port-Semikolon zugunsten der Abschlussklammer entfernen.
        lines[-1] = lines[-1].rstrip(";")
        lines.append("    );")
        lines.append(f"end {top_module};")
        lines.append("")

        lines.append("architecture Structural of " + top_module + " is")
        for sig in internal:
            lines.append(f"    signal {sig} : {sig_type_for(sig, width)};")
        lines.append("begin")
        lines.append("")

        for module_name, ports in module_ports.items():
            bindings = []
            for port, _, _ in ports:
                lowered_port = port.lower()
                if lowered_port in {"clk"}:
                    bindings.append(f"            {port} => clk")
                elif lowered_port in {"rst", "reset"}:
                    bindings.append(f"            {port} => rst")
                else:
                    bindings.append(f"            {port} => {lowered_port}")
            lines.append(f"    u_{module_name}: entity work.{module_name}")
            lines.append("        port map (")
            lines.append(",\n".join(bindings))
            lines.append("        );")
            lines.append("")

        lines.append("end Structural;")
        return "\n".join(lines) + "\n"

    def _parse_entity_ports(self, vhdl_content: str) -> list[tuple[str, str, str]]:
        """Extrahiert (Name, Mode, Typ) aus der Port-Klausel einer Entity."""
        port_block = _PORT_RE.search(vhdl_content or "")
        if not port_block:
            return []
        ports: list[tuple[str, str, str]] = []
        # Signaldefinitionen: name : in|out  typ
        for match in re.finditer(
            r"\b(\w+)\s*:\s*(in|out)\s+std_logic(?:_vector(?:\s*\(\s*[\w\-\s\d']+\s*downto\s+[\w\-\s\d']+\s*\))?)?",
            port_block.group(1),
            re.IGNORECASE,
        ):
            name, mode, vtype = match.group(1), match.group(2), match.group(0)
            ports.append((name, mode.lower(), vtype))
        return ports