import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.config import LLMConfig, load_config
from src.services.llm_service import OllamaLLMService


class FakeLLM:
    def __init__(self, reply="ok", raise_exc=None):
        self.reply = reply
        self.raise_exc = raise_exc
        self.calls = 0
        self.last_prompt = ""

    def invoke(self, prompt):
        self.calls += 1
        self.last_prompt = prompt
        if self.raise_exc is not None:
            raise self.raise_exc
        return self.reply


def make_service(**overrides):
    defaults = dict(
        model="gpt-oss:120b-cloud",
        base_url="http://localhost:11434",
        fallback_model="llama3.2:1b",
        fallback_cooldown=60.0,
        primary_timeout=120.0,
        fallback_timeout=600.0,
    )
    defaults.update(overrides)
    svc = OllamaLLMService(**defaults)
    svc._llm = FakeLLM(reply="primary-answer")
    svc._fallback_llm = FakeLLM(reply="fallback-answer")
    return svc


def test_primary_success_does_not_use_fallback():
    svc = make_service()
    assert svc._invoke("p") == "primary-answer"
    assert svc._llm.calls == 1
    assert svc._fallback_llm.calls == 0
    assert svc._primary_down_until == 0.0


def test_primary_failure_uses_fallback():
    svc = make_service()
    svc._llm.raise_exc = ConnectionError("ollama down")
    assert svc._invoke("p") == "fallback-answer"
    assert svc._llm.calls == 1
    assert svc._fallback_llm.calls == 1
    assert svc._primary_down_until > 0.0


def test_cooldown_skips_primary():
    import time

    svc = make_service()
    svc._llm.raise_exc = ConnectionError("down")
    svc._invoke("p")
    primary_calls = svc._llm.calls

    svc._llm.raise_exc = None
    assert svc._invoke("p") == "fallback-answer"
    assert svc._llm.calls == primary_calls
    assert svc._fallback_llm.calls == 2


def test_primary_retried_after_cooldown():
    import time

    svc = make_service()
    svc._llm.raise_exc = ConnectionError("down")
    svc._invoke("p")

    svc._primary_down_until = time.monotonic() - 1.0
    svc._llm.raise_exc = None
    assert svc._invoke("p") == "primary-answer"
    assert svc._llm.calls == 2
    assert svc._primary_down_until == 0.0


def test_no_fallback_configured_propagates_error():
    svc = make_service(fallback_model="")
    svc._fallback_llm = None
    svc._llm.raise_exc = ConnectionError("down")
    try:
        svc._invoke("p")
    except ConnectionError:
        pass
    else:
        raise AssertionError("expected ConnectionError to propagate")


def test_both_models_fail_raises_fallback_error():
    svc = make_service()
    svc._llm.raise_exc = ConnectionError("primary down")
    svc._fallback_llm.raise_exc = TimeoutError("local too slow")
    try:
        svc._invoke("p")
    except TimeoutError:
        pass
    else:
        raise AssertionError("expected TimeoutError from fallback")


def test_generate_project_name_falls_back():
    svc = make_service()
    svc._llm.raise_exc = ConnectionError("down")
    svc._fallback_llm.reply = "mein-projekt"
    name = svc.generate_project_name("erstelle einen Zaehler")
    assert name == "mein-projekt"


def test_generic_task_title_uses_circuit_topic_from_long_request():
    request = """Aufgabe 5
Erstelle die VHDL-Schaltung für die angehängte Übung und passe sie für mein FPGA-Board an.
Ziel
Ich möchte die beschriebene Ampelsteuerung als Hardware implementieren.
"""
    request += "\nZusatzanforderung: Alle Phasen sollen zuverlässig wechseln. " * 30
    svc = make_service()
    svc._llm.raise_exc = ConnectionError("primary unavailable")
    svc._fallback_llm.reply = "Aufgabe 5"

    assert svc.generate_project_name(request) == "ampelsteuerung"
    assert svc._llm.calls == 0


def test_generic_task_title_is_rejected_for_short_request():
    svc = make_service()
    svc._llm.raise_exc = ConnectionError("primary unavailable")
    svc._fallback_llm.reply = "Aufgabe 5"

    assert svc.generate_project_name("Erstelle einen Zaehler") == "zaehler"


def test_generate_code_empty_on_total_failure():
    svc = make_service()
    svc._llm.raise_exc = ConnectionError("down")
    svc._fallback_llm.raise_exc = TimeoutError("slow")
    assert svc.generate_text("code") == ""


def test_analysis_passes_entire_long_request_to_model():
    svc = make_service()
    request = "Anforderung " * 5000 + "ENDE_DER_VOLLSTAENDIGEN_ANFRAGE"

    svc.analyze_request(request)

    assert svc._llm.last_prompt.endswith("ENDE_DER_VOLLSTAENDIGEN_ANFRAGE\n\nAnalysis:")


def test_config_defaults():
    cfg = LLMConfig()
    assert cfg.fallback_model == "llama3.2:1b"
    assert cfg.fallback_cooldown == 60.0
    assert cfg.primary_timeout == 120.0
    assert cfg.fallback_timeout == 600.0
    assert cfg.context_window == 32768


def test_config_yaml_loads_fallback_keys():
    settings = load_config()
    assert settings.llm.fallback_model == "llama3.2:1b"
    assert settings.llm.fallback_cooldown == 60
    assert settings.llm.primary_timeout == 120
    assert settings.llm.fallback_timeout == 600
    assert settings.llm.context_window == 32768


def test_service_timeout_client_kwargs():
    svc = OllamaLLMService(
        model="gpt-oss:120b-cloud",
        base_url="http://localhost:11434",
        fallback_model="llama3.2:1b",
        primary_timeout=42.0,
        fallback_timeout=99.0,
    )
    primary = svc._get_llm()
    fallback = svc._get_fallback_llm()
    assert primary.client_kwargs == {"timeout": 42.0}
    assert fallback.client_kwargs == {"timeout": 99.0}
    assert primary.num_ctx == 32768
    assert fallback.num_ctx == 32768
    assert primary.num_predict == 4096
    assert fallback.num_predict == 4096
    assert fallback.model == "llama3.2:1b"
    assert fallback.base_url == "http://localhost:11434"
