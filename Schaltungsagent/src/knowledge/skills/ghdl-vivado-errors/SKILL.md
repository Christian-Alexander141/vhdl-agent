# Skill: ghdl-vivado-errors
# Beschreibung: Mapping von GHDL/Vivado-Fehlermeldungen zu Ursachen und Maßnahmen.
# Lade diesen Skill, wenn ein GHDL- oder Vivado-Fehler auftritt und die Diagnose/Reparatur geplant wird.
# Quelle: Nur belegte Fälle aus debug.py classify_error und echte Logs unter projects/*/build/.
# Keine erfundenen Einträge – Tabelle wächst bei Bedarf.

## GHDL Errors

| Meldung (wörtlich / Regex) | Ursache | Maßnahme |
|---|---|---|
| `** Error: <file>.vhd:<line>:<col>: syntax error` | VHDL-Syntaxfehler (fehlendes `;`, falsches Keyword, etc.) | Zeile prüfen, Syntax korrigieren |
| `** Error: <file>.vhd:<line>:<col>: entity "<name>" not found` | Entity nicht kompiliert oder falscher Name | `ghdl -a` für Entity ausführen, Namen prüfen |
| `** Error: <file>.vhd:<line>:<col>: no declaration for identifier "<name>"` | Signal/Variable/Constant nicht deklariert | Deklaration hinzufügen, Tippfehler prüfen |
| `** Error: <file>.vhd:<line>:<col>: type mismatch` | Inkompatible Typen in Zuweisung/Port-Map | Typen angleichen (`signed`/`unsigned`/`std_logic_vector`), Casts nutzen |
| `** Error: <file>.vhd:<line>:<col>: cannot associate formal port "<port>"` | Port-Map: falscher Name, Richtung, oder Typ | Port-Namen exakt aus Entity kopieren, Richtung prüfen |
| `** Error: <file>.vhd:<line>:<col>: actual is not a signal` | Variable in Port-Map oder Signal dort wo Variable erwartet | Nur Signale in Port-Maps, Variablen nur lokal |
| `** Error: <file>.vhd:<line>:<col>: simulation stopped (TB_COMPLETE)` | Normales Testbench-Ende | Kein Fehler – Erfolg |
| `** Error: <file>.vhd:<line>:<col>: assertion failed: <msg>` | `assert ... severity error` getriggert | Testfall oder DUT-Logik prüfen |
| `** Error: <file>.vhd:<line>:<col>: range constraint error` | Array-Index out of bounds, Zähler-Überlauf | Bounds prüfen, `if idx < MAX` vor Zugriff |
| `** Error: <file>.vhd:<line>:<col>: simulation loop detected` | Delta-Zyklus-Schleife (kombinatorische Schleife) | Sensitivity Lists prüfen, Latch entfernen, Pipeline |
| `ghdl: cannot open <file>.vhd: No such file or directory` | Dateipfad falsch, Datei nicht generiert | Pfad prüfen, Generierungsschritt prüfen |

## Vivado Synthesis/Implementation Errors

| Meldung | Ursache | Maßnahme |
|---|---|---|
| `[Synth 8-327] inferring latch for variable <name>` | Incomplete `if`/`case` in combinational process | `else` Zweig hinzufügen, `when others` in `case` |
| `[Synth 8-638] signal <name> has multiple drivers` | Signal in mehreren Prozessen zugewiesen | Ein Prozess pro Signal, oder `resolved` Typ |
| `[Synth 8-... ] unsupported construct: wait` | `wait` in synthetisierbarem Code | `wait` entfernen, Clock/Reset nutzen |
| `[Timing 38-282] Setup violation: slack = -X.XXXns` | Kombinatorischer Pfad zu lang für Clock | Pipeline-Register, Logik vereinfachen, Frequenz reduzieren |
| `[Timing 38-283] Hold violation: slack = -X.XXXns` | Clock Skew / zu schneller Pfad | Buffer, `set_clock_uncertainty` prüfen |
| `[DRC NSTD-1] No IOSTANDARD for port <port>` | Pin ohne IOSTANDARD Constraint | `set_property IOSTANDARD ...` in XDC |
| `[DRC UCIO-1] Unconstrained logical port <port>` | Pin ohne LOC Constraint | `set_property PACKAGE_PIN ...` in XDC |
| `[Common 17-69] Vivado binary 'vivado' not found` | Vivado nicht installiert / nicht im PATH | Vivado installieren, PATH prüfen, Docker nutzen |
| `[Project 1-...] Multiple top-level entities found` | Mehrere Entities ohne Hierarchie, keine Top angegeben | `top_entity` in manifest setzen, nur eine Top-Entity |

## Infrastructure Errors (nicht reparierbar durch Code-Änderung)

| Meldung | Klassifikation | Aktion |
|---|---|---|
| `ghdl not found` / `vivado not found` | `infrastructure` | Tool installieren, PATH setzen |
| `Docker permission denied` | `infrastructure` | User zu `docker` Gruppe, oder lokalen CLI nutzen |
| `license expired` / `quota exceeded` | `infrastructure` | Lizenz erneuern, Cloud-Konto prüfen |
| `No space left on device` | `infrastructure` | Platz schaffen, alte Builds löschen |

## Debug Agent Usage (deterministisch)
Der `DebugAgent` nutzt `classify_error` (regex-basiert) für:
1. `failure_type` (syntax_error, type_error, elaboration_error, interface_mismatch, clock_reset_error, testbench_error, functional_simulation_error, synthesis_error, timing_error, resource_error, bitstream_error, hardware_error, infrastructure)
2. `recommended_action` (fixierbarer Text)
3. `severity` (low, medium, high, critical)
4. `suspected_modules` – **nur** Module aus der Architektur (`architecture.modules`), nie erfundene Namen wie `alu`/`control_unit`

## Repair Path (Production)
1. `DebugAgent` liefert Diagnose (kein LLM)
2. Supervisor erstellt `RepairTask` für `HDLAgent._fix_hdl`
3. `HDLAgent` ruft **frische OpenCode-Instanz** mit:
   - `PROMPT.md` (Original, Hash geprüft)
   - `reports/last_failure.md` (Fehlerlog)
   - Betroffene Dateien, Architektur-Manifest
   - Aufgabe: Root Cause fixen, `ghdl -a --std=08` laufen lassen
4. Kein Ollama, kein Regel-Code im Debug

## Known Patterns from Projects
- `projects/ampel-projekt-678dcf/build/` → GHDL logs zeigen Entity `fpga` statt `ampel` (Name-Fallback-Problem)
- `projects/aufgabe-5-*/constraints/auto_generated.xdc` → R2 mit LVCMOS33 (Board-Fact Warning)