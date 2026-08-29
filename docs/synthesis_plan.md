# Synthese-Plan: getestetes VHDL → FPGA

Datum: 2026-08-16
Status: Planung abgeschlossen, Umsetzung offen
Ziel-FPGAs: **CologneChip GateMate A2** (CCGM1A2) und **Digilent Arty S7-50** (Xilinx Spartan-7 XC7S50CSGA324)

---

## 1. Zielbild (3 Stufen)

| Stufe | Beschreibung | Toolchain | Status |
|---|---|---|---|
| 1 | Synthese-Validierung: Ist der Code synthesierbar? Netlist als Artefakt | `ghdl synth` | **Heute nutzbar** (verifiziert) |
| 2 | Vendor-Synthese: P&R, Timing-Report, Bitstream | GateMate: OSS CAD Suite / Xilinx: Vivado | Toolchain-Installation nötig |
| 3 | Programmierung: Bitstream aufs Board | GateMate: openFPGALoader / Xilinx: Vivado Hardware Manager | Board + USB nötig |

**Kernprinzip (analog zur Verifikation):** Ein Projekt ist erst `COMPLETED`, wenn die
Synthese erfolgreich durchgelaufen ist. Synthetisch korrekter VHDL-Code ist nicht
automatisch ein synthesierbarer VHDL-Code.

## 2. Verifizierte Fakten

### GateMate A2 (CCGM1A2)
- Toolchain ist **komplett Open Source**: [OSS CAD Suite](https://github.com/YosysHQ/oss-cad-suite-build)
  (Yosys + GHDL-Plugin, nextpnr-himbaechel, gmpack, openFPGALoader). Linux-nativ, kein Wine.
- VHDL-Flow (laut CologneChip-Quickstart, 2026):
  ```text
  ghdl synth -fexplicit -fsynopsys --out=verilog <FILES> -e <top_entity>   # VHDL → Verilog-Netlist
  yosys -ql <log> -p 'read_verilog -defer -sv <netlist>.v;
                      synth_gatemate -top <top> -luttree -nomx8;
                      write_json <netlist>.json'
  nextpnr-himbaechel -l <log> --device=CCGM1A2 --json <netlist>.json \
                     -o ccf=<pins>.ccf -o out=impl.txt --sdc <clk>.sdc --router router2
  gmpack ...                                                                 # Bitstream
  openFPGALoader <bitstream>                                                 # Programmierung
  ```
- Verifiziert auf diesem Host: `ghdl synth -fexplicit -fsynopsys --out=verilog <file> -e <top>` ✅
- Bekannte Stolpersteine (Quelle: NEORV32-GateMate-Diskussion):
  - GHDL-Plugin braucht IEEE-Bibliotheken relativ zum Yosys-Binary (Hardcoded Paths)
  - Die eigentliche Bitstream-Datei ist die `.cfg`-Datei, nicht `.bit`
  - CCF (Pin-Constraints) und SDC (Timing) sind optional, aber ohne Timing-Check

### Digilent Arty S7-50 (Xilinx Spartan-7)
- FPGA-Part: **XC7S50CSGA324** (Vivado: `xc7s50csg324-1`)
- Vivado **WebPACK** (kostenlos) unterstützt Spartan-7
- Board-Daten:
  - 100 MHz Referenztakt, 4 Switches, 4 Buttons, 4 LEDs, 2 RGB-LEDs, 4× Pmod, Arduino-Header
  - 256 MB DDR3L, 128 Mbit Quad-SPI Flash
  - USB-JTAG-Programmierung (Micro-B), USB-UART-Bridge
- Board-Files: Digilent [vivado-boards](https://github.com/Digilent/vivado-boards) → `new/board_files/arty-s7-50`
- Master-Constraints: Digilent [digilent-xdc](https://github.com/Digilent/digilent-xdc) → `Arty-S7-50-Master.xdc`
- **Nicht installiert** auf diesem Host → Stufe 2 für Xilinx erst nach Vivado-Installation

## 3. Architektur (hexagonal, konsistent mit Bestand)

```
SynthesisService (Port, analog ValidationService)
 ├── GHDLSynthesisService      → Stufe 1: Synthesizierbarkeit + Netlist (universell, gratis)
 ├── GateMateSynthesisService  → Stufe 2: yosys → nextpnr-himbaechel → gmpack → .cfg
 └── VivadoSynthesisService    → Stufe 2: Batch-Tcl synth_design → write_bitstream
```

- `SynthesisResult` (passed, target, artifacts, steps, errors, reports)
  - `build_repair_instruction()` — gleiche Mechanik wie `ValidationResult`
- FPGA-Registry `fpgas.yaml`:

```yaml
fpgas:
  gatemate_a2:
    family: gatemate
    part: CCGM1A2
    toolchain: oss-cad-suite
    wiki: fpga_gatemate
    clock: 100000000      # Hz (typisch EVK)
  arty_s7_50:
    family: xilinx
    part: xc7s50csg324-1
    board_files: arty-s7-50
    toolchain: vivado
    wiki: fpga_xilinx_7series
    clock: 100000000      # Hz (100-MHz-Referenztakt)
```

- Konfiguration: `config.yaml` → `synthesis.default_fpga: gatemate_a2` (bzw. `arty_s7_50`),
  optional pro Projekt überschreibbar

## 4. Workflow-Integration (automatisch)

```
TESTING → SYNTHESIZING → (SYNTHESIS_REPAIRING ⇄ SYNTHESIZING) → COMPLETED
```

- Nach erfolgreicher GHDL-Validierung startet die Synthese automatisch
- Keine Toolchain konfiguriert/gefunden → Synthese wird sauber übersprungen (kein Fehler)
- Repair-Schleife analog `_test_and_repair`: Synthese-Logs + Wiki-Ausschnitte + DUT-Code
  gehen in die OpenCode-Reparatur-Instruktion; es darf nur Synthese-relevanter Code
  geändert werden (Regeln analog zu den Testbench-Cheating-Regeln)
- Neue States in `state_machine.py`: `SYNTHESIZING`, `SYNTHESIS_REPAIRING`
- Artefakte landen in `projects/<id>/build/synthesis/`

## 5. Wiki / Wissen (RAG pro FPGA)

- Bestehende RAG-Infrastruktur wiederverwenden (qdrant + Chunker + Embeddings)
- Eine Collection pro FPGA-Familie: `fpga_gatemate`, `fpga_xilinx_7series`
- Inhalte:
  - Toolchain-Quickstarts (CologneChip, Digilent)
  - CCF/SDC/XDC-Syntax und Pinout-Dokumentation (Arty-S7-50-Master.xdc, GateMate-EVK-Pinout)
  - Bekannte Fehlerbilder und Workarounds
  - Board-Referenzhandbücher (Arty S7 Reference Manual, GateMate Datasheet)
- Der Reparatur-Agent erhält relevante Wiki-Ausschnitte per RAG im Kontext

## 6. Umsetzungsreihenfolge

### Phase 1 — Grundgerüst (jetzt) ✅ abgeschlossen
- [x] `SynthesisService`-Port + `SynthesisResult` (analog ValidationService)
- [x] `GHDLSynthesisService`: `ghdl synth --out=edif/verilog`, Netlist-Artefakt, Steps/Errors
- [x] `fpgas.yaml`-Registry + `synthesis.default_fpga` in config.yaml
- [x] Regressionstests:
  - synthesierbarer DUT → PASS
  - nicht-synthesierbarer DUT (`wait for` im Prozess) → FAIL
- [ ] kein Synthese-Target konfiguriert → sauberer Skip (Orchestrator-Logik, Phase 2)

### Phase 2 — GateMate (Stufe 2)
- [ ] OSS CAD Suite installieren (User oder dokumentierte Anleitung)
- [ ] `GateMateSynthesisService`: ghdl→Verilog→yosys→nextpnr→gmpack
- [ ] Wiki-Collection `fpga_gatemate` befüllen (Quickstart, CCF/SDC, bekannte Fehler)
- [ ] Repair-Loop + State Machine + Orchestrator-Integration
- [ ] Test: Hamming-Decoder für GateMate A2 synthetisieren (echte Toolchain)

### Phase 3 — Arty S7 (Stufe 2, nach Vivado-Installation)
- [ ] `VivadoSynthesisService`: Batch-Tcl (synth_design, write_bitstream)
- [ ] Wiki-Collection `fpga_xilinx_7series` (Arty-S7-50-Master.xdc, Vivado-Guides)
- [ ] Test: Hamming-Decoder für Arty S7-50 → Bitstream

### Phase 4 — API/Dashboard + Programmierung (Stufe 3)
- [ ] API: Synthese-Status im Projekt (analog Test-Ergebnisse), optionaler „Synthesize"-Button
- [ ] Dashboard: Synthese-Ergebnisse/Artefakte anzeigen
- [ ] Programmierung: openFPGALoader (GateMate), Vivado hw_manager (Arty)

## 7. Offene Punkte

- [ ] OSS CAD Suite installieren (GateMate-Toolchain) — User oder dokumentierte Schritte
- [ ] Vivado installieren (Arty S7-50, WebPACK) — großer Download, separat planen
- [ ] GateMate-Board vorhanden? (EVK für spätere Programmierung)
- [ ] Zielauswahl: zunächst Default via `config.yaml`, später optional LLM-Extraktion
      aus der Benutzeranforderung („synthetisiere für GateMate A2")