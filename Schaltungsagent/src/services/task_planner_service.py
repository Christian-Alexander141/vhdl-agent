import json
import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from src.services.opencode_agent_tool import get_default_tools, execute_tool_call

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


def execute_plan_step(step: dict[str, Any], tool_registry: list | None = None) -> str:
    tool_name = step.get("tool_name")
    if not tool_name:
        return f"No tool for step: {step.get('description', '')}"

    tools = tool_registry or get_default_tools()
    for t in tools:
        if getattr(t, "name", None) == tool_name:
            try:
                return str(t.invoke(step.get("arguments", {})))
            except Exception as e:
                return f"Tool {tool_name} error: {e}"

    raise TaskPlannerError(f"Tool '{tool_name}' not available")


class TaskPlannerService:
    def __init__(
        self,
        model_name: str = "gpt-oss:120b-cloud",
        base_url: str = "",
        api_key: str = "",
        max_steps: int = 5,
    ):
        self._model_name = model_name
        self._base_url = base_url
        self._api_key = api_key
        self._max_steps = max_steps

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

    def plan_and_execute(
        self,
        task: str,
        tools: list | None = None,
    ) -> dict[str, Any]:
        model = self._get_llm()
        if model is None:
            return {
                "status": "unavailable",
                "task": task,
                "message": "LLM not available",
            }

        tool_registry = tools or get_default_tools()
        bound = model.bind_tools(tool_registry)

        planner_messages = [
            SystemMessage(
                content=(
                    "You are a task planner. Respond only as JSON with a 'steps' field. "
                    "Each step has 'description', 'needs_tool', 'tool_name', and 'arguments'. "
                    "Plan the task and return the steps as JSON."
                )
            ),
            HumanMessage(content=f"Plan and execute this task: {task}"),
        ]

        try:
            planner_response = bound.invoke(planner_messages)
            plan_text = (
                planner_response.content
                if hasattr(planner_response, "content")
                else str(planner_response)
            )
            steps = parse_plan(plan_text)
        except TaskPlannerError as e:
            return {
                "status": "planning_failed",
                "task": task,
                "error": str(e),
            }
        except Exception as e:
            return {
                "status": "error",
                "task": task,
                "error": str(e),
            }

        executed_steps = []
        try:
            for step in steps[: self._max_steps]:
                if step.get("needs_tool"):
                    result = execute_plan_step(step, tool_registry)
                else:
                    result = "No tool needed"

                executed_steps.append({
                    "description": step.get("description", ""),
                    "tool_name": step.get("tool_name"),
                    "result": result,
                })
        except TaskPlannerError as e:
            executed_steps.append({"error": str(e)})

        follow_up = [
            SystemMessage(content="You are an assistant summarizing task results."),
            HumanMessage(
                content=(
                    f"Task: {task}\n"
                    f"Steps: {json.dumps(executed_steps, ensure_ascii=False)}"
                )
            ),
            AIMessage(content="Summarize the results."),
        ]

        try:
            final = bound.invoke(follow_up)
            summary = final.content if hasattr(final, "content") else str(final)
        except Exception as e:
            summary = f"Summary generation failed: {e}"

        return {
            "status": "completed",
            "task": task,
            "steps": executed_steps,
            "summary": summary,
        }
