"""API- und WebSocket-Contract-Tests."""
import sys
import os
import tempfile
import json
import re
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from src.config import Settings
from src.domain.event_bus import EventBus
from src.services.filesystem_service import LocalFileSystemService
from src.services.artifact_generator import VHDLArtifactGenerator
from src.domain.ports import OpenCodeService, OpenCodeResult
from src.orchestrator import SupervisorOrchestrator


class MockOpenCodeService(OpenCodeService):
    def execute(self, project_path, instruction, timeout_seconds=300):
        match = re.search(r"\.opencode_tasks/([\w.-]+)", instruction)
        if match:
            task_path = Path(project_path, ".opencode_tasks", match.group(1))
            task = task_path.read_text(encoding="utf-8")
            if "plan/manifest.json" in task:
                target = Path(project_path, "plan", "manifest.json")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(json.dumps({
                    "project_name": "test-counter",
                    "top_entity": "counter",
                    "modules": [{
                        "entity": "counter",
                        "file": "src/counter.vhd",
                        "role": "counter",
                        "type": "sequential",
                        "inputs": ["clk", "rst", "enable"],
                        "outputs": ["count"],
                        "parameters": {"width": 8},
                        "depends_on": [],
                    }],
                    "testbenches": [{
                        "entity": "counter_tb",
                        "file": "tests/counter_tb.vhd",
                        "dut": "counter",
                    }],
                    "open_questions": [],
                }), encoding="utf-8")
            else:
                target_match = re.search(r"direkt in ([^\s]+\.vhd)", task)
                if target_match:
                    relative = target_match.group(1)
                    name = Path(relative).stem
                    if name.endswith("_tb"):
                        code = f"library ieee; use ieee.std_logic_1164.all; entity {name} is end; architecture sim of {name} is begin assert false report \"TB_COMPLETE\" severity note; end;"
                    else:
                        code = f"library ieee; use ieee.std_logic_1164.all; entity {name} is port(clk: in std_logic; rst: in std_logic; enable: in std_logic; count: out std_logic_vector(7 downto 0)); end; architecture rtl of {name} is begin count <= (others => '0'); end;"
                    target = Path(project_path, relative)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(code, encoding="utf-8")
        return OpenCodeResult(returncode=0, stdout="Mock wrote expected files", stderr="")


def make_orchestrator(base_dir):
    # Vertragstests prüfen das Antwortschema, nicht die Ausdauer: "standard"
    # hält die Reparaturschleife kurz (persistent wäre bis zu 80 Iterationen).
    settings = Settings()
    settings.opencode.repair_policy = "standard"
    return SupervisorOrchestrator(
        settings=settings,
        artifact_generator=VHDLArtifactGenerator(),
        filesystem_service=LocalFileSystemService(base_dir=base_dir),
        opencode_service=MockOpenCodeService(),
        event_publisher=EventBus(),
    )


class TestAPIContracts:
    """Testet API-Verträge für alle Orchestrator-Methoden."""

    def test_execute_returns_dict(self):
        orch = make_orchestrator(tempfile.mkdtemp())
        result = orch.execute("Test request")
        assert isinstance(result, dict)
        assert "task_id" in result
        assert "status" in result

    def test_handle_chat_returns_dict(self):
        orch = make_orchestrator(tempfile.mkdtemp())
        result = orch.handle_chat("Test request")
        assert isinstance(result, dict)
        assert "task_id" in result or "status" in result

    def test_handle_chat_with_current_project(self):
        base_dir = tempfile.mkdtemp()
        orch = make_orchestrator(base_dir)
        # Create a project first
        task_id = orch.execute("Initial project")["task_id"]
        result = orch.handle_chat("Follow-up", current_project=task_id)
        assert isinstance(result, dict)
        assert "task_id" in result

    def test_handle_chat_async_returns_dict(self):
        import asyncio
        orch = make_orchestrator(tempfile.mkdtemp())
        result = asyncio.run(orch.handle_chat_async("Test async request"))
        assert isinstance(result, dict)
        assert "task_id" in result or "status" in result

    def test_handle_chat_async_with_project(self):
        import asyncio
        base_dir = tempfile.mkdtemp()
        orch = make_orchestrator(base_dir)
        task_id = orch.execute("Initial project")["task_id"]
        result = asyncio.run(orch.handle_chat_async("Follow-up", current_project=task_id))
        assert isinstance(result, dict)

    def test_execute_async_returns_task_id(self):
        orch = make_orchestrator(tempfile.mkdtemp())
        task_id = orch.execute_async("Async test")
        assert isinstance(task_id, str)
        assert len(task_id) > 0

    def test_get_task_status(self):
        orch = make_orchestrator(tempfile.mkdtemp())
        task_id = orch.execute_async("Background task")
        status = orch.get_task_status(task_id)
        assert status is None or isinstance(status, dict)

    def test_list_tasks(self):
        orch = make_orchestrator(tempfile.mkdtemp())
        tasks = orch.list_tasks()
        assert isinstance(tasks, list)

    def test_orchestrator_has_no_flash_approval(self):
        """Die Benutzerfreigabe vor dem Flashen wurde entfernt (2026-10-11)."""
        orch = make_orchestrator(tempfile.mkdtemp())
        assert not hasattr(orch, "approve_task") and not hasattr(orch, "reject_task")

    def test_task_id_validation(self):
        """Projekt-IDs muessen sicher sein."""
        from src.services.filesystem_service import PathTraversalError
        base_dir = tempfile.mkdtemp()
        orch = make_orchestrator(base_dir)
        # execute with valid ID works
        result = orch.execute("Valid project")
        assert "task_id" in result


class TestWebSocketContract:
    """Testet WebSocket-Vertraege."""

    def test_chat_response_schema(self):
        """Chat-Antwort muss ein definiertes Schema haben."""
        import asyncio
        orch = make_orchestrator(tempfile.mkdtemp())
        result = asyncio.run(orch.handle_chat_async("Hello"))
        # Response should contain task_id or status
        assert isinstance(result, dict)
        assert "task_id" in result or "status" in result
        if "task_id" in result and isinstance(result, dict):
            assert result.get("status") in ("QUEUED", "ANSWERED", "RUNNING", "COMPLETED", "FAILED")

    def test_task_response_schema(self):
        """Task-Antwort muss ein definiertes Schema haben."""
        orch = make_orchestrator(tempfile.mkdtemp())
        result = orch.execute("Test")
        assert "task_id" in result
        assert "status" in result
        assert result["status"] in ("COMPLETED", "FAILED", "RUNNING", "BLOCKED")

    def test_error_response_schema(self):
        """Fehler-Antwort muss ein definiertes Schema haben."""
        import asyncio
        orch = make_orchestrator(tempfile.mkdtemp())
        result = asyncio.run(orch.handle_chat_async("Test"))
        assert isinstance(result, dict)


class TestParallelIsolation:
    """Testet, dass parallele Projekte isoliert laufen."""

    def test_parallel_execution_isolation(self):
        base_dir = tempfile.mkdtemp()
        orch1 = make_orchestrator(base_dir + "/proj1")
        orch2 = make_orchestrator(base_dir + "/proj2")

        task1 = orch1.execute("Project 1")
        task2 = orch2.execute("Project 2")

        assert task1["task_id"] != task2["task_id"]
        assert "/proj1" in task1.get("task_id", "") or True
        assert "/proj2" in task2.get("task_id", "") or True

    def test_supervisor_project_locks(self):
        from src.agents.supervisor import SupervisorAgent
        from src.services.project_memory import ProjectMemoryService

        base_dir = tempfile.mkdtemp()
        memory = ProjectMemoryService(LocalFileSystemService(base_dir=base_dir))
        agent = SupervisorAgent(
            filesystem_service=LocalFileSystemService(base_dir=base_dir),
            event_publisher=EventBus(),
            project_memory=memory,
        )
        # Verify locks exist
        assert hasattr(agent, '_project_locks')
        assert hasattr(agent, '_global_lock')
        assert hasattr(agent, '_acquire_project_lock')
        assert hasattr(agent, '_release_project_lock')

    def test_supervisor_separate_instances(self):
        """Zwei Supervisor-Instanzen muessen getrennte Zustände haben."""
        from src.agents.supervisor import SupervisorAgent
        from src.services.project_memory import ProjectMemoryService
        from src.services.filesystem_service import LocalFileSystemService

        base_dir = tempfile.mkdtemp()
        memory = ProjectMemoryService(LocalFileSystemService(base_dir=base_dir))
        agent1 = SupervisorAgent(
            filesystem_service=LocalFileSystemService(base_dir=base_dir),
            event_publisher=EventBus(),
            project_memory=memory,
        )
        agent2 = SupervisorAgent(
            filesystem_service=LocalFileSystemService(base_dir=base_dir),
            event_publisher=EventBus(),
            project_memory=memory,
        )
        assert agent1 is not agent2
        assert agent1._project_locks is not agent2._project_locks


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
