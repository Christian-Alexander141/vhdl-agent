# Lauf 20261010-091252-small_vhdl_bench_mas (unterbrochen)

- **Variante:** MAS auf small_vhdl_bench, Modelle nacheinander.
- **Vergleichsbasis:** Einzel-OpenCode aus `20261009-133223-small_vhdl_bench`.
- **Code-Stand:** Commit `ff3c9b4` plus 18 nicht committete Dateien (Prüfsummen in `meta.json`), also vor Doku #22 und #23.
- **Zeitraum:** 2026-10-10, 09:12 bis ca. 14:30.

## Ergebnis

| Modell | fertig | Ergebnis |
|---|---|---|
| Muse Spark 1.3 | 9/10 | Ø 78,6 Punkte über 9 Aufgaben (Einzel: 92,3); ohne task04 88,4 gegen 91,9 |
| MiMo, Nemotron 3 Ultra, Nemotron 3.5 Lightning | 0/10 | nicht gestartet |

Abgebrochen wegen Rate-Limit des Gratis-Kontingents, diesmal für alle vier Modelle gleichzeitig („Rate limit exceeded“). Das Kontingent gilt offenbar pro Konto, nicht pro Modell. Der Lauf wurde danach manuell gestoppt, um Fehler im MAS zu beheben.

## Im Lauf gefundene MAS-Fehler (danach behoben)

- **task04 – 0 Punkte:** `BLOCKED_NEEDS_NAME`. Die Namensvergabe fragte ein separates Ollama-LLM, das nicht lief, obwohl OpenCode im Plan bereits einen Namen vergeben hatte. Behoben durch Entfernen von Ollama (Doku #22).
- **task06:** Zwischenzeitlich `PromptIntegrityError`, weil parallele Worker ein halb geschriebenes `design_state.yaml` lasen (Race Condition, Doku #23). Der Lauf erreichte trotzdem 87 Punkte.
- **task09:** Eine Reparatur lief ins Zeitlimit von 3000 s; die Dateien lagen schon vor (87 Punkte).

## Verwendung

**Nicht mit späteren MAS-Läufen mischen.** Der Code-Stand unterscheidet sich (#22, #23), und es fehlen drei von vier Modellen. Als Beleg dient der Lauf nur für die Tendenz bei Muse Spark (MAS etwa gleichauf bis leicht schlechter als der Einzellauf, 4–10-mal langsamer) und für die gefundenen Fehler.
