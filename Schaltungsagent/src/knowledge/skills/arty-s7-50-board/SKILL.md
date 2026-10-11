# Skill: arty-s7-50-board
# Beschreibung: Arty S7-50 board facts, pinout, clock structure, XDC rules, JTAG/UART pins.
# Lade diesen Skill, wenn Pin-Constraints (XDC) für Arty S7-50 erzeugt werden, das Top-Level-Pinout geplant wird oder Board-spezifische Hardware-Fragen geklärt werden.
# Quelle: Arty_S7-50_RAG_Wissenspaket.pdf, Kapitel 2, 3, 5, 6, 8, 9; Takt, Taster und Schalter
# korrigiert 2026-10-11 nach dem offiziellen Digilent Arty-S7-50-Master.xdc (Rev. E).

## Board Overview
- **FPGA**: Xilinx Spartan-7 XC7S50CSGA324-1
- **Taktquellen**:
  - 100 MHz → Pin **R2** (IOSTANDARD **SSTL135**, Bank 34 mit 1,35 V; Master-XDC: CLK100MHZ) – Standard des XDC-Generators und der Registry (100 MHz)
  - 12 MHz → Pin **F14** (LVCMOS33; Master-XDC: CLK12MHZ) – Alternative
  - Das Taktfrequenz-Generic des Entwurfs muss zum gewählten Takt passen.
- **User I/O**:
  - 4 LEDs: led[0..3] = LD2..LD5 = E18, F13, E13, H15 (LVCMOS33, active HIGH)
  - 4 Buttons: BTN0=G15, BTN1=K16, BTN2=J16, BTN3=H13 (LVCMOS33, active HIGH)
  - 4 Switches: SW0=H14, SW1=H18, SW2=G18 (LVCMOS33), SW3=M5 (**SSTL135**, Bank 34)
  - Bank 34 (R2, M5) braucht `set_property INTERNAL_VREF 0.675 [get_iobanks 34]` (setzt das Build-Skript immer)
  - 2 Pmods (JA, JB) – 2×8 Pins, 3.3V
- **USB-UART** (FTDI):
  - RX (FPGA ← PC): **R12** (LVCMOS33)
  - TX (FPGA → PC): **V12** (LVCMOS33)
- **JTAG**: Standard 4-Pin (TCK, TMS, TDI, TDO) – über On-Board FTDI oder externer JTAG-HS2/HS3

## Pin Assignment Rules (für XDC-Generator)
| Port Name Patterns (case-insensitive) | Direction | Pin | IOSTANDARD | Note |
|---|---|---|---|---|
| `CLK`, `CLK_100MHZ`, `SYS_CLK`, `CLOCK` | in (1 bit) | R2 | SSTL135 | 100 MHz |
| `RESET`, `RST`, `RESET_N`, `RST_N` | in (1 bit) | G15 (BTN0) | LVCMOS33 | `_N` → invertierte Polarität |
| `ENABLE`, `EN` | in (1 bit) | H14 (SW0) | LVCMOS33 | |
| `LOAD`, `LD` | in (1 bit) | J16 (BTN2) | LVCMOS33 | |
| `sw…`, `btn…`, `led…` (Board-Namen) | in/out | bitweise: SW0–3, BTN0–3, LD2–LD5 | wie oben | |
| Andere **Ausgänge** (alphabetisch) | out | E18, F13, E13, H15 | LVCMOS33 | Max 8 Bits (4 LEDs × 2 Bit falls Vektor) |
| Andere **Eingänge** (z. B. `uart_rx`) | in | – | – | Kein Pin durch Generator |


## RAG-Regeln (aus Wissenspaket Abschnitt 8)
1. Do not choose a top entity by first-file order
2. Do not generate a real board build without XDC constraints
3. Do not suppress NSTD-1 or UCIO-1 as a workaround
4. Clocks: 100 MHz at R2 (SSTL135) or 12 MHz at F14 (LVCMOS33); the clock-frequency generic must match
5. Only four user LEDs: E18, F13, E13, H15 (LD2–LD5)
6. BTN0-3 are active HIGH (G15, K16, J16, H13); SW0-3: H14, H18, G18, M5 (SSTL135)
7. UART pins: RX=R12, TX=V12 (LVCMOS33)
8. Pmod JA pins N14/G13/F15/E15 are NOT LEDs

## XDC Template (manuell, wenn Generator nicht passt)
```tcl
# System clock: 100 MHz at R2 (SSTL135) ...
set_property -dict {PACKAGE_PIN R2 IOSTANDARD SSTL135} [get_ports clk]
create_clock -name sys_clk -period 10.000 [get_ports clk]
# ... or 12 MHz at F14 instead:
# set_property -dict {PACKAGE_PIN F14 IOSTANDARD LVCMOS33} [get_ports clk]
# create_clock -name sys_clk -period 83.333 [get_ports clk]

# Reset (BTN0, active high)
set_property -dict {PACKAGE_PIN G15 IOSTANDARD LVCMOS33} [get_ports rst]

# LEDs (4 user LEDs)
set_property -dict {PACKAGE_PIN E18 IOSTANDARD LVCMOS33} [get_ports led[0]]
set_property -dict {PACKAGE_PIN F13 IOSTANDARD LVCMOS33} [get_ports led[1]]
set_property -dict {PACKAGE_PIN E13 IOSTANDARD LVCMOS33} [get_ports led[2]]
set_property -dict {PACKAGE_PIN H15 IOSTANDARD LVCMOS33} [get_ports led[3]]

# UART (FTDI)
set_property -dict {PACKAGE_PIN R12 IOSTANDARD LVCMOS33} [get_ports uart_rx]
set_property -dict {PACKAGE_PIN V12 IOSTANDARD LVCMOS33} [get_ports uart_tx]

# Buttons (if used)
set_property -dict {PACKAGE_PIN K16 IOSTANDARD LVCMOS33} [get_ports {btn[1]}]
set_property -dict {PACKAGE_PIN J16 IOSTANDARD LVCMOS33} [get_ports {btn[2]}]
set_property -dict {PACKAGE_PIN H13 IOSTANDARD LVCMOS33} [get_ports {btn[3]}]

# Switches (if used)
set_property -dict {PACKAGE_PIN H14 IOSTANDARD LVCMOS33} [get_ports {sw[0]}]
set_property -dict {PACKAGE_PIN H18 IOSTANDARD LVCMOS33} [get_ports {sw[1]}]
set_property -dict {PACKAGE_PIN G18 IOSTANDARD LVCMOS33} [get_ports {sw[2]}]
set_property -dict {PACKAGE_PIN M5  IOSTANDARD SSTL135}  [get_ports {sw[3]}]
```

## Common Mistakes
| Fehler | Folge | Korrektur |
|---|---|---|
| R2 mit LVCMOS33 | Bank 34 läuft mit 1,35 V: IO-Standard-Fehler | R2 (und M5) immer mit SSTL135 |
| Taktfrequenz-Generic passt nicht zum Takt-Pin | Zeiten falsch (12 vs. 100 MHz: Faktor 8) | Generic zum gewählten Pin setzen |
| Pmod-Pins als LEDs | Hardware funktioniert nicht | Nur E18,F13,E13,H15 für LEDs |
| Kein `create_clock` | Keine Timing-Analyse | Immer `create_clock` für jeden Takt-Port |
| NSTD-1/UCIO-1 unterdrückt | Bitstream lädt, Hardware unvorhersehbar | Echte Constraints schreiben, nicht Severity ändern |

## Referenz
- Pinout-Tabelle: `references/pin_table.md` (detaillierte Pin-Liste aller FPGA-Pins)