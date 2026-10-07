"""GET /api/opencode/models: Caching und Fehlerbehandlung.

Ruft die Routenfunktion direkt auf (wie die übrige Testsuite api_server.py
testet) statt über einen HTTP-Client, da api_server.py beim Import eine
vollständige Orchestrator-/Service-Instanz aufbaut.
"""
import asyncio

import pytest

import src.api_server as api
from src.domain.exceptions import OpenCodeUnavailableError


@pytest.fixture(autouse=True)
def _clear_cache():
    api._models_cache.clear()
    yield
    api._models_cache.clear()


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_models_endpoint_returns_grouped_list(monkeypatch):
    monkeypatch.setattr(api.opencode, "list_models", lambda provider="": [
        "opencode/mimo-v2.6-flash-free", "opencode/nemotron-3.5-lightning-free",
    ])

    response = _run(api.list_opencode_models(provider="opencode"))
    body = response.body.decode() if hasattr(response, "body") else None
    import json
    data = json.loads(response.body)

    assert data["models"] == ["opencode/mimo-v2.6-flash-free", "opencode/nemotron-3.5-lightning-free"]
    assert data["by_provider"] == {"opencode": data["models"]}
    assert data["cached"] is False


def test_second_call_within_ttl_is_served_from_cache(monkeypatch):
    calls = []
    monkeypatch.setattr(api.opencode, "list_models", lambda provider="": calls.append(provider) or ["m/a"])

    _run(api.list_opencode_models(provider="opencode"))
    response = _run(api.list_opencode_models(provider="opencode"))
    import json
    data = json.loads(response.body)

    assert len(calls) == 1  # zweiter Aufruf hat NICHT erneut gelistet
    assert data["cached"] is True


def test_refresh_flag_bypasses_cache(monkeypatch):
    calls = []
    monkeypatch.setattr(api.opencode, "list_models", lambda provider="": calls.append(provider) or ["m/a"])

    _run(api.list_opencode_models(provider="opencode"))
    _run(api.list_opencode_models(provider="opencode", refresh=True))

    assert len(calls) == 2


def test_different_providers_cache_independently(monkeypatch):
    calls = []
    monkeypatch.setattr(api.opencode, "list_models", lambda provider="": calls.append(provider) or [f"{provider or 'all'}/m"])

    _run(api.list_opencode_models(provider="opencode"))
    _run(api.list_opencode_models(provider="ollama-cloud"))
    _run(api.list_opencode_models())

    assert calls == ["opencode", "ollama-cloud", ""]


def test_infrastructure_error_returns_502_with_hint(monkeypatch):
    def boom(provider=""):
        raise OpenCodeUnavailableError(
            "docker: Docker daemon not running",
            cause="Der Docker-Dienst läuft nicht.",
            hint="Docker starten oder Testmodus wählen.",
        )

    monkeypatch.setattr(api.opencode, "list_models", boom)
    response = _run(api.list_opencode_models(provider="opencode"))
    import json
    data = json.loads(response.body)

    assert response.status_code == 502
    assert "Docker daemon not running" in data["error"]
    assert data["hint"] == "Docker starten oder Testmodus wählen."
    # Fehler werden nicht gecacht: ein erneuter Aufruf versucht es wieder.
    assert "opencode" not in api._models_cache


def test_unexpected_error_returns_502_without_crashing(monkeypatch):
    monkeypatch.setattr(api.opencode, "list_models", lambda provider="": (_ for _ in ()).throw(RuntimeError("boom")))
    response = _run(api.list_opencode_models(provider="opencode"))

    assert response.status_code == 502
