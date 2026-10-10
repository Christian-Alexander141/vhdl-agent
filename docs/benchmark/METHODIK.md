# Benchmark: Multi-Agenten-System vs. einzelnes OpenCode

Dieser Ordner enthält Methodik und Ergebnisse des Vergleichs zwischen dem Multi-Agenten-System (MAS) des Schaltungsagenten und einem einzelnen OpenCode-Lauf. Die Messung soll klären, ob das MAS bei VHDL-Entwurfsaufgaben bessere Ergebnisse liefert als ein einzelner Agent mit demselben Sprachmodell. Davon hängt ab, ob die Docker-Isolation für den Produktivbetrieb weiterverfolgt wird (siehe `docs/doku.html`, Abschnitt 15).

```
docs/benchmark/
├── METHODIK.md                      dieses Dokument
└── ergebnisse/
    ├── <Lauf-ID>/                   ein Benchmark-Lauf (Zeitstempel)
    │   ├── meta.json                Aufruf, Modell, Werkzeugversionen, Code-Stand, Prüfsummen
    │   ├── results.csv              eine Zeile je Einzellauf (nach jedem Lauf geschrieben)
    │   └── summary.json             Erfolgsquoten, Dauer, Fehlerkategorien je Variante
    └── 20261008-121802-abgebrochen/ abgebrochener Vorlauf (älterer Code-Stand, siehe HINWEIS.md)
```

Werkzeug: `Schaltungsagent/benchmark/mas_vs_single.py`. Prompts: `Schaltungsagent/benchmark/prompts/`. Referenz-Testbenches: `Schaltungsagent/benchmark/reference/`. Die Arbeitsverzeichnisse der Läufe (generierter Code, Logs, Zwischenstände) liegen nicht im Repo, sondern unter `~/vhdl-agent-benchmark/<Lauf-ID>/`; der Pfad steht in `meta.json`.

## 1. Fragestellung

Erzeugt das MAS bei gleichem Sprachmodell häufiger einen spezifikationsgerechten VHDL-Entwurf als ein einzelner OpenCode-Lauf, und zu welchem Zeitaufwand?

## 2. Varianten

| Variante | Ablauf |
|---|---|
| `single` | Ein OpenCode-Aufruf erhält `PROMPT.md` und eine kurze Arbeitsanweisung: Quellen unter `src/`, Testbench unter `tests/`, Selbstprüfung mit GHDL. Keine Planung, keine Gates, keine Reparaturschleife. |
| `mas` | Vollständiges MAS mit modularer Implementierung: Plan/Manifest, Architektur, ein Worker je Modul und je Testbench (TaskGraph, parallel), Gates (Contracts, GHDL, Coverage, Golden-Vektoren), Debug-Agent und Reparatur. |
| `mas-single` | Wie `mas`, aber die Implementierung erfolgt in **einer** OpenCode-Sitzung für das ganze Projekt (`opencode.implementation_mode: single_session`). Planung, Gates und Reparatur bleiben gleich. |

Synthese, Flash und Hardwaretest sind bei allen Varianten abgeschaltet (`synthesis.enabled: false`). Verglichen wird die Simulationsreife.

## 3. Konstante Bedingungen

- **Gleiches Modell und gleiche Werkzeuge:** Alle Varianten nutzen `opencode.model` aus `config.yaml`, dieselbe OpenCode- und GHDL-Version (in `meta.json`) und dasselbe Zeitlimit pro OpenCode-Aufruf.
- **Gleiche Testbench-Regeln:** Alle Varianten erhalten dieselben Abnahmeregeln für Testbenches (`TESTBENCH_RULES`: Simulationsende vor 1&nbsp;ms, Marker `TB_COMPLETE`, Prüfungen mit `severity error`). Auch der Einzellauf kennt also die Kriterien, nach denen bewertet wird.
- **Native Ausführung:** OpenCode läuft direkt auf dem Host (Projektentscheidung, siehe Doku #1/#15). Jeder Aufruf erhält im Workspace eine `opencode.json` mit `external_directory: deny`, und `$PWD` wird auf den Workspace gesetzt (Doku #16/#17).
- **Workspaces außerhalb des Repos:** Innerhalb eines Git-Repos betrachtet OpenCode das ganze Repo als Projekt und kann es lesen und verändern. Der Benchmark verweigert deshalb Ablageorte innerhalb eines Git-Repos.
- **Frische Konfiguration je Lauf:** Kein Zustand wird zwischen Läufen übernommen.

## 4. Aufgaben (Prompts)

| Prompt | Umfang | Was er prüft |
|---|---|---|
| `01_counter` | ein sequenzielles Modul | Grundfähigkeit: synchroner Reset, Enable, Überlauf |
| `02_hamming_decoder` | ein kombinatorisches Modul | exakte Bitreihenfolge, Paritätslogik, Fehlerkorrektur |
| `03_ampel` | drei Module (Timer, Moore-Automat, Top-Level) | Hierarchie, Schnittstellen zwischen Modulen, Zeitverhalten; hier sollte ein MAS seine Stärken zeigen |

Alle Prompts legen Entity-Namen, Ports und Dateien fest, damit die Ergebnisse gegen eine Referenz geprüft werden können. Prüfsummen der Prompt-Dateien stehen in `meta.json`.

## 5. Ablauf und Reihenfolge

Ein Lauf besteht aus `--repeat` **Runden**. In jeder Runde wird jeder Prompt in jeder Variante genau einmal ausgeführt, in der Reihenfolge `--prompt-files` × `--variants`.

Weil die Varianten innerhalb jeder Runde abwechseln, wirken sich zeitabhängige Einflüsse des Modell-Providers (Rate-Limits, Last, Tageszeit) auf alle Varianten ähnlich aus. Bricht ein Lauf ab, sind die bis dahin erhobenen Daten trotzdem ausgewogen. Jede Zeile wird sofort nach dem Einzellauf in `results.csv` geschrieben.

Gemessen wird die Wanduhrzeit vom Start der Variante bis zum Ende ihres letzten Agentenschritts, ohne die anschließende Bewertung.

**Provider-Prüfung:** Vor jedem Einzellauf geht eine kurze Testanfrage an das Modell („Antworte nur mit dem Wort OK.“). Ist der Provider nicht erreichbar, wartet der Benchmark in 10-Minuten-Schritten bis höchstens `--max-provider-wait` Minuten (Standard 120) und beendet sich dann sauber; `meta.json` vermerkt den Abbruch. Nach jedem Lauf wird erneut geprüft (`provider_ok_after`). Ein fehlgeschlagener Lauf, nach dem der Provider nicht erreichbar ist, gilt als **ungültig** (`valid = False`): Er misst den Ausfall, nicht die Variante. `summary.json` rechnet Quoten nur über gültige Läufe und weist die ausgeschlossenen aus (`invalid_runs_excluded`).

## 6. Bewertung

Jeder Einzellauf wird zweifach bewertet:

1. **Eigene Testbench (`passed`).** Der `GHDLValidator` der Pipeline analysiert und elaboriert alle Quellen und simuliert jede `tests/*_tb.vhd` mit `--stop-time=1ms --assert-level=error`. Bestanden heißt: keine Fehler, keine fehlgeschlagene Assertion, Marker `TB_COMPLETE` vorhanden, mindestens eine Assertion. Das entspricht dem Kriterium, nach dem das MAS selbst arbeitet. Es hat aber eine Schwäche: Das System bewertet sich mit seiner eigenen Testbench. Eine zu schwache Testbench lässt auch einen falschen Entwurf bestehen; eine fehlerhafte Testbench lässt einen korrekten Entwurf scheitern.
2. **Unabhängige Referenz-Testbench (`ref_passed`, Hauptkriterium).** Für jeden Prompt gibt es eine vorab geschriebene Referenz-Testbench (`benchmark/reference/<prompt>_ref_tb.vhd`), die das System nie zu sehen bekommt. Sie wird nur gegen die erzeugten Quellen `src/*.vhd` simuliert; die vom System geschriebenen Testbenches spielen dabei keine Rolle. Die Kompilierreihenfolge bestimmt GHDL selbst (`ghdl -i`/`-m`). Bestanden heißt: Simulation endet mit Exit-Code 0, gibt `TB_COMPLETE` aus und meldet kein `REF_FAIL`.

Die Referenz-Testbenches wurden vorab gegen eigene korrekte Implementierungen (bestehen) und gegen absichtlich fehlerhafte Mutanten geprüft (fallen durch):
- Zähler zählt in Zweierschritten
- Decoder ohne Korrektur
- Ampel ohne Allrot-Phase
- Ampel mit gleichzeitigem Grün in beiden Richtungen

Wo der Prompt die Taktzählung offenlässt (Phasenlängen der Ampel), toleriert die Referenz ±2 Takte, prüft aber Phasenfolge und Sicherheitsbedingungen streng.

## 7. Erfasste Größen

| Spalte (`results.csv`) | Bedeutung |
|---|---|
| `round`, `prompt`, `variant`, `model` | Zuordnung |
| `passed`, `validator` | Ergebnis und Meldung der eigenen Testbench (Abschnitt 6.1) |
| `ref_passed`, `ref_detail` | Ergebnis und erste Fehlermeldung der Referenz-Testbench (Abschnitt 6.2) |
| `duration_s` | Wanduhrzeit des Einzellaufs |
| `final_stage`, `failure_type` | MAS: letzte Phase der Zustandsmaschine und erste klassifizierte Fehlerklasse |
| `mast_category` | grobe Zuordnung des Fehlschlags zur MAST-Taxonomie (Cemri et al., arXiv:2503.13657): Spezifikation, Abstimmung zwischen Agenten, Verifikation, Infrastruktur |
| `started_at`, `workspace`, `note` | Startzeit, Arbeitsverzeichnis, Fehlermeldung |
| `provider_ok_after`, `valid` | Provider nach dem Lauf erreichbar; Lauf gültig (Abschnitt 5) |

`summary.json` fasst je Variante zusammen: Läufe, Erfolgsquote (eigene und Referenz-Testbench), mittlere Dauer, Ergebnisse je Prompt und Verteilung der MAST-Kategorien.

## 8. Reproduzierbarkeit

`meta.json` hält für jeden Lauf fest:
- Aufruf, Modell und Fallback-Modell
- Zeitlimit und maximale Reparaturrunden
- OpenCode- und GHDL-Version
- Prüfsummen der Prompts und Referenz-Testbenches
- den Code-Stand: Git-Commit plus Prüfsumme jeder nicht committeten Datei

Für eine vollständig reproduzierbare Messung sollte vor dem Lauf committet werden, damit der Code-Stand allein durch den Commit beschrieben ist.

Erneut ausführen (aus `Schaltungsagent/`):

```
python -m benchmark.mas_vs_single --prompt-files 03_ampel.md 02_hamming_decoder.md 01_counter.md --repeat 2
```

## 9. Grenzen der Aussagekraft

- **Stichprobengröße:** Drei Aufgaben und wenige Wiederholungen ergeben keine statistisch belastbaren Unterschiede. Erfolgsquoten sind als Tendenz zu lesen; bei Bedarf `--repeat` erhöhen.
- **Streuung der Modelle:** LLM-Ausgaben sind nicht deterministisch. Derselbe Prompt kann in derselben Variante mal bestehen und mal scheitern (beobachtet: Einzellauf Zähler 2 von 3).
- **Kostenloses Modell:** `opencode/*-free`-Modelle unterliegen Rate-Limits und brechen gelegentlich vorzeitig ab. Das trifft das MAS mit seinen vielen Aufrufen stärker; Gegenmaßnahme siehe Doku #19 (einmalige Wiederholung).
- **Selbst verfasste Aufgaben und Referenzen:** Prompts und Referenz-Testbenches stammen vom Entwicklungsteam. Sie sind keine etablierte Benchmark-Suite. Für eine externe Validierung bieten sich VHDL-Eval (arXiv:2406.04379) oder VHDLSuite (arXiv:2606.13735) an.
- **Nur Simulation:** Synthesefähigkeit, Timing und Verhalten auf echter Hardware werden nicht bewertet.
- **Heuristische Fehlerkategorien:** Die MAST-Zuordnung beruht auf der automatischen Fehlerklasse des MAS und ersetzt keine manuelle Annotation der Läufe.
- **Ein Modell:** Die Aussage gilt für das gemessene Modell; stärkere Modelle können das Verhältnis verschieben.

## 10. Verlauf

| Lauf | Status | Bemerkung |
|---|---|---|
| 2026-10-08 11:33 | ungültig, keine Daten | Workspaces lagen im Repo, und OpenCode arbeitete wegen `$PWD` im Quellbaum (Doku #16/#17). Abgebrochen, Repo bereinigt. |
| `20261008-121802` | abgebrochen nach 8 von 27 Läufen | Älterer Code-Stand: vor Doku #18 (Fehlklassifikation `clock_reset_error`) und #19 (vorzeitiger Modellabbruch), noch ohne Referenz-Testbench. Ergebnisse und nachträgliche Referenzprüfung in `ergebnisse/20261008-121802-abgebrochen/`. |
| `20261008-161755` | größtenteils ungültig | Code-Stand Commit `73769ce`. Ab ca. 18:00 Ausfall des Modell-Providers ([502] Upstream error from Nvidia); 15 von 18 Läufen ungültig. Gültige Beobachtung: Beide Ampel-Entwürfe bleiben auf Haupt-Grün stehen, der MAS-Entwurf besteht trotzdem seine eigene Testbench. Anlass für die Provider-Prüfung (Abschnitt 5). Details: `ergebnisse/20261008-161755/HINWEIS.md`. |
| `20261009-133223-small_vhdl_bench` | Einzel vollständig, MAS abgebrochen | Modellvergleich auf small_vhdl_bench (Abschnitt 11). Einzel-OpenCode: alle 4 Modelle vollständig. MAS: Muse und MiMo nach Rate-Limit des Gratis-Kontingents abgebrochen, die Nemotron-Läufe manuell gestoppt, um zwei MAS-Fehler zu beheben (Doku #20, #21). Details: `ergebnisse/20261009-133223-small_vhdl_bench/HINWEIS.md`. |

| `20261010-091252-small_vhdl_bench_mas` | unterbrochen | MAS, Modelle nacheinander. Muse 9/10, dann Rate-Limit für alle Modelle (Kontingent pro Konto). Danach Doku #22 (Ollama entfernt, Namensvergabe) und #23 (Race Condition `design_state.yaml`) behoben; nicht mit späteren Läufen mischen. Details: `ergebnisse/20261010-091252-small_vhdl_bench_mas/HINWEIS.md`. |
## 11. Modellvergleich auf small_vhdl_bench

`small_vhdl_bench` (vom Projektautor, `Schaltungsagent/benchmark/small_vhdl_bench-main/`) umfasst 10 Aufgaben für den Arty S7: Lauflicht bis Aufzug, mit VHDL und XDC.

- **Bewertung:** `evaluate()` des Benchmarks, regelbasiert. Geprüft werden Struktur, Pflicht-Ports, Schlüsselwörter, keine Simulationskonstrukte, Takt, Entprellung, FSM und erlaubte XDC-Pins; 0–100 Punkte, bestanden ab 70. Bewertet wird **nicht das Verhalten**. Hohe Punktzahlen bedeuten „formal vollständig“, nicht „funktioniert“.
- **Werkzeug:** `Schaltungsagent/benchmark/small_bench_models.py`, Varianten `single` und `mas`.
  - `single`: ein nativer OpenCode-Lauf je Aufgabe, mit einer kurzen, für alle Modelle gleichen Anweisung (Dateien nach `src/`, `tests/`, `constraints/`; Syntaxprüfung mit `ghdl -a`).
  - `mas`: das vollständige MAS (modular, Synthese aus).
- **XDC beim MAS:** Das MAS lässt das Sprachmodell keine XDC schreiben, sondern erzeugt sie in der Synthesephase aus den Entity-Ports. Weil die Synthese im Benchmark aus ist, erzeugt der Runner die XDC nach dem Lauf mit genau dieser Funktion (`_generatexdc_for_board`), ohne Vivado zu starten.
- **Testbenches:** `evaluate()` nimmt nur Dateien mit Präfix `tb_` vom Verbot von Simulationskonstrukten aus. Der Runner reicht Dateien unter `tests/` oder mit `_tb` im Namen deshalb als `tb_<name>` weiter.
- **Gültigkeit:** Vor jedem Lauf wird geprüft, ob der Provider antwortet. Ein nicht bestandener Lauf gilt als ungültig, wenn die OpenCode-Ausgabe einen Provider-Fehler enthält (503/502, Rate-Limit) oder der Provider danach nicht erreichbar ist.
- **Rate-Limits:** Die Gratis-Modelle haben ein Kontingent. Das MAS braucht pro Aufgabe ein Vielfaches an Aufrufen; parallele MAS-Läufe mehrerer Modelle nach anderen Testserien am selben Tag erschöpften es (Lauf 20261009). Empfehlung: MAS-Läufe mit frischem Kontingent und je Modell nacheinander starten.

