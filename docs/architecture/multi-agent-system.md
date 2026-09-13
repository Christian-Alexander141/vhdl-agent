# Zielarchitektur: Multi-Agent-System für Digitale Hardwareentwicklung

## Übersicht

Erweiterung des bestehenden Systems zu einem **autonomen Multi-Agenten-System** mit:
- Zentralem Supervisor/Orchestrator
- 6 spezialisierten Agenten
- Persistentem gemeinsamen Design State
- Autonomen Feedback-Loops mit Safety-Limits
- Echter Hardware-Test-Integration

## Architektur-Diagramm

```
                         USER
                           |
                           v
                 +-------------------+
                 | SUPERVISOR AGENT  |
                 | (Orchestrator)    |
                 +---------+---------+
                           |
          +----------------+----------------+
          |                |                |
          v                v                v
   Architecture      HDL Agent        Verification
     Agent                                 Agent
          |                |                |
          +----------------+----------------+
                           |
                           v
                      Debug Agent
                           |
                           v
                    VHDL PROJECT
                           |
          +----------------+----------------+
          |                                |
          v                                v
       GHDL                              Vivado
          |                                |
          |                                v
          |                           BITSTREAM
          |                                |
          +----------------+----------------+
                           |
                           v
                      FPGA Agent
                           |
                           v
                         FPGA
                           |
                    UART / GPIO / JTAG
                           |
                           v
                 Hardware Test Agent
                           |
                 +---------+---------+
                 |                   |
                PASS                FAIL
                 |                   |
                 v                   v
              COMPLETE           Debug Loop
```

## Agenten-Rollen

### 1. SupervisorAgent (Zentrale Steuerung)
**Datei**: `src/agents/supervisor.py`

Verantwortlichkeiten:
- Anforderungen analysieren und zerlegen
- Agenten auswählen und koordinieren
- Design State verwalten und persistieren
- Zustandsübergänge steuern (State Machine)
- Feedback-Loops managen (Simulation → Debug → Repair → ...)
- Safety-Limits durchsetzen (max_iterations, max_repairs, etc.)
- Human-Intervention bei Limits/Fehlern anfordern

### 2. ArchitectureAgent (Hardware-Architektur)
**Datei**: `src/agents/architecture.py`

Verantwortlichkeiten:
- Aus Anforderungen strukturierte Modul-Architektur erstellen
- Interfaces, Signale, Clock/Reset-Konzept definieren
- Abhängigkeiten zwischen Modulen identifizieren
- Architektur als YAML speichern (maschinenlesbar)

Output:
```yaml
modules:
  - name: alu
    type: combinational
    inputs: [a, b, operation]
    outputs: [result, flags]
    parameters: {width: 8}
    dependencies: []
  - name: register_file
    type: sequential
    inputs: [clk, rst, read_addr_a, ...]
    outputs: [data_a, data_b]
    parameters: {width: 8, depth: 16}
    dependencies: []
interfaces:
  alu_to_regfile: "result -> write_data"
clock_domain: "clk"
reset_concept: "async_active_high"
decisions:
  - decision: "Single clock domain"
```

### 3. HDLAgent (VHDL-Implementierung)
**Datei**: `src/agents/hdl.py`

Verantwortlichkeiten:
- VHDL-Entities/Architectures pro Modul generieren
- Interfaces gemäß Architektur einhalten
- Synthesizable VHDL erzeugen (keine wait, after, file I/O)
- Testbenches generieren
- Coding Guidelines prüfen (Linting)
- Bei Architektur-Problemen: strukturiertes Error-Objekt an Supervisor

```json
{
  "status": "blocked",
  "reason": "missing_interface",
  "module": "register_file",
  "description": "Control unit requires read port not defined in architecture"
}
```

### 4. VerificationAgent (Verifikation)
**Datei**: `src/agents/verification.py`

Verantwortlichkeiten:
- Testplan aus Architektur/Requirements ableiten
- Testbenches generieren/validieren
- GHDL Simulation ausführen (Analyse, Elaboration, Run)
- Testergebnisse interpretieren (PASS/FAIL mit Details)
- Coverage analysieren

Output (VerificationResult):
```json
{
  "status": "failed",
  "tests_total": 20,
  "tests_passed": 17,
  "tests_failed": 3,
  "failures": [
    {"test": "alu_add_overflow", "expected": "0x00", "actual": "0x01"}
  ],
  "coverage": 85.0
}
```

### 5. DebugAgent (Fehleranalyse)
**Datei**: `src/agents/debug.py`

Verantwortlichkeiten:
- Fehler aus allen Stages analysieren (GHDL, Vivado, Flash, Hardware)
- Strukturierte Diagnose erstellen
- Verdächtige Module identifizieren
- Konkrete Reparatur-Empfehlung ausgeben

Output (DebugDiagnosis):
```json
{
  "status": "failed",
  "stage": "simulation",
  "suspected_modules": ["alu", "control_unit"],
  "failure_type": "incorrect_result",
  "evidence": ["ADD instruction produced 0x11 instead of 0x0F"],
  "recommended_action": "Inspect ALU carry handling",
  "severity": "high"
}
```

### 6. FPGAAgent (FPGA-Bereitstellung)
**Datei**: `src/agents/fpga.py`

Verantwortlichkeiten:
- GHDL Synthese-Prüfung (Stufe 1)
- Vivado Bitstream-Erzeugung (Stufe 2, Non-Project-Mode)
- Timing-Analyse (WNS, TNS, Fmax)
- Resource Utilization (LUT, FF, BRAM, DSP)
- FPGA Flash (Vivado JTAG / openFPGALoader)
- Board-Erkennung und -Matching

### 7. HardwareTestAgent (Echter Hardware-Test)
**Datei**: `src/agents/hardware_test.py`

Verantwortlichkeiten:
- Abstrakte `HardwareTestInterface` definieren
- Mock-Implementierung für Tests
- UART-Implementierung für echte Hardware
- Test-Suiten definieren und ausführen
- Hardware-Test-Ergebnisse strukturiert zurückgeben

Interface:
```python
class HardwareTestInterface:
    async def reset(self) -> bool
    async def send_command(self, command: bytes) -> bool
    async def send_program(self, program: bytes) -> bool
    async def start(self) -> bool
    async def read_output(self, length: int = 1024, timeout: float = 5.0) -> bytes
    async def run_test(self, test: dict) -> dict
    async def close(self) -> None
```

## Gemeinsamer Design State

**Datei**: `src/domain/models/design_state.py`

Persistenter, versionierter Projektzustand (YAML/JSON):

```yaml
project:
  id: "uuid"
  name: "8bit_cpu"
  version: 3
  created_at: "2026-01-15T10:00:00Z"
  updated_at: "2026-01-15T10:30:00Z"

requirements:
  - id: "req-1"
    description: "8-bit ALU with add/sub"
    status: "SATISFIED"
    satisfied_by: ["alu"]
    verified: true

architecture:
  status: "completed"
  version: 2
  modules:
    - name: "alu"
      type: "combinational"
      inputs: [a, b, op]
      outputs: [result, flags]
      status: "implemented"
      files: ["src/alu.vhd"]

implementation:
  status: "completed"
  files: ["src/alu.vhd", "src/regfile.vhd", ...]
  generated_files: [...]
  last_modified: "..."

verification:
  status: "passed"
  tests: [...]
  passed: 15
  failed: 0
  coverage: 92.0

synthesis:
  status: "passed"
  timing: {wns_ns: 0.5, fmax_mhz: 125.0}
  resources: {lut: 1250, ff: 2100, lut_pct: 15.2}
  bitstream_path: "build/cpu.bit"

fpga:
  target: "arty_s7_50"
  programmed: true
  bitstream: "build/cpu.bit"
  board_detected: true

hardware:
  status: "passed"
  tests: [...]
  passed: 5
  failed: 0

diagnostics:
  active: []
  history: [...]

iterations:
  total: 8
  by_stage: {architecting: 1, implementing: 2, simulating: 3}
  repairs: 3

human_interventions:
  count: 0
  reasons: []

current_stage: "HARDWARE_TESTING"
```

## Erweiterte State Machine

Neue Zustände (Zusätzlich zu bestehenden 15):
- `ARCHITECTING` - Architektur-Entwurf
- `IMPLEMENTING` - HDL-Implementierung
- `STATIC_CHECK` - Linting/Syntax-Check
- `SIMULATING` - GHDL Simulation
- `VALIDATING` - Post-Simulation Validierung
- `DEBUGGING` - Fehleranalyse & Repair-Planung
- `FPGA_PROGRAMMING` - Synthese + Flash
- `HARDWARE_TESTING` - Echter Hardware-Test
- `AUTONOMOUS_LIMIT_REACHED` - Safety-Limit überschritten

Wichtige Übergänge:
```
SIMULATION FAIL     → DEBUGGING → IMPLEMENTING
SYNTHESIS FAIL      → DEBUGGING → IMPLEMENTING
HARDWARE TEST FAIL  → DEBUGGING → IMPLEMENTING (oder FPGA_PROGRAMMING)
ARCHITECTURE ISSUE  → DEBUGGING → ARCHITECTING
```

## Agent Communication Protocol

**Datei**: `src/domain/agents/communication.py`

Strukturierte Kommunikation via `AgentTask` / `AgentResult`:

```python
@dataclass
class AgentTask:
    id: str
    type: str                    # "create_architecture", "implement_hdl", "verify", ...
    project_id: str
    inputs: dict                 # Domänenspezifische Eingaben
    constraints: dict            # Constraints (Timing, Area, etc.)
    context: dict                # Shared context (Architecture, DesignState, etc.)

@dataclass
class AgentResult:
    task_id: str
    status: AgentStatus          # PENDING, RUNNING, COMPLETED, FAILED, BLOCKED
    outputs: dict                # Domänenspezifische Ausgaben
    diagnostics: list[dict]      # Strukturierte Diagnosen
    next_actions: list[str]      # Empfohlene nächste Aktionen
    error_message: str
```

## EventBus Erweiterungen

Neue Event-Typen:
- `ARCHITECTURE_CREATED`, `ARCHITECTURE_FAILED`
- `IMPLEMENTATION_STARTED`, `IMPLEMENTATION_COMPLETED`, `IMPLEMENTATION_FAILED`
- `STATIC_CHECK_STARTED`, `STATIC_CHECK_PASSED`, `STATIC_CHECK_FAILED`
- `SIMULATION_STARTED`, `SIMULATION_PASSED`, `SIMULATION_FAILED`
- `DEBUG_STARTED`, `DEBUG_COMPLETED`, `REPAIR_ASSIGNED`
- `HARDWARE_TEST_STARTED`, `HARDWARE_TEST_PASSED`, `HARDWARE_TEST_FAILED`
- `AUTONOMOUS_LIMIT_REACHED`, `HUMAN_INTERVENTION_REQUESTED`

## Autonomer Entwicklungsloop

```python
while iteration < max_iterations:
    stage = design_state.current_stage
    result = await execute_stage(stage)
    
    if result.status == FAILED:
        diagnosis = await debug_agent.diagnose(result.diagnostics)
        repair_target = determine_repair_target(diagnosis)
        design_state.transition_to(repair_target)
        continue
    
    elif result.status == COMPLETED:
        next_stage = determine_next_stage(stage)
        if next_stage == COMPLETED:
            return SUCCESS
        design_state.transition_to(next_stage)
        continue
    
    elif result.status == BLOCKED:
        await request_human_intervention()
        continue

# Limit erreicht
design_state.transition_to(AUTONOMOUS_LIMIT_REACHED)
request_human_intervention("Max iterations reached")
```

## Safety Limits (Konfigurierbar)

```yaml
limits:
  max_iterations: 20
  max_repairs_per_stage: 5
  max_simulation_failures: 10
  max_hardware_failures: 5
```

Bei Überschreitung: `AUTONOMOUS_LIMIT_REACHED` State + Human Intervention Request

## Observability

Jede Agenten-Aktion loggt strukturiert:
```json
{
  "timestamp": "2026-01-15T10:30:00Z",
  "project_id": "uuid",
  "agent": "DebugAgent",
  "task_id": "task-123",
  "state": "DEBUGGING",
  "iteration": 4,
  "reason": "Hardware test failed on ADD instruction",
  "suspected_modules": ["alu"],
  "action": "request_hdl_repair",
  "diagnosis": {...}
}
```

## Integration mit Bestandssystem

| Bestehende Komponente | Verwendung im Multi-Agent |
|----------------------|--------------------------|
| GHDLValidator | VerificationAgent nutzt direkt |
| VivadoBitstreamService | FPGAAgent nutzt direkt |
| VivadoFlashService | FPGAAgent nutzt direkt |
| VHDLRAGService | Alle Agenten nutzen agentenspezifisch |
| ProjectMemoryService | SupervisorAgent verwaltet |
| EventBus | Unverändert, neue Events |
| FileSystemService | Unverändert |
| StateMachine | Erweitert, abwärtskompatibel |
| Domain Plugin System | Unverändert |
| API Endpunkte | Unverändert (neue /agent Endpunkte möglich) |

## 8-Bit-CPU Vorbereitung

Framework generisch für Hierarchien:
```
LED Controller → Counter → ALU → UART → Register File → 8-Bit CPU

CPU Module:
- ALU (combinational)
- Register File (sequential)
- Program Counter (sequential)
- Instruction Register (sequential)
- Instruction Decoder (combinational)
- Control Unit (FSM)
- Flags (sequential)
- Memory (sequential)
- UART (sequential)
```

## Tests

```
tests/
├── agents/
│   ├── test_supervisor.py
│   ├── test_architecture_agent.py
│   ├── test_hdl_agent.py
│   ├── test_verification_agent.py
│   ├── test_debug_agent.py
│   ├── test_fpga_agent.py
│   └── test_hardware_test_agent.py
├── workflow/
├── state/
├── hardware/
└── integration/
```

## Akzeptanzkriterien

1. ✅ Natürliche Sprachbeschreibung → Projektstart
2. ✅ Supervisor zerlegt in strukturierte Tasks
3. ✅ ArchitectureAgent & HDLAgent arbeiten getrennt
4. ✅ VerificationAgent erzeugt/pflegt Tests
5. ✅ GHDL automatisch ausgeführt
6. ✅ Simulationsfehler → Debug/Repair Loop
7. ✅ Nach Simulation → Automatisch Vivado
8. ✅ Nach Synthese → Automatisch Bitstream
9. ✅ FPGA automatisch programmiert
10. ✅ Nach Flash → Automatisch Hardware-Test
11. ✅ Hardware-Fehler → Zurück zu Debug/Implementation
12. ✅ Mehrere autonome Iterationen
13. ✅ Limits verhindern Endlosschleifen
14. ✅ Alle Entscheidungen nachvollziehbar geloggt
15. ✅ Bestehende Funktionalität erhalten