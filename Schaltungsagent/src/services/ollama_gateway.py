"""The only supported boundary for Ollama calls."""
from __future__ import annotations

import logging
import os
import re
import threading
import time
from pathlib import Path
from enum import Enum

logger = logging.getLogger(__name__)


class LLMPurpose(str, Enum):
    CHAT = "CHAT"
    NAMING = "NAMING"


class ForbiddenLLMUseError(RuntimeError):
    """Raised when a caller attempts to use Ollama outside its allowlist."""


class UnsafeLLMOutputError(ValueError):
    """Raised when Ollama returns code instead of chat text or a name."""


class CodeGuard:
    _VHDL_PATTERNS = (
        re.compile(r"```\s*vhdl", re.IGNORECASE),
        re.compile(r"\bentity\s+\w+\s+is\b", re.IGNORECASE),
        re.compile(r"\barchitecture\s+\w+\s+of\s+\w+\s+is\b", re.IGNORECASE),
        re.compile(r"\blibrary\s+ieee\b", re.IGNORECASE),
    )

    @classmethod
    def is_code(cls, response: str) -> bool:
        return any(pattern.search(response or "") for pattern in cls._VHDL_PATTERNS)


class OllamaGateway:
    """Purpose-limited Ollama client with a bounded, observable fallback."""

    def __init__(
        self,
        model: str = "gpt-oss:120b-cloud",
        base_url: str = "http://localhost:11434",
        fallback_model: str = "llama3.2:1b",
        context_window: int = 32768,
        api_key_file: str = "",
        chat_timeout_seconds: float = 120.0,
        naming_timeout_seconds: float = 30.0,
        naming_max_tokens: int = 96,
        fallback_cooldown: float = 60.0,
        event_publisher=None,
        primary=None,
        fallback=None,
    ):
        self._model = model
        self._base_url = base_url
        self._fallback_model = fallback_model
        self._context_window = context_window
        self._api_key_file = api_key_file
        self._chat_timeout = chat_timeout_seconds
        self._naming_timeout = naming_timeout_seconds
        self._naming_max_tokens = naming_max_tokens
        self._fallback_cooldown = fallback_cooldown
        self._events = event_publisher
        self._primary = primary
        self._fallback = fallback
        self._primary_down_until = 0.0
        self._breaker_lock = threading.Lock()

    def _api_key(self) -> str:
        value = os.environ.get("OLLAMA_API_KEY", "").strip()
        if value or not self._api_key_file:
            return value
        path = Path(self._api_key_file).expanduser()
        if not path.is_file():
            return ""
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("OLLAMA_API_KEY="):
                return line.split("=", 1)[1].strip()
        return ""

    def _client(self, model: str, timeout: float, max_tokens: int):
        from langchain_ollama import OllamaLLM

        kwargs = dict(
            model=model,
            base_url=self._base_url,
            temperature=0.1,
            num_ctx=self._context_window,
            num_predict=max_tokens,
            client_kwargs={"timeout": timeout},
        )
        api_key = self._api_key()
        if api_key:
            import httpx

            kwargs["base_url"] = "https://ollama.com"
            kwargs["http_client"] = httpx.Client(
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=timeout,
            )
        return OllamaLLM(**kwargs)

    def _emit(self, payload: dict) -> None:
        if not self._events:
            return
        try:
            self._events.publish_event("LLM_CALL", payload.get("task_id", ""), payload)
        except Exception:
            logger.exception("Could not publish LLM_CALL event")

    def invoke(
        self,
        purpose: LLMPurpose | str,
        prompt: str,
        *,
        timeout: float | None = None,
        max_tokens: int | None = None,
        task_id: str = "",
    ) -> str:
        try:
            purpose = LLMPurpose(purpose)
        except (ValueError, TypeError) as exc:
            raise ForbiddenLLMUseError(f"Ollama purpose is not allowed: {purpose}") from exc

        timeout = timeout or (
            self._naming_timeout if purpose is LLMPurpose.NAMING else self._chat_timeout
        )
        max_tokens = max_tokens or (
            self._naming_max_tokens if purpose is LLMPurpose.NAMING else 2048
        )
        started = time.monotonic()
        breaker_open = time.monotonic() < self._primary_down_until
        used_fallback = bool(breaker_open and self._fallback_model)
        model = self._fallback_model if used_fallback else self._model
        try:
            if used_fallback:
                client = self._fallback or self._client(model, timeout, max_tokens)
                response = str(client.invoke(prompt)).strip()
            else:
                client = self._primary or self._client(self._model, timeout, max_tokens)
                try:
                    response = str(client.invoke(prompt)).strip()
                    with self._breaker_lock:
                        self._primary_down_until = 0.0
                except Exception:
                    if not self._fallback_model:
                        raise
                    with self._breaker_lock:
                        self._primary_down_until = time.monotonic() + self._fallback_cooldown
                    fallback = self._fallback or self._client(
                        self._fallback_model, timeout, max_tokens
                    )
                    response = str(fallback.invoke(prompt)).strip()
                    used_fallback = True
                    model = self._fallback_model
        except Exception as exc:
            self._emit({
                "purpose": purpose.value,
                "model": model,
                "fallback": used_fallback,
                "prompt_length": len(prompt),
                "duration_seconds": time.monotonic() - started,
                "error": str(exc),
                "task_id": task_id,
            })
            raise

        self._emit({
            "purpose": purpose.value,
            "model": model,
            "fallback": used_fallback,
            "prompt_length": len(prompt),
            "duration_seconds": time.monotonic() - started,
            "task_id": task_id,
        })
        if CodeGuard.is_code(response):
            raise UnsafeLLMOutputError(
                f"Ollama returned code for the {purpose.value} purpose"
            )
        return response