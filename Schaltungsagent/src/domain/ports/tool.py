from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    success: bool = True
    output: str = ""
    error: str = ""
    data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "data": self.data,
        }


class Tool(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        ...

    @abstractmethod
    def execute(self, **kwargs) -> ToolResult:
        ...


class ToolRegistry(ABC):
    @abstractmethod
    def register(self, tool: Tool) -> None:
        ...

    @abstractmethod
    def unregister(self, tool_name: str) -> None:
        ...

    @abstractmethod
    def get_tool(self, name: str) -> Tool | None:
        ...

    @abstractmethod
    def list_tools(self) -> list[Tool]:
        ...


class ToolExecutor(ABC):
    @abstractmethod
    def execute(self, tool_name: str, **kwargs) -> ToolResult:
        ...

    @abstractmethod
    def execute_plan_step(self, step: dict[str, Any]) -> str:
        ...
