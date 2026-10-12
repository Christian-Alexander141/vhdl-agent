library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity alu_tb is
end entity alu_tb;

architecture sim of alu_tb is
  constant WIDTH : positive := 4;

  signal a      : std_logic_vector(WIDTH-1 downto 0) := (others => '0');
  signal b      : std_logic_vector(WIDTH-1 downto 0) := (others => '0');
  signal op     : std_logic_vector(2 downto 0) := (others => '0');
  signal result : std_logic_vector(WIDTH-1 downto 0);
  signal carry  : std_logic;
  signal zero   : std_logic;
begin

  dut: entity work.alu
    generic map (
      WIDTH => WIDTH
    )
    port map (
      a      => a,
      b      => b,
      op     => op,
      result => result,
      carry  => carry,
      zero   => zero
    );

  stim: process
  begin
    -- ADD ohne Uebertrag: 3 + 5 = 8
    a <= "0011"; b <= "0101"; op <= "000";
    wait for 10 ns;
    report "CHECK t=" & time'image(now) & " ADD 3+5 result=" & to_string(result) & " carry=" & to_string(carry) & " zero=" & to_string(zero) severity note;
    assert result = "1000" report "REQ R22: ADD 3+5 result muss 8 sein" severity error;
    assert carry = '0' report "REQ R22: ADD 3+5 carry muss 0 sein" severity error;
    assert zero = '0' report "REQ R34: ADD 3+5 zero muss 0 sein (result/=0)" severity error;

    -- ADD Fibonacci-Ueberlauf: 13 + 8 = 21 mod 16 = 5, carry 1
    a <= "1101"; b <= "1000"; op <= "000";
    wait for 10 ns;
    report "CHECK t=" & time'image(now) & " ADD 13+8 result=" & to_string(result) & " carry=" & to_string(carry) severity note;
    assert result = "0101" report "REQ R22: ADD 13+8 result muss 5 sein (21 mod 16)" severity error;
    assert carry = '1' report "REQ R22: ADD 13+8 carry muss 1 sein (Uebertrag aus Bit 3)" severity error;
    assert zero = '0' report "REQ R34: ADD 13+8 zero muss 0 sein" severity error;

    -- ADD 0+0 = 0, zero 1
    a <= "0000"; b <= "0000"; op <= "000";
    wait for 10 ns;
    report "CHECK t=" & time'image(now) & " ADD 0+0 result=" & to_string(result) severity note;
    assert result = "0000" report "REQ R22: ADD 0+0 result muss 0 sein" severity error;
    assert carry = '0' report "REQ R76: ADD 0+0 carry muss 0 sein" severity error;
    assert zero = '1' report "REQ R34: ADD 0+0 zero muss 1 sein (result=0)" severity error;

    -- ADD 15+1 = 0 mit carry (maximaler Ueberlauf)
    a <= "1111"; b <= "0001"; op <= "000";
    wait for 10 ns;
    assert result = "0000" report "REQ R22: ADD 15+1 result muss 0 sein" severity error;
    assert carry = '1' report "REQ R76: ADD 15+1 carry muss 1 sein" severity error;
    assert zero = '1' report "REQ R34: ADD 15+1 zero muss 1 sein" severity error;

    -- SUB ohne Borgen: 5 - 3 = 2
    a <= "0101"; b <= "0011"; op <= "001";
    wait for 10 ns;
    report "CHECK t=" & time'image(now) & " SUB 5-3 result=" & to_string(result) & " carry=" & to_string(carry) severity note;
    assert result = "0010" report "REQ R23: SUB 5-3 result muss 2 sein" severity error;
    assert carry = '0' report "REQ R23: SUB 5-3 carry muss 0 sein (kein Borgen)" severity error;
    assert zero = '0' report "REQ R34: SUB 5-3 zero muss 0 sein" severity error;

    -- SUB mit Borgen: 3 - 5 = 14 mod 16, carry 1
    a <= "0011"; b <= "0101"; op <= "001";
    wait for 10 ns;
    report "CHECK t=" & time'image(now) & " SUB 3-5 result=" & to_string(result) & " carry=" & to_string(carry) severity note;
    assert result = "1110" report "REQ R23: SUB 3-5 result muss 14 sein ((3-5) mod 16)" severity error;
    assert carry = '1' report "REQ R23: SUB 3-5 carry muss 1 sein (Borgen, ACC<RAM)" severity error;
    assert zero = '0' report "REQ R76: SUB 3-5 zero muss 0 sein" severity error;

    -- SUB gleich: 7 - 7 = 0
    a <= "0111"; b <= "0111"; op <= "001";
    wait for 10 ns;
    assert result = "0000" report "REQ R23: SUB 7-7 result muss 0 sein" severity error;
    assert carry = '0' report "REQ R23: SUB 7-7 carry muss 0 sein (kein Borgen bei gleich)" severity error;
    assert zero = '1' report "REQ R34: SUB 7-7 zero muss 1 sein" severity error;

    -- SUB 0 - 1 = 15 mit Borgen
    a <= "0000"; b <= "0001"; op <= "001";
    wait for 10 ns;
    assert result = "1111" report "REQ R23: SUB 0-1 result muss 15 sein" severity error;
    assert carry = '1' report "REQ R23: SUB 0-1 carry muss 1 sein" severity error;
    assert zero = '0' report "REQ R34: SUB 0-1 zero muss 0 sein" severity error;

    -- AND: 12 and 10 = 8
    a <= "1100"; b <= "1010"; op <= "010";
    wait for 10 ns;
    report "CHECK t=" & time'image(now) & " AND result=" & to_string(result) severity note;
    assert result = "1000" report "REQ R24: AND 12/10 result muss 8 sein" severity error;
    assert carry = '0' report "REQ R24: AND carry muss 0 sein" severity error;
    assert zero = '0' report "REQ R34: AND 12/10 zero muss 0 sein" severity error;

    -- AND mit Nullergebnis: 12 and 3 = 0
    a <= "1100"; b <= "0011"; op <= "010";
    wait for 10 ns;
    assert result = "0000" report "REQ R24: AND 12/3 result muss 0 sein" severity error;
    assert carry = '0' report "REQ R76: AND carry muss 0 sein" severity error;
    assert zero = '1' report "REQ R34: AND 12/3 zero muss 1 sein" severity error;

    -- OR: 12 or 10 = 14
    a <= "1100"; b <= "1010"; op <= "011";
    wait for 10 ns;
    report "CHECK t=" & time'image(now) & " OR result=" & to_string(result) severity note;
    assert result = "1110" report "REQ R25: OR 12/10 result muss 14 sein" severity error;
    assert carry = '0' report "REQ R25: OR carry muss 0 sein" severity error;
    assert zero = '0' report "REQ R34: OR 12/10 zero muss 0 sein" severity error;

    -- OR 0 or 0 = 0
    a <= "0000"; b <= "0000"; op <= "011";
    wait for 10 ns;
    assert result = "0000" report "REQ R25: OR 0/0 result muss 0 sein" severity error;
    assert carry = '0' report "REQ R76: OR carry muss 0 sein" severity error;
    assert zero = '1' report "REQ R34: OR 0/0 zero muss 1 sein" severity error;

    -- XOR: 12 xor 10 = 6
    a <= "1100"; b <= "1010"; op <= "100";
    wait for 10 ns;
    report "CHECK t=" & time'image(now) & " XOR result=" & to_string(result) severity note;
    assert result = "0110" report "REQ R26: XOR 12/10 result muss 6 sein" severity error;
    assert carry = '0' report "REQ R26: XOR carry muss 0 sein" severity error;
    assert zero = '0' report "REQ R34: XOR 12/10 zero muss 0 sein" severity error;

    -- XOR gleich: 7 xor 7 = 0
    a <= "0111"; b <= "0111"; op <= "100";
    wait for 10 ns;
    assert result = "0000" report "REQ R26: XOR 7/7 result muss 0 sein" severity error;
    assert carry = '0' report "REQ R76: XOR carry muss 0 sein" severity error;
    assert zero = '1' report "REQ R34: XOR 7/7 zero muss 1 sein" severity error;

    -- SHL ohne Carry: 3 << 1 = 6
    a <= "0011"; b <= "0000"; op <= "101";
    wait for 10 ns;
    report "CHECK t=" & time'image(now) & " SHL result=" & to_string(result) & " carry=" & to_string(carry) severity note;
    assert result = "0110" report "REQ R27: SHL 3 result muss 6 sein" severity error;
    assert carry = '0' report "REQ R27: SHL 3 carry muss 0 sein (altes Bit 3 = 0)" severity error;
    assert zero = '0' report "REQ R34: SHL 3 zero muss 0 sein" severity error;

    -- SHL mit Carry: 9 (1001) << 1 = 2 (0010), carry 1
    a <= "1001"; b <= "1111"; op <= "101";
    wait for 10 ns;
    assert result = "0010" report "REQ R27: SHL 9 result muss 2 sein (rechts 0 nachgeschoben)" severity error;
    assert carry = '1' report "REQ R27: SHL 9 carry muss 1 sein (altes Bit 3)" severity error;
    assert zero = '0' report "REQ R76: SHL 9 zero muss 0 sein" severity error;

    -- SHL 8 (1000) -> 0 mit carry (Nullergebnis mit Carry)
    a <= "1000"; b <= "0000"; op <= "101";
    wait for 10 ns;
    assert result = "0000" report "REQ R27: SHL 8 result muss 0 sein" severity error;
    assert carry = '1' report "REQ R27: SHL 8 carry muss 1 sein" severity error;
    assert zero = '1' report "REQ R34: SHL 8 zero muss 1 sein" severity error;

    -- SHR ohne Carry: 6 >> 1 = 3
    a <= "0110"; b <= "0000"; op <= "110";
    wait for 10 ns;
    report "CHECK t=" & time'image(now) & " SHR result=" & to_string(result) & " carry=" & to_string(carry) severity note;
    assert result = "0011" report "REQ R28: SHR 6 result muss 3 sein" severity error;
    assert carry = '0' report "REQ R28: SHR 6 carry muss 0 sein (altes Bit 0 = 0)" severity error;
    assert zero = '0' report "REQ R34: SHR 6 zero muss 0 sein" severity error;

    -- SHR mit Carry: 5 (0101) >> 1 = 2 (0010), carry 1
    a <= "0101"; b <= "1111"; op <= "110";
    wait for 10 ns;
    assert result = "0010" report "REQ R28: SHR 5 result muss 2 sein (links 0 nachgeschoben)" severity error;
    assert carry = '1' report "REQ R28: SHR 5 carry muss 1 sein (altes Bit 0)" severity error;
    assert zero = '0' report "REQ R76: SHR 5 zero muss 0 sein" severity error;

    -- SHR 1 -> 0 mit carry
    a <= "0001"; b <= "0000"; op <= "110";
    wait for 10 ns;
    assert result = "0000" report "REQ R28: SHR 1 result muss 0 sein" severity error;
    assert carry = '1' report "REQ R28: SHR 1 carry muss 1 sein" severity error;
    assert zero = '1' report "REQ R34: SHR 1 zero muss 1 sein" severity error;

    -- PASS b (LDI/LDA-Pfad): b wird durchgereicht, a ignoriert
    a <= "1111"; b <= "1001"; op <= "111";
    wait for 10 ns;
    report "CHECK t=" & time'image(now) & " PASS result=" & to_string(result) severity note;
    assert result = "1001" report "REQ R19: PASS b=9 result muss 9 sein (LDI n: ACC:=n)" severity error;
    assert carry = '0' report "REQ R76: PASS carry muss 0 sein" severity error;
    assert zero = '0' report "REQ R34: PASS b=9 zero muss 0 sein" severity error;

    -- PASS b = 0 -> zero gesetzt (Z neu)
    a <= "0101"; b <= "0000"; op <= "111";
    wait for 10 ns;
    assert result = "0000" report "REQ R19: PASS b=0 result muss 0 sein (LDI 0)" severity error;
    assert carry = '0' report "REQ R76: PASS b=0 carry muss 0 sein" severity error;
    assert zero = '1' report "REQ R34: PASS b=0 zero muss 1 sein (Z=1 wenn ACC=0)" severity error;

    report "TB_COMPLETE" severity note;
    wait;
  end process stim;

end architecture sim;