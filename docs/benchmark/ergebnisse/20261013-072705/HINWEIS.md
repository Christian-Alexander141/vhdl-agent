# Aufgabe 04 als einzelner OpenCode-Aufruf (Single), 2026-10-13

Vergleichslauf zu den drei MAS-Läufen vom 2026-10-12 (`../20261012-04_mini_cpu/`). Gleiches Modell
(`opencode/muse-spark-1.3-contributor-free`), ein Aufruf mit dem Benchmark-Auftrag `SINGLE_INSTRUCTION`
(Projekt umsetzen, Testbench, Selbstprüfung mit GHDL), Zeitlimit 3600 s.
Befehl: `benchmark/mas_vs_single.py --prompt-files 04_mini_cpu.md --variants single --opencode-timeout 3600`.

Synthese und Flash gehören nicht zur Single-Variante des Benchmarks. Sie wurden danach auf einer Kopie
mit dem FPGAAgent des MAS ausgeführt (gleiche deterministische Werkzeugkette: XDC aus den Top-Level-Ports,
Vivado 2026.1, Flash SRAM + QSPI), damit der Entwurf am Board geprüft werden kann.

| | Single | MAS (Lauf 1 / Lauf 2 / Kontrolllauf) |
|---|---|---|
| Dauer bis simulierter Entwurf | 4,6 min (1 Aufruf) | ca. 30 / 31 / 40 min (22–24 Aufrufe) |
| Dauer bis Board inkl. Synthese/Flash | ca. 10,5 min | 37,7 / 38,0 / 47,1 min |
| Module (10 vorgegeben) | 10 | 10 / 10 / 10 |
| Testbenches | 1 (Top-Level) | 9 / 9 / 10 |
| Eigene Testbench | bestanden | bestanden |
| Unabhängige Referenz-Testbench | bestanden | bestanden (alle drei) |
| Taktgenauer Vergleich mit den Referenzmodellen der 3 MAS-Läufe (je 4 Zufallsfolgen) | 12/12 übereinstimmend | – (Kontrolllauf: Abweichung gefunden und behoben) |
| Mutationsquote (Mutationsanalyse des MAS, 10 Mutanten, Seed 0) | 0,7 | 0,9 / 0,7 / 1,0 |
| Timing (WNS) | +4,69 ns | +3,76 / +3,14 / +3,77 ns |
| LUTs / Flipflops | 106 / 149 | 95/151, 108/149, 93/151 |
| Einzelanforderungen mit Nachweis | keine | 91 / 74 / 91 |

Überlebende Mutanten der Single-Testbench (alle in `control_unit.vhd`): HLT ohne Wirkung
(`state <= HALT_ST` entfernt) sowie die Schreibfreigaben für C und Z. Die Testbench würde also einen
wirkungslosen HLT-Befehl nicht bemerken; der Entwurf selbst ist korrekt.

Inhalt: `results.csv`, `summary.json`, `meta.json`, `benchmark.log` (vom Benchmark), `entwurf/src`,
`entwurf/tests` (Endstand), `entwurf/synthese` (XDC, Timing, Ressourcen).
