# Änderungsprotokoll des VHDL-Multiagentensystems

Vom ersten Konzept bis zum Stand vom 2026-10-12. Grundlagen: die früheren Konzeptdiagramme in
[`lagacy/`](lagacy/) (dazu `workflow.drawio` aus der Git-Historie), die Commit-Historie und die
Befundliste in [`docs/doku.html`](../doku.html), Abschnitte 15–17 (#1–#45).

Hinweis zur Quellenlage: Für die frühen Phasen (August bis Mitte September) stützt sich das
Protokoll auf Diagramme, Commit-Nachrichten und Dateilisten; die Daten der Konzeptdiagramme
stammen aus Dateizeitstempeln bzw. dem Commit, in dem sie zuerst auftauchen. Ab Oktober sind
die Änderungen in `doku.html` einzeln mit Anlass, Maßnahme und Quelle belegt.

---

## Überblick

| Phase | Zeitraum | Kern |
|---|---|---|
| 0 | Juli/August 2026 | Konzepte: Orchestrator mit Blackboard, mehrere Agenten-Frameworks, lokales Steuermodell mit Lernspeicher |
| 1 | 2026-08-02 | Erste lauffähige Version: Ports-und-Adapter-Architektur, RAG-Pipeline, linearer Zustandsautomat |
| 2 | 2026-08-15 | GHDL-Simulation im Ablauf |
| 3 | 2026-09-13 | Erster vollständiger Durchlauf bis Vivado; Umbau zum Multiagentensystem mit Supervisor |
| 4 | 2026-10-07 | Großer Umbau: RAG entfernt, Gates, TaskGraph, Dashboard, Tests |
| 5 | 2026-10-08/09 | Messung „MAS vs. einzelnes OpenCode“, Analyse #1–#19, Benchmark |
| 6 | 2026-10-10 | Referenzmodell und Mutationsanalyse, Ollama entfernt, Eskalation statt Aufgeben (#20–#27) |
| 7 | 2026-10-10/11 | Echte Läufe am Board decken Systemfehler auf (#28–#42) |
| 8 | 2026-10-11/12 | Letzte Systemfehler (#43–#45), erster vollständiger Lauf ohne Reparatur bis aufs Board, Dokumentation |

---

## Phase 0 – Konzepte (vor der ersten Version)

### Konzept 1: Orchestrator mit Blackboard ([`lagacy/Architekturüberblick.drawio.png`](lagacy/Architekturüberblick.drawio.png))

- Dashboard → **Orchestrator / Blackboard** als zentrale Ablage, an die alle Agenten angebunden sind.
- Agenten aus verschiedenen Welten: **Hermes** und **OpenCode** in einem **Docker**-Container,
  dazu ein **LangChain-Agent** und **CrewAI**.
- Idee: Orchestrierungsansätze vergleichen (so auch das erste README: „unterschiedliche
  Orchestrierungsansätze untersuchen und hinsichtlich Skalierbarkeit, Fehlertoleranz,
  Wartbarkeit und Sicherheit bewerten“).

### Konzept 2: Lokales Steuermodell mit Lernspeicher ([`lagacy/Grapische_arch.drawio`](lagacy/Grapische_arch.drawio), Seite 2)

- Ein **lokales Modell (1–7 B Parameter)** nimmt den Benutzer-Prompt an, legt den Projektordner
  an und steuert den Ablauf.
- **OpenCode** erzeugt VHDL und Testbench, simuliert mit GHDL und erstellt bei einem Fehlschlag
  eine Fehlerbeschreibung, die an den ursprünglichen Prompt angehängt wird (einfache
  Reparaturschleife).
- Nach Erfolg: Synthese- und Flash-Werkzeuge (Vivado) aufs FPGA.
- **Lernschleife:** OpenCode schreibt „Gelerntes aus dem erfolgreichen Lauf“ in `memory.md`,
  das in künftige Prompts einfließt.

**Was daraus wurde:** Docker-Isolation, Hermes, LangChain und CrewAI wurden nicht weiterverfolgt.
Docker ist zurückgestellt, bis das MAS einen einzelnen OpenCode-Lauf schlägt (#15). Das lokale
Steuermodell (Ollama) gab es bis 2026-10-10. Die Fehler-in-den-Prompt-Schleife lebt als
Reparaturauftrag mit Kernzeilen und Versuchsverlauf weiter (#31, #32). Die Lernschleife über
`memory.md` ist nicht umgesetzt: `ProjectMemoryService` existiert, schreibt aber nichts Gelerntes.

---

## Phase 1 – Erste lauffähige Version (2026-08-02)

Commits `bb5e68c` („Erste lauffähige version“, 91 Dateien) bis `b0e720e`.

- **Ports-und-Adapter-Architektur** („hexagonal“): `domain/ports` (Schnittstellen), `services`,
  `infrastructure`, Fachdomäne unter `domains/vhdl`.
- **RAG-Pipeline** (`infrastructure/rag`): Wissenssuche über Dokumente vor der Erzeugung.
- Ollama als lokale Sprachmodell-Laufzeit; OpenCode als ausführender Code-Agent.
- **Linearer Zustandsautomat** (`workflow.drawio`, im Arbeitsverzeichnis gelöscht, abrufbar mit `git show 82431d7:docs/architecture/workflow.drawio`):
  `CREATED → ANALYZING → RAG_SEARCH → GENERATING_ARTIFACTS → WORKSPACE_READY → RUNNING_AGENT →
  TESTING → COMPLETED`, mit Seitenzweigen `REPAIRING`, `VALIDATING`, `FAILED`.
  Es gab genau einen Agentenlauf; „Multiagent“ war noch nicht umgesetzt.
- Am selben Tag: `pyproject.toml`, Projektstruktur, Frontend-Korrekturen.

## Phase 2 – GHDL-Simulation (2026-08-15/16)

Commit `45880f0`: „ghdl simulation nun möglich“. Erzeugter Code wird erstmals automatisch
simuliert; Grundlage für die spätere Reparaturschleife.

## Phase 3 – Erster vollständiger Durchlauf und Umbau zum MAS (2026-09-13)

- `a37f1c3` „Erster vollständiger durchlauf“: erstmals bis Vivado (Synthese-Artefakte liegen
  versehentlich im Repo).
- `7e20a4f` „Vollständiger durchlauf und korrekturen“ (107 Dateien): **Einführung der Agenten**
  unter `src/agents/`: SupervisorAgent (922 Zeilen), ArchitectureAgent, HDLAgent,
  VerificationAgent, DebugAgent, FPGAAgent, HardwareTestAgent, dazu `domain/agents/base.py`.
  Aus dem linearen Ablauf wird eine Phasensteuerung durch den Supervisor.

## Phase 4 – Großer Umbau (2026-10-07)

Commit `82431d7` (211 Dateien, +24 944/−10 316 Zeilen). Den Stand zeigen die beiden damals
aktuellen Diagramme:

**[`lagacy/aktuelle_arch.drawio`](lagacy/aktuelle_arch.drawio) – „Aktuelle Produktionsarchitektur“**

- Dashboard/CLI → FastAPI → **SupervisorOrchestrator** → **SupervisorAgent** (Phasensteuerung,
  Fehlerbehandlung) → Projekt-Workspace (`design_state.yaml`, `task_graph.json`).
- **OllamaLLMService** nur für Text: Projektname, Analyse, Architektur, Diagnose.
- ArchitectureAgent erzeugt die Architektur als YAML/Text; **DebugAgent** diagnostiziert per LLM.
- HDLAgent → OpenCode CLI; **DeterministicDesignService** als Ersatz bei leerer OpenCode-Ausgabe.
- GHDLValidator → VerificationAgent; FPGAAgent → Vivado; Flash über Vivado oder openFPGALoader.
- Notiz im Diagramm: HardwareTestAgent existiert, wird nach dem Flash aber nicht gestartet.

**[`lagacy/aktuelle_arch.drawio`](lagacy/aktuelle_arch.drawio) Seite 2 und [`lagacy/Grapische_arch.drawio`](lagacy/Grapische_arch.drawio) Seite 1 – Produktionsablauf**

- Neues Projekt: Name über **Ollama** (`generate_project_name()`).
- Phasen: ANALYZING (Ollama) → ARCHITECTING (YAML vom LLM, deterministischer Fallback) →
  **UART_INTEGRATION verbindlich** (UART-Modul in jedem Projekt) → IMPLEMENTING (TaskGraph) →
  STATIC_CHECK → SIMULATING → VALIDATING → SYNTHESIZING → FPGA_PROGRAMMING → COMPLETED.
- Ein gemeinsamer Fehlerpfad: gleicher Fehler schon einmal? → Abbruch; sonst DebugAgent
  (LLM-Diagnose) → Infrastrukturfehler? → BLOCKED; sonst `HDLAgent._fix_hdl()` → Datei geändert
  und Limits übrig? → erneut simulieren, sonst FAILED.
- Notiz: `memory.md` ist kein Lern-Schritt; der Supervisor schreibt dort nichts.

Inhaltlich in diesem Commit: **RAG-Pipeline entfernt** (alle Sprachmodell-Aufgaben über
OpenCode), Gates mit Contracts, Abdeckung und Timing, persistierter TaskGraph mit Parallelität,
Freigabe vor dem Flashen an den Bitstream gebunden, Dashboard, rund 40 neue Testdateien
(Abschnitte 1–14 in doku.html; die damalige Bewertung `multi-agent-goal-assessment.md` steht in der Git-Historie).

## Phase 5 – Messung und Analyse (2026-10-08/09)

Commits `73769ce`, `f746f15`, `ff3c9b4`.

- **Leitfrage:** Warum blieb das MAS hinter einem einzelnen OpenCode-Lauf mit demselben Modell
  zurück? Benchmark `mas_vs_single` mit eigenen Prompts und unabhängigen Referenz-Testbenches.
- **Analyse #1–#19** (doku.html, Abschnitt 15): Die Worker prüften ihr Ergebnis nicht selbst,
  kannten die Abnahmeregeln des Validators nicht, bekamen widersprüchliche Interfaces und nur
  zerstückelten Kontext. UART wurde in jedes Projekt eingebaut, das Top-Level doppelt beauftragt,
  ungeprüfte Fallback-Vorlagen eingesetzt. Es gab mehr Aufrufe als nötig (Rate-Limits), falsche
  Regex-Klassifikation, vorzeitige Modellabbrüche, OpenCode im falschen Verzeichnis.
- **Maßnahmen:** GHDL-Selbstprüfung in jedem Auftrag, Testbench-Regeln, Entities der Nachbarmodule
  im Auftrag, UART nur bei Bedarf, Modus `single_session`, Benchmark-Methodik mit
  Provider-Prüfung und Archivierung der Läufe.
- Einbindung des Benchmarks `small_vhdl_bench` (10 Aufgaben, offizielle Arty-S7-Pins).

## Phase 6 – Verifikation und Ausdauer (2026-10-10)

Commits `1baea08`, `d6091af`.

- **Maßnahme A – Referenzmodell:** Ein Python-Modell aus PROMPT.md, vor der Implementierung
  erzeugt, wird Takt für Takt mit dem Entwurf verglichen (differentieller Test).
- **Maßnahme B – Mutationsanalyse:** Prüft, ob die Testbenches absichtlich fehlerhafte Varianten
  erkennen.
- **Ollama vollständig entfernt (#22):** Namen und Chat laufen über OpenCode; ein zweites
  Sprachmodell ist nicht mehr nötig. Damit ist das „lokale Steuermodell“ aus Konzept 2 entfallen.
- Weitere Korrekturen: zu strenge Planprüfung (#20), XDC-Erzeugung (#21), Race Condition auf
  `design_state.yaml` (#23), Vivado-Pfad (#24), verworfene Ereignisse (#25).
- **Planwiederholung mit Korrekturauftrag (#26)** statt Abbruch bei ungültigem Plan.
- **Eskalation statt Aufgeben (#27):** Leiter Reparatur → Modul neu → Architektur neu →
  Fallback-Modell → Mensch; Richtlinie `persistent` (echte Läufe) bzw. `standard` (Benchmark).
  Damit ersetzt eine abgestufte Strategie den alten Fehlerpfad „gleicher Fehler → Abbruch“.

## Phase 7 – Echte Läufe am Board (2026-10-10/11)

Commit `4a16216` (#28–#42). Läufe mit traffic-light, gray-countdown und led-pattern-display
zeigten vor allem Fehler im System selbst:

- **#28:** GHDL-Synthese ohne `--std=08`; Regressionsschutz (verschlechternde Reparaturen werden
  zurückgenommen); Zeitlimit als Eskalationsschritt.
- **#29 – Einzelanforderungen:** Der Plan listet jede Anforderung mit wörtlichem Zitat, Modulen
  und Ports. Testbenches kennzeichnen Prüfungen mit `REQ Rn`, ein Gate prüft das. Jeder Auftrag
  erhält die Anforderungen. Eine unabhängige Abschlussprüfung bewertet sie am Schluss.
- **#30:** Board-Konfiguration (`SPI_BUSWIDTH 4`) immer im Vivado-Build.
- **#31 – Vorfilter (Triage):** Kernzeilen aus der Werkzeugausgabe, Herkunft des Fehlers, Module
  nur über Dateiverweise. Ersetzt die reine LLM- bzw. Regex-Diagnose des alten Fehlerpfads.
- **#32:** Eskalationsleitern je Herkunft. Die nächste Stufe folgt sofort, ohne Pipeline-Neustart;
  jede Stufe kennt die bisherigen Versuche.
- **#33–#35:** Testbench-Reparatur über Dateien statt Konsolenausgabe, Synthese-Cache,
  Phasenwechsel ohne stilles Springen, Reset-Konzept im Plan.
- **#36 – Benutzerfreigabe vor dem Flashen entfernt:** Das System arbeitet bis aufs Board autonom.
- **#37:** OpenCode endet, sobald das Ergebnis vollständig ist.
- **#38:** Board-Wissen nach der offiziellen Master-XDC korrigiert; jeder Pin wird nur einmal vergeben.
- **#39/#40:** Generic-Vertrag zwischen Referenzmodell und Vergleichs-Testbench. Strukturierter
  Befund jeder Reparatur (`repair_verdict.json`); bei begründetem Modellstreit wird der
  Vergleichstest abgeschaltet statt den Entwurf zu zerreparieren.
- **#41:** Eigenes Git-Repo je Workspace, damit OpenCode nicht im System-Repo arbeitet.
- **#42:** Projektzustand von 1,27 MB auf rund 100 KB, Laden/Speichern von 6,7 s auf unter 0,2 s.

## Phase 8 – Abschluss der Fehlerkette und Dokumentation (2026-10-11/12)

Commits `63a4752`, `943b9dd`, `fbacfdc`.

- **#43:** OpenCode-Aufrufe erscheinen im Dashboard.
- **#44:** Das Top-Level wird an die Synthese übergeben. Vorher scheiterte jeder Entwurf mit
  mehreren Modulen an Vivado.
- **#45:** Vivado liest VHDL-2008; die XDC entsteht nur aus den Ports des Top-Levels.
- **Erster vollständiger Lauf ohne Reparatur:** `led-patterns-display-5816ba` (muse-spark-1.3).
  7 Module, 39 Anforderungen erfüllt, Mutationsquote 1,0, Timing erfüllt (WNS +5,97 ns), Board
  geflasht, 9 Schritte.
- **Dokumentation:** UML-Modell ([MAS-UML.md](MAS-UML.md)), Ablauf als Mermaid
  ([MAS-Ablauf.md](MAS-Ablauf.md)) und draw.io ([MAS-Ablauf.drawio](MAS-Ablauf.drawio)).
  Die bisherigen Diagramme liegen in `lagacy/`.
- **#46:** Lauf-Trajektorien als Trainingsdaten unter `~/vhdl-agent-runs/`, außerhalb des
  Workspaces. Werkzeugausgaben sind per `.gitignore` von OpenCodes Suche ausgeschlossen und werden
  nach erfolgreichem Lauf aufgeräumt.

---

## Konzept damals → Stand heute

| Thema | Frühere Konzeption (`lagacy/`) | Stand 2026-10-12 |
|---|---|---|
| Steuerung | Orchestrator/Blackboard bzw. lokales Modell (1–7 B) | SupervisorAgent mit festen Phasen und Gates; Orchestrator für Projekte und Threads |
| Sprachmodelle | Ollama lokal + OpenCode; LangChain, CrewAI, Hermes geplant | nur OpenCode (freie Zen-Modelle), Fallback-Modell in der Eskalation |
| Wissen | RAG-Pipeline, `memory.md` als Lernspeicher | Skills und Board-Daten je Workspace; kein Lernspeicher |
| Ablauf | linearer Zustandsautomat mit RAG_SEARCH | Analyse → Architektur → (UART) → Referenzmodell → Implementierung (TaskGraph, parallel) → Prüfungen → Synthese → Flash → (Hardwaretest) |
| Planung | Architektur als YAML/Text vom LLM, deterministischer Fallback | OpenCode-Manifest mit Ports, Generics, Reset-Konzept und Einzelanforderungen; Prüfung mit Korrekturschleife |
| UART | in jedem Projekt verbindlich | nur bei Bedarf |
| Verifikation | GHDL-Simulation | Port-Contracts, Testbenches, Referenzmodell mit Generic-Vertrag, Mutationsanalyse, REQ-Gate, Abschlussprüfung |
| Fehlerbehandlung | gleicher Fehler → Abbruch; LLM-Diagnose; HDL-Patch | Vorfilter (Kernzeilen, Herkunft) → zuständige Rolle → Eskalationsleiter je Herkunft → strukturierter Befund, Rücknahme bei Verschlechterung |
| Menschliche Eingriffe | Freigabe vor dem Flashen | keine Freigabe; Mensch nur, wenn die Leiter erschöpft ist oder Werkzeug/Board fehlen |
| Isolation | Docker geplant | nativ mit Verzeichnissperre und eigenem Git-Repo je Workspace; Docker zurückgestellt |
| Hardware | Flash, Hardwaretest nicht angebunden | Flash mit korrekter Board-Konfiguration; Hardwaretest nur mit echter UART |

---

## Noch offen

- Lernspeicher (`memory.md`) aus Konzept 2 ist nicht umgesetzt.
- Docker-Isolation zurückgestellt (#15).
- Hardwaretest nur mit echter UART-Schnittstelle; ohne sie wird kein Erfolg gemeldet.
- HDL-Reparatur noch nicht über den Task-Runner mit Skills (#9).
- UART- und Pmod-Pins im Board-Wissen ungeprüft (#38).
- Neue Benchmark-Messung MAS vs. einzelnes OpenCode mit dem aktuellen Stand.
