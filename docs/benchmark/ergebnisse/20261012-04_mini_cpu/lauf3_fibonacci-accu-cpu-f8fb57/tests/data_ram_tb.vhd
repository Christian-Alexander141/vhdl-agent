library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity data_ram_tb is
end entity data_ram_tb;

architecture sim of data_ram_tb is
  constant ADDR_WIDTH : positive := 4;
  constant DATA_WIDTH : positive := 4;

  constant CLK_PERIOD : time := 10 ns;

  signal clk   : std_logic := '0';
  signal rst   : std_logic := '1';
  signal addr  : std_logic_vector(ADDR_WIDTH-1 downto 0) := (others => '0');
  signal wdata : std_logic_vector(DATA_WIDTH-1 downto 0) := (others => '0');
  signal rdata : std_logic_vector(DATA_WIDTH-1 downto 0);
  signal we    : std_logic := '0';

  signal tb_done : boolean := false;

begin

  clk <= not clk after CLK_PERIOD / 2 when not tb_done else '0';

  dut: entity work.data_ram
    generic map (
      ADDR_WIDTH => ADDR_WIDTH,
      DATA_WIDTH => DATA_WIDTH
    )
    port map (
      addr  => addr,
      clk   => clk,
      rst   => rst,
      rdata => rdata,
      wdata => wdata,
      we    => we
    );

  stim: process
    procedure wait_cycles(n : positive) is
    begin
      for i in 1 to n loop
        wait until rising_edge(clk);
      end loop;
    end procedure;
  begin
    -- Reset-Sequenz: mind. 2 Zyklen rst='1' (synchroner Reset, active high)
    rst <= '1';
    we <= '0';
    addr <= (others => '0');
    wdata <= (others => '0');
    wait_cycles(2);
    rst <= '0';
    wait_cycles(1);

    -- TC1: Nach Reset sind alle 16 Zellen 0 (kombinatorisches Lesen)
    report "CHECK t=" & time'image(now) & " nach Reset, addr=0 rdata=" & to_string(rdata) severity note;
    for i in 0 to 15 loop
      addr <= std_logic_vector(to_unsigned(i, ADDR_WIDTH));
      wait for 10 ns;
      assert rdata = "0000" report "REQ R71: RAM Zelle " & integer'image(i) & " muss nach Reset 0 sein" severity error;
    end loop;
    report "CHECK t=" & time'image(now) & " alle 16 Zellen nach Reset 0" severity note;
    assert rdata = "0000" report "REQ R16: Datenspeicher hat 16 Zellen zu 4 Bit, Zelle 15 nach Reset 0" severity error;
    assert rdata = "0000" report "REQ R78: sync Reset loescht alle Zellen (Zelle 15 = 0)" severity error;

    -- TC2: Synchrones Schreiben (STA-Pfad) und kombinatorisches Lesen (LDA-Pfad)
    -- Schreibe 0001 nach Adresse 0
    addr <= "0000"; wdata <= "0001"; we <= '1';
    wait until rising_edge(clk);
    we <= '0';
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " nach STA 0<=1 rdata=" & to_string(rdata) severity note;
    assert rdata = "0001" report "REQ R21: STA a: RAM[0] muss nach Schreiben 1 sein" severity error;
    assert rdata = "0001" report "REQ R20: LDA a: RAM[0] muss kombinatorisch 1 liefern" severity error;

    -- Schreibe 0010 nach Adresse 1
    addr <= "0001"; wdata <= "0010"; we <= '1';
    wait until rising_edge(clk);
    we <= '0';
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " nach STA 1<=2 rdata=" & to_string(rdata) severity note;
    assert rdata = "0010" report "REQ R21: STA a: RAM[1] muss nach Schreiben 2 sein" severity error;

    -- Ruecklesen Adresse 0 ohne Takt (kombinatorisch)
    addr <= "0000";
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " Ruecklesen addr=0 rdata=" & to_string(rdata) severity note;
    assert rdata = "0001" report "REQ R78: kombinatorisches Lesen: RAM[0] bleibt 1 ohne Takt" severity error;

    -- TC3: we='0' schreibt nicht
    addr <= "0000"; wdata <= "1111"; we <= '0';
    wait_cycles(2);
    report "CHECK t=" & time'image(now) & " we=0 gehalten rdata=" & to_string(rdata) severity note;
    assert rdata = "0001" report "REQ R21: ohne we darf RAM[0] nicht ueberschrieben werden (bleibt 1)" severity error;

    -- TC4: Fibonacci-Werte in RAM[0]/RAM[1] (letzte beiden Fibonacci-Zahlen)
    -- Schreibe 1 nach 0 und 1 nach 1 wie Programmstart (LDI 1, STA 0, STA 1)
    addr <= "0000"; wdata <= "0001"; we <= '1';
    wait until rising_edge(clk);
    addr <= "0001"; wdata <= "0001";
    wait until rising_edge(clk);
    we <= '0';
    wait for 1 ns;
    addr <= "0000";
    wait for 10 ns;
    report "CHECK t=" & time'image(now) & " RAM0=" & to_string(rdata) severity note;
    assert rdata = "0001" report "REQ R52: RAM[0] haelt Fibonacci-Zahl 1" severity error;
    addr <= "0001";
    wait for 10 ns;
    report "CHECK t=" & time'image(now) & " RAM1=" & to_string(rdata) severity note;
    assert rdata = "0001" report "REQ R52: RAM[1] haelt Fibonacci-Zahl 1" severity error;
    assert rdata = "0001" report "REQ R78: synchrones Schreiben mit we, RAM[1]=1 lesbar" severity error;

    -- Fibonacci-Folge 2,3,5,8,13 in weitere Zellen (OUT-Werte aus PROMPT.md)
    addr <= "0010"; wdata <= "0010"; we <= '1';  -- 2
    wait until rising_edge(clk);
    addr <= "0011"; wdata <= "0011";            -- 3
    wait until rising_edge(clk);
    addr <= "0100"; wdata <= "0101";            -- 5
    wait until rising_edge(clk);
    addr <= "0101"; wdata <= "1000";            -- 8
    wait until rising_edge(clk);
    addr <= "0110"; wdata <= "1101";            -- 13
    wait until rising_edge(clk);
    we <= '0';
    wait for 1 ns;

    addr <= "0010"; wait for 10 ns;
    assert rdata = "0010" report "REQ R52: RAM[2] Fibonacci-Wert 2" severity error;
    addr <= "0011"; wait for 10 ns;
    assert rdata = "0011" report "REQ R52: RAM[3] Fibonacci-Wert 3" severity error;
    addr <= "0100"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " RAM4=" & to_string(rdata) severity note;
    assert rdata = "0101" report "REQ R52: RAM[4] Fibonacci-Wert 5" severity error;
    addr <= "0101"; wait for 10 ns;
    assert rdata = "1000" report "REQ R52: RAM[5] Fibonacci-Wert 8" severity error;
    addr <= "0110"; wait for 10 ns;
    assert rdata = "1101" report "REQ R52: RAM[6] Fibonacci-Wert 13" severity error;

    -- TC5: Alle 16 Zellen beschreibbar (R16: 16 Zellen zu 4 Bit, R78 Generics)
    for i in 0 to 15 loop
      addr <= std_logic_vector(to_unsigned(i, ADDR_WIDTH));
      wdata <= std_logic_vector(to_unsigned((i * 3 + 1) mod 16, DATA_WIDTH));
      we <= '1';
      wait until rising_edge(clk);
    end loop;
    we <= '0';
    wait for 1 ns;
    for i in 0 to 15 loop
      addr <= std_logic_vector(to_unsigned(i, ADDR_WIDTH));
      wait for 10 ns;
      assert rdata = std_logic_vector(to_unsigned((i * 3 + 1) mod 16, DATA_WIDTH))
        report "REQ R16: Zelle " & integer'image(i) & " muss Muster halten (16x4 pruefen)" severity error;
    end loop;
    report "CHECK t=" & time'image(now) & " alle 16 Zellen Muster ok" severity note;
    assert rdata = std_logic_vector(to_unsigned((15 * 3 + 1) mod 16, DATA_WIDTH))
      report "REQ R78: ADDR_WIDTH=4/DATA_WIDTH=4, Zelle 15 Muster ok" severity error;

    -- TC6: Ueberschreiben derselben Adresse (letzter Wert gewinnt)
    addr <= "0111"; wdata <= "0101"; we <= '1';
    wait until rising_edge(clk);
    wdata <= "1010";
    wait until rising_edge(clk);
    we <= '0';
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " overwrite addr=7 rdata=" & to_string(rdata) severity note;
    assert rdata = "1010" report "REQ R21: wiederholtes STA auf gleiche Adresse, letzter Wert gewinnt" severity error;

    -- TC7: Reset ist synchron (kein asynchrones Loeschen zwischen Flanken)
    -- Lege bekannten Wert an, setze rst ohne Taktflanke, pruefe dass Wert noch da ist
    addr <= "0000"; wdata <= "0111"; we <= '1';
    wait until rising_edge(clk);
    we <= '0';
    wait for 1 ns;
    assert rdata = "0111" report "REQ R71: Vorbereitung sync-Reset-Test, RAM[0]=7" severity error;
    wait until falling_edge(clk);
    rst <= '1';
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " rst=1 vor Flanke rdata=" & to_string(rdata) severity note;
    assert rdata = "0111" report "REQ R71: synchroner Reset darf vor Flanke nicht loeschen" severity error;
    assert rdata = "0111" report "REQ R78: synchroner (nicht asynchroner) Reset" severity error;
    wait until rising_edge(clk);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " nach Reset-Flanke rdata=" & to_string(rdata) severity note;
    assert rdata = "0000" report "REQ R71: nach Reset-Flanke muss RAM[0]=0 sein" severity error;
    -- Alle Zellen nach synchronem Reset 0
    rst <= '0';
    wait for 1 ns;
    rst <= '1';
    wait_cycles(1);
    rst <= '0';
    wait_cycles(1);
    for i in 0 to 15 loop
      addr <= std_logic_vector(to_unsigned(i, ADDR_WIDTH));
      wait for 10 ns;
      assert rdata = "0000" report "REQ R71: alle 16 RAM-Zellen nach Reset 0 (Zelle " & integer'image(i) & ")" severity error;
    end loop;
    report "CHECK t=" & time'image(now) & " Reset loescht alle Zellen, synchron" severity note;

    -- TC8: 4-Bit-Breite: Maximalwert 1111 speicherbar
    addr <= "1111"; wdata <= "1111"; we <= '1';
    wait until rising_edge(clk);
    we <= '0';
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " addr=15 rdata=" & to_string(rdata) severity note;
    assert rdata = "1111" report "REQ R16: Zelle 15 (hoechste Adresse) speichert 15 (4 Bit)" severity error;
    assert rdata = "1111" report "REQ R20: LDA von Adresse 15 liefert 15" severity error;

    tb_done <= true;
    report "TB_COMPLETE" severity note;
    wait;
  end process stim;

end architecture sim;