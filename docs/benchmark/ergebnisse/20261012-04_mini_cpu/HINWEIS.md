# Benchmark-Aufgabe 04 – 4-Bit-Akkumulator-CPU (2026-10-12)

Drei reale Läufe der Aufgabe `Schaltungsagent/benchmark/prompts/04_mini_cpu.md`, jeweils über
`POST /api/chat` wie aus dem Dashboard gestartet und ohne Eingriff bis zum Flashen auf das Arty S7-50
durchgelaufen. Ausführliche Beschreibung: `docs/Aufgabe04_Mini-CPU.pdf`.

| Lauf | Projekt | Stand | Dauer | Ergebnis |
|---|---|---|---|---|
| Lauf 1 | `fibonacci-accumulator-cpu-c71b1f` | `af7d863` (vor #48–#57) | 37,7 min | COMPLETED, 0 Reparaturen |
| Lauf 2 | `mini-accumulator-cpu-66e33d` | `af7d863` (vor #48–#57) | 38,0 min | COMPLETED, 0 Reparaturen |
| Kontrolllauf | `fibonacci-accu-cpu-f8fb57` | `256a317` (mit #48–#56) | 47,1 min | COMPLETED, 2 Reparaturen (Modellstreit um `tick_gen`) |

Alle drei Entwürfe bestehen die unabhängige Referenz-Testbench
(`Schaltungsagent/benchmark/reference/04_mini_cpu_ref_tb.vhd`); die LED-Ausgabe am Board hat der
Benutzer nach Lauf 2 bestätigt.

Nicht in `results.csv`: Ein erster Kontrollauf (`fibonacci-accu-cpu-588373`, Stand `034ec88`) endete
als BLOCKED, weil der Anbieter hinter OpenCode Zen rund 1,5 Stunden lang beide freien Modelle
ablehnte (`Upstream request failed: Invalid credential`). Er führte zu den Korrekturen #56.

## Inhalt

- `results.csv`, `summary.json`, `meta.json` – Kennzahlen aller Läufe, Versuchsaufbau
- `laufN_<projekt>/`
  - `kennzahlen.json` – Kennzahlen dieses Laufs
  - `plan/` – Manifest (Module, Ports, Einzelanforderungen, ggf. Prüfanleitung) und `requirements.md`
  - `src/`, `tests/`, `model/`, `constraints/` – Endstand des Entwurfs, der Testbenches und des Referenzmodells
  - `reports/` – Abschlussprüfung der Anforderungen, ggf. Befund der Reparatur und Prüfanleitung
  - `synthese/` – Vivado-Berichte (Timing, Ressourcen)
  - `events.jsonl` – alle Ereignisse, die das Dashboard empfing
  - `server.log` – Serverprotokoll
  - `trajectory.jsonl` – Lauf-Trajektorie (#46/#54)

Bitstreams sind nicht enthalten (je 8 MB, aus den Quellen reproduzierbar). Pfade, Home-Verzeichnis,
Benutzer- und Rechnername sind ersetzt (`<workspace>`, `~`, `<host>`).
