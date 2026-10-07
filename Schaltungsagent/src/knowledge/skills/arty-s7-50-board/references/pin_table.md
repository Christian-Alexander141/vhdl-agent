# Arty S7-50 Pin Table (Reference)
# Quelle: Arty_S7-50_RAG_Wissenspaket.pdf, Digilent Arty S7 Reference Manual
# Vollständige FPGA-Pin-Belegung für XC7S50CSGA324

## Clock Pins
| Schematic Name | FPGA Pin | I/O Standard | Notes |
|---|---|---|---|
| CLK12MHz (12 MHz Osc) | F14 | LVCMOS33 | General purpose system clock |
| DDR3_CLK_P | R2 | SSTL135 | DDR3 reference clock (positive) |
| DDR3_CLK_N | T2 | SSTL135 | DDR3 reference clock (negative) |

## User LEDs (4x)
| LED | FPGA Pin | I/O Standard | Schematic Net |
|---|---|---|---|
| LD0 | E18 | LVCMOS33 | LED0 |
| LD1 | F13 | LVCMOS33 | LED1 |
| LD2 | E13 | LVCMOS33 | LED2 |
| LD3 | H15 | LVCMOS33 | LED3 |

## Push Buttons (4x, Active HIGH)
| Button | FPGA Pin | I/O Standard | Schematic Net |
|---|---|---|---|
| BTN0 | G15 | LVCMOS33 | BTN0 |
| BTN1 | H13 | LVCMOS33 | BTN1 |
| BTN2 | J16 | LVCMOS33 | BTN2 |
| BTN3 | J15 | LVCMOS33 | BTN3 |

## Slide Switches (4x)
| Switch | FPGA Pin | I/O Standard | Schematic Net |
|---|---|---|---|
| SW0 | H14 | LVCMOS33 | SW0 |
| SW1 | G14 | LVCMOS33 | SW1 |
| SW2 | K18 | LVCMOS33 | SW2 |
| SW3 | K17 | LVCMOS33 | SW3 |

## Pmod JA (8 pins, 3.3V)
| Pmod Pin | FPGA Pin | Schematic Net |
|---|---|---|
| JA1 | N14 | JA1 |
| JA2 | G13 | JA2 |
| JA3 | F15 | JA3 |
| JA4 | E15 | JA4 |
| JA7 | K16 | JA7 |
| JA8 | J13 | JA8 |
| JA9 | H16 | JA9 |
| JA10 | H13 | JA10 |

## Pmod JB (8 pins, 3.3V)
| Pmod Pin | FPGA Pin | Schematic Net |
|---|---|---|
| JB1 | T10 | JB1 |
| JB2 | T11 | JB2 |
| JB3 | U12 | JB3 |
| JB4 | V12 | JB4 |
| JB7 | T9 | JB7 |
| JB8 | U9 | JB8 |
| JB9 | V9 | V9 |
| JB10 | V10 | V10 |

## USB-UART (FTDI)
| Signal | FPGA Pin | I/O Standard | Direction (FPGA view) |
|---|---|---|---|
| UART_RX | R12 | LVCMOS33 | Input |
| UART_TX | V12 | LVCMOS33 | Output |

## JTAG (On-board FTDI / External)
| Signal | FPGA Pin | Notes |
|---|---|---|
| TCK | - | Dedicated JTAG pins (not user I/O) |
| TMS | - | Dedicated JTAG pins |
| TDI | - | Dedicated JTAG pins |
| TDO | - | Dedicated JTAG pins |

## DDR3 Memory (not for general user I/O)
| Signal Group | Pins | I/O Standard |
|---|---|---|
| Address/Command | Multiple | SSTL135 |
| Data/Strobe | Multiple | SSTL135 |
| Clock | R2/T2 | SSTL135 Diff |

## Important Notes
1. **R2/T2 are SSTL135** – Do not use as LVCMOS33 user clock without MMCM
2. **F14 is the only general-purpose LVCMOS33 clock** (12 MHz)
3. **Only 4 user LEDs** – Pmod JA pins (N14, G13, F15, E15) are NOT LEDs
4. **Buttons are Active HIGH** – pressed = '1'
5. **UART pins fixed** – R12 (RX), V12 (TX) via FTDI bridge