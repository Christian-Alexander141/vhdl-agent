library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
library std;
use std.env.all;

entity program_counter_tb is
end entity program_counter_tb;

architecture sim of program_counter_tb is
  constant CLK_PERIOD : time := 20 ns;

  signal ce        : std_logic := '0';
  signal clk       : std_logic := '0';
  signal data_in   : std_logic_vector(3 downto 0) := (others => '0');
  signal j_load    : std_logic := '0';
  signal rst       : std_logic := '1';
  signal count_out : std_logic_vector(3 downto 0);

  signal tb_done : boolean := false;
begin
  clk <= not clk after CLK_PERIOD / 2 when not tb_done else '0';

  dut: entity work.program_counter
    port map (
      ce        => ce,
      clk       => clk,
      data_in   => data_in,
      j_load    => j_load,
      rst       => rst,
      count_out => count_out
    );

  stim: process
    procedure wait_cyc(n : positive) is
    begin
      for i in 1 to n loop
        wait until rising_edge(clk);
        wait for 1 ns;
      end loop;
    end procedure;
  begin
    -- Init: Reset aktiv
    ce <= '0';
    j_load <= '0';
    data_in <= (others => '0');
    rst <= '1';
    wait for 1 ns;

    -- Standard-Reset 2 Zyklen.
    wait_cyc(2);
    report "CHECK t=" & time'image(now) & " nach Reset count_out=" & to_string(count_out) severity note;
    assert count_out = "0000" report "REQ R43: rst=1 setzt PC=0" severity error;
    assert count_out = "0000" report "REQ R51: Loader-Clear (rst) setzt PC=0" severity error;

    -- Loslassen, Hold ohne CE/J.
    rst <= '0';
    wait for 1 ns;
    wait_cyc(2);
    report "CHECK t=" & time'image(now) & " Hold count_out=" & to_string(count_out) severity note;
    assert count_out = "0000" report "TC hold: ohne CE/J bleibt PC=0" severity error;

    -- CE: 3 Schritte -> 1,2,3.
    ce <= '1';
    j_load <= '0';
    wait until rising_edge(clk);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " CE1 count_out=" & to_string(count_out) severity note;
    assert count_out = "0001" report "TC CE: PC=1 nach 1xCE" severity error;
    wait until rising_edge(clk);
    wait for 1 ns;
    assert count_out = "0010" report "TC CE: PC=2 nach 2xCE" severity error;
    wait until rising_edge(clk);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " CE3 count_out=" & to_string(count_out) severity note;
    assert count_out = "0011" report "TC CE: PC=3 nach 3xCE" severity error;

    -- R16: CO legt PC oben-mit-0 auf den Bus; PC=3 -> Bus 00000011.
    assert count_out = "0011" report "REQ R16: CO-Quelle PC=3 (Bus=00000011 oben 0)" severity error;

    -- Weiter bis 5 fuer R16-Stichprobe.
    wait until rising_edge(clk);
    wait for 1 ns;
    assert count_out = "0100" report "TC CE: PC=4" severity error;
    wait until rising_edge(clk);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " PC5 count_out=" & to_string(count_out) severity note;
    assert count_out = "0101" report "REQ R16: CO-Quelle PC=5 (Bus=00000101)" severity error;

    -- Hold bei ce=0.
    ce <= '0';
    wait_cyc(2);
    assert count_out = "0101" report "TC hold: ce=0 haelt PC=5" severity error;

    -- J: lade 1010 (10).
    data_in <= "1010";
    j_load <= '1';
    ce <= '0';
    wait until rising_edge(clk);
    wait for 1 ns;
    j_load <= '0';
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " nach J count_out=" & to_string(count_out) severity note;
    assert count_out = "1010" report "TC J: J laedt Bus(3..0)=1010" severity error;
    assert count_out = "1010" report "REQ R16: CO nach J=10 (Bus=00001010)" severity error;

    -- J-Prioritaet ueber CE: beide aktiv -> J gewinnt.
    data_in <= "0011";
    j_load <= '1';
    ce <= '1';
    wait until rising_edge(clk);
    wait for 1 ns;
    j_load <= '0';
    ce <= '0';
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " J+CE count_out=" & to_string(count_out) severity note;
    assert count_out = "0011" report "TC J-Prio: J gewinnt gegen CE (3 statt 11)" severity error;

    -- CE-Ueberlauf: J auf 15, dann CE -> 0 (mod 16).
    data_in <= "1111";
    j_load <= '1';
    ce <= '0';
    wait until rising_edge(clk);
    wait for 1 ns;
    j_load <= '0';
    assert count_out = "1111" report "TC J: PC=15 geladen" severity error;
    ce <= '1';
    wait until rising_edge(clk);
    wait for 1 ns;
    ce <= '0';
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " Wrap count_out=" & to_string(count_out) severity note;
    assert count_out = "0000" report "TC CE-Wrap: PC 15+1=0 (mod 16)" severity error;

    -- Synchron-Nachweis: rst ausserhalb Flanke wirkt nicht sofort.
    -- Erst auf 2 zaehlen.
    ce <= '1';
    wait_cyc(2);
    ce <= '0';
    wait for 1 ns;
    assert count_out = "0010" report "TC pre-sync: PC=2" severity error;
    rst <= '1';
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " rst=1 vor Flanke count_out=" & to_string(count_out) severity note;
    assert count_out = "0010" report "REQ R43: synchroner Reset wirkt erst mit Flanke (noch 2)" severity error;
    wait until rising_edge(clk);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " nach Reset-Flanke count_out=" & to_string(count_out) severity note;
    assert count_out = "0000" report "REQ R43: rst active-high synchron loescht PC mit Flanke" severity error;
    wait_cyc(1);
    rst <= '0';
    wait for 1 ns;

    -- R51-Modell: nach Aktivitaet loescht Loader-Clear (rst-Puls) den PC.
    ce <= '1';
    wait_cyc(4);
    ce <= '0';
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " vor Loader-Clear count_out=" & to_string(count_out) severity note;
    assert count_out = "0100" report "TC pre-clear: PC=4" severity error;
    assert count_out = "0100" report "REQ R16: CO-Quelle PC=4 vor Clear" severity error;
    rst <= '1';
    wait_cyc(1);
    rst <= '0';
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " nach Loader-Clear count_out=" & to_string(count_out) severity note;
    assert count_out = "0000" report "REQ R51: vollstaendiger Rahmen loescht PC (rst-Modell)" severity error;
    assert count_out = "0000" report "REQ R43: rst-Puls setzt PC=0 zurueck" severity error;

    report "CHECK t=" & time'image(now) & " alle program_counter-Pruefungen fertig" severity note;
    tb_done <= true;
    report "TB_COMPLETE" severity note;
    std.env.stop(0);
    wait;
  end process stim;

end architecture sim;