library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.env.all;

entity debouncer_tb is
end entity debouncer_tb;

architecture sim of debouncer_tb is
  -- Herunterskaliert fuer Simulation < 1 ms (PROMPT-Default waere 1_000_000).
  constant DEBOUNCE_CYCLES : positive := 4;
  constant CLK_PERIOD      : time := 10 ns;

  signal clk     : std_logic := '0';
  signal rst     : std_logic := '1';
  signal din     : std_logic := '0';
  signal dout    : std_logic;
  signal rise    : std_logic;
  signal tb_done : boolean := false;

begin
  clk <= not clk after CLK_PERIOD / 2 when not tb_done else '0';

  dut: entity work.debouncer
    generic map (DEBOUNCE_CYCLES => DEBOUNCE_CYCLES)
    port map (
      clk  => clk,
      rst  => rst,
      din  => din,
      dout => dout,
      rise => rise
    );

  stim: process
    procedure wait_cycles(n : positive) is
    begin
      for i in 1 to n loop
        wait until rising_edge(clk);
      end loop;
      wait for 1 ns; -- DUT-Ausgaenge setzen lassen (Delta-Race vermeiden)
    end procedure;
  begin
    -- Reset sequence: mind. 2 Zyklen rst='1' (synchroner Reset, PROMPT.md).
    rst <= '1';
    din <= '0';
    wait_cycles(2);
    assert dout = '0'
      report "REQ R57: dout muss unter Reset 0 sein, ist " & std_logic'image(dout)
      severity error;
    assert rise = '0'
      report "REQ R57: rise muss unter Reset 0 sein, ist " & std_logic'image(rise)
      severity error;
    report "CHECK t=" & time'image(now) & " nach Reset dout=" & std_logic'image(dout) &
           " rise=" & std_logic'image(rise);

    -- Reset release, Eingang stabil 0: dout/rise bleiben 0.
    rst <= '0';
    wait_cycles(2);
    assert dout = '0'
      report "REQ R57: dout nach Reset-Release weiter 0"
      severity error;
    assert rise = '0'
      report "REQ R53: rise bei stabilem Eingang 0"
      severity error;
    report "CHECK t=" & time'image(now) & " nach Release dout=" & std_logic'image(dout) &
           " rise=" & std_logic'image(rise);

    -- Kurzpuls < DEBOUNCE_CYCLES: 3 Takte '1' duerfen keinen Wechsel ausloesen.
    -- (PROMPT mini_cpu-Sicht: Impuls kuerzer als DEBOUNCE_CYCLES loest keinen Schritt aus.)
    din <= '1';
    for i in 1 to DEBOUNCE_CYCLES - 1 loop
      wait_cycles(1);
      assert dout = '0'
        report "REQ R53: Kurzpuls Zyklus " & integer'image(i) & " dout muss 0 bleiben"
        severity error;
      assert rise = '0'
        report "REQ R71: Kurzpuls Zyklus " & integer'image(i) & " kein Schritt (rise 0)"
        severity error;
      report "CHECK t=" & time'image(now) & " kurzpuls cycle=" & integer'image(i) &
             " dout=" & std_logic'image(dout) & " rise=" & std_logic'image(rise);
    end loop;
    din <= '0';
    wait_cycles(2);
    assert dout = '0'
      report "REQ R53: nach Kurzpuls bleibt dout 0"
      severity error;
    assert rise = '0'
      report "REQ R71: Kurzpuls loest keinen Schritt aus (rise bleibt 0)"
      severity error;
    report "CHECK t=" & time'image(now) & " nach Kurzpuls dout=" & std_logic'image(dout) &
           " rise=" & std_logic'image(rise);

    -- Stabile '1' fuer DEBOUNCE_CYCLES Flanken: erst nach der 4. Flanke Wechsel.
    din <= '1';
    for i in 1 to DEBOUNCE_CYCLES - 1 loop
      wait_cycles(1);
      assert dout = '0'
        report "REQ R53: stabile 1, Zyklus " & integer'image(i) & " dout noch 0"
        severity error;
      assert rise = '0'
        report "REQ R53: stabile 1, Zyklus " & integer'image(i) & " rise noch 0"
        severity error;
      report "CHECK t=" & time'image(now) & " anstieg cycle=" & integer'image(i) &
             " dout=" & std_logic'image(dout) & " rise=" & std_logic'image(rise);
    end loop;
    wait_cycles(1); -- DEBOUNCE_CYCLES-te Flanke mit din /= dout
    assert dout = '1'
      report "REQ R53: nach DEBOUNCE_CYCLES-ten Flanke dout=1, ist " & std_logic'image(dout)
      severity error;
    assert rise = '1'
      report "REQ R53: mit 0->1-Wechsel rise=1, ist " & std_logic'image(rise)
      severity error;
    assert rise = '1'
      report "REQ R46: Schrittimpuls rise als go bei 0->1 genau einen Takt"
      severity error;
    report "CHECK t=" & time'image(now) & " wechsel auf 1 dout=" & std_logic'image(dout) &
           " rise=" & std_logic'image(rise);

    -- rise genau einen Takt lang: naechste Flanke rise=0, dout bleibt 1.
    wait_cycles(1);
    assert dout = '1'
      report "REQ R53: dout bleibt nach Wechsel 1"
      severity error;
    assert rise = '0'
      report "REQ R53: rise nach einem Takt wieder 0, ist " & std_logic'image(rise)
      severity error;
    assert rise = '0'
      report "REQ R46: go-Schrittimpuls nur einen Takt lang"
      severity error;
    report "CHECK t=" & time'image(now) & " nach Puls dout=" & std_logic'image(dout) &
           " rise=" & std_logic'image(rise);

    -- Weiter stabil '1': kein zweiter Puls.
    wait_cycles(2);
    assert dout = '1'
      report "REQ R53: bei stabilem Eingang bleibt dout 1"
      severity error;
    assert rise = '0'
      report "REQ R46: kein zweiter Schrittimpuls bei stabilem Eingang"
      severity error;
    report "CHECK t=" & time'image(now) & " stabil 1 dout=" & std_logic'image(dout) &
           " rise=" & std_logic'image(rise);

    -- Prellen: 2 Takte '0' (< 4), dann 1 Takt '1' (Zaehler-Reset), dann
    -- 3 Takte '0' (noch kein Wechsel), erst 4. '0'-Flanke schaltet.
    din <= '0';
    wait_cycles(2);
    assert dout = '1'
      report "REQ R53: Prellen nach 2 Flanken noch kein Wechsel"
      severity error;
    assert rise = '0'
      report "REQ R53: Prellen rise 0"
      severity error;
    report "CHECK t=" & time'image(now) & " prellen 2x0 dout=" & std_logic'image(dout);
    din <= '1';
    wait_cycles(1);
    assert dout = '1'
      report "REQ R53: din==dout setzt Zaehler zurueck, dout bleibt 1"
      severity error;
    assert rise = '0'
      report "REQ R53: Zaehler-Reset ohne rise"
      severity error;
    report "CHECK t=" & time'image(now) & " prellen rueck dout=" & std_logic'image(dout);
    din <= '0';
    wait_cycles(3);
    assert dout = '1'
      report "REQ R53: nach 3 aufeinanderfolgenden Flanken noch kein Wechsel"
      severity error;
    assert rise = '0'
      report "REQ R53: fallend noch kein rise"
      severity error;
    report "CHECK t=" & time'image(now) & " 3x0 dout=" & std_logic'image(dout);
    wait_cycles(1); -- 4. aufeinanderfolgende Flanke mit din /= dout
    assert dout = '0'
      report "REQ R53: nach 4. Flanke dout=0, ist " & std_logic'image(dout)
      severity error;
    assert rise = '0'
      report "REQ R53: fallender Wechsel erzeugt kein rise, ist " & std_logic'image(rise)
      severity error;
    assert rise = '0'
      report "REQ R46: nur 0->1 erzeugt Schrittimpuls, 1->0 nicht"
      severity error;
    report "CHECK t=" & time'image(now) & " wechsel auf 0 dout=" & std_logic'image(dout) &
           " rise=" & std_logic'image(rise);

    -- Zweiter Anstieg: wieder dout=1 mit genau einem rise-Takt.
    din <= '1';
    wait_cycles(DEBOUNCE_CYCLES);
    assert dout = '1'
      report "REQ R53: zweiter Anstieg dout=1"
      severity error;
    assert rise = '1'
      report "REQ R53: zweiter Anstieg rise=1"
      severity error;
    report "CHECK t=" & time'image(now) & " zweiter Anstieg dout=" & std_logic'image(dout) &
           " rise=" & std_logic'image(rise);
    wait_cycles(1);
    assert rise = '0'
      report "REQ R53: zweiter Puls auch nur einen Takt"
      severity error;
    assert rise = '0'
      report "REQ R71: Schrittimpuls genau ein Befehl (ein Takt rise)"
      severity error;

    -- Mid-Reset (R57): Entpreller-Register und Zaehler werden 0.
    rst <= '1';
    wait_cycles(2);
    assert dout = '0'
      report "REQ R57: Mid-Reset loescht dout, ist " & std_logic'image(dout)
      severity error;
    assert rise = '0'
      report "REQ R57: Mid-Reset loescht rise, ist " & std_logic'image(rise)
      severity error;
    report "CHECK t=" & time'image(now) & " mid-reset dout=" & std_logic'image(dout) &
           " rise=" & std_logic'image(rise);
    rst <= '0';
    din <= '0';
    wait_cycles(2);
    assert dout = '0'
      report "REQ R57: nach Mid-Reset wieder 0"
      severity error;
    assert rise = '0'
      report "REQ R57: nach Mid-Reset rise 0"
      severity error;
    report "CHECK t=" & time'image(now) & " nach Mid-Reset dout=" & std_logic'image(dout);

    tb_done <= true;
    report "TB_COMPLETE" severity note;
    stop;
    wait;
  end process stim;

end architecture sim;