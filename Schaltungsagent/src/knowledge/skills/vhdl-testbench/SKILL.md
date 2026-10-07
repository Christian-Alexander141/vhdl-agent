# Skill: vhdl-testbench
# Beschreibung: Self-checking VHDL testbench pattern with assertions, clock generation, and TB_COMPLETE marker.
# Lade diesen Skill, wenn eine Testbench für ein VHDL-Modul erzeugt wird (Entity `<name>_tb`, Architecture, Stimuli, Assertions).
# Quelle: Projektkonvention (hdl.py L690–713, VerificationAgent, keine Fachquelle im Archiv)

## Naming & Structure
- Datei: `tests/<entity>_tb.vhd`
- Entity: `<entity>_tb` (z. B. `timer_tb` für `timer`)
- Architecture: `sim` oder `behav`
- Keine Generics in der TB-Entity (außer für Parameter-Sweeps)

## Template
```vhdl
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity timer_tb is
end entity timer_tb;

architecture sim of timer_tb is
  -- DUT generics
  constant CLK_FREQ_HZ : positive := 50_000_000;
  constant WIDTH       : positive := 8;

  -- Clock / Reset
  constant CLK_PERIOD  : time := 1 sec / CLK_FREQ_HZ;
  signal clk   : std_logic := '0';
  signal rst   : std_logic := '1';

  -- DUT signals (match entity ports exactly)
  signal start : std_logic := '0';
  signal done  : std_logic;

  -- Test control
  signal tb_done : boolean := false;

begin
  -- Clock generator
  clk <= not clk after CLK_PERIOD / 2 when not tb_done else '0';

  -- DUT instantiation
  dut: entity work.timer
    generic map (CLK_FREQ_HZ => CLK_FREQ_HZ, WIDTH => WIDTH)
    port map (clk => clk, rst => rst, start => start, done => done);

  -- Stimulus process
  stim: process
    procedure wait_cycles(n : positive) is
    begin
      for i in 1 to n loop
        wait until rising_edge(clk);
      end loop;
    end procedure;
  begin
    -- Reset sequence
    rst <= '1'; wait_cycles(2);
    rst <= '0'; wait_cycles(2);

    -- Test case 1: basic start/stop
    start <= '1'; wait_cycles(1);
    start <= '0';
    wait until done = '1' for 10 us;
    assert done = '1' report "TC1: done not asserted" severity error;

    -- Test case 2: restart
    wait_cycles(5);
    start <= '1'; wait_cycles(1);
    start <= '0';
    wait until done = '1' for 10 us;
    assert done = '1' report "TC2: restart failed" severity error;

    -- End of test
    tb_done <= true;
    assert false report "TB_COMPLETE" severity note;
    wait;
  end process stim;

end architecture sim;
```

## Required Elements
1. **Clock generator** mit `constant CLK_PERIOD` und `tb_done` Gate
2. **Reset sequence**: mind. 2 Zyklen `rst='1'`, dann `rst='0'`
3. **DUT instantiation** mit exakt gleichen Port-Namen und Generics
4. **Assertions** mit `report` und `severity error` (nicht `note`/`warning`)
5. **TB_COMPLETE Marker**: `assert false report "TB_COMPLETE" severity note;` am Ende
6. **Kein `wait` ohne Zeitangabe** außer am Ende (`wait;`)

## Stimulus Helpers
```vhdl
procedure wait_cycles(n : positive) is
begin
  for i in 1 to n loop
    wait until rising_edge(clk);
  end loop;
end procedure;

procedure pulse(signal sig : out std_logic; cycles : positive := 1) is
begin
  sig <= '1'; wait_cycles(cycles); sig <= '0';
end procedure;
```

## GHDL Execution (Pipeline Standard)
```bash
ghdl -a --std=08 src/timer.vhd tests/timer_tb.vhd
ghdl -e --std=08 timer_tb
ghdl -r --std=08 timer_tb --assert-level=error --ieee-asserts=disable-at-0
```
- `--assert-level=error` → `severity error` bricht ab
- `--ieee-asserts=disable-at-0` → unterdrückt IEEE-Bibliothek-Assertionen bei Zeit 0

## Common Pitfalls
| Problem | Ursache | Fix |
|---|---|---|
| Port-Mismatch | TB-Ports stimmen nicht mit DUT-Entity überein | Exakt aus DUT-Entity kopieren |
| Kein TB_COMPLETE | Pipeline erkennt Testende nicht | `assert false report "TB_COMPLETE" severity note;` am Ende |
| Clock läuft nicht | `tb_done` nicht auf `true` gesetzt | Nach letzten Test `tb_done <= true;` |
| Assertion nicht scharf | `severity note` statt `error` | `severity error` für echte Prüfungen |
| Simulations-Timeout | Endlosschleife in Stimulus | `for`-Loop mit `wait until` statt `wait for` |