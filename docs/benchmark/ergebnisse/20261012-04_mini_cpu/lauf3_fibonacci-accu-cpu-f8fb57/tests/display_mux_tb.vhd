library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity display_mux_tb is
end entity display_mux_tb;

architecture sim of display_mux_tb is
  signal acc       : std_logic_vector(3 downto 0) := (others => '0');
  signal c         : std_logic := '0';
  signal disp      : std_logic_vector(3 downto 0);
  signal halted    : std_logic := '0';
  signal mode      : std_logic := '0';
  signal out_value : std_logic_vector(3 downto 0) := (others => '0');
  signal pc        : std_logic_vector(3 downto 0) := (others => '0');
  signal sel       : std_logic_vector(1 downto 0) := (others => '0');
  signal z         : std_logic := '0';
begin

  dut: entity work.display_mux
    port map (
      acc       => acc,
      c         => c,
      disp      => disp,
      halted    => halted,
      mode      => mode,
      out_value => out_value,
      pc        => pc,
      sel       => sel,
      z         => z
    );

  stim: process
  begin
    -- Grundbelegung mit unterscheidbaren Werten
    acc <= "0101"; out_value <= "0001"; pc <= "1010";
    halted <= '0'; mode <= '0'; c <= '0'; z <= '0';
    sel <= "00";
    wait for 10 ns;
    report "CHECK t=" & time'image(now) & " sel=" & to_string(sel) & " disp=" & to_string(disp) & " out=" & to_string(out_value) severity note;
    assert disp = "0001" report "REQ R10: sel 00 muss OUT anzeigen" severity error;
    assert disp = out_value report "REQ R5: Anzeige OUT (LD2-LD5 = OUT)" severity error;

    -- R68: kombinatorisch, kein Takt: sel-Wechsel sofort sichtbar (1 ns reicht)
    sel <= "01";
    wait for 1 ns;
    assert disp = acc report "REQ R68: display_mux ist kombinatorisch (sel-Wechsel ohne Takt sichtbar)" severity error;
    wait for 9 ns;
    report "CHECK t=" & time'image(now) & " sel=" & to_string(sel) & " disp=" & to_string(disp) & " acc=" & to_string(acc) severity note;
    assert disp = "0101" report "REQ R10: sel 01 muss ACC anzeigen" severity error;
    assert disp = acc report "REQ R5: Anzeige ACC (LD2-LD5 = ACC)" severity error;

    -- ACC-Wechsel bei sel=01
    acc <= "0001";
    wait for 10 ns;
    report "CHECK t=" & time'image(now) & " acc=1 disp=" & to_string(disp) severity note;
    assert disp = "0001" report "REQ R10: sel 01 folgt ACC (Wert 1)" severity error;

    -- Nicht-selektierter Eingang darf disp nicht beeinflussen (sel=01, OUT aendern)
    out_value <= "1101";
    wait for 10 ns;
    assert disp = "0001" report "REQ R10: sel 01 blendet OUT aus (nur ACC)" severity error;

    -- sel=10: PC-Anzeige
    sel <= "10";
    pc <= "0001";
    wait for 10 ns;
    report "CHECK t=" & time'image(now) & " sel=10 pc=" & to_string(pc) & " disp=" & to_string(disp) severity note;
    assert disp = "0001" report "REQ R10: sel 10 muss PC anzeigen" severity error;
    assert disp = pc report "REQ R70: PC-Anzeige zeigt naechsten Befehl (PC)" severity error;

    pc <= "1111";
    wait for 10 ns;
    report "CHECK t=" & time'image(now) & " pc=15 disp=" & to_string(disp) severity note;
    assert disp = "1111" report "REQ R70: PC-Anzeige zeigt PC=15 (Endzustand nach HALT)" severity error;

    pc <= "0100";
    wait for 10 ns;
    assert disp = "0100" report "REQ R70: PC-Anzeige zeigt PC=4 (Schleifenanfang)" severity error;
    assert disp = pc report "REQ R5: Anzeige PC (LD2-LD5 = PC)" severity error;

    -- sel=11: Statusanzeige halted & mode & c & z
    sel <= "11";
    halted <= '1'; mode <= '0'; c <= '1'; z <= '0';
    wait for 10 ns;
    report "CHECK t=" & time'image(now) & " status halted=" & to_string(halted) & " mode=" & to_string(mode) & " c=" & to_string(c) & " z=" & to_string(z) & " disp=" & to_string(disp) severity note;
    assert disp = "1010" report "REQ R69: Status muss 1010 sein (HALT, Automatik, C=1, Z=0)" severity error;
    assert disp = (halted & mode & c & z) report "REQ R69: Status led(3)=HALT led(2)=Mode led(1)=C led(0)=Z" severity error;
    assert disp = "1010" report "REQ R5: Status an LEDs ablesbar (Endzustand)" severity error;

    -- R11: Betriebsart-Bit (mode = synchronisiertes sw(2))
    mode <= '1';
    wait for 10 ns;
    report "CHECK t=" & time'image(now) & " mode=1 disp=" & to_string(disp) severity note;
    assert disp = "1110" report "REQ R11: Einzelschritt (mode=1) in Status-Bit 2 sichtbar" severity error;
    assert disp(2) = '1' report "REQ R69: Status-Bit 2 ist Betriebsart" severity error;

    mode <= '0';
    wait for 10 ns;
    assert disp = "1010" report "REQ R11: Automatik (mode=0) in Status-Bit 2 sichtbar" severity error;

    -- Weitere Status-Kombinationen
    halted <= '0'; mode <= '0'; c <= '0'; z <= '0';
    wait for 10 ns;
    assert disp = "0000" report "REQ R69: Status 0000 nach Reset (alle Register 0)" severity error;

    halted <= '0'; mode <= '1'; c <= '0'; z <= '1';
    wait for 10 ns;
    report "CHECK t=" & time'image(now) & " status disp=" & to_string(disp) severity note;
    assert disp = "0101" report "REQ R69: Status 0101 (kein HALT, Einzelschritt, C=0, Z=1)" severity error;

    halted <= '1'; mode <= '1'; c <= '1'; z <= '1';
    wait for 10 ns;
    assert disp = "1111" report "REQ R69: Status 1111 (alle Flags gesetzt)" severity error;

    -- Fibonacci-OUT-Folge ueber sel=00 (R5-Anbindung an Demoprogramm)
    sel <= "00";
    halted <= '0'; mode <= '0'; c <= '0'; z <= '0';
    out_value <= "0001";
    wait for 10 ns;
    assert disp = "0001" report "REQ R5: OUT-Folge Wert 1 sichtbar" severity error;
    out_value <= "0010";
    wait for 10 ns;
    assert disp = "0010" report "REQ R5: OUT-Folge Wert 2 sichtbar" severity error;
    out_value <= "0011";
    wait for 10 ns;
    assert disp = "0011" report "REQ R5: OUT-Folge Wert 3 sichtbar" severity error;
    out_value <= "0101";
    wait for 10 ns;
    report "CHECK t=" & time'image(now) & " out=5 disp=" & to_string(disp) severity note;
    assert disp = "0101" report "REQ R5: OUT-Folge Wert 5 sichtbar" severity error;
    out_value <= "1000";
    wait for 10 ns;
    assert disp = "1000" report "REQ R5: OUT-Folge Wert 8 sichtbar" severity error;
    out_value <= "1101";
    wait for 10 ns;
    report "CHECK t=" & time'image(now) & " out=13 disp=" & to_string(disp) severity note;
    assert disp = "1101" report "REQ R5: OUT-Folge Wert 13 (Endzustand OUT=13) sichtbar" severity error;

    -- ACC-Endzustand 5 ueber sel=01
    sel <= "01";
    acc <= "0101";
    wait for 10 ns;
    assert disp = "0101" report "REQ R5: ACC=5 nach HALT sichtbar" severity error;

    report "TB_COMPLETE" severity note;
    wait;
  end process stim;

end architecture sim;