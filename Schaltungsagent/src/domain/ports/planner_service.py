from abc import ABC, abstractmethod
from typing import Any


class PlannerService(ABC):
    @abstractmethod
    def analyze_task(self, task: str, context: dict | None = None) -> dict[str, Any]:
        ...

    @abstractmethod
    def create_plan(self, task: str, context: dict | None = None) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    def execute_plan(
        self,
        plan: list[dict[str, Any]],
        tools: Any | None = None,
    ) -> dict[str, Any]:
        ...
