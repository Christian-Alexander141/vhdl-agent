library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
library std;
use std.env.all;

entity register8_tb is
end entity register8_tb;

architecture sim of register8_tb is
  constant CLK_PERIOD : time := 20 ns;

  signal clk      : std_logic := '0';
  signal data_in  : std_logic_vector(7 downto 0) := (others => '0');
  signal data_out : std_logic_vector(7 downto 0);
  signal load_en  : std_logic := '0';
  signal rst      : std_logic := '1';

  signal tb_done : boolean := false;
begin
  clk <= not clk after CLK_PERIOD / 2 when not tb_done else '0';

  dut: entity work.register8
    port map (
      clk      => clk,
      data_in  => data_in,
      data_out => data_out,
      load_en  => load_en,
      rst      => rst
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
    -- Init: Reset aktiv, keine Ladung.
    load_en <= '0';
    data_in <= (others => '0');
    rst <= '1';
    wait for 1 ns;

    -- Standard-Reset 2 Zyklen.
    wait_cyc(2);
    report "CHECK t=" & time'image(now) & " nach Reset data_out=" & to_hstring(data_out) severity note;
    assert data_out = x"00" report "REQ R43: rst=1 setzt Register=0x00" severity error;
    assert data_out = x"00" report "REQ R51: Loader-Clear (rst) setzt Register=0x00" severity error;

    -- Loslassen, Hold ohne load_en.
    rst <= '0';
    wait for 1 ns;
    data_in <= x"A5";
    wait_cyc(2);
    report "CHECK t=" & time'image(now) & " Hold data_out=" & to_hstring(data_out) severity note;
    assert data_out = x"00" report "TC hold: load_en=0 haelt 0x00 trotz data_in=A5" severity error;
    assert data_out = x"00" report "REQ R16: Busquelle (AO) bleibt 0x00 ohne Ladesignal" severity error;

    -- Laden: A5 mit load_en=1.
    load_en <= '1';
    data_in <= x"A5";
    wait until rising_edge(clk);
    wait for 1 ns;
    load_en <= '0';
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " nach Load A5 data_out=" & to_hstring(data_out) severity note;
    assert data_out = x"A5" report "TC load: load_en=1 laedt 0xA5" severity error;
    assert data_out = x"A5" report "REQ R35: Register uebernimmt mit Schrittfreigabe-Flanke (A5)" severity error;
    assert data_out = x"A5" report "REQ R16: Busquelle (AO) treibt geladenes 0xA5" severity error;

    -- Hold: data_in wechselt, load_en=0 -> Wert bleibt.
    data_in <= x"5A";
    wait_cyc(2);
    report "CHECK t=" & time'image(now) & " Hold nach A5 data_out=" & to_hstring(data_out) severity note;
    assert data_out = x"A5" report "TC hold: load_en=0 haelt 0xA5 trotz data_in=5A" severity error;

    -- Laden: FF.
    load_en <= '1';
    data_in <= x"FF";
    wait until rising_edge(clk);
    wait for 1 ns;
    load_en <= '0';
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " nach Load FF data_out=" & to_hstring(data_out) severity note;
    assert data_out = x"FF" report "TC load: load_en=1 laedt 0xFF" severity error;

    -- Laden: 00 (Loeschen per Daten, kein Reset).
    load_en <= '1';
    data_in <= x"00";
    wait until rising_edge(clk);
    wait for 1 ns;
    load_en <= '0';
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " nach Load 00 data_out=" & to_hstring(data_out) severity note;
    assert data_out = x"00" report "TC load: load_en=1 laedt 0x00" severity error;

    -- R35-Nachweis: data_in-Wechsel kurz nach Flanke wirkt erst naechste Flanke.
    load_en <= '1';
    data_in <= x"3C";
    wait until rising_edge(clk);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " R35 Schritt1 data_out=" & to_hstring(data_out) severity note;
    assert data_out = x"3C" report "REQ R35: Uebernahme nutzt Vor-Flanken-Werte (3C)" severity error;
    data_in <= x"C3";
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " R35 Hold data_out=" & to_hstring(data_out) severity note;
    assert data_out = x"3C" report "REQ R35: Aenderung nach Flanke wirkt nicht sofort (noch 3C)" severity error;
    wait until rising_edge(clk);
    wait for 1 ns;
    load_en <= '0';
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " R35 Schritt2 data_out=" & to_hstring(data_out) severity note;
    assert data_out = x"C3" report "REQ R35: naechste Flanke uebernimmt C3" severity error;

    -- Synchron-Nachweis: rst ausserhalb Flanke wirkt nicht sofort.
    rst <= '1';
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " rst=1 vor Flanke data_out=" & to_hstring(data_out) severity note;
    assert data_out = x"C3" report "REQ R43: synchroner Reset wirkt erst mit Flanke (noch C3)" severity error;
    wait until rising_edge(clk);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " nach Reset-Flanke data_out=" & to_hstring(data_out) severity note;
    assert data_out = x"00" report "REQ R43: rst active-high synchron loescht Register mit Flanke" severity error;
    wait_cyc(1);
    rst <= '0';
    wait for 1 ns;

    -- Reset-Prioritaet ueber load_en.
    load_en <= '1';
    data_in <= x"7E";
    wait until rising_edge(clk);
    wait for 1 ns;
    load_en <= '0';
    wait for 1 ns;
    assert data_out = x"7E" report "TC pre-prio: 0x7E geladen" severity error;
    report "CHECK t=" & time'image(now) & " vor Prio data_out=" & to_hstring(data_out) severity note;
    rst <= '1';
    load_en <= '1';
    data_in <= x"BD";
    wait until rising_edge(clk);
    wait for 1 ns;
    rst <= '0';
    load_en <= '0';
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " nach Prio data_out=" & to_hstring(data_out) severity note;
    assert data_out = x"00" report "REQ R43: Reset hat Vorrang vor load_en (0x00 statt BD)" severity error;

    -- R51-Modell: nach Aktivitaet loescht Loader-Clear (rst-Puls) das Register.
    load_en <= '1';
    data_in <= x"42";
    wait until rising_edge(clk);
    wait for 1 ns;
    load_en <= '0';
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " vor Loader-Clear data_out=" & to_hstring(data_out) severity note;
    assert data_out = x"42" report "TC pre-clear: 0x42 geladen" severity error;
    assert data_out = x"42" report "REQ R16: Busquelle (AO) 0x42 vor Clear" severity error;
    rst <= '1';
    wait_cyc(1);
    rst <= '0';
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " nach Loader-Clear data_out=" & to_hstring(data_out) severity note;
    assert data_out = x"00" report "REQ R51: vollstaendiger Rahmen loescht Register (rst-Modell)" severity error;
    assert data_out = x"00" report "REQ R43: rst-Puls setzt Register=0x00 zurueck" severity error;

    report "CHECK t=" & time'image(now) & " alle register8-Pruefungen fertig" severity note;
    tb_done <= true;
    report "TB_COMPLETE" severity note;
    std.env.stop(0);
    wait;
  end process stim;

end architecture sim;