# Bekannte Grenzen von Schaltungsagent

> Grundlage für die Diskussionskapitel der Bachelorarbeit.
> Aktualisiert am 2026-10-07 nach Umsetzung der Kernlücken aus
> `multi-agent-goal-assessment.md`.

## Stand 2026-10-07: weiterhin offene Grenzen

Die Befunde 2–12 aus `multi-agent-goal-assessment.md` sind im Produktionspfad
umgesetzt (siehe dort). Offen bleiben:

### 1. Kein End-to-End-Akzeptanztest auf echter Hardware
Es gibt noch keinen reproduzierbaren Lauf, der eine 8-Bit-CPU oder einen
Decoder von der Anforderung über OpenCode, Vivado und Flash bis zu einer über
UART beobachteten Board-Antwort durchläuft. Alle neuen Gates sind mit
Stub-Agenten, echtem GHDL und nachgebildeten Vivado-Reports getestet
(`Schaltungsagent/tests/test_multi_agent_gates.py`).

### 2. Abdeckung ist strukturell, nicht funktional
Das Coverage-Gate prüft, ob jedes Modul von einer simulierten Testbench über
die Instanziierungshierarchie erreicht wird. Ob die Assertions das Verhalten
vollständig prüfen (Code-/Funktions-Coverage), wird nicht gemessen.

### 3. Contracts ohne Protokollsemantik
Der `ContractChecker` prüft Existenz, Richtung, Basistyp und Bitbreite von
Ports (auch mit Generics), Clock-Port sequentieller Module und das Top-Level.
Latenz, Handshake, Durchsatz, Reset-Polarität und Clock-Domain-Übergänge sind
nicht maschinenprüfbar. Typisierte Ports liefert der Planer nur, wenn OpenCode
das erweiterte Manifest-Schema (`ports`) befüllt.

### 4. Hardwaretests brauchen Konfiguration und Testvektoren
Ohne `hardware_test.uart_port` wird kein Hardwaretest ausgeführt; der Workflow
endet dann mit dem ausdrücklichen Hinweis, dass die Board-Funktion nicht
validiert ist. CPU-/Decoder-Vektoren müssen im Manifest (`hardware_tests`)
oder in `tests/hardware_tests.yaml` stehen. GPIO-Beobachtung gibt es nicht.

### 5. Constraint-, Ressourcen- und Board-Fehler werden nicht automatisch repariert
Sie werden erkannt, blockieren den Abschluss und gehen an den Benutzer.
Eine automatische Constraint-Erzeugung/-Reparatur durch einen Agenten fehlt.

### 6. Resume nur bei Approval automatisch
`task_graph.json`, `design_state.yaml` und die an den Bitstream gebundene
Freigabe in `state.json` erlauben idempotente Wiederaufnahme. Automatisch
fortgesetzt wird nach einem Neustart aber nur ein Workflow, der auf Freigabe
wartete; andere unterbrochene Läufe muss der Benutzer erneut anstoßen
(`SupervisorOrchestrator.resume_project`). Events werden nicht persistiert.

### 7. Parallelität teilt einen Workspace
HDL-Worker laufen parallel in eigenen Threads (`limits.max_parallel_workers`).
File Ownership ist pro Modul-Datei geregelt, OpenCode-Prozesse arbeiten aber
im selben Workspace; die Top-Datei wird von `implement_module_<top>` und
`implement_top` nacheinander geschrieben.

## Bekannte offene Punkte (aus docs/feedback.md)

- `build_definitions.py` ist inkonsistent zu `test_definitions.py` bei `--stop-time` (wurde auf `1ms` vereinheitlicht, bleibt aber minimal-invasiv).
- Der Repair-Kontext wird bei großen Projekten lang (Code-Inhalte auf 10.000 Zeichen gedeckelt).
- Docker-Konfiguration wurde nicht verändert; GHDL läuft auf dem Host.

## Abhängigkeitsstatus

- Ollama, `langchain-core` und `langchain-ollama` wurden entfernt (2026-10-10). Alle Sprachmodell-Aufgaben laufen über OpenCode.
- HDL-Module und Testbenches werden im Produktionspfad über OpenCode erzeugt; der LLM-Port heißt `generate_text` und bietet keine Codegenerierungs-Methode.

## Behoben in dieser Reparatur

- **`supervisor.py` async/sync Mismatch**: `_run_static_check()` rief `await self._validation_service.validate()` auf, aber `ValidationService.validate()` ist synchron. Korrigiert auf `self._validation_service.validate()` ohne `await`.
- **`test_ghdl_validator.py`**: 6 vorbestehende Fehler, nicht durch diese Reparatur verursacht (nachgewiesen via `git stash`-Test).
