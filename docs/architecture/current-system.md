# Aktuelle System-Architektur (Analyse)

## Übersicht

Das bestehende `vhdl-agent` System ist eine **Hexagonal Architecture** (Ports & Adapters) für KI-gestützte VHDL-Entwicklung.

## Kernkomponenten

### 1. Orchestrator (Monolithisch)
- **Datei**: `Schaltungsagent/src/orchestrator/orchestrator.py` (1195 Zeilen)
- **Klasse**: `AsyncAgentOrchestrator`
- **Verantwortung**: Kompletter Workflow von Anforderung bis FPGA-Flash
- **Status**: Wird durch SupervisorAgent ersetzt

### 2. State Machine
- **Datei**: `Schaltungsagent/src/domain/state_machine.py`
- **15 Zustände**: CREATED → ANALYZING → RAG_SEARCH → GENERATING_ARTIFACTS → WORKSPACE_READY → RUNNING_AGENT → TESTING → REPAIRING → VALIDATING → SYNTHESIZING → AWAITING_APPROVAL → FLASHING → FLASHED → COMPLETED/FAILED
- **Erweitert**: Um ARCHITECTING, IMPLEMENTING, STATIC_CHECK, SIMULATING, DEBUGGING, FPGA_PROGRAMMING, HARDWARE_TESTING, AUTONOMOUS_LIMIT_REACHED

### 3. EventBus
- **Datei**: `Schaltungsagent/src/domain/event_bus.py`
- **Pattern**: In-Memory Pub/Sub
- **27 Event-Typen**: Für Observability und Agent-Kommunikation

### 4. Domain Models (Pydantic)
- **TaskState**: Zentraler Task-Zustand
- **Event/EventType**: Strukturierte Events
- **KnowledgeBundle/ArtifactBundle**: RAG/Artefakt-Container
- **DesignState (NEU)**: Persistenter Projektzustand für Multi-Agent

### 5. Ports (ABCs) - Alle wiederverwendet
| Port | Interface | Implementierung |
|------|-----------|-----------------|
| LLMService | analyze, generate, classify, answer | OllamaLLMService |
| RAGService | retrieve_knowledge | VHDLRAGService |
| ValidationService | validate, validate_file | GHDLValidator |
| BitstreamService | build_bitstream | VivadoBitstreamService |
| FlashService | flash, detect_boards | VivadoFlashService, OpenFPGALoaderFlashService |
| OpenCodeService | execute | SubprocessOpenCodeService, DockerOpenCodeService |
| FileSystemService | workspace, files | LocalFileSystemService |
| EventPublisher | publish_event | EventBus |

### 6. Infrastructure Services (Alle wiederverwendet)
- **GHDLValidator**: 3-Stufen-Validierung (Analyse, Elaboration, Simulation)
- **VivadoBitstreamService**: Non-Project-Mode Bitstream-Erzeugung
- **VivadoFlashService**: JTAG-Flash via Vivado Hardware Manager
- **OpenFPGALoaderFlashService**: Flash via openFPGALoader
- **VHDLRAGService**: Template-Matching + Qdrant Vector Search
- **ProjectMemoryService**: memory.md pro Projekt

### 7. Domain Plugin System
- **DomainRegistry**: Dynamisches Laden von Domains (VHDL, später Verilog)
- **VHDL Plugin**: Templates, Prompts, Test-Definitions, Build-Definitions

### 8. API (FastAPI)
- REST-Endpunkte für Task-Management, Chat, Projekte, RAG
- WebSocket für Echtzeit-Events

## Workflow (Legacy)

```
User Request
    ↓
Classify (new_project/resume/question)
    ↓
Analyze → RAG Search → Generate Artifacts → Prepare Workspace
    ↓
Run Agent (OpenCode) → Test & Repair Loop (max 5) → Validate
    ↓
Synthesize (Vivado) → Await Approval → Flash (FPGA) → Complete
```

## Wichtige Design-Entscheidungen

1. **Human-in-the-Loop**: Approval vor Flash (threading.Event)
2. **Self-Healing**: Test & Repair Loop mit strukturierten Repair-Instruktionen
3. **Template-basiert**: Sichere Code-Generierung mit UNTRUSTED DATA-Markierung
4. **Multi-Board**: FPGA Registry für GateMate A1 und Arty S7-50