#!/usr/bin/env python3
"""
Self-healing launcher for the AI Engineer Platform.

On startup failure, writes a structured error log to log.md,
then dispatches a LangGraph agent that uses OpenCode to fix the error,
and retries automatically.
"""

import os
import sys
import shutil
import json
import subprocess
import traceback
from datetime import datetime, timezone
from pathlib import Path


LOG_FILE = Path(__file__).parent / "log.md"


def write_error_log(error: Exception) -> dict:
    tb = traceback.format_exc()
    error_info = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "type": type(error).__name__,
        "message": str(error),
        "traceback": tb,
        "python_version": sys.version,
        "platform": sys.platform,
        "cwd": str(Path.cwd()),
        "argv": sys.argv,
    }

    log_entry = f"""# Error Log

**Timestamp:** {error_info['timestamp']}
**Type:** {error_info['type']}
**Message:** {error_info['message']}

## Traceback

```
{error_info['traceback']}
```

## Environment

- Python: {error_info['python_version']}
- Platform: {error_info['platform']}
- CWD: {error_info['cwd']}
- Args: {error_info['argv']}

---
"""

    existing = ""
    if LOG_FILE.exists():
        existing = LOG_FILE.read_text(encoding="utf-8")

    LOG_FILE.write_text(log_entry + "\n" + existing, encoding="utf-8")
    print(f"[launcher] Error logged to {LOG_FILE}")
    return error_info


def run_opencode(task: str, project_path: str = ".", timeout: int = 300) -> dict:
    binary = shutil.which("opencode")
    if not binary:
        return {"status": "unavailable", "message": "opencode CLI not found"}

    cmd = [binary, "run", task]
    print(f"[launcher] Running: {' '.join(cmd)}")

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=project_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        output_lines: list[str] = []
        import time as _time
        deadline = _time.time() + timeout

        while True:
            line = proc.stdout.readline()
            if line:
                output_lines.append(line.rstrip())
                print(f"  [opencode] {line.rstrip()}")
            if proc.poll() is not None:
                break
            if _time.time() > deadline:
                proc.terminate()
                _time.sleep(2)
                if proc.poll() is None:
                    proc.kill()
                return {
                    "status": "timeout",
                    "message": f"Task timed out after {timeout}s",
                    "output": "\n".join(output_lines),
                }
            _time.sleep(0.2)

        exit_code = proc.returncode
        output = "\n".join(output_lines)
        status = "completed" if exit_code == 0 else "failed"
        return {
            "status": status,
            "exit_code": exit_code,
            "output": output,
            "message": f"Exit code {exit_code}",
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}


def build_fix_prompt(error_info: dict) -> str:
    return f"""Fix the following Python error in the AI Engineer Platform project.

Error Type: {error_info['type']}
Error Message: {error_info['message']}

Traceback:
```
{error_info['traceback']}
```

The project is located at {Path(__file__).parent}.
Analyze the error and fix the root cause. Do NOT modify launcher.py itself.
After fixing, verify the fix by running: python -c "from src.main import main; print('OK')"
"""


def dispatch_self_healing(error_info: dict) -> bool:
    if shutil.which("opencode") is None:
        print("[launcher] opencode CLI not available — skipping self-healing")
        return False

    try:
        from langgraph.graph import StateGraph, MessagesState, START
        from langchain_core.tools import tool
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_ollama import ChatOllama
    except ImportError:
        print("[launcher] LangGraph or ChatOllama not available — using direct OpenCode repair")
        task = build_fix_prompt(error_info)
        result = run_opencode(task, timeout=600)
        if result.get("status") == "completed":
            print("[launcher] OpenCode repair completed")
            return True
        print(f"[launcher] OpenCode repair failed: {result.get('message')}")
        return False

    @tool
    def opencode_fix(fix_instruction: str) -> str:
        """Send a fix instruction to OpenCode CLI for automated code repair."""
        result = run_opencode(fix_instruction, timeout=600)
        return json.dumps(result, ensure_ascii=False)

    @tool
    def read_log() -> str:
        """Read the current error log content."""
        if LOG_FILE.exists():
            return LOG_FILE.read_text(encoding="utf-8")
        return "No log file found."

    @tool
    def verify_fix() -> str:
        """Verify that the fix resolved the error by attempting an import."""
        try:
            result = subprocess.run(
                [sys.executable, "-c", "from src.main import main; print('OK')"],
                cwd=Path(__file__).parent,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                return f"VERIFIED: Import successful.\n{result.stdout}"
            return f"STILL BROKEN: {result.stderr[:1000]}"
        except subprocess.TimeoutExpired:
            return "TIMEOUT: Verification timed out"

    tools = [opencode_fix, read_log, verify_fix]

    try:
        model_name = os.environ.get("OLLAMA_MODEL", "gpt-oss:120b-cloud")
        llm = ChatOllama(model=model_name, temperature=0.1)
    except Exception:
        print("[launcher] Failed to create ChatOllama — using direct OpenCode repair")
        task = build_fix_prompt(error_info)
        result = run_opencode(task, timeout=600)
        return result.get("status") == "completed"

    llm_with_tools = llm.bind_tools(tools)

    def agent_node(state: MessagesState) -> dict:
        messages = state["messages"]
        response = llm_with_tools.invoke(messages)
        return {"messages": [response]}

    graph = StateGraph(MessagesState)
    graph.add_node("agent", agent_node)
    graph.add_edge(START, "agent")
    graph.set_finish_point("agent")
    runnable = graph.compile()

    system_msg = SystemMessage(
        content=f"""You are an autonomous repair agent for the AI Engineer Platform.
Your task is to fix the error described below.

Available tools:
- opencode_fix: Send an instruction to OpenCode CLI to edit source files
- read_log: Read the error log
- verify_fix: Test if the import now works

Analyze the error, propose a fix, use opencode_fix to apply it,
then verify with verify_fix. If verification fails, try again.

Error: {error_info['type']}: {error_info['message']}

Project root: {Path(__file__).parent}
"""
    )

    human_msg = HumanMessage(
        content=f"Fix this error: {error_info['type']}: {error_info['message']}"
    )

    try:
        for chunk in runnable.stream({"messages": [system_msg, human_msg]}):
            if "__end__" in chunk:
                continue
            for node_name, node_data in chunk.items():
                msgs = node_data.get("messages", [])
                for m in msgs:
                    if hasattr(m, "content") and m.content:
                        print(f"  [{node_name}] {m.content[:200]}")
                    if hasattr(m, "tool_calls") and m.tool_calls:
                        for tc in m.tool_calls:
                            print(f"  [{node_name}] tool: {tc.get('name', '?')}")

        final_verify = subprocess.run(
            [sys.executable, "-c", "from src.main import main; print('OK')"],
            cwd=Path(__file__).parent,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return final_verify.returncode == 0

    except Exception as e:
        print(f"[launcher] Self-healing agent failed: {e}")
        return False


def main():
    log_file = LOG_FILE
    print(f"[launcher] Starting AI Engineer Platform (log: {log_file})")

    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            from src.main import main as platform_main
            platform_main()
            return 0

        except SystemExit as e:
            return e.code if isinstance(e.code, int) else 0

        except Exception as e:
            print(f"\n[launcher] Attempt {attempt}/{max_retries} FAILED: {type(e).__name__}: {e}")

            error_info = write_error_log(e)

            if attempt < max_retries:
                print(f"[launcher] Starting self-healing (attempt {attempt})...")
                fixed = dispatch_self_healing(error_info)
                if fixed:
                    print("[launcher] Fix applied — retrying...")
                    continue
                else:
                    print("[launcher] Self-healing failed or unavailable")
                    break
            else:
                print("[launcher] Max retries reached. Giving up.")
                break

    print(f"[launcher] Failed after {max_retries} attempts. See {log_file} for details.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
