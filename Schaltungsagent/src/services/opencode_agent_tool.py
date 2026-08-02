import json
import shutil
import subprocess
import time
import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


def run_opencode_task(
    task: str,
    project_path: str | Path | None = None,
    timeout_seconds: int = 600,
    model: str | None = None,
) -> dict[str, Any]:
    project_dir = Path(project_path or ".").resolve()
    cli_path = shutil.which("opencode")
    if cli_path is None:
        return {
            "status": "unavailable",
            "message": "OpenCode CLI not found on PATH.",
            "output": "",
            "exit_code": None,
        }

    command = ["opencode", "run", task]
    if model:
        command.extend(["--model", model])

    try:
        process = subprocess.Popen(
            command,
            cwd=str(project_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except Exception as exc:
        return {
            "status": "failed",
            "message": f"Unable to start OpenCode: {exc}",
            "output": "",
            "exit_code": None,
        }

    output_lines: list[str] = []
    started_at = time.time()

    while True:
        if process.stdout is not None:
            line = process.stdout.readline()
            if line:
                output_lines.append(line.rstrip())
                continue

        if process.poll() is not None:
            break

        if timeout_seconds is not None and (time.time() - started_at) > timeout_seconds:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            return {
                "status": "timeout",
                "message": f"OpenCode task exceeded timeout of {timeout_seconds}s.",
                "output": "\n".join(output_lines),
                "exit_code": process.returncode,
            }

        time.sleep(0.2)

    exit_code = getattr(process, "returncode", None) or 0

    if exit_code == 0:
        return {
            "status": "completed",
            "message": "OpenCode task completed successfully.",
            "output": "\n".join(output_lines),
            "exit_code": exit_code,
        }

    return {
        "status": "failed",
        "message": "OpenCode task finished with an error.",
        "output": "\n".join(output_lines),
        "exit_code": exit_code,
    }


try:
    from langchain_core.tools import tool as _langchain_tool

    @_langchain_tool
    def dispatch_opencode(
        task: str,
        project_path: Optional[str] = None,
        timeout_seconds: int = 600,
        model: Optional[str] = None,
    ) -> str:
        """Send a task to OpenCode CLI for automated execution.

        Use this tool when a file operation, code generation, or system
        administration task requires elevated filesystem access or a
        dedicated agent session.

        Args:
            task: The task description for OpenCode
            project_path: Working directory (default: current dir)
            timeout_seconds: Maximum execution time (default: 600)
            model: Model name override
        """
        result = run_opencode_task(
            task=task,
            project_path=project_path,
            timeout_seconds=timeout_seconds,
            model=model,
        )
        return json.dumps(result, ensure_ascii=False)

    @_langchain_tool
    def read_file_tool(path: str) -> str:
        """Read the contents of a file from the filesystem.

        Args:
            path: Path to the file (relative or absolute)
        """
        file_path = Path(path)
        if not file_path.exists():
            return f"File not found: {path}"
        try:
            return file_path.read_text(encoding="utf-8")
        except Exception as e:
            return f"Error reading {path}: {e}"

    @_langchain_tool
    def write_file_tool(path: str, content: str) -> str:
        """Write content to a file on the filesystem.

        Args:
            path: Path where to write the file
            content: Content to write
        """
        file_path = Path(path)
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")
            return f"File saved: {file_path}"
        except Exception as e:
            return f"Error writing {path}: {e}"

    def get_default_tools() -> list:
        return [dispatch_opencode, read_file_tool, write_file_tool]

    def execute_tool_call(tool_call: Any, tools: list) -> str:
        name = (
            getattr(tool_call, "name", None)
            or (tool_call.get("name") if isinstance(tool_call, dict) else None)
        )
        args = (
            getattr(tool_call, "args", None)
            or (tool_call.get("args", {}) if isinstance(tool_call, dict) else {})
        )
        if not isinstance(args, dict):
            args = {}

        for t in tools:
            if getattr(t, "name", None) == name:
                try:
                    return str(t.invoke(args))
                except Exception as e:
                    return f"Tool {name} error: {e}"
        return f"Tool '{name}' not available."

except ImportError:
    def get_default_tools() -> list:
        return []

    def execute_tool_call(tool_call: Any, tools: list) -> str:
        return "Tools unavailable"
