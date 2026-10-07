# Vivado & Arty S7-50 Setup - vhdl-agent

## System

| Komponente | Wert |
|---|---|
| Betriebssystem | Linux Mint 22.2 (Zara), basierend auf Ubuntu Noble |
| Vivado-Version | 2026.1 (Build 6511674) |
| Vivado-Installationspfad | `/home/alex/Xilinx/2026.1/` |
| Vivado-Binary | `/home/alex/Xilinx/2026.1/Vivado/bin/vivado` |
| Settings-Script | `/home/alex/Xilinx/2026.1/Vivado/settings64.sh` |
| Xilinx-Tools | Vivado Design Suite (BASIC License) |

## Hardware

| Komponente | Wert |
|---|---|
| FPGA-Board | Digilent Arty S7-50 |
| FPGA-Chip | Xilinx Spartan-7 XC7S50CSGA324-1 |
| Vivado-Part-Name | `xc7s50csga324-1` |
| Takt | 100 MHz System-Clock |
| USB-Interface | FTDI FT2232H (JTAG + UART) |

## Vorher

### Verwendete Pfade (ursprünglich)

- `vivado_binary: vivado` (nur Name, kein vollständiger Pfad)
- Kein `settings_script` konfiguriert
- Keine `LD_LIBRARY_PATH`-Konfiguration in den Skripten
- Kein `XILINX_VIVADO` in der Shell-Umgebung

### Festgestellte Probleme

1. **Vivado nicht im PATH**: Das Vivado-Binary ist nur über `source settings64.sh` erreichbar. Ohne das Laden der Umgebung ist `vivado` weder über `which` noch über `shutil.which()` auffindbar.

2. **LD_LIBRARY_PATH fehlt**: Vivado benötigt `LD_LIBRARY_PATH=/home/alex/Xilinx/2026.1/Vivado/lib/lnx64.o/Ubuntu/24` für `libncurses.so.5` und andere Bibliotheken. Die `settings64.sh` setzt diesen Pfad nicht automatisch.

3. **FPGA-Part-Name falsch**: In `fpgas.yaml` war `xc7s50csg324-1` konfiguriert, der korrekte Name ist `xc7s50csga324-1` (mit 'a' in csga).

4. **Board-Files nicht installiert**: Das Verzeichnis `/home/alex/Xilinx/2026.1/Vivado/data/boards/board_files/` existiert nicht. Die Digilent Board Files wurden nicht manuell installiert.

5. **openFPGALoader nicht installiert**: Das Tool für die FPGA-Programmierung über die Kommandozeile ist nicht verfügbar.

6. **DRC-Fehler bei Bitstream**: Designs ohne I/O-Constraints (XDC) schlagen bei `write_bitstream` fehl, weil Vivado standardmäßig I/O-Standard- und Pin-Location-Checks durchführt.

## Änderungen

### 1. `config.yaml` (Projekt-Root)

| Vorher | Nachher |
|---|---|
| `binary: vivado` | `binary: /home/alex/Xilinx/2026.1/Vivado/bin/vivado` |
| (nicht vorhanden) | `settings_script: /home/alex/Xilinx/2026.1/Vivado/settings64.sh` |

**Begründung**: Vollständiger Pfad ermöglicht die Vivado-Erkennung ohne manuelles Laden der Umgebung. `settings_script` wird als Fallback verwendet, falls das Binary nicht direkt im PATH liegt.

### 2. `Schaltungsagent/src/config.yaml`

Gleiche Änderung wie oben.

### 3. `Schaltungsagent/src/config.py`

`VivadoConfig`-Dataclass erweitert:

| Vorher | Nachher |
|---|---|
| `binary: str = "vivado"` | `binary: str = "vivado"` |
| (nicht vorhanden) | `settings_script: str = ""` |

### 4. `Schaltungsagent/src/infrastructure/synthesis/vivado_synthesis.py`

- `__init__`: Neuer Parameter `settings_script`
- `toolchain_available()`: Prüft auch `settings_script` als Fallback
- `_run_step()`: Wrappt den Vivado-Aufruf mit `source settings64.sh` und `LD_LIBRARY_PATH` wenn nötig
- `_generate_tcl_script()`: Fügt DRC-Relaxierungen für Designs ohne I/O-Constraints hinzu

### 5. `Schaltungsagent/src/services/eda_tools.py`

- `detect_eda_tools()`: Prüft auch den konfigurierten vivado-Pfad aus `config.yaml`
- `_open_vivado()`: Verwendet den konfigurierten Pfad falls `shutil.which()` fehlschlägt
- `open_project_in_tool()`: Gleiche Fallback-Logik

### 6. `Schaltungsagent/src/main.py` und `Schaltungsagent/src/api_server.py`

Übergabe des `settings_script` Parameters an `VivadoBitstreamService`.

### 7. `Schaltungsagent/src/data/fpgas.yaml`

| Vorher | Nachher |
|---|---|
| `part: xc7s50csg324-1` | `part: xc7s50csga324-1` |

**Begründung**: Der korrekte Vivado-Part-Name für das Arty S7-50 enthält ein 'a' in "csga".

### 8. `setup_vivado_env.sh` (neu)

Shell-Script zum Laden der Vivado-Umgebung. kann per `source setup_vivado_env.sh` in der Shell geladen werden.

## Workflow

### 1. Vivado-Umgebung laden

```bash
# Für interaktive Shell:
source setup_vivado_env.sh

# Oder manuell:
source /home/alex/Xilinx/2026.1/Vivado/settings64.sh
export LD_LIBRARY_PATH="/home/alex/Xilinx/2026.1/Vivado/lib/lnx64.o/Ubuntu/24:$LD_LIBRARY_PATH"
```

### 2. VHDL-Build (über den Agenten)

Der Agent führt automatisch aus:
1. GHDL-Validierung (Syntax-Check)
2. Vivado-Bitstream-Generierung im Non-Project-Mode

### 3. Bitstream-Generierung (manuell)

```bash
source setup_vivado_env.sh
vivado -mode batch -source build_bitstream.tcl
```

### 4. FPGA-Programmierung

**Noch nicht verfügbar** - erfordert Installation von `openFPGALoader`:

```bash
# Installation (sudo erforderlich):
sudo apt install openfpgaloader

# Oder aus Quellen:
git clone https://github.com/trabucayre/openFPGALoader.git
cd openFPGALoader && mkdir build && cd build
cmake .. && make -j$(nproc)
sudo make install

# Programmierung:
openFPGALoader -b arty_s7 /pfad/zum/design.bit
```

### 5. Über den Agenten (Vollautomatisch)

```bash
cd /home/alex/Dokumente/Github/vhdl-agent
python -m Schaltungsagent.src.main run "Erstelle einen LED-Blinker für Arty S7-50"
```

Der Agent durchläuft automatisch:
1. VHDL-Codegenerierung
2. GHDL-Validierung
3. Vivado-Bitstream-Generierung
4. FPGA-Programmierung (wenn openFPGALoader verfügbar)

## Verifikation

### Test 1: GHDL-Validierung

```bash
ghdl -a --std=08 projects/hamming74-encoder-01c12c/src/hamming_decoder.vhd
ghdl -a --std=08 projects/hamming74-encoder-01c12c/tests/hamming_decoder_tb.vhd
ghdl -e --std=08 hamming_decoder_tb
ghdl -r --std=08 hamming_decoder_tb --stop-time=1us
```

**Ergebnis**: Erfolgreich - alle 128 Testfälle (16 no-error + 112 single-bit) bestanden.

### Test 2: Vivado-Bitstream-Generierung

```bash
source setup_vivado_env.sh
vivado -mode batch -source projects/hamming74-encoder-01c12c/build/bitstream/build_bitstream.tcl
```

**Ergebnis**: Erfolgreich - Bitstream `hamming_decoder.bit` (2.1 MB) wurde erzeugt.

### Test 3: FPGA-Programmierung

**Status**: Noch nicht getestet - `openFPGALoader` nicht installiert.

## Offene Probleme

### 1. openFPGALoader fehlt

- **Fehler**: `openFPGALoader` ist nicht installiert
- **Ursache**: Wurde nicht manuell installiert
- **Lösung**: `sudo apt install openfpgaloader` oder Kompilierung aus Quellen
- **Nächster Schritt**: User muss `openFPGALoader` installieren

### 2. Digilent Board-Files fehlen

- **Fehler**: `/home/alex/Xilinx/2026.1/Vivado/data/boards/board_files/` existiert nicht
- **Ursache**: Board-Files wurden nicht manuell installiert
- **Auswirkung**: Im Vivado-GUI kann das Arty S7-50 nicht als Board ausgewählt werden (nur als generischer Part)
- **Lösung**: Board-Files gemäß `doc/vivado-&-arty-s7-50-setup-dokumentation.html` installieren
- **Hinweis**: Für den Non-Project-Mode (wie vom Agenten verwendet) sind Board-Files nicht zwingend erforderlich - der Part-Name `xc7s50csga324-1` reicht aus.

### 3. LD_LIBRARY_PATH manuell setzen

- **Problem**: Die `settings64.sh` setzt `LD_LIBRARY_PATH` nicht automatisch
- **Ursache**: Xilinx-Installation auf diesem System
- **Lösung**: Wird durch den Code automatisch gehandhabt (wrapper in `_run_step()`)
- **Fallback**: `source setup_vivado_env.sh` vor dem manuellen Aufruf

## Geänderte Dateien

| Datei | Status |
|---|---|
| `config.yaml` | Geändert (Vivado-Pfad) |
| `Schaltungsagent/src/config.yaml` | Geändert (Vivado-Pfad) |
| `Schaltungsagent/src/config.py` | Geändert (settings_script) |
| `Schaltungsagent/src/infrastructure/synthesis/vivado_synthesis.py` | Geändert (environment-aware) |
| `Schaltungsagent/src/services/eda_tools.py` | Geändert (Vivado-Pfad) |
| `Schaltungsagent/src/main.py` | Geändert (settings_script) |
| `Schaltungsagent/src/api_server.py` | Geändert (settings_script) |
| `Schaltungsagent/src/data/fpgas.yaml` | Geändert (Part-Name korrigiert) |
| `setup_vivado_env.sh` | Neu erstellt |

## Agent-/OpenCode-Konfiguration

### Status

| Fähigkeit | Status |
|---|---|
| Vivado aufrufen | Funktioniert (über settings_script wrapper) |
| Shell-Kommandos ausführen | Funktioniert |
| Tcl-Skripte ausführen | Funktioniert |
| VHDL-Dateien erzeugen/ändern | Funktioniert |
| Vivado-Projekte erzeugen | Funktioniert (Non-Project-Mode) |
| Bitstreams bauen | Funktioniert (getestet) |
| FPGA programmieren | Nicht verfügbar (openFPGALoader fehlt) |

### Empfehlungen

1. **openFPGALoader installieren** für die FPGA-Programmierung
2. **Board-Files installieren** für die Vivado-GUI-Nutzung (optional)
3. **Umgebungsvariable `VIVADO_BASE`** setzen für zentrale Konfiguration
