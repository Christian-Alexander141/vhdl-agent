# Lauf 20261009-133223-small_vhdl_bench

Benchmark: `small_vhdl_bench` (vom Projektautor, 10 Aufgaben für den Arty S7). Bewertung mit `evaluate()` des Benchmarks: regelbasiert (Struktur, Ports, Schlüsselwörter, keine Simulationskonstrukte, Takt, Entprellung, FSM, XDC-Pins), 0–100 Punkte, bestanden ab 70. **Keine Verhaltensprüfung.**

Modelle: `opencode/muse-spark-1.3-contributor-free`, `opencode/mimo-v2.6-flash-free`, `opencode/nemotron-3-ultra-free`, `opencode/nemotron-3.5-lightning-free`. Werkzeug: `Schaltungsagent/benchmark/small_bench_models.py`. Code-Stand: Arbeitsstand nach Commit `ff3c9b4` mit den nicht committeten Maßnahmen A und B (docs/doku.html, Abschnitt 16).

## Variante `single` (vollständig, 2026-10-09 13:32–17:00)

Ein nativer OpenCode-Lauf je Aufgabe und Modell; die vier Modelle liefen parallel.

| Modell | gültig | bestanden | Ø Punkte | Ø Zeit |
|---|---|---|---|---|
| Muse Spark 1.3 | 10 | 10 | 92,5 | 3,1 min |
| Nemotron 3.5 Lightning | 10 | 10 | 87,8 | 14,3 min |
| Nemotron 3 Ultra | 9 | 9 | 94,5 | 5,6 min |
| MiMo v2.6 Flash | 10 | 8 | 75,2 | 12,3 min |

- Ungültig: Ultra/task09 (Provider meldete „[503] Upstream error from Nvidia“; der Lauf misst den Ausfall). Die Regel „Provider-Fehler in der Ausgabe ⇒ ungültig“ wurde erst nach diesem Lauf ergänzt und nachträglich angewandt.
- MiMo/task04 und task05: Das Modell endete ohne eine einzige Datei (echtes Modellversagen).

## Variante `mas` (abgebrochen, 2026-10-09 17:30–22:15)

Vollständiges MAS (modular, Synthese aus). Die XDC wird wie in der Synthesephase des MAS aus den Entity-Ports erzeugt (`_generatexdc_for_board`), weil das MAS die Constraints nicht vom Sprachmodell schreiben lässt.

| Modell | fertig | gültig | bestanden | Abbruchgrund |
|---|---|---|---|---|
| Muse Spark 1.3 | 2/10 | 2 | 2 | Rate-Limit des Gratis-Kontingents („Rate limit exceeded“) |
| MiMo v2.6 Flash | 1/10 | 1 | 1 | Rate-Limit des Gratis-Kontingents |
| Nemotron 3.5 Lightning | 4/10 | 4 | 3 | manuell gestoppt (Entscheidung: Fehler beheben, morgen neu) |
| Nemotron 3 Ultra | 6/10 | 4 | 2 | manuell gestoppt |

**Nicht als Endergebnis verwenden.** Gründe:

1. **Unvollständig:** Bei Muse und MiMo war das Gratis-Kontingent erschöpft. Beide Modelle liefen an diesem Tag in drei Testserien; das MAS verbraucht pro Aufgabe ein Vielfaches an Aufrufen gegenüber einem Einzellauf. Der Runner hat nach zwei Stunden Wartezeit korrekt abgebrochen.
2. **Zwei MAS-Fehler drücken das Ergebnis.** Beide wurden danach behoben (docs/doku.html, #20 und #21):
   - Die Planprüfung lehnte Pläne mit einem unbekannten Modultyp ab (Lightning/task03 → 0 Punkte statt eines Ergebnisses).
   - Die automatisch erzeugte XDC setzte den Takt-Pin R2 und `sw[3]`/M5 auf `LVCMOS33` statt des offiziellen `SSTL135`, und `INTERNAL_VREF` für Bank 34 fehlte.
3. **Provider:** Ultra scheiterte viermal in der Planung am Zeitlimit von 1200 s, einmal mit Nvidia-503.

**Beobachtung, als Hinweis:** Wo das MAS einen Entwurf lieferte, lag die Punktzahl auf dem Niveau des Einzellaufs (z. B. Muse 01: 88 → 89, MiMo 01: 87 → 93, Lightning 02: 93 → 80). Die Laufzeit war mit 30–120 min je Aufgabe aber 5–20-mal so lang.

Dateien: `results_<variante>_<modell>.csv` (eine Zeile je Aufgabe), `summary.json`, `meta.json`, `logs/` (Konsolenausgaben). Workspaces: `~/vhdl-agent-benchmark/20261009-133223-small_vhdl_bench/` (außerhalb des Repos).
