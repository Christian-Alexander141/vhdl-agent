# Lauf 20261008-161755 – größtenteils ungültig (Provider-Ausfall)

- **Zeitraum:** 2026-10-08 16:17 bis 2026-10-09 03:19, Code-Stand Commit `73769ce`.
- **Aufruf:** `--prompt-files 03_ampel.md 02_hamming_decoder.md 01_counter.md --repeat 2`, alle drei Varianten.

## Was passiert ist

Ab etwa 18:00 war der Provider des Gratis-Modells `opencode/nemotron-3.5-lightning-free` praktisch nicht erreichbar. Laut OpenCode-Log fielen die Modellanfragen von 93–176 pro Stunde (bis 17:59) auf 2–6 pro Stunde, und jede davon endete mit einem Fehler: „Streaming response failed: [502] Upstream error from Nvidia: Internal server error“, `AI_RetryError`. OpenCode versuchte es still weiter, bis das Zeitlimit griff (Planung 1200&nbsp;s, Einzellauf 3000&nbsp;s). Die betroffenen Läufe messen den Ausfall, nicht die Varianten.

Dieser Lauf hatte noch keine Provider-Prüfung. Die Spalte `valid` fehlt daher in `results.csv`, und `summary.json` rechnet die ungültigen Läufe mit ein. **`summary.json` ist für diesen Lauf nicht aussagekräftig.** Die nachträgliche Einordnung steht unten. Seitdem prüft der Benchmark den Provider vor und nach jedem Lauf (Spalten `provider_ok_after`, `valid`).

## Nachträgliche Einordnung

| Start | Prompt | Variante | Eigene TB | Referenz | Gültig? | Bemerkung |
|---|---|---|---|---|---|---|
| 16:17 | 03_ampel | single | FAIL | FAIL | ja | vor dem Ausfall beendet |
| 16:44 | 03_ampel | mas | PASS | FAIL | ja, Entwurf bewertbar | Entwurf lag vollständig vor; Abschluss danach scheiterte am Ausfall |
| 18:36–01:46 | alle | alle | FAIL | FAIL | **nein** | 15 Läufe, Zeitlimit wegen Provider-Ausfall |
| 02:06 | 01_counter | mas-single | PASS | PASS | ja | Provider wieder erreichbar |

## Inhaltliche Beobachtung aus den gültigen Läufen

Beide Ampel-Entwürfe (Einzel-OpenCode und MAS) **bleiben dauerhaft auf Haupt-Grün stehen**: Der Timer löst nie aus. Das wurde mit einer eigenen Hilfs-Testbench nachvollzogen, die die Lampenfolge über 200 Takte aufzeichnet: `MR MY MG SR SY SG = 0 0 1 1 0 0`, 200 Takte lang. Die Referenz-Testbench meldet deshalb zu Recht „kein vollständiger Zyklus in 200 Takten“.

Der MAS-Entwurf hat seine **eigene** Testbench trotzdem bestanden. Die systemeigene Testbench prüfte also das zentrale Zeitverhalten nicht. Das bestätigt, warum die unabhängige Referenz-Testbench das Hauptkriterium ist (`METHODIK.md`, Abschnitt 6).
