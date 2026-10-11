"""Vorfilter (Triage) für alle Fehler eines Laufs.

Bevor ein Fehler an einen Agenten geht, wird er hier aufbereitet:

1. **Kernzeilen**: Die eigentlichen Fehlerzeilen stehen meist nicht in der
   Kurzmeldung („GHDL simulation failed for x_tb“), sondern in ``details``
   (GHDL-/Vivado-Ausgabe, fehlgeschlagene Assertion, Modellabweichung). Früher
   sah die Diagnose nur die Kurzmeldung; Fehlerklasse und Modul gingen verloren,
   und die Reparatur musste die Ursache selbst neu ermitteln.
2. **Herkunft**: Entwurf, Testbench, Anforderungen, Werkzeug-/Board-
   Konfiguration, Hardware oder Infrastruktur. Sie bestimmt den zuständigen
   Agenten und die Eskalationsleiter. Werkzeug- und Konfigurationsfehler
   werden nie als HDL-Fehler behandelt (Lauf gray-countdown 2026-10-11: ein
   Vivado-Konfigurationsfehler beim Flashen ging als „unknown“ an die
   HDL-Reparatur, dann an Neuschreiben und Architekturüberarbeitung, 5 h).
3. **Module** nur aus belegbaren Quellen: ausdrückliche Angabe des Erzeugers
   oder eine Fehlerzeile mit ``<datei>.vhd:<zeile>``. Früher genügte ein
   Modulname irgendwo im Text (z. B. im Pfad der .bit-Datei).
"""
from __future__ import annotations

import re

from src.domain.agents.repair_routing import RepairTarget, route_repair

# Herkunft -> Bedeutung für Routing und Eskalation
DESIGN = "design"              # VHDL-Code des Entwurfs
VERIFICATION = "verification"  # Testbenches, Abdeckung
REQUIREMENTS = "requirements"  # Anforderungsliste/Plan
TOOLCHAIN = "toolchain"        # Constraints, Build-/Board-Konfiguration
HARDWARE = "hardware"          # Board, Kabel, JTAG
INFRASTRUCTURE = "infrastructure"  # fehlende Werkzeuge, Provider

ORIGIN_BY_TYPE = {
    "syntax_error": DESIGN, "type_error": DESIGN, "elaboration_error": DESIGN,
    "clock_reset_error": DESIGN, "functional_simulation_error": DESIGN,
    "contract_violation": DESIGN, "logic_error": DESIGN, "model_mismatch": DESIGN,
    "synthesis_error": DESIGN, "timing_error": DESIGN, "requirement_violation": DESIGN,
    "simulation_hardware_divergence": DESIGN, "interface_mismatch": DESIGN,
    "architecture_error": DESIGN, "unknown": DESIGN,
    "testbench_error": VERIFICATION, "coverage_gap": VERIFICATION,
    "weak_testbench": VERIFICATION, "requirement_gap": VERIFICATION,
    "requirement_missing": REQUIREMENTS,
    "constraint_error": TOOLCHAIN, "bitstream_error": TOOLCHAIN,
    "bitstream_config_error": TOOLCHAIN,
    "flash_error": HARDWARE, "hardware_error": HARDWARE, "resource_error": HARDWARE,
    "target_ambiguous": HARDWARE,
    "infrastructure": INFRASTRUCTURE,
}

_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\[[0-9;]*m")
_KEY_LINE = re.compile(
    r"error|ERROR:|CRITICAL WARNING|assertion|MODEL_MISMATCH|\bFAIL\b|failed|timed out|"
    r"not found|no declaration|unexpected|expected|mismatch|cannot|unable",
    re.IGNORECASE,
)
# Wiederkehrende Meldungen ohne Aussagekraft
_NOISE = re.compile(r"metavalue detected|TB_COMPLETE|report note|^\s*\^\s*$", re.IGNORECASE)
_FILE_REF = re.compile(r"(?:^|[\s/\"'(])((?:src|tests)/)?(\w+)\.vhdl?:\d+", re.MULTILINE)

MAX_KEY_LINES = 25
MAX_LINE_CHARS = 400

# Phase -> Klasse, wenn nichts Genaueres erkennbar ist
_STAGE_FALLBACK = {
    "flash": "flash_error",
    "hardware": "hardware_error",
    "synthesis": "synthesis_error",
}

_FLASH_BOARD = re.compile(
    r"kein passendes fpga-board|mehrere passende fpga|no hardware devices|no_matching_board|"
    r"multiple_matching_boards|hw_server|cable|jtag chain|could not connect",
    re.IGNORECASE,
)
_FLASH_CONFIG = re.compile(
    r"writecfgmem|spi_buswidth|bitstream\.config|config_mode|cfgbvs|config_voltage",
    re.IGNORECASE,
)
_CONSTRAINT = re.compile(
    r"\[Place 30-|UCIO-1|NSTD-1|IOSTANDARD|PACKAGE_PIN|unconstrained|get_ports|\.xdc", re.IGNORECASE,
)


def classify_flash_output(text: str, board_detected: bool) -> str:
    """Fehlerklasse eines Flash-Versuchs (vom FPGAAgent selbst gesetzt)."""
    if not board_detected or _FLASH_BOARD.search(text or ""):
        return "flash_error"
    if _FLASH_CONFIG.search(text or ""):
        return "bitstream_config_error"
    return "flash_error"


def clean(text: str) -> str:
    return _ANSI.sub("", str(text or ""))


def _detail_texts(diagnostic: dict) -> list[str]:
    details = diagnostic.get("details") or {}
    texts: list[str] = []
    if isinstance(details, dict):
        for key in ("error", "stderr", "stdout", "cause", "hint"):
            value = details.get(key)
            if isinstance(value, str) and value.strip():
                texts.append(value)
        failed_case = details.get("failed_case")
        if isinstance(failed_case, dict) and failed_case:
            texts.append("failed case: " + ", ".join(f"{k}={v}" for k, v in failed_case.items()))
        errors = details.get("errors")
        if isinstance(errors, list):
            texts.extend(str(e) for e in errors)
        steps = details.get("steps")
        if isinstance(steps, list):
            for step in steps[-3:]:
                if isinstance(step, dict) and step.get("returncode") not in (0, None):
                    texts.append(str(step.get("stderr") or ""))
                    texts.append(str(step.get("stdout") or "")[-4000:])
    for key in ("evidence",):
        value = diagnostic.get(key)
        if isinstance(value, list):
            texts.extend(str(v) for v in value)
    return texts


def key_lines(diagnostic: dict) -> list[str]:
    """Aussagekräftige Fehlerzeilen aus Meldung und Details (ohne ANSI, ohne Dubletten)."""
    lines: list[str] = []
    seen: set[str] = set()
    for line in diagnostic.get("key_lines") or []:  # bereits beim Speichern ermittelt
        if line not in seen:
            seen.add(line)
            lines.append(line)
    message = clean(diagnostic.get("message", "")).strip()
    if message:
        first = message.splitlines()[0][:MAX_LINE_CHARS]
        lines.append(first)
        seen.add(first)
    for text in [message, *_detail_texts(diagnostic)]:
        for raw in clean(text).splitlines():
            line = raw.strip()[:MAX_LINE_CHARS]
            if not line or line in seen or _NOISE.search(line) or not _KEY_LINE.search(line):
                continue
            seen.add(line)
            lines.append(line)
            if len(lines) >= MAX_KEY_LINES:
                return lines
    return lines


_HEAVY_DETAIL_KEYS = ("dut_content", "tb_content", "steps", "stdout", "stdout (Ende)", "stderr (Ende)")
_MAX_DETAIL_CHARS = 4000


def compact(diagnostic: dict) -> dict:
    """Diagnose für den gespeicherten Projektzustand: Kernzeilen statt kompletter
    Quelltexte und Simulationsausgaben.

    Lauf led-pattern-display: Jede Diagnose trug den Quelltext aller Dateien
    (``dut_content``) und die volle Ausgabe; design_state.yaml wuchs auf 1,27 MB,
    jedes Laden/Speichern kostete 6,7 s (vor jedem OpenCode-Aufruf).
    """
    result = dict(diagnostic)
    result["key_lines"] = key_lines(diagnostic)
    details = diagnostic.get("details")
    if isinstance(details, dict):
        slim = {}
        for key, value in details.items():
            if key in _HEAVY_DETAIL_KEYS:
                continue
            if isinstance(value, str) and len(value) > _MAX_DETAIL_CHARS:
                value = value[:_MAX_DETAIL_CHARS // 2] + "\n…\n" + value[-_MAX_DETAIL_CHARS // 2:]
            slim[key] = value
        result["details"] = slim
    message = result.get("message")
    if isinstance(message, str) and len(message) > _MAX_DETAIL_CHARS:
        result["message"] = message[:_MAX_DETAIL_CHARS] + " …"
    return result


def referenced_modules(lines: list[str], known_modules: list[str]) -> list[str]:
    """Module, auf deren Quelldatei eine Fehlerzeile verweist (x.vhd:12)."""
    known = {m.lower(): m for m in known_modules}
    found: list[str] = []
    for line in lines:
        for folder, stem in _FILE_REF.findall(line):
            name = stem.lower()
            if folder.startswith("tests") or name.endswith("_tb"):
                name = name[:-3] if name.endswith("_tb") else name
            module = known.get(name)
            if module and module not in found:
                found.append(module)
    return found


def _classify_lines(text: str, stage: str) -> str:
    from src.agents.debug import classify_error

    if stage == "flash":
        if _FLASH_CONFIG.search(text):
            return "bitstream_config_error"
        if _FLASH_BOARD.search(text):
            return "flash_error"
    if stage == "synthesis" and _CONSTRAINT.search(text):
        return "constraint_error"
    failure_type, _, _ = classify_error(text, stage)
    if failure_type == "unknown":
        lowered = text.lower()
        if stage in ("static_check", "simulation"):
            if "analysis failed" in lowered:
                return "syntax_error"
            if "elaboration failed" in lowered:
                return "elaboration_error"
            if "simulation" in lowered and ("failed" in lowered or "assertion" in lowered):
                return "functional_simulation_error"
        return _STAGE_FALLBACK.get(stage, "unknown")
    if stage == "flash" and ORIGIN_BY_TYPE.get(failure_type) == DESIGN:
        # Beim Flashen gibt es keinen Entwurfsfehler mehr: der Bitstream ist gebaut.
        return "flash_error"
    return failure_type


def triage(diagnostics: list[dict], stage: str, known_modules: list[str]) -> dict:
    """Fehlerklasse, Herkunft, zuständiger Agent, Module und Kernzeilen."""
    lines: list[str] = []
    explicit = ""
    explicit_modules: list[str] = []
    for diagnostic in diagnostics or []:
        for line in key_lines(diagnostic):
            if line not in lines:
                lines.append(line)
        failure_type = str(diagnostic.get("failure_type") or "")
        if failure_type and failure_type != "unknown" and not explicit:
            explicit = failure_type
        for module in diagnostic.get("modules") or ([diagnostic["module"]] if diagnostic.get("module") else []):
            if module in known_modules and module not in explicit_modules:
                explicit_modules.append(module)
    lines = lines[:MAX_KEY_LINES]
    text = "\n".join(lines)
    failure_type = explicit or _classify_lines(text, stage)
    origin = ORIGIN_BY_TYPE.get(failure_type, DESIGN)
    if origin in (DESIGN, VERIFICATION, REQUIREMENTS):
        modules = explicit_modules or referenced_modules(lines, known_modules)
    else:
        modules = explicit_modules  # Werkzeug/Hardware: keine Zuordnung aus Freitext
    return {
        "failure_type": failure_type,
        "origin": origin,
        "repair_target": route_repair(failure_type).value,
        "modules": modules,
        "key_lines": lines,
    }


def owner_label(target: str) -> str:
    return {
        RepairTarget.HDL.value: "HDLAgent",
        RepairTarget.FPGA.value: "FPGAAgent",
        RepairTarget.VERIFICATION.value: "VerificationAgent",
        RepairTarget.ARCHITECTURE.value: "ArchitectureAgent",
        RepairTarget.HUMAN.value: "Benutzer",
    }.get(target, target)
