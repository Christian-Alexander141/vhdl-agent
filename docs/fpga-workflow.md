# FPGA-Workflow: vhdl-agent

## Architektur

```
                 OpenCode Agent
                       │
                       ▼
                  VHDL erzeugen
                       │
              ┌────────┴────────┐
              ▼                 ▼
            GHDL              Vivado
         Simulation          Synthese
              │                 │
              ▼                 ▼
          Testbench         Implementation
                                │
                                ▼
                            Bitstream
                                │
                                ▼
                       Vivado Hardware
                           Manager
                                │
                                ▼
                              JTAG
                                │
                                ▼
                         Arty S7-50 FPGA
```

## Simulation (GHDL)

| Komponente | Wert |
|---|---|
| Tool | GHDL |
| Zweck | VHDL-Syntaxprüfung und Simulation |
| Modus | `--std=08` (VHDL-2008) |

### Simulations-Workflow

```bash
ghdl -a --std=08 src/design.vhd
ghdl -a --std=08 tests/design_tb.vhd
ghdl -e --std=08 design_tb
ghdl -r --std=08 design_tb --stop-time=1us
```

GHDL ist **ausschließlich für die Simulation** zuständig. Es erzeugt **keinen Bitstream** und programmier **kein FPGA**.

## Synthese & Bitstream (Vivado)

| Komponente | Wert |
|---|---|
| Tool | Xilinx Vivado 2026.1 |
| Pfad | `/home/alex/Xilinx/2026.1/Vivado/bin/vivado` |
| Settings | `/home/alex/Xilinx/2026.1/Vivado/settings64.sh` |
| FPGA-Part | `xc7s50csga324-1` (Spartan-7 XC7S50) |
| Modus | Non-Project-Mode (Batch) |

### Build-Workflow

Vivado wird automatisch über den `VivadoBitstreamService` aufgerufen:

1. VHDL-Dateien einlesen
2. `synth_design` (Synthese)
3. `opt_design` / `place_design` / `route_design` (Implementation)
4. `write_bitstream` (Bitstream-Erzeugung)

### Logs & Journals

Vivado-Logs und Journals werden automatisch in den Build-Ordner umgeleitet:

```
projects/<name>/build/bitstream/vivado_logs/
  ├── <entity>.log    # Vivado-Ausgabe
  └── <entity>.jou    # Vivado-Journal (Tcl-History)
```

## Programmierung (Vivado Hardware Manager)

| Komponente | Wert |
|---|---|
| Tool | Vivado Hardware Manager (integriert) |
| Protokoll | JTAG via FTDI FT2232H |
| Schnittstelle | USB-Micro an Arty S7-50 PROG-Port |

### Programmier-Workflow

Vivado programmiert das FPGA direkt über den Hardware Manager:

```
open_hw_manager
connect_hw_server -allow_non_jtag
open_hw_target
set_property PROGRAM.FILE <bitstream.bit> xc7s50_0
program_hw_devices xc7s50_0
```

### JTAG-Verbindung

| Eigenschaft | Wert |
|---|---|
| USB-Gerät | FTDI FT2232C/D/H (0403:6010) |
| JTAG-Target | `localhost:3121/xilinx_tcf/Digilent/210352B7DDABA` |
| Device | `xc7s50_0` |
| Part | `xc7s50` |

### Testergebnis (23. Aug 2026)

```
INFO: [Labtools 27-3164] End of startup status: HIGH
Programming completed successfully!
```

Das FPGA wurde erfolgreich programmiert und läuft.

## OpenFPGA Loader

**Ist OpenFPGA Loader für diesen Workflow erforderlich?**

```
NEIN
```

### Technische Begründung

OpenFPGA Loader ist ein externes, plattformübergreifendes Tool zum Programmieren von FPGAs über JTAG. Es wird häufig verwendet, wenn:

- Kein Vivado/Quartus verfügbar ist (z.B. bei Open-Source-Workflows)
- Nur ein schneller CLI-Befehl gewünscht ist
- Mehrere FPGA-Familien unterstützt werden sollen

**Auf diesem System ist OpenFPGA Loader nicht erforderlich**, weil:

1. **Vivado ist installiert** und enthält den vollständigen Hardware Manager
2. **Vivado kann das Arty S7-50 via JTAG erkennen** (nachgewiesen)
3. **Vivado kann das FPGA programmieren** (nachgewiesen)
4. **Vivado bietet einen Batch-Modus** (`vivado -mode batch -source script.tcl`) für die Automatisierung
5. **Keine zusätzliche Software nötig** — der vollständige Workflow (Synthese → Implementation → Bitstream → Programmierung) läuft über Vivado

### Wann wäre OpenFPGA Loader nötig?

- Wenn Vivado **nicht installiert** wäre
- Wenn ein **Open-Source-Workflow** ohne Vendor-Tools gewünscht wäre
- Wenn **andere FPGA-Familien** (nicht Xilinx) programmiert werden müssten

## Konfiguration

### config.yaml

```yaml
vivado:
  binary: /home/alex/Xilinx/2026.1/Vivado/bin/vivado
  settings_script: /home/alex/Xilinx/2026.1/Vivado/settings64.sh
  timeout_seconds: 600

flash:
  method: vivado_jtag
  timeout_seconds: 120

synthesis:
  enabled: true
  default_fpga: arty_s7_50
  timeout_seconds: 120

ghdl:
  binary: ghdl
  timeout_seconds: 60
```

### fpgas.yaml

```yaml
fpgas:
  arty_s7_50:
    family: xilinx
    part: xc7s50csga324-1
    toolchain: vivado
    wiki: fpga_xilinx_7series
    clock_hz: 100000000
```

## Vollständiger Build-Test

### Testfall: Hamming Decoder

```bash
# 1. GHDL-Simulation
ghdl -a --std=08 projects/hamming74-encoder-01c12c/src/hamming_decoder.vhd
ghdl -a --std=08 projects/hamming74-encoder-01c12c/tests/hamming_decoder_tb.vhd
ghdl -e --std=08 hamming_decoder_tb
ghdl -r --std=08 hamming_decoder_tb --stop-time=1us
# Ergebnis: 128/128 Testfälle bestanden

# 2. Vivado Bitstream
source /home/alex/Xilinx/2026.1/Vivado/settings64.sh
vivado -mode batch -source build_bitstream.tcl
# Ergebnis: hamming_decoder.bit erzeugt (2.1 MB)

# 3. Vivado JTAG Programmierung
vivado -mode batch -source test_program.tcl
# Ergebnis: FPGA programmiert, "startup status: HIGH"
```

## Geänderte Dateien

| Datei | Änderung |
|---|---|
| `config.yaml` | flash: openFPGALoader → vivado_jtag |
| `Schaltungsagent/src/config.yaml` | flash: openFPGALoader → vivado_jtag |
| `Schaltungsagent/src/config.py` | FlashConfig: method statt binary/board |
| `Schaltungsagent/src/main.py` | VivadoFlashService statt OpenFPGALoaderFlashService |
| `Schaltungsagent/src/api_server.py` | VivadoFlashService statt OpenFPGALoaderFlashService |
| `Schaltungsagent/src/infrastructure/synthesis/__init__.py` | VivadoFlashService exportiert |
| `Schaltungsagent/src/infrastructure/synthesis/vivado_synthesis.py` | Logs nach vivado_logs/ umleiten |
| `.gitignore` | vivado_logs/ hinzugefügt |

## Neu erstellte Dateien

| Datei | Zweck |
|---|---|
| `Schaltungsagent/src/infrastructure/synthesis/vivado_flash.py` | VivadoFlashService — JTAG-Programmierung via Vivado |
| `setup_vivado_env.sh` | Vivado-Umgebung laden |
| `docs/vivado-setup.md` | Vivado-Setup-Dokumentation |
| `docs/fpga-workflow.md` | Diese Datei |
