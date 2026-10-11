# Aktuelle System-Architektur (Analyse)

## Übersicht

Das bestehende `vhdl-agent` System ist eine **Hexagonal Architecture** (Ports & Adapters) für KI-gestützte VHDL-Entwicklung.

## Kernkomponenten

### 1. Supervisor-Orchestrator
- **Datei**: `Schaltungsagent/src/orchestrator/supervisor_orchestrator.py`
- **Klasse**: `SupervisorOrchestrator`
- **Verantwortung**: Task-Lifecycle, Phasensteuerung und Agentenkoordination

### 2. State Machine
- **Datei**: `Schaltungsagent/src/domain/state_machine.py`
- **Produktionsablauf**: ANALYZING → ARCHITECTING → IMPLEMENTING → STATIC_CHECK → SIMULATING → VALIDATING → SYNTHESIZING → FPGA_PROGRAMMING → HARDWARE_TESTING
- **Erweitert**: Um ARCHITECTING, IMPLEMENTING, STATIC_CHECK, SIMULATING, DEBUGGING, FPGA_PROGRAMMING, HARDWARE_TESTING, AUTONOMOUS_LIMIT_REACHED

### 3. EventBus
- **Datei**: `Schaltungsagent/src/domain/event_bus.py`
- **Pattern**: In-Memory Pub/Sub
- **27 Event-Typen**: Für Observability und Agent-Kommunikation

### 4. Domain Models (Pydantic)
- **TaskState**: Zentraler Task-Zustand
- **Event/EventType**: Strukturierte Events
- **ArtifactBundle**: Deterministische Artefakt-Fallbacks
- **DesignState (NEU)**: Persistenter Projektzustand für Multi-Agent

### 5. Ports (ABCs) - Alle wiederverwendet
| Port | Interface | Implementierung |
|------|-----------|-----------------|
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
- **Sprachmodell-Aufgaben**: ausschließlich OpenCode (Plan samt Namen, Module, Testbenches, Referenzmodelle, Reparaturen, Chat-Antworten); Ollama wurde 2026-10-10 entfernt
- **ProjectMemoryService**: memory.md pro Projekt

### 7. Domain Plugin System
- **DomainRegistry**: Dynamisches Laden von Domains (VHDL, später Verilog)
- **VHDL Plugin**: Templates, Prompts, Test-Definitions, Build-Definitions

### 8. API (FastAPI)
- REST-Endpunkte für Task-Management, Chat und Projekte
- WebSocket für Echtzeit-Events

## Workflow

```
User Request
    ↓
Classify (new_project/resume/question)
    ↓
Analyze → Architect → Implement (OpenCode) → Static Check → Simulate
    ↓
    Vorfilter/Debug/Repair (bei Fehlern) → Synthesize → Flash → Hardware Test
```

## Wichtige Design-Entscheidungen

1. **Autonom bis zum Board**: keine Benutzerfreigabe vor dem Flashen (entfernt 2026-10-11); der Benutzer wird nur gerufen, wenn die Eskalationsleiter erschöpft ist oder Werkzeug/Board fehlen
2. **Self-Healing**: Test & Repair Loop mit strukturierten Repair-Instruktionen
3. **OpenCode für alle Sprachmodell-Aufgaben**: kein zweites LLM
4. **Multi-Board**: FPGA Registry für GateMate A1 und Arty S7-50