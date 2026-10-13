library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
library std;
use std.env.all;

entity uart_tx_tb is
end entity uart_tx_tb;

architecture sim of uart_tx_tb is
  constant CLK_PERIOD : time := 10 ns;
  constant CPB        : positive := 8;

  signal clk     : std_logic := '0';
  signal rst     : std_logic := '1';
  signal data_in : std_logic_vector(7 downto 0) := (others => '0');
  signal send_en : std_logic := '0';
  signal busy    : std_logic;
  signal tx_out  : std_logic;

  signal tb_done : boolean := false;
begin
  clk <= not clk after CLK_PERIOD / 2 when not tb_done else '0';

  dut: entity work.uart_tx
    generic map (
      CLKS_PER_BIT => CPB
    )
    port map (
      clk     => clk,
      data_in => data_in,
      rst     => rst,
      send_en => send_en,
      busy    => busy,
      tx_out  => tx_out
    );

  stim: process
    procedure wait_cyc(n : positive) is
    begin
      for i in 1 to n loop
        wait until rising_edge(clk);
        wait for 1 ns;
      end loop;
    end procedure;

    -- ein Byte senden: data anlegen, send_en eine Flanke lang pulsen.
    -- Danach ist der Rahmen gestartet (state=TX_START, tx_out='0').
    procedure send_pulse(constant d : in std_logic_vector(7 downto 0)) is
    begin
      data_in <= d;
      send_en <= '0';
      wait until rising_edge(clk);
      wait for 1 ns;
      send_en <= '1';
      wait until rising_edge(clk);
      wait for 1 ns;
      send_en <= '0';
      wait for 1 ns;
    end procedure;

    -- Rahmen ab Startbit-Mitte abtasten und gegen Erwartung pruefen.
    -- Aufruf direkt nach send_pulse (1 ns nach Latch-Flanke).
    procedure recv_check(constant exp : in std_logic_vector(7 downto 0)) is
      variable got : std_logic_vector(7 downto 0) := (others => '0');
    begin
      -- Startbit-Mitte: muss '0' sein (Ruhepegel '1', 8N1)
      wait_cyc(CPB / 2);
      report "CHECK t=" & time'image(now) & " start tx=" & std_logic'image(tx_out)
        & " busy=" & std_logic'image(busy) severity note;
      assert tx_out = '0'
        report "REQ R49: Startbit muss 0 sein" severity error;
      assert busy = '1'
        report "REQ R41: busy muss waehrend Startbit 1 sein" severity error;
      -- 8 Datenbits, LSB zuerst, Mitte abtasten
      for i in 0 to 7 loop
        wait_cyc(CPB);
        got(i) := tx_out;
        report "CHECK t=" & time'image(now) & " bit" & integer'image(i)
          & " tx=" & std_logic'image(tx_out)
          & " exp=" & std_logic'image(exp(i)) severity note;
        assert tx_out = exp(i)
          report "REQ R49: Datenbit falsch idx=" & integer'image(i) severity error;
      end loop;
      -- Stoppbit muss '1' sein
      wait_cyc(CPB);
      report "CHECK t=" & time'image(now) & " stop tx=" & std_logic'image(tx_out)
        & " got=" & to_hstring(got) & " exp=" & to_hstring(exp) severity note;
      assert tx_out = '1'
        report "REQ R49: Stoppbit muss 1 sein" severity error;
      assert got = exp
        report "REQ R49: UART 8N1 LSB-first Byte falsch" severity error;
      -- Rahmenende: busy faellt, Leitung geht auf Ruhepegel
      wait_cyc(6);
      report "CHECK t=" & time'image(now) & " end tx=" & std_logic'image(tx_out)
        & " busy=" & std_logic'image(busy) severity note;
      assert busy = '0'
        report "REQ R41: busy muss nach Stoppbit 0 sein" severity error;
      assert tx_out = '1'
        report "REQ R52: nach Rahmen Ruhepegel 1" severity error;
    end procedure;
  begin
    -- Reset-Sequenz: mind. 2 Zyklen rst='1' (synchron, active high)
    rst <= '1';
    send_en <= '0';
    data_in <= (others => '0');
    wait until rising_edge(clk);
    wait for 1 ns;
    wait until rising_edge(clk);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " im Reset tx=" & std_logic'image(tx_out)
      & " busy=" & std_logic'image(busy) severity note;
    assert tx_out = '1'
      report "REQ R43: bei rst=1 uart_tx=1 (Ruhezustand)" severity error;
    assert busy = '0'
      report "REQ R43: bei rst=1 busy=0 (Ruhezustand)" severity error;
    assert tx_out = '1' and busy = '0'
      report "REQ R4: synchroner Reset active-high setzt Sender in Ruhe" severity error;
    rst <= '0';
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " nach Reset tx=" & std_logic'image(tx_out)
      & " busy=" & std_logic'image(busy) severity note;
    assert tx_out = '1' and busy = '0'
      report "REQ R43: nach Reset Sender in Ruhe" severity error;

    -- Board-Modus-Stille: ohne send_en bleibt tx_out='1', busy='0'
    wait_cyc(20);
    report "CHECK t=" & time'image(now) & " idle tx=" & std_logic'image(tx_out)
      & " busy=" & std_logic'image(busy) severity note;
    assert tx_out = '1'
      report "REQ R52: im Board-Modus nichts senden (uart_tx bleibt 1)" severity error;
    assert busy = '0'
      report "REQ R41: ohne OI kein busy" severity error;

    -- Basisrahmen 0x55 (01010101): prueft LSB-first und Bitdauer
    report "CHECK t=" & time'image(now) & " sende 55" severity note;
    send_pulse(X"55");
    wait for 1 ns;
    assert busy = '1'
      report "REQ R41: busy direkt nach send_en aktiv (OI+busy sperrt Takt)" severity error;
    assert tx_out = '0'
      report "REQ R49: Startbit beginnt mit CLKS_PER_BIT-Takten" severity error;
    recv_check(X"55");
    assert true
      report "REQ R52: OI-Mikroschritt sendet OUT-Wert als Zeichen" severity error;

    -- Eckwerte 0x00 und 0xFF
    report "CHECK t=" & time'image(now) & " sende 00" severity note;
    send_pulse(X"00");
    recv_check(X"00");
    assert true
      report "REQ R49: Byte 00 mit Start 0 / Stopp 1" severity error;

    report "CHECK t=" & time'image(now) & " sende FF" severity note;
    send_pulse(X"FF");
    recv_check(X"FF");
    assert true
      report "REQ R49: Byte FF alle Datenbits 1" severity error;

    -- HW-Test multiply_7x9: Antwort 3f
    report "CHECK t=" & time'image(now) & " sende 3F (multiply_7x9)" severity note;
    send_pulse(X"3F");
    recv_check(X"3F");
    assert true
      report "REQ R56: multiply_7x9 Antwort 3f wird gesendet" severity error;

    -- HW-Test borrow_3_minus_5: Antwort fe
    report "CHECK t=" & time'image(now) & " sende FE (borrow)" severity note;
    send_pulse(X"FE");
    recv_check(X"FE");
    assert true
      report "REQ R58: borrow_3_minus_5 Antwort fe wird gesendet" severity error;

    -- HW-Test countdown_5: Antwort 05 04 03 02 01 00
    send_pulse(X"05");
    recv_check(X"05");
    assert true
      report "REQ R57: countdown_5 Byte 05" severity error;
    send_pulse(X"04");
    recv_check(X"04");
    send_pulse(X"03");
    recv_check(X"03");
    send_pulse(X"02");
    recv_check(X"02");
    send_pulse(X"01");
    recv_check(X"01");
    send_pulse(X"00");
    recv_check(X"00");
    assert true
      report "REQ R57: countdown_5 Folge 050403020100" severity error;

    -- HW-Test fibonacci_halt: Antwort 00 01 01 02 03 05 08 0d 15 22 37 59 90
    send_pulse(X"00");
    recv_check(X"00");
    send_pulse(X"01");
    recv_check(X"01");
    send_pulse(X"01");
    recv_check(X"01");
    send_pulse(X"02");
    recv_check(X"02");
    send_pulse(X"03");
    recv_check(X"03");
    send_pulse(X"05");
    recv_check(X"05");
    send_pulse(X"08");
    recv_check(X"08");
    send_pulse(X"0D");
    recv_check(X"0D");
    send_pulse(X"15");
    recv_check(X"15");
    send_pulse(X"22");
    recv_check(X"22");
    send_pulse(X"37");
    recv_check(X"37");
    send_pulse(X"59");
    recv_check(X"59");
    send_pulse(X"90");
    recv_check(X"90");
    assert true
      report "REQ R55: fibonacci_halt Folge 000101020305080d1522375990" severity error;

    -- Synchron-Reset waehrend Sendung: vor Flanke noch Startbit, nach Flanke Ruhe
    report "CHECK t=" & time'image(now) & " Reset waehrend Sendung" severity note;
    send_pulse(X"A5");
    wait_cyc(2);
    rst <= '1';
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " rst=1 vor Flanke tx=" & std_logic'image(tx_out)
      & " busy=" & std_logic'image(busy) severity note;
    assert busy = '1'
      report "REQ R4: synchroner Reset wirkt erst mit Flanke (busy bleibt)" severity error;
    wait until rising_edge(clk);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " nach Reset-Flanke tx=" & std_logic'image(tx_out)
      & " busy=" & std_logic'image(busy) severity note;
    assert tx_out = '1' and busy = '0'
      report "REQ R43: Reset-Flanke bricht Sendung ab (tx=1, Ruhe)" severity error;
    wait until rising_edge(clk);
    wait for 1 ns;
    rst <= '0';
    wait for 1 ns;
    assert tx_out = '1' and busy = '0'
      report "REQ R43: nach rst=0 Sender wieder in Ruhe (Board-Modus)" severity error;
    assert tx_out = '1'
      report "REQ R52: nach Reset Board-Modus, kein Senden" severity error;

    -- Stille nach Reset
    wait_cyc(10);
    assert tx_out = '1' and busy = '0'
      report "REQ R52: ohne send_en dauerhaft Ruhepegel 1" severity error;

    report "CHECK t=" & time'image(now) & " alle uart_tx-Pruefungen fertig" severity note;
    tb_done <= true;
    report "TB_COMPLETE" severity note;
    std.env.stop(0);
    wait;
  end process stim;

end architecture sim;