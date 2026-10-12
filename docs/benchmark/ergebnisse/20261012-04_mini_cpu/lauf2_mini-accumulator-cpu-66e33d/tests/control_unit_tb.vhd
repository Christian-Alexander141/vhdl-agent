library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
library std;
use std.env.all;

entity control_unit_tb is
end entity control_unit_tb;

architecture sim of control_unit_tb is
  constant CLK_PERIOD : time := 10 ns;

  signal clk        : std_logic := '0';
  signal rst        : std_logic := '1';
  signal go         : std_logic := '0';
  signal rom_data   : std_logic_vector(7 downto 0) := (others => '0');
  signal acc_in     : std_logic_vector(3 downto 0) := (others => '0');
  signal ram_dout   : std_logic_vector(3 downto 0) := (others => '0');
  signal alu_result : std_logic_vector(3 downto 0) := (others => '0');
  signal alu_carry  : std_logic := '0';
  signal alu_zero   : std_logic := '0';
  signal z_in       : std_logic := '0';
  signal c_in       : std_logic := '0';
  signal rom_addr   : std_logic_vector(3 downto 0);
  signal ram_addr   : std_logic_vector(3 downto 0);
  signal ram_din    : std_logic_vector(3 downto 0);
  signal ram_we     : std_logic;
  signal alu_op     : std_logic_vector(2 downto 0);
  signal alu_a      : std_logic_vector(3 downto 0);
  signal alu_b      : std_logic_vector(3 downto 0);
  signal acc_next   : std_logic_vector(3 downto 0);
  signal acc_we     : std_logic;
  signal z_next     : std_logic;
  signal z_we       : std_logic;
  signal c_next     : std_logic;
  signal c_we       : std_logic;
  signal out_we     : std_logic;
  signal pc         : std_logic_vector(3 downto 0);
  signal ir         : std_logic_vector(7 downto 0);
  signal halted     : std_logic;

  signal tb_done : boolean := false;
begin
  clk <= not clk after CLK_PERIOD / 2 when not tb_done else '0';

  dut: entity work.control_unit
    port map (
      clk        => clk,
      rst        => rst,
      go         => go,
      rom_data   => rom_data,
      acc_in     => acc_in,
      ram_dout   => ram_dout,
      alu_result => alu_result,
      alu_carry  => alu_carry,
      alu_zero   => alu_zero,
      z_in       => z_in,
      c_in       => c_in,
      rom_addr   => rom_addr,
      ram_addr   => ram_addr,
      ram_din    => ram_din,
      ram_we     => ram_we,
      alu_op     => alu_op,
      alu_a      => alu_a,
      alu_b      => alu_b,
      acc_next   => acc_next,
      acc_we     => acc_we,
      z_next     => z_next,
      z_we       => z_we,
      c_next     => c_next,
      c_we       => c_we,
      out_we     => out_we,
      pc         => pc,
      ir         => ir,
      halted     => halted
    );

  stim: process
    procedure wait_cycles(n : positive) is
    begin
      for i in 1 to n loop
        wait until rising_edge(clk);
        wait for 1 ns;
      end loop;
    end procedure;

    procedure check_idle_ctrl(msg : string) is
    begin
      assert ram_we = '0' report "REQ R49: " & msg & " ram_we muss 0 sein" severity error;
      assert acc_we = '0' report "REQ R49: " & msg & " acc_we muss 0 sein" severity error;
      assert z_we = '0' report "REQ R49: " & msg & " z_we muss 0 sein" severity error;
      assert c_we = '0' report "REQ R49: " & msg & " c_we muss 0 sein" severity error;
      assert out_we = '0' report "REQ R49: " & msg & " out_we muss 0 sein" severity error;
    end procedure;
  begin
    -- Reset-Sequenz (mind. 2 Zyklen, synchron active-high laut PROMPT)
    rst <= '1';
    go <= '0';
    wait_cycles(3);
    report "CHECK t=" & time'image(now) & " nach Reset-Phase pc=" & to_hstring(pc) & " ir=" & to_hstring(ir) & " halted=" & std_logic'image(halted);
    assert pc = "0000" report "REQ R57: nach Reset PC=0" severity error;
    assert ir = x"00" report "REQ R57: nach Reset IR=0" severity error;
    assert halted = '0' report "REQ R45: nach Reset nicht HALT (WAIT)" severity error;
    assert rom_addr = "0000" report "REQ R48: nach Reset rom_addr=PC=0" severity error;

    rst <= '0';
    wait_cycles(2);
    report "CHECK t=" & time'image(now) & " nach Reset-Ende pc=" & to_hstring(pc) & " ir=" & to_hstring(ir);

    -- WAIT bleibt ohne go (R47)
    assert pc = "0000" report "REQ R47: WAIT bleibt ohne go (PC stabil)" severity error;
    assert ir = x"00" report "REQ R47: WAIT bleibt ohne go (IR stabil)" severity error;
    assert halted = '0' report "REQ R47: WAIT halted=0 ohne go" severity error;
    check_idle_ctrl("WAIT idle");

    ------------------------------------------------------------------
    -- Instr 0: LDI 1 (x11), pc 0->1 (R13, R48, R49, R50, R51)
    ------------------------------------------------------------------
    rom_data <= x"11";
    acc_in <= "0000"; ram_dout <= "0000";
    alu_result <= "0000"; alu_carry <= '0'; alu_zero <= '1';
    z_in <= '0'; c_in <= '0';
    go <= '1';
    wait until rising_edge(clk); wait for 1 ns; -- Kante: WAIT->FETCH
    report "CHECK t=" & time'image(now) & " LDI FETCH-State pc=" & to_hstring(pc) & " ir=" & to_hstring(ir) & " rom_addr=" & to_hstring(rom_addr);
    assert pc = "0000" report "REQ R48: FETCH PC noch alt (0)" severity error;
    assert ir = x"00" report "REQ R49: FETCH IR noch alt" severity error;
    assert halted = '0' report "REQ R45: FETCH nicht HALT" severity error;
    go <= '0';
    wait until rising_edge(clk); wait for 1 ns; -- Kante: FETCH->DECODE
    report "CHECK t=" & time'image(now) & " LDI DECODE pc=" & to_hstring(pc) & " ir=" & to_hstring(ir);
    assert ir = x"11" report "REQ R48: FETCH IR:=ROM[PC]=x11" severity error;
    assert pc = "0001" report "REQ R48: FETCH PC:=PC+1 (0->1)" severity error;
    assert rom_addr = "0001" report "REQ R48: rom_addr folgt PC" severity error;
    check_idle_ctrl("DECODE LDI");
    wait until rising_edge(clk); wait for 1 ns; -- Kante: DECODE->EXECUTE
    report "CHECK t=" & time'image(now) & " LDI EXECUTE pc=" & to_hstring(pc) & " ir=" & to_hstring(ir);
    assert pc = "0001" report "REQ R49: DECODE kein Register (PC stabil)" severity error;
    assert ir = x"11" report "REQ R49: DECODE kein Register (IR stabil)" severity error;
    -- EXECUTE-Kontrollen (kombinatorisch waehrend EXECUTE)
    assert acc_next = "0001" report "REQ R13: LDI ACC:=n=1" severity error;
    assert acc_we = '1' report "REQ R13: LDI acc_we=1" severity error;
    assert z_next = '0' report "REQ R13: LDI Z=0 bei ACC=1" severity error;
    assert z_we = '1' report "REQ R26: LDI Z neu (z_we=1)" severity error;
    assert c_we = '0' report "REQ R26: LDI C un Veraendert (c_we=0)" severity error;
    assert ram_we = '0' report "REQ R50: LDI kein RAM-Schreiben" severity error;
    assert out_we = '0' report "REQ R50: LDI kein OUT" severity error;
    wait until rising_edge(clk); wait for 1 ns; -- Kante: EXECUTE->WAIT
    report "CHECK t=" & time'image(now) & " LDI WAIT pc=" & to_hstring(pc);
    assert pc = "0001" report "REQ R50: LDI EXECUTE->WAIT PC bleibt 1" severity error;
    assert halted = '0' report "REQ R51: nach 3 Folgekanten wieder WAIT" severity error;

    ------------------------------------------------------------------
    -- Instr 1: STA 0 (x30), pc 1->2 (R15)
    ------------------------------------------------------------------
    rom_data <= x"30";
    acc_in <= "0001";
    go <= '1';
    wait until rising_edge(clk); wait for 1 ns;
    go <= '0';
    wait until rising_edge(clk); wait for 1 ns;
    assert ir = x"30" report "REQ R48: STA FETCH IR=x30" severity error;
    assert pc = "0010" report "REQ R48: STA FETCH PC 1->2" severity error;
    assert ram_we = '0' report "REQ R49: STA DECODE ram_we=0" severity error;
    assert ram_we = '0' report "REQ R15: STA erst in EXECUTE schreiben (DECODE 0)" severity error;
    wait until rising_edge(clk); wait for 1 ns;
    assert ir = x"30" report "REQ R49: STA DECODE IR stabil" severity error;
    -- EXECUTE pruefen
    report "CHECK t=" & time'image(now) & " STA EXECUTE ram_we=" & std_logic'image(ram_we) & " ram_addr=" & to_hstring(ram_addr);
    assert ram_we = '1' report "REQ R15: STA RAM[a]:=ACC (ram_we=1)" severity error;
    assert ram_addr = "0000" report "REQ R15: STA ram_addr=Operand 0" severity error;
    assert ram_din = "0001" report "REQ R15: STA ram_din=ACC" severity error;
    assert acc_we = '0' report "REQ R26: STA Flags/ACC unveraendert acc_we=0" severity error;
    assert z_we = '0' report "REQ R26: STA z_we=0" severity error;
    assert c_we = '0' report "REQ R26: STA c_we=0" severity error;
    assert out_we = '0' report "REQ R50: STA out_we=0" severity error;
    wait until rising_edge(clk); wait for 1 ns;
    assert pc = "0010" report "REQ R50: STA EXECUTE->WAIT" severity error;

    ------------------------------------------------------------------
    -- Instr 2: LDA 0 (x20) mit RAM=0101, pc 2->3 (R14)
    ------------------------------------------------------------------
    rom_data <= x"20";
    ram_dout <= "0101";
    acc_in <= "0001";
    go <= '1';
    wait until rising_edge(clk); wait for 1 ns;
    go <= '0';
    wait until rising_edge(clk); wait for 1 ns;
    assert ir = x"20" report "REQ R48: LDA FETCH IR" severity error;
    assert pc = "0011" report "REQ R48: LDA FETCH PC 2->3" severity error;
    wait until rising_edge(clk); wait for 1 ns;
    report "CHECK t=" & time'image(now) & " LDA EXECUTE acc_next=" & to_hstring(acc_next);
    assert acc_next = "0101" report "REQ R14: LDA ACC:=RAM[a]" severity error;
    assert acc_we = '1' report "REQ R14: LDA acc_we=1" severity error;
    assert z_next = '0' report "REQ R14: LDA Z=0 bei 5" severity error;
    assert z_we = '1' report "REQ R26: LDA Z neu" severity error;
    assert c_we = '0' report "REQ R26: LDA C unveraendert" severity error;
    wait until rising_edge(clk); wait for 1 ns;
    assert pc = "0011" report "REQ R50: LDA ->WAIT" severity error;

    ------------------------------------------------------------------
    -- Instr 3: LDI 0 (x10) -> Z=1 (R13, R26)
    ------------------------------------------------------------------
    rom_data <= x"10";
    go <= '1';
    wait until rising_edge(clk); wait for 1 ns;
    go <= '0';
    wait until rising_edge(clk); wait for 1 ns;
    assert ir = x"10" report "REQ R48: LDI0 FETCH" severity error;
    assert pc = "0100" report "REQ R48: LDI0 PC 3->4" severity error;
    wait until rising_edge(clk); wait for 1 ns;
    assert acc_next = "0000" report "REQ R13: LDI0 ACC=0" severity error;
    assert z_next = '1' report "REQ R26: Z=1 wenn ACC=0" severity error;
    assert z_we = '1' report "REQ R26: LDI z_we=1" severity error;
    wait until rising_edge(clk); wait for 1 ns;

    ------------------------------------------------------------------
    -- Instr 4: NOP (x00), pc 4->5 (R12)
    ------------------------------------------------------------------
    rom_data <= x"00";
    go <= '1';
    wait until rising_edge(clk); wait for 1 ns;
    go <= '0';
    wait until rising_edge(clk); wait for 1 ns;
    assert ir = x"00" report "REQ R48: NOP FETCH" severity error;
    assert pc = "0101" report "REQ R48: NOP PC 4->5" severity error;
    wait until rising_edge(clk); wait for 1 ns;
    report "CHECK t=" & time'image(now) & " NOP EXECUTE acc_we=" & std_logic'image(acc_we);
    assert acc_we = '0' report "REQ R12: NOP keine Wirkung acc_we=0" severity error;
    assert z_we = '0' report "REQ R12: NOP z_we=0" severity error;
    assert c_we = '0' report "REQ R12: NOP c_we=0" severity error;
    assert ram_we = '0' report "REQ R12: NOP ram_we=0" severity error;
    assert out_we = '0' report "REQ R12: NOP out_we=0" severity error;
    wait until rising_edge(clk); wait for 1 ns;
    assert pc = "0101" report "REQ R12: NOP PC bleibt 5" severity error;

    ------------------------------------------------------------------
    -- Instr 5: ADD (x41) 3+5=8 ohne Carry (R16)
    ------------------------------------------------------------------
    rom_data <= x"41";
    acc_in <= "0011"; ram_dout <= "0101";
    alu_result <= "1000"; alu_carry <= '0'; alu_zero <= '0';
    go <= '1';
    wait until rising_edge(clk); wait for 1 ns;
    go <= '0';
    wait until rising_edge(clk); wait for 1 ns;
    assert pc = "0110" report "REQ R48: ADD PC 5->6" severity error;
    wait until rising_edge(clk); wait for 1 ns;
    report "CHECK t=" & time'image(now) & " ADD EXECUTE alu_op=" & to_hstring(alu_op) & " acc_next=" & to_hstring(acc_next);
    assert alu_op = "000" report "REQ R16: ADD alu_op=000" severity error;
    assert alu_a = "0011" report "REQ R16: ADD alu_a=ACC" severity error;
    assert alu_b = "0101" report "REQ R16: ADD alu_b=RAM" severity error;
    assert ram_addr = "0001" report "REQ R16: ADD ram_addr=Operand" severity error;
    assert acc_next = "1000" report "REQ R16: ADD ACC=8" severity error;
    assert acc_we = '1' report "REQ R16: ADD acc_we=1" severity error;
    assert c_next = '0' report "REQ R16: ADD C=Uebertrag 0" severity error;
    assert c_we = '1' report "REQ R16: ADD c_we=1" severity error;
    assert z_next = '0' report "REQ R16: ADD Z=0" severity error;
    assert z_we = '1' report "REQ R16: ADD z_we=1" severity error;
    wait until rising_edge(clk); wait for 1 ns;

    ------------------------------------------------------------------
    -- Instr 6: ADD mit Ueberlauf 15+1=0 Carry (R16)
    ------------------------------------------------------------------
    rom_data <= x"41";
    acc_in <= "1111"; ram_dout <= "0001";
    alu_result <= "0000"; alu_carry <= '1'; alu_zero <= '1';
    go <= '1';
    wait until rising_edge(clk); wait for 1 ns;
    go <= '0';
    wait until rising_edge(clk); wait for 1 ns;
    assert pc = "0111" report "REQ R48: ADDov PC 6->7" severity error;
    wait until rising_edge(clk); wait for 1 ns;
    assert acc_next = "0000" report "REQ R16: ADD Ueberlauf ACC=0" severity error;
    assert c_next = '1' report "REQ R16: ADD Ueberlauf C=1" severity error;
    assert z_next = '1' report "REQ R26: ADD Z=1 bei 0" severity error;
    wait until rising_edge(clk); wait for 1 ns;

    ------------------------------------------------------------------
    -- Instr 7: SUB 5-3=2 ohne Borgen (R17)
    ------------------------------------------------------------------
    rom_data <= x"52";
    acc_in <= "0101"; ram_dout <= "0011";
    alu_result <= "0010"; alu_carry <= '0'; alu_zero <= '0';
    go <= '1';
    wait until rising_edge(clk); wait for 1 ns;
    go <= '0';
    wait until rising_edge(clk); wait for 1 ns;
    assert pc = "1000" report "REQ R48: SUB PC 7->8" severity error;
    wait until rising_edge(clk); wait for 1 ns;
    report "CHECK t=" & time'image(now) & " SUB EXECUTE acc_next=" & to_hstring(acc_next) & " c=" & std_logic'image(c_next);
    assert alu_op = "001" report "REQ R17: SUB alu_op=001" severity error;
    assert acc_next = "0010" report "REQ R17: SUB ACC=2" severity error;
    assert c_next = '0' report "REQ R17: SUB C=0 ohne Borgen" severity error;
    assert c_we = '1' report "REQ R17: SUB c_we=1" severity error;
    assert z_next = '0' report "REQ R17: SUB Z=0" severity error;
    wait until rising_edge(clk); wait for 1 ns;

    ------------------------------------------------------------------
    -- Instr 8: SUB mit Borgen 3-5 (R17)
    ------------------------------------------------------------------
    rom_data <= x"52";
    acc_in <= "0011"; ram_dout <= "0101";
    alu_result <= "1110"; alu_carry <= '1'; alu_zero <= '0';
    go <= '1';
    wait until rising_edge(clk); wait for 1 ns;
    go <= '0';
    wait until rising_edge(clk); wait for 1 ns;
    assert pc = "1001" report "REQ R48: SUBb PC 8->9" severity error;
    wait until rising_edge(clk); wait for 1 ns;
    assert acc_next = "1110" report "REQ R17: SUB Borgen ACC mod16" severity error;
    assert c_next = '1' report "REQ R17: SUB C=1 bei Borgen" severity error;
    wait until rising_edge(clk); wait for 1 ns;

    ------------------------------------------------------------------
    -- Instr 9: AND (x63) 1100 & 1010 = 1000 (R18)
    ------------------------------------------------------------------
    rom_data <= x"63";
    acc_in <= "1100"; ram_dout <= "1010";
    alu_result <= "1000"; alu_carry <= '0'; alu_zero <= '0';
    go <= '1';
    wait until rising_edge(clk); wait for 1 ns;
    go <= '0';
    wait until rising_edge(clk); wait for 1 ns;
    assert pc = "1010" report "REQ R48: AND PC 9->10" severity error;
    wait until rising_edge(clk); wait for 1 ns;
    report "CHECK t=" & time'image(now) & " AND EXECUTE alu_op=" & to_hstring(alu_op);
    assert alu_op = "010" report "REQ R18: AND alu_op=010" severity error;
    assert acc_next = "1000" report "REQ R18: AND ACC" severity error;
    assert c_next = '0' report "REQ R18: AND C=0" severity error;
    assert c_we = '1' report "REQ R18: AND c_we=1" severity error;
    assert z_next = '0' report "REQ R18: AND Z neu" severity error;
    wait until rising_edge(clk); wait for 1 ns;

    ------------------------------------------------------------------
    -- Instr 10: OR (x74) (R18)
    ------------------------------------------------------------------
    rom_data <= x"74";
    acc_in <= "1100"; ram_dout <= "1010";
    alu_result <= "1110"; alu_carry <= '0'; alu_zero <= '0';
    go <= '1';
    wait until rising_edge(clk); wait for 1 ns;
    go <= '0';
    wait until rising_edge(clk); wait for 1 ns;
    assert pc = "1011" report "REQ R48: OR PC 10->11" severity error;
    wait until rising_edge(clk); wait for 1 ns;
    assert alu_op = "011" report "REQ R18: OR alu_op=011" severity error;
    assert acc_next = "1110" report "REQ R18: OR ACC" severity error;
    assert c_next = '0' report "REQ R18: OR C=0" severity error;
    wait until rising_edge(clk); wait for 1 ns;

    ------------------------------------------------------------------
    -- Instr 11: XOR (x85) (R18)
    ------------------------------------------------------------------
    rom_data <= x"85";
    acc_in <= "1100"; ram_dout <= "1010";
    alu_result <= "0110"; alu_carry <= '0'; alu_zero <= '0';
    go <= '1';
    wait until rising_edge(clk); wait for 1 ns;
    go <= '0';
    wait until rising_edge(clk); wait for 1 ns;
    assert pc = "1100" report "REQ R48: XOR PC 11->12" severity error;
    wait until rising_edge(clk); wait for 1 ns;
    assert alu_op = "100" report "REQ R18: XOR alu_op=100" severity error;
    assert acc_next = "0110" report "REQ R18: XOR ACC" severity error;
    assert c_next = '0' report "REQ R18: XOR C=0" severity error;
    wait until rising_edge(clk); wait for 1 ns;

    ------------------------------------------------------------------
    -- Instr 12: SHL (x90) 1001 -> 0010 Carry 1 (R19)
    ------------------------------------------------------------------
    rom_data <= x"90";
    acc_in <= "1001";
    alu_result <= "0010"; alu_carry <= '1'; alu_zero <= '0';
    go <= '1';
    wait until rising_edge(clk); wait for 1 ns;
    go <= '0';
    wait until rising_edge(clk); wait for 1 ns;
    assert pc = "1101" report "REQ R48: SHL PC 12->13" severity error;
    wait until rising_edge(clk); wait for 1 ns;
    report "CHECK t=" & time'image(now) & " SHL EXECUTE acc_next=" & to_hstring(acc_next);
    assert alu_op = "101" report "REQ R19: SHL alu_op=101" severity error;
    assert alu_a = "1001" report "REQ R19: SHL alu_a=ACC" severity error;
    assert acc_next = "0010" report "REQ R19: SHL ACC links" severity error;
    assert c_next = '1' report "REQ R19: SHL C=altes Bit3" severity error;
    assert c_we = '1' report "REQ R19: SHL c_we=1" severity error;
    wait until rising_edge(clk); wait for 1 ns;

    ------------------------------------------------------------------
    -- Instr 13: SHR (xA0) 1001 -> 0100 Carry 1 (R20)
    ------------------------------------------------------------------
    rom_data <= x"A0";
    acc_in <= "1001";
    alu_result <= "0100"; alu_carry <= '1'; alu_zero <= '0';
    go <= '1';
    wait until rising_edge(clk); wait for 1 ns;
    go <= '0';
    wait until rising_edge(clk); wait for 1 ns;
    assert pc = "1110" report "REQ R48: SHR PC 13->14" severity error;
    wait until rising_edge(clk); wait for 1 ns;
    report "CHECK t=" & time'image(now) & " SHR EXECUTE acc_next=" & to_hstring(acc_next);
    assert alu_op = "110" report "REQ R20: SHR alu_op=110" severity error;
    assert acc_next = "0100" report "REQ R20: SHR ACC rechts" severity error;
    assert c_next = '1' report "REQ R20: SHR C=altes Bit0" severity error;
    assert c_we = '1' report "REQ R20: SHR c_we=1" severity error;
    wait until rising_edge(clk); wait for 1 ns;

    ------------------------------------------------------------------
    -- Instr 14: JMP 4 (xB4), pc 14 -> 4 (R21, R50 Sprung)
    ------------------------------------------------------------------
    rom_data <= x"B4";
    go <= '1';
    wait until rising_edge(clk); wait for 1 ns;
    go <= '0';
    wait until rising_edge(clk); wait for 1 ns;
    assert ir = x"B4" report "REQ R48: JMP FETCH IR" severity error;
    assert pc = "1111" report "REQ R48: JMP FETCH PC 14->15 (vor Sprung)" severity error;
    wait until rising_edge(clk); wait for 1 ns;
    report "CHECK t=" & time'image(now) & " JMP EXECUTE pc=" & to_hstring(pc);
    assert acc_we = '0' report "REQ R21: JMP kein ACC" severity error;
    assert ram_we = '0' report "REQ R21: JMP kein RAM" severity error;
    wait until rising_edge(clk); wait for 1 ns;
    assert pc = "0100" report "REQ R21: JMP PC:=t=4" severity error;
    assert pc = "0100" report "REQ R50: Sprung ueberschreibt PC+1" severity error;
    assert halted = '0' report "REQ R50: JMP ->WAIT" severity error;

    ------------------------------------------------------------------
    -- JZ genommen (xC9), z=1, pc 4 -> 9 (R22)
    ------------------------------------------------------------------
    rom_data <= x"C9";
    z_in <= '1'; c_in <= '0';
    go <= '1';
    wait until rising_edge(clk); wait for 1 ns;
    go <= '0';
    wait until rising_edge(clk); wait for 1 ns;
    assert pc = "0101" report "REQ R48: JZ FETCH PC 4->5" severity error;
    wait until rising_edge(clk); wait for 1 ns;
    wait until rising_edge(clk); wait for 1 ns;
    report "CHECK t=" & time'image(now) & " JZ taken pc=" & to_hstring(pc);
    assert pc = "1001" report "REQ R22: JZ PC:=t wenn Z=1" severity error;

    ------------------------------------------------------------------
    -- JZ nicht genommen, z=0, pc 9 -> 10 (R22)
    ------------------------------------------------------------------
    rom_data <= x"C9";
    z_in <= '0';
    go <= '1';
    wait until rising_edge(clk); wait for 1 ns;
    go <= '0';
    wait until rising_edge(clk); wait for 1 ns;
    assert pc = "1010" report "REQ R48: JZnt FETCH PC 9->10" severity error;
    wait until rising_edge(clk); wait for 1 ns;
    wait until rising_edge(clk); wait for 1 ns;
    assert pc = "1010" report "REQ R22: JZ kein Sprung wenn Z=0" severity error;

    ------------------------------------------------------------------
    -- JC genommen (xD2), c=1, pc 10 -> 2 (R23)
    ------------------------------------------------------------------
    rom_data <= x"D2";
    c_in <= '1'; z_in <= '0';
    go <= '1';
    wait until rising_edge(clk); wait for 1 ns;
    go <= '0';
    wait until rising_edge(clk); wait for 1 ns;
    assert pc = "1011" report "REQ R48: JC FETCH PC 10->11" severity error;
    wait until rising_edge(clk); wait for 1 ns;
    wait until rising_edge(clk); wait for 1 ns;
    report "CHECK t=" & time'image(now) & " JC taken pc=" & to_hstring(pc);
    assert pc = "0010" report "REQ R23: JC PC:=t wenn C=1" severity error;

    ------------------------------------------------------------------
    -- JC nicht genommen, c=0, pc 2 -> 3 (R23)
    ------------------------------------------------------------------
    rom_data <= x"D2";
    c_in <= '0';
    go <= '1';
    wait until rising_edge(clk); wait for 1 ns;
    go <= '0';
    wait until rising_edge(clk); wait for 1 ns;
    assert pc = "0011" report "REQ R48: JCnt FETCH PC 2->3" severity error;
    wait until rising_edge(clk); wait for 1 ns;
    wait until rising_edge(clk); wait for 1 ns;
    assert pc = "0011" report "REQ R23: JC kein Sprung wenn C=0" severity error;

    ------------------------------------------------------------------
    -- OUT (xE0), pc 3 -> 4 (R24)
    ------------------------------------------------------------------
    rom_data <= x"E0";
    acc_in <= "1101";
    go <= '1';
    wait until rising_edge(clk); wait for 1 ns;
    go <= '0';
    wait until rising_edge(clk); wait for 1 ns;
    assert pc = "0100" report "REQ R48: OUT FETCH PC 3->4" severity error;
    wait until rising_edge(clk); wait for 1 ns;
    report "CHECK t=" & time'image(now) & " OUT EXECUTE out_we=" & std_logic'image(out_we);
    assert out_we = '1' report "REQ R24: OUT OUT:=ACC (out_we=1)" severity error;
    assert acc_we = '0' report "REQ R24: OUT kein ACC-Schreiben" severity error;
    wait until rising_edge(clk); wait for 1 ns;
    assert pc = "0100" report "REQ R50: OUT ->WAIT" severity error;

    ------------------------------------------------------------------
    -- go wird in FETCH/DECODE/EXECUTE ignoriert (R47)
    ------------------------------------------------------------------
    rom_data <= x"00"; -- NOP, pc 4 -> 5
    go <= '1';
    wait until rising_edge(clk); wait for 1 ns; -- WAIT->FETCH
    go <= '1'; -- go bleibt 1 in FETCH
    wait until rising_edge(clk); wait for 1 ns; -- FETCH->DECODE
    assert ir = x"00" report "REQ R47: go in FETCH ignoriert (genau ein FETCH)" severity error;
    assert pc = "0101" report "REQ R47: go in FETCH kein doppelter Schritt" severity error;
    go <= '1'; -- go bleibt 1 in DECODE
    wait until rising_edge(clk); wait for 1 ns; -- DECODE->EXECUTE
    assert pc = "0101" report "REQ R47: go in DECODE ignoriert" severity error;
    go <= '1';
    wait until rising_edge(clk); wait for 1 ns; -- EXECUTE->WAIT (nur ein Befehl)
    assert pc = "0101" report "REQ R47: go in EXECUTE ignoriert (nur ein Befehl, PC=5)" severity error;
    assert ir = x"00" report "REQ R47: nur ein NOP ausgefuehrt" severity error;
    go <= '0';
    wait_cycles(2);
    assert pc = "0101" report "REQ R51: ein Befehl = genau 3 Folgekanten (PC stabil in WAIT)" severity error;

    ------------------------------------------------------------------
    -- PC-Ueberlauf mod 16: JMP 15, dann NOP bei 15 -> 0 (R48)
    ------------------------------------------------------------------
    rom_data <= x"BF"; -- JMP 15, pc 5 -> 15
    go <= '1';
    wait until rising_edge(clk); wait for 1 ns;
    go <= '0';
    wait until rising_edge(clk); wait for 1 ns;
    wait until rising_edge(clk); wait for 1 ns;
    wait until rising_edge(clk); wait for 1 ns;
    assert pc = "1111" report "REQ R21: JMP 15 PC=15" severity error;
    rom_data <= x"00"; -- NOP bei 15
    go <= '1';
    wait until rising_edge(clk); wait for 1 ns;
    go <= '0';
    wait until rising_edge(clk); wait for 1 ns;
    assert pc = "0000" report "REQ R48: FETCH PC:=PC+1 mod 16 (15->0)" severity error;
    wait until rising_edge(clk); wait for 1 ns;
    wait until rising_edge(clk); wait for 1 ns;
    assert pc = "0000" report "REQ R48: Ueberlauf PC bleibt 0 nach EXECUTE" severity error;

    ------------------------------------------------------------------
    -- Reset mitten im Programm (R57)
    ------------------------------------------------------------------
    rst <= '1';
    wait_cycles(2);
    report "CHECK t=" & time'image(now) & " Reset-mitte pc=" & to_hstring(pc) & " ir=" & to_hstring(ir);
    assert pc = "0000" report "REQ R57: Reset-mitte PC=0" severity error;
    assert ir = x"00" report "REQ R57: Reset-mitte IR=0" severity error;
    assert halted = '0' report "REQ R57: Reset-mitte Steuerwerk nach WAIT" severity error;
    rst <= '0';
    wait_cycles(1);

    ------------------------------------------------------------------
    -- HLT (xF0), pc 0 -> 1, dann HALT (R25, R45)
    ------------------------------------------------------------------
    rom_data <= x"F0";
    go <= '1';
    wait until rising_edge(clk); wait for 1 ns;
    go <= '0';
    wait until rising_edge(clk); wait for 1 ns;
    assert ir = x"F0" report "REQ R48: HLT FETCH IR" severity error;
    assert pc = "0001" report "REQ R48: HLT FETCH PC 0->1" severity error;
    wait until rising_edge(clk); wait for 1 ns;
    wait until rising_edge(clk); wait for 1 ns;
    report "CHECK t=" & time'image(now) & " HALT halted=" & std_logic'image(halted) & " pc=" & to_hstring(pc);
    assert halted = '1' report "REQ R25: HLT CPU haelt an (halted=1)" severity error;
    assert halted = '1' report "REQ R45: HALT-Zustand erreicht" severity error;
    -- HALT bleibt bis Reset, auch mit go=1 (R25, R47)
    go <= '1';
    wait_cycles(3);
    go <= '0';
    assert halted = '1' report "REQ R25: HALT bleibt trotz go" severity error;
    assert pc = "0001" report "REQ R25: HALT PC eingefroren" severity error;
    assert ir = x"F0" report "REQ R25: HALT IR eingefroren" severity error;
    -- Reset aus HALT -> WAIT (R57, R45)
    rst <= '1';
    wait_cycles(2);
    assert pc = "0000" report "REQ R57: Reset aus HALT PC=0" severity error;
    assert halted = '0' report "REQ R45: nach Reset WAIT (halted=0)" severity error;
    rst <= '0';
    wait_cycles(1);

    report "CHECK t=" & time'image(now) & " final pc=" & to_hstring(pc) & " halted=" & std_logic'image(halted);
    tb_done <= true;
    report "TB_COMPLETE" severity note;
    std.env.stop;
    wait;
  end process stim;

end architecture sim;