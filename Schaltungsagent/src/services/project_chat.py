"""Projektfragen im Chat beantworten – mit OpenCode statt eines separaten Sprachmodells.

Früher beantwortete ein eigenes Ollama-LLM die Fragen anhand eines
JSON-Auszugs des Projektzustands (Relikt aus der RAG-Zeit). OpenCode läuft
ohnehin für alle Entwurfsaufgaben und kann im Projektordner den echten Code,
design_state.yaml und die Berichte lesen. Der Auftrag ist ausdrücklich
lesend; ändert OpenCode trotzdem Dateien, wird das gemeldet.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

ANSWER_TIMEOUT_S = 300
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
# Fortschrittszeilen von "opencode run" (Werkzeugaufrufe, Agent-Kopfzeile)
_TOOL_LINE = re.compile(r"^\s*(?:[→✱✗$>]|\| |build ·|plan ·)")

INSTRUCTION = (
    "Beantworte die folgende Frage zu dem VHDL-Projekt in diesem Ordner auf Deutsch, knapp und "
    "verständlich. Lies dazu bei Bedarf PROMPT.md, design_state.yaml, src/, tests/ und reports/. "
    "Ändere, erstelle oder lösche KEINE Dateien und führe keine Synthese oder Simulation aus. "
    "Zitiere keinen vollständigen Code; erkläre das Design.\n\nFrage: {question}"
)


def clean_answer(output: str) -> str:
    lines = [_ANSI.sub("", line).rstrip() for line in (output or "").splitlines()]
    kept = [line for line in lines if line.strip() and not _TOOL_LINE.match(line)]
    return "\n".join(kept).strip()


def _snapshot(workspace: Path) -> dict[str, float]:
    from src.services.opencode_task_runner import _snapshot as task_snapshot
    return task_snapshot(workspace)


class OpenCodeProjectChat:
    def __init__(self, opencode_service):
        self._opencode = opencode_service

    def answer_question(self, question: str, context: dict) -> str:
        workspace = Path(context.get("workspace", ""))
        if not context.get("workspace") or not workspace.is_dir():
            return f"Projektstatus: {context.get('status', 'unbekannt')}. (Kein Projektordner gefunden.)"
        before = _snapshot(workspace)
        try:
            result = self._opencode.execute(
                str(workspace), INSTRUCTION.format(question=question), timeout_seconds=ANSWER_TIMEOUT_S,
            )
        except Exception as exc:
            logger.exception("Project question failed")
            return f"Ich kann die Projektfrage gerade nicht beantworten: {getattr(exc, 'cause', '') or exc}"
        changed = sorted(name for name, mtime in _snapshot(workspace).items() if before.get(name) != mtime)
        answer = clean_answer(result.stdout or "")
        if result.returncode != 0 or not answer:
            from src.services.opencode_service import describe_opencode_failure
            cause, _ = describe_opencode_failure(result.returncode, result.stdout or "", result.stderr or "")
            return f"Ich kann die Projektfrage gerade nicht beantworten: {cause or 'keine Antwort erhalten'}"
        if changed:
            logger.warning("OpenCode changed files while answering a question: %s", changed)
            answer += "\n\nHinweis: Beim Beantworten wurden Dateien verändert: " + ", ".join(changed[:10])
        return answer
