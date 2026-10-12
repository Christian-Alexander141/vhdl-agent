library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.env.all;

entity display_mux_tb is
end entity display_mux_tb;

architecture sim of display_mux_tb is
  signal sel       : std_logic_vector(1 downto 0) := "00";
  signal mode      : std_logic := '0';
  signal out_value : std_logic_vector(3 downto 0) := (others => '0');
  signal acc       : std_logic_vector(3 downto 0) := (others => '0');
  signal pc        : std_logic_vector(3 downto 0) := (others => '0');
  signal z         : std_logic := '0';
  signal c         : std_logic := '0';
  signal halted    : std_logic := '0';
  signal disp      : std_logic_vector(3 downto 0);

  signal tb_done : boolean := false;
begin

  dut: entity work.display_mux
    port map (
      sel       => sel,
      mode      => mode,
      out_value => out_value,
      acc       => acc,
      pc        => pc,
      z         => z,
      c         => c,
      halted    => halted,
      disp      => disp
    );

  stim: process
    variable exp : std_logic_vector(3 downto 0);
  begin
    -- Breitenpruefung (R3: 4 LEDs ablesbar)
    assert disp'length = 4 report "REQ R3: disp-Breite muss 4 sein (LD2-LD5)" severity error;
    report "CHECK t=" & time'image(now) & " disp_len=" & integer'image(disp'length);

    -- R8: sel="00" -> OUT (Fibonacci-Folge 1,2,3,5,8,13 aus PROMPT.md)
    sel <= "00"; mode <= '0'; halted <= '0'; z <= '0'; c <= '0';
    acc <= "1111"; pc <= "1111"; -- Stoerwerte: duerfen OUT-Auswahl nicht beeinflussen
    out_value <= "0001"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " sel=" & to_string(sel) & " out=" & to_string(out_value) & " disp=" & to_string(disp);
    assert disp = "0001" report "REQ R8: sel 00 muss OUT zeigen (OUT=1)" severity error;
    out_value <= "0010"; wait for 10 ns;
    assert disp = "0010" report "REQ R8: sel 00 muss OUT zeigen (OUT=2)" severity error;
    out_value <= "0011"; wait for 10 ns;
    assert disp = "0011" report "REQ R8: sel 00 muss OUT zeigen (OUT=3)" severity error;
    out_value <= "0101"; wait for 10 ns;
    assert disp = "0101" report "REQ R8: sel 00 muss OUT zeigen (OUT=5)" severity error;
    out_value <= "1000"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " sel=" & to_string(sel) & " out=" & to_string(out_value) & " disp=" & to_string(disp);
    assert disp = "1000" report "REQ R8: sel 00 muss OUT zeigen (OUT=8)" severity error;
    out_value <= "1101"; wait for 10 ns;
    assert disp = "1101" report "REQ R3: OUT=13 muss an disp ablesbar sein (sel=00)" severity error;
    assert disp = "1101" report "REQ R8: sel 00 muss OUT zeigen (OUT=13)" severity error;

    -- R3/R8: sel="01" -> ACC
    sel <= "01"; out_value <= "0000"; pc <= "0000";
    acc <= "0101"; wait for 10 ns; -- ACC=5 (Endzustand PROMPT.md)
    report "CHECK t=" & time'image(now) & " sel=" & to_string(sel) & " acc=" & to_string(acc) & " disp=" & to_string(disp);
    assert disp = "0101" report "REQ R8: sel 01 muss ACC zeigen (ACC=5)" severity error;
    assert disp = "0101" report "REQ R3: ACC=5 muss an disp ablesbar sein (sel=01)" severity error;
    acc <= "0001"; wait for 10 ns;
    assert disp = "0001" report "REQ R8: sel 01 muss ACC zeigen (ACC=1)" severity error;
    -- Isolation: OUT-Aenderung darf ACC-Anzeige nicht beeinflussen
    out_value <= "1101"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " isol sel=" & to_string(sel) & " out=" & to_string(out_value) & " acc=" & to_string(acc) & " disp=" & to_string(disp);
    assert disp = "0001" report "REQ R8: sel 01 darf nicht auf OUT reagieren" severity error;

    -- R8/R70: sel="10" -> PC (Adresse des naechsten Befehls)
    sel <= "10"; acc <= "0000"; out_value <= "0000";
    pc <= "0001"; wait for 10 ns; -- PC=1 nach erstem Befehl
    report "CHECK t=" & time'image(now) & " sel=" & to_string(sel) & " pc=" & to_string(pc) & " disp=" & to_string(disp);
    assert disp = "0001" report "REQ R8: sel 10 muss PC zeigen (PC=1)" severity error;
    assert disp = "0001" report "REQ R70: PC-Anzeige muss naechsten Befehl zeigen (PC=1)" severity error;
    pc <= "1111"; wait for 10 ns; -- PC=15 Endzustand PROMPT.md
    report "CHECK t=" & time'image(now) & " sel=" & to_string(sel) & " pc=" & to_string(pc) & " disp=" & to_string(disp);
    assert disp = "1111" report "REQ R8: sel 10 muss PC zeigen (PC=15)" severity error;
    assert disp = "1111" report "REQ R70: PC-Anzeige muss Endwert 15 zeigen" severity error;
    assert disp = "1111" report "REQ R3: PC=15 muss an disp ablesbar sein (sel=10)" severity error;
    pc <= "0100"; wait for 10 ns;
    assert disp = "0100" report "REQ R70: PC-Anzeige muss PC=4 zeigen" severity error;

    -- R8/R69: sel="11" -> Status halted & mode & c & z
    -- Endzustand PROMPT.md: HALT=1, Automatik mode=0, C=1, Z=0 -> "1010"
    sel <= "11"; halted <= '1'; mode <= '0'; c <= '1'; z <= '0';
    out_value <= "1101"; acc <= "0101"; pc <= "1111"; -- duerfen Status nicht beeinflussen
    wait for 10 ns;
    report "CHECK t=" & time'image(now) & " sel=" & to_string(sel) & " h=" & std_logic'image(halted) & " m=" & std_logic'image(mode) & " c=" & std_logic'image(c) & " z=" & std_logic'image(z) & " disp=" & to_string(disp);
    assert disp = "1010" report "REQ R69: Status muss 1010 sein (HALT=1,Auto=0,C=1,Z=0)" severity error;
    assert disp = "1010" report "REQ R8: sel 11 muss Status zeigen (1010)" severity error;
    assert disp = "1010" report "REQ R3: Status 1010 muss an disp ablesbar sein (sel=11)" severity error;

    -- R69: Bitreihenfolge halted & mode & c & z, einzelne Bits
    halted <= '0'; mode <= '0'; c <= '0'; z <= '0'; wait for 10 ns;
    assert disp = "0000" report "REQ R69: Status 0000 erwartet" severity error;
    halted <= '1'; mode <= '0'; c <= '0'; z <= '0'; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " status disp=" & to_string(disp);
    assert disp = "1000" report "REQ R69: led(3) muss HALT sein" severity error;
    halted <= '0'; mode <= '1'; c <= '0'; z <= '0'; wait for 10 ns;
    assert disp = "0100" report "REQ R69: led(2) muss Betriebsart mode sein" severity error;
    halted <= '0'; mode <= '0'; c <= '1'; z <= '0'; wait for 10 ns;
    assert disp = "0010" report "REQ R69: led(1) muss C sein" severity error;
    halted <= '0'; mode <= '0'; c <= '0'; z <= '1'; wait for 10 ns;
    assert disp = "0001" report "REQ R69: led(0) muss Z sein" severity error;
    halted <= '1'; mode <= '1'; c <= '1'; z <= '1'; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " status disp=" & to_string(disp);
    assert disp = "1111" report "REQ R69: Status 1111 erwartet" severity error;
    -- Einzelschritt-Betriebsart: mode=1 sichtbar
    halted <= '0'; mode <= '1'; c <= '0'; z <= '1'; wait for 10 ns;
    assert disp = "0101" report "REQ R69: Status mit mode=1 (Einzelschritt) muss 0101 sein" severity error;

    -- R69 vollstaendiger Nibble-Sweep: disp muss Eingabe-Nibble entsprechen
    for i in 0 to 15 loop
      halted <= std_logic(to_unsigned(i, 4)(3));
      mode   <= std_logic(to_unsigned(i, 4)(2));
      c      <= std_logic(to_unsigned(i, 4)(1));
      z      <= std_logic(to_unsigned(i, 4)(0));
      wait for 10 ns;
      exp := std_logic_vector(to_unsigned(i, 4));
      assert disp = exp report "REQ R69: Status-Sweep " & integer'image(i) & " fehlerhaft" severity error;
    end loop;
    report "CHECK t=" & time'image(now) & " status-sweep done disp=" & to_string(disp);

    -- R67: display_mux ist kombinatorisch (kein Takt): Aenderung sofort sichtbar
    sel <= "00"; out_value <= "0011"; acc <= "0000"; pc <= "0000";
    halted <= '0'; mode <= '0'; c <= '0'; z <= '0';
    wait for 10 ns;
    assert disp = "0011" report "REQ R67: Kombinatorik Basis OUT=3" severity error;
    out_value <= "0101"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " comb out=" & to_string(out_value) & " disp=" & to_string(disp);
    assert disp = "0101" report "REQ R67: disp muss OUT-Aenderung ohne Takt folgen (LED-Register ausserhalb, Mux selbst taktfrei)" severity error;
    -- sel-Umschaltung ebenfalls taktfrei
    acc <= "1001";
    sel <= "01"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " comb sel=" & to_string(sel) & " acc=" & to_string(acc) & " disp=" & to_string(disp);
    assert disp = "1001" report "REQ R67: disp muss sel-Wechsel ohne Takt folgen" severity error;

    -- R68: Schalter-Latenz 3 Flanken entsteht in sync2+LED-Register, Mux selbst 0 Flanken
    sel <= "10"; pc <= "0110"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " sel=" & to_string(sel) & " pc=" & to_string(pc) & " disp=" & to_string(disp);
    assert disp = "0110" report "REQ R68: Mux-Auswahl selbst ist ohne Takt sichtbar (System-Latenz 3 anderswo)" severity error;
    pc <= "0111"; wait for 10 ns;
    assert disp = "0111" report "REQ R68: CPU-Registeraenderung am Mux ohne extra Takt sichtbar" severity error;

    tb_done <= true;
    assert false report "TB_COMPLETE" severity note;
    std.env.stop;
    wait;
  end process stim;

end architecture sim;