"""Projektfragen im Chat werden von OpenCode beantwortet (Ollama entfernt)."""
from pathlib import Path

from src.domain.ports import OpenCodeResult
from src.services.project_chat import OpenCodeProjectChat, clean_answer


class FakeOpenCode:
    def __init__(self, result=None, error=None, touch=None):
        self.result, self.error, self.touch = result, error, touch
        self.calls = []

    def execute(self, workspace, instruction, timeout_seconds=None):
        self.calls.append((workspace, instruction))
        if self.touch:
            (Path(workspace) / self.touch).write_text("geändert")
        if self.error:
            raise self.error
        return self.result


def _ws(tmp_path):
    (tmp_path / "src").mkdir(exist_ok=True)
    (tmp_path / "src" / "ampel.vhd").write_text("entity ampel is end;")
    return {"workspace": str(tmp_path), "status": "COMPLETED"}


def test_answer_comes_from_opencode_in_the_project_folder(tmp_path):
    output = "\x1b[0m> build · muse\n→ Read src/ampel.vhd\nDie Ampel hat acht Phasen.\nGrün dauert 30 s."
    oc = FakeOpenCode(OpenCodeResult(0, output, ""))
    answer = OpenCodeProjectChat(oc).answer_question("Wie viele Phasen?", _ws(tmp_path))
    assert answer == "Die Ampel hat acht Phasen.\nGrün dauert 30 s."
    workspace, instruction = oc.calls[0]
    assert workspace == str(tmp_path) and "Wie viele Phasen?" in instruction and "KEINE Dateien" in instruction


def test_changed_files_are_reported(tmp_path):
    oc = FakeOpenCode(OpenCodeResult(0, "Antwort.", ""), touch="src/ampel.vhd")
    answer = OpenCodeProjectChat(oc).answer_question("?", _ws(tmp_path))
    assert "Dateien verändert" in answer and "src/ampel.vhd" in answer


def test_failures_give_a_clear_message(tmp_path):
    rate = FakeOpenCode(OpenCodeResult(1, "Error: Rate limit exceeded. Please try again later.", ""))
    assert "nicht beantworten" in OpenCodeProjectChat(rate).answer_question("?", _ws(tmp_path))
    boom = FakeOpenCode(error=RuntimeError("weg"))
    assert "nicht beantworten" in OpenCodeProjectChat(boom).answer_question("?", _ws(tmp_path))


def test_missing_workspace_is_answered_without_opencode():
    oc = FakeOpenCode()
    answer = OpenCodeProjectChat(oc).answer_question("?", {"workspace": "", "status": "FAILED"})
    assert "FAILED" in answer and oc.calls == []


def test_clean_answer_drops_tool_lines():
    assert clean_answer("$ ls\n✱ Glob\nNur das.") == "Nur das."
