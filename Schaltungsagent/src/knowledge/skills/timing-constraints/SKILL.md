# Skill: timing-constraints
# Beschreibung: Timing analysis, setup/hold, clock constraints, Slack, Vivado XDC constraining.
# Lade diesen Skill, wenn Timing-Constraints (XDC) geschrieben, geprüft oder ein Timing-Fehler analysiert wird.
# Quelle: eds_erg_04_timing.pdf (Timing-Analyse, Setup/Hold), eds_erg_05_opt.pdf (5.1 Constraining)

## Grundlagen
- **Setup Time**: Daten müssen `t_su` vor Clock-Flanke stabil sein
- **Hold Time**: Daten müssen `t_h` nach Clock-Flanke stabil bleiben
- **Slack** = `Required Time - Arrival Time`
  - `Slack > 0` → Timing erfüllt
  - `Slack < 0` → Timing-Verletzung (Violation)

## Clock Definition (XDC)
```tcl
# Primärer Takt (Beispiel: 50 MHz = 20 ns Periode)
create_clock -name sys_clk -period 20.000 [get_ports clk]

# Erzeugter Takt (nach MMCM/PLL)
create_generated_clock -name clk_out1 -source [get_pins mmcm/inst/CLKOUT0] \
  [get_pins mmcm/inst/CLKOUT0]

# Virtueller Takt für I/O Constraints
create_clock -name virt_clk -period 10.000
```

## Input/Output Delay (I/O Constraints)
```tcl
# Input Delay (externes Gerät → FPGA)
set_input_delay -clock sys_clk -min 0.500 [get_ports data_in]
set_input_delay -clock sys_clk -max 2.000 [get_ports data_in]

# Output Delay (FPGA → externes Gerät)
set_output_delay -clock sys_clk -min 0.300 [get_ports data_out]
set_output_delay -clock sys_clk -max 1.500 [get_ports data_out]
```

## False Paths & Multicycle
```tcl
# Asynchrone Reset-Pfade (kein Timing-Check)
set_false_path -from [get_ports rst] -to [all_registers]

# Multicycle Path (Daten alle N Zyklen)
set_multicycle_path 2 -setup -from [get_cells u_slow/*] -to [get_cells u_slow/*]
set_multicycle_path 1 -hold  -from [get_cells u_slow/*] -to [get_cells u_slow/*]
```

## Clock Domain Crossing (CDC)
```tcl
# Asynchrone Clock-Domains → kein Timing zwischen ihnen
set_clock_groups -asynchronous -group [get_clocks clk_a] -group [get_clocks clk_b]

# Oder einzeln:
set_false_path -from [get_clocks clk_a] -to [get_clocks clk_b]
set_false_path -from [get_clocks clk_b] -to [get_clocks clk_a]
```

## Vivado Reporting
```tcl
# Timing Summary Report
report_timing_summary -max_paths 10 -file timing_summary.rpt

# Detaillierter Pfad
report_timing -from [get_cells u_top/u_dut/reg*] -to [get_cells u_top/u_dut/reg*] \
  -max_paths 5 -sort_by slack
```

## Typische Violations & Fixes
| Violation | Ursache | Maßnahme |
|---|---|---|
| **Negative Setup Slack** | Kombinatorischer Pfad zu lang | Pipeline-Register einfügen, Logik vereinfachen, Frequenz reduzieren |
| **Negative Hold Slack** | Clock Skew / zu schneller Pfad | Buffer einfügen, `set_clock_uncertainty` prüfen |
| **Clock Skew** | Ungleichmäßige Clock-Verteilung | Global Clock Buffer (BUFG), Clock Tree optimieren |
| **IO Timing** | `set_input/output_delay` fehlt oder falsch | XDC vervollständigen, virtuelle Clocks nutzen |

## Constraining für Synthese (eds_erg_05_opt.pdf 5.1)
- **Clock**: `create_clock` für jeden echten Takt
- **I/O Delays**: Für alle externen Signale (außer Reset, Test-Pins)
- **False Paths**: Reset, CDC, Konfigurations-Register
- **Multicycle**: Bekannte langsame Pfade (z. B. Multiplikator über 2 Zyklen)
- **Keine** `set_max_delay`/`set_min_delay` ohne `create_clock` Basis

## Arty S7-50 Besonderheiten
- **Systemtakt 12 MHz** (Pin F14, LVCMOS33) → `create_clock -period 83.333 [get_ports sys_clk]`
- **DDR3-Takt 100 MHz** (R2/T2, SSTL135) → **nicht** als User-Clock constraining ohne MMCM
- Wenn Prompt 50 MHz verlangt → MMCM/Clocking Wizard nötig (12 MHz → 50 MHz)

## XDC Generator Verhalten (vivado_synthesis.py)
- Erzeugt `auto_generated.xdc` nur wenn `constraints/` leer
- Port-Name → Pin Mapping (section 1.4.D im Plan)
- **Warnung**: Generator nutzt R2 mit LVCMOS33, Board-Fakt sagt SSTL135 → `BOARD_FACT_WARNING`
- Bei user-XDC in `constraints/` wird Generator übersprungen