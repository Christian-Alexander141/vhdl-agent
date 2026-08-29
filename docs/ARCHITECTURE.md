# AI Engineer Platform — Architecture

## Hexagonale Architektur (Ports & Adapters)

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           DOMAIN LAYER (Kern)                            │
│  ┌──────────────┐  ┌────────────────┐  ┌────────────────────────────┐   │
│  │   Models      │  │  StateMachine  │  │        EventBus            │   │
│  │  TaskState    │  │                │  │  - multi subscriber        │   │
│  │  Event        │  │  11 states     │  │  - typed events            │   │
│  │  Knowledge    │  │  transitions   │  │  - event log               │   │
│  │  Artifacts    │  │  validation    │  │                            │   │
│  └──────────────┘  └────────────────┘  └────────────────────────────┘   │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │                     PORTS (Interfaces)                             │  │
│  │  ┌──────────┐  ┌──────────┐  ┌────────────────┐  ┌──────────────┐ │  │
│  │  │LLMService │  │RAGService │  │ArtifactGenerator│  │  FsSvc     │ │  │
│  │  └──────────┘  └──────────┘  └────────────────┘  └──────────────┘ │  │
│  │  ┌─────────────────┐  ┌────────────────┐                           │  │
│  │  │OpenCodeService   │  │EventPublisher  │                           │  │
│  │  └─────────────────┘  └────────────────┘                           │  │
│  └────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────┘
                                   │
                     implements ───┴─── depends on
                                   │
┌──────────────────────────────────────────────────────────────────────────┐
│                        SERVICE LAYER (Adapter)                           │
│  ┌───────────┐ ┌──────────────┐ ┌────────────────┐ ┌────────────────┐   │
│  │StubLLM    │ │ VHDLRAG      │ │VHDLArtifact    │ │LocalFS         │   │
│  │Service    │ │ Service      │ │Generator       │ │Service         │   │
│  └───────────┘ └──────┬───────┘ └────────────────┘ └────────────────┘   │
│                       │ delegates                                        │
│  ┌───────────────────────────────────┐  ┌─────────────────────────────┐  │
│  │    RAGChatPipeline                │  │ SubprocessOpenCodeService    │  │
│  │  - Qdrant Vector Store            │  │  - subprocess wrapper        │  │
│  │  - HuggingFace Embeddings         │  │  - timeout handling          │  │
│  │  - Chat Memory (soul.md)          │  │                              │  │
│  │  - Context Retrieval + RAG Prompt │  └─────────────────────────────┘  │
│  └───────────────────────────────────┘                                   │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │                   Agent / Planner Tools                             │  │
│  │  ┌──────────────────────────┐  ┌───────────────────────────────┐   │  │
│  │  │OpenCodeAgentTool         │  │ TaskPlannerService             │   │  │
│  │  │  - dispatch_opencode     │  │  - LangGraph task planner     │   │  │
│  │  │  - read_file_tool        │  │  - step plan + execute        │   │  │
│  │  │  - write_file_tool       │  │  - tool binding               │   │  │
│  │  │  - execute_tool_call     │  │                               │   │  │
│  │  └──────────────────────────┘  └───────────────────────────────┘   │  │
│  └────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────┘
                                   │
                     verwendet ────┴───
                                   │
┌──────────────────────────────────────────────────────────────────────────┐
│                          ORCHESTRATOR                                     │
│  AgentOrchestrator                                                        │
│  - arbeitet ausschließlich gegen Ports                                   │
│  - treibt die StateMachine an                                            │
│  - emittiert Events                                                      │
│  - entscheidet Workflow-Schritte                                         │
│  - behandelt Fehler / Wiederholungen                                     │
└──────────────────────────────────────────────────────────────────────────┘
                                   │
                     Einstiegspunkte ──┴──
                                   │
┌──────────────┐     ┌──────────────┐     ┌───────────┐     ┌────────────┐
│   CLI main   │     │  FastAPI      │     │ Dashboard │     │ RAG Chat   │
│  (argparse)  │     │  + WebSocket  │     │ (HTML/JS) │     │ (interaktiv│
│ run/list/show│     │  + RAG Router │     │           │     │  /api/rag) │
│ file/discover│     │               │     │           │     │            │
│ serve / rag  │     │               │     │           │     │            │
└──────────────┘     └──────────────┘     └───────────┘     └────────────┘
```

## Zustandsautomat (State Machine)

```
CREATED ──→ ANALYZING ──→ RAG_SEARCH ──→ GENERATING_ARTIFACTS
                                                │
                                                ▼
                                          WORKSPACE_READY
                                                │
                                                ▼
                                          RUNNING_AGENT
                                                │
                                                ▼
           ┌────────────────────────────── TESTING
           │                                  │
           │                      ┌───────────┼────────────┐
           │                      ▼           ▼            ▼
           │                COMPLETED    REPAIRING      FAILED
           │                      │           │
           └──────────────────────┼───────────┘
                                  ▼        (retry loop)
                             VALIDATING ──→ COMPLETED
                                  │
                                  └──→ FAILED
```

## Event-Fluss

```
User ──→ CLI/API ──→ Orchestrator ──→ EventBus ──→ Dashboard (WebSocket)
                         │
                         ├──→ LLMService (Analyse)
                         ├──→ RAGService → RAGChatPipeline (KnowledgeBundle)
                         ├──→ ArtifactGenerator (ArtifactBundle)
                         ├──→ FileSystemService (Dateien/Workspaces)
                         └──→ OpenCodeService (Agent-Ausführung)
```

## Dateistruktur

```
src/
├── main.py                     # Zentrales CLI-Startskript (alle Befehle)
├── config.py                   # Dataclasses + YAML-Loader
├── config.yaml                 # Konfiguration (LLM, RAG, Workspace, …)
├── api_server.py               # FastAPI-App (Dashboard + WebSocket + Task-API)
│
├── domain/                     # ===== DOMAIN LAYER =====
│   ├── models.py               #   TaskState, Event, KnowledgeBundle, …
│   ├── state_machine.py        #   StateMachine mit 11 Zuständen
│   ├── event_bus.py            #   EventBus (sync, multi-subscriber)
│   ├── ports.py                #   Interfaces: LLMService, RAGService, …
│   └── domain_registry.py      #   Dynamische Domain-Erkennung
│
├── services/                   # ===== SERVICE LAYER =====
│   ├── llm_service.py          #   OllamaLLMService + StubLLMService
│   ├── rag_service.py          #   VHDLRAGService (delegiert an Pipeline)
│   ├── rag_pipeline.py         #   RAGChatPipeline (Qdrant, Embeddings, Memory)
│   ├── opencode_agent_tool.py  #   LangChain-Tools für OpenCode CLI
│   ├── task_planner_service.py #   LangGraph-basierter Task-Planner
│   ├── artifact_generator.py   #   VHDLArtifactGenerator (Templates)
│   ├── filesystem_service.py   #   LocalFileSystemService (Workspaces)
│   └── opencode_service.py     #   SubprocessOpenCodeService
│
├── api/                        # ===== REST API ROUTES =====
│   ├── __init__.py
│   └── rag_router.py           #   /api/rag/* Endpunkte
│
├── orchestrator.py             # AgentOrchestrator (zentrale Steuerung)
│
├── domains/                    # ===== DOMAIN-MODULE =====
│   └── vhdl/
│       ├── __init__.py
│       ├── rag_data.py         #   Keywords, Coding Rules, Referenzdesigns
│       ├── templates.py        #   VHDL-Codetemplates (Jinja2)
│       ├── prompts.py          #   Domain-Prompts
│       ├── test_definitions.py #   GHDL-Testkonfiguration
│       └── build_definitions.py#   Build-Konfiguration
│
├── dashboard/                  # Statisches Frontend (HTML/JS)
└── tests/                      # Tests (37 Unit-Tests)
    ├── test_unit.py
    └── test_projects.py

memory/                         # RAG: Vektordatenbank + Chat-Memory
Dateien/                        # RAG: Quelldokumente zum Indexieren
projects/                       # Workspace-Verzeichnis (Task-Isolation)
```

## RAG-Pipeline (detailliert)

```
                    ┌──────────────┐
                    │  Dokumente   │
                    │  Dateien/    │
                    └──────┬───────┘
                           ▼
                    ┌──────────────┐
                    │   Chunking   │
                    │  1000/200    │
                    └──────┬───────┘
                           ▼
                    ┌──────────────┐
                    │  Embeddings  │
                    │  jina-emb..  │
                    └──────┬───────┘
                           ▼
                    ┌──────────────┐
                    │Qdrant Vector │
                    │Store         │
                    └──────┬───────┘
                           │
         ┌─────────────────┼─────────────────┐
         ▼                 ▼                  ▼
  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
  │  User Query  │  │ Context Retr.│  │ Chat Memory  │
  │              │  │  (top_k=5)   │  │  (soul.md)   │
  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘
         └─────────────────┼──────────────────┘
                           ▼
                    ┌──────────────┐
                    │  RAG Prompt  │
                    │  (LLM)       │
                    └──────┬───────┘
                           ▼
                    ┌──────────────┐
                    │   Antwort    │
                    └──────────────┘

Optional mit Tools:
  Query → LLM(bound_tools) → Tool-Call → Execute → Antwort
```

## Task Planner (detailliert)

```
Task ──→ LLM(bound_tools) ──→ JSON-Plan (steps)
                                   │
              ┌────────────────────┼────────────────────┐
              ▼                    ▼                    ▼
        Step 1                Step 2                Step 3
     (tool_name)           (tool_name)           (tool_name)
         │                      │                     │
         ▼                      ▼                     ▼
    execute_plan_step()   execute_plan_step()   execute_plan_step()
         │                      │                     │
         └──────────────────────┼─────────────────────┘
                                ▼
                         LLM-Summary
```

## REST-API-Endpunkte

| Methode | Pfad | Beschreibung |
|---------|------|-------------|
| GET | `/api/rag/health` | Status |
| POST | `/api/rag/query` | RAG-Chat-Frage (mit/ohne Tools/Planner) |
| POST | `/api/rag/chat` | Neue Chat-Session erstellen |
| POST | `/api/rag/index` | Dokumente in Qdrant indexieren |
| POST | `/api/rag/upload` | Dateien hochladen |
| GET | `/api/rag/models` | Verfügbare Modelle |
| GET | `/` | Dashboard (HTML) |
| GET | `/api/tasks` | Alle Tasks |
| GET | `/api/tasks/{id}` | Task-Detail |
| POST | `/api/task` | Task async starten |
| POST | `/api/task/sync` | Task sync starten |
| GET | `/api/domains` | Verfügbare Domains |
| POST | `/api/cleanup` | Alte Workspaces löschen |
| WS | `/ws` | WebSocket-Events |

## CLI-Befehle

| Befehl | Beschreibung |
|--------|-------------|
| `run <request>` | Task ausführen |
| `list` | Alle Tasks anzeigen |
| `show <task_id>` | Task-Details |
| `file <task_id> <filename>` | Generierte Datei anzeigen |
| `discover` | Domains erkennen |
| `serve` | FastAPI-Server starten (Dashboard) |
| `rag` | Interaktiver RAG-Chat |

## Wichtige Design-Entscheidungen

1. **Orchestrator ist King** — steuert alle Workflow-Schritte, LLM liefert nur Analysen
2. **Keine direkten Service-Aufrufe** — alle Services über Ports angebunden
3. **RAG liefert nur Wissen** — erzeugt nie Dateien
4. **ArtifactGenerator erzeugt Artifakte** — speichert sie nicht
5. **FileSystemService verwaltet Dateien** — alleiniger Owner für File-I/O
6. **OpenCodeService gekapselt** — einzelne `execute()`-Methode
7. **Isolierte Workspaces** — `projects/<task_uuid>/src|tests|docs|build|logs`
8. **Typisiertes Event-System** — EventType-Enum, strukturiertes Event-Modell
9. **Pluggable Domains** — `domains/python/`, `domains/embedded/` ohne Orchestrator-Änderungen
10. **RAG-Pipeline modular** — austauschbare Embeddings, Vector Stores, Chunking-Strategien
11. **Chat-Memory persistiert** — Unterhaltungsverlauf in `memory/soul_<id>.md`
12. **Task Planner optional** — über `usePlanner=true` im RAG-Query aktivierbar
13. **Zentraler Einstieg** — `python3 -m src.main` für CLI, Server und RAG-Chat

## Zielbild (Roadmap)

1. **Simulation in Docker** — Die VHDL-Simulation (GHDL) soll mittelfristig vollständig in einem eigenen Docker-Container ausgeführt werden und nicht mehr auf dem Host. Aktuell übernimmt der `GHDLValidator` die Analyse noch direkt auf dem Host.
2. **Isolation & Reproduzierbarkeit** — Jede Simulation läuft in einem frischen, deterministischen Container-Umfeld mit genau definierter GHDL-Toolchain.
3. **Schneller Reset bei Problemen** — Da die Simulation isoliert im Container stattfindet, kann bei Fehlern oder kaputtem Zustand einfach ein neuer Container erzeugt werden, ohne den Host zu beeinflussen.
4. **Austauschbare Toolchain** — Durch die Containerisierung bleibt der Agent selbst schlank (aktuell: OpenCode-Container ohne GHDL); die GHDL-Umgebung wird als eigenes Image bereitgestellt.
