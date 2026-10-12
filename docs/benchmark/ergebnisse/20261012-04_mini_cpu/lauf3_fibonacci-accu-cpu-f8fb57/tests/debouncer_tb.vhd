library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.env.all;

entity debouncer_tb is
end entity debouncer_tb;

architecture sim of debouncer_tb is

  constant CLK_PERIOD     : time := 20 ns;
  constant DEBOUNCE_CYCLES : positive := 4;

  signal clk    : std_logic := '0';
  signal rst    : std_logic := '1';
  signal d_in   : std_logic := '0';
  signal dout   : std_logic;
  signal rise   : std_logic;

  signal tb_done : boolean := false;

begin

  clk <= not clk after CLK_PERIOD / 2 when not tb_done else '0';

  dut: entity work.debouncer
    generic map (
      DEBOUNCE_CYCLES => DEBOUNCE_CYCLES
    )
    port map (
      clk  => clk,
      rst  => rst,
      d_in => d_in,
      dout => dout,
      rise => rise
    );

  stim: process
    procedure wait_cycles(n : positive) is
    begin
      for i in 1 to n loop
        wait until rising_edge(clk);
      end loop;
      wait for 1 ns;
    end procedure;
  begin
    -- Reset sequence: mind. 2 Zyklen rst='1'
    rst  <= '1';
    d_in <= '0';
    wait_cycles(2);
    report "CHECK t=" & time'image(now) & " after reset dout=" & to_string(dout) & " rise=" & to_string(rise);
    assert dout = '0' report "REQ R71: nach Reset dout=0" severity error;
    assert rise = '0' report "REQ R71: nach Reset rise=0" severity error;

    rst <= '0';
    wait_cycles(2);
    report "CHECK t=" & time'image(now) & " idle dout=" & to_string(dout) & " rise=" & to_string(rise);
    assert dout = '0' report "REQ R71: nach Reset-Release dout=0" severity error;
    assert rise = '0' report "REQ R71: nach Reset-Release rise=0" severity error;

    -- Kurzpuls < DEBOUNCE_CYCLES: kein Schritt
    report "CHECK t=" & time'image(now) & " short pulse start";
    d_in <= '1';
    wait_cycles(1);
    report "CHECK t=" & time'image(now) & " short+1 dout=" & to_string(dout) & " rise=" & to_string(rise);
    assert dout = '0' report "REQ R65: nach 1 Flanke ungleich noch kein Wechsel" severity error;
    assert rise = '0' report "REQ R66: nach 1 Flanke kein rise" severity error;
    wait_cycles(1);
    report "CHECK t=" & time'image(now) & " short+2 dout=" & to_string(dout) & " rise=" & to_string(rise);
    assert dout = '0' report "REQ R65: nach 2 Flanken (<4) noch kein Wechsel" severity error;
    assert rise = '0' report "REQ R86: Impuls kuerzer als DEBOUNCE_CYCLES loest keinen Schritt aus" severity error;
    assert rise = '0' report "REQ R57: kein go-Impuls bei Kurzpuls" severity error;
    d_in <= '0';
    wait_cycles(2);
    report "CHECK t=" & time'image(now) & " short aborted dout=" & to_string(dout) & " rise=" & to_string(rise);
    assert dout = '0' report "REQ R65: Zaehler wird 0 wenn Eingang gleich dout (Abbruch)" severity error;
    assert rise = '0' report "REQ R66: kein rise nach abgebrochenem Puls" severity error;

    -- Langer stabiler Pegel 1: Wechsel mit 4. Flanke, rise genau 1 Takt
    d_in <= '1';
    wait_cycles(3);
    report "CHECK t=" & time'image(now) & " long+3 dout=" & to_string(dout) & " rise=" & to_string(rise);
    assert dout = '0' report "REQ R65: nach 3 Flanken noch kein Wechsel (braucht 4)" severity error;
    assert rise = '0' report "REQ R66: vor Wechsel kein rise" severity error;
    wait_cycles(1);
    report "CHECK t=" & time'image(now) & " long+4 dout=" & to_string(dout) & " rise=" & to_string(rise);
    assert dout = '1' report "REQ R65: dout wechselt mit DEBOUNCE_CYCLES-ter Flanke (0->1)" severity error;
    assert rise = '1' report "REQ R66: rise=1 mit derselben Flanke wie dout 0->1" severity error;
    assert rise = '1' report "REQ R57: Schrittimpuls rise als go nach Entprellung" severity error;
    wait_cycles(1);
    report "CHECK t=" & time'image(now) & " long+5 dout=" & to_string(dout) & " rise=" & to_string(rise);
    assert dout = '1' report "REQ R65: dout bleibt 1 bei stabilem Eingang" severity error;
    assert rise = '0' report "REQ R66: rise genau einen Takt lang 1" severity error;
    assert rise = '0' report "REQ R57: go-Impuls genau einen Takt lang" severity error;
    wait_cycles(2);
    assert dout = '1' report "REQ R65: dout stabil 1" severity error;
    assert rise = '0' report "REQ R66: rise bleibt 0 bei stabilem Eingang" severity error;

    -- Fallende Flanke: braucht ebenfalls 4 Flanken, kein rise
    d_in <= '0';
    wait_cycles(3);
    report "CHECK t=" & time'image(now) & " fall+3 dout=" & to_string(dout) & " rise=" & to_string(rise);
    assert dout = '1' report "REQ R65: fallend nach 3 Flanken noch kein Wechsel" severity error;
    assert rise = '0' report "REQ R66: fallend kein rise" severity error;
    wait_cycles(1);
    report "CHECK t=" & time'image(now) & " fall+4 dout=" & to_string(dout) & " rise=" & to_string(rise);
    assert dout = '0' report "REQ R65: dout wechselt mit 4. Flanke (1->0)" severity error;
    assert rise = '0' report "REQ R66: rise bleibt 0 bei dout 1->0" severity error;
    wait_cycles(1);
    assert dout = '0' report "REQ R65: dout stabil 0" severity error;
    assert rise = '0' report "REQ R66: rise 0 nach fallendem Wechsel" severity error;

    -- Prellen: unterbrochene Folge verworfen (Zaehler-Reset)
    d_in <= '1';
    wait_cycles(3);
    assert dout = '0' report "REQ R65: Prelltest 3 Flanken noch 0" severity error;
    d_in <= '0';
    wait_cycles(1);
    report "CHECK t=" & time'image(now) & " bounce gap dout=" & to_string(dout) & " rise=" & to_string(rise);
    assert dout = '0' report "REQ R65: Luecke setzt Zaehler zurueck (Eingang==dout)" severity error;
    assert rise = '0' report "REQ R86: prellender Kurzpuls kein Schritt" severity error;
    d_in <= '1';
    wait_cycles(3);
    report "CHECK t=" & time'image(now) & " bounce+3 dout=" & to_string(dout) & " rise=" & to_string(rise);
    assert dout = '0' report "REQ R65: nach Unterbrechung wieder 3 Flanken nicht genug" severity error;
    assert rise = '0' report "REQ R66: nach Unterbrechung kein rise" severity error;
    wait_cycles(1);
    report "CHECK t=" & time'image(now) & " bounce+4 dout=" & to_string(dout) & " rise=" & to_string(rise);
    assert dout = '1' report "REQ R65: nach 4 aufeinanderfolgenden Flanken Wechsel" severity error;
    assert rise = '1' report "REQ R66: rise nach 4 aufeinanderfolgenden Flanken" severity error;
    wait_cycles(1);
    assert rise = '0' report "REQ R66: rise nur einen Takt" severity error;
    d_in <= '0';
    wait_cycles(4);
    assert dout = '0' report "REQ R65: Rueckkehr nach 0 mit 4 Flanken" severity error;
    assert rise = '0' report "REQ R66: fallend kein rise" severity error;
    wait_cycles(1);

    -- Reset mitten im Betrieb
    d_in <= '1';
    wait_cycles(4);
    assert dout = '1' report "REQ R71: Setup HT dout=1 vor Mid-Reset" severity error;
    report "CHECK t=" & time'image(now) & " pre-mid-reset dout=" & to_string(dout) & " rise=" & to_string(rise);
    rst <= '1';
    wait_cycles(2);
    report "CHECK t=" & time'image(now) & " mid-reset dout=" & to_string(dout) & " rise=" & to_string(rise);
    assert dout = '0' report "REQ R71: Mid-Reset loescht dout (alle Register 0)" severity error;
    assert rise = '0' report "REQ R71: Mid-Reset loescht rise" severity error;
    rst <= '0';
    d_in <= '0';
    wait_cycles(2);
    assert dout = '0' report "REQ R71: nach Mid-Reset dout=0" severity error;
    assert rise = '0' report "REQ R71: nach Mid-Reset rise=0" severity error;

    tb_done <= true;
    report "TB_COMPLETE" severity note;
    stop;
    wait;
  end process stim;

end architecture sim;