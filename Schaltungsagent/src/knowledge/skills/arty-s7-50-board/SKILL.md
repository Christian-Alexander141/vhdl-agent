# Skill: arty-s7-50-board
# Beschreibung: Arty S7-50 board facts, pinout, clock structure, XDC rules, JTAG/UART pins.
# Lade diesen Skill, wenn Pin-Constraints (XDC) für Arty S7-50 erzeugt werden, das Top-Level-Pinout geplant wird oder Board-spezifische Hardware-Fragen geklärt werden.
# Quelle: Arty_S7-50_RAG_Wissenspaket.pdf, Kapitel 2, 3, 5, 6, 8, 9

## Board Overview
- **FPGA**: Xilinx Spartan-7 XC7S50CSGA324-1
- **Taktquellen**:
  - 12 MHz On-Board Oszillator → Pin **F14** (LVCMOS33) – **allgemeiner Systemtakt**
  - 100 MHz DDR3-Referenztakt → Pins **R2** (P) / **T2** (N) (SSTL135) – **nur für DDR3/MIG**, nicht als User-Clock ohne MMCM
- **User I/O**:
  - 4 LEDs: E18, F13, E13, H15 (LVCMOS33, active HIGH)
  - 4 Buttons: BTN0=G15, BTN1=H13, BTN2=J16, BTN3=J15 (LVCMOS33, active HIGH)
  - 4 Switches: SW0=H14, SW1=G14, SW2=K18, SW3=K17 (LVCMOS33)
  - 2 Pmods (JA, JB) – 2×8 Pins, 3.3V
- **USB-UART** (FTDI):
  - RX (FPGA ← PC): **R12** (LVCMOS33)
  - TX (FPGA → PC): **V12** (LVCMOS33)
- **JTAG**: Standard 4-Pin (TCK, TMS, TDI, TDO) – über On-Board FTDI oder externer JTAG-HS2/HS3

## Pin Assignment Rules (für XDC-Generator)
| Port Name Patterns (case-insensitive) | Direction | Pin | IOSTANDARD | Note |
|---|---|---|---|---|
| `CLK`, `CLK_100MHZ`, `SYS_CLK`, `CLOCK` | in (1 bit) | R2 | LVCMOS33* | Generator nutzt R2; Board-Fakt: SSTL135 (DDR3) → **Warning** |
| `RESET`, `RST`, `RESET_N`, `RST_N` | in (1 bit) | G15 (BTN0) | LVCMOS33 | `_N` → invertierte Polarität |
| `ENABLE`, `EN` | in (1 bit) | H14 (SW0) | LVCMOS33 | |
| `LOAD`, `LD` | in (1 bit) | J16 (BTN2) | LVCMOS33 | |
| Andere **Ausgänge** (alphabetisch) | out | E18, F13, E13, H15 | LVCMOS33 | Max 8 Bits (4 LEDs × 2 Bit falls Vektor) |
| Andere **Eingänge** (z. B. `uart_rx`) | in | – | – | Kein Pin durch Generator |

> *Known deviation: Generator assigns R2 with LVCMOS33. Board fact says R2 is SSTL135 (DDR3 clock). This triggers `BOARD_FACT_WARNING` rule 1.

## RAG-Regeln (aus Wissenspaket Abschnitt 8)
1. Do not choose a top entity by first-file order
2. Do not generate a real board build without XDC constraints
3. Do not suppress NSTD-1 or UCIO-1 as a workaround
4. System clock is 12 MHz at F14 (LVCMOS33); 100 MHz at R2/T2 is SSTL135 for DDR3 only
5. Only four user LEDs: E18, F13, E13, H15
6. BTN0-3 are active HIGH (G15, H13, J16, J15)
7. UART pins: RX=R12, TX=V12 (LVCMOS33)
8. Pmod JA pins N14/G13/F15/E15 are NOT LEDs

## XDC Template (manuell, wenn Generator nicht passt)
```tcl
# System clock (12 MHz at F14)
set_property -dict {PACKAGE_PIN F14 IOSTANDARD LVCMOS33} [get_ports sys_clk]
create_clock -name sys_clk -period 83.333 [get_ports sys_clk]

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
set_property -dict {PACKAGE_PIN H13 IOSTANDARD LVCMOS33} [get_ports btn1]
set_property -dict {PACKAGE_PIN J15 IOSTANDARD LVCMOS33} [get_ports btn3]
```

## Common Mistakes
| Fehler | Folge | Korrektur |
|---|---|---|
| R2 als 100 MHz User-Clock | Timing-Analyse falsch, MMCM nötig | 12 MHz an F14 nutzen, MMCM für 50/100 MHz |
| Pmod-Pins als LEDs | Hardware funktioniert nicht | Nur E18,F13,E13,H15 für LEDs |
| Kein `create_clock` | Keine Timing-Analyse | Immer `create_clock` für jeden Takt-Port |
| NSTD-1/UCIO-1 unterdrückt | Bitstream lädt, Hardware unvorhersehbar | Echte Constraints schreiben, nicht Severity ändern |

## Referenz
- Pinout-Tabelle: `references/pin_table.md` (detaillierte Pin-Liste aller FPGA-Pins)