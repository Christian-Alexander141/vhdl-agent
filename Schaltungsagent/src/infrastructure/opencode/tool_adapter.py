import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from src.domain.ports.tool import Tool, ToolResult

try:
    from langchain_core.tools import tool as _langchain_tool
    HAS_LANGCHAIN = True
except ImportError:
    HAS_LANGCHAIN = False


class OpenCodeToolAdapter(Tool):
    def __init__(self, binary: str = "opencode"):
        self._binary = binary

    @property
    def name(self) -> str:
        return "dispatch_opencode"

    @property
    def description(self) -> str:
        return (
            "Send a task to OpenCode CLI for automated execution. "
            "Use this tool when a file operation, code generation, or system "
            "administration task requires elevated filesystem access or a "
            "dedicated agent session."
        )

    def execute(self, task: str, project_path: str | None = None,
                timeout_seconds: int = 600, model: str | None = None) -> ToolResult:
        project_dir = Path(project_path or ".").resolve()
        cli_path = shutil.which(self._binary)
        if cli_path is None:
            return ToolResult(
                success=False,
                error=f"OpenCode CLI '{self._binary}' not found on PATH.",
            )
        command = [self._binary, "run", task]
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
            return ToolResult(success=False, error=str(exc))
        output_lines = []
        started_at = time.time()
        while True:
            if process.stdout is not None:
                line = process.stdout.readline()
                if line:
                    output_lines.append(line.rstrip())
                    continue
            if process.poll() is not None:
                break
            if timeout_seconds and (time.time() - started_at) > timeout_seconds:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                return ToolResult(success=False, error="Timed out",
                                 output="\n".join(output_lines))
            time.sleep(0.2)
        exit_code = getattr(process, "returncode", None) or 0
        return ToolResult(
            success=exit_code == 0,
            output="\n".join(output_lines),
            data={"exit_code": exit_code},
        )

    def to_langchain_tool(self):
        if not HAS_LANGCHAIN:
            return None

        @_langchain_tool
        def dispatch_opencode(
            task: str,
            project_path: str | None = None,
            timeout_seconds: int = 600,
            model: str | None = None,
        ) -> str:
            result = self.execute(
                task=task,
                project_path=project_path,
                timeout_seconds=timeout_seconds,
                model=model,
            )
            return json.dumps(result.to_dict(), ensure_ascii=False)

        return dispatch_opencode


class ReadFileToolAdapter(Tool):
    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return "Read the contents of a file from the filesystem."

    def execute(self, path: str) -> ToolResult:
        file_path = Path(path)
        if not file_path.exists():
            return ToolResult(success=False, error=f"File not found: {path}")
        try:
            content = file_path.read_text(encoding="utf-8")
            return ToolResult(output=content, data={"path": path})
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    def to_langchain_tool(self):
        if not HAS_LANGCHAIN:
            return None

        @_langchain_tool
        def read_file_tool(path: str) -> str:
            result = self.execute(path=path)
            return result.output if result.success else result.error

        return read_file_tool


class WriteFileToolAdapter(Tool):
    @property
    def name(self) -> str:
        return "write_file"

    @property
    def description(self) -> str:
        return "Write content to a file on the filesystem."

    def execute(self, path: str, content: str) -> ToolResult:
        file_path = Path(path)
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")
            return ToolResult(output=f"File saved: {file_path}", data={"path": str(file_path)})
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    def to_langchain_tool(self):
        if not HAS_LANGCHAIN:
            return None

        @_langchain_tool
        def write_file_tool(path: str, content: str) -> str:
            result = self.execute(path=path, content=content)
            return result.output if result.success else result.error

        return write_file_tool
