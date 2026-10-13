# LLM-basierte autonome Agentenplattform zur Software- und Systemartefakterzeugung



## Übersicht

Dieses Projekt untersucht und implementiert eine Umgebung zur autonomen Erzeugung komplexer Software- und Systemartefakte mithilfe LLM-basierter Agenten.

Ziel ist die Entwicklung einer sicheren, modularen Agentenarchitektur, welche mehrere spezialisierte Agenten zur Bearbeitung komplexer Aufgaben koordinieren kann. Dabei werden unterschiedliche Orchestrierungsansätze untersucht und hinsichtlich Skalierbarkeit, Fehlertoleranz, Wartbarkeit und Sicherheit bewertet.

Der Fokus liegt auf einer Architektur, die autonome Softwareentwicklung ermöglicht, gleichzeitig aber Risiken durch unkontrollierte Agentenausführung reduziert.

---

# Zielsetzung

## Agenten-Ausführung: Docker (produktiv) und Testmodus

Die OpenCode-Agenten laufen **produktiv immer isoliert in Docker**. Einstellbar ist
alles im Dashboard unter *Einstellungen → Agenten-Ausführung* (gespeichert in
`config.yaml`, Abschnitt `opencode`):

| Einstellung | Bedeutung |
|---|---|
| Ausführungsmodus | Docker (Standard) oder nativ – nativ nur als Testmodus |
| Isolation `per_task` (Standard) | Jeder Auftrag startet einen eigenen Container (`docker run --rm`), eingebunden ist **nur** das Projektverzeichnis; ohne Capabilities, ohne Rechteausweitung, als Host-Benutzer |
| Isolation `shared` | `docker exec` in einen laufenden Container (`docker compose up -d opencode`), der nur `./projects` sieht |
| Image, Netzwerk, Speicher-/CPU-Limit | Container-Parameter für `per_task` |
| Zugangsdaten | Host-Verzeichnis der OpenCode-Zugangsdaten, wird schreibgeschützt eingebunden |

Ist Docker nicht verfügbar, bricht der Auftrag mit einer Infrastruktur-Meldung ab.
Es gibt **keinen** stillen Rückfall auf die Ausführung auf dem Host.

### Testmodus (ohne Docker)

Für Entwicklungsrechner, die für Docker zu leistungsschwach sind, führt der
Testmodus OpenCode direkt auf dem Host aus. Die Agenten haben dann Zugriff auf
alle Dateien des Benutzers – nicht für Produktivumgebungen verwenden.

```bash
python3 start.py --test-mode          # oder: VHDL_AGENT_TEST_MODE=1 python3 start.py
```

Alternativ dauerhaft über das Dashboard oder `opencode.test_mode: true`.

Meldet OpenCode das Kontingent des aktuellen Providers, wird der Lauf einmal mit
`opencode.fallback_model` wiederholt.

### Modell- und Fallback-Modell wählen

`opencode.model`/`opencode.fallback_model` sind Freitext – der String geht
unverändert als `--model <wert>` an OpenCode. Eine Verwechslung fällt daher
nicht beim Speichern auf, sondern erst beim nächsten Agentenlauf, oft mit
einer irreführenden generischen Providermeldung statt "model not found".
Besonders leicht übersehen: Kostenlose Modelle bei OpenCode tragen das Suffix
`-free` (`opencode/nemotron-3.5-lightning-free`); ohne diesen Zusatz greift
ein kostenpflichtiges Modell, das ohne Guthaben fehlschlägt.

Im Dashboard unter *Einstellungen → OpenCode-Modelle* lädt der Button
„Modelle laden" die tatsächlich verfügbaren Modelle (`opencode models`,
gruppiert nach Provider) in ein Dropdown über jedem Textfeld; eine Auswahl
übernimmt den exakten Bezeichner ins Textfeld. Der aktuell konfigurierte Wert
bleibt als Option erhalten, auch wenn er nicht in der Liste auftaucht – so
geht bei einem Listing-Fehler kein gültiger, nur gerade nicht gemeldeter Wert
verloren. Das Laden kann bei kaltem Cache von OpenCode selbst 10-20s dauern.

Moderne Large Language Models ermöglichen die Entwicklung autonomer Agentensysteme, welche nicht nur Texte erzeugen, sondern komplexe Aufgaben planen, Werkzeuge verwenden und Ergebnisse überprüfen können.

Für die Erzeugung komplexer Softwareartefakte entstehen jedoch besondere Anforderungen:

- Zerlegung komplexer Aufgaben in Teilaufgaben
- Koordination verschiedener Spezialagenten
- Verwaltung von Zwischenzuständen
- Fehlererkennung und Wiederherstellung
- Nachvollziehbarkeit der Entscheidungen
- Sichere Ausführung nicht vollständig deterministischer Systeme

Dieses Projekt untersucht verschiedene Agentenarchitekturen und entwickelt eine geeignete Umgebung für deren praktischen Einsatz.

---

# Verwendete Technologien

## OpenCode

Alle Sprachmodell-Aufgaben laufen über OpenCode: Planung (inklusive Projekt- und Modulnamen), VHDL-Module, Testbenches, Referenzmodelle, Reparaturen und die Beantwortung von Projektfragen im Chat. Welches Modell verwendet wird, wird in den Einstellungen unter OpenCode festgelegt (z. B. die kostenlosen Modelle von OpenCode Zen).

Ein separates Sprachmodell über Ollama, ein Relikt der früheren RAG-Pipeline, wurde entfernt (2026-10-10).

---

## Docker

Docker wird zur Containerisierung und Isolation der Agentenumgebung eingesetzt.

Vorteile:

- Trennung des Agenten vom Hostsystem
- reproduzierbare Umgebungen
- einfache Bereitstellung vorkonfigurierter Agenten
- geringerer Ressourcenverbrauch gegenüber vollständigen virtuellen Maschinen

Docker stellt damit einen Kompromiss zwischen Sicherheit und Bedienkomfort dar.

---

## Dashboard

Das Dashboard (`Schaltungsagent/src/dashboard/`, HTML/CSS/JavaScript ohne Build-Schritt)
wird vom FastAPI-Server ausgeliefert und zeigt Ablauf, Agenten-Chat, Ereignisse,
Projekte und alle Einstellungen.

---

## OpenCode

OpenCode dient als Entwicklungsagent für Softwareaufgaben.

Funktionen:

- Codeanalyse
- Codegenerierung
- Änderungen an Projekten
- Unterstützung bei Entwicklungsprozessen

---

# Architektur

## Anforderungen

Die Architektur muss folgende Anforderungen erfüllen:

| Anforderung | Beschreibung |
|-|-|
| Modularität | Einfache Erweiterung durch zusätzliche Agenten |
| Sicherheit | Isolation autonomer Komponenten |
| Fehlertoleranz | Wiederaufnahme nach Fehlern |
| Nachvollziehbarkeit | Speicherung von Entscheidungen und Ergebnissen |
| Skalierbarkeit | Unterstützung mehrerer spezialisierter Agenten |
| Flexibilität | Kombination verschiedener Agentenframeworks |

---

# Vergleich möglicher Agentenarchitekturen

## Hierarchische Subagenten (Orchestrator-Worker)

Bei dieser Architektur übernimmt ein zentraler Orchestrator die Planung und Delegation von Aufgaben.
<img width="479" height="361" alt="grafik" src="https://github.com/user-attachments/assets/90c2a4a1-f3da-4cdb-adca-167ac17ca3ca" />

### Gates, Reparaturrouting und Hardwaretests

Der Supervisor lässt eine Phase nur weiterlaufen, wenn ihr Gate bestanden ist:

| Phase | Gate |
|---|---|
| Analyse | Ziel-FPGA aus der Anforderung bestimmt (`fpga_target.py`); widersprüchliche Angaben → Rückfrage |
| Implementierung | Persistierter TaskGraph (`task_graph.json`); unabhängige Module laufen parallel, Checkpoint nach jedem Batch |
| Statischer Check | Architektur-Contracts (Ports, Richtung, Typ, Bitbreite, Top-Level) + GHDL-Analyse |
| Validierung | Simulation bestanden, Ergebnis gehört zur aktuellen Architekturversion, jedes Modul von einer Testbench erreicht |
| Synthese | Vivado-Reports vorhanden, Clock-Constraint gesetzt, WNS/WHS ≥ 0, Auslastung ≤ 100 % |
| Flash | Ohne Benutzerfreigabe; das Build-Skript setzt die Konfigurationsspeicher-Einstellungen des Boards (z. B. `SPI_BUSWIDTH 4`) immer |
| Hardwaretest | Nur mit echter UART-Schnittstelle; ohne sie wird kein Erfolg gemeldet |

Jeder Fehler läuft zuerst durch den Vorfilter (`src/domain/agents/triage.py`): Er holt die Kernzeilen aus der GHDL-/Vivado-Ausgabe, bestimmt die Herkunft (Entwurf, Testbench, Anforderungen, Werkzeug/Konfiguration, Hardware, Infrastruktur) und ordnet Module nur über belegbare Dateiverweise zu. Danach gibt der Supervisor ihn nach `src/domain/agents/repair_routing.py` an die zuständige Rolle: Interfacefehler zwischen contract-treuen Modulen an den ArchitectureAgent, Modul- und Contractfehler an den HDLAgent, Test- und Abdeckungslücken an den VerificationAgent, Synthese-, Timing-, Constraint- und Bitstream-Konfigurationsfehler an die FPGA-Reparatur; fehlende Werkzeuge und Board-/Kabelprobleme an den Benutzer.

Konfiguration (`config.yaml`):

```yaml
limits:
  max_parallel_workers: 2        # 1 = sequentiell (schont lokales OpenCode)
gates:
  min_module_coverage: 1.0       # Anteil der Module, die simuliert werden müssen
  enforce_contracts: true
  require_timing_closure: true
hardware_test:
  uart_port: "/dev/ttyUSB1"      # leer = kein Hardwaretest, kein Hardware-Erfolg
  baudrate: 115200
```

Projektspezifische Hardware-Testvektoren kommen aus dem Plan-Manifest (`hardware_tests`) oder aus `tests/hardware_tests.yaml` im Projekt:

```yaml
tests:
  - name: cpu_add
    type: cpu_program          # oder uart_exchange / echo
    program: "01 05 02 03 0A FF"
    expected: "08"
    requirement: "ALU addiert"
```

# Ablauf in der Workflow.py 
<img width="1096" height="2441" alt="grafik" src="https://github.com/user-attachments/assets/be7d02e9-cea4-47d5-8e42-095f5f8732a3" />
