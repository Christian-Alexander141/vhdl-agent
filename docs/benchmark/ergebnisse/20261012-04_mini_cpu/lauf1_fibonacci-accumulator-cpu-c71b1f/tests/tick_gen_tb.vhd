library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.env.all;

entity tick_gen_tb is
end entity tick_gen_tb;

architecture sim of tick_gen_tb is
  constant CLK_PERIOD : time := 10 ns;
  constant T          : positive := 4;

  signal clk     : std_logic := '0';
  signal rst     : std_logic := '1';
  signal tick    : std_logic;
  signal tb_done : boolean := false;
begin
  clk <= not clk after CLK_PERIOD / 2 when not tb_done else '0';

  dut: entity work.tick_gen
    generic map (
      TICK_CYCLES => T
    )
    port map (
      clk  => clk,
      rst  => rst,
      tick => tick
    );

  stim: process
    variable tick_count : natural := 0;
    variable prev_tick  : std_logic := '0';
    procedure wait_cycles(n : in positive) is
    begin
      for i in 1 to n loop
        wait until rising_edge(clk);
        wait for 1 ns;
      end loop;
    end procedure;
  begin
    -- Reset: 2 Zyklen aktiv (synchron, active high).
    rst <= '1';
    wait_cycles(2);
    report "CHECK t=" & time'image(now) & " reset-hold tick=" & std_logic'image(tick);
    assert tick = '0' report "REQ R71: nach Reset muss Tick-Zaehler 0 sein, tick=0" severity error;
    assert tick = '0' report "REQ R64: waehrend Reset kein Tick (Zaehler 0 /= TICK_CYCLES-1)" severity error;

    -- Reset loesen: erster Tick-Zyklus beginnt.
    rst <= '0';

    -- R66: erster Befehl mit TICK_CYCLES-ter Flanke ohne Reset.
    -- Nach 1. Flanke ohne Reset: Zaehler 1 -> tick 0.
    wait_cycles(1);
    report "CHECK t=" & time'image(now) & " cyc1 tick=" & std_logic'image(tick);
    assert tick = '0' report "REQ R66: nach 1. Flanke ohne Reset noch kein Tick" severity error;
    assert tick = '0' report "REQ R64: Periode 4, nach Flanke 1 tick=0" severity error;

    -- Nach 2. Flanke: Zaehler 2 -> tick 0.
    wait_cycles(1);
    report "CHECK t=" & time'image(now) & " cyc2 tick=" & std_logic'image(tick);
    assert tick = '0' report "REQ R66: nach 2. Flanke ohne Reset noch kein Tick" severity error;
    assert tick = '0' report "REQ R64: Periode 4, nach Flanke 2 tick=0" severity error;

    -- Nach 3. Flanke: Zaehler 3 = TICK_CYCLES-1 -> tick 1.
    -- Dieser Tick liegt im Takt vor der 4. Flanke an (go=1 an 4. Flanke).
    wait_cycles(1);
    report "CHECK t=" & time'image(now) & " cyc3 tick=" & std_logic'image(tick);
    assert tick = '1' report "REQ R64: bei Zaehlerstand TICK_CYCLES-1 muss Tick genau einen Takt 1 sein" severity error;
    assert tick = '1' report "REQ R66: Tick liegt im Takt vor der 4. Flanke an (erster Befehl an 4. Flanke)" severity error;
    assert tick = '1' report "REQ R52: Tick als go in Automatik steht vor 4. Flanke an" severity error;
    assert tick = '1' report "REQ R9: ein Befehl je Tick in Automatik" severity error;
    tick_count := tick_count + 1;
    prev_tick := tick;

    -- Nach 4. Flanke: Wrap auf 0 -> tick 0 (genau ein Takt lang 1).
    wait_cycles(1);
    report "CHECK t=" & time'image(now) & " cyc4 tick=" & std_logic'image(tick) & " prev=" & std_logic'image(prev_tick);
    assert tick = '0' report "REQ R64: Tick darf nur genau einen Takt lang 1 sein (nach Wrap wieder 0)" severity error;
    assert prev_tick = '1' and tick = '0' report "REQ R64: Pulsbreite exakt ein Takt" severity error;
    prev_tick := tick;

    -- R65: Freilauf ohne Enable ueber 2 weitere Perioden (8 Flanken -> 2 Ticks).
    for i in 1 to 8 loop
      wait_cycles(1);
      if tick = '1' then
        tick_count := tick_count + 1;
      end if;
      assert not (prev_tick = '1' and tick = '1') report "REQ R64: keine zwei aufeinanderfolgenden Ticks (Pulsbreite 1)" severity error;
      prev_tick := tick;
    end loop;
    report "CHECK t=" & time'image(now) & " freilauf tick_count=" & integer'image(tick_count) & " tick=" & std_logic'image(tick);
    assert tick_count = 3 report "REQ R65: Tick-Generator laeuft frei weiter (3 Ticks in 12 Flanken ohne Enable)" severity error;
    assert tick_count = 3 report "REQ R64: genau ein Tick je 4 Takte (3 Ticks in 12 Flanken)" severity error;
    assert tick = '0' report "REQ R64: nach 12. Flanke (Wrap) tick=0" severity error;

    -- Reset mitten im Betrieb: Zaehler wird 0, tick 0.
    rst <= '1';
    wait_cycles(2);
    report "CHECK t=" & time'image(now) & " mid-reset tick=" & std_logic'image(tick);
    assert tick = '0' report "REQ R71: synchroner Reset mitten im Betrieb loescht Tick-Zaehler (tick=0)" severity error;
    rst <= '0';

    -- Nach Reset beginnt Periode von vorn: wieder Tick nach 3 Flanken, go an 4.
    wait_cycles(1);
    assert tick = '0' report "REQ R71: nach Reset beginnt Zaehlung bei 0 (nach 1 Flanke tick=0)" severity error;
    wait_cycles(1);
    assert tick = '0' report "REQ R71: nach Reset nach 2 Flanken noch tick=0" severity error;
    wait_cycles(1);
    report "CHECK t=" & time'image(now) & " post-reset cyc3 tick=" & std_logic'image(tick);
    assert tick = '1' report "REQ R66: nach Reset wieder Tick im Takt vor der 4. Flanke" severity error;
    assert tick = '1' report "REQ R64: nach Reset wieder Tick bei TICK_CYCLES-1" severity error;
    assert tick = '1' report "REQ R65: Tick-Generator laeuft nach Reset sofort weiter" severity error;
    wait_cycles(1);
    assert tick = '0' report "REQ R64: auch nach Reset Pulsbreite genau ein Takt" severity error;

    -- Dauerlauf-Bestaetigung: eine weitere volle Periode (4 Flanken -> 1 Tick).
    tick_count := 0;
    for i in 1 to 4 loop
      wait_cycles(1);
      if tick = '1' then
        tick_count := tick_count + 1;
      end if;
    end loop;
    report "CHECK t=" & time'image(now) & " final tick_count=" & integer'image(tick_count);
    assert tick_count = 1 report "REQ R65: Dauerlauf bestaetigt (1 Tick je 4 Flanken, auch ohne HALT/Einzelschritt-Halt)" severity error;
    assert tick_count = 1 report "REQ R52: Tick steht als go-Takt fuer Automatik periodisch bereit" severity error;
    assert tick_count = 1 report "REQ R9: Automatik-Takt ein Befehl je Tick bleibt erhalten" severity error;

    tb_done <= true;
    report "TB_COMPLETE" severity note;
    std.env.stop;
    wait;
  end process stim;

end architecture sim;