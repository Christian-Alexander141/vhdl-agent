import json
import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from src.domain.ports import PlannerService
from src.domain.ports.tool import ToolRegistry, ToolExecutor

logger = logging.getLogger(__name__)


class TaskPlannerError(RuntimeError):
    pass


def parse_plan(response_text: str) -> list[dict[str, Any]]:
    try:
        payload = json.loads(response_text)
    except Exception as e:
        raise TaskPlannerError(f"Planner returned invalid JSON: {e}") from None
    if not isinstance(payload, dict):
        raise TaskPlannerError("Planner response was not an object")
    steps = payload.get("steps")
    if not isinstance(steps, list):
        raise TaskPlannerError("Planner response contains no steps list")
    return steps


class LangGraphPlannerAdapter(PlannerService):
    def __init__(
        self,
        model_name: str = "gpt-oss:120b-cloud",
        base_url: str = "",
        api_key: str = "",
        max_steps: int = 5,
        tool_executor: ToolExecutor | None = None,
    ):
        self._model_name = model_name
        self._base_url = base_url
        self._api_key = api_key
        self._max_steps = max_steps
        self._tool_executor = tool_executor

    def _get_llm(self):
        try:
            from langchain_ollama import ChatOllama
        except ImportError:
            logger.warning("langchain-ollama not installed")
            return None
        kwargs = {"model": self._model_name, "temperature": 0.2}
        if self._api_key:
            kwargs["base_url"] = "https://ollama.com"
            try:
                import httpx
                kwargs["http_client"] = httpx.Client(
                    headers={"Authorization": f"Bearer {self._api_key}"}
                )
            except ImportError:
                pass
        elif self._base_url:
            kwargs["base_url"] = self._base_url
        try:
            return ChatOllama(**kwargs)
        except Exception as e:
            logger.warning("Failed to create ChatOllama: %s", e)
            return None

    def analyze_task(self, task: str, context: dict | None = None) -> dict[str, Any]:
        model = self._get_llm()
        if model is None:
            return {"status": "unavailable", "task": task, "analysis": "LLM not available"}
        prompt = (
            f"Analyze the following engineering task and return a structured analysis as JSON.\n"
            f"Task: {task}\n"
            f"Context: {json.dumps(context or {})}\n"
            f"Analysis:"
        )
        try:
            response = model.invoke(prompt)
            text = response.content if hasattr(response, "content") else str(response)
            return {"status": "completed", "task": task, "analysis": text}
        except Exception as e:
            return {"status": "error", "task": task, "error": str(e)}

    def create_plan(self, task: str, context: dict | None = None) -> list[dict[str, Any]]:
        model = self._get_llm()
        if model is None:
            return [{"description": "LLM not available", "needs_tool": False}]
        messages = [
            SystemMessage(
                content=(
                    "You are a task planner. Respond only as JSON with a 'steps' field. "
                    "Each step has 'description', 'needs_tool', 'tool_name', and 'arguments'. "
                    "Plan the task and return the steps as JSON."
                )
            ),
            HumanMessage(
                content=f"Plan this task: {task}\nContext: {json.dumps(context or {})}"
            ),
        ]
        try:
            response = model.invoke(messages)
            text = response.content if hasattr(response, "content") else str(response)
            return parse_plan(text)
        except Exception as e:
            logger.error("Plan creation failed: %s", e)
            return [{"description": f"Planning failed: {e}", "needs_tool": False}]

    def execute_plan(
        self,
        plan: list[dict[str, Any]],
        tools: Any | None = None,
    ) -> dict[str, Any]:
        executed_steps = []
        for step in plan[:self._max_steps]:
            if step.get("needs_tool"):
                if self._tool_executor:
                    result = self._tool_executor.execute_plan_step(step)
                else:
                    result = "No tool executor available"
            else:
                result = "No tool needed"
            executed_steps.append({
                "description": step.get("description", ""),
                "tool_name": step.get("tool_name"),
                "result": result,
            })
        model = self._get_llm()
        summary = "No LLM available for summary"
        if model:
            try:
                follow_up = [
                    SystemMessage(content="You are an assistant summarizing task results."),
                    HumanMessage(
                        content=(
                            f"Task steps: {json.dumps(executed_steps, ensure_ascii=False)}"
                        )
                    ),
                ]
                final = model.invoke(follow_up)
                summary = final.content if hasattr(final, "content") else str(final)
            except Exception as e:
                summary = f"Summary failed: {e}"
        return {
            "status": "completed",
            "steps": executed_steps,
            "summary": summary,
        }
