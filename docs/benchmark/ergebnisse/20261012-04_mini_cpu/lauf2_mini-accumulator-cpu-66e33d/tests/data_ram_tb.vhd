library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.env.all;

entity data_ram_tb is
end entity data_ram_tb;

architecture sim of data_ram_tb is
  constant ADDR_WIDTH : positive := 4;
  constant DATA_WIDTH : positive := 4;
  constant CLK_PERIOD : time := 10 ns;

  signal clk     : std_logic := '0';
  signal rst     : std_logic := '1';
  signal we      : std_logic := '0';
  signal addr    : std_logic_vector(ADDR_WIDTH-1 downto 0) := (others => '0');
  signal din     : std_logic_vector(DATA_WIDTH-1 downto 0) := (others => '0');
  signal dout    : std_logic_vector(DATA_WIDTH-1 downto 0);
  signal tb_done : boolean := false;

begin

  clk <= not clk after CLK_PERIOD / 2 when not tb_done else '0';

  dut: entity work.data_ram
    generic map (
      ADDR_WIDTH => ADDR_WIDTH,
      DATA_WIDTH => DATA_WIDTH
    )
    port map (
      clk  => clk,
      rst  => rst,
      we   => we,
      addr => addr,
      din  => din,
      dout => dout
    );

  stim: process
    procedure wait_cycles(n : positive) is
    begin
      for i in 1 to n loop
        wait until rising_edge(clk);
      end loop;
      wait for 1 ns; -- Ausgaenge setzen lassen (Delta-Race vermeiden)
    end procedure;
  begin
    -- Reset sequence: mind. 2 Zyklen rst='1' (synchroner Reset, PROMPT.md).
    rst  <= '1';
    we   <= '0';
    addr <= (others => '0');
    din  <= (others => '0');
    wait_cycles(2);

    -- R57: Nach Reset sind alle 16 Zellen 0 (kombinatorisch ausgelesen).
    for i in 0 to 15 loop
      addr <= std_logic_vector(to_unsigned(i, ADDR_WIDTH));
      wait for 1 ns;
      report "CHECK t=" & time'image(now) & " reset addr=" & to_hstring(addr) & " dout=" & to_hstring(dout);
      assert dout = "0000"
        report "REQ R57: nach Reset muss RAM[" & integer'image(i) & "] = 0 sein, ist " & to_hstring(dout)
        severity error;
    end loop;
    report "CHECK t=" & time'image(now) & " alle 16 Zellen nach Reset 0";

    -- Reset release.
    rst <= '0';
    wait_cycles(2);
    addr <= x"0";
    wait for 1 ns;
    assert dout = "0000"
      report "REQ R57: nach Reset-Release RAM[0] weiter 0, ist " & to_hstring(dout)
      severity error;
    report "CHECK t=" & time'image(now) & " nach Release dout=" & to_hstring(dout);

    -- R64: Kombinatorisches Lesen (ohne Taktflanke, nur addr-Wechsel).
    -- Zuerst zwei verschiedene Werte synchron schreiben.
    we <= '1'; addr <= x"0"; din <= x"1";
    wait_cycles(1);
    we <= '1'; addr <= x"1"; din <= x"2";
    wait_cycles(1);
    we <= '0';
    addr <= x"0";
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " komb addr=0 dout=" & to_hstring(dout);
    assert dout = x"1"
      report "REQ R64: kombinatorisches Lesen addr=0 muss 1 sein, ist " & to_hstring(dout)
      severity error;
    addr <= x"1";
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " komb addr=1 dout=" & to_hstring(dout);
    -- Hinweis: an addr 1 wurde x"2" geschrieben (STA-Pfad).
    assert dout = x"2"
      report "REQ R15: STA-Pfad RAM[1]:=ACC(2) muss 2 lesen, ist " & to_hstring(dout)
      severity error;

    -- R15: STA a (RAM[a] := ACC) -- Fibonacci-Kontext STA 0 / STA 1.
    -- RAM[0]=1, RAM[1]=1 sind die letzten beiden Fibonacci-Zahlen (PROMPT.md).
    addr <= x"0";
    wait for 1 ns;
    assert dout = x"1"
      report "REQ R15: STA 0 muss RAM[0]=1 liefern (Fibonacci), ist " & to_hstring(dout)
      severity error;
    report "CHECK t=" & time'image(now) & " STA-Kontext RAM0=" & to_hstring(dout);

    -- R14: LDA a (ACC := RAM[a]) lesbar -- Datenspeicher liefert Operanden.
    we <= '1'; addr <= x"5"; din <= x"D";
    wait_cycles(1);
    we <= '0';
    addr <= x"5";
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " LDA-Kontext addr=5 dout=" & to_hstring(dout);
    assert dout = x"D"
      report "REQ R14: LDA-Pfad RAM[5] muss D liefern, ist " & to_hstring(dout)
      severity error;

    -- R64: Synchrones Schreiben -- ohne we kein Schreiben.
    we <= '0'; addr <= x"5"; din <= x"0";
    wait_cycles(2);
    addr <= x"5";
    wait for 1 ns;
    assert dout = x"D"
      report "REQ R64: ohne we darf RAM[5] nicht ueberschrieben werden, ist " & to_hstring(dout)
      severity error;
    report "CHECK t=" & time'image(now) & " we=0 haelt dout=" & to_hstring(dout);

    -- R64: Synchronitaet -- we/din duerfen erst mit Flanke wirken.
    -- Lege we=1/din an kurz nach einer Flanke an, pruefe vor naechster Flanke alten Wert.
    we <= '0'; addr <= x"6"; din <= x"0";
    wait_cycles(1);
    addr <= x"6";
    wait for 1 ns;
    assert dout = x"0"
      report "REQ R64: RAM[6] vor Schreiben 0, ist " & to_hstring(dout)
      severity error;
    we <= '1'; din <= x"9";
    wait for 1 ns; -- noch keine Flanke: kombinatorisch darf sich nichts aendern
    report "CHECK t=" & time'image(now) & " vor Flanke addr=6 dout=" & to_hstring(dout);
    assert dout = x"0"
      report "REQ R64: Schreiben erst mit Taktflanke (vor Flanke weiter 0), ist " & to_hstring(dout)
      severity error;
    wait_cycles(1); -- diese Flanke uebernimmt
    we <= '0';
    addr <= x"6";
    wait for 1 ns;
    assert dout = x"9"
      report "REQ R64: nach Flanke RAM[6]=9, ist " & to_hstring(dout)
      severity error;
    report "CHECK t=" & time'image(now) & " nach Flanke dout=" & to_hstring(dout);

    -- Alle 16 Zellen mit Muster i beschreiben und zuruecklesen.
    for i in 0 to 15 loop
      we   <= '1';
      addr <= std_logic_vector(to_unsigned(i, ADDR_WIDTH));
      din  <= std_logic_vector(to_unsigned((i * 3 + 1) mod 16, DATA_WIDTH));
      wait_cycles(1);
    end loop;
    we <= '0';
    for i in 0 to 15 loop
      addr <= std_logic_vector(to_unsigned(i, ADDR_WIDTH));
      wait for 1 ns;
      report "CHECK t=" & time'image(now) & " muster addr=" & to_hstring(addr) & " dout=" & to_hstring(dout);
      assert dout = std_logic_vector(to_unsigned((i * 3 + 1) mod 16, DATA_WIDTH))
        report "REQ R64: RAM[" & integer'image(i) & "] Muster falsch, ist " & to_hstring(dout)
        severity error;
    end loop;
    report "CHECK t=" & time'image(now) & " 16 Zellen Muster ok";

    -- R57: Synchroner Reset wirkt erst mit Flanke (nicht asynchron).
    -- RAM[7] ist aktuell Muster (7*3+1) mod 16 = 6.
    addr <= x"7";
    wait for 1 ns;
    assert dout = x"6"
      report "REQ R57: Vorbedingung RAM[7]=6, ist " & to_hstring(dout)
      severity error;
    rst <= '1';
    wait for 1 ns; -- noch keine Flanke
    report "CHECK t=" & time'image(now) & " rst=1 vor Flanke dout=" & to_hstring(dout);
    assert dout = x"6"
      report "REQ R57: synchroner Reset darf vor Flanke nichts loeschen, ist " & to_hstring(dout)
      severity error;
    wait_cycles(1); -- Reset-Flanke
    for i in 0 to 15 loop
      addr <= std_logic_vector(to_unsigned(i, ADDR_WIDTH));
      wait for 1 ns;
      assert dout = "0000"
        report "REQ R57: Mid-Reset muss RAM[" & integer'image(i) & "] loeschen, ist " & to_hstring(dout)
        severity error;
    end loop;
    report "CHECK t=" & time'image(now) & " Mid-Reset alle Zellen 0";
    assert dout = "0000"
      report "REQ R57: nach Mid-Reset alle RAM-Zellen 0"
      severity error;

    -- Nach Reset-Release wieder beschreibbar (Programm beginnt von vorn).
    rst <= '0';
    wait_cycles(1);
    we <= '1'; addr <= x"0"; din <= x"1";
    wait_cycles(1);
    we <= '1'; addr <= x"1"; din <= x"1";
    wait_cycles(1);
    we <= '0';
    addr <= x"0"; wait for 1 ns;
    assert dout = x"1"
      report "REQ R15: nach Reset STA 0 erneut 1, ist " & to_hstring(dout)
      severity error;
    addr <= x"1"; wait for 1 ns;
    assert dout = x"1"
      report "REQ R14: nach Reset LDA 1 erneut 1, ist " & to_hstring(dout)
      severity error;
    report "CHECK t=" & time'image(now) & " nach Reset Fib-Start RAM0=1 RAM1=1";

    tb_done <= true;
    report "TB_COMPLETE" severity note;
    stop;
    wait;
  end process stim;

end architecture sim;