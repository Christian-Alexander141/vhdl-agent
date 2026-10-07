# Verbesserungsvorschläge & Identifizierte technische Schulden

## ✅ Bereits umgesetzt

| # | Verbesserung | Status |
|---|-------------|--------|
| 1 | **LLM-Integration** — `OllamaLLMService` mit realem Ollama-LLM (Fallback auf `StubLLMService`) | ✅ |
| 2 | **RAG-Vector-Database** — Qdrant-basierte Vektorsuche mit HuggingFace-Embeddings, Keyword-Matching als Fallback | ✅ |
| 3 | **Testabdeckung** — 36 Unit-Tests für StateMachine, EventBus, TaskState, KnowledgeBundle, FileSystemService + 6 Integrationstests | ✅ |
| 4 | **Domain-Registry** — Automatische Erkennung von Domänen in `src/domain_plugins/` per `DomainRegistry.discover()` | ✅ |
| 5 | **Async-Workflow** — `execute_async()` für nicht-blockierende Task-Ausführung im Hintergrund-Thread | ✅ |
| 6 | **Workspace-Cleanup** — TTL-basierte Cleanup-Strategie (`cleanup_ttl_hours`), Limits (`max_workspaces`) | ✅ |
| 7 | **Template-Engine** — Migration von `str.format()` zu Jinja2-Templates | ✅ |
| 8 | **State-Serialisierung** — `TaskState`, `KnowledgeBundle`, `ArtifactBundle` als Pydantic-Modelle (JSON-Serialisierung via `model_dump_json`) | ✅ |

## Kurzfristige Verbesserungen (noch offen)

1. **Dashboard-State-Sync** — Dashboard verwendet REST-Polling als Fallback.
   - WebSocket-basierter Event-Stream ist vollständig implementiert
   - Eventuelle Latenz-Probleme bei vielen parallelen Tasks

## Mittelfristige Verbesserungen

2. **API-Authentifizierung** — Derzeit kein Schutz der API-Endpunkte.
   - API-Key oder JWT für Produktion erforderlich

3. **Dashboard-Code-Qualität** — Vanilla-JS ohne Framework.
   - Migration zu React/Vue für bessere Wartbarkeit
   - Komponenten-basierte Architektur

## Langfristige Architektur-Entscheidungen

4. **Multi-Agent-Orchestrierung** — Derzeit Single-Agent-Workflow.
   - Parallelisierte Agenten für verschiedene Aspekte (HDL, Testbench, Dokumentation)
   - Agent-Kommunikation über EventBus

5. **Caching-Strategie** — Kein Caching von LLM- oder RAG-Ergebnissen.
   - Result-Cache auf Task-Ebene
   - Embedding-Cache für wiederkehrende Suchanfragen

6. **Metriken & Monitoring** — Keine Instrumentierung.
   - Prometheus-Metriken für Task-Dauer, Fehlerraten, LLM-Latenz
   - Strukturierte Logs für ELK-Stack

7. **Async-Native API** — Der `POST /api/task`-Endpoint arbeitet asynchron, aber der WebSocket-Endpoint läuft noch synchron. Migration zu vollständig asynchronem Orchestrator mit `asyncio`.

## Technische Schulden

- **Import-Pfade** — `from src.services...` setzt voraus, dass `src/` als Paket importiert wird (Python-Modul-Pfad). Alternative: Relativer Import oder Installations-Package
- **Exception-Handling** — Einige Service-Fehler werden nicht granular genug behandelt (z.B. Netzwerk-Fehler in LLM-Service)
- **Keine Datenbank** — Task-States nur als JSON-Dateien. Für viele parallele Tasks: SQLite/PostgreSQL
- **sentence-transformers** — Für Qdrant-Vektorsuche wird `sentence-transformers` benötigt (nicht in Standard-Venv)
