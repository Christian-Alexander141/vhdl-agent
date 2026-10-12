# UML-Modell des VHDL-Multiagentensystems

Stand: 2026-10-12 (Branch `mas-verbesserungen-2026-10-11`, Commit `63a4752`). Die Diagramme sind
aus dem Code unter `Schaltungsagent/src/` abgeleitet; Methoden sind auf die öffentliche
Schnittstelle und die für den Ablauf wichtigen internen Schritte beschränkt. Ablauf und
Fehlerbehandlung: [MAS-Ablauf.md](MAS-Ablauf.md).

Das Modell ist in vier Sichten aufgeteilt, weil ein einzelnes Diagramm mit über 60 Klassen
nicht lesbar wäre:

1. Paketübersicht (Schichten und Abhängigkeiten)
2. Agenten und Orchestrierung
3. Dienste, Ports und Adapter
4. Domänenmodell (Projektzustand)

## 1. Paketübersicht

```mermaid
flowchart TB
    subgraph UI["Präsentation"]
        Dashboard["dashboard/ (index.html, app.js)"]
        API["api_server.py (FastAPI, WebSocket)"]
    end
    subgraph ORCH["orchestrator/"]
        Orchestrator["SupervisorOrchestrator"]
        Factory["agent_factory.build_supervisor_agent()"]
    end
    subgraph AG["agents/"]
        Agents["SupervisorAgent, ArchitectureAgent, HDLAgent,<br/>VerificationAgent, DebugAgent, FPGAAgent, HardwareTestAgent"]
    end
    subgraph DOM["domain/"]
        DomAgents["domain/agents: BaseAgent, TaskGraph, ContractChecker,<br/>triage, repair_routing, requirements,<br/>reference_model, mutation, test_plan"]
        Models["domain/models: DesignState, Events"]
        Ports["domain/ports: OpenCodeService, FileSystemService,<br/>ValidationService, SynthesisService,<br/>BitstreamService, FlashService, EventPublisher"]
        Bus["domain/event_bus: EventBus"]
    end
    subgraph SRV["services/"]
        Services["PlanService, OpenCodeTaskRunner, PromptStore,<br/>Subprocess-/Docker-/ReconfigurableOpenCodeService,<br/>LocalFileSystemService, KnowledgeProvisioner,<br/>NameResolver, OpenCodeProjectChat, ChatRouter"]
    end
    subgraph INF["infrastructure/"]
        Infra["GHDLValidator, GHDLSynthesisService,<br/>VivadoBitstreamService, VivadoFlashService"]
    end
    subgraph EXT["Externe Werkzeuge"]
        OpenCode["OpenCode CLI (Sprachmodelle)"]
        GHDL["GHDL"]
        Vivado["Vivado"]
        Board["Arty S7-50 (JTAG)"]
    end

    Dashboard <--> API
    API --> Orchestrator
    Orchestrator --> Factory --> Agents
    Agents --> DomAgents
    Agents --> Models
    Agents --> Ports
    Services -.implementiert.-> Ports
    Infra -.implementiert.-> Ports
    Agents --> Services
    Agents --> Bus
    Bus --> API
    Services --> OpenCode
    Infra --> GHDL
    Infra --> Vivado
    Infra --> Board
```

## 2. Agenten und Orchestrierung

```mermaid
classDiagram
    direction LR

    class SupervisorOrchestrator {
        -PlanService _plan_service
        -KnowledgeProvisioner _knowledge_provisioner
        -SupervisorAgent _supervisor
        +handle_chat_async(request, current_project, callback) dict
        +execute(request, domain, task_id, extra_inputs) dict
        +execute_async(request, domain, callback) str
        +resume_project(project_id) str
        +get_task_status(task_id) dict
        +list_tasks() list
        -_bootstrap_new_project(request_full, domain) tuple
    }

    class BaseAgent {
        <<abstract>>
        +agent_name str
        +supported_task_types list
        +execute(task AgentTask)* AgentResult
        +emit_event(event_type, payload)
    }

    class AgentTask {
        +id str
        +type str
        +project_id str
        +inputs dict
        +depends_on list
        +acceptance_criteria list
        +expected_artifacts list
    }

    class AgentResult {
        +task_id str
        +status AgentStatus
        +outputs dict
        +diagnostics list
        +error_message str
        +next_actions list
    }

    class AgentStatus {
        <<enumeration>>
        COMPLETED
        FAILED
        BLOCKED
        SKIPPED
        RUNNING
    }

    class SupervisorAgent {
        -DesignState _design_state
        -bool _persistent
        -dict _repair_snapshot
        -callable _model_switcher
        +execute(task) AgentResult
        -_run_autonomous_loop() AgentResult
        -_execute_stage(stage) AgentResult
        -_run_analysis()
        -_run_architecture()
        -_run_implementation()
        -_schedule_priority(graph) dict
        -_run_static_check()
        -_run_simulation()
        -_run_validation()
        -_requirement_gaps() dict
        -_requirements_review() list
        -_mutation_gate() dict
        -_run_synthesis()
        -_run_fpga_programming()
        -_run_hardware_test()
        -_handle_failure(stage, result) AgentResult
        -_escalate(failure_type, diagnosis, target) tuple
        -_dispatch_repair(action, target, failure_type, diagnosis) AgentResult
        -_read_repair_verdict() dict
        -_handle_model_dispute(verdict, diagnosis) AgentResult
        -_rollback_regression(stage) bool
        -_safe_transition_to(stage)
    }

    class ArchitectureAgent {
        -PlanService _plan
        +execute(task) AgentResult
        create_architecture()
        refine_architecture()
        validate_architecture()
    }

    class HDLAgent {
        -OpenCodeTaskRunner _task_runner
        -OpenCodeService _opencode
        +execute(task) AgentResult
        implement_module()
        implement_top()
        implement_project()
        fix_hdl()
        modify_hdl()
        review_hdl()
    }

    class VerificationAgent {
        -GHDLValidator _validator
        -OpenCodeTaskRunner _task_runner
        +execute(task) AgentResult
        verify()
        generate_testbench()
        reference_model()
        review_requirements()
        analyze_coverage()
    }

    class DebugAgent {
        +execute(task) AgentResult
        diagnose()
        -_fallback_diagnosis(diagnostics, stage, architecture) DebugDiagnosis
    }

    class FPGAAgent {
        -VivadoBitstreamService _bitstream_service
        -VivadoFlashService _vivado_flash
        -OpenFPGALoaderFlashService _openfpgaloader_flash
        +execute(task) AgentResult
        synthesize()
        flash()
        +evaluate_gates(timing, resources)$ list
    }

    class HardwareTestAgent {
        -HardwareTestInterface _interface
        +has_real_hardware bool
        +execute(task) AgentResult
        hardware_test()
    }

    class HardwareTestInterface {
        <<abstract>>
        +reset() bool
        +send_program(program) bool
        +send_command(command) bool
        +read_output(length, timeout) bytes
        +run_test(test) dict
        +close()
    }
    class MockHardwareTestInterface
    class UARTHardwareTestInterface

    class DebugDiagnosis {
        +failure_type str
        +origin str
        +suspected_modules list
        +evidence list
        +recommended_action str
        +severity str
    }

    class RepairTarget {
        <<enumeration>>
        ARCHITECTURE
        HDL
        VERIFICATION
        FPGA
        HUMAN
    }

    class TaskGraph {
        +add_task(task, owned_files)
        +get_dependencies(task_id) list
        +get_dependents(task_id) list
        +update_task_status(task_id, status)
        +to_dict() dict
    }

    class ContractChecker {
        +check(architecture, workspace) ContractCheckResult
    }

    SupervisorOrchestrator --> SupervisorAgent : baut über build_supervisor_agent()
    SupervisorOrchestrator --> PlanService : Bootstrap-Planung
    BaseAgent <|-- SupervisorAgent
    BaseAgent <|-- ArchitectureAgent
    BaseAgent <|-- HDLAgent
    BaseAgent <|-- VerificationAgent
    BaseAgent <|-- DebugAgent
    BaseAgent <|-- FPGAAgent
    BaseAgent <|-- HardwareTestAgent
    SupervisorAgent o-- ArchitectureAgent
    SupervisorAgent o-- HDLAgent
    SupervisorAgent o-- VerificationAgent
    SupervisorAgent o-- DebugAgent
    SupervisorAgent o-- FPGAAgent
    SupervisorAgent o-- HardwareTestAgent
    SupervisorAgent --> TaskGraph : Implementierung
    SupervisorAgent --> ContractChecker : Port-Contracts
    SupervisorAgent --> RepairTarget : route_repair()
    SupervisorAgent ..> AgentTask : erzeugt
    BaseAgent ..> AgentResult : liefert
    AgentResult --> AgentStatus
    DebugAgent ..> DebugDiagnosis : Vorfilter triage()
    HardwareTestAgent --> HardwareTestInterface
    HardwareTestInterface <|-- MockHardwareTestInterface
    HardwareTestInterface <|-- UARTHardwareTestInterface
    ArchitectureAgent --> PlanService
```

Fachliche Hilfsmodule des Supervisors (Funktionen, keine Klassen), alle unter `domain/agents/`:

| Modul | Aufgabe | Wichtige Funktionen |
|---|---|---|
| `triage.py` | Vorfilter aller Fehler: Kernzeilen, Herkunft, belegbare Module | `triage`, `key_lines`, `compact`, `classify_flash_output` |
| `repair_routing.py` | Fehlerklasse → zuständige Rolle | `route_repair` |
| `requirements.py` | Einzelanforderungen, `REQ`-Gate, Abschlussprüfung | `check_requirements`, `uncovered_simulation_requirements`, `parse_review`, `task_instruction_suffix` |
| `reference_model.py` | Differentieller Test gegen Python-Modell, Generic-Vertrag | `write_model_testbench`, `resolve_generics`, `mismatch_line` |
| `mutation.py` | Mutationsanalyse der Testbenches | `generate_mutants`, `run_mutation_analysis` |
| `test_plan.py` | Abdeckung je Modul und Anforderung | `build_test_plan` |
| `worker_instructions.py` | Gemeinsame Auftragsbausteine | `ghdl_selfcheck`, `source_compile_order`, `TESTBENCH_RULES` |

## 3. Dienste, Ports und Adapter

```mermaid
classDiagram
    direction LR

    class OpenCodeService {
        <<interface>>
        +execute(project_path, instruction, timeout_seconds, stop_when) OpenCodeResult
    }
    class SubprocessOpenCodeService {
        +execute(...) OpenCodeResult
        +list_models(provider) list
    }
    class DockerOpenCodeService {
        +execute(...) OpenCodeResult
        +build_command(project_path, instruction) list
    }
    class ReconfigurableOpenCodeService {
        +execute(...) OpenCodeResult
        +reconfigure(settings)
    }
    class OpenCodeResult {
        +returncode int
        +stdout str
        +stderr str
    }

    class OpenCodeTaskRunner {
        -PromptStore _prompts
        +run(workspace, request_full, stage, task_instruction, expected_files, stop_when) OpenCodeDelivery
    }
    class OpenCodeDelivery {
        +ok bool
        +files dict
        +reason str
        +changed_files list
        +error(subject) Exception
    }
    class PromptStore {
        +save(workspace, request_full) str
        +verify(workspace) str
    }

    class PlanService {
        +plan(workspace, request_full, task_id, change_request) dict
        -_correction(problems) str
        -_autofix(manifest)
    }
    class PlanValidator {
        +validate(manifest)$ list
        +find_cycle(modules)$ list
    }

    class FileSystemService {
        <<interface>>
        +read_file(path) str
        +write_file(path, content) str
        +workspace_path(project_id) str
    }
    class LocalFileSystemService

    class ValidationService {
        <<interface>>
        +validate(workspace, domain) ValidationResult
    }
    class GHDLValidator

    class SynthesisService {
        <<interface>>
        +synthesize(workspace, target, domain, top_entity) SynthesisResult
    }
    class GHDLSynthesisService

    class BitstreamService {
        <<interface>>
        +build_bitstream(workspace, target, domain, top_entity) BitstreamResult
    }
    class VivadoBitstreamService {
        -_generate_tcl_script(...) str
        -_generatexdc_for_board(top_entity, src_files, board_name, clock_hz) str
        -_hierarchy_roots(src_dir, entities)$ list
    }

    class FlashService {
        <<interface>>
        +flash(bitstream_path, board, expected_part, workspace) FlashResult
        +toolchain_available() bool
    }
    class VivadoFlashService {
        +detect_boards(expected_part) list
    }
    class OpenFPGALoaderFlashService

    class EventPublisher {
        <<interface>>
        +publish_event(event_type, task_id, payload)
    }
    class EventBus {
        +on_event(listener)
        +get_events(since_index) list
    }

    class KnowledgeProvisioner {
        +provision(workspace, board_id) KnowledgeReceipt
    }
    class NameResolver {
        +resolve(request_full, plan_names) NameSet
    }
    class OpenCodeProjectChat {
        +answer_question(question, context) str
    }
    class ChatRouter {
        +route(request, current_project, has_attachments) ChatRoute
    }

    OpenCodeService <|.. SubprocessOpenCodeService
    OpenCodeService <|.. DockerOpenCodeService
    OpenCodeService <|.. ReconfigurableOpenCodeService
    ReconfigurableOpenCodeService o-- OpenCodeService : delegiert
    OpenCodeService ..> OpenCodeResult
    OpenCodeTaskRunner --> OpenCodeService
    OpenCodeTaskRunner --> PromptStore
    OpenCodeTaskRunner ..> OpenCodeDelivery
    OpenCodeTaskRunner --> EventPublisher : OPENCODE_CALL
    PlanService --> OpenCodeTaskRunner
    PlanService --> PlanValidator
    PlanService --> NameResolver
    FileSystemService <|.. LocalFileSystemService
    ValidationService <|.. GHDLValidator
    SynthesisService <|.. GHDLSynthesisService
    BitstreamService <|.. VivadoBitstreamService
    FlashService <|.. VivadoFlashService
    FlashService <|.. OpenFPGALoaderFlashService
    EventPublisher <|.. EventBus
    OpenCodeProjectChat --> OpenCodeService
```

Hilfsfunktionen ohne eigene Klasse: `ensure_native_guard` und `isolate_workspace_repo`
(Sperre und eigenes Git-Repo je Workspace, `opencode_service.py`), `atomic_write_text`
(`opencode_task_runner.py`), `synthesis_digest` und Synthese-Cache (`agents/fpga.py`),
`yaml_io` (schnelles YAML für den Projektzustand).

## 4. Domänenmodell (Projektzustand `design_state.yaml`)

```mermaid
classDiagram
    direction TB

    class DesignState {
        +project dict
        +current_stage DesignStage
        +metadata dict
        +iterations dict
        +transition_to(stage)
        +to_yaml() str
        +from_yaml(text)$ DesignState
    }
    class DesignStage {
        <<enumeration>>
        ANALYZING
        ARCHITECTING
        UART_INTEGRATION
        IMPLEMENTING
        STATIC_CHECK
        SIMULATING
        VALIDATING
        DEBUGGING
        SYNTHESIZING
        FPGA_PROGRAMMING
        HARDWARE_TESTING
        COMPLETED
        FAILED
        INFRASTRUCTURE_FAILURE
        AUTONOMOUS_LIMIT_REACHED
    }
    class Requirement {
        +id str
        +description str
        +quote str
        +satisfied_by list
        +ports list
        +check str
        +status RequirementStatus
        +review str
        +verified bool
    }
    class ArchitectureInfo {
        +version int
        +top_module str
        +reset_concept str
        +clock_domain str
        +hardware_tests list
    }
    class ModuleInfo {
        +name str
        +type str
        +ports dict
        +parameters dict
        +dependencies list
        +files list
    }
    class ImplementationInfo
    class VerificationInfo {
        +status str
        +coverage float
        +test_plan dict
        +contract_check dict
    }
    class SynthesisInfo {
        +status str
        +bitstream_path str
        +timing dict
        +resources dict
    }
    class FPGAInfo {
        +target str
        +programmed bool
        +board_detected bool
        +programmer str
    }
    class HardwareTestInfo {
        +status str
        +test_mode str
    }
    class DiagnosticInfo {
        +active list
        +history list
    }
    class HumanIntervention {
        +count int
        +reasons list
    }

    DesignState --> DesignStage
    DesignState *-- "0..*" Requirement
    DesignState *-- ArchitectureInfo
    ArchitectureInfo *-- "1..*" ModuleInfo
    DesignState *-- ImplementationInfo
    DesignState *-- VerificationInfo
    DesignState *-- SynthesisInfo
    DesignState *-- FPGAInfo
    DesignState *-- HardwareTestInfo
    DesignState *-- DiagnosticInfo
    DesignState *-- HumanIntervention
```

Wichtige Einträge in `DesignState.metadata`: `plan_manifest`, `request_full`, `reference_model`,
`model_testbench` (mit `generics`), `mutation`, `requirements_review`, `escalation` und
`escalation_log` (Versuche je Fehlerklasse und Modul mit Ergebnis), `repair_verdicts`,
`rollbacks`, `agent_notes`, `open_questions`, `task_graph` (nur Übersicht; der Graph steht in
`task_graph.json`).

Dateien im Projekt-Workspace (`projects/<name>/`): `PROMPT.md`, `design_state.yaml`,
`task_graph.json`, `plan/manifest.json`, `plan/requirements.md`, `src/*.vhd`, `tests/*_tb.vhd`
(davon `tests/<top>_model_tb.vhd` automatisch erzeugt), `model/reference_model.py`,
`constraints/*.xdc`, `reports/` (`repair_verdict.json`, `repair_notes.md`, `review.md`,
`requirements_review.json`), `build/` (GHDL, Synthese, Bitstream, Synthese-Cache), eigenes `.git`.
