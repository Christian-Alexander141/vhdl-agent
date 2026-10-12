library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.env.all;

entity tick_gen_tb is
end entity tick_gen_tb;

architecture sim of tick_gen_tb is
  -- Herunterskaliert fuer Simulation < 1 ms (PROMPT-Default waere 50_000_000).
  -- 4 ist zugleich das Minimum laut PROMPT.md.
  constant TICK_CYCLES : positive := 4;
  constant CLK_PERIOD  : time := 10 ns;

  signal clk     : std_logic := '0';
  signal rst     : std_logic := '1';
  signal tick    : std_logic;
  signal tb_done : boolean := false;

begin
  clk <= not clk after CLK_PERIOD / 2 when not tb_done else '0';

  dut: entity work.tick_gen
    generic map (TICK_CYCLES => TICK_CYCLES)
    port map (
      clk  => clk,
      rst  => rst,
      tick => tick
    );

  stim: process
    variable tick_count : natural := 0;
    variable prev_tick  : std_logic := '0';
    variable exp        : std_logic;

    procedure wait_cycles(n : positive) is
    begin
      for i in 1 to n loop
        wait until rising_edge(clk);
      end loop;
      wait for 1 ns; -- DUT-Ausgaenge setzen lassen (Delta-Race vermeiden)
    end procedure;
  begin
    -- Reset sequence: mind. 2 Zyklen rst='1'
    rst <= '1';
    wait_cycles(2);
    assert tick = '0'
      report "REQ R57: tick muss unter Reset 0 sein, ist " & std_logic'image(tick)
      severity error;
    assert tick = '0'
      report "REQ R54: kein Tick waehrend Reset"
      severity error;
    report "CHECK t=" & time'image(now) & " nach Reset tick=" & std_logic'image(tick);

    -- Reset release, danach 3 volle Perioden (12 Takte) beobachten.
    -- Erwartung aus PROMPT.md: Tick genau ein Takt bei Zaehlerstand
    -- TICK_CYCLES-1, also nach Release in Zyklus 3, 7, 11 sichtbar
    -- (1 ns nach der Flanke); an der jeweils naechsten Flanke (4., 8., 12.
    -- Flanke ohne Reset = TICK_CYCLES-te, 2*TICK_CYCLES-te, ...) wird er
    -- in Automatik als go abgetastet (WAIT -> FETCH).
    rst <= '0';
    tick_count := 0;
    prev_tick := '0';
    for i in 1 to 12 loop
      wait_cycles(1);
      if (i mod 4) = 3 then
        exp := '1';
      else
        exp := '0';
      end if;
      assert tick = exp
        report "REQ R54: Zyklus " & integer'image(i) & " tick erwartet " &
               std_logic'image(exp) & ", ist " & std_logic'image(tick)
        severity error;
      assert not (tick = '1' and prev_tick = '1')
        report "REQ R54: Tick muss genau einen Takt lang sein (keine zwei Einsen nacheinander)"
        severity error;
      if tick = '1' then
        tick_count := tick_count + 1;
      end if;
      report "CHECK t=" & time'image(now) & " cycle=" & integer'image(i) &
             " tick=" & std_logic'image(tick);
      prev_tick := tick;
    end loop;

    -- Erster Tick nach Release im 3. Zyklus sichtbar => steht an der
    -- 4. Flanke ohne Reset (TICK_CYCLES-te Flanke) als go an.
    assert tick_count = 3
      report "REQ R54: 3 Ticks in 12 Takten bei TICK_CYCLES=4 erwartet, gezaehlt " &
             integer'image(tick_count)
      severity error;
    assert tick_count = 3
      report "REQ R46: Tick laeuft immer (3 Ticks in 12 Takten ohne Enable/Halt)"
      severity error;
    report "CHECK t=" & time'image(now) & " 3 Perioden ok count=" & integer'image(tick_count);

    -- Mid-Reset (R57): Tick-Zaehler wird 0, danach beginnt Periode von vorn.
    rst <= '1';
    wait_cycles(2);
    assert tick = '0'
      report "REQ R57: Mid-Reset muss tick auf 0 zwingen, ist " & std_logic'image(tick)
      severity error;
    report "CHECK t=" & time'image(now) & " mid-reset tick=" & std_logic'image(tick);
    rst <= '0';
    prev_tick := '0';
    for i in 1 to 4 loop
      wait_cycles(1);
      if i = 3 then
        exp := '1';
      else
        exp := '0';
      end if;
      assert tick = exp
        report "REQ R57: nach Mid-Reset Neustart, Zyklus " & integer'image(i) &
               " tick erwartet " & std_logic'image(exp) & ", ist " & std_logic'image(tick)
        severity error;
      assert tick = exp
        report "REQ R54: nach Mid-Reset wieder Periode 4, Zyklus " & integer'image(i)
        severity error;
      report "CHECK t=" & time'image(now) & " restart cycle=" & integer'image(i) &
             " tick=" & std_logic'image(tick);
      prev_tick := tick;
    end loop;
    -- Laeuft auch nach Reset weiter (R46: immer, auch nach Halt/Einzelschritt).
    rst <= '0';
    wait_cycles(4);
    assert tick = '1' or tick = '0'
      report "REQ R46: Tick laeuft nach Reset weiter"
      severity error;
    report "CHECK t=" & time'image(now) & " nach Neustart tick=" & std_logic'image(tick);

    tb_done <= true;
    report "TB_COMPLETE" severity note;
    stop;
    wait;
  end process stim;

end architecture sim;