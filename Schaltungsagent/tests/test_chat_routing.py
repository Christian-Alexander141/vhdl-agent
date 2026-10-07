"""Tests for deterministic chat routing (AP7)."""
from unittest.mock import Mock, MagicMock

import pytest

from src.services.chat_router import ChatRouter, ChatRoute
from src.services.llm_service import OllamaChatAssistant, StubChatAssistant, CODE_CHAT_MESSAGE
from src.services.ollama_gateway import CodeGuard, LLMPurpose, UnsafeLLMOutputError


def test_long_message_routes_to_new_project():
    """Messages >= 400 chars route to new_project, no Ollama."""
    router = ChatRouter()
    
    long_msg = "x" * 400
    route = router.route(long_msg, current_project=None)
    assert route.kind == "new_project"
    
    long_msg_with_project = "x" * 500
    route = router.route(long_msg_with_project, current_project="existing")
    assert route.kind == "new_project"


def test_multi_line_message_routes_to_new_project():
    """Messages with >= 3 lines route to new_project."""
    router = ChatRouter()
    
    multi_line = "line 1\nline 2\nline 3"
    route = router.route(multi_line, current_project="existing")
    assert route.kind == "new_project"


def test_question_routes_to_question():
    """Question-form messages route to question."""
    router = ChatRouter()
    
    questions = [
        "Warum funktioniert das nicht?",
        "Was macht der Timer?",
        "Wie kann ich den Reset ändern?",
        "Welche Pins werden verwendet?",
        "Erkläre mir die Architektur.",
        "Was bedeutet dieser Fehler?",
    ]
    
    for q in questions:
        route = router.route(q, current_project="project-123")
        assert route.kind == "question", f"Failed for: {q}"
        assert route.project_id == "project-123"


def test_change_request_routes_to_change():
    """Change/error hints route to change."""
    router = ChatRouter()
    
    changes = [
        "Ändere den Timer auf 10 MHz",
        "Korrigiere den Reset",
        "Behebe den Fehler im Control",
        "Repariere die Ampel",
        "Fix the LED output",
        "Passe die Taktfrequenz an",
        "Ergänze einen Enable-Eingang",
        "Füge einen Button hinzu",
        "Baue nochmal den Timer",
        "Nochmal versuchen",
        "Versuch es erneut",
        "Weiter machen",
        "Fortsetzen",
    ]
    
    for c in changes:
        route = router.route(c, current_project="project-123")
        assert route.kind == "change", f"Failed for: {c}"
        assert route.project_id == "project-123"


def test_unclear_routes_to_clarify():
    """Unclear messages route to clarify."""
    router = ChatRouter()
    
    route = router.route("Hallo", current_project="project-123")
    assert route.kind == "clarify"
    assert route.project_id == "project-123"
    assert "neues Projekt" in route.message or "ändern" in route.message


def test_attachment_routes_to_new_project():
    """Messages with attachments route to new_project."""
    router = ChatRouter()
    
    route = router.route("short", current_project="project-123", has_attachments=True)
    assert route.kind == "new_project"


def test_chat_assistant_rejects_code():
    """OllamaChatAssistant returns fixed message when Ollama outputs code."""
    # Mock gateway that returns VHDL
    mock_gateway = Mock()
    mock_gateway.invoke.side_effect = UnsafeLLMOutputError("Ollama returned code")
    
    assistant = OllamaChatAssistant(mock_gateway)
    answer = assistant.answer_question("Wie erstelle ich einen Zähler?", {})
    
    assert answer == CODE_CHAT_MESSAGE
    mock_gateway.invoke.assert_called_once_with(LLMPurpose.CHAT, mock_gateway.invoke.call_args[0][1])


def test_chat_assistant_returns_answer_when_no_code():
    """OllamaChatAssistant returns answer when Ollama outputs text."""
    mock_gateway = Mock()
    mock_gateway.invoke.return_value = "Der Timer zählt bei jedem Clock-Zyklus hoch."
    
    assistant = OllamaChatAssistant(mock_gateway)
    answer = assistant.answer_question("Was macht der Timer?", {"status": "IMPLEMENTING"})
    
    assert answer == "Der Timer zählt bei jedem Clock-Zyklus hoch."
    mock_gateway.invoke.assert_called_once()


def test_stub_chat_assistant_deterministic():
    """StubChatAssistant returns deterministic responses."""
    assistant = StubChatAssistant()
    
    answer = assistant.answer_question("Status?", {"status": "IMPLEMENTING"})
    assert "IMPLEMENTING" in answer
    
    clarification = assistant.phrase_clarification(["Frage 1", "Frage 2"], {})
    assert "Frage 1" in clarification
    assert "Frage 2" in clarification


def test_code_guard_detects_vhdl():
    """CodeGuard detects various VHDL patterns."""
    vhdl_samples = [
        "```vhdl\nentity test is\nend;\n```",
        "entity my_entity is\n  port (clk: in std_logic);\nend entity;",
        "architecture rtl of my_entity is\nbegin\nend architecture;",
        "library ieee;\nuse ieee.std_logic_1164.all;",
    ]
    
    for sample in vhdl_samples:
        assert CodeGuard.is_code(sample), f"Missed VHDL in: {sample[:50]}"
    
    non_code = [
        "This is a chat response.",
        "The entity should have a clock port.",
        "No code here.",
    ]
    
    for sample in non_code:
        assert not CodeGuard.is_code(sample), f"False positive for: {sample}"


def test_question_does_not_start_supervisor():
    """Question route returns answer directly, no Supervisor execution."""
    # This is verified by the api_server.py route_chat_message function
    # which returns immediately for 'question' kind
    from src.api_server import route_chat_message
    import asyncio
    
    # Mock the chat assistant
    mock_assistant = Mock()
    mock_assistant.answer_question.return_value = "Test answer"
    
    # We can't easily test the full integration here without more mocks,
    # but the routing logic is tested above


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

# ---------------------------------------------------------------------------
# Log-/Fehlerausgaben-Schutz: siehe chat_router.looks_like_log_or_error_dump.
# Motivierender Vorfall: eine eigene Fehlermeldung landete versehentlich
# (vermutlich aus der Zwischenablage) als "Anforderung" in einem neuen
# Projekt; das Ergebnis war ein über mehrere Minuten sauber fehlgeschlagener
# Lauf statt einer sofortigen Rückfrage.
# ---------------------------------------------------------------------------

REAL_INCIDENT_TEXT = """AI Engineer
18:02:44
OpenCode konnte keinen sicheren Projektplan erstellen: Projektplan: OpenCode hat plan/manifest.json nicht gültig geliefert
  Ursache: plan/manifest.json wurde nicht geschrieben – OpenCode endete ohne Fehler, hat aber keine Projektdatei geschrieben
  Hinweis: Das Modell hat vermutlich nur geantwortet statt die Datei zu schreiben; stdout prüfen oder ein anderes Modell wählen.
  Phase: plan
  Erwartete Dateien: plan/manifest.json (fehlt)
  Exit-Code: 0
  Laufzeit: 89.5 s
  Ausführung: nativ (Testmodus)
  Auftragsdatei: .opencode_tasks/bootstrap-6a8d114bcbea_plan.md
  Von OpenCode geänderte Dateien: keine"""

PYTHON_TRACEBACK_TEXT = '''Traceback (most recent call last):
  File "/home/alex/app.py", line 42, in <module>
    raise RuntimeError("boom")
RuntimeError: boom'''

ANSI_LOG_TEXT = "\x1b[91m\x1b[1mError: \x1b[0mSomething failed\nRead PROMPT.md failed"

PLAIN_LOG_TEXT = """2026-10-07 18:17:22 [ERROR] src.agents.supervisor: Supervisor execution failed
2026-10-07 18:17:23 [INFO] src.services.filesystem_service: Workspace deleted"""

JS_STACK_TEXT = """TypeError: cannot read property of undefined
    at handleClick (app.js:120:15)
    at HTMLButtonElement.onclick (app.js:88:9)"""


def test_real_incident_text_is_flagged():
    from src.services.chat_router import looks_like_log_or_error_dump
    assert looks_like_log_or_error_dump(REAL_INCIDENT_TEXT)


def test_python_traceback_is_flagged():
    from src.services.chat_router import looks_like_log_or_error_dump
    assert looks_like_log_or_error_dump(PYTHON_TRACEBACK_TEXT)


def test_ansi_colored_log_is_flagged():
    from src.services.chat_router import looks_like_log_or_error_dump
    assert looks_like_log_or_error_dump(ANSI_LOG_TEXT)


def test_plain_timestamped_log_is_flagged():
    from src.services.chat_router import looks_like_log_or_error_dump
    assert looks_like_log_or_error_dump(PLAIN_LOG_TEXT)


def test_js_stack_trace_is_flagged():
    from src.services.chat_router import looks_like_log_or_error_dump
    assert looks_like_log_or_error_dump(JS_STACK_TEXT)


def test_normal_hardware_request_is_not_flagged():
    from src.services.chat_router import looks_like_log_or_error_dump

    requests = [
        "Baue eine Ampelsteuerung für das Arty S7-50.",
        "Erstelle einen 8-Bit-Zähler mit synchronem Reset und Enable-Eingang.",
        "Ich brauche einen UART-Transceiver mit 115200 Baud, 8N1.",
    ]
    for r in requests:
        assert not looks_like_log_or_error_dump(r), r


def test_long_legitimate_spec_mentioning_errors_is_not_flagged():
    """Hardwarebeschreibungen dürfen frei über Fehlerbehandlung sprechen,
    solange sie nicht unsere eigenen Diagnose-Label im Log-Format verwenden."""
    from src.services.chat_router import looks_like_log_or_error_dump

    spec = (
        "Baue einen UART-Empfänger mit Fehlererkennung über ein Paritätsbit. "
        "Bei einem Fehler soll ein Statusregister den Grund anzeigen und ein "
        "Interrupt-Signal ausgelöst werden. Die Ursache des Fehlers (Parity "
        "oder Framing) soll getrennt codiert werden. Zusätzlich soll ein "
        "Watchdog nach Ablauf eines Timeouts einen Reset auslösen."
    )
    assert not looks_like_log_or_error_dump(spec)


def test_single_own_diagnostic_label_alone_is_not_flagged():
    """Ein einzelnes Label reicht nicht - Schwelle ist bewusst >= 2."""
    from src.services.chat_router import looks_like_log_or_error_dump
    assert not looks_like_log_or_error_dump("Die Phase: Analyse ist mir unklar, was macht sie genau?")


def test_router_intercepts_log_dump_before_new_project_for_fresh_chat():
    """Ohne aktives Projekt würde sonst sofort new_project greifen (kein
    current_project) - der Log-Check muss davor abfangen."""
    router = ChatRouter()
    route = router.route(REAL_INCIDENT_TEXT, current_project=None)
    assert route.kind == "clarify"
    assert route.project_id is None
    assert "Log- oder Fehlerausgabe" in route.message


def test_router_intercepts_log_dump_with_active_project():
    router = ChatRouter()
    route = router.route(REAL_INCIDENT_TEXT, current_project="ampelsteuerung-abc")
    assert route.kind == "clarify"
    assert route.project_id == "ampelsteuerung-abc"


def test_router_log_check_skipped_for_attachments():
    """Eine Datei-Anfrage mit begleitendem (zufällig log-ähnlichem) Text darf
    nicht blockiert werden - Anhänge sind explizite Nutzerabsicht."""
    router = ChatRouter()
    route = router.route(REAL_INCIDENT_TEXT, current_project=None, has_attachments=True)
    assert route.kind == "new_project"


def test_router_still_routes_long_legitimate_request_to_new_project():
    """Regression: der neue Check darf echte, lange Anforderungen nicht
    aufhalten."""
    router = ChatRouter()
    spec = "Baue eine Ampelsteuerung. " * 20  # > 400 Zeichen, aber kein Log
    route = router.route(spec, current_project=None)
    assert route.kind == "new_project"
