library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity debouncer_tb is
end entity debouncer_tb;

architecture sim of debouncer_tb is
  constant DEBOUNCE_CYCLES_TB : positive := 4;
  constant CLK_PERIOD          : time := 10 ns;

  signal clk   : std_logic := '0';
  signal rst   : std_logic := '1';
  signal din   : std_logic := '0';
  signal dout  : std_logic;
  signal rise  : std_logic;

  signal tb_done : boolean := false;
begin
  clk <= not clk after CLK_PERIOD / 2 when not tb_done else '0';

  dut: entity work.debouncer
    generic map (
      DEBOUNCE_CYCLES => DEBOUNCE_CYCLES_TB
    )
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
      wait for 1 ns;
    end procedure;
  begin
    -- Reset sequence (min. 2 cycles rst='1')
    rst <= '1';
    din <= '0';
    wait_cycles(2);
    assert dout = '0' report "REQ R4: nach Sync-Reset dout=0" severity error;
    assert rise = '0' report "REQ R4: nach Sync-Reset rise=0" severity error;
    assert dout = '0' report "REQ R43: bei rst=1 Entpreller in Ruhe (dout=0)" severity error;
    assert rise = '0' report "REQ R43: bei rst=1 Entpreller in Ruhe (rise=0)" severity error;
    report "CHECK t=" & time'image(now) & " nach Reset dout=" & std_logic'image(dout) & " rise=" & std_logic'image(rise);
    rst <= '0';
    wait_cycles(2);

    -- TC1: stabiler Eingang -> keine Aenderung (R39)
    din <= '0';
    wait_cycles(5);
    assert dout = '0' report "REQ R39: stabiler Eingang din=dout haelt dout=0" severity error;
    assert rise = '0' report "REQ R39: stabiler Eingang erzeugt kein rise" severity error;
    report "CHECK t=" & time'image(now) & " idle dout=" & std_logic'image(dout) & " rise=" & std_logic'image(rise);

    -- TC2: kurzer Stoerimpuls (< DEBOUNCE_CYCLES) wird ignoriert (R39)
    din <= '1';
    wait_cycles(2);
    din <= '0';
    wait_cycles(2);
    assert dout = '0' report "REQ R39: Glitch 2 Takte < 4 wird ignoriert, dout bleibt 0" severity error;
    assert rise = '0' report "REQ R39: Glitch erzeugt kein rise" severity error;
    report "CHECK t=" & time'image(now) & " nach Glitch dout=" & std_logic'image(dout) & " rise=" & std_logic'image(rise);

    -- TC3: gueltiger Druck -> nach genau DEBOUNCE_CYCLES Flanke + rise (R39/R5/R74)
    din <= '1';
    wait_cycles(3);
    assert dout = '0' report "REQ R39: nach 3 Takten noch kein Wechsel (braucht 4)" severity error;
    assert rise = '0' report "REQ R39: vor Erreichen von DEBOUNCE_CYCLES kein rise" severity error;
    report "CHECK t=" & time'image(now) & " vor Flanke dout=" & std_logic'image(dout) & " rise=" & std_logic'image(rise);
    wait_cycles(1); -- 4. Takt mit abweichendem Eingang
    assert dout = '1' report "REQ R39: nach 4 Takten uebernimmt dout den Eingang" severity error;
    assert rise = '1' report "REQ R39: rise=1 genau mit 0->1-Flanke von dout" severity error;
    assert dout = '1' report "REQ R5: Tastendruck setzt dout=1" severity error;
    assert rise = '1' report "REQ R5: je Druck genau ein rise-Impuls" severity error;
    assert rise = '1' report "REQ R74: jeder Druck erzeugt genau einen Mikroschritt (rise=1)" severity error;
    report "CHECK t=" & time'image(now) & " Flanke dout=" & std_logic'image(dout) & " rise=" & std_logic'image(rise);
    -- rise genau einen Takt lang
    wait_cycles(1);
    assert dout = '1' report "REQ R39: dout bleibt 1 bei stabilem Eingang" severity error;
    assert rise = '0' report "REQ R39: rise faellt nach genau einem Takt auf 0" severity error;
    assert rise = '0' report "REQ R5: rise nicht laenger als einen Takt" severity error;
    report "CHECK t=" & time'image(now) & " nach rise dout=" & std_logic'image(dout) & " rise=" & std_logic'image(rise);

    -- TC4: langes Halten -> kein weiteres rise (R5/R74: ohne neuen Druck kein Fortschritt)
    wait_cycles(10);
    assert dout = '1' report "REQ R5: Halten erzeugt keinen zweiten Wechsel" severity error;
    assert rise = '0' report "REQ R5: Halten erzeugt kein weiteres rise" severity error;
    assert rise = '0' report "REQ R74: ohne neuen Druck kein weiterer Mikroschritt" severity error;
    report "CHECK t=" & time'image(now) & " Halten dout=" & std_logic'image(dout) & " rise=" & std_logic'image(rise);

    -- TC5: fallende Flanke -> nach 4 Takten dout=0, kein rise (R39)
    din <= '0';
    wait_cycles(3);
    assert dout = '1' report "REQ R39: fallend nach 3 Takten noch kein Wechsel" severity error;
    assert rise = '0' report "REQ R39: fallend vorab kein rise" severity error;
    wait_cycles(1);
    assert dout = '0' report "REQ R39: fallend nach 4 Takten dout=0" severity error;
    assert rise = '0' report "REQ R39: 1->0-Wechsel erzeugt kein rise" severity error;
    report "CHECK t=" & time'image(now) & " fallend dout=" & std_logic'image(dout) & " rise=" & std_logic'image(rise);
    wait_cycles(1);
    assert rise = '0' report "REQ R39: nach fallender Flanke bleibt rise=0" severity error;

    -- TC6: zweiter Druck -> wieder genau ein rise (R5/R74 Wiederholbarkeit)
    din <= '1';
    wait_cycles(4);
    assert dout = '1' report "REQ R5: zweiter Druck setzt dout wieder 1" severity error;
    assert rise = '1' report "REQ R5: zweiter Druck erzeugt wieder genau ein rise" severity error;
    assert rise = '1' report "REQ R74: zweiter Druck = ein Mikroschritt" severity error;
    report "CHECK t=" & time'image(now) & " 2.Druck dout=" & std_logic'image(dout) & " rise=" & std_logic'image(rise);
    wait_cycles(1);
    assert rise = '0' report "REQ R74: zweiter rise ebenfalls nur einen Takt" severity error;

    -- TC7: synchroner Reset (R4) und Reset-Ruhe (R43)
    -- dout ist jetzt 1; rst ohne Flanke darf nichts aendern (sync-Nachweis)
    rst <= '1';
    wait for 1 ns; -- keine Taktflanke dazwischen
    assert dout = '1' report "REQ R4: Reset ist synchron (kein sofortiges Loeschen ohne Flanke)" severity error;
    report "CHECK t=" & time'image(now) & " rst ohne Flanke dout=" & std_logic'image(dout) & " rise=" & std_logic'image(rise);
    wait_cycles(1); -- erste Flanke mit rst=1
    assert dout = '0' report "REQ R4: Sync-Reset active high loescht dout mit Flanke" severity error;
    assert rise = '0' report "REQ R4: Sync-Reset loescht rise mit Flanke" severity error;
    assert dout = '0' report "REQ R43: bei rst=1 Entpreller 0 trotz din=1" severity error;
    assert rise = '0' report "REQ R43: bei rst=1 kein rise trotz din=1" severity error;
    report "CHECK t=" & time'image(now) & " im Reset dout=" & std_logic'image(dout) & " rise=" & std_logic'image(rise);
    din <= '1';
    wait_cycles(2); -- rst bleibt 1, din=1: muss in Ruhe bleiben
    assert dout = '0' report "REQ R43: RAM/Entpreller bleiben bei rst=1 in Ruhe" severity error;
    assert rise = '0' report "REQ R43: kein rise waehrend rst=1" severity error;
    rst <= '0';
    din <= '0';
    wait_cycles(2);

    -- TC8: ohne Druck kein Fortschritt (R74)
    din <= '0';
    wait_cycles(5);
    assert dout = '0' report "REQ R74: ohne Tastendruck kein Fortschritt (dout=0)" severity error;
    assert rise = '0' report "REQ R74: ohne Tastendruck kein rise" severity error;
    report "CHECK t=" & time'image(now) & " final dout=" & std_logic'image(dout) & " rise=" & std_logic'image(rise);

    tb_done <= true;
    report "TB_COMPLETE" severity note;
    std.env.stop;
    wait;
  end process stim;

end architecture sim;