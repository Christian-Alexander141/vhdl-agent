import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from Schaltungsagent.evaluation.runner import ExperimentRunner


class SingleAgentStub:
    def execute(self, request: str, domain: str = "vhdl") -> dict:
        return {
            "status": "failed",
            "iterations": 1,
            "files": [],
            "workspace": "/tmp/single",
            "details": {"steps": [{"status": "failed"}]},
        }


class MultiAgentStub:
    def execute(self, request: str, domain: str = "vhdl") -> dict:
        return {
            "status": "completed",
            "iterations": 2,
            "files": ["src/top.vhd"],
            "workspace": "/tmp/multi",
            "details": {"steps": [{"status": "passed"}, {"status": "passed"}]},
        }


def test_multi_agent_benchmark_demonstrates_superiority(tmp_path):
    tasks = [{"id": "task_1", "name": "counter", "description": "Build a counter", "difficulty": 1}]
    architectures = [
        {"id": "single_agent", "name": "Single Agent", "description": "OpenCode only"},
        {"id": "multi_agent", "name": "Multi Agent", "description": "Supervisor + workers"},
    ]

    runner = ExperimentRunner(
        orchestrator={
            "single_agent": SingleAgentStub(),
            "multi_agent": MultiAgentStub(),
        },
        output_dir=str(tmp_path / "results"),
        runs_per_task=2,
    )

    results = runner.run_all(tasks=tasks, architectures=architectures)
    summary = runner.compare_architectures(results)

    assert len(results) == 4
    assert summary["winner"] == "multi_agent"
    assert summary["multi_agent"]["success_rate"] > summary["single_agent"]["success_rate"]
    assert summary["multi_agent"]["accepted_projects_per_hour"] > 0
    assert summary["single_agent"]["accepted_projects_per_hour"] >= 0

    summary_file = tmp_path / "results" / "summary.json"
    assert summary_file.exists()
    payload = json.loads(summary_file.read_text())
    assert any(item["architecture_id"] == "multi_agent" for item in payload)
