library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity tick_gen_tb is
end entity tick_gen_tb;

architecture sim of tick_gen_tb is
  constant CLK_PERIOD : time := 100 ns;
  constant T1 : positive := 4;
  constant T2 : positive := 7;

  signal clk   : std_logic := '0';
  signal rst   : std_logic := '1';
  signal tick1 : std_logic;
  signal tick2 : std_logic;

  signal tb_done : boolean := false;

begin
  clk <= not clk after CLK_PERIOD / 2 when not tb_done else '0';

  dut1: entity work.tick_gen
    generic map (TICK_CYCLES => T1)
    port map (clk => clk, rst => rst, tick => tick1);

  dut2: entity work.tick_gen
    generic map (TICK_CYCLES => T2)
    port map (clk => clk, rst => rst, tick => tick2);

  stim: process
    variable n1 : natural;
    variable n2 : natural;
    variable prev1 : std_logic := '0';
    variable prev2 : std_logic := '0';
  begin
    -- Reset sequence: mindestens 2 Zyklen rst='1' (synchron, active high)
    rst <= '1';
    for i in 1 to 3 loop
      wait until rising_edge(clk);
      wait for 1 ns;
      assert tick1 = '0'
        report "REQ R71: tick muss unter synchronem Reset 0 sein (T1)"
        severity error;
      assert tick2 = '0'
        report "REQ R71: tick muss unter synchronem Reset 0 sein (T2)"
        severity error;
      assert tick1 = '0'
        report "REQ R67: kein Tick waehrend Reset (TICK_CYCLES=4)"
        severity error;
    end loop;
    report "CHECK t=" & time'image(now)
      & " reset-phase done tick1=" & std_logic'image(tick1)
      & " tick2=" & std_logic'image(tick2);

    rst <= '0';

    -- Phase B: erste 14 Takte nach Resetfreigabe.
    -- PROMPT R67: Tick kombinatorisch beim Zaehlerstand TICK_CYCLES-1.
    -- Tick-Ausgang='1' nach globalem Zyklus 3,7,11 (T1=4) bzw. 6,13 (T2=7);
    -- der zugehoerige Befehl (WAIT->FETCH) folgt mit der naechsten Flanke,
    -- also erster Befehl mit der TICK_CYCLES-ten Flanke (4 bzw. 7).
    for c in 1 to 14 loop
      wait until rising_edge(clk);
      wait for 1 ns;
      if (c mod T1 = T1 - 1) then
        assert tick1 = '1'
          report "REQ R67: T1 erster/periodischer Tick erwartet bei Zyklus "
            & integer'image(c) & " t=" & time'image(now)
          severity error;
        assert tick1 = '1'
          report "REQ R57: Tick als go in Automatik muss bei Zyklus "
            & integer'image(c) & " genau einen Takt '1' sein t=" & time'image(now)
          severity error;
      else
        assert tick1 = '0'
          report "REQ R67: T1 kein Tick erwartet bei Zyklus "
            & integer'image(c) & " t=" & time'image(now)
            & " tick1=" & std_logic'image(tick1)
          severity error;
      end if;
      if (c mod T2 = T2 - 1) then
        assert tick2 = '1'
          report "REQ R67: T2 erster/periodischer Tick erwartet bei Zyklus "
            & integer'image(c) & " t=" & time'image(now)
          severity error;
      else
        assert tick2 = '0'
          report "REQ R67: T2 kein Tick erwartet bei Zyklus "
            & integer'image(c) & " t=" & time'image(now)
            & " tick2=" & std_logic'image(tick2)
          severity error;
      end if;
      -- Pulsbreite: nie zwei Takte hintereinander '1' (TICK_CYCLES >= 4)
      if c > 1 then
        assert not (prev1 = '1' and tick1 = '1')
          report "REQ R67: T1 Tick muss genau einen Takt lang sein t=" & time'image(now)
          severity error;
        assert not (prev2 = '1' and tick2 = '1')
          report "REQ R67: T2 Tick muss genau einen Takt lang sein t=" & time'image(now)
          severity error;
      end if;
      assert (tick1 = '0' or tick1 = '1')
        report "REQ R57: tick1 muss definierter go-Pegel 0/1 sein t=" & time'image(now)
        severity error;
      prev1 := tick1;
      prev2 := tick2;
      if (c = 3 or c = 6 or c = 7 or c = 13) then
        report "CHECK t=" & time'image(now)
          & " c=" & integer'image(c)
          & " tick1=" & std_logic'image(tick1)
          & " tick2=" & std_logic'image(tick2);
      end if;
    end loop;
    report "CHECK t=" & time'image(now) & " phase-B done (erste Ticks + Periode ok)";

    -- Phase C: Dauerlauf ueber 28 Takte (LCM von 4 und 7).
    -- Globale Zyklen 15..42: exakt 7x tick1 und 4x tick2 erwartet.
    -- Beweist: Zaehler 0..TICK_CYCLES-1, laeuft immer (auch ohne Halt).
    n1 := 0;
    n2 := 0;
    for c in 1 to 28 loop
      wait until rising_edge(clk);
      wait for 1 ns;
      if ((14 + c) mod T1 = T1 - 1) then
        assert tick1 = '1'
          report "REQ R67: T1 Dauerlauf-Tick erwartet global "
            & integer'image(14 + c) & " t=" & time'image(now)
          severity error;
      else
        assert tick1 = '0'
          report "REQ R67: T1 Dauerlauf kein Tick global "
            & integer'image(14 + c) & " t=" & time'image(now)
          severity error;
      end if;
      if ((14 + c) mod T2 = T2 - 1) then
        assert tick2 = '1'
          report "REQ R67: T2 Dauerlauf-Tick erwartet global "
            & integer'image(14 + c) & " t=" & time'image(now)
          severity error;
      else
        assert tick2 = '0'
          report "REQ R67: T2 Dauerlauf kein Tick global "
            & integer'image(14 + c) & " t=" & time'image(now)
          severity error;
      end if;
      assert not (prev1 = '1' and tick1 = '1')
        report "REQ R67: T1 Dauerlauf Pulsbreite genau 1 Takt t=" & time'image(now)
        severity error;
      assert not (prev2 = '1' and tick2 = '1')
        report "REQ R57: T2 Dauerlauf Pulsbreite genau 1 Takt (go) t=" & time'image(now)
        severity error;
      if tick1 = '1' then
        n1 := n1 + 1;
      end if;
      if tick2 = '1' then
        n2 := n2 + 1;
      end if;
      prev1 := tick1;
      prev2 := tick2;
    end loop;
    report "CHECK t=" & time'image(now)
      & " dauerlauf n1=" & integer'image(n1) & " n2=" & integer'image(n2);
    assert n1 = 7
      report "REQ R67: T1 Dauerlauf 7 Ticks in 28 Takten erwartet, n1=" & integer'image(n1)
      severity error;
    assert n2 = 4
      report "REQ R67: T2 Dauerlauf 4 Ticks in 28 Takten erwartet, n2=" & integer'image(n2)
      severity error;
    assert n1 = 7
      report "REQ R57: Tick laeuft immer (kein Anhalten), n1=" & integer'image(n1)
      severity error;

    -- Phase D: Reset mitten im Lauf loescht Tick-Zaehler (R71),
    -- danach beginnt die Zaählung von vorn.
    rst <= '1';
    for i in 1 to 2 loop
      wait until rising_edge(clk);
      wait for 1 ns;
      assert tick1 = '0'
        report "REQ R71: tick1 muss bei Mid-Run-Reset 0 sein t=" & time'image(now)
        severity error;
      assert tick2 = '0'
        report "REQ R71: tick2 muss bei Mid-Run-Reset 0 sein t=" & time'image(now)
        severity error;
    end loop;
    report "CHECK t=" & time'image(now) & " mid-run reset aktiv tick1="
      & std_logic'image(tick1) & " tick2=" & std_logic'image(tick2);
    rst <= '0';
    prev1 := '0';
    prev2 := '0';
    for c in 1 to 8 loop
      wait until rising_edge(clk);
      wait for 1 ns;
      if (c mod T1 = T1 - 1) then
        assert tick1 = '1'
          report "REQ R71: nach Reset erster T1-Tick wieder bei Zyklus 3/7, c="
            & integer'image(c) & " t=" & time'image(now)
          severity error;
      else
        assert tick1 = '0'
          report "REQ R71: nach Reset T1 kein Tick bei c="
            & integer'image(c) & " t=" & time'image(now)
          severity error;
      end if;
      if (c mod T2 = T2 - 1) then
        assert tick2 = '1'
          report "REQ R71: nach Reset erster T2-Tick wieder bei Zyklus 6, c="
            & integer'image(c) & " t=" & time'image(now)
          severity error;
      else
        assert tick2 = '0'
          report "REQ R71: nach Reset T2 kein Tick bei c="
            & integer'image(c) & " t=" & time'image(now)
          severity error;
      end if;
      assert tick1 = '0' or tick1 = '1'
        report "REQ R67: nach Reset definierter Pegel T1 t=" & time'image(now)
        severity error;
      if (c = 3 or c = 6 or c = 7) then
        report "CHECK t=" & time'image(now)
          & " restart c=" & integer'image(c)
          & " tick1=" & std_logic'image(tick1)
          & " tick2=" & std_logic'image(tick2);
      end if;
    end loop;

    tb_done <= true;
    report "TB_COMPLETE" severity note;
    wait;
  end process stim;

end architecture sim;