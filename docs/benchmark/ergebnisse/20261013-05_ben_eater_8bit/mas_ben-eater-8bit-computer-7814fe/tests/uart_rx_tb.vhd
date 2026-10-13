library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
library std;
use std.env.all;

entity uart_rx_tb is
end entity uart_rx_tb;

architecture sim of uart_rx_tb is
  constant CLK_PERIOD : time := 10 ns;
  constant CPB        : positive := 8;
  constant BIT_TIME   : time := CPB * CLK_PERIOD;

  signal clk        : std_logic := '0';
  signal rst        : std_logic := '1';
  signal rx_in      : std_logic := '1';
  signal data_out   : std_logic_vector(7 downto 0);
  signal data_valid : std_logic;

  signal got_data  : std_logic_vector(7 downto 0) := (others => '0');
  signal got_count : natural := 0;

  signal tb_done : boolean := false;
begin
  clk <= not clk after CLK_PERIOD / 2 when not tb_done else '0';

  dut: entity work.uart_rx
    generic map (
      CLKS_PER_BIT => CPB
    )
    port map (
      clk        => clk,
      rst        => rst,
      rx_in      => rx_in,
      data_out   => data_out,
      data_valid => data_valid
    );

  -- Empfangsmonitor: zeichnet jedes data_valid auf, prueft Ein-Takt-Puls.
  mon: process(clk)
    variable prev_valid : std_logic := '0';
  begin
    if rising_edge(clk) then
      if rst = '1' then
        prev_valid := '0';
      else
        assert not (data_valid = '1' and prev_valid = '1')
          report "REQ R49: data_valid muss genau einen Takt lang 1 sein" severity error;
        if data_valid = '1' then
          got_data  <= data_out;
          got_count <= got_count + 1;
        end if;
        prev_valid := data_valid;
      end if;
    end if;
  end process mon;

  stim: process
    procedure wait_cyc(n : positive) is
    begin
      for i in 1 to n loop
        wait until rising_edge(clk);
        wait for 1 ns;
      end loop;
    end procedure;

    -- Ein gueltiges 8N1-Zeichen senden, LSB zuerst, Bitdauer = CPB Takte.
    -- Aufruf im Idle (rx_in='1'); endet im Idle.
    procedure send_byte(constant d : in std_logic_vector(7 downto 0)) is
    begin
      wait until falling_edge(clk);
      rx_in <= '0';
      wait for BIT_TIME;
      for i in 0 to 7 loop
        rx_in <= d(i);
        wait for BIT_TIME;
      end loop;
      rx_in <= '1';
      wait for BIT_TIME;
      wait for 1 ns;
    end procedure;

    -- Rahmen mit defektem Stoppbit (Stopp = '0') senden.
    procedure send_bad_stop(constant d : in std_logic_vector(7 downto 0)) is
    begin
      wait until falling_edge(clk);
      rx_in <= '0';
      wait for BIT_TIME;
      for i in 0 to 7 loop
        rx_in <= d(i);
        wait for BIT_TIME;
      end loop;
      rx_in <= '0'; -- defektes Stoppbit
      wait for BIT_TIME;
      rx_in <= '1';
      wait for BIT_TIME;
      wait for 1 ns;
    end procedure;

    variable base : natural;
  begin
    -- Reset-Sequenz: mind. 2 Zyklen rst='1' (synchron, active high)
    rx_in <= '1';
    rst   <= '1';
    wait until rising_edge(clk);
    wait for 1 ns;
    wait until rising_edge(clk);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " im Reset dout=" & to_hstring(data_out)
      & " valid=" & std_logic'image(data_valid) severity note;
    assert data_out = X"00"
      report "REQ R43: bei rst=1 Empfaenger-Ausgabe 0 (Ruhezustand)" severity error;
    assert data_valid = '0'
      report "REQ R43: bei rst=1 data_valid=0 (Ruhezustand)" severity error;
    assert data_out = X"00" and data_valid = '0'
      report "REQ R4: synchroner Reset active-high setzt Empfaenger in Ruhe" severity error;
    rst <= '0';
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " nach Reset dout=" & to_hstring(data_out)
      & " valid=" & std_logic'image(data_valid) severity note;
    assert data_valid = '0'
      report "REQ R43: nach Reset data_valid=0" severity error;

    -- Ruhepegel: ohne Startflanke kein Zeichen
    wait_cyc(3 * CPB);
    report "CHECK t=" & time'image(now) & " idle count=" & integer'image(got_count) severity note;
    assert got_count = 0
      report "REQ R49: Ruhepegel 1 erzeugt kein Zeichen (Start an fallender Flanke)" severity error;
    assert rx_in = '1' and data_valid = '0'
      report "REQ R49: UART idle 1, kein data_valid ohne Rahmen" severity error;

    -- Basiszeichen 0x55 (01010101)
    report "CHECK t=" & time'image(now) & " sende 55" severity note;
    base := got_count;
    send_byte(X"55");
    wait_cyc(5);
    report "CHECK t=" & time'image(now) & " nach 55 got=" & to_hstring(got_data)
      & " count=" & integer'image(got_count) severity note;
    assert got_count = base + 1
      report "REQ R49: Zeichen 55 muss genau ein data_valid erzeugen (8N1, Bitmitte)" severity error;
    assert got_data = X"55"
      report "REQ R49: UART 8N1 LSB-first Byte 55 falsch" severity error;

    -- Eckwerte 0x00 und 0xFF
    report "CHECK t=" & time'image(now) & " sende 00" severity note;
    base := got_count;
    send_byte(X"00");
    wait_cyc(5);
    report "CHECK t=" & time'image(now) & " nach 00 got=" & to_hstring(got_data) severity note;
    assert got_count = base + 1
      report "REQ R49: Zeichen 00 muss genau ein data_valid erzeugen" severity error;
    assert got_data = X"00"
      report "REQ R49: Byte 00 falsch (Start 0 / Stopp 1, alle Bits 0)" severity error;

    report "CHECK t=" & time'image(now) & " sende FF" severity note;
    base := got_count;
    send_byte(X"FF");
    wait_cyc(5);
    report "CHECK t=" & time'image(now) & " nach FF got=" & to_hstring(got_data) severity note;
    assert got_count = base + 1
      report "REQ R49: Zeichen FF muss genau ein data_valid erzeugen" severity error;
    assert got_data = X"FF"
      report "REQ R49: Byte FF falsch (alle Datenbits 1)" severity error;

    -- LSB-first-Nachweis: 0x01 darf nicht als 0x80 ankommen und umgekehrt.
    report "CHECK t=" & time'image(now) & " sende 01 (LSB-first)" severity note;
    base := got_count;
    send_byte(X"01");
    wait_cyc(5);
    report "CHECK t=" & time'image(now) & " nach 01 got=" & to_hstring(got_data) severity note;
    assert got_count = base + 1
      report "REQ R49: Zeichen 01 muss genau ein data_valid erzeugen" severity error;
    assert got_data = X"01"
      report "REQ R49: LSB-first falsch: 01 kam nicht als 01 an (MSB-first waere 80)" severity error;

    report "CHECK t=" & time'image(now) & " sende 80 (LSB-first)" severity note;
    base := got_count;
    send_byte(X"80");
    wait_cyc(5);
    report "CHECK t=" & time'image(now) & " nach 80 got=" & to_hstring(got_data) severity note;
    assert got_count = base + 1
      report "REQ R49: Zeichen 80 muss genau ein data_valid erzeugen" severity error;
    assert got_data = X"80"
      report "REQ R49: LSB-first falsch: 80 kam nicht als 80 an" severity error;

    -- Unsymmetrisches Byte 0xC9 (11001001): verdreht waere 0x93.
    report "CHECK t=" & time'image(now) & " sende C9" severity note;
    base := got_count;
    send_byte(X"C9");
    wait_cyc(5);
    report "CHECK t=" & time'image(now) & " nach C9 got=" & to_hstring(got_data) severity note;
    assert got_count = base + 1
      report "REQ R49: Zeichen C9 muss genau ein data_valid erzeugen" severity error;
    assert got_data = X"C9"
      report "REQ R49: LSB-first falsch: C9 kam nicht als C9 an (Bitreihenfolge)" severity error;

    -- Kurzer Stoerimpuls (Low nur 2 Takte): Startbit-Mitte ist 1 -> verwerfen.
    report "CHECK t=" & time'image(now) & " Stoerimpuls (falsches Startbit)" severity note;
    base := got_count;
    wait until falling_edge(clk);
    rx_in <= '0';
    wait for 2 * CLK_PERIOD;
    rx_in <= '1';
    wait for 2 * BIT_TIME;
    wait_cyc(3);
    report "CHECK t=" & time'image(now) & " nach Glitch count=" & integer'image(got_count)
      & " basis=" & integer'image(base) severity note;
    assert got_count = base
      report "REQ R49: Zeichen mit Startbit-Mitte /= 0 muss verworfen werden" severity error;

    -- Defektes Stoppbit (Stopp = 0): verwerfen, data_out haelt letztes Zeichen.
    report "CHECK t=" & time'image(now) & " sende A5 mit Stopp=0" severity note;
    base := got_count;
    send_bad_stop(X"A5");
    wait_cyc(5);
    report "CHECK t=" & time'image(now) & " nach bad-stop count=" & integer'image(got_count)
      & " got=" & to_hstring(got_data) severity note;
    assert got_count = base
      report "REQ R49: Zeichen mit Stoppbit /= 1 muss verworfen werden" severity error;
    assert got_data = X"C9"
      report "REQ R49: nach verworfenem Zeichen muss data_out letztes gueltiges Zeichen halten" severity error;

    -- Direkt danach gueltiges Zeichen: Empfaenger ist wieder synchron.
    report "CHECK t=" & time'image(now) & " sende A5 gueltig nach bad-stop" severity note;
    base := got_count;
    send_byte(X"A5");
    wait_cyc(5);
    report "CHECK t=" & time'image(now) & " nach A5 got=" & to_hstring(got_data) severity note;
    assert got_count = base + 1
      report "REQ R49: nach verworfenem Zeichen muss naechstes gueltiges Zeichen ankommen" severity error;
    assert got_data = X"A5"
      report "REQ R49: Byte A5 nach Resync falsch" severity error;

    -- Back-to-back: zwei Zeichen mit nur einer Bitzeit Pause.
    report "CHECK t=" & time'image(now) & " back-to-back 3F FE" severity note;
    base := got_count;
    send_byte(X"3F");
    send_byte(X"FE");
    wait_cyc(5);
    report "CHECK t=" & time'image(now) & " nach burst count=" & integer'image(got_count)
      & " got=" & to_hstring(got_data) severity note;
    assert got_count = base + 2
      report "REQ R49: zwei aufeinanderfolgende Zeichen muessen beide ankommen" severity error;
    assert got_data = X"FE"
      report "REQ R49: zweites Burst-Zeichen FE falsch" severity error;

    -- Synchron-Reset waehrend Empfang: wirkt erst mit Flanke, loescht dann.
    report "CHECK t=" & time'image(now) & " Reset waehrend Empfang" severity note;
    wait until falling_edge(clk);
    rx_in <= '0'; -- Startbit eines 0x96-Rahmens beginnen
    wait for BIT_TIME;
    rx_in <= '1';
    wait for BIT_TIME; -- Bit 0
    rst <= '1';
    rx_in <= '1';
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " rst=1 vor Flanke valid=" & std_logic'image(data_valid) severity note;
    assert data_valid = '0'
      report "REQ R4: synchroner Reset wirkt erst mit Flanke (vorher kein valid)" severity error;
    wait until rising_edge(clk);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " nach Reset-Flanke dout=" & to_hstring(data_out)
      & " valid=" & std_logic'image(data_valid) severity note;
    assert data_out = X"00" and data_valid = '0'
      report "REQ R43: Reset-Flanke loescht Empfaenger (dout=0, valid=0)" severity error;
    wait until rising_edge(clk);
    wait for 1 ns;
    rst <= '0';
    wait for 1 ns;
    base := got_count;
    wait for 2 * BIT_TIME;
    wait_cyc(3);
    report "CHECK t=" & time'image(now) & " nach Abbruch count=" & integer'image(got_count)
      & " basis=" & integer'image(base) severity note;
    assert got_count = base
      report "REQ R43: abgebrochener Rahmen nach Reset erzeugt kein Zeichen" severity error;

    -- Nach Reset wieder empfangsbereit.
    report "CHECK t=" & time'image(now) & " sende 96 nach Reset" severity note;
    base := got_count;
    send_byte(X"96");
    wait_cyc(5);
    report "CHECK t=" & time'image(now) & " nach 96 got=" & to_hstring(got_data) severity note;
    assert got_count = base + 1
      report "REQ R49: nach Reset muss Empfang wieder funktionieren" severity error;
    assert got_data = X"96"
      report "REQ R49: Byte 96 nach Reset falsch" severity error;

    report "CHECK t=" & time'image(now) & " alle uart_rx-Pruefungen fertig" severity note;
    tb_done <= true;
    report "TB_COMPLETE" severity note;
    std.env.stop(0);
    wait;
  end process stim;

end architecture sim;