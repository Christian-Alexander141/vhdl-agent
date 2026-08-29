# Feedback: Erweiterung der GHDL-Verifikationspipeline

Datum: 2026-08-16
Umfang: Analyse/Elaboration/Simulation mit Assertions-Auswertung, strukturierte
Fehlerberichte (`failed_case`), erweiterter Repair-Kontext, Regressionstests.

---

## Geänderte Dateien

| Datei | Änderung |
|---|---|
| `Schaltungsagent/src/infrastructure/validation/ghdl_validator.py` | Duplikat-Code entfernt: Der Validator nutzt jetzt die Kommandobuilder `analyze_command()`, `elaborate_command()` und `run_command()` aus `test_definitions.py` statt eigener, paralleler Kommando-Konstruktion (`_simulate_command` gelöscht). Der konfigurierte `ghdl_binary` wird per `dataclasses.replace()` in die Testdefinition übernommen, ohne das geteilte `VHDLTestDefinitions.DEFAULT`-Objekt zu mutieren. |
| dito | Totes Feld `failed_case` belebt: Neue Methode `_parse_failed_case()` extrahiert strukturierte Testbench-Reports (`FAIL CASE data=.. bit=.. code=.. ...`) aus der GHDL-Simulationsausgabe. `failed_case` enthält Testbench, Testfall-Typ (Einzelbitfehler / fehlerfreies Codewort), Datenwort, verfälschtes Bit, Eingabecodewort sowie erwartete/tatsächliche Werte für `DATA_OUT`, `ERROR_DETECT`, `ERROR_CORRECT`. |
| dito | Neue Methode `_attach_artifacts()`: Hängt den erzeugten VHDL-Code (`dut_content`) und die Testbench (`testbench_content`) an die Fehlerdetails aller Fehlerpfade an (Analyse-, Elaborations-, Simulationsfehler, fehlende Testbench, fehlende Assertions). |
| dito | `validate_file()` nutzt ebenfalls `analyze_command()` statt hartkodiertem `["-a"]`. |
| `Schaltungsagent/src/domain/ports/validation_service.py` | `build_repair_instruction()` erweitert: `failed_case` wird mit deutschen Labels gerendert (`FAILED_CASE_LABELS`), zusätzlich „Betroffene Datei", „Erzeugter VHDL-Code (DUT)" und „Erzeugte Testbench" im Reparatur-Kontext. Die Anti-Cheating-Regeln bleiben unverändert. |
| `Schaltungsagent/src/domain_plugins/vhdl/templates.py` | Hamming-(7,4)-Testbench: Alle drei `check_case`-Reports enthalten jetzt das Eingabecodewort (`code=<bin>`), formatiert über eine neue VHDL-93-kompatible Hilfsfunktion `slv_to_string()`. |
| `Schaltungsagent/tests/test_ghdl_validator.py` | Zwei neue Regressionstests: `test_failed_case_wird_aus_simulationsausgabe_extrahiert` (beweist die `failed_case`-Extraktion) und `test_repair_instruction_enthaelt_generierten_code_und_testbench` (beweist den vollständigen Repair-Kontext). |

## Verifikationspipeline (Ist-Zustand)

1. **Analyse**: `ghdl -a <datei>` für alle VHDL-Dateien (DUTs + Testbenches)
2. **Elaborierung**: `ghdl -e <testbench>` (Testbench-Entity wird aus den Dateien in `tests/` ermittelt, nicht hartkodiert)
3. **Simulation**: `ghdl -r <testbench> --stop-time=... --assert-level=error` (Flags aus `test_definitions.py`, `--assert-level=error` wird erzwungen)
4. **Assertions-Auswertung**: Exit-Code != 0, Assertion-Failure-Patterns, fehlender `TB_COMPLETE`-Marker und Testbenches ohne `severity error/failure` führen zu FAIL
5. **PASS nur, wenn**: Analyse PASS UND Elaborierung PASS UND Simulation PASS UND alle Assertions PASS

## Testbench-Schutzmaßnahmen

- Erwartungswerte stammen aus unabhängiger Referenz (`hamming_encode`-Funktion in der Testbench), nie aus dem DUT
- `EXPECTED_DATA <= DATA_OUT`-Muster sind durch die Anti-Cheating-Regeln in `build_repair_instruction()` ausgeschlossen
- Hamming-Testbench: 16 Datenwörter × (1 fehlerfreier Fall + 7 Einzelbitfehler) = **128 Testfälle** (per Assertion `test_count = 128` abgesichert)
- Zwei-Bit-Fehler werden nicht als korrigierbar erwartet (dokumentiert im Testbench-Kommentar)

## Durchgeführte Tests

| Test | Ergebnis |
|---|---|
| `pytest Schaltungsagent/tests/` (10 Tests) | **10/10 PASSED** |
| `Schaltungsagent/src/tests/test_unit.py` (36 Tests) | **36/36 PASSED** |
| `Schaltungsagent/src/tests/test_architecture.py` (40 Tests) | **40/40 PASSED** |
| Manuell: korrekter Hamming-DUT | **PASS** |
| Manuell: absichtlich fehlerhafter Hamming-DUT (Fehlererkennung invertiert) | **FAIL** mit `failed_case` `{data: 0, bit: -1, code: 0000000, ERROR_DETECT expected: '0', actual: '1'}` |
| `py_compile` aller geänderten Dateien + `main.py`/`api_server.py` | **OK** |

Die Regressionstests decken alle vier Pflichtfälle ab:

1. syntaktisch + funktional korrekter DUT → PASS
2. syntaktisch falscher DUT → FAIL (Analysefehler)
3. syntaktisch korrekter, funktional falscher DUT → FAIL (Simulation/Assertion)
4. korrekter DUT + fehlerhafte Testbench → FAIL (beweist, dass nicht nur `ghdl -a` läuft)

## Beispiel: Repair-Instruktion (Auszug)

```
Repariere die VHDL-Komponente. Die Validierung ist fehlgeschlagen.
Ursprüngliche Anforderung: Hamming-(7,4)-Decoder bauen
Reparatur-Iteration: 1
Validierungsergebnis: FAIL
Meldung: GHDL simulation failed for hamming_decoder_tb (...)
Testbench: hamming_decoder_tb
Betroffene Datei: .../tests/hamming_decoder_tb.vhd

Fehlgeschlagener Testfall:
  Testbench: hamming_decoder_tb
  Testfall: Fehlerfreies Codewort
  Datenwort: 0
  Verfälschtes Bit: -1
  Eingabecodewort: 0000000
  Erwarteter ERROR_DETECT: '0'
  Tatsächlicher ERROR_DETECT: '1'

[ANALYZE] hamming_decoder.vhd        Returncode: 0
[ELABORATE] hamming_decoder_tb       Returncode: 0
[SIMULATE] hamming_decoder_tb        Returncode: 1
  GHDL-Ausgabe: ... FAIL CASE data=0 bit=-1 code=0000000 ...

Erzeugter VHDL-Code (DUT): ...
Erzeugte Testbench: ...

Regeln für die Reparatur:
- Ändere nur den notwendigen VHDL-Code des DUT bzw. die notwendigen Artefakte.
- Verändere die Testbench NICHT so, dass ein eigentlich fehlerhafter DUT den Test besteht.
- ...
```

## Noch offene Punkte

- `build_definitions.py` (ungenutzt, `--stop-time=1us`) ist inkonsistent zu `test_definitions.py` (`--stop-time=10us`). Bewusst nicht angefasst (minimal-invasiv); bei einer späteren Bereinigung vereinheitlichen oder entfernen.
- Der Repair-Kontext wird bei großen Projekten lang (Code-Inhalte auf 10.000 Zeichen gedeckelt). Der OpenCode-Agent kann die Dateien im Workspace ohnehin direkt lesen.
- Docker-Konfiguration wurde nicht verändert; GHDL läuft weiterhin auf dem Host.
- Änderungen sind nicht committet.

---

# Phase 1: FPGA-Synthese (Grundgerüst)

Datum: 2026-08-16
Umfang: Stufe-1-Synthese mit `ghdl synth`, FPGA-Registry, Synthese-Konfiguration.
Gesamtplan siehe [doc/synthesis_plan.md](synthesis_plan.md).

## Geänderte/neue Dateien

| Datei | Änderung |
|---|---|
| `Schaltungsagent/src/domain/ports/synthesis_service.py` | **Neu**: Port `SynthesisService` (`synthesize()` + `toolchain_available()`) und `SynthesisResult` mit `build_repair_instruction()` — analog zum `ValidationResult`. Die Repair-Instruktion enthält Ziel-FPGA, fehlgeschlagene Synthese-Schritte samt Tool-Ausgabe, den erzeugten VHDL-Code und Schutzregeln (Schnittstelle nicht ändern, Simulations- UND Synthesefähigkeit wahren). |
| `Schaltungsagent/src/infrastructure/synthesis/ghdl_synthesis.py` | **Neu**: `GHDLSynthesisService` (Stufe 1). Führt pro Entity `ghdl synth -fexplicit -fsynopsys --out=verilog <files> -e <entity>` aus; die Netlist (stdout) wird als Artefakt nach `<workspace>/build/synthesis/<entity>.v` geschrieben. Die erste synthetisierbare Entity gewinnt; alle Schritte werden transparent in `details["steps"]` protokolliert. Fehlerpfade hängen den DUT-Code (`dut_content`) an. Verifiziert: `ghdl synth --out=verilog` funktioniert auf dem Host. |
| `Schaltungsagent/src/data/fpgas.yaml` | **Neu**: FPGA-Registry mit `gatemate_a2` (CCGM1A2, OSS-CAD-Suite, Wiki `fpga_gatemate`, 100 MHz) und `arty_s7_50` (xc7s50csg324-1, Vivado, Wiki `fpga_xilinx_7series`, 100 MHz). |
| `Schaltungsagent/src/config.py` | `SynthesisConfig` (`enabled`, `default_fpga`, `timeout_seconds`) in `Settings`; neue Funktion `load_fpga_registry()` lädt `fpgas.yaml` in `dict[str, FpgaConfig]` (Standard: `Schaltungsagent/src/data/fpgas.yaml`). |
| `config.yaml` + `Schaltungsagent/src/config.yaml` | Neue Sektion `synthesis:` (`enabled: true`, `default_fpga: gatemate_a2`, `timeout_seconds: 120`). |
| `Schaltungsagent/tests/test_ghdl_synthesis.py` | **Neu**: 6 Regressionstests (synthesierbar → PASS + Netlist-Artefakt; nicht-synthesierbar (`wait for`) → FAIL; Repair-Instruktion; Toolchain-Verfügbarkeit; Registry-Inhalte; Config-Defaults). |

## Durchgeführte Tests

| Test | Ergebnis |
|---|---|
| `pytest Schaltungsagent/tests/` (16 Tests, inkl. 10 Validator-Tests) | **16/16 PASSED** |
| `py_compile` config.py, synthesis_service.py, ghdl_synthesis.py | **OK** |
| Smoke: `load_config().synthesis`, `load_fpga_registry()` → `['gatemate_a2', 'arty_s7_50']`, `GHDLSynthesisService().toolchain_available()` → `True` | **OK** |
| Manuell: Hamming-Decoder synthetisiert → Verilog-Netlist mit `module hamming_decoder` | **PASS** |
| Manuell: `wait for`-Konstrukt → `ghdl synth`-Fehler „expect wait condition" | **FAIL wie erwartet** |

## Bekannte Grenzen (bewusst, Phase 2)

- `ghdl synth` akzeptiert `after`-Klauseln im Prozess (wird ignoriert) — Vendor-Synthese (yosys/Vivado) kann trotzdem scheitern.
- Die Ziel-FPGA-Auswahl (`target`) ist im Port angelegt, aber noch unbenutzt: Stufe 1 ist universell. Der Vendor-Adapter (Phase 2) wird das `target` über die Registry auflösen.
- Kein Skip-Verhalten im Orchestrator: Die „Toolchain fehlt → sauberer Skip"-Logik kommt mit der Orchestrator-Integration (Phase 2).
- Änderungen sind nicht committet.