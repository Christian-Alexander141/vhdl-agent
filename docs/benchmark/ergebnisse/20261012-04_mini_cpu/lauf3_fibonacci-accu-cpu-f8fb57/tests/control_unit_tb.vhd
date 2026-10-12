library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.env.all;

entity control_unit_tb is
end entity control_unit_tb;

architecture sim of control_unit_tb is
  constant CLK_PERIOD : time := 10 ns;

  signal clk       : std_logic := '0';
  signal rst       : std_logic := '1';
  signal go        : std_logic := '0';
  signal rom_data  : std_logic_vector(7 downto 0) := (others => '0');
  signal z_flag    : std_logic := '0';
  signal c_flag    : std_logic := '0';
  signal acc_en    : std_logic;
  signal alu_b_sel : std_logic;
  signal alu_op    : std_logic_vector(2 downto 0);
  signal c_en      : std_logic;
  signal halted    : std_logic;
  signal ir        : std_logic_vector(7 downto 0);
  signal out_en    : std_logic;
  signal pc        : std_logic_vector(3 downto 0);
  signal ram_addr  : std_logic_vector(3 downto 0);
  signal ram_we    : std_logic;
  signal z_en      : std_logic;

  signal tb_done : boolean := false;
begin

  clk <= not clk after CLK_PERIOD / 2 when not tb_done else '0';

  dut: entity work.control_unit
    port map (
      clk       => clk,
      rst       => rst,
      go        => go,
      rom_data  => rom_data,
      z_flag    => z_flag,
      c_flag    => c_flag,
      acc_en    => acc_en,
      alu_b_sel => alu_b_sel,
      alu_op    => alu_op,
      c_en      => c_en,
      halted    => halted,
      ir        => ir,
      out_en    => out_en,
      pc        => pc,
      ram_addr  => ram_addr,
      ram_we    => ram_we,
      z_en      => z_en
    );

  stim: process
    procedure wait_cycles(n : positive) is
    begin
      for i in 1 to n loop
        wait until rising_edge(clk);
      end loop;
    end procedure;
  begin
    -- Reset-Sequenz: mind. 2 Zyklen rst='1'
    rst <= '1';
    go <= '0';
    rom_data <= (others => '0');
    z_flag <= '0';
    c_flag <= '0';
    wait_cycles(2);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " nach Reset pc=" & to_string(pc) & " ir=" & to_string(ir) & " halted=" & to_string(halted) severity note;
    assert pc = "0000" report "REQ R71: Reset muss PC=0 setzen" severity error;
    assert ir = "00000000" report "REQ R71: Reset muss IR=0 setzen" severity error;
    assert halted = '0' report "REQ R56: nach Reset muss Steuerwerk in WAIT sein (halted=0)" severity error;
    assert halted = '0' report "REQ R62: nach Reset nicht in HALT" severity error;
    assert acc_en = '0' report "REQ R71: Reset muss acc_en=0 liefern (WAIT)" severity error;
    assert ram_we = '0' report "REQ R71: Reset muss ram_we=0 liefern" severity error;
    assert out_en = '0' report "REQ R71: Reset muss out_en=0 liefern" severity error;
    assert z_en = '0' report "REQ R71: Reset muss z_en=0 liefern" severity error;
    assert c_en = '0' report "REQ R71: Reset muss c_en=0 liefern" severity error;
    assert ram_addr = "0000" report "REQ R71: Reset ram_addr=IR(3..0)=0" severity error;

    rst <= '0';
    wait_cycles(2);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " WAIT ohne go pc=" & to_string(pc) & " halted=" & to_string(halted) severity note;
    assert pc = "0000" report "REQ R58: WAIT bleibt ohne go=1 (PC unveraendert)" severity error;
    assert halted = '0' report "REQ R58: WAIT ohne go bleibt in WAIT" severity error;
    assert acc_en = '0' and ram_we = '0' and out_en = '0' report "REQ R58: WAIT ohne go keine Steuersignale" severity error;

    -- LDI x"11" mit vollem Timing-Nachweis (E0=go, E1=FETCH, E2=DECODE->EXEC, E3=EXEC->WAIT)
    rom_data <= x"11";
    z_flag <= '0';
    c_flag <= '0';
    go <= '1';
    wait until rising_edge(clk); -- E0: WAIT -> FETCH
    go <= '0';
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " nach go-E0 (FETCH) acc_en=" & to_string(acc_en) severity note;
    assert halted = '0' report "REQ R57: go=1 in WAIT verlaesst WAIT (nicht HALT)" severity error;
    assert acc_en = '0' and ram_we = '0' and out_en = '0' report "REQ R63: direkt nach go (FETCH) noch keine EXECUTE-Signale" severity error;

    wait until rising_edge(clk); -- E1: FETCH-Aktion -> DECODE
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " nach E1 FETCH pc=" & to_string(pc) & " ir=" & to_string(ir) severity note;
    assert ir = x"11" report "REQ R59: FETCH muss IR:=ROM[PC] laden (x11)" severity error;
    assert pc = "0001" report "REQ R59: FETCH muss PC:=PC+1 (0->1)" severity error;
    assert ram_addr = "0001" report "REQ R59: ram_addr muss Operanden IR(3..0) zeigen" severity error;
    assert ir = x"11" report "REQ R60: DECODE IR stabil (Befehl dekodieren, Register unveraendert)" severity error;
    assert pc = "0001" report "REQ R60: DECODE PC stabil" severity error;
    assert acc_en = '0' and ram_we = '0' and out_en = '0' report "REQ R63: in DECODE noch keine EXECUTE-Signale (2. Flanke nach go)" severity error;

    wait until rising_edge(clk); -- E2: DECODE -> EXECUTE
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " in EXECUTE LDI acc_en=" & to_string(acc_en) & " op=" & to_string(alu_op) & " bsel=" & to_string(alu_b_sel) & " z_en=" & to_string(z_en) & " c_en=" & to_string(c_en) severity note;
    assert acc_en = '1' report "REQ R19: LDI muss acc_en=1 liefern" severity error;
    assert z_en = '1' report "REQ R19: LDI muss z_en=1 liefern (Z neu)" severity error;
    assert c_en = '0' report "REQ R19: LDI laesst C unveraendert (c_en=0)" severity error;
    assert alu_op = "111" report "REQ R19: LDI muss alu_op=PASS(111) liefern" severity error;
    assert alu_b_sel = '1' report "REQ R19: LDI muss alu_b_sel=1 (immediate) liefern" severity error;
    assert ram_we = '0' report "REQ R61: LDI schreibt nicht in RAM" severity error;
    assert out_en = '0' report "REQ R61: LDI setzt out_en=0" severity error;

    wait until rising_edge(clk); -- E3: EXECUTE -> WAIT
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " nach E3 EXECUTE pc=" & to_string(pc) & " halted=" & to_string(halted) severity note;
    assert pc = "0001" report "REQ R61: EXECUTE LDI ohne Sprung behaelt PC+1 aus FETCH" severity error;
    assert halted = '0' report "REQ R61: EXECUTE nicht-HLT geht nach WAIT" severity error;
    assert acc_en = '0' and ram_we = '0' and out_en = '0' and z_en = '0' and c_en = '0' report "REQ R61: nach EXECUTE zurueck in WAIT (Signale 0)" severity error;
    assert halted = '0' report "REQ R63: ein Befehl braucht genau 3 weitere Flanken (FETCH,DECODE,EXECUTE) und endet in WAIT" severity error;

    wait_cycles(2);
    wait for 1 ns;
    assert pc = "0001" report "REQ R58: WAIT ohne go bleibt stehen (PC=1)" severity error;

    -- Reset vor Sweep (PC wieder 0)
    rst <= '1';
    wait_cycles(2);
    wait for 1 ns;
    assert pc = "0000" report "REQ R71: Reset mitten im Programm setzt PC=0" severity error;
    assert ir = "00000000" report "REQ R71: Reset setzt IR=0" severity error;
    rst <= '0';
    wait_cycles(1);

    -- NOP x"00" (R18): PC 0 -> 1
    rom_data <= x"00";
    z_flag <= '0'; c_flag <= '0';
    go <= '1';
    wait until rising_edge(clk); -- E0
    go <= '0';
    wait until rising_edge(clk); -- E1 -> DECODE
    wait for 1 ns;
    assert ir = x"00" report "REQ R59: FETCH NOP IR=x00" severity error;
    assert pc = "0001" report "REQ R59: FETCH NOP PC=1" severity error;
    assert ir = x"00" report "REQ R60: DECODE NOP IR stabil" severity error;
    assert pc = "0001" report "REQ R60: DECODE NOP PC stabil" severity error;
    wait until rising_edge(clk); -- E2 -> EXECUTE
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " NOP EXECUTE acc_en=" & to_string(acc_en) & " ram_we=" & to_string(ram_we) severity note;
    assert acc_en = '0' report "REQ R18: NOP acc_en=0 in EXECUTE" severity error;
    assert ram_we = '0' report "REQ R18: NOP ram_we=0" severity error;
    assert out_en = '0' report "REQ R18: NOP out_en=0" severity error;
    assert z_en = '0' report "REQ R18: NOP z_en=0 (Flags unveraendert)" severity error;
    assert c_en = '0' report "REQ R18: NOP c_en=0" severity error;
    wait until rising_edge(clk); -- E3 -> WAIT
    wait for 1 ns;
    assert pc = "0001" report "REQ R61: NOP geht nach WAIT mit PC=1" severity error;
    assert halted = '0' report "REQ R56: NOP fuehrt nicht nach HALT" severity error;

    -- LDA x"23" (R20): PC 1 -> 2
    rom_data <= x"23";
    go <= '1';
    wait until rising_edge(clk); -- E0
    go <= '0';
    wait until rising_edge(clk); -- E1
    wait for 1 ns;
    assert ir = x"23" report "REQ R59: FETCH LDA IR=x23" severity error;
    assert pc = "0010" report "REQ R59: FETCH LDA PC=2" severity error;
    assert pc = "0010" report "REQ R60: DECODE LDA PC stabil" severity error;
    wait until rising_edge(clk); -- E2 -> EXECUTE
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " LDA EXECUTE op=" & to_string(alu_op) & " bsel=" & to_string(alu_b_sel) severity note;
    assert acc_en = '1' report "REQ R20: LDA acc_en=1" severity error;
    assert z_en = '1' report "REQ R20: LDA z_en=1 (Z neu)" severity error;
    assert c_en = '0' report "REQ R20: LDA c_en=0 (C unveraendert)" severity error;
    assert alu_op = "111" report "REQ R20: LDA alu_op=PASS" severity error;
    assert alu_b_sel = '0' report "REQ R20: LDA alu_b_sel=0 (RAM)" severity error;
    assert ram_addr = "0011" report "REQ R20: LDA ram_addr=a=3" severity error;
    wait until rising_edge(clk); -- E3 -> WAIT
    wait for 1 ns;
    assert pc = "0010" report "REQ R61: LDA nach WAIT PC=2" severity error;

    -- STA x"34" (R21): PC 2 -> 3
    rom_data <= x"34";
    go <= '1';
    wait until rising_edge(clk); -- E0
    go <= '0';
    wait until rising_edge(clk); -- E1
    wait for 1 ns;
    assert ir = x"34" and pc = "0011" report "REQ R59: FETCH STA PC=3" severity error;
    wait until rising_edge(clk); -- E2 -> EXECUTE
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " STA EXECUTE ram_we=" & to_string(ram_we) & " addr=" & to_string(ram_addr) severity note;
    assert ram_we = '1' report "REQ R21: STA ram_we=1" severity error;
    assert ram_addr = "0100" report "REQ R21: STA ram_addr=a=4" severity error;
    assert acc_en = '0' report "REQ R21: STA acc_en=0 (Flags unveraendert)" severity error;
    assert z_en = '0' report "REQ R21: STA z_en=0" severity error;
    assert c_en = '0' report "REQ R21: STA c_en=0" severity error;
    assert out_en = '0' report "REQ R21: STA out_en=0" severity error;
    wait until rising_edge(clk); -- E3 -> WAIT
    wait for 1 ns;
    assert pc = "0011" report "REQ R61: STA nach WAIT PC=3" severity error;

    -- ADD x"45" mit go gehalten (R22 + R58 go-ignoriert): PC 3 -> 4
    rom_data <= x"45";
    go <= '1';
    wait until rising_edge(clk); -- E0
    wait until rising_edge(clk); -- E1 -> DECODE (go weiter 1)
    wait for 1 ns;
    assert pc = "0100" report "REQ R58: go in FETCH ignoriert (PC nur +1, nicht +2)" severity error;
    assert acc_en = '0' report "REQ R58: go in FETCH erzeugt keine EXECUTE-Signale" severity error;
    wait until rising_edge(clk); -- E2 -> EXECUTE (go weiter 1)
    wait for 1 ns;
    assert pc = "0100" report "REQ R58: go in DECODE ignoriert (PC stabil)" severity error;
    report "CHECK t=" & time'image(now) & " ADD EXECUTE op=" & to_string(alu_op) & " go-gehalten" severity note;
    assert acc_en = '1' report "REQ R22: ADD acc_en=1" severity error;
    assert z_en = '1' report "REQ R22: ADD z_en=1 (Z neu)" severity error;
    assert c_en = '1' report "REQ R22: ADD c_en=1 (Uebertrag aus Bit3)" severity error;
    assert alu_op = "000" report "REQ R22: ADD alu_op=000" severity error;
    assert alu_b_sel = '0' report "REQ R22: ADD alu_b_sel=0 (RAM)" severity error;
    assert ram_addr = "0101" report "REQ R22: ADD ram_addr=5" severity error;
    go <= '0';
    wait until rising_edge(clk); -- E3 -> WAIT
    wait for 1 ns;
    assert pc = "0100" report "REQ R58: go in EXECUTE ignoriert (EXECUTE->WAIT, nicht FETCH)" severity error;

    -- SUB x"56" (R23): PC 4 -> 5
    rom_data <= x"56";
    go <= '1';
    wait until rising_edge(clk); -- E0
    go <= '0';
    wait until rising_edge(clk); -- E1
    wait for 1 ns;
    assert ir = x"56" report "REQ R59: FETCH SUB IR" severity error;
    wait until rising_edge(clk); -- E2
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " SUB EXECUTE op=" & to_string(alu_op) severity note;
    assert acc_en = '1' report "REQ R23: SUB acc_en=1" severity error;
    assert z_en = '1' report "REQ R23: SUB z_en=1 (Z neu)" severity error;
    assert c_en = '1' report "REQ R23: SUB c_en=1 (Borgen wenn ACC<RAM)" severity error;
    assert alu_op = "001" report "REQ R23: SUB alu_op=001" severity error;
    assert alu_b_sel = '0' report "REQ R23: SUB alu_b_sel=0" severity error;
    wait until rising_edge(clk); -- E3
    wait for 1 ns;
    assert pc = "0101" report "REQ R61: SUB PC=5" severity error;

    -- AND x"67" (R24): PC 5 -> 6
    rom_data <= x"67";
    go <= '1';
    wait until rising_edge(clk); -- E0
    go <= '0';
    wait until rising_edge(clk); -- E1
    wait until rising_edge(clk); -- E2
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " AND EXECUTE op=" & to_string(alu_op) severity note;
    assert acc_en = '1' report "REQ R24: AND acc_en=1" severity error;
    assert z_en = '1' report "REQ R24: AND z_en=1 (Z neu)" severity error;
    assert c_en = '1' report "REQ R24: AND c_en=1 (C:=0 via ALU)" severity error;
    assert alu_op = "010" report "REQ R24: AND alu_op=010" severity error;
    wait until rising_edge(clk); -- E3
    wait for 1 ns;
    assert pc = "0110" report "REQ R61: AND PC=6" severity error;

    -- OR x"78" (R25): PC 6 -> 7
    rom_data <= x"78";
    go <= '1';
    wait until rising_edge(clk); -- E0
    go <= '0';
    wait until rising_edge(clk); -- E1
    wait until rising_edge(clk); -- E2
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " OR EXECUTE op=" & to_string(alu_op) severity note;
    assert acc_en = '1' report "REQ R25: OR acc_en=1" severity error;
    assert z_en = '1' report "REQ R25: OR z_en=1" severity error;
    assert c_en = '1' report "REQ R25: OR c_en=1 (C:=0)" severity error;
    assert alu_op = "011" report "REQ R25: OR alu_op=011" severity error;
    wait until rising_edge(clk); -- E3
    wait for 1 ns;
    assert pc = "0111" report "REQ R61: OR PC=7" severity error;

    -- XOR x"89" (R26): PC 7 -> 8
    rom_data <= x"89";
    go <= '1';
    wait until rising_edge(clk); -- E0
    go <= '0';
    wait until rising_edge(clk); -- E1
    wait until rising_edge(clk); -- E2
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " XOR EXECUTE op=" & to_string(alu_op) severity note;
    assert acc_en = '1' report "REQ R26: XOR acc_en=1" severity error;
    assert z_en = '1' report "REQ R26: XOR z_en=1" severity error;
    assert c_en = '1' report "REQ R26: XOR c_en=1 (C:=0)" severity error;
    assert alu_op = "100" report "REQ R26: XOR alu_op=100" severity error;
    wait until rising_edge(clk); -- E3
    wait for 1 ns;
    assert pc = "1000" report "REQ R61: XOR PC=8" severity error;

    -- SHL x"90" (R27): PC 8 -> 9
    rom_data <= x"90";
    go <= '1';
    wait until rising_edge(clk); -- E0
    go <= '0';
    wait until rising_edge(clk); -- E1
    wait until rising_edge(clk); -- E2
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " SHL EXECUTE op=" & to_string(alu_op) severity note;
    assert acc_en = '1' report "REQ R27: SHL acc_en=1" severity error;
    assert z_en = '1' report "REQ R27: SHL z_en=1 (Z neu)" severity error;
    assert c_en = '1' report "REQ R27: SHL c_en=1 (C:=altes Bit3)" severity error;
    assert alu_op = "101" report "REQ R27: SHL alu_op=101" severity error;
    wait until rising_edge(clk); -- E3
    wait for 1 ns;
    assert pc = "1001" report "REQ R61: SHL PC=9" severity error;

    -- SHR x"A5" (R28): PC 9 -> 10
    rom_data <= x"A5";
    go <= '1';
    wait until rising_edge(clk); -- E0
    go <= '0';
    wait until rising_edge(clk); -- E1
    wait until rising_edge(clk); -- E2
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " SHR EXECUTE op=" & to_string(alu_op) severity note;
    assert acc_en = '1' report "REQ R28: SHR acc_en=1" severity error;
    assert z_en = '1' report "REQ R28: SHR z_en=1" severity error;
    assert c_en = '1' report "REQ R28: SHR c_en=1 (C:=altes Bit0)" severity error;
    assert alu_op = "110" report "REQ R28: SHR alu_op=110" severity error;
    wait until rising_edge(clk); -- E3
    wait for 1 ns;
    assert pc = "1010" report "REQ R59: FETCH PC mod16 Zaehler (9->10)" severity error;

    -- JMP x"B4" (R29): PC 10 -> FETCH 11 -> Sprung 4
    rom_data <= x"B4";
    go <= '1';
    wait until rising_edge(clk); -- E0
    go <= '0';
    wait until rising_edge(clk); -- E1
    wait for 1 ns;
    assert ir = x"B4" report "REQ R59: FETCH JMP IR=xB4" severity error;
    assert pc = "1011" report "REQ R59: FETCH JMP PC+1=11" severity error;
    wait until rising_edge(clk); -- E2
    wait for 1 ns;
    assert acc_en = '0' and ram_we = '0' and out_en = '0' and z_en = '0' and c_en = '0' report "REQ R29: JMP keine Datenpfad-Enables" severity error;
    wait until rising_edge(clk); -- E3
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " JMP EXECUTE pc=" & to_string(pc) severity note;
    assert pc = "0100" report "REQ R29: JMP PC:=t=4 (ueberschreibt PC+1)" severity error;
    assert halted = '0' report "REQ R61: JMP geht nach WAIT" severity error;

    -- JZ taken x"C7" mit z=1 (R30): PC 4 -> 5 -> Sprung 7
    rom_data <= x"C7";
    z_flag <= '1'; c_flag <= '0';
    go <= '1';
    wait until rising_edge(clk); -- E0
    go <= '0';
    wait until rising_edge(clk); -- E1
    wait until rising_edge(clk); -- E2
    wait for 1 ns;
    assert acc_en = '0' and ram_we = '0' and out_en = '0' report "REQ R30: JZ keine Datenpfad-Aktion" severity error;
    wait until rising_edge(clk); -- E3
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " JZ taken pc=" & to_string(pc) severity note;
    assert pc = "0111" report "REQ R30: JZ mit Z=1 springt nach t=7" severity error;
    assert halted = '0' report "REQ R61: JZ taken nach WAIT" severity error;

    -- JZ not taken x"C7" mit z=0 (R30): PC 7 -> 8
    rom_data <= x"C7";
    z_flag <= '0';
    go <= '1';
    wait until rising_edge(clk); -- E0
    go <= '0';
    wait until rising_edge(clk); -- E1
    wait until rising_edge(clk); -- E2
    wait for 1 ns;
    assert acc_en = '0' and z_en = '0' and c_en = '0' report "REQ R30: JZ not-taken keine Enables" severity error;
    wait until rising_edge(clk); -- E3
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " JZ not-taken pc=" & to_string(pc) severity note;
    assert pc = "1000" report "REQ R30: JZ mit Z=0 kein Sprung (PC+1=8)" severity error;

    -- JC taken x"DE" mit c=1 (R31,R54): PC 8 -> 9 -> Sprung 14
    rom_data <= x"DE";
    c_flag <= '1'; z_flag <= '0';
    go <= '1';
    wait until rising_edge(clk); -- E0
    go <= '0';
    wait until rising_edge(clk); -- E1
    wait until rising_edge(clk); -- E2
    wait for 1 ns;
    assert acc_en = '0' and ram_we = '0' report "REQ R31: JC keine Datenpfad-Aktion" severity error;
    wait until rising_edge(clk); -- E3
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " JC taken pc=" & to_string(pc) & " halted=" & to_string(halted) severity note;
    assert pc = "1110" report "REQ R31: JC mit C=1 springt nach t=14" severity error;
    assert pc = "1110" report "REQ R54: JC bei Ueberlauf (C=1) springt nach 14" severity error;

    -- JC not taken x"DE" mit c=0 (R31): PC 14 -> 15
    rom_data <= x"DE";
    c_flag <= '0';
    go <= '1';
    wait until rising_edge(clk); -- E0
    go <= '0';
    wait until rising_edge(clk); -- E1
    wait for 1 ns;
    assert pc = "1111" report "REQ R59: FETCH PC 14->15" severity error;
    wait until rising_edge(clk); -- E2
    wait until rising_edge(clk); -- E3
    wait for 1 ns;
    assert pc = "1111" report "REQ R31: JC mit C=0 kein Sprung (PC=15)" severity error;

    -- OUT x"E0" (R32): PC 15 -> 0 (mod16 wrap)
    rom_data <= x"E0";
    go <= '1';
    wait until rising_edge(clk); -- E0
    go <= '0';
    wait until rising_edge(clk); -- E1
    wait for 1 ns;
    assert ir = x"E0" report "REQ R59: FETCH OUT IR=xE0" severity error;
    assert pc = "0000" report "REQ R59: FETCH PC mod16 Wrap 15+1=0" severity error;
    wait until rising_edge(clk); -- E2
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " OUT EXECUTE out_en=" & to_string(out_en) severity note;
    assert out_en = '1' report "REQ R32: OUT out_en=1 (OUT:=ACC)" severity error;
    assert acc_en = '0' and ram_we = '0' and z_en = '0' and c_en = '0' report "REQ R32: OUT nur out_en, keine Flags" severity error;
    wait until rising_edge(clk); -- E3
    wait for 1 ns;
    assert pc = "0000" report "REQ R61: OUT geht nach WAIT mit PC=0" severity error;

    -- HLT x"F0" (R33,R62): PC 0 -> 1, dann HALT
    rom_data <= x"F0";
    go <= '1';
    wait until rising_edge(clk); -- E0
    go <= '0';
    wait until rising_edge(clk); -- E1
    wait for 1 ns;
    assert pc = "0001" report "REQ R59: FETCH HLT PC=1" severity error;
    wait until rising_edge(clk); -- E2 -> EXECUTE
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " HLT EXECUTE halted=" & to_string(halted) severity note;
    assert acc_en = '0' and ram_we = '0' and out_en = '0' report "REQ R33: HLT keine Datenpfad-Aktion" severity error;
    assert halted = '0' report "REQ R62: in EXECUTE noch nicht HALT" severity error;
    wait until rising_edge(clk); -- E3 -> HALT
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " nach HLT pc=" & to_string(pc) & " halted=" & to_string(halted) severity note;
    assert halted = '1' report "REQ R33: HLT fuehrt nach HALT (halted=1)" severity error;
    assert halted = '1' report "REQ R62: HALT bleibt bis Reset" severity error;
    assert pc = "0001" report "REQ R61: HLT behaelt PC+1 aus FETCH" severity error;

    -- HALT bleibt auch mit go=1 und weiteren Takten
    go <= '1';
    wait_cycles(3);
    go <= '0';
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " HALT bestaendig pc=" & to_string(pc) & " halted=" & to_string(halted) severity note;
    assert halted = '1' report "REQ R62: HALT bleibt trotz go=1" severity error;
    assert pc = "0001" report "REQ R62: HALT PC stabil trotz go" severity error;
    assert acc_en = '0' and ram_we = '0' and out_en = '0' report "REQ R33: in HALT keine Steuersignale" severity error;

    -- Reset aus HALT (R71)
    rst <= '1';
    wait_cycles(2);
    wait for 1 ns;
    assert pc = "0000" report "REQ R71: Reset aus HALT setzt PC=0" severity error;
    assert ir = "00000000" report "REQ R71: Reset aus HALT setzt IR=0" severity error;
    assert halted = '0' report "REQ R71: Reset aus HALT geht nach WAIT" severity error;
    rst <= '0';
    wait_cycles(1);
    wait for 1 ns;
    assert halted = '0' report "REQ R56: nach Reset wieder WAIT" severity error;

    tb_done <= true;
    report "TB_COMPLETE" severity note;
    std.env.stop;
    wait;
  end process stim;

end architecture sim;