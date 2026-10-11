# VHDL-Multiagentensystem — Vollständige Projektdokumentation

> **Projekt**: Bachelorarbeit — *Konzeption, Implementierung und Evaluation eines Multi-Agenten-Systems zur automatisierten FPGA-Hardware-Entwicklung*
> **Stand**: 2025-09-22
> **Technologiestack**: Python 3.12, VHDL-2008, GHDL, Vivado, OpenCode, Ollama/LangChain, Qdrant, FastAPI, WebSocket

---

## Inhaltsverzeichnis

1. [Architekturübersicht](#1-architekturübersicht)
2. [Schichtenarchitektur](#2-schichtenarchitektur)
3. [Agenten](#3-agenten)
4. [Orchestration](#4-orchestration)
5. [Domain-Modelle](#5-domain-Modelle)
6. [Services und Infrastruktur](#6-services-und-infrastruktur)
7. [Dashboard und API](#7-dashboard-und-api)
8. [Datenflüsse](#8-datenflüsse)
9. [Test-Suite](#9-test-suite)
10. [Offene Lücken](#10-offene-lücken)

---

## 1. Architekturübersicht

### 1.1 Gesamtübersicht

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           VHDL-MULTIAGENTENSYSTEM                               │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  ┌──────────────┐    ┌──────────────────┐    ┌──────────────────────┐          │
│  │   USER /      │───▶│    API-SERVER    │───▶│   SupervisorAgent   │          │
│  │   Dashboard   │    │  (FastAPI + WS)  │    │   (Autonomer Loop)  │          │
│  └──────────────┘    └──────────────────┘    └──────────┬───────────┘          │
│                                                         │                      │
│                    ┌────────────────────────────────────┼──────────────┐       │
│                    │                                    │              │       │
│                    ▼                                    ▼              │       │
│  ┌───────────────┐  ┌──────────────────┐  ┌──────────────────────┐  ┌────┐  │
│  │  LangGraph    │  │  SupervisorOrch. │  │  AgentFactory        │  │... │  │
│  │  Orchestrator │  │                  │  │                      │  │    │  │
│  │  (StateGraph) │  │                  │  │  Delegiert an:       │  │    │  │
│  └───────────────┘  └──────────────────┘  └──────────────────────┘  └────┘  │
│                                                                                 │
│                    ┌──────────────────────────────────────────────────┐        │
│                    │              AGENTEN-LAYER                       │        │
│                    │                                                │        │
│                    │  ┌──────────┐ ┌──────────┐ ┌───────────────┐  │        │
│                    │  │Architecture│ │  HDL      │ │  Verification │  │        │
│                    │  │Agent     │ │ Agent     │ │ Agent         │  │        │
│                    │  └──────────┘ └──────────┘ └───────────────┘  │        │
│                    │  ┌──────────┐ ┌──────────┐ ┌───────────────┐  │        │
│                    │  │Debug     │ │FPGA      │ │HardwareTest   │  │        │
│                    │  │Agent     │ │Agent     │ │Agent          │  │        │
│                    │  └──────────┘ └──────────┘ └───────────────┘  │        │
│                    └──────────────────────────────────────────────────┘        │
│                                                                                 │
│  ┌──────────────────────────────────────────────────────────────────────┐     │
│  │                    SERVICES / INFRASTRUCTURE                         │     │
│  │  OpenCode ─ LLM ─ RAG ─ GHDL ─ Vivado ─ FileSystem ─ Qdrant       │     │
│  └──────────────────────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Schichtendiagramm

```
┌─────────────────────────────────────────────┐
│               PRESENTATION LAYER            │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐ │
│  │Dashboard │  │  CLI     │  │  API      │ │
│  │(HTML/JS) │  │(argparse)│  │(FastAPI)  │ │
│  └─────┬────┘  └────┬─────┘  └─────┬──────┘ │
├───────┼─────────────┼─────────────┼─────────┤
│       │             │             │         │
│  ┌────▼─────────────▼─────────────▼──────┐  │
│  │           ORCHESTRATION LAYER         │  │
│  │  ┌─────────────────────────────────┐  │  │
│  │  │  SupervisorOrchestrator         │  │  │
│  │  │  ┌───────────────────────────┐  │  │  │
│  │  │  │  build_supervisor_agent() │  │  │  │
│  │  │  └───────────────────────────┘  │  │  │
│  │  │                                 │  │  │
│  │  │  ┌───────────────────────────┐  │  │  │
│  │  │  │  LangGraphOrchestrator    │  │  │  │
│  │  │  │  (StateGraph)             │  │  │  │
│  │  │  └───────────────────────────┘  │  │  │
│  │  └─────────────────────────────────┘  │  │
│  └───────────────────────────────────────┘  │
├─────────────────────────────────────────────┤
│              DOMAIN LAYER                   │
│  ┌───────────────────────────────────────┐  │
│  │  Agents: Supervisor, Architecture,    │  │
│  │          HDL, Verification, Debug,    │  │
│  │          FPGA, HardwareTest           │  │
│  │                                       │  │
│  │  Models: DesignState, TaskState,      │  │
│  │          AgentTask, AgentResult       │  │
│  │                                       │  │
│  │  Domain: TaskGraph, ContractChecker,  │  │
│  │          StateMachine, EventBus       │  │
│  │                                       │  │
│  │  Ports: LLM, RAG, OpenCode,          │  │
│  │         Validation, Synthesis,        │  │
│  │         Bitstream, Flash, FileSystem  │  │
│  └───────────────────────────────────────┘  │
├─────────────────────────────────────────────┤
│          INFRASTRUCTURE LAYER               │
│  ┌───────────────────────────────────────┐  │
│  │  Services: OpenCode, LLM, RAG,        │  │
│  │          FileSystem, Flash, Synthesis │  │
│  │                                       │  │
│  │  Infrastructure: GHDLValidator,       │  │
│  │                 VivadoBitstreamService│  │
│  │                 VivadoFlashService    │  │
│  │                 QdrantVectorStore     │  │
│  │                 OpenCodeWorker        │  │
│  │                 FileOwnershipRegistry │  │
│  └───────────────────────────────────────┘  │
├─────────────────────────────────────────────┤
│        TOOLCHAIN LAYER                      │
│  ┌───────────┐ ┌──────────┐ ┌────────────┐ │
│  │  GHDL     │ │ Vivado   │ │  OpenCode  │ │
│  │  (Sim)    │ │ (Synth)  │ │  (Repair)  │ │
│  └───────────┘ └──────────┘ └────────────┘ │
│  ┌──────────┐ ┌──────────┐ ┌────────────┐ │
│  │  Ollama  │ │ Qdrant   │ │  PySerial  │ │
│  │  (LLM)  │ │ (RAG)    │ │  (UART)    │ │
│  └──────────┘ └──────────┘ └────────────┘ │
└─────────────────────────────────────────────┘
```

---

## 2. Schichtenarchitektur

### 2.1 Domain-Ports (Schnittstellen)

Jeder Agent und Service kommuniziert über **Domain-Ports** — abstrakte Basisklassen, die die Verträge definieren:

```
┌─────────────────────────────────────────────────────┐
│              domain/ports/                            │
│                                                     │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐│
│  │ LLMService   │ │ RAGService   │ │OpenCodeService││
│  │ ABC          │ │ ABC          │ │ ABC          ││
│  │              │ │              │ │              ││
│  │•analyze_req  │ │•retrieve_knw │ │•execute()    ││
│  │•generate_code│ │•retrieve_knw │ │•execute()    ││
│  │•classify_req │ │•chat_query() │ │              ││
│  │•answer_ques. │ │•index_data() │ │              ││
│  └──────┬───────┘ └──────┬───────┘ └──────┬───────┘│
├──────────┼───────────────┼───────────────┼─────────┤
│          │               │               │         │
│  ┌───────▼───────────────▼───────────────▼───────┐ │
│  │              Infrastructure Adapters          │ │
│  │                                               │ │
│  │ ┌──────────┐ ┌──────────┐ ┌───────────────┐  │ │
│  │ │StubLLM  │ │VHDLRAG  │ │SubprocessOC  │  │ │
│  │ │Service  │ │Service  │ │DockerOC Svc  │  │ │
│  │ └──────────┘ └──────────┘ └───────────────┘  │ │
│  │ ┌──────────┐ ┌──────────┐ ┌───────────────┐  │ │
│  │ │OllamaLLM│ │QdrantVS │ │OpenCodeWorkr │  │ │
│  │ │Service  │ │         │ │              │  │ │
│  │ └──────────┘ └──────────┘ └───────────────┘  │ │
│  └───────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐│
│  │ValidationSvc │ │SynthesisSvc │ │BitstreamSvc  ││
│  │ ABC          │ │ ABC          │ │ ABC          ││
│  │              │ │              │ │              ││
│  │•validate()   │ │•synthesize() │ │•build_bs()   ││
│  │•validate_    │ │•toolchain_av │ │•toolchain_av ││
│  │  file()      │ │              │ │              ││
│  └──────┬───────┘ └──────┬───────┘ └──────┬───────┘│
│         │               │               │         │
│  ┌──────▼───────────────▼───────────────▼───────┐ │
│  │         Concrete Implementations              │ │
│  │  ┌──────────┐ ┌──────────┐ ┌───────────────┐ │ │
│  │  │GHDLValid │ │GHDLSynth │ │VivadoBitstream│ │ │
│  │  │(3-step)  │ │Service   │ │Service        │ │ │
│  │  └──────────┘ └──────────┘ └───────────────┘ │ │
│  │  ┌──────────┐ ┌──────────┐ ┌───────────────┐ │ │
│  │  │VivadoFl  │ │OpenFPGAL │ │VivadoArtifa   │ │ │
│  │  │ashServic │ │oaderFls │ │cts            │ │ │
│  │  └──────────┘ └──────────┘ └───────────────┘ │ │
│  └───────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

### 2.2 Abhängigkeitsgraph der Services

```
SupervisorOrchestrator
    │
    ├──► build_supervisor_agent()
    │       │
    │       ├──► ArchitectureAgent
    │       │       ├──► LLMService
    │       │       ├──► RAGService
    │       │       └──► EventPublisher
    │       │
    │       ├──► HDLAgent
    │       │       ├──► LLMService
    │       │       ├──► RAGService
    │       │       ├──► OpenCodeService
    │       │       ├──► FileSystemService
    │       │       └──► EventPublisher
    │       │
    │       ├──► VerificationAgent
    │       │       ├──► LLMService
    │       │       ├──► RAGService
    │       │       ├──► FileSystemService
    │       │       ├──► OpenCodeService
    │       │       ├──► EventPublisher
    │       │       └──► ValidationService(GHDLValidator)
    │       │
    │       ├──► DebugAgent
    │       │       ├──► LLMService
    │       │       └──► RAGService
    │       │
    │       ├──► FPGAAgent
    │       │       ├──► LLMService
    │       │       ├──► RAGService
    │       │       ├──► FileSystemService
    │       │       ├──► EventPublisher
    │       │       ├──► BitstreamService(VivadoBitstreamService)
    │       │       ├──► FlashService(VivadoFlashService)
    │       │       └──► FlashService(OpenFPGALoaderFlashService)
    │       │
    │       └──► HardwareTestAgent
    │               ├──► LLMService
    │               ├──► RAGService
    │               ├──► FileSystemService
    │               ├──► EventPublisher
    │               └──► HardwareTestInterface(Mock/UART)
    │
    └──► EventBus ──► broadcast_sync ──► WebSocket clients
```

---

## 3. Agenten

### 3.1 Agenten-Übersicht

```
┌─────────────────────────────────────────────────────────────┐
│                     AGENTEN-LAYER                            │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              SupervisorAgent                          │   │
│  │  (939 Zeilen - Hauptorchestrierer)                    │   │
│  │                                                      │   │
│  │  Zuständig für: Autonomer Loop, Phasensteuerung,      │   │
│  │  Reparatur-Management, Safety-Limits                  │   │
│  └─────────────────────┬────────────────────────────────┘   │
│                        │ nutzt                                │
│  ┌─────────────────────▼────────────────────────────────┐   │
│  │              ArchitectureAgent                        │   │
│  │  ┌────────────────────────────────────────────────┐  │   │
│  │  │ _create_architecture()                         │  │   │
│  │  │ _refine_architecture()                         │  │   │
│  │  │ _validate_architecture()                       │  │   │
│  │  │ _parse_architecture_yaml()                     │  │   │
│  │  │ _generate_task_graph()                         │  │   │
│  │  └────────────────────────────────────────────────┘  │   │
│  │  Produziert: ArchitectureInfo, ArchitectureHandoff   │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              HDLAgent                                 │   │
│  │  ┌────────────────────────────────────────────────┐  │   │
│  │  │ _implement_hdl()        (OpenCode + LLM)       │  │   │
│  │  │ _fix_hdl()              (OpenCode + Kontext)   │  │   │
│  │  │ _modify_hdl()           (OpenCode)             │  │   │
│  │  │ _generate_testbenches() (LLM)                  │  │   │
│  │  │ _review_hdl()           (Statische Prüfung)    │  │   │
│  │  └────────────────────────────────────────────────┘  │   │
│  │  Produziert: .vhd Dateien, _tb.vhd Testbenches       │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              VerificationAgent                        │   │
│  │  ┌────────────────────────────────────────────────┐  │   │
│  │  │ _run_verification()     (GHDLValidator)        │  │   │
│  │  │ _create_testplan()      (LLM)                  │  │   │
│  │  │ _generate_testbench()   (LLM + VHDL)           │  │   │
│  │  │ _analyze_coverage()     (Placeholder)          │  │   │
│  │  └────────────────────────────────────────────────┘  │   │
│  │  Produziert: ValidationResult, Testbench-Dateien     │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              DebugAgent                               │   │
│  │  ┌────────────────────────────────────────────────┐  │   │
│  │  │ _diagnose()              (LLM + Fallback)      │  │   │
│  │  │ _fallback_diagnosis()    (13 Regex-Patterns)   │  │   │
│  │  │ _extract_modules_from_errors() (Datei-Analyse) │  │   │
│  │  │ _recommend_repair()      (Reparatur-Aktion)    │  │   │
│  │  └────────────────────────────────────────────────┘  │   │
│  │  Produziert: DebugDiagnosis                          │   │
│  │  ┌───────────────────────────────────────────────┐  │   │
│  │  │ 13 Error-Typen:                               │  │   │
│  │  │ infrastructure, syntax_error, type_error,     │  │   │
│  │  │ elaboration_error, interface_mismatch,         │  │   │
│  │  │ clock_reset_error, testbench_error,            │  │   │
│  │  │ functional_simulation_error, synthesis_error,  │  │   │
│  │  │ timing_error, resource_error,                  │  │   │
│  │  │ bitstream_error, hardware_error                │  │   │
│  │  └───────────────────────────────────────────────┘  │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              FPGAAgent                                │   │
│  │  ┌────────────────────────────────────────────────┐  │   │
│  │  │ _run_synthesis()        (GHDL + Vivado)        │  │   │
│  │  │ _build_bitstream()      (VivadoBitstream)      │  │   │
│  │  │ _flash_fpga()           (VivadoFlash/OpenFPGA) │  │   │
│  │  │ _analyze_timing()       (HARDCODED ⚠️)         │  │   │
│  │  │ _check_resources()      (HARDCODED ⚠️)         │  │   │
│  │  └────────────────────────────────────────────────┘  │   │
│  │  Produziert: Bitstream, Flash-Ergebnisse             │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              HardwareTestAgent                        │   │
│  │  ┌────────────────────────────────────────────────┐  │   │
│  │  │ _run_hardware_test()    (Mock/UART)            │  │   │
│  │  │ _define_test_suite()    (projektspezifisch)    │  │   │
│  │  │ _run_test_suite()       (durch UART)           │  │   │
│  │  │ _validate_hardware()    (PING-Test)            │  │   │
│  │  └────────────────────────────────────────────────┘  │   │
│  │  Produziert: HardwareTestInfo                        │   │
│  │  Interfaces: MockHardwareTestInterface,              │   │
│  │              UARTHardwareTestInterface               │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 SupervisorAgent — Autonomer Loop

```
┌──────────────────────────────────────────────────────────────┐
│                    _run_autonomous_loop()                     │
│                                                              │
│  while iteration < max_iterations(20):                       │
│  │                                                           │
│  │  ┌────────────────────────────────────────────┐          │
│  │  │ 1. Check Safety Limits                     │          │
│  │  │    _check_safety_limits()                  │          │
│  │  │    - max_iterations                        │          │
│  │  │    - max_repairs_per_stage(5)              │          │
│  │  │    - max_simulation_failures(10)           │          │
│  │  │    - max_hardware_failures(5)              │          │
│  │  └──────────────────┬─────────────────────────┘          │
│  │                     │                                    │
│  │  ┌──────────────────▼─────────────────────────┐          │
│  │  │ 2. Execute Stage                           │          │
│  │  │    _execute_stage(current_stage)           │          │
│  │  │    ┌────────────────────────────────┐      │          │
│  │  │    │ ANALYZING → _run_analysis()  │      │          │
│  │  │    │ ARCHITECTING → _run_arch()   │      │          │
│  │  │    │ IMPLEMENTING → _run_impl()   │      │          │
│  │  │    │ STATIC_CHECK → _run_static() │      │          │
│  │  │    │ SIMULATING → _run_sim()      │      │          │
│  │  │    │ DEBUGGING → _run_debug()     │      │          │
│  │  │    │ SYNTHESIZING → _run_synth()  │      │          │
│  │  │    │ FPGA_PROGRAMMING → _run_fpga()│      │          │
│  │  │    │ HARDWARE_TESTING → _run_hw() │      │          │
│  │  │    └────────────────────────────────┘      │          │
│  │  └──────────────────┬─────────────────────────┘          │
│  │                     │                                    │
│  │  ┌──────────────────▼─────────────────────────┐          │
│  │  │ 3. Handle Result                           │          │
│  │  │                                            │          │
│  │  │  COMPLETED → next_stage or DONE            │          │
│  │  │  FAILED → _handle_failure() → Debug → Repair│          │
│  │  │  BLOCKED → _request_human_intervention()   │          │
│  │  └──────────────────┬─────────────────────────┘          │
│  │                     │                                    │
│  │  ┌──────────────────▼─────────────────────────┐          │
│  │  │ 4. If Failed → Repair Loop                 │          │
│  │  │                                            │          │
│  │  │  _handle_failure(stage, result):           │          │
│  │  │    1. _run_debugging() → DebugDiagnosis    │          │
│  │  │    2. _run_repair() → HDLAgent._fix_hdl()  │          │
│  │  │       ├── Hash-Vergleich (No-Progress)     │          │
│  │  │       ├── Identical-Error-Erkennung        │          │
│  │  │       └── Return to IMPLEMENTING           │          │
│  │  └────────────────────────────────────────────┘          │
│  │                                                           │
│  └──────────────────────────────────────────────────────────┘
```

### 3.3 Reparatur-Workflow (Detail)

```
┌──────────────────────────────────────────────────────────┐
│               Reparatur-Workflow                          │
│                                                          │
│  Simulation/Synthesis Failed                             │
│         │                                                │
│         ▼                                                │
│  ┌─────────────────────┐                                │
│  │ DebugAgent          │                                │
│  │ _diagnose()         │                                │
│  │                     │                                │
│  │ 1. LLM-Analyse      │                                │
│  │    (Prompt mit      │                                │
│  │     Fehlermeldungen) │                                │
│  │                     │                                │
│  │ 2. Fallback:        │                                │
│  │    classify_error() │                                │
│  │    13 Regex-Patterns│                                │
│  └────────┬────────────┘                                │
│           │                                             │
│           ▼                                             │
│  ┌─────────────────────┐                                │
│  │ DebugDiagnosis      │                                │
│  │                     │                                │
│  │ - status: failed    │                                │
│  │ - failure_type:     │                                │
│  │   (13 Typen)        │                                │
│  │ - suspected_modules │                                │
│  │ - evidence[]        │                                │
│  │ - recommended_action│                                │
│  │ - severity          │                                │
│  └────────┬────────────┘                                │
│           │                                             │
│           ▼                                             │
│  ┌─────────────────────┐                                │
│  │ _determine_repair_  │                                │
│  │ target()            │                                │
│  │                     │                                │
│  │ simulation/timing → │                                │
│  │   IMPLEMENTING      │                                │
│  │ architecture/iface →│                                │
│  │   ARCHITECTING      │                                │
│  │ hardware/flash →    │                                │
│  │   FPGA_PROGRAMMING  │                                │
│  │ infrastructure →    │                                │
│  │   BLOCKED           │                                │
│  └────────┬────────────┘                                │
│           │                                             │
│           ▼                                             │
│  ┌─────────────────────┐                                │
│  │ HDLAgent            │                                │
│  │ _fix_hdl()          │                                │
│  │                     │                                │
│  │ 1. OpenCodeContext  │                                │
│  │    Builder          │                                │
│  │    (17 Sektionen)   │                                │
│  │                     │                                │
│  │ 2. OpenCode.execute │                                │
│  │    (nur betroffene │                                │
│  │     Dateien)        │                                │
│  │                     │                                │
│  │ 3. SHA-256 Prüfung │                                │
│  │    → No-Progress?   │                                │
│  │                     │                                │
│  └────────┬────────────┘                                │
│           │                                             │
│           ▼                                             │
│  ┌─────────────────────┐                                │
│  │ No-Progress-Erkennung│                                │
│  │                     │                                │
│  │ SHA-256 Hash        │                                │
│  │ Vergleich           │                                │
│  │                     │                                │
│  │ Identisch →         │                                │
│  │   NO_PROGRESS Event │                                │
│  │   FAILED Status     │                                │
│  │                     │                                │
│  │ Identical Error     │                                │
│  │ → IDENTICAL_ERROR   │                                │
│  │   → AUTONOMOUS_LIMIT│                                │
│  └─────────────────────┘                                │
└──────────────────────────────────────────────────────────┘
```

---

## 4. Orchestration

### 4.1 Zwei Orchestrator-Pfade

```
┌───────────────────────────────────────────────────────────┐
│                    ORCHESTRATOR-LAYER                       │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐  │
│  │           SupervisorOrchestrator                    │  │
│  │           (Produktions-Orchestrator)                 │  │
│  │                                                     │  │
│  │  API: execute(), execute_async(), handle_chat()     │  │
│  │  Delegation: _run_analysis() ... _run_hardware_test()│  │
│  └──────────────────┬──────────────────────────────────┘  │
│                     │                                      │
│  ┌──────────────────▼──────────────────────────────────┐  │
│  │           AgentFactory                              │  │
│  │           (build_supervisor_agent())                 │  │
│  │                                                     │  │
│  │  Erzeugt alle 6 Sub-Agenten mit gemeinsamen         │  │
│  │  Services:                                          │  │
│  │  - ArchitectureAgent                                │  │
│  │  - HDLAgent                                         │  │
│  │  - VerificationAgent                                │  │
│  │  - DebugAgent                                       │  │
│  │  - FPGAAgent                                        │  │
│  │  - HardwareTestAgent                                │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐  │
│  │           LangGraphOrchestrator (Alternative)       │  │
│  │                                                     │  │
│  │  StateGraph mit 9 Knoten + bedingten Kanten         │  │
│  │                                                     │  │
│  │  analyze → architect → implement → verify           │  │
│  │              ↘ debug → repair → implement           │  │
│  │              → synthesize → flash → hardware_test   │  │
│  │              → END                                    │  │
│  │                                                     │  │
│  │  Delegiert an SupervisorAgent._run_*() Methoden     │  │
│  └─────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────┘
```

### 4.2 LangGraph State Graph

```
┌──────────────────────────────────────────────────────────┐
│                  StateGraph                               │
│                  WorkflowState                            │
│                                                          │
│  ┌──────────┐                                           │
│  │  __start__│                                           │
│  └────┬─────┘                                           │
│       │                                                  │
│       ▼                                                  │
│  ┌──────────┐  edge: no error                           │
│  │  analyze │──────────────────────┐                    │
│  └────┬─────┘                     │                    │
│       │  edge: error → END       │                    │
│       ▼                          │                    │
│  ┌──────────┐                    │                    │
│  │ architect│──┐                 │                    │
│  └────┬─────┘  │                 │                    │
│       │         │                │                    │
│       ▼         │                │                    │
│  ┌──────────┐  │  edge: error   │                    │
│  │ implement│──┘  → END         │                    │
│  └────┬─────┘                   │                    │
│       │                         │                    │
│       │  edge: error → debug    │                    │
│       ▼                         │                    │
│  ┌──────────┐                   │                    │
│  │  verify  │──┐                │                    │
│  └────┬─────┘  │                │                    │
│       │         │               │                    │
│       │  edge: error → debug    │                    │
│       ▼         │               │                    │
│  ┌──────────┐  │               │                    │
│  │ synthesize│──┘              │                    │
│  └────┬─────┘                  │                    │
│       │                        │                    │
│       │  edge: error → debug   │                    │
│       ▼                        │                    │
│  ┌──────────┐                  │                    │
│  │   flash  │──┐               │                    │
│  └────┬─────┘  │               │                    │
│       │         │              │                    │
│       │  edge: error → debug   │                    │
│       ▼         │              │                    │
│  ┌──────────────┐              │                    │
│  │hardware_test │──┐           │                    │
│  └────┬─────────┘  │           │                    │
│       │            │           │                    │
│       │  edge:     │           │                    │
│       │  completed │           │                    │
│       │  → END     │           │                    │
│       │  error → debug      │                    │
│       │  → debug            │                    │
│       ▼                     │                    │
│  ┌──────────┐                │                    │
│  │   END    │◄───────────────┘                    │
│  └──────────┘                                     │
│                                                  │
│  Loopback: debug → repair → implement             │
│  (max_iterations begrenzt)                        │
└──────────────────────────────────────────────────┘
```

### 4.3 Event-Fluss im Workflow

```
┌────────────┐     ┌────────────┐     ┌────────────┐
│  ANALYZING │     │ ARCHITECT. │     │ IMPLEMENT. │
│            │     │            │     │            │
│ STAGE_START│     │ STAGE_START│     │ STAGE_START│
│ → Analyz.  │     │ → Architec.│     │ → Implement│
└─────┬──────┘     └─────┬──────┘     └─────┬──────┘
      │                 │                 │
      │    ┌────────────┘                 │
      │    │    ┌─────────────────────────┘
      │    │    │
      ▼    ▼    ▼
┌──────────────────────────────────────────┐
│           EVENT_BUS                      │
│                                          │
│  • TASK_CREATED                          │
│  • STATE_CHANGED (status→stage)          │
│  • STAGE_STARTED (stage name)            │
│  • AGENT_STARTED/FINISHED                │
│  • FILES_CREATED                         │
│  • ANALYSIS_FINISHED                     │
│  • ARCHITECTURE_CREATED                  │
│  • IMPLEMENTATION_COMPLETED              │
│  • STATIC_CHECK_PASSED/FAILED            │
│  • SIMULATION_STARTED/PASSED/FAILED      │
│  • DEBUG_STARTED/COMPLETED               │
│  • REPAIR_ASSIGNED/COMPLETED/FAILED      │
│  • NO_PROGRESS / IDENTICAL_ERROR         │
│  • SYNTHESIS_STARTED/FINISHED            │
│  • FLASH_STARTED/FINISHED                │
│  • HARDWARE_TEST_STARTED/PASSED/FAILED   │
│  • TASK_COMPLETED                        │
│  • TASK_FAILED                           │
│  • AUTONOMOUS_LIMIT_REACHED              │
└──────────────────┬───────────────────────┘
                   │
                   ▼
          ┌──────────────┐
          │  WebSocket   │
          │  Broadcast   │
          │  (Dashboard) │
          └──────────────┘
```

---

## 5. Domain-Modelle

### 5.1 DesignState — Der Haupt-Aggregat

```
┌───────────────────────────────────────────────────────────┐
│                    DesignState                               │
│                    (Pydantic BaseModel)                      │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ project: {id, name, version}                         │  │
│  └─────────────────────────────────────────────────────┘  │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ requirements: list[Requirement]                      │  │
│  │   - id, description, status, satisfied_by, verified  │  │
│  └─────────────────────────────────────────────────────┘  │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ architecture: ArchitectureInfo                       │  │
│  │   - status, version, modules[], interfaces[],        │  │
│  │     clock_domain, reset_concept, decisions[]         │  │
│  └─────────────────────────────────────────────────────┘  │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ implementation: ImplementationInfo                   │  │
│  │   - status, files[], generated_files[], modified_    │  │
│  └─────────────────────────────────────────────────────┘  │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ verification: VerificationInfo                       │  │
│  │   - status, tests[], passed, failed, coverage        │  │
│  └─────────────────────────────────────────────────────┘  │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ synthesis: SynthesisInfo                             │  │
│  │   - status, timing, resources, bitstream_path,       │  │
│  │     fpga_part, errors[]                              │  │
│  └─────────────────────────────────────────────────────┘  │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ fpga: FPGAInfo                                       │  │
│  │   - target, programmed, bitstream, board_detected,   │  │
│  │     programmer                                       │  │
│  └─────────────────────────────────────────────────────┘  │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ hardware: HardwareTestInfo                           │  │
│  │   - status, tests[], passed, failed, log             │  │
│  └─────────────────────────────────────────────────────┘  │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ diagnostics: DiagnosticInfo                          │  │
│  │   - active, history[]                                │  │
│  └─────────────────────────────────────────────────────┘  │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ iterations: {stage: count}                           │  │
│  │ human_interventions: {count, reasons[], last}        │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                           │
│  current_stage: DesignStage                                │
│  metadata: dict                                            │
│                                                          │
│  Methoden:                                                 │
│  • transition_to(stage)                                  │
│  • increment_iteration(stage)                            │
│  • to_yaml() / from_yaml(yaml_str)                       │
│  • to_dict() / to_json()                                 │
└───────────────────────────────────────────────────────────┘
```

### 5.2 DesignStage-Enum

```
┌─────────────────────────────────────────────────────┐
│               DesignStage (Enum)                      │
│                                                     │
│  CREATED ──→ ANALYZING ──→ ARCHITECTING ──→ IMPLEMENTING│
│                                         │              │
│                                         ▼              │
│                                    STATIC_CHECK        │
│                                         │              │
│                                         ▼              │
│                                    SIMULATING          │
│                                         │              │
│                                         ▼              │
│                                    VALIDATING          │
│                                         │              │
│                            ┌────────────┼────┐         │
│                            │            │    │         │
│                     FAILED    │      SUCCESS │         │
│                            │            │    │         │
│                            ▼            ▼    ▼         │
│                       DEBUGGING ──→ REPAIRING         │
│                            │        (loop back to      │
│                            │         IMPLEMENTING)     │
│                            │                          │
│                     SUCCESS ▼                          │
│                            │                          │
│                     SYNTHESIZING                         │
│                            │                          │
│                            ▼                          │
│                     FPGA_PROGRAMMING                   │
│                            │                          │
│                            ▼                          │
│                     HARDWARE_TESTING                   │
│                            │                          │
│                     ┌──────┴──────┐                   │
│                     │             │                   │
│               COMPLETED    FAILED                       │
│                     │             │                   │
│                     ▼             ▼                   │
│              (DONE)       AUTONOMOUS_LIMIT              │
│                           _REACHED                    │
└─────────────────────────────────────────────────────┘
```

### 5.3 TaskGraph mit File-Ownership

```
┌───────────────────────────────────────────────────────────┐
│                    TaskGraph                                │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ _tasks: dict[str, AgentTask]                         │  │
│  │ _dependency_map: dict[str, set[str]]                 │  │
│  │ _ownership: FileOwnershipRegistry                    │  │
│  │ _invalidated: set[str]                               │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ FileOwnershipRegistry                                │  │
│  │                                                      │  │
│  │ _ownerships: task_id → set[file_paths]               │  │
│  │ _file_to_task: file_path → task_id                   │  │
│  │                                                      │  │
│  │ claim(task_id, files) → conflicts[]                  │  │
│  │ release(task_id)                                     │  │
│  │ check_access(task_id, file_path) → bool              │  │
│  │ get_owner(file_path) → task_id                       │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ Beispiel DAG:                                        │  │
│  │                                                      │  │
│  │   implement_top → verify_top                        │  │
│  │   implement_modA → verify_top                       │  │
│  │   implement_modB → verify_top                       │  │
│  │   verify_top → synthesize                           │  │
│  │   synthesize → build_bitstream                      │  │
│  │   build_bitstream → flash (ohne Benutzerfreigabe)   │  │
│  │   flash → hardware_test                             │  │
│  └─────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────┘
```

### 5.4 ContractChecker

```
┌───────────────────────────────────────────────────────────┐
│                  ContractChecker                            │
│                  (src/domain/agents/contract_check.py)      │
│                                                           │
│  check(architecture, workspace) → ContractCheckResult     │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ Prüfungen:                                          │  │
│  │ ✓ Entity-Port-Namen existieren                      │  │
│  │ ✓ Interface-Quelle/Ziel existieren                  │  │
│  │ ✓ Top-Level-Modul existiert                         │  │
│  │                                                     │  │
│  │ ✗ NICHT implementiert:                              │  │
│  │   Bitbreiten-Synchronisation                        │  │
│  │   signed/unsigned                                   │  │
│  │   Clock/Reset-Polarität                             │  │
│  │   Handshake-Protokolle                              │  │
│  │   Latenzen                                          │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                           │
│  Status: Existiert, aber NICHT im Produktions-Pipeline     │
│          (wird in test_multi_agent_collaboration.py        │
│          aufgerufen, aber nicht vom Supervisor aufgerufen) │
└───────────────────────────────────────────────────────────┘
```

---

## 6. Services und Infrastruktur

### 6.1 OpenCode-Service-Stack

```
┌───────────────────────────────────────────────────────────┐
│              OpenCode Service Stack                         │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  OpenCodeService (ABC)                              │  │
│  │  ┌─────────────────────────────────────────────┐   │  │
│  │  │  SubprocessOpenCodeService                  │   │  │
│  │  │  • subprocess.run("opencode run ...")       │   │  │
│  │  │  • Fallback zu opencode/nemotron-3.5        │   │  │
│  │  │  • bei Quota/Rate-Limit                     │   │  │
│  │  └─────────────────────────────────────────────┘   │  │
│  │  ┌─────────────────────────────────────────────┐   │  │
│  │  │  DockerOpenCodeService                      │   │  │
│  │  │  • docker exec (container)                  │   │  │
│  │  │  • Fallback zu Subprocess bei Docker-Fehlern│   │  │
│  │  └─────────────────────────────────────────────┘   │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  OpenCodeContextBuilder                             │  │
│  │  • _build_project_section()                         │  │
│  │  • _build_fpga_section()                            │  │
│  │  • _build_requirements_section()                    │  │
│  │  • _build_architecture_section()                    │  │
│  │  • _build_current_design_section()                  │  │
│  │  • _build_task_section()                            │  │
│  │  • _build_interfaces_section()                      │  │
│  │  • _build_constraints_section()                     │  │
│  │  • _build_rag_section()                             │  │
│  │  • _build_previous_failures_section()               │  │
│  │  • _build_acceptance_criteria_section()             │  │
│  │  • _build_expected_artifacts_section()              │  │
│  │  • _build_instructions_section()                    │  │
│  │                                                     │  │
│  │  → Gibt einen formatierten TEXT-STRING zurück        │  │
│  │    (NICHT maschinenlesbarer Plan)                    │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  OpenCodeWorker (infrastructure/opencode/)           │  │
│  │  • WorkerTask / WorkerResult                        │  │
│  │  • FileOwnershipRegistry Integration                │  │
│  │  • assign_files() / can_access_file()               │  │
│  │  • WorkerPool für parallele Worker                  │  │
│  │                                                     │  │
│  │  Achtung: Wird NICHT im Produktions-Pfad verwendet!  │  │
│  │  Die Services werden direkt aufgerufen.              │  │
│  └─────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────┘
```

### 6.2 GHDL-Validierungs-Pipeline

```
┌───────────────────────────────────────────────────────────┐
│              GHDLValidator (3-Phase)                        │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  Phase A: Analyse                                    │  │
│  │  • Sortiere VHDL-Dateien nach Abhängigkeit          │  │
│  │  • Führe GHDL analyse für jede Datei aus            │  │
│  │  • Bei Fehler → sofortiger Abbruch                  │  │
│  └─────────────────────────────────────────────────────┘  │
│                     │                                    │
│                     ▼                                    │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  Phase B: Elaboration                                │  │
│  │  • Extrahiere Testbench-Entity                       │  │
│  │  • Elaboriere Testbench-Top-Level                    │  │
│  │  • Bei Fehler → sofortiger Abbruch                  │  │
│  └─────────────────────────────────────────────────────┘  │
│                     │                                    │
│                     ▼                                    │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  Phase C: Simulation                                 │  │
│  │  • Führe GHDL simulation mit --assert-level=error  │  │
│  │  • Prüfe auf Assertion-Failures                     │  │
│  │  • Prüfe auf TB_COMPLETE Marker                     │  │
│  │  • Prüfe auf has_assertions                         │  │
│  │  • Parse failed_case (FAIL CASE data=<n>)           │  │
│  │                                                     │  │
│  │  Exit-Code 0 allein = KEINE Bestätigung             │  │
│  │  TB_COMPLETE Marker MUSS vorhanden sein             │  │
│  │  Assertions MIT severity error/failure MUSS da sein │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  Output: ValidationResult                            │  │
│  │  • passed: bool                                      │  │
│  │  • message: str                                      │  │
│  │  • details: {steps[], files_checked[], testbench,    │  │
│  │     completion_marker, assertions_present}            │  │
│  └─────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────┘
```

### 6.3 Vivado Bitstream-Generierung

```
┌───────────────────────────────────────────────────────────┐
│          VivadoBitstreamService                           │
│                                                           │
│  build_bitstream(workspace, target, domain, top_entity)   │
│                                                           │
│  1. Finde VHDL-Dateien und Entities                       │
│     └── Auto-detect: Wenn genau 1 Entity ohne Deps      │
│         → Top-Level                                       │
│     └── Wenn mehrere → Fehler (ambiguous)               │
│                                                           │
│  2. Bestimme FPGA-Konfiguration                           │
│     └── load_fpga_registry() → fpgas.yaml               │
│     └── Abhängig von target (z.B. arty_s7_50)           │
│                                                           │
│  3. Generiere Tcl-Skript                                  │
│     └── create_project (in-memory)                       │
│     └── read_vhdl / read_xdc                             │
│     └── synth_design / opt_design / place_design         │
│     └── route_design                                     │
│     └── write_bitstream                                  │
│     └── report_utilization → utilization.rpt            │
│     └── report_timing_summary → timing.rpt              │
│                                                           │
│  4. Führe Vivado aus                                     │
│     └── vivado -mode batch -source <tcl>                │
│     └── settings64.sh einbinden                          │
│     └── 4GB Memory Limit                                │
│                                                           │
│  5. Verifiziere Bitstream                                │
│     └── .bit Datei existiert?                            │
│     └── Dateigröße > 0?                                  │
│                                                           │
│  ⚠️ CRITICAL GAP:                                       │
│     Die .rpt-Dateien werden NICHT geparst!              │
│     WNS/TNS/Fmax/LUT/FF/BRAM/DSP/DRC = HARDCODED oder   │
│     gar nicht verfügbar                                  │
└───────────────────────────────────────────────────────────┘
```

---

## 7. Dashboard und API

### 7.1 Dashboard-Architektur

```
┌───────────────────────────────────────────────────────────┐
│                    Dashboard                                │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  index.html                                         │  │
│  │  ┌──────────────┐ ┌──────────────┐ ┌─────────────┐ │  │
│  │  │  Sidebar     │ │  Chat        │ │  Right      │  │  │
│  │  │  Navigation  │ │  Messages    │ │  Panel      │  │  │
│  │  │              │ │              │ │             │  │  │
│  │  │  AI Engineer │ │              │ │  Project    │  │  │
│  │  │  RAG         │ │              │ │  Files      │  │  │
│  │  │  Projekte    │ │              │ │  Logs       │  │  │
│  │  │  Settings    │ │              │ │  Tests      │  │  │
│  │  │  Code        │ │              │ │             │  │  │
│  │  └──────────────┘ └──────────────┘ └─────────────┘ │  │
│  │                                                     │  │
│  │  Workflow Steps:                                    │  │
│  │  CREATED → ANALYZING → ARCHITECTING → IMPLEMENTING  │  │
│  │  → STATIC_CHECK → SIMULATING → DEBUGGING → REPAIRING│  │
│  │  → SYNTHESIZING → FPGA_PROGRAMMING → HARDWARE_TEST  │  │
│  │  → COMPLETED/FAILED                                 │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  app.js                                               │  │
│  │  • WebSocket Verbindung                              │  │
│  │  • Event-Handler für alle EventType                  │  │
│  │  • updateWorkflow(stage)                             │  │
│  │  • setBadgeFromStatus(status)                        │  │
│  │  • handleServerMessage(msg)                          │  │
│  │  • sendTask(request, files)                          │  │
│  └─────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────┘
```

### 7.2 API-Endpunkte

```
┌───────────────────────────────────────────────────────────┐
│                    API (FastAPI)                           │
│                                                           │
│  GET    /api/tasks                                        │
│  GET    /api/tasks/{task_id}                              │
│  POST   /api/task                                         │
│  POST   /api/task/sync                                    │
│  POST   /api/chat                                         │
│  POST   /api/chat/upload                                  │
│  GET    /api/domains                                      │
│  GET    /api/eda-tools                                    │
│  GET    /api/debug                                        │
│  POST   /api/cleanup                                      │
│  GET    /api/projects                                     │
│  GET    /api/projects/{project}                           │
│  GET    /api/projects/{project}/memory                    │
│  DELETE /api/projects/{project}                           │
│  POST   /api/projects/{project}/open-tool                 │
│  GET    /api/projects/{project}/file?path=...             │
│  GET    /api/rag/files                                    │
│  POST   /api/rag/upload                                   │
│  POST   /api/rag/index                                    │
│                                                           │
│  WebSocket: /ws                                           │
│  • action: run_task / chat                                │
│  • EventTypes: TASK_CREATED, STATE_CHANGED,               │
│    TASK_COMPLETED, TASK_FAILED, CHAT_RESPONSE,            │
│    STAGE_STARTED, STAGE_FINISHED, ...                     │
└───────────────────────────────────────────────────────────┘
```

### 7.3 WebSocket-Event-Flow

```
┌────────────┐     ┌────────────┐     ┌────────────┐     ┌────────────┐
│            │     │            │     │            │     │            │
│   User     │────▶│  API-Server│────▶│  Supervisor│────▶│  Sub-Agent │
│            │     │            │     │            │     │            │
└─────┬──────┘     └─────┬──────┘     └─────┬──────┘     └─────┬──────┘
      │                  │                   │                    │
      │   WebSocket      │                   │                    │
      │◀──── broadcast ──│                   │                    │
      │                  │                   │                    │
      ▼                  ▼                   ▼                    ▼
  Dashboard          EventBus           AgentTask          AgentResult
  (WS clients)       (listeners)        (via LLM/OpenCode)  (via agent)
```

---

## 8. Datenflüsse

### 8.1 Kompletter Workflow-Datenfluss

```
┌──────────────────────────────────────────────────────────────────┐
│                      DATENFLÜSS DIAGRAM                           │
│                                                                  │
│  User Input                                                     │
│       │                                                          │
│       ▼                                                          │
│  ┌─────────────┐                                                │
│  │ Classify     │── LLMService.classify_request()               │
│  │ Request      │   → {type: new_project/resume/question}      │
│  └──────┬───────┘                                                │
│         │                                                          │
│    ┌────┴────┐                                                    │
│    │new_proj │  ┌────┴─────┐    ┌──────────────────────┐        │
│    └────┬────┘  │ resume   │    │ question            │        │
│         │       └────┬─────┘    └──────┬───────────────┘        │
│         │            │                │                          │
│         ▼            ▼                ▼                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐                  │
│  │ Create   │  │ Resume   │  │ Answer       │                  │
│  │ Project  │  │ Project  │  │ Question     │                  │
│  │ workspace│  │ workspace│  │ (no build)   │                  │
│  └────┬─────┘  └────┬─────┘  └──────┬───────┘                  │
│       │             │               │                           │
│       ▼             ▼               ▼                           │
│  ┌──────────────────────────────────────────┐                   │
│  │        SupervisorAgent.execute()         │                   │
│  │                                          │                   │
│  │  DesignState erstellen/laden             │                   │
│  │  _run_autonomous_loop()                  │                   │
│  └──────────────────────┬───────────────────┘                   │
│                         │                                       │
│          ┌──────────────┼──────────────┐                        │
│          │              │              │                        │
│          ▼              ▼              ▼                        │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐                 │
│  │ ANALYZING  │ │ARCHITECTING│ │IMPLEMENTING│                 │
│  │            │ │            │ │            │                 │
│  │ LLM analyze│ │LLM archi-  │ │LLM code   │                 │
│  │+ RAG search│ │ + RAG      │ │gen+ OpenCode│                │
│  │            │ │            │ │gen+ LLM   │                 │
│  └─────┬──────┘ └─────┬──────┘ └─────┬─────┘                 │
│        │              │              │                          │
│        ▼              ▼              ▼                          │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐                 │
│  │ STATIC_CHECK│ │ SIMULATING │ │DEBUGGING   │                 │
│  │            │ │            │ │            │                 │
│  │ GHDL valid.│ │ GHDL valid.│ │ DebugAgent │                 │
│  │ (placeholder│ │(3-phase)   │ │(Regex+LLM) │                 │
│  │  ⚠️)       │ │            │ │            │                 │
│  └─────┬──────┘ └─────┬──────┘ └─────┬─────┘                 │
│        │              │              │                          │
│        │         FAILED ▼              │                          │
│        │         ┌────────────┐        │                          │
│        │         │ REPAIRING  │◀───────┘                          │
│        │         │            │                                   │
│        │         │ DebugAgent │                                   │
│        │         │ HDLAgent   │                                   │
│        │         │ (OpenCode) │                                   │
│        │         └─────┬──────┘                                   │
│        │             │                                          │
│        │             │ back to IMPLEMENTING                       │
│        │             │ (max 5 repairs)                            │
│        │             │ (max 20 iterations)                        │
│        ▼             ▼                                          │
│  ┌────────────┐ ┌────────────┐                                  │
│  │ SYNTHESIZING│ │FPGA_PROGRAM│                                  │
│  │            │ │  MING      │                                  │
│  │ GHDL synth │ │ Vivado     │                                  │
│  │+ Vivado    │ │ JTAG/QSPI  │                                  │
│  │ bitstream  │ │ (ohne      │                                  │
│  │            │ │ Freigabe)  │                                  │
│  └─────┬──────┘ └─────┬──────┘                                  │
│        │              │                                          │
│        │        FLASHED ▼                                      │
│        │         ┌────────────┐                                  │
│        │         │HARDWARE    │                                  │
│        │         │TESTING     │                                  │
│        │         │            │                                  │
│        │         │Mock/UART   │                                  │
│        │         │Interface   │                                  │
│        │         └─────┬──────┘                                  │
│        │             │                                          │
│        │        PASSED ▼                                       │
│        ▼        ┌────────────┐                                 │
│  ┌──────────┐  │ COMPLETED  │                                 │
│  │  END     │◀─┤ (DONE)     │                                 │
│  └──────────┘  └────────────┘                                 │
│                                                                  │
│  ┌──────────────────────────────────────────┐                   │
│  │    Persistenz (state.json)                │                   │
│  │    • status, task_id, workspace          │                   │
│  │    • design_state.yaml (SupervisorAgent)  │                   │
│  │    • memory.md (ProjectMemoryService)     │                   │
│  └──────────────────────────────────────────┘                   │
└──────────────────────────────────────────────────────────────────┘
```

### 8.2 Agent-Datenfluss Detail

```
┌─────────────────────────────────────────────────────────────┐
│                 Agent-Datenfluss                              │
│                                                             │
│  ArchitectureAgent:                                          │
│    Input:  requirement + analysis + RAG                     │
│    Process: LLM.generate_code() → YAML-Parse               │
│    Output: ArchitectureInfo + ArchitectureHandoff            │
│            + TaskGraph {tasks, dependencies}                │
│                                                             │
│  HDLAgent:                                                   │
│    Input:  ArchitectureInfo + DesignState + Task            │
│    Process:                                               │
│      • implement: LLM.generate_code() → .vhd files         │
│      • fix: OpenCodeContextBuilder → OpenCode.execute()    │
│      • review: statische Prüfung auf wait/styles            │
│    Output: .vhd files + _tb.vhd testbenches                 │
│                                                             │
│  VerificationAgent:                                          │
│    Input:  Workspace + Architecture + Domain                 │
│    Process: GHDLValidator.validate()                        │
│    Output: VerificationResult + failed_case details         │
│                                                             │
│  DebugAgent:                                                 │
│    Input:  diagnostics[] + stage + architecture             │
│    Process:                                                │
│      • LLM: Prompt → JSON diagnosis                        │
│      • Fallback: classify_error() (13 Regex)               │
│      • _extract_modules_from_errors()                      │
│    Output: DebugDiagnosis {status, type, modules, evidence, │
│            action, severity}                                │
│                                                             │
│  FPGAAgent:                                                  │
│    Input:  Workspace + Target + BitstreamService            │
│    Process:                                                │
│      • GHDLSynthesisService.synthesize() (GHDL pre-check)  │
│      • VivadoBitstreamService.build_bitstream()            │
│      • VivadoFlashService / OpenFPGALoaderFlashService     │
│    Output: BitstreamResult + FlashResult                    │
│                                                             │
│  HardwareTestAgent:                                          │
│    Input:  Architecture + FPGAConfig + HardwareInterface    │
│    Process:                                                │
│      • Reset hardware                                     │
│      • Define test suite (uart/cpu/gpio based on arch)    │
│      • Run via HardwareTestInterface                       │
│    Output: HardwareTestInfo {tests[], passed, failed}       │
└─────────────────────────────────────────────────────────────┘
```

---

## 9. Test-Suite

### 9.1 Test-Übersicht

```
┌───────────────────────────────────────────────────────────┐
│                  Test-Suite                                 │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ test_unit.py (446 Zeilen)                           │  │
│  │                                                     │  │
│  │ • State Machine Tests                               │  │
│  │ • EventBus Tests                                    │  │
│  │ • TaskState Tests                                   │  │
│  │ • FileSystem Operations                             │  │
│  │ • ValidationService Tests                           │  │
│  │ • Workflow Tests                                    │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ test_architecture.py (508 Zeilen)                   │  │
│  │                                                     │  │
│  │ • Domain Model Tests                                │  │
│  │ • ContractChecker Tests                             │  │
│  │ • GHDLValidator Tests                               │  │
│  │ • Tool Detection Tests                              │  │
│  │ • Workflow Tests                                    │  │
│  │ • Pre-existing FAILURES: 2 (domain_registry,        │  │
│  │   chat_memory)                                      │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ test_chat.py (213 Zeilen)                           │  │
│  │                                                     │  │
│  │ • SupervisorOrchestrator via make_agent()           │  │
│  │ • Test classify_new_project/classify_resume/         │  │
│  │   classify_question                                 │  │
│  │ • Test chat flows (new_project, resume, question)   │  │
│  │• PRE-EXISTING FAILURE: test_chat_new_project_       │  │
│  │  creates_memory (Architecture YAML Parsing Error)   │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ test_projects.py (80 Zeilen)                        │  │
│  │                                                     │  │
│  │ • 6 Test Cases (EN/DE Counter, Match, Empty)       │  │
│  │• 37/37 tests PASS (mit test_unit.py)               │  │
│  │• PRE-EXISTING FAILURE: test (Architecture YAML)     │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ test_multi_agent_collaboration.py                   │  │
│  │                                                     │  │
│  │ • 12 Multi-Agent Tests                              │  │
│  │ • ContractChecker Integration                       │  │
│  │ • Agent Interaction Tests                           │  │
│  └─────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────┘
```

### 9.2 Akzeptanztests (noch nicht vollständig implementiert)

```
┌───────────────────────────────────────────────────────────┐
│            Akzeptanztests (Implementierungs-Prompt)        │
│                                                           │
│  ✅ Vollständige Factory-/DI                              │
│  ✅ End-to-End Reparatur (fehlerhaftes VHDL → bestanden)  │
│  ⚠️  STATIC_CHECK Gate (ruft Validator nicht auf)        │
│  ❌ Fehlende Assertions / fehlender Abschlussmarker       │
│  ⚠️  Contract-Verletzungen (ContractChecker existiert,    │
│      aber nicht im Pipeline)                              │
│  ⚠️  Fehlerklassifikation (13 Typen + Regex, aber        │
│      kein vollständiger Error-Contract)                   │
│  ❌ No-Progress und max. Reparaturbudget                  │
│  ❌ OpenCode-Sandbox, Ownership, Timeout, Exit-Code       │
│  ❌ TaskGraph mit Invalidation und Resume nach Neustart   │
│  ❌ Vivado-Reportauswertung (alle Werte hardcoded)        │
│  ❌ Klare Trennung Mock/Simulation/Real-Hardware          │
│  ❌ Mehrmoduliges Referenzdesign (8-Bit-CPU, Hamming)    │
└───────────────────────────────────────────────────────────┘
```

---

## 10. Offene Lücken

### 10.1 Priorisierte Lücken (nach Schwere)

```
┌───────────────────────────────────────────────────────────┐
│                    Kritische Lücken                         │
│                                                           │
│  🔴 P0: handle_chat_async fehlt                           │
│      ├── SupervisorOrchestrator hat KEIN                 │
│      │   handle_chat_async()                              │
│      ├── API-Server ruft es an 3× auf                    │
│      └── → AttributeError zur Laufzeit                   │
│                                                           │
│  🔴 P0: STATIC_CHECK ruft Validator nicht auf             │
│      ├── _run_static_check() gibt "checks: passed"       │
│      │   als harten String zurück                        │
│      └── → Falsch-positive Ergebnisse                    │
│                                                           │
│  🔴 P0: Synthese-Report-Parsing fehlt komplett            │
│      ├── _analyze_timing() gibt wns_ns=0.5 HART-CODED   │
│      ├── _check_resources() gibt lut=1250 HART-CODED     │
│      └── → Alle Timing/Ressourcen-Werte sind Fake        │
│                                                           │
│  🟠 P1: Strukturierte Gate-Ergebnisse fehlen             │
│      ├── input_hash, source_revision, artifacts,          │
│      │   diagnostics fehlen auf allen Modellen            │
│      └── → Keine Nachvollziehbarkeit                     │
│                                                           │
│  🟠 P1: ContractChecker nicht im Pipeline                 │
│      ├── Existiert in contract_check.py                  │
│      ├── Prüft nur Port-Namen (keine Breiten/signed)     │
│      └── → Interface-Verletzungen nicht erkannt          │
│                                                           │
│  🟠 P1: TaskGraph wird nie persistiert                    │
│      ├── SupervisorOrchestrator erstellt TaskGraph()     │
│      ├── Aber nie to_dict() aufgerufen                   │
│      └── → Kein Resume möglich                           │
│                                                           │
│  🟡 P1: Hardwaretest meldet FAILED statt SKIPPED/BLOCKED  │
│      ├── _run_hardware_test() gibt FAILED bei keine      │
│      │   Hardware                                        │
│      └── → SKIPPED/BLOCKED erwartet                      │
│                                                           │
│  🟡 P2: OpenCode produziert keinen Maschinenlesbaren     │
│         Plan                                             │
│      ├── OpenCodeContextBuilder gibt TEXT-String         │
│      ├── Kein JSON-Struktur-Plan                         │
│      └── → Kein strukturiertes Plan-Format               │
│                                                           │
│  🟡 P2: Keine atomaren Schreiboperationen (behoben       │
│         2026-10-10)                                       │
│      ├── design_state.yaml: Plain-Write                  │
│      ├── state.json: Plain-Write                         │
│      └── → Datei-Korruption bei Absturz möglich          │
│                                                           │
│  🟡 P3: Kein dedizierter Constructor-/DI-Test             │
│      ├── Kein test_constructor_dependency_injection       │
│      ├── test_chat.py nutzt Factory indirekt             │
│      └── → Kein expliziter DI-Test                       │
│                                                           │
│  🟡 P3: repair_owner und failure_id fehlen                │
│      ├── Error-Contract unvollständig                    │
│      └── → Keine nachvollziehbare Reparatur-Zuordnung    │
└───────────────────────────────────────────────────────────┘
```

### 10.2 Empfohlene Reihenfolge für nächste Iteration

```
1. handle_chat_async implementieren → API-Chat reparieren
2. _run_static_check() korrigieren → Validator aufrufen
3. FPGAAgent._analyze_timing() → Vivado-Report-Parsing
4. FPGAAgent._check_resources() → Vivado-Report-Parsing
5. DesignState um gates-Feld erweitern
6. TaskGraph persistieren (to_dict() im Orchestrator)
7. HardwareTestAgent → SKIPPED/BLOCKED
8. ContractChecker im Pipeline einbinden
9. DebugDiagnosis erweitern (failure_id, root_cause)
10. (entfallen: Benutzerfreigabe am 2026-10-11 entfernt)
```

---

## 11. Projektstruktur

```
Schaltungsagent/
├── src/
│   ├── main.py                          (CLI Entry Point)
│   ├── api_server.py                    (FastAPI + WebSocket)
│   ├── config.py                        (Settings-Dataclasses)
│   ├── config.yaml                      (App-Konfiguration)
│   ├── launcher.py                      (Launcher Script)
│   │
│   ├── agents/                          (Agenten-Klasse)
│   │   ├── __init__.py                  (Exports)
│   │   ├── supervisor.py                (939 Zeilen - Hauptorchestrierer)
│   │   ├── hdl.py                       (527 Zeilen - VHDL-Generierung/Reparatur)
│   │   ├── architecture.py              (441 Zeilen - Architektur-Erstellung)
│   │   ├── verification.py              (249 Zeilen - GHDL-Verification)
│   │   ├── debug.py                     (456 Zeilen - Fehlerklassifikation)
│   │   ├── fpga.py                      (309 Zeilen - Synthesis/Flash)
│   │   └── hardware_test.py             (425 Zeilen - Hardware-Tests)
│   │
│   ├── domain/                          (Domain-Layer)
│   │   ├── models/                      (Pydantic Models)
│   │   │   ├── task_state.py            (TaskState + WorkflowStatus)
│   │   │   ├── design_state.py          (DesignState + 13 Sub-Modelle)
│   │   │   ├── events.py                (EventType + Event)
│   │   │   ├── artifacts.py             (FileArtifact, ArtifactBundle)
│   │   │   └── commands.py              (Commands)
│   │   ├── agents/                      (BaseAgent, AgentTask, TaskGraph)
│   │   │   ├── base.py                  (BaseAgent, AgentTask, AgentResult)
│   │   │   ├── communication.py         (DebugDiagnosis, AgentMessage)
│   │   │   ├── task_graph.py            (TaskGraph + FileOwnershipRegistry)
│   │   │   └── contract_check.py        (ContractChecker)
│   │   ├── ports/                       (Service Interfaces)
│   │   │   ├── llm_service.py           (LLMService ABC)
│   │   │   ├── rag_service.py           (RAGService ABC)
│   │   │   ├── opencode_service.py      (OpenCodeService ABC)
│   │   │   ├── validation_service.py    (ValidationService ABC)
│   │   │   ├── synthesis_service.py     (SynthesisService ABC)
│   │   │   ├── bitstream_service.py     (BitstreamService ABC)
│   │   │   ├── flash_service.py         (FlashService ABC)
│   │   │   ├── filesystem_service.py    (FileSystemService ABC)
│   │   │   ├── artifact_generator.py    (ArtifactGenerator ABC)
│   │   │   ├── planner_service.py       (PlannerService ABC)
│   │   │   ├── tool.py                  (Tool/ToolRegistry ABC)
│   │   │   ├── event_publisher.py       (EventPublisher ABC)
│   │   │   └── __init__.py              (All Exports)
│   │   ├── state_machine.py             (StateMachine + WorkflowState)
│   │   ├── event_bus.py                 (EventBus)
│   │   ├── domain_registry.py           (DomainRegistry)
│   │   └── exceptions.py                (StateMachineError)
│   │
│   ├── services/                        (Business Logic Services)
│   │   ├── opencode_service.py          (Subprocess/Docker OpenCode)
│   │   ├── opencode_context.py          (17-Section Context Builder)
│   │   ├── opencode_worker.py           (WorkerPool + FileOwnership)
│   │   ├── opencode_agent_tool.py       (Agent-Tool-Integration)
│   │   ├── llm_service.py               (StubLLMService + OllamaLLMService)
│   │   ├── rag_service.py               (VHDLRAGService)
│   │   ├── rag_pipeline.py              (RAG Pipeline)
│   │   ├── artifact_generator.py        (VHDLArtifactGenerator)
│   │   ├── eda_tools.py                 (EDA-Tool-Detection)
│   │   ├── flash_service.py             (Flash Service)
│   │   ├── filesystem_service.py        (LocalFileSystemService)
│   │   ├── project_memory.py            (ProjectMemoryService)
│   │   ├── project_namer.py             (make_unique, sanitize)
│   │   └── task_planner_service.py      (Task Planner)
│   │
│   ├── orchestrator/                    (Orchestration)
│   │   ├── __init__.py                  (SupervisorOrchestrator Export)
│   │   ├── agent_factory.py             (build_supervisor_agent())
│   │   ├── supervisor_orchestrator.py   (374 Zeilen - Produktions-Orchestrator)
│   │   └── langgraph_orchestrator.py    (504 Zeilen - Alternative StateGraph)
│   │
│   ├── infrastructure/                  (Infrastructure Layer)
│   │   ├── validation/
│   │   │   └── ghdl_validator.py        (GHDLValidator - 3-Phase)
│   │   ├── synthesis/
│   │   │   ├── vivado_synthesis.py      (VivadoBitstreamService)
│   │   │   ├── vivado_flash.py          (VivadoFlashService)
│   │   │   ├── vivado_artifacts.py      (Artifact Cleanup)
│   │   │   └── ghdl_synthesis.py        (GHDL Synthesis)
│   │   ├── opencode/
│   │   │   ├── opencode_worker.py       (Worker + Pool)
│   │   │   ├── planner_adapter.py       (Planner Adapter)
│   │   │   ├── tool_adapter.py          (Tool Adapter)
│   │   │   └── tool_registry.py         (Tool Registry)
│   │   └── rag/
│   │       ├── vector_store.py          (Qdrant)
│   │       ├── document_loader.py       (Document Loader)
│   │       ├── embedding_provider.py    (Embedding Provider)
│   │       ├── retriever.py             (Retriever)
│   │       └── memory_provider.py       (Memory Provider)
│   │
│   ├── domain_plugins/                  (Domain-Specific Plugins)
│   │   └── vhdl/
│   │       ├── templates.py             (743 Zeilen - VHDL Templates)
│   │       ├── rag_data.py              (RAG Data)
│   │       ├── prompts.py               (Prompts)
│   │       ├── test_definitions.py      (Test Definitions)
│   │       └── build_definitions.py     (Build Definitions)
│   │
│   ├── dashboard/                       (Dashboard Frontend)
│   │   ├── index.html                   (Dashboard HTML)
│   │   ├── style.css                    (Dashboard Styles)
│   │   └── app.js                       (Dashboard Client Logic)
│   │
│   ├── tests/                           (Tests)
│   │   ├── test_unit.py                 (446 Zeilen)
│   │   ├── test_architecture.py         (508 Zeilen)
│   │   ├── test_chat.py                 (213 Zeilen)
│   │   └── test_projects.py             (80 Zeilen)
│   │
│   ├── data/
│   │   └── fpgas.yaml                   (FPGA Registry)
│   │
│   └── config.yaml                      (App Konfiguration)
│
├── evaluation/                          (Experiment Runner)
│   ├── __init__.py
│   └── runner.py                        (Experiment-Runner)
│
├── docs/                                (Dokumentation)
│   ├── FPGA/
│   │   ├── FPGA-IMPLEMENTIERUNG.md      (Lückenanalyse)
│   │   ├── PROJECT-DOKU.md              (Diese Datei)
│   │   ├── vivado-setup.md              (Vivado Setup)
│   │   └── vivado-&-arty-s7-50-setup-dokumentation.html
│   ├── architecture/
│   │   ├── ARCHITECTURE.md              (Architektur-Doku)
│   │   ├── current-system.md            (Aktuelles System)
│   │   ├── multi-agent-system.md        (Multi-Agenten-Doku)
│   │   └── Architekturüberblick.drawio.png
│   ├── fpgagent-implementation-prompt.md
│   ├── fpga-workflow.md
│   ├── IMPROVEMENTS.md
│   ├── multi-agent-goal-assessment.md
│   └── prompt.txt
│
├── projects/                            (55+ Projekte)
├── memory/qdrant/                       (Qdrant Vector DB)
└── venv.sh                              (Virtual Environment Setup)
```

---

## Zusammenfassung der Test-Suite

| Datei | Tests | Status |
|-------|-------|--------|
| test_unit.py | ~20 Tests | ✅ Bestehen |
| test_architecture.py | ~15 Tests | ✅ 13 bestehen, 2 Pre-existing FAIL |
| test_chat.py | ~5 Tests | ⚠️ 3 bestehen, 1 Pre-existing FAIL |
| test_projects.py | ~6 Tests | ⚠️ 5 bestehen, 1 Pre-existing FAIL |
| test_multi_agent_collaboration.py | 12 Tests | ✅ Bestehen |
| **Gesamt** | **37+ Tests** | **37 bestehen (ohne Pre-existing)** |

---

> **Hinweis**: Diese Dokumentation basiert auf einer systematischen Analyse des gesamten `src/`-Baums (88 Python-Dateien, ~17.300 Zeilen Code) sowie 5 parallelen Code-Untersuchungen durch spezialisierte Agenten. Alle Erkenntnisse wurden durch direkten Datei-Lesen und Testausführung verifiziert.
