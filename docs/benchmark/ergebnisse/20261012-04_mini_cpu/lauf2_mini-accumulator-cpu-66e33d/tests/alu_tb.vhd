library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.env.all;

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
    generic map (WIDTH => WIDTH)
    port map (
      a      => a,
      b      => b,
      op     => op,
      result => result,
      carry  => carry,
      zero   => zero
    );

  stim: process
    variable av      : unsigned(WIDTH-1 downto 0);
    variable bv      : unsigned(WIDTH-1 downto 0);
    variable sum_ext : unsigned(WIDTH downto 0);
    variable exp     : std_logic_vector(WIDTH-1 downto 0);
    variable exp_c   : std_logic;
    variable exp_z   : std_logic;
  begin
    -- ============================================================
    -- R62: op-Codierung / kombinatorisch, Grundfunktion ADD 1+1=2
    -- ============================================================
    a <= "0001"; b <= "0001"; op <= "000";
    wait for 10 ns;
    report "CHECK t=" & time'image(now) & " ADD a=1 b=1 result=" & integer'image(to_integer(unsigned(result))) & " carry=" & std_logic'image(carry) & " zero=" & std_logic'image(zero);
    assert result = "0010" report "REQ R16: ADD 1+1 muss 2 sein, ist " & integer'image(to_integer(unsigned(result))) severity error;
    assert carry = '0' report "REQ R16: ADD 1+1 carry muss 0 sein" severity error;
    assert zero = '0' report "REQ R26: ADD 1+1 zero muss 0 sein (result/=0)" severity error;
    assert op = "000" report "REQ R62: ADD-Opcode muss 000 sein" severity error;

    -- R16: Fibonacci-Kontext 5+8=13 (kein Uebertrag)
    a <= "0101"; b <= "1000"; op <= "000";
    wait for 10 ns;
    report "CHECK t=" & time'image(now) & " ADD 5+8 result=" & integer'image(to_integer(unsigned(result))) & " carry=" & std_logic'image(carry);
    assert result = "1101" report "REQ R16: ADD 5+8 muss 13 sein, ist " & integer'image(to_integer(unsigned(result))) severity error;
    assert carry = '0' report "REQ R16: ADD 5+8 carry muss 0 sein" severity error;
    assert zero = '0' report "REQ R26: ADD 5+8 zero muss 0 sein" severity error;

    -- R16: Fibonacci-Ueberlauf 8+13=21 mod 16=5 mit C=1 (PROMPT.md: JC nach 14)
    a <= "1000"; b <= "1101"; op <= "000";
    wait for 10 ns;
    report "CHECK t=" & time'image(now) & " ADD 8+13 result=" & integer'image(to_integer(unsigned(result))) & " carry=" & std_logic'image(carry);
    assert result = "0101" report "REQ R16: ADD 8+13 muss 5 sein (21 mod 16), ist " & integer'image(to_integer(unsigned(result))) severity error;
    assert carry = '1' report "REQ R16: ADD 8+13 carry muss 1 sein (Uebertrag aus Bit 3)" severity error;
    assert zero = '0' report "REQ R26: ADD 8+13 zero muss 0 sein" severity error;

    -- R16/R26: 15+1=0 mit C=1, Z=1
    a <= "1111"; b <= "0001"; op <= "000";
    wait for 10 ns;
    report "CHECK t=" & time'image(now) & " ADD 15+1 result=" & integer'image(to_integer(unsigned(result))) & " carry=" & std_logic'image(carry) & " zero=" & std_logic'image(zero);
    assert result = "0000" report "REQ R16: ADD 15+1 muss 0 sein (mod 16)" severity error;
    assert carry = '1' report "REQ R16: ADD 15+1 carry muss 1 sein" severity error;
    assert zero = '1' report "REQ R26: ADD 15+1 zero muss 1 sein (result=0)" severity error;

    -- R16: 8+8=0 mit C=1
    a <= "1000"; b <= "1000"; op <= "000";
    wait for 10 ns;
    assert result = "0000" report "REQ R16: ADD 8+8 muss 0 sein" severity error;
    assert carry = '1' report "REQ R16: ADD 8+8 carry muss 1 sein" severity error;
    assert zero = '1' report "REQ R26: ADD 8+8 zero muss 1 sein" severity error;

    -- R16: 0+0=0 ohne Carry
    a <= "0000"; b <= "0000"; op <= "000";
    wait for 10 ns;
    assert result = "0000" report "REQ R16: ADD 0+0 muss 0 sein" severity error;
    assert carry = '0' report "REQ R16: ADD 0+0 carry muss 0 sein" severity error;
    assert zero = '1' report "REQ R26: ADD 0+0 zero muss 1 sein" severity error;

    -- ============================================================
    -- R17: SUB (C=1 bei Borgen, d.h. a<b)
    -- ============================================================
    -- 5-3=2, kein Borgen
    a <= "0101"; b <= "0011"; op <= "001";
    wait for 10 ns;
    report "CHECK t=" & time'image(now) & " SUB 5-3 result=" & integer'image(to_integer(unsigned(result))) & " carry=" & std_logic'image(carry);
    assert result = "0010" report "REQ R17: SUB 5-3 muss 2 sein, ist " & integer'image(to_integer(unsigned(result))) severity error;
    assert carry = '0' report "REQ R17: SUB 5-3 carry muss 0 sein (kein Borgen)" severity error;
    assert zero = '0' report "REQ R26: SUB 5-3 zero muss 0 sein" severity error;

    -- 3-5=14 (mod 16), Borgen
    a <= "0011"; b <= "0101"; op <= "001";
    wait for 10 ns;
    report "CHECK t=" & time'image(now) & " SUB 3-5 result=" & integer'image(to_integer(unsigned(result))) & " carry=" & std_logic'image(carry);
    assert result = "1110" report "REQ R17: SUB 3-5 muss 14 sein (mod 16), ist " & integer'image(to_integer(unsigned(result))) severity error;
    assert carry = '1' report "REQ R17: SUB 3-5 carry muss 1 sein (Borgen, 3<5)" severity error;
    assert zero = '0' report "REQ R26: SUB 3-5 zero muss 0 sein" severity error;

    -- 5-5=0, kein Borgen, Z=1
    a <= "0101"; b <= "0101"; op <= "001";
    wait for 10 ns;
    assert result = "0000" report "REQ R17: SUB 5-5 muss 0 sein" severity error;
    assert carry = '0' report "REQ R17: SUB 5-5 carry muss 0 sein (5<5 falsch)" severity error;
    assert zero = '1' report "REQ R26: SUB 5-5 zero muss 1 sein" severity error;

    -- 0-1=15, Borgen
    a <= "0000"; b <= "0001"; op <= "001";
    wait for 10 ns;
    assert result = "1111" report "REQ R17: SUB 0-1 muss 15 sein" severity error;
    assert carry = '1' report "REQ R17: SUB 0-1 carry muss 1 sein (Borgen)" severity error;
    assert zero = '0' report "REQ R26: SUB 0-1 zero muss 0 sein" severity error;

    -- 0-0=0, kein Borgen
    a <= "0000"; b <= "0000"; op <= "001";
    wait for 10 ns;
    assert result = "0000" report "REQ R17: SUB 0-0 muss 0 sein" severity error;
    assert carry = '0' report "REQ R17: SUB 0-0 carry muss 0 sein" severity error;
    assert zero = '1' report "REQ R26: SUB 0-0 zero muss 1 sein" severity error;

    -- 8-13=11 (mod 16), Borgen (8<13)
    a <= "1000"; b <= "1101"; op <= "001";
    wait for 10 ns;
    assert result = "1011" report "REQ R17: SUB 8-13 muss 11 sein, ist " & integer'image(to_integer(unsigned(result))) severity error;
    assert carry = '1' report "REQ R17: SUB 8-13 carry muss 1 sein" severity error;

    -- ============================================================
    -- R18: AND / OR / XOR (C=0, Z neu)
    -- ============================================================
    -- AND: 1010 & 1100 = 1000
    a <= "1010"; b <= "1100"; op <= "010";
    wait for 10 ns;
    report "CHECK t=" & time'image(now) & " AND result=" & integer'image(to_integer(unsigned(result))) & " carry=" & std_logic'image(carry);
    assert result = "1000" report "REQ R18: AND 1010&1100 muss 1000 sein" severity error;
    assert carry = '0' report "REQ R18: AND carry muss 0 sein" severity error;
    assert zero = '0' report "REQ R26: AND 1010&1100 zero muss 0 sein" severity error;

    -- AND zero-Fall: 1111 & 0000 = 0000
    a <= "1111"; b <= "0000"; op <= "010";
    wait for 10 ns;
    assert result = "0000" report "REQ R18: AND 1111&0000 muss 0 sein" severity error;
    assert carry = '0' report "REQ R18: AND carry muss 0 sein" severity error;
    assert zero = '1' report "REQ R26: AND 0-Ergebnis zero muss 1 sein" severity error;

    -- OR: 1010 | 1100 = 1110
    a <= "1010"; b <= "1100"; op <= "011";
    wait for 10 ns;
    report "CHECK t=" & time'image(now) & " OR result=" & integer'image(to_integer(unsigned(result)));
    assert result = "1110" report "REQ R18: OR 1010|1100 muss 1110 sein" severity error;
    assert carry = '0' report "REQ R18: OR carry muss 0 sein" severity error;
    assert zero = '0' report "REQ R26: OR zero muss 0 sein" severity error;

    -- OR zero-Fall: 0000 | 0000 = 0000
    a <= "0000"; b <= "0000"; op <= "011";
    wait for 10 ns;
    assert result = "0000" report "REQ R18: OR 0|0 muss 0 sein" severity error;
    assert carry = '0' report "REQ R18: OR carry muss 0 sein" severity error;
    assert zero = '1' report "REQ R26: OR 0-Ergebnis zero muss 1 sein" severity error;

    -- XOR: 1010 xor 1100 = 0110
    a <= "1010"; b <= "1100"; op <= "100";
    wait for 10 ns;
    report "CHECK t=" & time'image(now) & " XOR result=" & integer'image(to_integer(unsigned(result)));
    assert result = "0110" report "REQ R18: XOR 1010^1100 muss 0110 sein" severity error;
    assert carry = '0' report "REQ R18: XOR carry muss 0 sein" severity error;
    assert zero = '0' report "REQ R26: XOR zero muss 0 sein" severity error;

    -- XOR zero-Fall: 0101 ^ 0101 = 0000
    a <= "0101"; b <= "0101"; op <= "100";
    wait for 10 ns;
    assert result = "0000" report "REQ R18: XOR 0101^0101 muss 0 sein" severity error;
    assert carry = '0' report "REQ R18: XOR carry muss 0 sein" severity error;
    assert zero = '1' report "REQ R26: XOR 0-Ergebnis zero muss 1 sein" severity error;

    -- ============================================================
    -- R19: SHL von a (rechts 0, C=altes Bit 3)
    -- ============================================================
    a <= "0001"; b <= "0000"; op <= "101";
    wait for 10 ns;
    report "CHECK t=" & time'image(now) & " SHL 0001 result=" & integer'image(to_integer(unsigned(result))) & " carry=" & std_logic'image(carry);
    assert result = "0010" report "REQ R19: SHL 0001 muss 0010 sein" severity error;
    assert carry = '0' report "REQ R19: SHL 0001 carry muss 0 sein (altes Bit3)" severity error;
    assert zero = '0' report "REQ R26: SHL 0001 zero muss 0 sein" severity error;

    -- SHL 1000 -> 0000, C=1, Z=1
    a <= "1000"; b <= "0000"; op <= "101";
    wait for 10 ns;
    assert result = "0000" report "REQ R19: SHL 1000 muss 0000 sein" severity error;
    assert carry = '1' report "REQ R19: SHL 1000 carry muss 1 sein (altes Bit3)" severity error;
    assert zero = '1' report "REQ R26: SHL 1000 zero muss 1 sein" severity error;

    -- SHL 1011 -> 0110, C=1
    a <= "1011"; b <= "0000"; op <= "101";
    wait for 10 ns;
    assert result = "0110" report "REQ R19: SHL 1011 muss 0110 sein" severity error;
    assert carry = '1' report "REQ R19: SHL 1011 carry muss 1 sein" severity error;
    assert zero = '0' report "REQ R26: SHL 1011 zero muss 0 sein" severity error;

    -- SHL ignoriert b: gleiches a, anderes b -> gleiches Ergebnis
    a <= "0011"; b <= "1111"; op <= "101";
    wait for 10 ns;
    assert result = "0110" report "REQ R19: SHL 0011 muss 0110 sein (b unabhaengig)" severity error;
    assert carry = '0' report "REQ R19: SHL 0011 carry muss 0 sein" severity error;
    a <= "0011"; b <= "0000"; op <= "101";
    wait for 10 ns;
    assert result = "0110" report "REQ R62: SHL muss b ignorieren (nur von a abhaengen)" severity error;

    -- ============================================================
    -- R20: SHR von a (links 0, C=altes Bit 0)
    -- ============================================================
    a <= "1000"; b <= "0000"; op <= "110";
    wait for 10 ns;
    report "CHECK t=" & time'image(now) & " SHR 1000 result=" & integer'image(to_integer(unsigned(result))) & " carry=" & std_logic'image(carry);
    assert result = "0100" report "REQ R20: SHR 1000 muss 0100 sein" severity error;
    assert carry = '0' report "REQ R20: SHR 1000 carry muss 0 sein (altes Bit0)" severity error;
    assert zero = '0' report "REQ R26: SHR 1000 zero muss 0 sein" severity error;

    -- SHR 0001 -> 0000, C=1, Z=1
    a <= "0001"; b <= "0000"; op <= "110";
    wait for 10 ns;
    assert result = "0000" report "REQ R20: SHR 0001 muss 0000 sein" severity error;
    assert carry = '1' report "REQ R20: SHR 0001 carry muss 1 sein (altes Bit0)" severity error;
    assert zero = '1' report "REQ R26: SHR 0001 zero muss 1 sein" severity error;

    -- SHR 1011 -> 0101, C=1
    a <= "1011"; b <= "0000"; op <= "110";
    wait for 10 ns;
    assert result = "0101" report "REQ R20: SHR 1011 muss 0101 sein" severity error;
    assert carry = '1' report "REQ R20: SHR 1011 carry muss 1 sein" severity error;
    assert zero = '0' report "REQ R26: SHR 1011 zero muss 0 sein" severity error;

    -- SHR ignoriert b
    a <= "1100"; b <= "1111"; op <= "110";
    wait for 10 ns;
    assert result = "0110" report "REQ R20: SHR 1100 muss 0110 sein (b unabhaengig)" severity error;
    assert carry = '0' report "REQ R20: SHR 1100 carry muss 0 sein" severity error;
    a <= "1100"; b <= "0000"; op <= "110";
    wait for 10 ns;
    assert result = "0110" report "REQ R62: SHR muss b ignorieren (nur von a abhaengen)" severity error;

    -- ============================================================
    -- R13/R62: PASS b (LDI-Pfad: ACC:=n, C=0, Z neu)
    -- ============================================================
    a <= "0000"; b <= "0001"; op <= "111";
    wait for 10 ns;
    report "CHECK t=" & time'image(now) & " PASS b=1 result=" & integer'image(to_integer(unsigned(result)));
    assert result = "0001" report "REQ R13: PASS/LDI 1 muss 0001 liefern (ACC:=n), ist " & integer'image(to_integer(unsigned(result))) severity error;
    assert carry = '0' report "REQ R62: PASS carry muss 0 sein" severity error;
    assert zero = '0' report "REQ R26: PASS 1 zero muss 0 sein" severity error;

    -- PASS 0 -> Z=1
    a <= "1111"; b <= "0000"; op <= "111";
    wait for 10 ns;
    assert result = "0000" report "REQ R13: PASS/LDI 0 muss 0000 liefern" severity error;
    assert carry = '0' report "REQ R62: PASS carry muss 0 sein" severity error;
    assert zero = '1' report "REQ R26: PASS 0 zero muss 1 sein (Z neu: ACC=0)" severity error;

    -- PASS ignoriert a
    a <= "0101"; b <= "1101"; op <= "111";
    wait for 10 ns;
    assert result = "1101" report "REQ R62: PASS muss b liefern (13), unabhaengig von a" severity error;
    a <= "0000"; b <= "1101"; op <= "111";
    wait for 10 ns;
    assert result = "1101" report "REQ R62: PASS muss b liefern, unabhaengig von a" severity error;
    assert carry = '0' report "REQ R62: PASS carry muss 0 sein" severity error;

    -- PASS Fibonacci-Wert 5
    a <= "0000"; b <= "0101"; op <= "111";
    wait for 10 ns;
    assert result = "0101" report "REQ R13: PASS/LDI 5 muss 0101 liefern" severity error;
    assert zero = '0' report "REQ R26: PASS 5 zero muss 0 sein" severity error;

    -- ============================================================
    -- R62: Kombinatorik-Nachweis (ohne Takt, 1 ns Latenz)
    -- ============================================================
    a <= "0010"; b <= "0011"; op <= "000";
    wait for 1 ns;
    assert result = "0101" report "REQ R62: ALU muss kombinatorisch sein (ADD 2+3=5 nach 1 ns)" severity error;
    report "CHECK t=" & time'image(now) & " komb ADD 2+3=" & integer'image(to_integer(unsigned(result)));
    op <= "001";
    wait for 1 ns;
    -- 2-3 = 15 mod 16 (gleiche Eingaenge, nur op gewechselt)
    assert result = "1111" report "REQ R62: ALU muss kombinatorisch op folgen (SUB 2-3=15)" severity error;
    wait for 9 ns;

    -- ============================================================
    -- Erschoepfend: ADD/SUB/AND/OR/XOR ueber alle 16x16 Paare
    -- Golden Model unabhaengig mit numeric_std berechnet
    -- ============================================================
    op <= "000";
    for i in 0 to 15 loop
      for j in 0 to 15 loop
        a <= std_logic_vector(to_unsigned(i, WIDTH));
        b <= std_logic_vector(to_unsigned(j, WIDTH));
        wait for 10 ns;
        sum_ext := ('0' & to_unsigned(i, WIDTH)) + ('0' & to_unsigned(j, WIDTH));
        exp := std_logic_vector(sum_ext(WIDTH-1 downto 0));
        exp_c := sum_ext(WIDTH);
        if exp = "0000" then exp_z := '1'; else exp_z := '0'; end if;
        assert result = exp report "REQ R16: ADD exhaust i=" & integer'image(i) & " j=" & integer'image(j) severity error;
        assert carry = exp_c report "REQ R16: ADD exhaust carry i=" & integer'image(i) & " j=" & integer'image(j) severity error;
        assert zero = exp_z report "REQ R26: ADD exhaust zero i=" & integer'image(i) & " j=" & integer'image(j) severity error;
      end loop;
    end loop;
    report "CHECK t=" & time'image(now) & " ADD exhaustiv 256 Paare ok";

    op <= "001";
    for i in 0 to 15 loop
      for j in 0 to 15 loop
        a <= std_logic_vector(to_unsigned(i, WIDTH));
        b <= std_logic_vector(to_unsigned(j, WIDTH));
        wait for 10 ns;
        av := to_unsigned(i, WIDTH);
        bv := to_unsigned(j, WIDTH);
        exp := std_logic_vector(av - bv);
        if av < bv then exp_c := '1'; else exp_c := '0'; end if;
        if exp = "0000" then exp_z := '1'; else exp_z := '0'; end if;
        assert result = exp report "REQ R17: SUB exhaust i=" & integer'image(i) & " j=" & integer'image(j) severity error;
        assert carry = exp_c report "REQ R17: SUB exhaust borrow i=" & integer'image(i) & " j=" & integer'image(j) severity error;
        assert zero = exp_z report "REQ R26: SUB exhaust zero i=" & integer'image(i) & " j=" & integer'image(j) severity error;
      end loop;
    end loop;
    report "CHECK t=" & time'image(now) & " SUB exhaustiv 256 Paare ok";

    op <= "010";
    for i in 0 to 15 loop
      for j in 0 to 15 loop
        a <= std_logic_vector(to_unsigned(i, WIDTH));
        b <= std_logic_vector(to_unsigned(j, WIDTH));
        wait for 10 ns;
        exp := std_logic_vector(to_unsigned(i, WIDTH) and to_unsigned(j, WIDTH));
        if exp = "0000" then exp_z := '1'; else exp_z := '0'; end if;
        assert result = exp report "REQ R18: AND exhaust i=" & integer'image(i) & " j=" & integer'image(j) severity error;
        assert carry = '0' report "REQ R18: AND exhaust carry muss 0 sein" severity error;
        assert zero = exp_z report "REQ R26: AND exhaust zero i=" & integer'image(i) & " j=" & integer'image(j) severity error;
      end loop;
    end loop;
    report "CHECK t=" & time'image(now) & " AND exhaustiv ok";

    op <= "011";
    for i in 0 to 15 loop
      for j in 0 to 15 loop
        a <= std_logic_vector(to_unsigned(i, WIDTH));
        b <= std_logic_vector(to_unsigned(j, WIDTH));
        wait for 10 ns;
        exp := std_logic_vector(to_unsigned(i, WIDTH) or to_unsigned(j, WIDTH));
        if exp = "0000" then exp_z := '1'; else exp_z := '0'; end if;
        assert result = exp report "REQ R18: OR exhaust i=" & integer'image(i) & " j=" & integer'image(j) severity error;
        assert carry = '0' report "REQ R18: OR exhaust carry muss 0 sein" severity error;
        assert zero = exp_z report "REQ R26: OR exhaust zero i=" & integer'image(i) & " j=" & integer'image(j) severity error;
      end loop;
    end loop;
    report "CHECK t=" & time'image(now) & " OR exhaustiv ok";

    op <= "100";
    for i in 0 to 15 loop
      for j in 0 to 15 loop
        a <= std_logic_vector(to_unsigned(i, WIDTH));
        b <= std_logic_vector(to_unsigned(j, WIDTH));
        wait for 10 ns;
        exp := std_logic_vector(to_unsigned(i, WIDTH) xor to_unsigned(j, WIDTH));
        if exp = "0000" then exp_z := '1'; else exp_z := '0'; end if;
        assert result = exp report "REQ R18: XOR exhaust i=" & integer'image(i) & " j=" & integer'image(j) severity error;
        assert carry = '0' report "REQ R18: XOR exhaust carry muss 0 sein" severity error;
        assert zero = exp_z report "REQ R26: XOR exhaust zero i=" & integer'image(i) & " j=" & integer'image(j) severity error;
      end loop;
    end loop;
    report "CHECK t=" & time'image(now) & " XOR exhaustiv ok";

    -- SHL/SHR/PASS erschoepfend ueber alle a- bzw. b-Werte
    op <= "101";
    b <= "0000";
    for i in 0 to 15 loop
      a <= std_logic_vector(to_unsigned(i, WIDTH));
      wait for 10 ns;
      exp := std_logic_vector(shift_left(to_unsigned(i, WIDTH), 1));
      if (i / 8) = 1 then exp_c := '1'; else exp_c := '0'; end if;
      if exp = "0000" then exp_z := '1'; else exp_z := '0'; end if;
      assert result = exp report "REQ R19: SHL exhaust i=" & integer'image(i) severity error;
      assert carry = exp_c report "REQ R19: SHL exhaust carry i=" & integer'image(i) severity error;
      assert zero = exp_z report "REQ R26: SHL exhaust zero i=" & integer'image(i) severity error;
    end loop;
    report "CHECK t=" & time'image(now) & " SHL exhaustiv ok";

    op <= "110";
    b <= "0000";
    for i in 0 to 15 loop
      a <= std_logic_vector(to_unsigned(i, WIDTH));
      wait for 10 ns;
      exp := std_logic_vector(shift_right(to_unsigned(i, WIDTH), 1));
      if (i mod 2) = 1 then exp_c := '1'; else exp_c := '0'; end if;
      if exp = "0000" then exp_z := '1'; else exp_z := '0'; end if;
      assert result = exp report "REQ R20: SHR exhaust i=" & integer'image(i) severity error;
      assert carry = exp_c report "REQ R20: SHR exhaust carry i=" & integer'image(i) severity error;
      assert zero = exp_z report "REQ R26: SHR exhaust zero i=" & integer'image(i) severity error;
    end loop;
    report "CHECK t=" & time'image(now) & " SHR exhaustiv ok";

    op <= "111";
    a <= "0000";
    for j in 0 to 15 loop
      b <= std_logic_vector(to_unsigned(j, WIDTH));
      wait for 10 ns;
      exp := std_logic_vector(to_unsigned(j, WIDTH));
      if exp = "0000" then exp_z := '1'; else exp_z := '0'; end if;
      assert result = exp report "REQ R13: PASS exhaust j=" & integer'image(j) severity error;
      assert carry = '0' report "REQ R62: PASS exhaust carry muss 0 sein" severity error;
      assert zero = exp_z report "REQ R26: PASS exhaust zero j=" & integer'image(j) severity error;
    end loop;
    report "CHECK t=" & time'image(now) & " PASS exhaustiv ok";

    report "TB_COMPLETE" severity note;
    stop;
    wait;
  end process stim;

end architecture sim;