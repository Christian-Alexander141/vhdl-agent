# Aufgabe 05 – Ben-Eater-8-Bit-Rechner: MAS gegen einen einzelnen OpenCode-Aufruf (2026-10-13)

Aufgabe: `Schaltungsagent/benchmark/prompts/05_ben_eater_8bit.md` (originalgetreu nach Ben Eaters
Mikrocode `microcode-eeprom-with-flags`, UART-Lader im Protokoll des System-Hardwaretests).
Gleiches Modell für beide Varianten: `opencode/muse-spark-1.3-contributor-free`.

- **MAS** (`mas_ben-eater-8bit-computer-7814fe/`): über `POST /api/chat` wie aus dem Dashboard, ohne
  Eingriff, bis einschließlich Flash und automatischem Hardwaretest über die USB-UART (Stand `6f7f985`).
- **Single** (`single_20261013-111444/`): ein OpenCode-Aufruf über den Benchmark
  (`--variants single --opencode-timeout 3600`, Kennzahlen in `../20261013-111444/`). Synthese, Flash und
  derselbe Hardwaretest danach mit dem FPGAAgent und dem HardwareTestAgent des Systems.
- **Eigene Umsetzung** (`Schaltungsagent/benchmark/reference/05_pruefgrundlagen/`): Gegenprobe für Aufgabe,
  Referenz-Testbench und Hardwarestrecke.

| | MAS | Single | eigene Umsetzung |
|---|---|---|---|
| Dauer bis simulierter Entwurf | ca. 40 min | **8,4 min** | – |
| Dauer bis Hardwaretest bestanden | **45:44 min** (in einem Lauf) | ca. 14,5 min (8,4 + Synthese/Flash/Test) | – |
| OpenCode-Aufrufe (Modellzeit) | 27 (57,4 min) | 1 (8,4 min) | – |
| Reparaturen | 0 | – | – |
| Module (12 vorgegeben) | 12 | 12 | 1 Entity |
| Testbenches | 12 (je Modul) + Top | 1 (Top, 444 Zeilen) | – |
| Eigene Testbench(es) | bestanden | bestanden | – |
| Referenz-Testbench (neutrale Fassung) | bestanden | bestanden | bestanden |
| Strenge Lesart „Verwerfen ab dem ersten Längenbyte“ | nicht erfüllt | nicht erfüllt | erfüllt |
| Taktgenauer Vergleich mit dem Referenzmodell (4 Zufallsfolgen) | bestanden (im Lauf) | 4/4 übereinstimmend | 4/4 übereinstimmend |
| Mutationsquote (10 Mutanten, Seed 0) | 0,9 | 0,9 | – |
| Hardwaretest am Board (4 UART-Programme) | **4/4, automatisch im Lauf** | 4/4 | 4/4 |
| Timing (WNS) | +3,10 ns | +3,01 ns | +3,09 ns |
| LUTs / Flipflops | 399 / 508 | 428 / 479 | 390 / 434 |
| Einzelanforderungen mit Nachweis | 78, unabhängig bewertet | keine | – |

**Unschärfe in der Aufgabe.** Die Aufgabe sagt, ein abweichendes Byte (z. B. Länge außerhalb 1..16) verwerfe
den Rahmen, und das nächste Byte sei wieder das erste Längenbyte. Beide Entwürfe prüfen die Länge erst nach
allen vier Längenbytes. Die ursprüngliche Referenz-Testbench sendete nur das Byte `0x11` und setzte die
byteweise Lesart voraus; der folgende Rahmen ging dann bei beiden verloren. Die Referenz-Testbench sendet
seit dem 2026-10-13 den vollständigen ungültigen Längenwert `11 00 00 00`, den beide Lesarten verwerfen
(Änderung vor der Auswertung von Single, angewandt auf beide Entwürfe; alle 11 Fehlervarianten werden
weiterhin erkannt).

**Einordnung.** Funktional gleichwertig: beide bestehen alle Prüfungen einschließlich des Hardwaretests,
beide taktgenau. Single war etwa 5-mal schneller bis zum simulierten Entwurf und brauchte ein Siebtel der
Modellzeit. Das MAS liefert dafür ohne Zusatzschritte den vollständigen Weg bis zum bestandenen
Hardwaretest, eine Testbench je Modul und eine begründete Bewertung jeder Einzelanforderung. Ein Lauf je
Variante ist eine Stichprobe.

Inhalt: je Variante `src/`, `tests/`, `constraints/`, `synthese/`; beim MAS zusätzlich Plan, Referenzmodell,
Abschlussprüfung, Ereignisse, Serverlog und Trajektorie. Pfade und Rechnerdaten ersetzt.
