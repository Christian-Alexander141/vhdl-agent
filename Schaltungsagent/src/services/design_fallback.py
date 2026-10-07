"""Small, conservative fallback boundary for the existing deterministic templates."""
from __future__ import annotations

from abc import ABC, abstractmethod

from src.services.deterministic_design import DeterministicDesignService


class DesignFallbackProvider(ABC):
    @abstractmethod
    def module_vhdl(self, request_full: str, entity: str) -> str | None:
        ...

    @abstractmethod
    def testbench_vhdl(self, request_full: str, entity: str) -> str | None:
        ...

    @abstractmethod
    def top_vhdl(self, request_full: str, plan: dict) -> str | None:
        ...


class RuleBasedFallback(DesignFallbackProvider):
    """Transition fallback; deliberately declines long and ambiguous requests."""

    def __init__(self, deterministic: DeterministicDesignService | None = None):
        self._design = deterministic or DeterministicDesignService()

    @staticmethod
    def _safe(request_full: str) -> bool:
        if len(request_full.encode("utf-8")) > 500:
            return False
        patterns = {
            "lauflicht": ("lauflicht", "running light", "running_light", "shift register"),
            "comparator": ("vergleicher", "vergleich", "comparator"),
            "counter": ("zaehler", "zähler", "counter", "binärzähler"),
        }
        matched = [
            key for key, terms in patterns.items()
            if any(term in request_full.lower() for term in terms)
        ]
        return len(matched) == 1

    def module_vhdl(self, request_full: str, entity: str) -> str | None:
        if not self._safe(request_full):
            return None
        return self._design.module_vhdl(request_full, "", entity)

    def testbench_vhdl(self, request_full: str, entity: str) -> str | None:
        if not self._safe(request_full):
            return None
        return self._design.testbench_vhdl(request_full, "", entity)

    def top_vhdl(self, request_full: str, plan: dict) -> str | None:
        if not self._safe(request_full):
            return None
        modules = plan.get("modules", [])
        top = plan.get("top_entity", "")
        return self._design.top_module_vhdl(request_full, "", modules, top)