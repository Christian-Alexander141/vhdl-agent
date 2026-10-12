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

  signal clk   : std_logic := '0';
  signal rst   : std_logic := '1';
  signal we    : std_logic := '0';
  signal addr  : std_logic_vector(ADDR_WIDTH - 1 downto 0) := (others => '0');
  signal din   : std_logic_vector(DATA_WIDTH - 1 downto 0) := (others => '0');
  signal dout  : std_logic_vector(DATA_WIDTH - 1 downto 0);

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
    end procedure;
  begin
    -- Geometrie / Generics (R14: 16 Zellen zu 4 Bit)
    assert addr'length = 4 report "REQ R14: addr-Breite muss 4 sein (16 Zellen)" severity error;
    assert din'length = 4 report "REQ R14: din-Breite muss 4 sein" severity error;
    assert dout'length = 4 report "REQ R14: dout-Breite muss 4 sein" severity error;
    assert addr'length = 4 and din'length = 4 and dout'length = 4 report "REQ R79: data_ram hat ADDR_WIDTH=4 DATA_WIDTH=4" severity error;
    report "CHECK t=" & time'image(now) & " widths addr=" & integer'image(addr'length) & " din=" & integer'image(din'length);

    -- Reset-Sequenz: mind. 2 Zyklen rst='1' (synchroner Reset)
    rst <= '1';
    we <= '0';
    addr <= (others => '0');
    din <= (others => '0');
    wait_cycles(2);
    -- Nach Reset muessen alle 16 Zellen 0 sein (R71), Lesen ist kombinatorisch
    for i in 0 to 15 loop
      addr <= std_logic_vector(to_unsigned(i, ADDR_WIDTH));
      wait for 1 ns;
      report "CHECK t=" & time'image(now) & " reset-check addr=" & integer'image(i) & " dout=" & to_string(dout);
      assert dout = "0000" report "REQ R71: nach synchronem Reset muss RAM(" & integer'image(i) & ")=0 sein" severity error;
    end loop;
    report "CHECK t=" & time'image(now) & " reset-clear done";
    rst <= '0';
    wait_cycles(2);
    -- Nach Reset-Ende weiterhin 0 (kein versehentliches Schreiben)
    addr <= "0000";
    wait for 1 ns;
    assert dout = "0000" report "REQ R71: nach Reset-Ende muss RAM(0)=0 bleiben" severity error;

    -- R19 (STA): synchrones Schreiben mit we=1, eine Zelle
    addr <= "0000"; din <= "0001"; we <= '1';
    wait_cycles(1);
    wait for 1 ns;
    we <= '0';
    report "CHECK t=" & time'image(now) & " write0 dout=" & to_string(dout);
    assert dout = "0001" report "REQ R19: nach STA RAM[0]:=ACC(1) muss dout=0001 sein" severity error;

    -- R18 (LDA): kombinatorisches Lesen ohne Takt
    addr <= "0000";
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " read0 dout=" & to_string(dout);
    assert dout = "0001" report "REQ R18: LDA RAM[0] muss ACC=0001 liefern (komb. Lesen)" severity error;

    -- Zweite Zelle schreiben (Programmstart RAM[1]=1)
    addr <= "0001"; din <= "0001"; we <= '1';
    wait_cycles(1);
    wait for 1 ns;
    we <= '0';
    report "CHECK t=" & time'image(now) & " write1 dout=" & to_string(dout);
    assert dout = "0001" report "REQ R19: nach STA RAM[1]:=1 muss dout=0001 sein" severity error;

    addr <= "0001";
    wait for 1 ns;
    assert dout = "0001" report "REQ R18: LDA RAM[1] muss 0001 liefern" severity error;

    -- we='0' darf nicht schreiben (R19/R79: nur mit we)
    addr <= "0000"; din <= "1111"; we <= '0';
    wait_cycles(1);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " nowe dout=" & to_string(dout);
    assert dout = "0001" report "REQ R19: ohne we darf RAM[0] nicht ueberschrieben werden (bleibt 0001)" severity error;

    -- Alle 16 Zellen mit Adressmuster beschreiben (R14: 16 Zellen)
    for i in 0 to 15 loop
      addr <= std_logic_vector(to_unsigned(i, ADDR_WIDTH));
      din <= std_logic_vector(to_unsigned((i * 3 + 1) mod 16, DATA_WIDTH));
      we <= '1';
      wait_cycles(1);
      wait for 1 ns;
    end loop;
    we <= '0';
    -- Ruecklesen und pruefen
    for i in 0 to 15 loop
      addr <= std_logic_vector(to_unsigned(i, ADDR_WIDTH));
      wait for 1 ns;
      report "CHECK t=" & time'image(now) & " full addr=" & integer'image(i) & " dout=" & to_string(dout);
      assert dout = std_logic_vector(to_unsigned((i * 3 + 1) mod 16, DATA_WIDTH))
        report "REQ R14: RAM(" & integer'image(i) & ") muss geschriebenen Wert halten" severity error;
    end loop;
    assert true report "REQ R79: synchrones Schreiben mit we und kombinatorisches Lesen fuer 16 Zellen ok" severity error;

    -- Fibonacci-Szenario (R48): RAM[0]/RAM[1] halten letzte zwei Fibonacci-Zahlen
    -- Start: 1,1 wie im Demoprogramm nach Befehl 1/2 (STA 0 / STA 1)
    addr <= "0000"; din <= "0001"; we <= '1';
    wait_cycles(1);
    wait for 1 ns;
    addr <= "0001"; din <= "0001";
    wait_cycles(1);
    wait for 1 ns;
    we <= '0';
    addr <= "0000"; wait for 1 ns;
    assert dout = "0001" report "REQ R48: RAM[0] haelt Fibonacci-Zahl 1" severity error;
    addr <= "0001"; wait for 1 ns;
    assert dout = "0001" report "REQ R48: RAM[1] haelt Fibonacci-Zahl 1" severity error;
    report "CHECK t=" & time'image(now) & " fib-start ok";

    -- Iteration: Summe 1+1=2 -> STA 2, shift (wie Befehle 5-11)
    addr <= "0010"; din <= "0010"; we <= '1';
    wait_cycles(1);
    wait for 1 ns;
    we <= '0';
    addr <= "0010"; wait for 1 ns;
    assert dout = "0010" report "REQ R48: RAM[2] haelt Summe 2" severity error;
    -- shift: RAM[0]:=RAM[1]=1, RAM[1]:=RAM[2]=2
    addr <= "0000"; din <= "0001"; we <= '1';
    wait_cycles(1);
    wait for 1 ns;
    addr <= "0001"; din <= "0010";
    wait_cycles(1);
    wait for 1 ns;
    we <= '0';
    addr <= "0000"; wait for 1 ns;
    assert dout = "0001" report "REQ R48: nach Shift RAM[0]=1" severity error;
    addr <= "0001"; wait for 1 ns;
    assert dout = "0010" report "REQ R48: nach Shift RAM[1]=2" severity error;
    -- naechste Summe 1+2=3
    addr <= "0010"; din <= "0011"; we <= '1';
    wait_cycles(1);
    wait for 1 ns;
    we <= '0';
    addr <= "0010"; wait for 1 ns;
    assert dout = "0011" report "REQ R48: RAM[2] haelt Summe 3" severity error;
    -- shift: RAM[0]=2, RAM[1]=3
    addr <= "0000"; din <= "0010"; we <= '1';
    wait_cycles(1);
    wait for 1 ns;
    addr <= "0001"; din <= "0011";
    wait_cycles(1);
    wait for 1 ns;
    we <= '0';
    addr <= "0000"; wait for 1 ns;
    assert dout = "0010" report "REQ R48: nach Shift RAM[0]=2" severity error;
    addr <= "0001"; wait for 1 ns;
    assert dout = "0011" report "REQ R48: nach Shift RAM[1]=3" severity error;
    -- Fibonacci-Folge 5, 8, 13 in RAM ablegen
    addr <= "0000"; din <= "0101"; we <= '1';  -- 5
    wait_cycles(1);
    wait for 1 ns;
    addr <= "0001"; din <= "1000";             -- 8
    wait_cycles(1);
    wait for 1 ns;
    we <= '0';
    addr <= "0000"; wait for 1 ns;
    assert dout = "0101" report "REQ R48: RAM[0]=5 (Fibonacci)" severity error;
    addr <= "0001"; wait for 1 ns;
    assert dout = "1000" report "REQ R48: RAM[1]=8 (Fibonacci)" severity error;
    report "CHECK t=" & time'image(now) & " fib 5/8 ok";
    addr <= "0000"; din <= "1000"; we <= '1';  -- RAM[0]=8
    wait_cycles(1);
    wait for 1 ns;
    addr <= "0001"; din <= "1101";             -- RAM[1]=13
    wait_cycles(1);
    wait for 1 ns;
    we <= '0';
    addr <= "0000"; wait for 1 ns;
    assert dout = "1000" report "REQ R48: RAM[0]=8 vor Ueberlauf" severity error;
    addr <= "0001"; wait for 1 ns;
    assert dout = "1101" report "REQ R48: RAM[1]=13 (letzte OUT vor Halt)" severity error;
    report "CHECK t=" & time'image(now) & " fib 8/13 ok";

    -- R20 (ADD-Operand): RAM liefert Operanden 8 und 13 fuer 8+13=21 (mod16=5)
    addr <= "0000"; wait for 1 ns;
    assert dout = "1000" report "REQ R20: ADD-Operand RAM[0] muss 8 sein (8+13=21 mod16=5)" severity error;
    addr <= "0001"; wait for 1 ns;
    assert dout = "1101" report "REQ R20: ADD-Operand RAM[1] muss 13 sein (8+13=21 mod16=5)" severity error;

    -- R21 (SUB-Operand): Operanden fuer Borrow-Fall bereitstellen
    addr <= "0010"; din <= "0011"; we <= '1';  -- 3
    wait_cycles(1);
    wait for 1 ns;
    addr <= "0011"; din <= "0101";             -- 5
    wait_cycles(1);
    wait for 1 ns;
    we <= '0';
    addr <= "0010"; wait for 1 ns;
    assert dout = "0011" report "REQ R21: SUB-Operand RAM[2] muss 3 sein" severity error;
    addr <= "0011"; wait for 1 ns;
    assert dout = "0101" report "REQ R21: SUB-Operand RAM[3] muss 5 sein (3<5 -> Borrow)" severity error;
    report "CHECK t=" & time'image(now) & " sub-operands ok";

    -- R22 (AND/OR/XOR-Operanden): z.B. 12 (1100) und 10 (1010)
    addr <= "0100"; din <= "1100"; we <= '1';
    wait_cycles(1);
    wait for 1 ns;
    addr <= "0101"; din <= "1010";
    wait_cycles(1);
    wait for 1 ns;
    we <= '0';
    addr <= "0100"; wait for 1 ns;
    assert dout = "1100" report "REQ R22: Logik-Operand RAM[4] muss 1100 sein" severity error;
    addr <= "0101"; wait for 1 ns;
    assert dout = "1010" report "REQ R22: Logik-Operand RAM[5] muss 1010 sein" severity error;
    report "CHECK t=" & time'image(now) & " logic-operands ok";

    -- Adresswechsel ohne Takt: kombinatorisches Lesen (R18/R79)
    addr <= "0100"; wait for 1 ns;
    assert dout = "1100" report "REQ R18: kombinatorisches Lesen addr=4 ohne Takt" severity error;
    addr <= "0101"; wait for 1 ns;
    assert dout = "1010" report "REQ R18: kombinatorisches Lesen addr=5 ohne Takt" severity error;
    addr <= "0001"; wait for 1 ns;
    assert dout = "1101" report "REQ R79: kombinatorisches Lesen liefert sofort (addr=1 -> 13)" severity error;

    -- Reset mitten im Betrieb loescht alle Zellen (R71 zweiter Durchgang)
    rst <= '1';
    wait_cycles(2);
    for i in 0 to 15 loop
      addr <= std_logic_vector(to_unsigned(i, ADDR_WIDTH));
      wait for 1 ns;
      report "CHECK t=" & time'image(now) & " re-reset addr=" & integer'image(i) & " dout=" & to_string(dout);
      assert dout = "0000" report "REQ R71: nach zweitem synchronem Reset muss RAM(" & integer'image(i) & ")=0 sein" severity error;
    end loop;
    rst <= '0';
    wait_cycles(1);
    addr <= "0000"; wait for 1 ns;
    assert dout = "0000" report "REQ R71: nach Reset-Ende bleibt RAM(0)=0" severity error;

    tb_done <= true;
    assert false report "TB_COMPLETE" severity note;
    std.env.stop;
    wait;
  end process stim;

end architecture sim;