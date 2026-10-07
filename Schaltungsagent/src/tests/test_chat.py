import sys
import os
import shutil
import tempfile
import json
import re
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.domain.event_bus import EventBus
from src.domain.ports import OpenCodeService, OpenCodeResult
from src.services.chat_router import ChatRouter
from src.services.filesystem_service import LocalFileSystemService
from src.services.artifact_generator import VHDLArtifactGenerator
from src.orchestrator import SupervisorOrchestrator


class MockOpenCodeService(OpenCodeService):
    def execute(self, project_path, instruction, timeout_seconds=300):
        task_match = re.search(r"\.opencode_tasks/([\w.-]+)", instruction)
        if task_match:
            task = Path(project_path, ".opencode_tasks", task_match.group(1)).read_text()
            if "plan/manifest.json" in task:
                target = Path(project_path, "plan", "manifest.json")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(json.dumps({
                    "project_name": "zaehler-projekt",
                    "top_entity": "zaehler",
                    "modules": [{
                        "entity": "zaehler",
                        "file": "src/zaehler.vhd",
                        "role": "8-bit counter",
                        "type": "sequential",
                        "inputs": ["clk", "rst", "enable"],
                        "outputs": ["count"],
                        "parameters": {"width": 8},
                        "depends_on": [],
                    }],
                    "testbenches": [{
                        "entity": "zaehler_tb",
                        "file": "tests/zaehler_tb.vhd",
                        "dut": "zaehler",
                    }],
                    "open_questions": [],
                }), encoding="utf-8")
            else:
                target_match = re.search(r"direkt in ([^\s]+\.vhd)", task)
                if target_match:
                    relative = target_match.group(1)
                    name = Path(relative).stem
                    if name.endswith("_tb"):
                        code = f"library ieee; use ieee.std_logic_1164.all; entity {name} is end entity {name}; architecture sim of {name} is begin assert false report \"TB_COMPLETE\" severity note; end architecture sim;"
                    else:
                        code = f"library ieee; use ieee.std_logic_1164.all; entity {name} is port(clk: in std_logic; rst: in std_logic; enable: in std_logic; count: out std_logic_vector(7 downto 0)); end entity {name}; architecture rtl of {name} is begin count <= (others => '0'); end architecture rtl;"
                    target = Path(project_path, relative)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(code, encoding="utf-8")
        return OpenCodeResult(returncode=0, stdout="Mock wrote expected files", stderr="")


def _vivado_available() -> bool:
    """Erkennung einer nutzbaren Vivado-Toolchain für den Hardware-E2E-Pfad.

    Die End-to-End-Tests (vollständiger COMPLETED-Durchlauf inkl. Bitstream,
    Flash und Hardware-Test) benötigen eine echte, ausgesourcte Vivado-
    Umgebung und ein verbundenes FPGA. Ist sie nicht vorhanden, werden diese
    Tests übersprungen statt zu scheitern.
    """
    if os.environ.get("VHDLAGENT_TEST_HARDWARE", "").lower() in {"1", "true", "yes"}:
        return True
    if shutil.which("vivado"):
        return True
    settings = os.environ.get("VIVADO_SETTINGS", "")
    if settings:
        return os.path.isfile(settings)
    return False


VIVADO_UNAVAILABLE = not _vivado_available()
HARDWARE_E2E_REASON = (
    "Hardware-E2E (Synthese/Flash) benötigt eine ausgesourcte Vivado-"
    "Toolchain und ein verbundenes FPGA; setze VHDLAGENT_TEST_HARDWARE=1 "
    "zum Erzwingen"
)


def make_agent(base_dir):
    return SupervisorOrchestrator(
        artifact_generator=VHDLArtifactGenerator(),
        filesystem_service=LocalFileSystemService(base_dir=base_dir),
        opencode_service=MockOpenCodeService(),
        event_publisher=EventBus(),
        max_repair_iterations=2,
    )


def test_classify_new_project():
    route = ChatRouter().route("bau mir einen 8-bit Zähler", None)
    assert route.kind == "new_project"


def test_classify_resume():
    route = ChatRouter().route(
        "docker war nicht aktiv, versuch nochmal das Projekt zu bauen",
        "zaehler-abc123",
    )
    assert route.kind == "change"
    assert route.project_id == "zaehler-abc123"


def test_classify_question():
    route = ChatRouter().route("was macht der Zähler?", "zaehler-abc123")
    assert route.kind == "question"
    assert route.project_id == "zaehler-abc123"


@pytest.mark.skipif(VIVADO_UNAVAILABLE, reason=HARDWARE_E2E_REASON)
def test_chat_new_project_creates_memory():
    tmp = tempfile.mkdtemp()
    try:
        agent = make_agent(os.path.join(tmp, "projects"))
        result = agent.handle_chat("bau einen Zähler mit Testbench")
        assert result["type"] == "new_project"
        assert result["status"] == "COMPLETED"
        memory_path = os.path.join(tmp, "projects", result["task_id"], "memory.md")
        assert os.path.exists(memory_path)
        content = open(memory_path).read()
        assert "Gedächtnis" in content
        assert content.count("### ") == 2  # user + assistant entry
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@pytest.mark.skipif(VIVADO_UNAVAILABLE, reason=HARDWARE_E2E_REASON)
def test_chat_resume_uses_same_project():
    tmp = tempfile.mkdtemp()
    try:
        agent = make_agent(os.path.join(tmp, "projects"))
        first = agent.handle_chat("bau einen Zähler mit Testbench")
        project_id = first["task_id"]

        second = agent.handle_chat(
            "docker war nicht aktiv, versuch jetzt nochmal das Projekt zu bauen",
            current_project=project_id,
        )
        assert second["type"] == "resume"
        assert second["task_id"] == project_id
        assert second["status"] == "COMPLETED"
        assert second["workspace"] == first["workspace"]

        memory_path = os.path.join(tmp, "projects", project_id, "memory.md")
        content = open(memory_path).read()
        assert content.count("### ") == 4  # two user/assistant pairs
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@pytest.mark.skipif(VIVADO_UNAVAILABLE, reason=HARDWARE_E2E_REASON)
def test_chat_question_answers_without_new_workspace():
    tmp = tempfile.mkdtemp()
    try:
        agent = make_agent(os.path.join(tmp, "projects"))
        first = agent.handle_chat("bau einen Zähler mit Testbench")
        project_id = first["task_id"]

        result = agent.handle_chat(
            "was macht der Zähler?", current_project=project_id
        )
        assert result["type"] == "question"
        assert result["project_id"] == project_id
        assert result["status"] == "ANSWERED"
        assert result["answer"]
        # no new project workspace created
        workspaces = os.listdir(os.path.join(tmp, "projects"))
        assert workspaces == [project_id]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@pytest.mark.skipif(VIVADO_UNAVAILABLE, reason=HARDWARE_E2E_REASON)
def test_memory_load_entries():
    tmp = tempfile.mkdtemp()
    try:
        agent = make_agent(os.path.join(tmp, "projects"))
        result = agent.handle_chat("bau einen Zähler")
        workspace = result["workspace"]
        agent._memory.append(workspace, "user", "Frage eins")
        agent._memory.append(workspace, "assistant", "Antwort eins")
        entries = agent._memory.load_entries(workspace)
        roles = [e["role"] for e in entries]
        assert "assistant" in roles
        assert any("Antwort eins" in e["content"] for e in entries)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_deterministic_pipeline_reaches_ghdl_verification():
    """Deterministischer Kern des Flow ohne Hardware-Umgebung.

    Architektur → TaskGraph-Implementierung → GHDL-Statik → GHDL-Simulation
    müssen ohne LLM (Stub) und ohne Vivado deterministisch funktionieren.
    Der strikte Hardware-Pfad (Synthese/Flash) endet in der Test-Umgebung
    erst nach der Simulation; geprüft wird der verifizierbare Teil.
    """
    import json

    tmp = tempfile.mkdtemp()
    try:
        base = os.path.join(tmp, "projects")
        agent = make_agent(base)
        result = agent.handle_chat("bau einen Zähler")
        task_id = result["task_id"]
        workspace = os.path.join(base, task_id)

        # TaskGraph wurde persistiert (Modul-Tasks + File-Ownership)
        graph_path = os.path.join(workspace, "task_graph.json")
        assert os.path.exists(graph_path), "task_graph.json muss persistiert sein"
        graph = json.load(open(graph_path))
        assert graph["tasks"], "TaskGraph muss implementierte Tasks enthalten"
        assert any(
            t.startswith("implement_module_") for t in graph["tasks"]
        ), "Modul-Implementierungs-Tasks fehlen"

        # Deterministisch erzeugte VHDL-Dateien (Src + Testbench)
        src_files = os.listdir(os.path.join(workspace, "src"))
        assert src_files, "src/ muss VHDL-Dateien enthalten"
        assert os.path.exists(os.path.join(workspace, "tests")), \
            "tests/ muss die Testbench enthalten"

        # GHDL-Verifikation besteht deterministisch (Simulation PASS)
        from src.infrastructure.validation.ghdl_validator import GHDLValidator
        validation = GHDLValidator().validate(workspace)
        assert validation.passed, f"GHDL validation failed: {validation.message}"

        # Design-State: Simulation war PASS (strikter Flow endet erst in Synthese)
        state_content = open(os.path.join(workspace, "design_state.yaml")).read()
        assert "status: passed" in state_content, \
            "Verification-Status muss 'passed' festgehalten sein"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_delete_project_only_deletes_target():
    import asyncio
    import importlib

    tmp = tempfile.mkdtemp()
    try:
        spec = importlib.util.spec_from_file_location(
            "api_server", os.path.join(os.path.dirname(__file__), "..", "api_server.py")
        )
        server = importlib.util.module_from_spec(spec)
        sys.modules["api_server"] = server
        spec.loader.exec_module(server)

        base = os.path.join(tmp, "projects")
        server.settings.workspace.base_dir = base
        server.fs = LocalFileSystemService(base_dir=base)
        server.fs.create_workspace("projekt-a")
        server.fs.create_workspace("projekt-b")

        response = asyncio.run(server.delete_project("projekt-a"))
        assert response.status_code == 200
        assert response.body
        remaining = server.fs.list_workspaces()
        assert remaining == ["projekt-b"]
        assert "projekt-a" not in remaining
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_delete_project_rejects_invalid_name():
    import asyncio
    import importlib

    tmp = tempfile.mkdtemp()
    try:
        spec = importlib.util.spec_from_file_location(
            "api_server2", os.path.join(os.path.dirname(__file__), "..", "api_server.py")
        )
        server = importlib.util.module_from_spec(spec)
        sys.modules["api_server2"] = server
        spec.loader.exec_module(server)

        base = os.path.join(tmp, "projects")
        server.settings.workspace.base_dir = base
        server.fs = LocalFileSystemService(base_dir=base)
        server.fs.create_workspace("projekt-a")

        response = asyncio.run(server.delete_project(".."))
        assert response.status_code == 400
        # nothing was deleted
        assert server.fs.list_workspaces() == ["projekt-a"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
            print(f"  [PASS] {t.__name__}")
        except AssertionError as e:
            print(f"  [FAIL] {t.__name__}: {e}")
        except Exception as e:
            print(f"  [ERROR] {t.__name__}: {e}")
    print(f"\n  {passed}/{len(tests)} passed")
    return passed == len(tests)


if __name__ == "__main__":
    ok = test()
    sys.exit(0 if ok else 1)
