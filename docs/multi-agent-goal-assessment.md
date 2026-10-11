# Bewertung des Multi-Agent-Ziels

Erstbewertung: 2026-09-13 · Aktualisiert: 2026-10-07 (Umsetzung der Kernlücken)

## Zielmaßstab

Das eigentliche Ziel des Projekts ist nicht die Demonstration eines einzelnen OpenCode-Agenten. Das Ziel ist ein belastbares Multi-Agent-System, das komplexe Hardwareaufgaben wie eine 8-Bit-CPU, einen RS-/Hamming-Decoder oder einen ähnlichen mehrmoduligen Entwurf:

1. aus einer Anforderung in überprüfbare Architektur und Teilaufgaben zerlegt,
2. mit mehreren spezialisierten Agenten implementiert,
3. über Verträge und Simulation gegen die Architektur verifiziert,
4. bei Fehlern gezielt diagnostiziert und repariert,
5. für ein konkretes FPGA synthetisiert und zeitlich bewertet,
6. ohne Benutzerfreigabe auf das Board programmiert (die frühere Freigabe vor dem Flashen wurde am 2026-10-11 entfernt) und
7. anschließend mit einem echten, projektspezifischen Hardwaretest validiert.

Ein erfolgreicher LED-Blinker oder ein einzelner OpenCode-Lauf ist dafür nur ein Smoke-Test, kein Nachweis der Zielerreichung.

## Kurzurteil

**Stand 2026-10-07: Alle Phasen haben echte Gates, Fehler werden an die zuständige Rolle geroutet, und kein Erfolg wird mehr aus Mock- oder Platzhalterwerten abgeleitet. Nachgewiesen ist das mit Komponenten- und Integrationstests (Stub-Agenten, echtes GHDL, nachgebildete Vivado-Reports). Ein End-to-End-Lauf einer CPU oder eines Decoders auf dem Board steht noch aus.**

| # | Befund (2026-09-13) | Status 2026-10-07 |
|---|---|---|
| 1 | Approval nicht persistent / nicht wiederaufnehmbar | **entfallen** (2026-10-11): Die Benutzerfreigabe vor dem Flashen wurde entfernt |
| 2 | TaskGraph kein produktiver Scheduler | **behoben** für die Implementierung: persistierter, wiederaufnehmbarer Modul-DAG |
| 3 | Hardwaretests standardmäßig simuliert, Dummy-CPU-Programm | **behoben**: Mock ⇒ `SKIPPED`, kein Erfolg; projektspezifische Testvektoren |
| 4 | Statischer Check ohne Prüfung | **behoben** (schon vor diesem Stand) + Contract-Gate |
| 5 | Verification kein verlässliches Gate | **behoben**: versionierte Ergebnisse, Testplan, Coverage-Gate |
| 6 | Reparatur immer über HDL/OpenCode | **behoben**: verbindliches Routing pro Fehlerklasse |
| 7 | Timing/Ressourcen Platzhalter | **behoben**: Reports werden geparst und sind hartes Gate |
| 8 | Programmer-Konfiguration widersprüchlich | **behoben** (schon vor diesem Stand): Arty S7 → `vivado` |
| 9 | FPGA-Ziel nicht aus Anforderung | **behoben**: Normalisierung in der Analyse, Rückfrage bei Widerspruch |
| 10 | Contracts zu schwach | **teilweise**: Richtung, Typ, Bitbreite (mit Generics); keine Protokollsemantik |
| 11 | Persistenz/Resume unvollständig | **weitgehend behoben**: Checkpoint pro Batch, idempotentes Resume; Events nicht persistiert |
| 12 | Parallelität nicht im Produktionspfad | **behoben**: unabhängige Module laufen in parallelen Worker-Threads |

## Befunde und Umsetzung

### 1. Freigabe vor dem Flashen (entfernt)

Die Benutzerfreigabe vor dem Flashen wurde am 2026-10-11 entfernt (Orchestrator, API, Zustandsautomat, Dashboard). Anlass: Im Lauf gray-countdown wartete der Workflow vor jedem Flash-Versuch auf die Freigabe, insgesamt mehrere Stunden. Der Benutzer wird nur noch gerufen, wenn die Eskalationsleiter erschöpft ist oder Werkzeug bzw. Board fehlen (siehe `docs/doku.html`, Abschnitt 15, #36).

### 2. TaskGraph als produktiver Scheduler

**Befund:** Der Orchestrator legte nur einen leeren `TaskGraph` an. Der Supervisor baute für die Implementierung zwar einen Graphen, führte ihn aber faktisch sequenziell aus und verwarf ihn bei jedem Lauf.

**Umsetzung:** [supervisor.py](../Schaltungsagent/src/agents/supervisor.py) `_run_implementation`
- Jeder Modul-Task trägt einen **Contract-Fingerprint** (Modul-Contract, beteiligte Interfaces, Clock/Reset) und einen **Run-Key** (Auftrag + Anzahl abgeschlossener Läufe), dazu Abhängigkeiten, Ownership, Status, Versuchszähler und Ergebnis.
- `task_graph.json` wird nach jedem Batch atomar geschrieben (Checkpoint).
- Beim nächsten Lauf werden abgeschlossene Tasks mit gleichem Fingerprint und Run-Key übernommen. Neu ausgeführt werden nur Tasks mit geändertem Contract, deren transitiv Abhängige sowie offene oder fehlgeschlagene Tasks (`TASK_INVALIDATED`-Events).
- Tasks, deren Abhängigkeit fehlgeschlagen ist, werden `BLOCKED` statt trotzdem ausgeführt.
- Der tote `_task_graph` im Orchestrator ist entfernt. `load_task_graph()` liest jetzt den persistierten Graphen des Supervisors.

**Grenze:** Analyse, Verifikation, Synthese und Flash sind weiterhin feste Phasen der Zustandsmaschine; der DAG umfasst die Implementierungsaufträge.

### 3. Hardwaretests

**Befund:** Das Mock-Interface konnte Erfolg melden. Der Code verwendete einen nicht existierenden `AgentStatus.SKIPPED` und lief deshalb in einen Fehler. Das CPU-Programm bestand aus Dummy-Bytes, und unbekannte Testtypen galten als bestanden.

**Umsetzung:** [hardware_test.py](../Schaltungsagent/src/agents/hardware_test.py)
- Ohne echte Schnittstelle ist das Ergebnis `SKIPPED` (`test_mode: MOCK`); es wird kein Test ausgeführt. `AgentStatus.SKIPPED` existiert jetzt.
- Testvektoren stammen aus dem Plan-Manifest (`hardware_tests`) oder aus `tests/hardware_tests.yaml`. Typen: `echo`, `uart_exchange`, `cpu_program`. Ein erwartetes Ergebnis ist Pflicht, und ungültige Spezifikationen werden abgelehnt.
- Aus der Architektur abgeleitet wird nur der UART-Loopback: Die UART-Integration fügt dem Top-Level eine Echo-Brücke hinzu.
- Bei echter Hardware ohne Testvektoren ist das Ergebnis `BLOCKED` mit Rückfrage. Unbekannte Testtypen gelten als nicht bestanden.
- Der UART-Port wird über `hardware_test.uart_port` konfiguriert. Nur dann folgt auf den Flash die Phase `HARDWARE_TESTING`. Ohne Port endet der Workflow mit dem ausdrücklichen Hinweis, dass die Board-Funktion nicht validiert ist (`hardware_validated: false`).
- Ein Neustart in `HARDWARE_TESTING` mit echter Hardware wiederholt den Test, statt ihn als abgeschlossen zu werten.

### 4. Statischer Check

Der Check prüft jetzt zuerst die Architektur-Contracts (siehe 10) und ruft danach GHDL auf. Contract-Verletzungen erzeugen eine strukturierte Diagnose `contract_violation` mit den betroffenen Modulen.

### 5. Verifikation als Gatekeeper

**Umsetzung:** [test_plan.py](../Schaltungsagent/src/domain/agents/test_plan.py), `_record_verification` / `_run_validation`
- Jedes Simulationsergebnis wird mit Architekturversion, Testplan und Historie in `DesignState.verification` gespeichert.
- Der **Testplan** ermittelt über die Instanziierungshierarchie, welches Modul von welcher Testbench erreicht wird, und leitet daraus die Abdeckung je Requirement ab (`Requirement.verified`).
- Die Synthese startet nur, wenn alle folgenden Bedingungen erfüllt sind:
  - Die Simulation ist bestanden.
  - Das Simulationsergebnis gehört zur aktuellen Architekturversion.
  - Der Contract-Check für diese Version ist bestanden.
  - Die Modulabdeckung erreicht mindestens `gates.min_module_coverage` (Standard 100 %).
- Der VerificationAgent übernimmt eine neu erzeugte Testbench nur, wenn sie den DUT instanziiert und der Workspace damit weiter kompiliert und simuliert. Sonst bleibt die alte Datei erhalten.

**Beobachtung:** Das Gate fand sofort eine echte Lücke. Im deterministischen Testpfad instanziiert die Mock-Testbench `zaehler_tb` den Zähler gar nicht, und der GHDL-Lauf war trotzdem „PASS“. Der Workflow endet jetzt mit `Coverage gap … zaehler`.

### 6. Reparatur auf der richtigen Ebene

**Umsetzung:** [repair_routing.py](../Schaltungsagent/src/domain/agents/repair_routing.py), [debug.py](../Schaltungsagent/src/agents/debug.py), `_handle_failure`

| Fehlerklasse | Ziel | Wirkung |
|---|---|---|
| `interface_mismatch` bei erfüllten Contracts | ArchitectureAgent | Plan verfeinern, Version +1, nur geänderte Module + Abhängige neu implementieren |
| `interface_mismatch` bei verletztem Contract, `contract_violation`, Syntax-, Typ-, Elaborations-, Simulations-, Clock/Reset-Fehler | HDLAgent | `fix_hdl` für die betroffenen Module |
| `testbench_error`, `coverage_gap` | VerificationAgent | Testbench erzeugen und prüfen |
| `synthesis_error`, `timing_error` | HDLAgent mit Synthesekontext | `fix_hdl` mit Timing-/Ressourcenwerten und Timing-Akzeptanzkriterium |
| `constraint_error`, `resource_error`, `bitstream_error`, `flash_error`, `hardware_error`, `infrastructure`, `target_ambiguous` | Benutzer | `BLOCKED` mit Begründung, `HUMAN_INTERVENTION_REQUESTED` |

- Strukturierte Fehlerklassen der Gates haben Vorrang vor der Regex-Klassifikation.
- Jede HDL-Reparatur läuft mit einem **Vorher-/Nachher-Contract-Check**. Ein Patch, der neue Contract-Verletzungen einführt, wird abgelehnt.
- Nach jeder Reparatur beginnt die Verifikation wieder beim statischen Check, nicht erst bei der Simulation.
- Reparaturversuche werden gezählt (nicht nur Erfolge), damit `max_repairs_per_stage` greift.
- Behobene Schleifenfehler:
  - Die Erkennung wiederholter Fehler verglich `type` mit `failure_type` und schlug deshalb nie an.
  - Nach `IDENTICAL_ERROR` lief die Schleife im Zustand `FAILED` weiter bis zum Iterationslimit.
  - Aus `VALIDATING` fiel `_safe_transition_to` mangels erlaubtem Übergang nach `SYNTHESIZING` zurück. Ein Validierungsfehler konnte so in die Synthese führen.

### 7. Timing und Ressourcen

**Umsetzung:** [fpga.py](../Schaltungsagent/src/agents/fpga.py)
- `report_timing_summary` wird spaltengenau geparst (WNS, TNS, WHS, THS), Fmax aus Taktperiode und WNS berechnet. Der alte Parser las WHS/THS aus den Endpunkt-Spalten.
- `report_utilization` wird zeilenweise geparst (Slice/CLB LUTs, Register, BRAM, DSP, Auslastung in %).
- Fehlende Werte bleiben `None`, es gibt keine Platzhalter mehr.
- Eine Synthese gilt nur als erfolgreich, wenn alle folgenden Bedingungen erfüllt sind:
  - Beide Reports sind vorhanden.
  - Ein Takt-Constraint ist gesetzt.
  - WNS ≥ 0 und WHS ≥ 0.
  - Keine Ressource ist über 100 % ausgelastet.

  Sonst gibt es eine Diagnose `timing_error`, `constraint_error`, `resource_error` oder `infrastructure`. Abschaltbar ist das Gate nur über `gates.require_timing_closure`.
- Timing und Ressourcen stehen jetzt in `DesignState.synthesis`.

### 8. FPGA-Konfiguration

Unverändert gültig: Für das Arty S7-50 ist `vivado` der Programmer, Registry und `test_ghdl_synthesis.py` stimmen überein.

### 9. FPGA-Ziel aus der Anforderung

[fpga_target.py](../Schaltungsagent/src/services/fpga_target.py): Die Analysephase erkennt Board-Nennungen (z. B. „GateMate A1“, „CCGM1A1“, „Arty S7-50“, „xc7s50“, „Spartan-7“). Das Ergebnis landet in `DesignState.fpga` (Ziel, Programmer, Part) und wird von Synthese und Flash verwendet. Bei mehreren Boards oder einer explizit gesetzten, aber widersprechenden Angabe endet die Phase mit `BLOCKED` und einer offenen Frage. Ohne Nennung gilt `synthesis.default_fpga`.

### 10. Contracts

[contract_check.py](../Schaltungsagent/src/domain/agents/contract_check.py) prüft jetzt:
- Existenz, Richtung, Basistyp und Bitbreite jedes vertraglich festgelegten Ports, auch bei Breiten mit Generics (`WIDTH-1 downto 0`),
- den Entity-Namen,
- den Clock-Port sequentieller Module (Warnung),
- die Richtungen von Interface-Signalen und das deklarierte Top-Level.

Typisierte Ports kommen aus dem erweiterten Manifest-Schema (`modules[].ports` mit `name`/`direction`/`type`, validiert im `PlanValidator`). Sie werden in `ModuleInfo.ports` gespeichert und dem HDLAgent als verbindliches Interface übergeben, statt Typen zu raten.

**Offen:** Latenz, Handshake, Durchsatz, Reset-Polarität und Clock-Domain-Übergänge sind nicht maschinenprüfbar.

### 11. Persistenz und Wiederaufnahme

| Artefakt | Inhalt |
|---|---|
| `design_state.yaml` | Phase, Architekturversion, Verifikation inkl. Testplan und Historie, Synthesewerte, Diagnosehistorie mit Reparaturziel, Reparaturprotokoll |
| `task_graph.json` | Tasks mit Status, Fingerprint, Run-Key, Versuchszähler, Ergebnis, Ownership |

Resume ist idempotent: Abgeschlossene Tasks werden übernommen, laufende und fehlgeschlagene werden wiederholt.

**Offen:** Events werden nicht persistiert. Nach einem Neustart setzt der Benutzer unterbrochene Läufe mit `resume_project()` fort.

### 12. Parallelität

Tasks eines Batches laufen in eigenen Worker-Threads mit eigener Event-Loop, weil der HDLAgent den OpenCode-Subprozess blockierend aufruft. `asyncio.gather` allein lief deshalb faktisch sequenziell. Die Anzahl begrenzt `limits.max_parallel_workers` (Standard 2, 1 = sequenziell). Ein Worker-Absturz wird als fehlgeschlagener Task isoliert.

## Nachweisstand (2026-10-07)

Neue Akzeptanztests: [test_multi_agent_gates.py](../Schaltungsagent/tests/test_multi_agent_gates.py), **46 Tests, alle bestanden** (5 Wiederholungen ohne Flakiness). Sie prüfen die Abnahmekriterien der Phasen 1–4 direkt:

| Phase | Abnahmekriterium | Test |
|---|---|---|
| 1 | Zwei unabhängige Module laufen parallel | `test_independent_modules_run_in_parallel` (Zeitfenster überlappen) |
| 1 | Architekturänderung invalidiert nur Abhängige | `test_contract_change_invalidates_only_dependent_tasks` |
| 1 | Resume wiederholt nur offene Tasks | `test_resume_after_crash_reruns_only_open_tasks` |
| 2 | Falscher Port / falsche Breite / falsche Richtung / falscher Typ erkannt | `test_contract_checker_detects_port_errors` (echte VHDL-Dateien) |
| 2 | … und an die richtige Rolle geleitet | `test_static_check_blocks_wrong_width_and_routes_to_hdl`, `test_wrong_simulation_result_routes_to_hdl`, `test_interface_mismatch_between_valid_modules_routes_to_architecture` |
| 2 | Coverage- und Versions-Gate | `test_validation_gate_blocks_uncovered_modules`, `test_validation_gate_rejects_stale_simulation` |
| 3 | Verletztes Timing / fehlender Constraint nicht erfolgreich | `test_timing_violation_blocks_success`, `test_missing_clock_constraint_blocks_success`, `test_missing_reports_and_overuse_block_success` |
| 4 | Kein Erfolg aus Mock; CPU-Programm mit erwarteter UART-Ausgabe | `test_mock_hardware_never_reports_success`, `test_cpu_program_vectors_pass_and_fail_on_real_interface` |
| – | Ziel-FPGA, Flashen ohne Freigabe | `test_fpga_target_*`, `test_flash_runs_without_waiting_for_approval` |

Gesamte Testsuite (`tests`, `src/tests`, `test`): **365 bestanden, 37 fehlgeschlagen, 7 Fehler, 11 übersprungen**. Vor den Änderungen waren es 316 bestanden, 39 fehlgeschlagen und 7 Fehler. Keine neuen Fehlschläge; zwei API-Tests laufen jetzt wieder (fehlender `Path`-Import im Orchestrator). Die verbleibenden Fehlschläge bestanden schon vorher und gehen auf veraltete Test-APIs zurück. Behoben ist außerdem die frühere Regression in `test_multi_agent_collaboration.py::test_full_multi_agent_workflow`: Das Test-Mock kannte die `plan()`-Schnittstelle des ArchitectureAgent nicht.

## Verbleibende Schritte

1. **Ziel-Akzeptanztest auf dem Board (Phase 5).** 8-Bit-CPU und Hamming-Decoder mit Testvektoren im Manifest, `hardware_test.uart_port` gesetzt, realer Lauf bis zur UART-Antwort. Dazu ein absichtlich fehlerhaftes Projekt (Reparatur) und ein Projekt mit Timing-Verletzung (Blockade).
2. **Planer-Schema im Betrieb prüfen.** Liefert OpenCode verlässlich typisierte `ports` und sinnvolle `hardware_tests`? Ohne sie bleiben Contracts namensbasiert und Hardwaretests auf den UART-Loopback beschränkt.
3. **Funktionale Coverage.** Assertions je Requirement statt nur struktureller Erreichbarkeit.
4. **Protokoll-Contracts.** Latenz, Handshake, Reset-Polarität, Clock-Domains.
5. **Constraint-Agent.** Pin-/Clock-Constraints aus Board-Vertrag erzeugen und reparieren, statt `constraint_error` an den Benutzer zu geben.
6. **Vorbestehende Testschulden.** Etwa 37 Tests scheitern unabhängig von diesen Änderungen an veralteten APIs (`llm_service=`-Parameter, Zustandsübergänge, entfernte Module wie `Schaltungsagent.evaluation`).

## Endzustand, der als Ziel gelten sollte

Das Projekt ist am Ziel, wenn für ein komplexes Beispieldesign alle folgenden Aussagen gleichzeitig wahr sind:

- Die Aufgabe wird in nachvollziehbare AgentTasks zerlegt. — *Implementierung: ja; übrige Phasen als Zustandsmaschine*
- Mehrere Agenten arbeiten mit klaren Contracts und Ownership-Regeln. — *ja, Contracts ohne Protokollsemantik*
- Der Zustand kann nach jedem Schritt geladen und fortgesetzt werden. — *ja (Checkpoint pro Batch/Phase)*
- Fehler werden klassifiziert und an die zuständige Rolle delegiert. — *ja*
- Kein Erfolg wird aus Mock-, Platzhalter- oder ungeprüften Werten abgeleitet. — *ja*
- Simulation, Synthese, Timing, Ressourcen, Bitstream, Flash und Hardwaretest sind echte Gates. — *ja; Hardwaretest nur mit konfiguriertem UART*
- Die Benutzeroberfläche zeigt Agent, Task, Phase, Diagnose, Artefakte und Entscheidungsmöglichkeiten. — *Events vorhanden (`REPAIR_ASSIGNED`, `TASK_INVALIDATED`, `PARALLEL_BATCH_*`, `CONTRACT_CHECK_*`); Dashboard nicht angepasst*
- Ein echter CPU-/Decoder-Akzeptanztest läuft reproduzierbar bis zum Board und zurück. — **offen**
