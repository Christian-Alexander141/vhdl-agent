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
    -- Unterscheidbare Startwerte (Fibonacci-Kontext aus PROMPT.md)
    out_value <= "0001"; -- 1
    acc       <= "0101"; -- 5
    pc        <= "1111"; -- 15
    z         <= '0';
    c         <= '1';
    halted    <= '1';
    mode      <= '0';
    sel       <= "00";
    wait for 10 ns;

    -- R6: sel="00" -> OUT
    assert disp = "0001"
      report "REQ R6: sel 00 muss OUT zeigen, disp=" & integer'image(to_integer(unsigned(disp)))
      severity error;
    report "CHECK t=" & time'image(now) & " sel=0 out=" & integer'image(to_integer(unsigned(out_value))) & " disp=" & integer'image(to_integer(unsigned(disp)));

    -- R5: sel entspricht sw(1 downto 0); "01" -> ACC
    sel <= "01";
    wait for 10 ns;
    assert disp = "0101"
      report "REQ R5: sel 01 (sw=01) muss ACC zeigen, disp=" & integer'image(to_integer(unsigned(disp)))
      severity error;
    assert disp = acc
      report "REQ R6: sel 01 muss ACC zeigen"
      severity error;
    report "CHECK t=" & time'image(now) & " sel=1 acc=" & integer'image(to_integer(unsigned(acc))) & " disp=" & integer'image(to_integer(unsigned(disp)));

    -- R6: sel="10" -> PC (Adresse des naechsten Befehls)
    sel <= "10";
    wait for 10 ns;
    assert disp = "1111"
      report "REQ R6: sel 10 muss PC zeigen, disp=" & integer'image(to_integer(unsigned(disp)))
      severity error;
    report "CHECK t=" & time'image(now) & " sel=2 pc=" & integer'image(to_integer(unsigned(pc))) & " disp=" & integer'image(to_integer(unsigned(disp)));

    -- R6+R56: sel="11" -> Status halted & mode & c & z = "1010"
    -- (HALT=1, Automatik mode=0, C=1, Z=0 wie nach 58. Befehl in PROMPT.md)
    sel <= "11";
    wait for 10 ns;
    assert disp = "1010"
      report "REQ R6: sel 11 muss Status 1010 zeigen, disp=" & integer'image(to_integer(unsigned(disp)))
      severity error;
    assert disp = (halted & mode & c & z)
      report "REQ R56: Status muss halted&mode&c&z sein"
      severity error;
    report "CHECK t=" & time'image(now) & " status disp=" & integer'image(to_integer(unsigned(disp))) & " halted=" & std_logic'image(halted) & " mode=" & std_logic'image(mode) & " c=" & std_logic'image(c) & " z=" & std_logic'image(z);

    -- R7: mode = synchronisiertes sw(2); led(2)=Betriebsart
    -- mode='1' (Einzelschritt) -> Status "1110"
    mode <= '1';
    wait for 10 ns;
    assert disp = "1110"
      report "REQ R7: mode 1 (Einzelschritt) muss in Status Bit2 erscheinen, disp=" & integer'image(to_integer(unsigned(disp)))
      severity error;
    assert disp(2) = '1'
      report "REQ R56: led(2) muss Betriebsart mode sein"
      severity error;
    report "CHECK t=" & time'image(now) & " mode=1 disp=" & integer'image(to_integer(unsigned(disp)));
    mode <= '0';
    wait for 10 ns;
    assert disp(2) = '0'
      report "REQ R7: mode 0 (Automatik) muss in Status Bit2 erscheinen"
      severity error;

    -- R56: alle Status-Bits einzeln (HALT, C, Z)
    halted <= '0'; c <= '0'; z <= '0'; mode <= '0';
    wait for 10 ns;
    assert disp = "0000"
      report "REQ R56: Status 0000 erwartet, disp=" & integer'image(to_integer(unsigned(disp)))
      severity error;
    halted <= '1';
    wait for 10 ns;
    assert disp(3) = '1'
      report "REQ R56: led(3) muss HALT sein"
      severity error;
    halted <= '0'; c <= '1';
    wait for 10 ns;
    assert disp(1) = '1'
      report "REQ R56: led(1) muss C sein"
      severity error;
    c <= '0'; z <= '1';
    wait for 10 ns;
    assert disp(0) = '1'
      report "REQ R56: led(0) muss Z sein"
      severity error;
    report "CHECK t=" & time'image(now) & " einzelbits disp=" & integer'image(to_integer(unsigned(disp)));
    -- Vollstaendiger Status-Vektor "0111" gegen Konkatenation
    halted <= '0'; mode <= '1'; c <= '1'; z <= '1';
    wait for 10 ns;
    exp := halted & mode & c & z;
    assert disp = exp
      report "REQ R56: Status-Vektor muss halted&mode&c&z entsprechen"
      severity error;

    -- R56: erschöpfend alle 16 Status-Kombinationen
    for h in 0 to 1 loop
      for m in 0 to 1 loop
        for cc in 0 to 1 loop
          for zz in 0 to 1 loop
            if h = 1 then halted <= '1'; else halted <= '0'; end if;
            if m = 1 then mode <= '1'; else mode <= '0'; end if;
            if cc = 1 then c <= '1'; else c <= '0'; end if;
            if zz = 1 then z <= '1'; else z <= '0'; end if;
            wait for 10 ns;
            exp := halted & mode & c & z;
            assert disp = exp
              report "REQ R56: Status-Kombi h=" & integer'image(h) & " m=" & integer'image(m) & " c=" & integer'image(cc) & " z=" & integer'image(zz) & " disp=" & integer'image(to_integer(unsigned(disp)))
              severity error;
          end loop;
        end loop;
      end loop;
    end loop;
    report "CHECK t=" & time'image(now) & " 16 Status-Kombis ok";

    -- Fibonacci-Werte aus PROMPT.md auf allen drei Datenquellen
    halted <= '0'; mode <= '0'; c <= '0'; z <= '0';
    -- OUT-Folge 1,2,3,5,8,13
    sel <= "00";
    out_value <= "0001"; wait for 10 ns;
    assert disp = "0001" report "REQ R6: OUT=1" severity error;
    out_value <= "0010"; wait for 10 ns;
    assert disp = "0010" report "REQ R6: OUT=2" severity error;
    out_value <= "0011"; wait for 10 ns;
    assert disp = "0011" report "REQ R6: OUT=3" severity error;
    out_value <= "0101"; wait for 10 ns;
    assert disp = "0101" report "REQ R6: OUT=5" severity error;
    out_value <= "1000"; wait for 10 ns;
    assert disp = "1000" report "REQ R6: OUT=8" severity error;
    out_value <= "1101"; wait for 10 ns;
    assert disp = "1101" report "REQ R6: OUT=13" severity error;
    report "CHECK t=" & time'image(now) & " OUT-Folge 1,2,3,5,8,13 ok disp=" & integer'image(to_integer(unsigned(disp)));
    -- ACC-Pfad (Endwert ACC=5 nach Halt)
    sel <= "01";
    acc <= "0101"; wait for 10 ns;
    assert disp = "0101" report "REQ R6: ACC=5 Endwert" severity error;
    acc <= "0000"; wait for 10 ns;
    assert disp = "0000" report "REQ R6: ACC=0" severity error;
    acc <= "1111"; wait for 10 ns;
    assert disp = "1111" report "REQ R6: ACC=15" severity error;
    -- PC-Pfad (Endwert PC=15 nach Halt)
    sel <= "10";
    pc <= "1111"; wait for 10 ns;
    assert disp = "1111" report "REQ R6: PC=15 Endwert" severity error;
    pc <= "0100"; wait for 10 ns;
    assert disp = "0100" report "REQ R6: PC=4 Schleifenanfang" severity error;
    pc <= "0000"; wait for 10 ns;
    assert disp = "0000" report "REQ R6: PC=0 Anfang" severity error;
    report "CHECK t=" & time'image(now) & " ACC/PC-Pfade ok";

    -- R55: display_mux ist kombinatorisch (kein LED-Register hier):
    -- disp folgt Eingangswechsel ohne Takt, innerhalb eines Delta-Zyklus.
    sel <= "00";
    out_value <= "0110";
    wait for 1 ns;
    assert disp = "0110"
      report "REQ R55: disp muss OUT kombinatorisch folgen (kein Register im Mux)"
      severity error;
    acc <= "1001";
    sel <= "01";
    wait for 1 ns;
    assert disp = "1001"
      report "REQ R55: disp muss ACC kombinatorisch folgen"
      severity error;
    report "CHECK t=" & time'image(now) & " kombinatorisch disp=" & integer'image(to_integer(unsigned(disp)));

    -- R5: alle vier sel-Werte nochmals mit festen Vektoren
    out_value <= "0001"; acc <= "0010"; pc <= "0011";
    halted <= '1'; mode <= '0'; c <= '1'; z <= '0';
    sel <= "00"; wait for 10 ns;
    assert disp = "0001" report "REQ R5: sw=00 -> OUT" severity error;
    sel <= "01"; wait for 10 ns;
    assert disp = "0010" report "REQ R5: sw=01 -> ACC" severity error;
    sel <= "10"; wait for 10 ns;
    assert disp = "0011" report "REQ R5: sw=10 -> PC" severity error;
    sel <= "11"; wait for 10 ns;
    assert disp = "1010" report "REQ R5: sw=11 -> Status 1010" severity error;
    report "CHECK t=" & time'image(now) & " sw-Mapping ok disp=" & integer'image(to_integer(unsigned(disp)));

    tb_done <= true;
    report "TB_COMPLETE" severity note;
    stop;
    wait;
  end process stim;

end architecture sim;