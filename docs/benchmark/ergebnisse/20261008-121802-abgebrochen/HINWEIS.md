# Lauf 20261008-121802 (abgebrochen)

- **Gestartet:** 2026-10-08 12:18; **abgebrochen:** 16:10 nach 8 von 27 geplanten Einzelläufen, auf Entscheidung des Projektverantwortlichen.
- **Aufruf:** `python -m benchmark.mas_vs_single --repeat 3`, also alle Prompts alphabetisch, Varianten nacheinander statt abwechselnd.
- **Modell:** `opencode/nemotron-3.5-lightning-free` (Fallback `opencode/muse-spark-1.3-free`), nativ, Workspaces unter `~/vhdl-agent-benchmark/20261008-121802/`.

## Warum nicht mit späteren Läufen vergleichbar

1. **Alter Code-Stand der MAS-Varianten:** Der Benchmark-Prozess hat den Code beim Start geladen. Die MAS-Läufe enthalten daher noch die fehlerhafte Fehlerklassifikation (Doku #18: jedes Vorkommen von „Reset“ wurde zu `clock_reset_error`) und keine Wiederholung bei vorzeitigem Modellabbruch (Doku #19).
2. **Keine Referenz-Testbench:** `results.csv` enthält nur das Ergebnis der systemeigenen Testbench. Die unabhängige Referenzprüfung (`referenz_nachtraeglich.csv`) wurde nachträglich auf die vorhandenen Workspaces angewandt. Die MAS-Workspaces lassen sich den Zeilen in `results.csv` nicht sicher zuordnen.
3. **Reihenfolge:** Varianten liefen nacheinander, nicht abwechselnd; zeitabhängige Provider-Effekte sind daher nicht ausgeglichen.

## Inhalt

| Datei | Inhalt |
|---|---|
| `results.csv` | aus dem Log rekonstruierte Ergebnisse (Prompt, Variante, Lauf, bestanden, Dauer, Fehlerklasse bzw. Validator-Meldung) |
| `referenz_nachtraeglich.csv` | Ergebnis der Referenz-Testbench je vorhandenem Workspace |
| `benchmark.log` | vollständige Konsolenausgabe des Laufs |

## Beobachtungen (nur als Hinweis, nicht als Ergebnis)

- **Einzel-OpenCode:** eigene Testbench 2 von 3 bestanden, Referenz ebenfalls 2 von 3. Der gescheiterte Entwurf zählt beim ersten Takt nicht.
- **MAS modular:** eigene Testbench 1 von 3. Alle MAS-Entwürfe, die überhaupt Quellen erzeugten, bestehen jedoch die Referenz-Testbench; die Fehlschläge lagen an Testbench, Klassifikation oder Infrastruktur, nicht am Entwurf. Das war der Anlass, die Referenz-Testbench als Hauptkriterium einzuführen.
- **Dauer:** Ein MAS-Lauf brauchte beim Zähler etwa 22–55 min, ein Einzellauf etwa 9–12 min.
