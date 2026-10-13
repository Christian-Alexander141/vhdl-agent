# LLM-basierte autonome Agentenplattform zur Software- und Systemartefakterzeugung



## Übersicht

Dieses Projekt untersucht und implementiert eine Umgebung zur autonomen Erzeugung komplexer Software- und Systemartefakte mithilfe LLM-basierter Agenten.

Ziel ist die Entwicklung einer sicheren, modularen Agentenarchitektur, welche mehrere spezialisierte Agenten zur Bearbeitung komplexer Aufgaben koordinieren kann. Dabei werden unterschiedliche Orchestrierungsansätze untersucht und hinsichtlich Skalierbarkeit, Fehlertoleranz, Wartbarkeit und Sicherheit bewertet.

Der Fokus liegt auf einer Architektur, die autonome Softwareentwicklung ermöglicht, gleichzeitig aber Risiken durch unkontrollierte Agentenausführung reduziert.

---

# Zielsetzung

## Lokaler OpenCode-Testmodus

Für Entwicklung auf Rechnern mit begrenzten Ressourcen kann OpenCode ohne Docker
ausgeführt werden. Der Modus ignoriert `opencode.use_docker` und verwendet direkt
das lokale `opencode`-Binary:

```bash
VHDL_AGENT_TEST_MODE=1 python3 start.py
```

Alternativ kann er in `config.yaml` mit `opencode.test_mode: true` aktiviert oder
beim direkten CLI-Start mit `--test-mode` gesetzt werden. Für den API-/Dashboard-
Start wird der Schalter an den Server-Prozess weitergereicht.

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

## Ollama

:contentReference[oaicite:0]{index=0} wird als lokale Laufzeitumgebung für Large Language Models verwendet.

Ollama ermöglicht:

- lokale Ausführung verschiedener Sprachmodelle
- Nutzung ohne Übertragung sensibler Daten an externe Dienste
- einfache Verwaltung verschiedener Modelle
- Integration in lokale Agentensysteme

Alternativ bietet Ollama eine Cloud-Schnittstelle mit umfangreichen kostenlosen Nutzungsmöglichkeiten.

Ein wesentlicher Vorteil besteht darin, dass Interaktionen mit lokalen Modellen nicht zur Modellweiterentwicklung verwendet werden.

---

## Docker

:contentReference[oaicite:1]{index=1} wird zur Containerisierung und Isolation der Agentenumgebung eingesetzt.

Vorteile:

- Trennung des Agenten vom Hostsystem
- reproduzierbare Umgebungen
- einfache Bereitstellung vorkonfigurierter Agenten
- geringerer Ressourcenverbrauch gegenüber vollständigen virtuellen Maschinen

Docker stellt damit einen Kompromiss zwischen Sicherheit und Bedienkomfort dar.

---

## Next.js / React

Die Benutzeroberfläche wird mit Next.js und React umgesetzt.

Einsatzbereiche:

- Dashboard zur Steuerung des Systems
- Darstellung von Agentenzuständen
- Anzeige von Ergebnissen und Zwischenständen
- Benutzerinteraktion mit dem Orchestrator

---

## Hermes Agent

Hermes ist ein autonomer Agent zur Durchführung komplexer Aufgaben.

Der Agent kann:

- Aufgaben analysieren
- Werkzeuge verwenden
- Dateien bearbeiten
- Softwareartefakte erzeugen

Aufgrund seiner Autonomie wird Hermes isoliert innerhalb eines Containers ausgeführt.

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

# Ablauf in der Workflow.py 
<img width="1096" height="2441" alt="grafik" src="https://github.com/user-attachments/assets/be7d02e9-cea4-47d5-8e42-095f5f8732a3" />
