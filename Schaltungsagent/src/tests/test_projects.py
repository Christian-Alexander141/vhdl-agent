import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.services.filesystem_service import LocalFileSystemService
from src.services.artifact_generator import VHDLArtifactGenerator
from src.domain.ports import OpenCodeService, OpenCodeResult
from src.domain.event_bus import EventBus
from src.orchestrator import SupervisorOrchestrator
from src.config import load_config


class MockOpenCodeService(OpenCodeService):
    def execute(self, project_path, instruction, timeout_seconds=300):
        return OpenCodeResult(returncode=0, stdout="Mock: OK", stderr="")


def make_agent(opencode_result=None):
    settings = load_config()
    event_bus = EventBus()
    opencode = MockOpenCodeService()
    return SupervisorOrchestrator(
        artifact_generator=VHDLArtifactGenerator(),
        filesystem_service=LocalFileSystemService(base_dir=settings.workspace.base_dir),
        opencode_service=opencode,
        event_publisher=event_bus,
        max_repair_iterations=settings.opencode.max_repair_iterations,
    )


TEST_CASES = [
    ("EN Counter", "8-bit counter with testbench", 2),
    ("DE Zähler", "VHDL Zähler 8 Bit mit Testbench", 2),
    ("DE Zaehler", "VHDL Zaehler", 2),
    ("No Match", "Create an AND gate in VHDL", 0),
    ("Short", "counter", 2),
    ("Empty", "", 0),
]


def test():
    passed = 0
    failed = 0

    for name, request, expected_files in TEST_CASES:
        agent = make_agent()
        result = agent.execute(request)
        count = len(result["generated_files"])
        ok = count == expected_files
        status = "PASS" if ok else "FAIL"
        if ok:
            passed += 1
        else:
            failed += 1

        ws = result.get("workspace", "?")
        files = ", ".join(result["generated_files"]) if result["generated_files"] else "\u2014"
        print(f"  [{status}] {name:15s} | files: {count} (expected {expected_files}) | {files}")

    print(f"\n{'='*50}")
    print(f"  {passed} passed, {failed} failed, {len(TEST_CASES)} total")
    print(f"{'='*50}")
    return failed == 0


if __name__ == "__main__":
    settings = load_config()
    projects_dir = settings.workspace.base_dir
    if os.path.exists(projects_dir):
        import shutil
        for d in os.listdir(projects_dir):
            shutil.rmtree(os.path.join(projects_dir, d))

    ok = test()
    sys.exit(0 if ok else 1)
