# Ergaenzender Implementierungs-Prompt: Betriebssicherheit und reale EDA-Gates

## Kontext

Die bestehende Statusanalyse in `FPGA-IMPLEMENTIERUNG.md` beschreibt bereits die wichtigsten Luecken in Validierung, Reparatur, OpenCode, Synthese, Hardwaretests und Persistenz. Dieser Folgeauftrag behandelt zusaetzliche Risiken, die vor einem belastbaren Multiagentenbetrieb behoben werden muessen.

Wichtig: Die Aussagen zum Teststatus muessen mit einem aktuellen Testlauf belegt werden. Eine historische Angabe wie "37/37 Tests bestanden" darf nicht als aktueller Nachweis verwendet werden. Dokumentiere Datum, Kommando, Umgebung, Passed/Failed/Skipped/Error und externe Toolversionen.

## Ziel

Ergaenze das bestehende VHDL/RTL-Multiagentensystem so, dass parallele Projekte, Neustarts, API-Zugriffe, OpenCode-Ausfuehrung und FPGA-EDA-Schritte deterministisch, sicher und nachvollziehbar funktionieren.

OpenCode bleibt Planungs- und Coding-Agent. Es darf VHDL/RTL und zugehoerige Artefakte bearbeiten, aber niemals ein Gate als bestanden markieren. Die deterministischen Services bleiben fuer Validierung, Synthese, Timing, Bitstream, Flash und Hardwaretest autoritativ.

## P0: Zustands- und Ausfuehrungskonsistenz

### 1. Eine verbindliche Zustandsmaschine

`StateMachine` und `DesignState.current_stage` duerfen nicht unabhaengig voneinander laufen.

- Entscheide, welches Modell die autoritative Zustandsmaschine ist.
- Fuehre jeden erlaubten Uebergang ueber eine zentrale Transition-Funktion.
- Persistiere Zustand, letzte Transition, Grund, Task-ID und Zeitstempel.
- Modellier `INFRASTRUCTURE_FAILURE`, `BLOCKED`, `SKIPPED`, `FAILED` und `AWAITING_APPROVAL` konsistent in Zustand, API und Resume-Logik.
- Ungueltige Uebergaenge muessen deterministisch mit strukturiertem Fehler abgelehnt werden.

**Abnahme:** Ein Test prueft fuer jede Produktionsphase die Synchronitaet von `DesignState` und `StateMachine`, ungueltige Uebergaenge und den Resume-Zustand nach einem Prozessneustart.

### 2. Supervisor muss pro Projekt isoliert sein

`SupervisorAgent` haelt mutable Felder wie `_current_task` und `_design_state`. Eine Instanz darf deshalb nicht ungeschuetzt mehrere Projekte parallel bearbeiten.

- Erzeuge pro Lauf eine isolierte Supervisor-Instanz oder fuehre eine nachweisbar thread-sichere per-project Session ein.
- Keine gemeinsam genutzten mutable Agentenzustaende zwischen Projekten.
- Events, Logs, Artefakte, Approvals und Reparaturzaehler muessen immer eine `project_id` und `task_id` tragen.
- Definiere Cancellation, Timeout und Cleanup fuer Threads und externe Prozesse.

**Abnahme:** Zwei parallele Projekte mit unterschiedlichen Workspaces, Reparaturen und Approvals duerfen weder Dateien noch DesignState noch Events vermischen.

## P0: Workspace- und OpenCode-Isolation

### 1. Filesystem-Grenzen technisch erzwingen

`LocalFileSystemService` muss alle Pfade gegen die erlaubte Workspace-Basis pruefen. Das gilt auch bei direkter Nutzung ohne API.

- Erlaube nur kanonische Pfade unter `base_dir` beziehungsweise dem zugewiesenen Projekt-Workspace.
- Lehne `..`, absolute Fremdpfade, Nullbytes und Symlinks aus dem Workspace ab, sofern sie nicht explizit freigegeben sind.
- Validiere Projekt-IDs als sichere Namen ohne `/`, `\\`, `..` oder Steuerzeichen.
- Wende die Pruefung auf `read_file`, `write_file`, `file_exists`, `list_files`, `delete_workspace` und Cleanup an.
- Verwende atomare Writes fuer Quellcode, DesignState und Checkpoints.

**Abnahme:** Direkte Service-Aufrufe mit Traversal, absoluten Pfaden, Symlinks und gleichnamigen Pfadpraefixen werden abgelehnt und erzeugen keinen Dateischaden.

### 2. Docker-Modus darf nicht unbemerkt unsandboxed werden

- Ein aktiv konfigurierter Docker-Modus darf bei fehlendem Docker, fehlenden Rechten oder falschem Containerpfad nicht automatisch auf lokale Ausfuehrung zurueckfallen.
- Lokaler Fallback ist nur bei explizitem `test_mode` oder einer expliziten Policy erlaubt und muss als eigener Status protokolliert werden.
- `_resolve_container_path()` muss Pfade ausserhalb der Host-Workspace-Basis hart ablehnen, nicht auf den Container-Root umbiegen.
- Pruefe Symlinks, gleichnamige Praefixe und Container-/Host-Pfadmapping.
- OpenCode muss eine erlaubte Dateiliste oder File-Ownership erhalten und Aenderungen ausserhalb dieser Liste ablehnen.

**Abnahme:** Tests beweisen, dass Dockerfehler nicht stillschweigend zu einem ungeschuetzten Hostlauf fuehren und dass unzulaessige Dateien nicht veraendert werden koennen.

## P1: API-, Async- und Zugriffssicherheit

### 1. API-Vertraege vollstaendig pruefen

- Implementiere und teste alle vom API-Server aufgerufenen Methoden, insbesondere `handle_chat_async`.
- Verwende fuer Chat, Task-Start, Upload, Status, Dateilesen, Loeschen und Approval ein dokumentiertes Request-/Response-Schema.
- Ein synchroner EDA-Lauf darf den FastAPI-/WebSocket-Eventloop nicht blockieren. Verwende einen kontrollierten Worker-Pool oder eine Job-Queue.
- Cancellation, Disconnect, Timeout und Worker-Absturz muessen einen definierten Taskstatus hinterlassen.
- Keine doppelte Ausfuehrung bei wiederholten Requests oder Retries.

**Abnahme:** Ein API-/WebSocket-Test beantwortet waehrend eines laufenden GHDL-/Vivado-Doubles weitere Requests, verarbeitet Disconnects sauber und meldet den finalen Taskstatus genau einmal.

### 2. API nicht offen ins Netz stellen

Da der Server standardmaessig an `0.0.0.0` bindet, muessen alle schreibenden und sicherheitskritischen Endpunkte geschuetzt werden:

- Authentisierung fuer Projektzugriff, Upload, Loeschen, Taskstart und Approval.
- Rollen oder Policies fuer Viewer, Developer und FPGA-Operator.
- Approval fuer Flashen muss auditierbar sein und darf nicht nur aus einer frei erreichbaren HTTP-Anfrage bestehen.
- CORS/Origin, Requestgroessen, Rate Limits und sensible Logdaten pruefen.
- Dateilesen nur fuer das angeforderte Projekt und erlaubte Artefakte.

**Abnahme:** Nicht authentisierte und falsch autorisierte Requests werden fuer Lesen, Schreiben, Loeschen und Flash-Freigabe abgewiesen.

## P1: Board-, Top-Level- und Constraint-Vertrag

### 1. Ein verbindlicher Hardwarevertrag

Vor Synthese und Flash muessen `DesignState`, FPGA-Registry, Top-Level-VHDL, XDC/Constraints und Hardwaretest dieselben Werte verwenden:

- Board-ID, FPGA-Part und Programmer
- Top-Level-Entity
- Clock-Port, Frequenz und Clock-Domain
- Reset-Port, Polaritaet und Synchronitaet
- alle Top-Level-Ports und Bitbreiten
- Pin-Mapping und I/O-Standards
- erwartetes Kommunikationsprotokoll fuer den Hardwaretest

Unklare oder mehrfach passende Top-Level-Entities muessen blockieren.

### 2. Constraints nicht heuristisch als erfolgreich behandeln

- Nicht gemappte Ports sind ein Fehler, kein Warnhinweis.
- Unbekannte Clock-/Reset-Namen, fehlende Clock-Constraints und falsche Frequenzen blockieren den Lauf.
- Pruefe Vektorbreiten, aktive Reset-Polaritaet, mehrere Clock-Domains und synchronisierte CDC-Uebergaenge.
- Generierte XDC-Dateien muessen als Artefakt versioniert und geprueft werden.
- Automatische LED-/Port-Zuordnung darf nur mit explizitem Boardvertrag erfolgen.
- Ein Bitstream gilt nicht als hardwarebereit, wenn DRC, Timing oder Constraint-Vollstaendigkeit nicht bestanden sind.

**Abnahme:** Tests decken fehlende Ports, falsche Breiten, falsche Polaritaet, fehlende Clock-Constraints, mehrere Clock-Domains, falsches FPGA-Part und mehrdeutige JTAG-Geraete ab.

## P1: Artefakt- und Ergebnisintegritaet

Jeder Agentenschritt und jedes externe Tool muss ein unverwechselbares, persistentes Ergebnis liefern:

- `task_id`, `project_id`, `attempt_id`, Stage und Status
- Toolname, Version, Kommando ohne geheime Argumente
- Start-/Endzeit, Timeout und Returncode
- stdout/stderr als referenziertes Logartefakt
- Input-/Quellhash, Output-/Artefakthashes und Parent-Revision
- erzeugte Dateien mit kanonischen Workspace-relativen Pfaden
- Gate-Entscheidung mit Evidenz und Schwellenwerten

Pruefe vor Nutzung, dass Bitstream, Netlist, Reports und Testlogs existieren, zum aktuellen Source-Hash gehoeren und nicht ausserhalb des Workspace liegen. Ein erfolgreicher Returncode ohne erwartete Artefakte ist `FAILED` oder `BLOCKED`, nicht `PASSED`.

**Abnahme:** Manipulierte, veraltete, fehlende oder fremde Artefakte werden erkannt; ein Bitstream aus einer anderen Source-Revision wird nicht geflasht.

## P2: Toolchain- und Ressourcenverhalten

- GHDL, Vivado, Flash-Tool und Hardwaretreiber muessen vor dem Lauf mit Version und Capability geprueft werden.
- `SKIPPED` ist nur fuer bewusst optionale Gates zulaessig. Ein notwendiges Gate ohne Toolchain ist `BLOCKED`, nicht `PASSED`.
- Timeouts muessen Prozesse und Kindprozesse beenden oder deren Weiterlauf explizit als `ORPHANED` melden.
- stdout/stderr, Arbeitsverzeichnis, Umgebungsrelevantes und Toolversionen muessen reproduzierbar erfasst werden.
- Vivado-Synthese, Place-and-Route und Bitstream muessen dieselbe Registry, dasselbe Part, dieselben Constraints und denselben Top-Level verwenden.
- Ressourcen- und Timinglimits muessen aus Boardprofil und Requirements kommen; keine stillen Defaultwerte.

## P2: Test- und CI-Nachweis

Ergaenze mindestens:

- DI-/Factory-Smoke-Test
- API- und WebSocket-Contract-Tests
- Parallelitaets- und Projektisolations-Tests
- Workspace-Traversal- und Symlink-Tests
- Docker-Fallback- und Containerpfad-Tests
- StateMachine-/Resume-/Idempotenztests
- Top-Level-/XDC-/Clock-/Reset-Contract-Tests
- Artefaktintegritaets- und Source-Hash-Tests
- Prozess-Timeout-/Cancellation-Tests
- Testmatrix ohne GHDL, ohne Vivado und ohne Hardware
- optionale Toolchain- und Hardwaretests mit explizitem `BLOCKED`/`SKIPPED`

Richte eine CI-Pipeline ein, die mindestens Syntax, Unit-Tests, Integrations-Doubles, Sicherheitsgrenzen und Coverage ausfuehrt. Externe Toolchain-Tests werden separat markiert und nicht als bestanden simuliert.

## Abschlusskriterien

Der Folgeauftrag ist erst abgeschlossen, wenn:

1. der aktuelle Teststatus reproduzierbar dokumentiert ist;
2. Zustandsmaschine und DesignState konsistent sind;
3. parallele Projekte isoliert laufen;
4. Filesystem und OpenCode keine Workspace-Grenzen umgehen koennen;
5. API und WebSocket nicht durch EDA-Aufgaben blockieren;
6. Board-, Top-Level-, Clock-, Reset- und Constraint-Vertraege vor Synthese geprueft werden;
7. jedes verwendete Artefakt zur aktuellen Source-Revision gehoert;
8. fehlende Infrastruktur als `BLOCKED`/`SKIPPED` und nicht als falscher Pass gemeldet wird;
9. alle neuen Fehlerfaelle durch automatisierte Tests abgedeckt sind.

Arbeite in kleinen, validierten Schritten. Beginne mit P0-Zustandskonsistenz, Projektisolierung und Workspace-Sicherheit. Fuehre danach API-/Async- und Boardvertrags-Gates ein. Erst wenn diese Grundlagen belastbar sind, erweitere OpenCode-Planung, Report-Parsing und echte Hardwaretests.
