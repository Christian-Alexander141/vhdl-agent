# Review – Widerspruch Skills vs. PROMPT.md

- Modul cpu_core: `vhdl-synthesis-rules`/`vhdl-fsm` nennen asynchronen Reset als Default (`process(clk, rst)`, `if rst = '1'` ohne Flanke). PROMPT.md verlangt synchronen Reset active-high ("Taster BTN0, synchroner Reset", "Reset: Alle Register werden 0 ... Steuerwerk geht nach WAIT"). PROMPT.md hat Vorrang (R9): cpu_core nutzt `process(clk)` mit `rising_edge` + synchronem Reset, konsistent mit control_unit/data_ram.
