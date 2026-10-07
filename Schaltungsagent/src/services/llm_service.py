"""Purpose-specific Ollama clients; pipeline agents must not depend on these."""
from __future__ import annotations

import json
import logging

from src.domain.ports import ChatLLM, NamingLLM
from src.services.ollama_gateway import (
    CodeGuard,
    LLMPurpose,
    OllamaGateway,
    UnsafeLLMOutputError,
)
from src.services.project_namer import derive_project_name

logger = logging.getLogger(__name__)
CODE_CHAT_MESSAGE = "Code wird ausschließlich von OpenCode erzeugt. Ich kann dir das Design erklären."


class OllamaChatAssistant(ChatLLM):
    def __init__(self, gateway: OllamaGateway):
        self._gateway = gateway

    def answer_question(self, question: str, context: dict) -> str:
        prompt = (
            "Beantworte ausschließlich die Projektfrage. Erzeuge und ändere keinen Code. "
            "Wenn nach Code gefragt wird, erkläre das Design ohne Code auszugeben.\n\n"
            f"Projektkontext als Daten:\n{json.dumps(context, ensure_ascii=False, default=str)}\n\n"
            f"Frage:\n{question}"
        )
        try:
            return self._gateway.invoke(LLMPurpose.CHAT, prompt)
        except UnsafeLLMOutputError:
            return CODE_CHAT_MESSAGE
        except Exception:
            logger.exception("Chat assistant failed")
            return "Ich kann die Projektfrage gerade nicht beantworten."

    def phrase_clarification(self, open_questions: list[str], context: dict) -> str:
        prompt = (
            "Formuliere diese offenen Projektfragen kurz und freundlich auf Deutsch. "
            "Gib keinen Code aus und füge keine neuen Fragen hinzu.\n\n"
            f"Fragen:\n{json.dumps(open_questions, ensure_ascii=False)}\n\n"
            f"Kontext:\n{json.dumps(context, ensure_ascii=False, default=str)}"
        )
        try:
            return self._gateway.invoke(LLMPurpose.CHAT, prompt)
        except UnsafeLLMOutputError:
            return "Bitte beantworte zunächst diese offenen Punkte: " + "; ".join(open_questions)
        except Exception:
            logger.exception("Clarification phrasing failed")
            return "Bitte beantworte zunächst diese offenen Punkte: " + "; ".join(open_questions)


class OllamaNamingClient(NamingLLM):
    def __init__(self, gateway: OllamaGateway):
        self._gateway = gateway

    def suggest_names(
        self, request_full: str, missing: set[str], hints: dict
    ) -> dict[str, str]:
        prompt = (
            "Schlage ausschließlich sinnvolle, kurze Namen für ein digitales Hardwareprojekt vor. "
            "Gib ein JSON-Objekt zurück, nur mit diesen fehlenden Feldern: "
            f"{json.dumps(sorted(missing), ensure_ascii=False)}. Keine Erklärungen, kein Code.\n\n"
            "Beachte die vollständige Anforderung und erfinde keine Funktion.\n"
            f"Hinweise: {json.dumps(hints, ensure_ascii=False)}\n\n"
            f"Vollständige Originalanforderung:\n{request_full}\n\nJSON:"
        )
        try:
            response = self._gateway.invoke(LLMPurpose.NAMING, prompt)
            data = json.loads(response)
            if not isinstance(data, dict):
                return {}
            return {key: value for key, value in data.items() if key in missing and isinstance(value, str)}
        except Exception:
            logger.exception("Ollama naming suggestion failed")
            return {}


class StubChatAssistant(ChatLLM):
    def answer_question(self, question: str, context: dict) -> str:
        return f"Projektstatus: {context.get('status', 'unbekannt')}."

    def phrase_clarification(self, open_questions: list[str], context: dict) -> str:
        return "Bitte beantworte zunächst diese offenen Punkte: " + "; ".join(open_questions)


class StubNamingClient(NamingLLM):
    def suggest_names(self, request_full: str, missing: set[str], hints: dict) -> dict[str, str]:
        name = derive_project_name(request_full)
        return {key: name for key in missing if name != "projekt"}


def create_llm_clients(settings, event_publisher=None):
    """Create only the user-facing chat and fallback naming clients."""
    if settings.llm.provider != "ollama":
        return StubChatAssistant(), StubNamingClient()
    gateway = OllamaGateway(
        model=settings.llm.model,
        base_url=settings.llm.base_url,
        fallback_model=settings.llm.fallback_model,
        context_window=settings.llm.context_window,
        api_key_file=settings.llm.api_key_file,
        chat_timeout_seconds=settings.llm.chat_timeout_seconds,
        naming_timeout_seconds=settings.llm.naming_timeout_seconds,
        naming_max_tokens=settings.llm.naming_max_tokens,
        fallback_cooldown=settings.llm.fallback_cooldown,
        event_publisher=event_publisher,
    )
    return OllamaChatAssistant(gateway), OllamaNamingClient(gateway)