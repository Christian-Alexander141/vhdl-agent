"""Normalisierung des Ziel-FPGAs aus Benutzeranforderung und Registry.

Das Ziel wird früh im Workflow bestimmt und im DesignState gespeichert, damit
Architektur, Constraints, Synthese und Flash dasselbe Board verwenden.
Widersprüchliche Angaben führen zu einer Rückfrage statt zu einem stillen
Default.
"""
import re
from dataclasses import dataclass

# Board-Schlüssel (fpgas.yaml) -> Suchmuster in der Anforderung
_ALIASES: dict[str, list[str]] = {
    "arty_s7_50": [
        r"arty[\s_-]*s7(?:[\s_-]*50)?", r"xc7s50", r"spartan[\s_-]*7",
    ],
    "gatemate_a1": [
        r"gate[\s_-]*mate(?:[\s_-]*a1)?", r"ccgm1a1",
    ],
}


class AmbiguousTargetError(ValueError):
    """Die Anforderung nennt mehrere oder widersprüchliche Ziel-FPGAs."""

    def __init__(self, message: str, candidates: list[str]):
        super().__init__(message)
        self.candidates = candidates


@dataclass
class FpgaTarget:
    key: str
    source: str  # "request", "explicit" oder "default"


def detect_targets(text: str, registry_keys: list[str] | None = None) -> list[str]:
    """Alle in ``text`` genannten Board-Schlüssel in Nennungsreihenfolge."""
    lowered = (text or "").lower()
    hits: list[tuple[int, str]] = []
    keys = registry_keys or list(_ALIASES)
    for key in keys:
        patterns = _ALIASES.get(key, []) + [re.escape(key.lower())]
        positions = [m.start() for p in patterns for m in re.finditer(p, lowered)]
        if positions:
            hits.append((min(positions), key))
    return [key for _, key in sorted(hits)]


def resolve_fpga_target(
    request: str,
    registry_keys: list[str],
    explicit: str | None = None,
    default: str = "arty_s7_50",
) -> FpgaTarget:
    """Bestimmt das Ziel-FPGA.

    Reihenfolge: explizite Angabe > Nennung in der Anforderung > Default.
    Eine explizite Angabe, die der Anforderung widerspricht, und mehrere
    genannte Boards sind mehrdeutig.
    """
    mentioned = detect_targets(request, registry_keys)
    if explicit:
        if registry_keys and explicit not in registry_keys:
            raise AmbiguousTargetError(
                f"Unbekanntes Ziel-FPGA '{explicit}'. Bekannt: {', '.join(registry_keys)}",
                registry_keys,
            )
        if mentioned and explicit not in mentioned:
            raise AmbiguousTargetError(
                f"Ziel-FPGA '{explicit}' widerspricht der Anforderung ({', '.join(mentioned)})",
                [explicit, *mentioned],
            )
        return FpgaTarget(explicit, "explicit")
    if len(mentioned) > 1:
        raise AmbiguousTargetError(
            f"Die Anforderung nennt mehrere Ziel-FPGAs: {', '.join(mentioned)}",
            mentioned,
        )
    if mentioned:
        return FpgaTarget(mentioned[0], "request")
    return FpgaTarget(default, "default")
