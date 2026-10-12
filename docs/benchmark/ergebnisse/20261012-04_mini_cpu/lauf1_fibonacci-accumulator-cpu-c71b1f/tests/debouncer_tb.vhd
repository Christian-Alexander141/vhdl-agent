library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
library std;
use std.env.all;

entity debouncer_tb is
end entity debouncer_tb;

architecture sim of debouncer_tb is
  constant CLK_PERIOD : time := 10 ns;
  constant D          : positive := 4;

  signal clk     : std_logic := '0';
  signal rst     : std_logic := '1';
  signal din     : std_logic := '0';
  signal dout    : std_logic;
  signal rise    : std_logic;
  signal tb_done : boolean := false;
begin
  clk <= not clk after CLK_PERIOD / 2 when not tb_done else '0';

  dut: entity work.debouncer
    generic map (
      DEBOUNCE_CYCLES => D
    )
    port map (
      clk  => clk,
      rst  => rst,
      din  => din,
      dout => dout,
      rise => rise
    );

  stim: process
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
    din <= '0';
    wait_cycles(2);
    report "CHECK t=" & time'image(now) & " after reset-hold dout=" & std_logic'image(dout) & " rise=" & std_logic'image(rise);
    assert dout = '0' report "REQ R71: nach Reset muss dout='0' sein" severity error;
    assert rise = '0' report "REQ R71: nach Reset muss rise='0' sein" severity error;

    -- Reset loesen, stabil 0.
    rst <= '0';
    wait_cycles(2);
    report "CHECK t=" & time'image(now) & " idle dout=" & std_logic'image(dout) & " rise=" & std_logic'image(rise);
    assert dout = '0' report "REQ R71: nach Reset-loesen bleibt dout='0'" severity error;
    assert rise = '0' report "REQ R71: nach Reset-loesen bleibt rise='0'" severity error;

    -- Kurzpuls < DEBOUNCE_CYCLES (D-1=3 Flanken): kein Umschalten.
    din <= '1';
    wait_cycles(3);
    report "CHECK t=" & time'image(now) & " short-pulse dout=" & std_logic'image(dout) & " rise=" & std_logic'image(rise);
    assert dout = '0' report "REQ R62: Puls kuerzer als DEBOUNCE_CYCLES darf dout nicht umschalten" severity error;
    assert rise = '0' report "REQ R63: Kurzplus darf kein rise erzeugen" severity error;
    assert dout = '0' report "REQ R60: entprellt - Kurzimpuls kein Schritt" severity error;

    -- Eingang zurueck auf 0: Zaehler muss verworfen werden (R61).
    din <= '0';
    wait_cycles(2);
    report "CHECK t=" & time'image(now) & " after-short dout=" & std_logic'image(dout);
    assert dout = '0' report "REQ R61: bei Eingang=dout wird Zaehler 0, dout bleibt 0" severity error;
    assert rise = '0' report "REQ R52: ohne stabilen Schritt kein go/rise" severity error;

    -- Stabile 1: erste D-1 Flanken kein Wechsel.
    din <= '1';
    wait_cycles(3);
    report "CHECK t=" & time'image(now) & " pre-switch dout=" & std_logic'image(dout) & " rise=" & std_logic'image(rise);
    assert dout = '0' report "REQ R62: dout erst an DEBOUNCE_CYCLES-ter Flanke, nach D-1 noch 0" severity error;
    assert rise = '0' report "REQ R63: rise vor Umschaltung 0" severity error;

    -- D-te Flanke: dout 0->1 und rise='1' genau einen Takt.
    wait_cycles(1);
    report "CHECK t=" & time'image(now) & " switched dout=" & std_logic'image(dout) & " rise=" & std_logic'image(rise);
    assert dout = '1' report "REQ R62: dout wechselt mit DEBOUNCE_CYCLES-ter Flanke auf 1" severity error;
    assert rise = '1' report "REQ R63: rise=1 mit Flanke des dout-Wechsels 0->1" severity error;
    assert rise = '1' report "REQ R52: Schrittimpuls rise als go im Einzelschritt" severity error;
    assert dout = '1' report "REQ R61: bei Zaehler=DEBOUNCE_CYCLES-1 uebernimmt dout den Eingang" severity error;

    -- Naechste Flanke: rise genau einen Takt -> wieder 0, dout bleibt 1.
    wait_cycles(1);
    report "CHECK t=" & time'image(now) & " after-rise dout=" & std_logic'image(dout) & " rise=" & std_logic'image(rise);
    assert dout = '1' report "REQ R62: dout bleibt 1 bei stabilem Eingang" severity error;
    assert rise = '0' report "REQ R63: rise genau einen Takt lang 1" severity error;
    assert rise = '0' report "REQ R9: pro Druck genau ein Schrittimpuls (kein Dauer-1)" severity error;

    wait_cycles(2);
    assert dout = '1' report "REQ R61: bei Eingang=dout Zaehler 0, dout stabil 1" severity error;
    assert rise = '0' report "REQ R52: stabiles dout erzeugt kein weiteres rise/go" severity error;

    -- Prellen: 1 Flanke 0, dann zurueck 1 -> kein Wechsel (Zaehler verworfen).
    din <= '0';
    wait_cycles(1);
    report "CHECK t=" & time'image(now) & " bounce dout=" & std_logic'image(dout);
    assert dout = '1' report "REQ R61: einzelne abweichende Flanke schaltet nicht (Zaehler=1)" severity error;
    din <= '1';
    wait_cycles(2);
    assert dout = '1' report "REQ R60: Prellen wird entprellt, dout bleibt 1" severity error;
    assert rise = '0' report "REQ R63: Prellen erzeugt kein rise" severity error;

    -- Stabiles 0: D-1 Flanken noch 1, D-te Flanke 1->0 ohne rise.
    din <= '0';
    wait_cycles(3);
    report "CHECK t=" & time'image(now) & " pre-fall dout=" & std_logic'image(dout);
    assert dout = '1' report "REQ R62: fallend erst an D-ter Flanke, nach D-1 noch 1" severity error;
    wait_cycles(1);
    report "CHECK t=" & time'image(now) & " fallen dout=" & std_logic'image(dout) & " rise=" & std_logic'image(rise);
    assert dout = '0' report "REQ R62: dout faellt mit D-ter Flanke auf 0" severity error;
    assert rise = '0' report "REQ R63: Wechsel 1->0 erzeugt kein rise" severity error;
    wait_cycles(1);
    assert dout = '0' report "REQ R61: nach Fall dout stabil 0" severity error;
    assert rise = '0' report "REQ R63: rise bleibt 0 nach 1->0" severity error;

    -- Zweiter stabiler Druck: wieder genau ein rise (R9 Wiederholbarkeit).
    din <= '1';
    wait_cycles(3);
    assert dout = '0' report "REQ R62: zweiter Druck braucht wieder D Flanken" severity error;
    wait_cycles(1);
    assert dout = '1' report "REQ R9: zweiter Druck schaltet dout wieder auf 1" severity error;
    assert rise = '1' report "REQ R9: zweiter Druck erzeugt genau einen Schrittimpuls" severity error;
    wait_cycles(1);
    assert rise = '0' report "REQ R9: rise auch beim zweiten Druck nur einen Takt" severity error;
    assert dout = '1' report "REQ R60: zweiter stabiler Druck entprellt auf 1" severity error;

    -- Reset mitten im Betrieb: alles auf 0.
    rst <= '1';
    wait_cycles(2);
    report "CHECK t=" & time'image(now) & " mid-reset dout=" & std_logic'image(dout) & " rise=" & std_logic'image(rise);
    assert dout = '0' report "REQ R71: synchroner Reset mitten im Betrieb loescht dout" severity error;
    assert rise = '0' report "REQ R71: synchroner Reset mitten im Betrieb loescht rise" severity error;
    rst <= '0';
    -- din ist noch 1: nach Reset braucht es wieder volle D Flanken.
    wait_cycles(2);
    report "CHECK t=" & time'image(now) & " post-reset dout=" & std_logic'image(dout);
    assert dout = '0' report "REQ R71: nach Reset beginnt Zaehler von vorn (nach 2 Flanken noch 0)" severity error;
    wait_cycles(2);
    assert dout = '1' report "REQ R71: nach Reset und D stabilen Flanken wieder 1" severity error;
    assert rise = '1' report "REQ R52: nach Reset funktioniert Schrittimpuls wieder" severity error;
    wait_cycles(1);
    assert rise = '0' report "REQ R63: rise nach Reset wieder nur einen Takt" severity error;

    -- Reset waehrend des Zaehlens verwirft Teilmessung.
    din <= '0';
    wait_cycles(4);
    assert dout = '0' report "REQ R62: Vorbereitung fallend ok" severity error;
    din <= '1';
    wait_cycles(2);
    rst <= '1';
    wait_cycles(1);
    assert dout = '0' report "REQ R71: Reset waehrend Zaehlung haelt dout 0" severity error;
    rst <= '0';
    wait_cycles(2);
    assert dout = '0' report "REQ R71: Teilzaehlung vor Reset verworfen, nach 2 Flanken noch 0" severity error;
    wait_cycles(2);
    assert dout = '1' report "REQ R61: nach Reset volle D Flanken bis Wechsel noetig" severity error;

    tb_done <= true;
    report "TB_COMPLETE" severity note;
    wait;
  end process stim;

end architecture sim;