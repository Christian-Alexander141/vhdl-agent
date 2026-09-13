# Bewertung des Multi-Agent-Ziels

Datum: 2026-09-13

## Zielmaßstab

Das eigentliche Ziel des Projekts ist nicht die Demonstration eines einzelnen OpenCode-Agenten. Das Ziel ist ein belastbares Multi-Agent-System, das komplexe Hardwareaufgaben wie eine 8-Bit-CPU, einen RS-/Hamming-Decoder oder einen ähnlichen mehrmoduligen Entwurf:

1. aus einer Anforderung in überprüfbare Architektur und Teilaufgaben zerlegt,
2. mit mehreren spezialisierten Agenten implementiert,
3. über Verträge und Simulation gegen die Architektur verifiziert,
4. bei Fehlern gezielt diagnostiziert und repariert,
5. für ein konkretes FPGA synthetisiert und zeitlich bewertet,
6. nach menschlicher Freigabe auf das Board programmiert und
7. anschließend mit einem echten, projektspezifischen Hardwaretest validiert.

Ein erfolgreicher LED-Blinker oder ein einzelner OpenCode-Lauf ist dafür nur ein Smoke-Test, kein Nachweis der Zielerreichung.

## Kurzurteil

**Architektur und Bausteine: teilweise vorhanden. Produktionsreife für komplexe Designs: noch nicht erreicht.**

Das Repository enthält bereits einen Supervisor, spezialisierte Agenten, einen persistenten `DesignState`, einen TaskGraph, Vertragsprüfungen, GHDL, Vivado/openFPGALoader und Hardware-Test-Abstraktionen. Die vorhandenen Tests belegen vor allem isolierte Fähigkeiten. Der reale Produktionspfad nutzt diese Fähigkeiten jedoch nicht vollständig und enthält mehrere harte Brüche:

- Der produktive Supervisor orchestriert die Phasen seriell, nicht als tatsächlich persistierten und ausführbaren Projekt-DAG.
- Der TaskGraph wird im `SupervisorOrchestrator` nur erzeugt, aber nicht mit den Produktionsaufgaben befüllt oder ausgeführt.
- Der statische Check ist ein Platzhalter und prüft den Workspace nicht.
- Approval, FPGA-Programmierung und Hardwaretests sind zwischen Legacy- und Supervisor-Pfad inkonsistent.
- Der HardwareTestAgent nutzt standardmäßig ein Mock-Interface und kann dadurch einen erfolgreichen Hardwaretest melden, ohne echte Hardware zu prüfen.
- Timing- und Ressourcenanalyse liefern Platzhalterwerte.
- FPGA-/Programmer-Konfiguration und Tests widersprechen sich.
- Es fehlt ein echter End-to-End-Akzeptanztest für ein mehrmoduliges Design wie CPU oder Decoder.

## Befunde

### Kritisch

#### 1. Produktionspfad und Approval-Pfad sind nicht konsistent

Der API-Server verwendet den [SupervisorOrchestrator](../Schaltungsagent/src/orchestrator/supervisor_orchestrator.py), dessen `approve_task()` und `reject_task()` derzeit Platzhalter sind und immer `False` zurückgeben. Der ältere [AsyncAgentOrchestrator](../Schaltungsagent/src/orchestrator/orchestrator.py) besitzt dagegen eine echte `threading.Event`-basierte Approval-Registry.

Folge: Es gibt zwei Workflow-Implementierungen mit unterschiedlichen Fähigkeiten. Ein komplexes Projekt kann im Supervisor-Pfad bis zur Synthese gelangen, aber die Freigabe-/Flash-Steuerung ist dort nicht gleichwertig implementiert.

**Erforderliche Änderung:** Einen einzigen produktiven Workflow festlegen. Approval muss im Supervisor-Pfad als persistenter Taskzustand implementiert werden, inklusive `approve`, `reject`, Wiederaufnahme nach Prozessneustart und Anzeige der zugehörigen Task-ID. Die Legacy-Implementierung darf danach nur noch als Kompatibilitätsschicht existieren oder entfernt werden.

#### 2. Der TaskGraph ist kein produktiver Scheduler

Der [TaskGraph](../Schaltungsagent/src/domain/agents/task_graph.py) unterstützt Abhängigkeiten, Parallel-Batches, File Ownership und Invalidation. Im [SupervisorOrchestrator](../Schaltungsagent/src/orchestrator/supervisor_orchestrator.py) wird jedoch lediglich `self._task_graph = TaskGraph()` angelegt. Die Produktionsaufgaben werden nicht eingetragen, nicht über den Graphen gestartet und nicht als Ergebnisse persistiert.

Der Supervisor ruft stattdessen in [supervisor.py](../Schaltungsagent/src/agents/supervisor.py) eine fest codierte Phasenfolge auf. Das ist eine sequenzielle Zustandsmaschine, aber noch keine belastbare Multi-Agent-Projektplanung.

**Erforderliche Änderung:** Aus Analyse und Architektur einen persistierten Projekt-DAG erzeugen. Jeder Agentenauftrag braucht Inputs, Dependencies, Outputs, Ownership, Status, Retry-Zähler und Version. Der Scheduler muss unabhängige Module parallel ausführen können und nach Änderungen nur abhängige Aufgaben invalidieren.

#### 3. Hardwaretests sind standardmäßig simuliert

Der [HardwareTestAgent](../Schaltungsagent/src/agents/hardware_test.py) verwendet standardmäßig `MockHardwareTestInterface()`. Die Mock-Tests können daher `fpga_alive`, CPU- und GPIO-Tests bestehen, ohne dass ein FPGA programmiert oder UART/GPIO beobachtet wurde.

Zusätzlich erzeugt `_generate_cpu_test_program()` nur Dummy-Bytes. Das ist kein CPU-Programm und kann keine 8-Bit-CPU validieren.

**Erforderliche Änderung:** Hardwaretests müssen klar zwischen `MOCK`, `SIMULATION` und `REAL_HARDWARE` unterscheiden. `COMPLETED` darf für einen Hardwareworkflow nur bei realer Verbindung und projektspezifischem Protokolltest vergeben werden. Für CPU/Decoder müssen Testvektoren, erwartete Ausgaben, UART-Protokoll und Reset-/Clock-Verhalten aus der Architektur abgeleitet werden.

### Hoch

#### 4. Statischer Check prüft den Code aktuell nicht

`SupervisorAgent._run_static_check()` erstellt zwar einen `GHDLValidator`, ruft ihn aber nicht auf und gibt anschließend direkt `checks: passed` zurück. Damit kann der Multi-Agent-Pfad von fehlerhaftem oder nicht synthesizierbarem VHDL in die Simulation/Synthese weiterlaufen, ohne dass der vorgesehene Gatekeeper greift.

**Erforderliche Änderung:** Einen echten `StaticCheckService` bzw. den vorhandenen Validator aufrufen. Der Schritt muss alle Entities, Libraries, VHDL-Standards, Top-Level-Auswahl und synthesizability-relevante Regeln prüfen und strukturierte Diagnosen erzeugen.

#### 5. Verification-Ergebnisse werden nicht zuverlässig als Gate verwendet

Der Supervisor übergibt die Architektur an den `VerificationAgent`, aber die Zustandsaktualisierung und Fehlerweiterleitung ist nicht durchgehend konsistent. Der `VerificationAgent` führt GHDL aus, während der statische Check keinen echten Check macht. Für komplexe Designs fehlen außerdem verbindliche Testplan- und Coverage-Gates.

**Erforderliche Änderung:** Pro Requirement und Modul einen Testplan erzeugen. Simulationsergebnisse müssen im `DesignState` versioniert werden. Der Supervisor darf nur bei bestandenem Compile, Elaboration, Simulation und akzeptierter Coverage zur Synthese übergehen.

#### 6. Debug/Repair repariert nicht immer auf der richtigen Ebene

Der Reparaturpfad delegiert hauptsächlich an den `HDLAgent` und OpenCode. Bei Architektur- und Interfacefehlern muss aber zuerst die Architektur geändert und anschließend die abhängige Implementierung invalidiert werden. Bei Timing-, Constraint-, Toolchain- oder Hardwarefehlern ist eine HDL-Reparatur oft falsch.

**Erforderliche Änderung:** Fehlerklassen und Reparaturziele verbindlich definieren:

- Architektur-/Interfacefehler -> `ArchitectureAgent`
- Modul-/VHDL-Fehler -> `HDLAgent`
- Test-/Erwartungsfehler -> `VerificationAgent`/Testplan
- Synthese-/Timing-/Constraintfehler -> `FPGAAgent` plus Constraint- oder HDL-Reparatur
- Flash-/USB-/Treiberfehler -> Infrastruktur/Human Intervention
- Hardwarefunktionstest -> HDL/Integration/HardwareTestAgent abhängig von Diagnose

Jede Reparatur muss einen Vorher-/Nachher-Contract-Check und eine erneute Verifikation auslösen.

#### 7. Timing- und Ressourcenwerte sind Platzhalter

[FPGAAgent](../Schaltungsagent/src/agents/fpga.py) liefert in `analyze_timing()` und `check_resources()` feste Beispielwerte wie `fmax_mhz: 100.0`, `lut: 1250` und `ff: 2100`. Diese Werte stammen nicht aus Vivado-Reports.

Damit kann das System ein komplexes Design fälschlich als timing- und ressourcenkonform melden.

**Erforderliche Änderung:** Vivado-Reports strukturiert parsen und Werte im `DesignState` speichern. Harte Gates einführen: WNS/TNS, Fmax, LUT/FF/BRAM/DSP-Auslastung, DRC und Bitstream-Erzeugung.

#### 8. FPGA-Konfiguration ist widersprüchlich

[fpgas.yaml](../Schaltungsagent/src/data/fpgas.yaml) konfiguriert das Arty S7 mit `programmer: openfpgaloader`, während [test_ghdl_synthesis.py](../Schaltungsagent/tests/test_ghdl_synthesis.py) `vivado` erwartet. Andere Dokumentation beschreibt Vivado als nachgewiesenen Flashpfad.

Das führt dazu, dass Tests und Produktionspfad unterschiedliche Programmer wählen. Für komplexe Projekte ist das ein reproduzierbarer Integrationsfehler.

**Erforderliche Änderung:** Pro Board einen verbindlichen Toolchain-/Programmer-Vertrag festlegen. Für Arty S7 sollte auf diesem Host der nachgewiesene Vivado-Hardware-Manager der Standard sein; openFPGALoader kann als explizite Alternative bleiben. Registry, Konfiguration, Tests und Dokumentation müssen denselben Wert verwenden.

### Mittel

#### 9. FPGA-Ziel wird nicht zuverlässig aus der Benutzeranforderung übernommen

Der Supervisor verwendet in seinen FPGA-Aufgaben standardmäßig `arty_s7_50`. Eine robuste Extraktion eines Zielboards aus Anforderungen wie „für GateMate A1“ oder „für Arty S7-50“ ist im produktiven Pfad nicht sichtbar abgesichert.

**Erforderliche Änderung:** FPGA-Ziel früh normalisieren, im `DesignState` speichern und vor Architektur-/Constraint-/Syntheseplanung validieren. Unklare oder widersprüchliche Ziele müssen eine Rückfrage auslösen.

#### 10. Architektur- und Implementierungsverträge sind zu schwach

Der [ContractChecker](../Schaltungsagent/src/domain/agents/contract_check.py) prüft vor allem Portnamen und einige statische Bedingungen. Für CPU oder RS-Decoder reichen Portnamen nicht aus. Es fehlen unter anderem Bitbreiten, signed/unsigned-Semantik, Clock-/Reset-Polarität, Latenzen, Handshake-Protokolle, Durchsatz, Paketgrenzen und Top-Level-Pinverträge.

**Erforderliche Änderung:** Contracts als versionierte, maschinenprüfbare Schnittstellen definieren. Für jede Verbindung müssen Richtung, Breite, Typ, Clock-Domain, Reset, Latenz und Handshake feststehen.

#### 11. Persistenz und Wiederaufnahme sind nicht vollständig multi-agent-fähig

`DesignState` ist vorhanden, aber laufende Agentenaufträge, TaskGraph-Status, File Ownership, Events und Approval-Wartezustände werden nicht als ein zusammenhängender wiederaufnehmbarer Workflow persistiert. Ein Prozessneustart kann dadurch zu verlorenen oder doppelten Aufgaben führen.

**Erforderliche Änderung:** Atomare Checkpoints nach jedem Agentenauftrag. Persistieren: DAG, AgentTask, Inputs/Outputs, Versionshashes, Ownership, Diagnosehistorie, Approvalstatus und externe Artefakte. Resume muss idempotent sein.

#### 12. Parallelität ist getestet, aber nicht im Produktionspfad aktiv

[test_multi_agent_collaboration.py](../test_multi_agent_collaboration.py) testet Task-DAG, Ownership, Parallel-Batches und Handoffs erfolgreich. Das belegt die Bausteine, nicht deren Nutzung im realen Workflow.

**Erforderliche Änderung:** Ein produktiver WorkerPool/Scheduler muss unabhängige Module tatsächlich parallel ausführen, Ressourcenlimits beachten und Konflikte verhindern. Gemeinsame Integrations- und Top-Level-Dateien müssen sequenziell geschützt werden.

## Was bereits vorhanden ist

- Spezialisierte Agenten für Architektur, HDL, Verifikation, Debug, FPGA und Hardwaretests.
- Persistentes [DesignState-Modell](../Schaltungsagent/src/domain/models/design_state.py).
- EventBus und WebSocket-Observability.
- TaskGraph, File Ownership und ContractChecker als brauchbare Grundlagen.
- GHDL-Validierung und Vivado-Bitstream-Service.
- Board-Registry und Approval-Konzept.
- Reparaturbegrenzungen und Erkennung identischer Fehler/fehlenden Fortschritts.
- Lokale OpenCode-Ausführung als ressourcenschonender Testmodus.
- Der aktuelle openFPGALoader-Ausgabeparser erkennt das angeschlossene Arty S7 korrekt.

## Nachweisstand

Am 2026-09-13 wurden folgende Prüfungen ausgeführt:

- `test_multi_agent_collaboration.py` plus `test_supervisor_workflow.py`: **17 Tests bestanden**.
- `test_flash_service.py`: **13 Tests bestanden**.
- Echte Host-Erkennung: Arty S7 wurde als `xc7s50`, Familie `spartan7`, erkannt.
- `test_ghdl_synthesis.py`: **1 Test fehlgeschlagen**, weil Registry und Test beim Arty-Programmer `openfpgaloader` versus `vivado` widersprechen.

Die 17 Multi-Agent-Tests sind überwiegend Komponenten-/Mocktests. Es gibt keinen belastbaren Akzeptanztest, der ein mehrmoduliges CPU- oder Decoderdesign vom Requirement bis zur echten Board-Funktion durchläuft.

## Empfohlene Umsetzungsreihenfolge

### Phase 0: Produktionspfad festlegen

1. SupervisorOrchestrator als einzigen Produktionspfad festlegen.
2. Legacy-Orchestrator aus dem API-Pfad entfernen oder als Adapter kapseln.
3. Approval im Supervisor-Pfad implementieren und Prozessneustart unterstützen.
4. FPGA-Programmer für Arty S7 in Registry, Konfiguration, Tests und Dokumentation vereinheitlichen.

**Abnahmekriterium:** Ein kleiner Entwurf kann über API gestartet, freigegeben, geflasht und eindeutig abgeschlossen werden.

### Phase 1: Echter Multi-Agent-DAG

1. ArchitectureAgent erzeugt versionierte Module, Contracts, Dependencies und Testplan.
2. Supervisor materialisiert daraus `AgentTask`-Objekte im TaskGraph.
3. Scheduler führt unabhängige Module parallel aus.
4. File Ownership, Handoffs und Invalidation sind produktiv aktiv.
5. Jeder Task schreibt einen Checkpoint und ein strukturiertes Ergebnis.

**Abnahmekriterium:** Zwei unabhängige Module laufen parallel; eine Architekturänderung invalidiert nur abhängige Implementierungs-/Testaufgaben.

### Phase 2: Verifikation als Gatekeeper

1. Statischen Check implementieren.
2. ContractChecker in den Produktionspfad integrieren.
3. Testplan pro Requirement/Modul erzeugen.
4. GHDL Compile, Elaboration, Simulation und Coverage als harte Gates behandeln.
5. Debugdiagnosen mit Fehlerklasse, Evidenz, Modul und Reparaturziel persistieren.

**Abnahmekriterium:** Ein absichtlich falscher Port, eine falsche Bitbreite und ein falsches Simulationsergebnis werden jeweils erkannt und an die richtige Agentenrolle weitergeleitet.

### Phase 3: Synthese und FPGA-Vertrauen

1. Vivado-Reports für Timing, Ressourcen, DRC und Bitstream auswerten.
2. Constraints als Teil des Architektur-/Board-Vertrags behandeln.
3. Synthesereparaturen von Simulationsreparaturen trennen.
4. Toolchain- und Boarddiagnose vollständig in Events/Chat ausgeben.

**Abnahmekriterium:** Ein Design mit absichtlich verletztem Timing oder fehlendem Pin-Constraint wird nicht als erfolgreich abgeschlossen.

### Phase 4: Echte Hardwarevalidierung

1. Mock- und Real-Hardware explizit unterscheiden.
2. UART-/GPIO-Interface für das konkrete Board konfigurieren.
3. Hardwaretest-Suiten aus der Architektur und den Requirements ableiten.
4. CPU- und Decoder-Testvektoren statt Dummy-Bytes verwenden.
5. Hardwarefehler klassifizieren und gezielt an Debug/HDL/FPGA oder den Benutzer zurückgeben.

**Abnahmekriterium:** Ein 8-Bit-CPU-Smoke-Test führt ein definiertes Programm aus und meldet echte, über UART oder GPIO beobachtete Ergebnisse.

### Phase 5: Ziel-Akzeptanztests

Mindestens folgende reproduzierbare End-to-End-Projekte sollten als CI-/Hardware-Testfälle aufgenommen werden:

- 8-Bit-CPU mit ALU, Registerfile, Steuerwerk, Programmspeicher, UART-Ausgabe und Testprogramm.
- RS- oder Hamming-Decoder mit Fehlervektoren, Latenz-/Throughput-Vertrag und UART/GPIO-Ergebnis.
- Ein absichtlich fehlerhaftes Projekt, das durch Debug/Repair erfolgreich repariert wird.
- Ein absichtlich fehlerhaftes Constraint-/Timing-Projekt, das korrekt blockiert.
- Resume nach Prozessneustart in Approval, Reparatur und Hardwaretest.

## Endzustand, der als Ziel gelten sollte

Das Projekt ist am Ziel, wenn für ein komplexes Beispieldesign alle folgenden Aussagen gleichzeitig wahr sind:

- Die Aufgabe wird in nachvollziehbare AgentTasks zerlegt.
- Mehrere Agenten arbeiten mit klaren Contracts und Ownership-Regeln.
- Der Zustand kann nach jedem Schritt geladen und fortgesetzt werden.
- Fehler werden nicht nur wieder an OpenCode weitergereicht, sondern klassifiziert und an die zuständige Rolle delegiert.
- Kein Erfolg wird aus Mock-, Platzhalter- oder ungeprüften Werten abgeleitet.
- Simulation, Synthese, Timing, Ressourcen, Bitstream, Flash und Hardwaretest sind echte Gates.
- Die Benutzeroberfläche zeigt Agent, Task, Phase, Diagnose, Artefakte und Entscheidungsmöglichkeiten.
- Ein echter CPU-/Decoder-Akzeptanztest läuft reproduzierbar bis zum Board und zurück.
