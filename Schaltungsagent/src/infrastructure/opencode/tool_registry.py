from typing import Any

from src.domain.ports.tool import Tool, ToolRegistry, ToolExecutor, ToolResult


class DefaultToolRegistry(ToolRegistry):
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def unregister(self, tool_name: str) -> None:
        self._tools.pop(tool_name, None)

    def get_tool(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[Tool]:
        return list(self._tools.values())


class DefaultToolExecutor(ToolExecutor):
    def __init__(self, registry: ToolRegistry):
        self._registry = registry

    def execute(self, tool_name: str, **kwargs) -> ToolResult:
        tool = self._registry.get_tool(tool_name)
        if tool is None:
            return ToolResult(success=False, error=f"Tool '{tool_name}' not available")
        try:
            return tool.execute(**kwargs)
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    def execute_plan_step(self, step: dict[str, Any]) -> str:
        tool_name = step.get("tool_name")
        if not tool_name:
            return f"No tool for step: {step.get('description', '')}"
        args = step.get("arguments", {})
        result = self.execute(tool_name, **args)
        return result.output if result.success else f"Tool {tool_name} error: {result.error}"
