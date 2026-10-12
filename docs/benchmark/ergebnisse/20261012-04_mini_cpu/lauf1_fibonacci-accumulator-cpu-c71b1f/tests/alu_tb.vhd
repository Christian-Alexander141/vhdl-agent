library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.env.all;

entity alu_tb is
end entity alu_tb;

architecture sim of alu_tb is
  constant WIDTH : positive := 4;

  signal a      : std_logic_vector(WIDTH - 1 downto 0) := (others => '0');
  signal b      : std_logic_vector(WIDTH - 1 downto 0) := (others => '0');
  signal op     : std_logic_vector(2 downto 0) := (others => '0');
  signal result : std_logic_vector(WIDTH - 1 downto 0);
  signal carry  : std_logic;
  signal zero   : std_logic;

  signal tb_done : boolean := false;
begin

  -- DUT mit Default-Generic WIDTH=4 (kein generic map: prueft Standardwert)
  dut: entity work.alu
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
    -- R75: WIDTH-Default 4 -> Busbreite 4 Bit
    assert result'length = 4 report "REQ R75: result-Breite muss 4 sein bei Default-WIDTH" severity error;
    assert a'length = 4 report "REQ R75: a-Breite muss 4 sein bei Default-WIDTH" severity error;
    report "CHECK t=" & time'image(now) & " widths a=" & integer'image(a'length) & " result=" & integer'image(result'length);

    -- R76: Op-Mapping Grundpruefung (ADD-Code 000)
    a <= "0001"; b <= "0001"; op <= "000"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " op=" & to_string(op) & " a=" & to_string(a) & " b=" & to_string(b) & " result=" & to_string(result) & " c=" & std_logic'image(carry) & " z=" & std_logic'image(zero);
    assert result = "0010" and carry = '0' and zero = '0' report "REQ R76: op 000 muss ADD sein: 1+1=2 C=0 Z=0" severity error;

    -- R17: LDI n -> PASS b (ACC := n), C unveraendert (ALU liefert C=0, Control updated C nicht)
    op <= "111"; a <= "0000"; b <= "0001"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " LDI1 op=" & to_string(op) & " b=" & to_string(b) & " result=" & to_string(result);
    assert result = "0001" report "REQ R17: LDI 1 muss ACC=0001 liefern (PASS b)" severity error;
    assert carry = '0' report "REQ R17: LDI/PASS carry muss 0 sein" severity error;
    assert zero = '0' report "REQ R17: LDI 1 darf Z nicht setzen (result/=0)" severity error;

    op <= "111"; a <= "1111"; b <= "0000"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " LDI0 result=" & to_string(result) & " z=" & std_logic'image(zero);
    assert result = "0000" report "REQ R17: LDI 0 muss ACC=0000 liefern" severity error;
    assert zero = '1' report "REQ R30: LDI 0 muss Z=1 setzen (result=0)" severity error;
    assert carry = '0' report "REQ R31: LDI/PASS carry muss 0 sein (C bleibt unveraendert)" severity error;

    op <= "111"; a <= "0101"; b <= "1111"; wait for 10 ns;
    assert result = "1111" report "REQ R17: LDI 15 muss ACC=1111 liefern" severity error;
    assert zero = '0' report "REQ R30: LDI 15 darf Z nicht setzen" severity error;

    -- R18: LDA a -> PASS b (ACC := RAM[a])
    op <= "111"; a <= "0000"; b <= "0011"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " LDA3 result=" & to_string(result);
    assert result = "0011" report "REQ R18: LDA muss RAM-Wert 3 nach ACC laden (PASS b)" severity error;
    assert carry = '0' report "REQ R18: LDA/PASS carry muss 0 sein" severity error;
    assert zero = '0' report "REQ R18: LDA 3 darf Z nicht setzen" severity error;

    op <= "111"; a <= "1010"; b <= "0000"; wait for 10 ns;
    assert result = "0000" report "REQ R18: LDA 0 muss ACC=0 liefern" severity error;
    assert zero = '1' report "REQ R30: LDA 0 muss Z=1 setzen" severity error;

    -- R20: ADD (ACC + RAM) mod 16, C = Uebertrag aus Bit 3
    op <= "000"; a <= "0001"; b <= "0001"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " ADD1+1 result=" & to_string(result) & " c=" & std_logic'image(carry);
    assert result = "0010" report "REQ R20: ADD 1+1 muss 2 ergeben" severity error;
    assert carry = '0' report "REQ R20: ADD 1+1 darf keinen Uebertrag haben" severity error;
    assert zero = '0' report "REQ R30: ADD 1+1 darf Z nicht setzen" severity error;

    op <= "000"; a <= "0101"; b <= "1000"; wait for 10 ns;  -- 5 + 8 = 13 (Fibonacci)
    report "CHECK t=" & time'image(now) & " ADD5+8 result=" & to_string(result);
    assert result = "1101" report "REQ R20: ADD 5+8 muss 13 ergeben" severity error;
    assert carry = '0' report "REQ R20: ADD 5+8 darf keinen Uebertrag haben" severity error;
    assert zero = '0' report "REQ R30: ADD 5+8 darf Z nicht setzen" severity error;

    op <= "000"; a <= "1000"; b <= "1101"; wait for 10 ns;  -- 8 + 13 = 21 -> 5, C=1 (Fibonacci-Ueberlauf)
    report "CHECK t=" & time'image(now) & " ADD8+13 result=" & to_string(result) & " c=" & std_logic'image(carry);
    assert result = "0101" report "REQ R20: ADD 8+13 muss (21 mod 16)=5 ergeben" severity error;
    assert carry = '1' report "REQ R20: ADD 8+13 muss Uebertrag C=1 liefern" severity error;
    assert zero = '0' report "REQ R30: ADD 8+13 darf Z nicht setzen" severity error;

    op <= "000"; a <= "1111"; b <= "0001"; wait for 10 ns;  -- 15 + 1 = 0, C=1
    assert result = "0000" report "REQ R20: ADD 15+1 muss (16 mod 16)=0 ergeben" severity error;
    assert carry = '1' report "REQ R20: ADD 15+1 muss Uebertrag C=1 liefern" severity error;
    assert zero = '1' report "REQ R30: ADD 15+1 muss Z=1 setzen (result=0)" severity error;

    op <= "000"; a <= "0000"; b <= "0000"; wait for 10 ns;
    assert result = "0000" report "REQ R20: ADD 0+0 muss 0 ergeben" severity error;
    assert carry = '0' report "REQ R20: ADD 0+0 darf keinen Uebertrag haben" severity error;
    assert zero = '1' report "REQ R30: ADD 0+0 muss Z=1 setzen" severity error;

    -- R21: SUB (ACC - RAM) mod 16, C = Borrow (1 wenn a < b)
    op <= "001"; a <= "0101"; b <= "0011"; wait for 10 ns;  -- 5 - 3 = 2
    report "CHECK t=" & time'image(now) & " SUB5-3 result=" & to_string(result) & " c=" & std_logic'image(carry);
    assert result = "0010" report "REQ R21: SUB 5-3 muss 2 ergeben" severity error;
    assert carry = '0' report "REQ R21: SUB 5-3 darf kein Borrow haben (5>=3)" severity error;
    assert zero = '0' report "REQ R30: SUB 5-3 darf Z nicht setzen" severity error;

    op <= "001"; a <= "0011"; b <= "0101"; wait for 10 ns;  -- 3 - 5 = 14 mod 16, Borrow
    report "CHECK t=" & time'image(now) & " SUB3-5 result=" & to_string(result) & " c=" & std_logic'image(carry);
    assert result = "1110" report "REQ R21: SUB 3-5 muss (mod 16)=14 ergeben" severity error;
    assert carry = '1' report "REQ R21: SUB 3-5 muss Borrow C=1 liefern (3<5)" severity error;
    assert zero = '0' report "REQ R30: SUB 3-5 darf Z nicht setzen" severity error;

    op <= "001"; a <= "0000"; b <= "0000"; wait for 10 ns;
    assert result = "0000" report "REQ R21: SUB 0-0 muss 0 ergeben" severity error;
    assert carry = '0' report "REQ R21: SUB 0-0 darf kein Borrow haben" severity error;
    assert zero = '1' report "REQ R30: SUB 0-0 muss Z=1 setzen" severity error;

    op <= "001"; a <= "0000"; b <= "0001"; wait for 10 ns;  -- 0 - 1 = 15, Borrow
    assert result = "1111" report "REQ R21: SUB 0-1 muss (mod 16)=15 ergeben" severity error;
    assert carry = '1' report "REQ R21: SUB 0-1 muss Borrow C=1 liefern" severity error;
    assert zero = '0' report "REQ R30: SUB 0-1 darf Z nicht setzen" severity error;

    op <= "001"; a <= "0101"; b <= "0101"; wait for 10 ns;  -- 5 - 5 = 0
    assert result = "0000" report "REQ R21: SUB 5-5 muss 0 ergeben" severity error;
    assert carry = '0' report "REQ R21: SUB 5-5 darf kein Borrow haben" severity error;
    assert zero = '1' report "REQ R30: SUB 5-5 muss Z=1 setzen" severity error;

    -- R22: AND / OR / XOR, C := 0
    op <= "010"; a <= "1100"; b <= "1010"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " AND result=" & to_string(result);
    assert result = "1000" report "REQ R22: AND 1100/1010 muss 1000 ergeben" severity error;
    assert carry = '0' report "REQ R22: AND carry muss 0 sein" severity error;
    assert zero = '0' report "REQ R30: AND 1100/1010 darf Z nicht setzen" severity error;

    op <= "010"; a <= "0000"; b <= "1111"; wait for 10 ns;
    assert result = "0000" report "REQ R22: AND 0/15 muss 0 ergeben" severity error;
    assert carry = '0' report "REQ R31: AND carry muss 0 sein" severity error;
    assert zero = '1' report "REQ R30: AND 0/15 muss Z=1 setzen" severity error;

    op <= "010"; a <= "1111"; b <= "1111"; wait for 10 ns;
    assert result = "1111" report "REQ R22: AND 15/15 muss 15 ergeben" severity error;
    assert carry = '0' report "REQ R22: AND 15/15 carry muss 0 sein" severity error;

    op <= "011"; a <= "1100"; b <= "1010"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " OR result=" & to_string(result);
    assert result = "1110" report "REQ R22: OR 1100/1010 muss 1110 ergeben" severity error;
    assert carry = '0' report "REQ R22: OR carry muss 0 sein" severity error;
    assert zero = '0' report "REQ R30: OR 1100/1010 darf Z nicht setzen" severity error;

    op <= "011"; a <= "0000"; b <= "0000"; wait for 10 ns;
    assert result = "0000" report "REQ R22: OR 0/0 muss 0 ergeben" severity error;
    assert carry = '0' report "REQ R31: OR carry muss 0 sein" severity error;
    assert zero = '1' report "REQ R30: OR 0/0 muss Z=1 setzen" severity error;

    op <= "100"; a <= "1100"; b <= "1010"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " XOR result=" & to_string(result);
    assert result = "0110" report "REQ R22: XOR 1100/1010 muss 0110 ergeben" severity error;
    assert carry = '0' report "REQ R22: XOR carry muss 0 sein" severity error;
    assert zero = '0' report "REQ R30: XOR 1100/1010 darf Z nicht setzen" severity error;

    op <= "100"; a <= "0101"; b <= "0101"; wait for 10 ns;
    assert result = "0000" report "REQ R22: XOR 5/5 muss 0 ergeben" severity error;
    assert carry = '0' report "REQ R31: XOR carry muss 0 sein" severity error;
    assert zero = '1' report "REQ R30: XOR 5/5 muss Z=1 setzen" severity error;

    -- R23: SHL von a, C = altes Bit 3
    op <= "101"; a <= "0001"; b <= "0000"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " SHL0001 result=" & to_string(result) & " c=" & std_logic'image(carry);
    assert result = "0010" report "REQ R23: SHL 0001 muss 0010 ergeben" severity error;
    assert carry = '0' report "REQ R23: SHL 0001 muss C=0 liefern (altes Bit3=0)" severity error;
    assert zero = '0' report "REQ R30: SHL 0001 darf Z nicht setzen" severity error;

    op <= "101"; a <= "1001"; b <= "1111"; wait for 10 ns;  -- b muss ignoriert werden
    report "CHECK t=" & time'image(now) & " SHL1001 result=" & to_string(result) & " c=" & std_logic'image(carry);
    assert result = "0010" report "REQ R23: SHL 1001 muss 0010 ergeben (b ignoriert)" severity error;
    assert carry = '1' report "REQ R23: SHL 1001 muss C=1 liefern (altes Bit3=1)" severity error;

    op <= "101"; a <= "0000"; b <= "0000"; wait for 10 ns;
    assert result = "0000" report "REQ R23: SHL 0000 muss 0000 ergeben" severity error;
    assert carry = '0' report "REQ R23: SHL 0000 muss C=0 liefern" severity error;
    assert zero = '1' report "REQ R30: SHL 0000 muss Z=1 setzen" severity error;

    op <= "101"; a <= "1000"; b <= "0000"; wait for 10 ns;
    assert result = "0000" report "REQ R23: SHL 1000 muss 0000 ergeben" severity error;
    assert carry = '1' report "REQ R23: SHL 1000 muss C=1 liefern" severity error;
    assert zero = '1' report "REQ R77: SHL 1000 muss Z=1 setzen (result=0)" severity error;

    -- R24: SHR von a, C = altes Bit 0
    op <= "110"; a <= "0010"; b <= "0000"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " SHR0010 result=" & to_string(result) & " c=" & std_logic'image(carry);
    assert result = "0001" report "REQ R24: SHR 0010 muss 0001 ergeben" severity error;
    assert carry = '0' report "REQ R24: SHR 0010 muss C=0 liefern (altes Bit0=0)" severity error;
    assert zero = '0' report "REQ R30: SHR 0010 darf Z nicht setzen" severity error;

    op <= "110"; a <= "0011"; b <= "1111"; wait for 10 ns;  -- b muss ignoriert werden
    report "CHECK t=" & time'image(now) & " SHR0011 result=" & to_string(result) & " c=" & std_logic'image(carry);
    assert result = "0001" report "REQ R24: SHR 0011 muss 0001 ergeben (b ignoriert)" severity error;
    assert carry = '1' report "REQ R24: SHR 0011 muss C=1 liefern (altes Bit0=1)" severity error;

    op <= "110"; a <= "0000"; b <= "0000"; wait for 10 ns;
    assert result = "0000" report "REQ R24: SHR 0000 muss 0000 ergeben" severity error;
    assert carry = '0' report "REQ R24: SHR 0000 muss C=0 liefern" severity error;
    assert zero = '1' report "REQ R30: SHR 0000 muss Z=1 setzen" severity error;

    op <= "110"; a <= "0001"; b <= "0000"; wait for 10 ns;
    assert result = "0000" report "REQ R24: SHR 0001 muss 0000 ergeben" severity error;
    assert carry = '1' report "REQ R24: SHR 0001 muss C=1 liefern" severity error;
    assert zero = '1' report "REQ R77: SHR 0001 muss Z=1 setzen (result=0)" severity error;

    -- R77 Nachpruefung: PASS carry 0, zero aus result
    op <= "111"; a <= "1101"; b <= "1000"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " PASS result=" & to_string(result) & " c=" & std_logic'image(carry) & " z=" & std_logic'image(zero);
    assert result = "1000" report "REQ R77: PASS muss b=1000 durchreichen (a ignoriert)" severity error;
    assert carry = '0' report "REQ R77: PASS carry muss 0 sein" severity error;
    assert zero = '0' report "REQ R77: PASS 8 darf Z nicht setzen" severity error;

    op <= "111"; a <= "1111"; b <= "0000"; wait for 10 ns;
    assert carry = '0' report "REQ R77: PASS 0 carry muss 0 sein" severity error;
    assert zero = '1' report "REQ R77: PASS 0 muss Z=1 setzen (result=0)" severity error;

    -- R76 Vollstaendigkeit: alle 8 Opcodes mit festen Gold-Vektoren
    op <= "000"; a <= "0010"; b <= "0011"; wait for 10 ns;
    assert result = "0101" report "REQ R76: ADD 2+3 muss 5 sein" severity error;
    op <= "001"; a <= "0010"; b <= "0011"; wait for 10 ns;
    assert result = "1111" and carry = '1' report "REQ R76: SUB 2-3 muss 15 mit Borrow sein" severity error;
    op <= "010"; a <= "0010"; b <= "0011"; wait for 10 ns;
    assert result = "0010" report "REQ R76: AND 2/3 muss 2 sein" severity error;
    op <= "011"; a <= "0010"; b <= "0011"; wait for 10 ns;
    assert result = "0011" report "REQ R76: OR 2/3 muss 3 sein" severity error;
    op <= "100"; a <= "0010"; b <= "0011"; wait for 10 ns;
    assert result = "0001" report "REQ R76: XOR 2/3 muss 1 sein" severity error;
    op <= "101"; a <= "0010"; b <= "0011"; wait for 10 ns;
    assert result = "0100" report "REQ R76: SHL 0010 muss 0100 sein" severity error;
    op <= "110"; a <= "0010"; b <= "0011"; wait for 10 ns;
    assert result = "0001" and carry = '0' report "REQ R76: SHR 0010 muss 0001 C=0 sein" severity error;
    op <= "111"; a <= "0010"; b <= "0011"; wait for 10 ns;
    assert result = "0011" and carry = '0' report "REQ R76: PASS muss b=0011 liefern" severity error;
    report "CHECK t=" & time'image(now) & " opcode-sweep done result=" & to_string(result);

    tb_done <= true;
    assert false report "TB_COMPLETE" severity note;
    std.env.stop;
    wait;
  end process stim;

end architecture sim;