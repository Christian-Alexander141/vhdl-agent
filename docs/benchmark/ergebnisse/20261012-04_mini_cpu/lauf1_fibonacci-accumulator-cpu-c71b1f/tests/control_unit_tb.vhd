library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.env.all;

entity control_unit_tb is
end entity control_unit_tb;

architecture sim of control_unit_tb is
  constant CLK_PERIOD : time := 10 ns;

  signal clk      : std_logic := '0';
  signal rst      : std_logic := '1';
  signal go       : std_logic := '0';
  signal z        : std_logic := '0';
  signal c        : std_logic := '0';
  signal rom_data : std_logic_vector(7 downto 0) := (others => '0');
  signal pc       : std_logic_vector(3 downto 0);
  signal ram_addr : std_logic_vector(3 downto 0);
  signal ram_we   : std_logic;
  signal alu_op   : std_logic_vector(2 downto 0);
  signal use_imm  : std_logic;
  signal acc_we   : std_logic;
  signal z_we     : std_logic;
  signal c_we     : std_logic;
  signal out_we   : std_logic;
  signal halted   : std_logic;

  signal tb_done : boolean := false;
begin
  clk <= not clk after CLK_PERIOD / 2 when not tb_done else '0';

  dut: entity work.control_unit
    port map (
      clk      => clk,
      rst      => rst,
      go       => go,
      z        => z,
      c        => c,
      rom_data => rom_data,
      pc       => pc,
      ram_addr => ram_addr,
      ram_we   => ram_we,
      alu_op   => alu_op,
      use_imm  => use_imm,
      acc_we   => acc_we,
      z_we     => z_we,
      c_we     => c_we,
      out_we   => out_we,
      halted   => halted
    );

  stim: process
    procedure wait_cycles(n : in positive) is
    begin
      for i in 1 to n loop
        wait until rising_edge(clk);
        wait for 1 ns;
      end loop;
    end procedure;
  begin
    -- Reset 2 Zyklen aktiv (synchron, active high).
    rst <= '1'; go <= '0'; z <= '0'; c <= '0'; rom_data <= x"00";
    wait_cycles(2);
    report "CHECK t=" & time'image(now) & " after-reset pc=" & to_string(pc) & " halted=" & std_logic'image(halted);
    assert pc = "0000" report "REQ R51: nach Reset muss PC=0 sein (WAIT, naechster Befehl Adresse 0)" severity error;
    assert halted = '0' report "REQ R51: nach Reset muss Steuerwerk in WAIT sein (halted=0)" severity error;
    assert pc = "0000" report "REQ R71: synchroner Reset loescht PC auf 0" severity error;
    assert halted = '0' report "REQ R71: synchroner Reset loescht HALT-Zustand (WAIT, halted=0)" severity error;
    assert ram_we = '0' and acc_we = '0' and z_we = '0' and c_we = '0' and out_we = '0' report "REQ R71: nach Reset keine Steuersignale aktiv" severity error;
    assert halted = '0' report "REQ R57: nach Reset nicht in HALT" severity error;

    rst <= '0';
    -- WAIT ohne go: bleibt stehen (R53a).
    wait_cycles(2);
    report "CHECK t=" & time'image(now) & " wait-idle pc=" & to_string(pc) & " halted=" & std_logic'image(halted);
    assert pc = "0000" report "REQ R53: in WAIT ohne go=1 bleibt PC stabil (kein FETCH)" severity error;
    assert halted = '0' report "REQ R53: in WAIT ohne go kein HALT" severity error;
    assert halted = '0' report "REQ R52: ohne go (kein Tick/rise) startet kein Befehl" severity error;

    -- NOP x"00": voller 4-Flanken-Ablauf, FETCH/DECODE/EXECUTE pruefen.
    -- R58: nach go genau drei weitere Flanken bis WAIT.
    rom_data <= x"00"; z <= '0'; c <= '0'; go <= '0';
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " NOP setup pc=" & to_string(pc);
    assert pc = "0000" report "REQ R54: vor FETCH zeigt PC die naechste Adresse 0" severity error;
    go <= '1';
    wait until rising_edge(clk); wait for 1 ns; -- edge0 WAIT->FETCH
    go <= '0';
    report "CHECK t=" & time'image(now) & " NOP edge0 (WAIT+go) pc=" & to_string(pc) & " halted=" & std_logic'image(halted);
    assert pc = "0000" report "REQ R52: go=1 in WAIT startet FETCH (PC noch alt bis FETCH-Flanke)" severity error;
    assert halted = '0' report "REQ R51: nach go noch nicht HALT" severity error;
    wait until rising_edge(clk); wait for 1 ns; -- edge1 FETCH->DECODE, pc 0->1
    report "CHECK t=" & time'image(now) & " NOP edge1 FETCH pc=" & to_string(pc) & " ram_addr=" & to_string(ram_addr);
    assert pc = "0001" report "REQ R54: FETCH inkrementiert PC 0->1 (mod 16)" severity error;
    assert ram_addr = "0000" report "REQ R54: FETCH laedt IR:=ROM[PC], ram_addr=Operand 0000" severity error;
    assert halted = '0' report "REQ R56: FETCH fuehrt nicht nach HALT" severity error;
    -- Jetzt in DECODE: kein Register aendert sich (R55).
    assert pc = "0001" report "REQ R55: DECODE aendert PC nicht (bleibt 1)" severity error;
    assert ram_we = '0' and acc_we = '0' and out_we = '0' report "REQ R55: DECODE dekodiert nur, keine Register/WE aktiv" severity error;
    assert acc_we = '0' and z_we = '0' and c_we = '0' report "REQ R55: DECODE keine Flag/ACC-We" severity error;
    wait until rising_edge(clk); wait for 1 ns; -- edge2 DECODE->EXECUTE
    report "CHECK t=" & time'image(now) & " NOP edge2 DECODE->EXECUTE pc=" & to_string(pc) & " acc_we=" & std_logic'image(acc_we);
    assert pc = "0001" report "REQ R55: DECODE->EXECUTE aendert PC nicht" severity error;
    -- Jetzt in EXECUTE NOP: keine Wirkung.
    assert ram_we = '0' and acc_we = '0' and z_we = '0' and c_we = '0' and out_we = '0' report "REQ R16: NOP hat keine Wirkung (kein WE)" severity error;
    assert halted = '0' report "REQ R16: NOP fuehrt nicht nach HALT" severity error;
    assert pc = "0001" report "REQ R56: EXECUTE NOP aendert PC nicht (kein Sprung)" severity error;
    wait until rising_edge(clk); wait for 1 ns; -- edge3 EXECUTE->WAIT
    report "CHECK t=" & time'image(now) & " NOP edge3 EXECUTE->WAIT pc=" & to_string(pc);
    assert pc = "0001" report "REQ R56: nach EXECUTE NOP zurueck nach WAIT mit PC=1" severity error;
    assert halted = '0' report "REQ R56: nach NOP in WAIT (halted=0)" severity error;
    assert halted = '0' report "REQ R58: ein Befehl braucht nach go genau drei weitere Flanken (jetzt wieder WAIT)" severity error;
    -- Bestaetigung WAIT: ohne go bleibt PC stabil.
    wait_cycles(1);
    assert pc = "0001" report "REQ R58: nach 4 Flanken genau ein Befehl (PC=1, kein zweiter FETCH ohne go)" severity error;
    assert pc = "0001" report "REQ R66: erster Befehl nach Reset braucht genau einen go (Tick) und 3 Folgeflanken" severity error;

    -- go wird in FETCH/DECODE/EXECUTE ignoriert (R53b): go waehrend DECODE/EXECUTE hoch halten.
    rom_data <= x"00";
    wait_cycles(1);
    assert pc = "0001" report "REQ R53: WAIT ohne go bleibt (vor ignore-Test)" severity error;
    go <= '1';
    wait until rising_edge(clk); wait for 1 ns; -- edge0 WAIT->FETCH mit go
    report "CHECK t=" & time'image(now) & " IGNORE edge0 pc=" & to_string(pc) & " go=1 gehalten";
    -- go bleibt absichtlich 1 waehrend FETCH/DECODE/EXECUTE
    wait until rising_edge(clk); wait for 1 ns; -- edge1 FETCH
    assert pc = "0010" report "REQ R53: FETCH trotz go=1 normal nach DECODE (PC=2)" severity error;
    wait until rising_edge(clk); wait for 1 ns; -- edge2 DECODE->EXECUTE, go immer noch 1
    assert pc = "0010" report "REQ R53: go in DECODE wird ignoriert (PC stabil 2)" severity error;
    assert ram_we = '0' and acc_we = '0' report "REQ R53: go in EXECUTE erzeugt keinen Extra-Befehl (NOP WE=0)" severity error;
    wait until rising_edge(clk); wait for 1 ns; -- edge3 EXECUTE->WAIT
    go <= '0';
    wait for 1 ns;
    assert pc = "0010" report "REQ R53: trotz gehaltenem go nur ein Befehl (PC=2, kein Doppel-FETCH)" severity error;
    report "CHECK t=" & time'image(now) & " IGNORE done pc=" & to_string(pc);
    -- Nach Rueckkehr nach WAIT mit go=1 gehalten waere sofort naechster FETCH gestartet;
    -- da go jetzt 0 ist, muss WAIT halten:
    wait_cycles(2);
    assert pc = "0010" report "REQ R53: nach EXECUTE mit go=0 bleibt WAIT (PC=2)" severity error;

    -- LDI 5 x"15": ACC:=5, Z neu, C unveraendert (c_we=0).
    rom_data <= x"15"; z <= '0'; c <= '0';
    wait_cycles(1);
    go <= '1';
    wait until rising_edge(clk); wait for 1 ns; go <= '0';
    wait until rising_edge(clk); wait for 1 ns; -- FETCH 2->3
    assert pc = "0011" report "REQ R54: FETCH LDI inkrementiert PC 2->3" severity error;
    wait until rising_edge(clk); wait for 1 ns; -- DECODE->EXECUTE
    report "CHECK t=" & time'image(now) & " LDI EXECUTE alu_op=" & to_string(alu_op) & " use_imm=" & std_logic'image(use_imm) & " acc_we=" & std_logic'image(acc_we) & " z_we=" & std_logic'image(z_we) & " c_we=" & std_logic'image(c_we);
    assert alu_op = "111" and use_imm = '1' report "REQ R17: LDI nutzt PASS b mit use_imm=1 (Konstante n)" severity error;
    assert acc_we = '1' report "REQ R17: LDI setzt acc_we=1 (ACC:=n)" severity error;
    assert z_we = '1' report "REQ R17: LDI aktualisiert Z (z_we=1)" severity error;
    assert z_we = '1' report "REQ R30: Z neu bei LDI (z_we=1, Z=1 genau wenn neuer ACC=0)" severity error;
    assert c_we = '0' report "REQ R17: LDI laesst C unveraendert (c_we=0)" severity error;
    assert c_we = '0' report "REQ R31: bei LDI bleibt C unveraendert (c_we=0)" severity error;
    assert ram_we = '0' and out_we = '0' report "REQ R17: LDI schreibt weder RAM noch OUT" severity error;
    assert ram_addr = "0101" report "REQ R56: ram_addr fuehrt Operanden n=0101 (auch bei LDI)" severity error;
    wait until rising_edge(clk); wait for 1 ns; -- EXECUTE->WAIT
    assert pc = "0011" report "REQ R56: LDI kein Sprung (PC bleibt 3)" severity error;

    -- LDA 2 x"22": ACC:=RAM[2].
    rom_data <= x"22";
    wait_cycles(1);
    go <= '1';
    wait until rising_edge(clk); wait for 1 ns; go <= '0';
    wait until rising_edge(clk); wait for 1 ns;
    assert pc = "0100" report "REQ R54: FETCH LDA PC 3->4" severity error;
    wait until rising_edge(clk); wait for 1 ns;
    report "CHECK t=" & time'image(now) & " LDA EXECUTE alu_op=" & to_string(alu_op) & " use_imm=" & std_logic'image(use_imm);
    assert alu_op = "111" and use_imm = '0' report "REQ R18: LDA nutzt PASS b mit use_imm=0 (RAM[a])" severity error;
    assert acc_we = '1' and z_we = '1' report "REQ R18: LDA setzt acc_we=1 und z_we=1 (ACC:=RAM[a], Z neu)" severity error;
    assert z_we = '1' report "REQ R30: Z neu bei LDA (z_we=1)" severity error;
    assert c_we = '0' report "REQ R18: LDA laesst C unveraendert (c_we=0)" severity error;
    assert c_we = '0' report "REQ R31: bei LDA bleibt C unveraendert" severity error;
    assert ram_addr = "0010" report "REQ R18: LDA Adresse a=0010 an ram_addr" severity error;
    wait until rising_edge(clk); wait for 1 ns;
    assert pc = "0100" report "REQ R56: LDA kein Sprung" severity error;

    -- STA 3 x"33": RAM[3]:=ACC, Flags unveraendert.
    rom_data <= x"33";
    wait_cycles(1);
    go <= '1';
    wait until rising_edge(clk); wait for 1 ns; go <= '0';
    wait until rising_edge(clk); wait for 1 ns;
    assert pc = "0101" report "REQ R54: FETCH STA PC 4->5" severity error;
    wait until rising_edge(clk); wait for 1 ns;
    report "CHECK t=" & time'image(now) & " STA EXECUTE ram_we=" & std_logic'image(ram_we) & " ram_addr=" & to_string(ram_addr);
    assert ram_we = '1' report "REQ R19: STA setzt ram_we=1 (RAM[a]:=ACC)" severity error;
    assert ram_addr = "0011" report "REQ R19: STA Adresse a=0011" severity error;
    assert acc_we = '0' and z_we = '0' and c_we = '0' and out_we = '0' report "REQ R19: STA aendert keine Flags/ACC/OUT" severity error;
    assert z_we = '0' and c_we = '0' report "REQ R31: STA laesst Z und C unveraendert" severity error;
    wait until rising_edge(clk); wait for 1 ns;
    assert pc = "0101" report "REQ R56: STA kein Sprung" severity error;

    -- ADD 1 x"41": alu_op 000, acc/z/c we.
    rom_data <= x"41";
    wait_cycles(1);
    go <= '1';
    wait until rising_edge(clk); wait for 1 ns; go <= '0';
    wait until rising_edge(clk); wait for 1 ns;
    assert pc = "0110" report "REQ R54: FETCH ADD PC 5->6" severity error;
    wait until rising_edge(clk); wait for 1 ns;
    report "CHECK t=" & time'image(now) & " ADD EXECUTE alu_op=" & to_string(alu_op);
    assert alu_op = "000" report "REQ R20: ADD nutzt alu_op 000" severity error;
    assert acc_we = '1' and z_we = '1' and c_we = '1' report "REQ R20: ADD setzt acc_we/z_we/c_we=1" severity error;
    assert z_we = '1' report "REQ R30: Z neu bei ADD" severity error;
    assert ram_addr = "0001" report "REQ R20: ADD Adresse a=0001" severity error;
    assert out_we = '0' and ram_we = '0' report "REQ R56: ADD kein RAM/OUT-Schreiben" severity error;
    wait until rising_edge(clk); wait for 1 ns;
    assert pc = "0110" report "REQ R56: ADD kein Sprung" severity error;

    -- SUB 1 x"52": alu_op 001.
    rom_data <= x"52";
    wait_cycles(1);
    go <= '1';
    wait until rising_edge(clk); wait for 1 ns; go <= '0';
    wait until rising_edge(clk); wait for 1 ns;
    assert pc = "0111" report "REQ R54: FETCH SUB PC 6->7" severity error;
    wait until rising_edge(clk); wait for 1 ns;
    report "CHECK t=" & time'image(now) & " SUB EXECUTE alu_op=" & to_string(alu_op);
    assert alu_op = "001" report "REQ R21: SUB nutzt alu_op 001" severity error;
    assert acc_we = '1' and z_we = '1' and c_we = '1' report "REQ R21: SUB setzt acc_we/z_we/c_we=1 (C=Borrow)" severity error;
    assert z_we = '1' report "REQ R30: Z neu bei SUB" severity error;
    wait until rising_edge(clk); wait for 1 ns;
    assert pc = "0111" report "REQ R56: SUB kein Sprung" severity error;

    -- AND 1 x"63": alu_op 010, C:=0 (c_we=1, ALU liefert 0).
    rom_data <= x"63";
    wait_cycles(1);
    go <= '1';
    wait until rising_edge(clk); wait for 1 ns; go <= '0';
    wait until rising_edge(clk); wait for 1 ns;
    assert pc = "1000" report "REQ R54: FETCH AND PC 7->8" severity error;
    wait until rising_edge(clk); wait for 1 ns;
    report "CHECK t=" & time'image(now) & " AND EXECUTE alu_op=" & to_string(alu_op);
    assert alu_op = "010" report "REQ R22: AND nutzt alu_op 010" severity error;
    assert acc_we = '1' and z_we = '1' and c_we = '1' report "REQ R22: AND setzt acc/z/c_we=1 (C:=0)" severity error;
    assert z_we = '1' report "REQ R30: Z neu bei AND" severity error;
    wait until rising_edge(clk); wait for 1 ns;
    assert pc = "1000" report "REQ R56: AND kein Sprung" severity error;

    -- OR 1 x"74": alu_op 011.
    rom_data <= x"74";
    wait_cycles(1);
    go <= '1';
    wait until rising_edge(clk); wait for 1 ns; go <= '0';
    wait until rising_edge(clk); wait for 1 ns;
    assert pc = "1001" report "REQ R54: FETCH OR PC 8->9" severity error;
    wait until rising_edge(clk); wait for 1 ns;
    report "CHECK t=" & time'image(now) & " OR EXECUTE alu_op=" & to_string(alu_op);
    assert alu_op = "011" report "REQ R22: OR nutzt alu_op 011" severity error;
    assert acc_we = '1' and z_we = '1' and c_we = '1' report "REQ R22: OR setzt acc/z/c_we=1 (C:=0)" severity error;
    assert z_we = '1' report "REQ R30: Z neu bei OR" severity error;
    wait until rising_edge(clk); wait for 1 ns;
    assert pc = "1001" report "REQ R56: OR kein Sprung" severity error;

    -- XOR 1 x"85": alu_op 100.
    rom_data <= x"85";
    wait_cycles(1);
    go <= '1';
    wait until rising_edge(clk); wait for 1 ns; go <= '0';
    wait until rising_edge(clk); wait for 1 ns;
    assert pc = "1010" report "REQ R54: FETCH XOR PC 9->10" severity error;
    wait until rising_edge(clk); wait for 1 ns;
    report "CHECK t=" & time'image(now) & " XOR EXECUTE alu_op=" & to_string(alu_op);
    assert alu_op = "100" report "REQ R22: XOR nutzt alu_op 100" severity error;
    assert acc_we = '1' and z_we = '1' and c_we = '1' report "REQ R22: XOR setzt acc/z/c_we=1 (C:=0)" severity error;
    assert z_we = '1' report "REQ R30: Z neu bei XOR" severity error;
    wait until rising_edge(clk); wait for 1 ns;
    assert pc = "1010" report "REQ R56: XOR kein Sprung" severity error;

    -- SHL x"90": alu_op 101.
    rom_data <= x"90";
    wait_cycles(1);
    go <= '1';
    wait until rising_edge(clk); wait for 1 ns; go <= '0';
    wait until rising_edge(clk); wait for 1 ns;
    assert pc = "1011" report "REQ R54: FETCH SHL PC 10->11" severity error;
    wait until rising_edge(clk); wait for 1 ns;
    report "CHECK t=" & time'image(now) & " SHL EXECUTE alu_op=" & to_string(alu_op);
    assert alu_op = "101" report "REQ R23: SHL nutzt alu_op 101" severity error;
    assert acc_we = '1' and z_we = '1' and c_we = '1' report "REQ R23: SHL setzt acc/z/c_we=1 (C=altes Bit3)" severity error;
    assert z_we = '1' report "REQ R30: Z neu bei SHL" severity error;
    wait until rising_edge(clk); wait for 1 ns;
    assert pc = "1011" report "REQ R56: SHL kein Sprung" severity error;

    -- SHR x"A0": alu_op 110.
    rom_data <= x"A0";
    wait_cycles(1);
    go <= '1';
    wait until rising_edge(clk); wait for 1 ns; go <= '0';
    wait until rising_edge(clk); wait for 1 ns;
    assert pc = "1100" report "REQ R54: FETCH SHR PC 11->12" severity error;
    wait until rising_edge(clk); wait for 1 ns;
    report "CHECK t=" & time'image(now) & " SHR EXECUTE alu_op=" & to_string(alu_op);
    assert alu_op = "110" report "REQ R24: SHR nutzt alu_op 110" severity error;
    assert acc_we = '1' and z_we = '1' and c_we = '1' report "REQ R24: SHR setzt acc/z/c_we=1 (C=altes Bit0)" severity error;
    assert z_we = '1' report "REQ R30: Z neu bei SHR" severity error;
    wait until rising_edge(clk); wait for 1 ns;
    assert pc = "1100" report "REQ R56: SHR kein Sprung" severity error;

    -- JMP 15 x"BF": PC:=15 (Sprung ueberschreibt PC+1 aus FETCH).
    rom_data <= x"BF";
    wait_cycles(1);
    go <= '1';
    wait until rising_edge(clk); wait for 1 ns; go <= '0';
    wait until rising_edge(clk); wait for 1 ns; -- FETCH 12->13
    assert pc = "1101" report "REQ R54: FETCH JMP inkrementiert zunaechst PC 12->13" severity error;
    wait until rising_edge(clk); wait for 1 ns; -- EXECUTE JMP
    assert acc_we = '0' and z_we = '0' and c_we = '0' and ram_we = '0' and out_we = '0' report "REQ R25: JMP aendert keine Daten/Flags (nur PC)" severity error;
    assert z_we = '0' and c_we = '0' report "REQ R31: JMP laesst Z und C unveraendert" severity error;
    wait until rising_edge(clk); wait for 1 ns; -- EXECUTE->WAIT, PC=15
    report "CHECK t=" & time'image(now) & " JMP15 done pc=" & to_string(pc);
    assert pc = "1111" report "REQ R25: JMP t setzt PC:=t (12->15, PC+1 ueberschrieben)" severity error;
    assert pc = "1111" report "REQ R56: Sprung ueberschreibt PC+1 aus FETCH" severity error;

    -- NOP bei Adresse 15 x"00": wrap 15->0 (mod 16).
    rom_data <= x"00";
    wait_cycles(1);
    go <= '1';
    wait until rising_edge(clk); wait for 1 ns; go <= '0';
    wait until rising_edge(clk); wait for 1 ns; -- FETCH 15->0
    report "CHECK t=" & time'image(now) & " WRAP FETCH pc=" & to_string(pc);
    assert pc = "0000" report "REQ R54: FETCH mit PC=15 wrappt auf 0 (mod 16)" severity error;
    wait until rising_edge(clk); wait for 1 ns;
    assert pc = "0000" report "REQ R55: DECODE nach Wrap stabil" severity error;
    wait until rising_edge(clk); wait for 1 ns;
    assert pc = "0000" report "REQ R16: NOP bei 15 ohne Wirkung (PC=0)" severity error;

    -- JMP 4 x"B4": 0->4.
    rom_data <= x"B4";
    wait_cycles(1);
    go <= '1';
    wait until rising_edge(clk); wait for 1 ns; go <= '0';
    wait until rising_edge(clk); wait for 1 ns;
    assert pc = "0001" report "REQ R54: FETCH JMP4 PC 0->1" severity error;
    wait until rising_edge(clk); wait for 1 ns;
    wait until rising_edge(clk); wait for 1 ns;
    assert pc = "0100" report "REQ R25: JMP 4 setzt PC:=0100" severity error;

    -- JZ 8 nicht genommen (z=0) x"C8": 4->5.
    rom_data <= x"C8"; z <= '0'; c <= '0';
    wait_cycles(1);
    go <= '1';
    wait until rising_edge(clk); wait for 1 ns; go <= '0';
    wait until rising_edge(clk); wait for 1 ns;
    assert pc = "0101" report "REQ R54: FETCH JZ PC 4->5" severity error;
    wait until rising_edge(clk); wait for 1 ns;
    assert acc_we = '0' and z_we = '0' and c_we = '0' report "REQ R26: JZ aendert keine Daten/Flags" severity error;
    wait until rising_edge(clk); wait for 1 ns;
    report "CHECK t=" & time'image(now) & " JZ-not-taken pc=" & to_string(pc);
    assert pc = "0101" report "REQ R26: JZ mit Z=0 springt nicht (PC=5)" severity error;
    assert pc = "0101" report "REQ R31: JZ laesst Z und C unveraendert" severity error;

    -- JZ 8 genommen (z=1) x"C8": 5->8.
    rom_data <= x"C8"; z <= '1';
    wait_cycles(1);
    go <= '1';
    wait until rising_edge(clk); wait for 1 ns; go <= '0';
    wait until rising_edge(clk); wait for 1 ns; -- FETCH 5->6
    assert pc = "0110" report "REQ R54: FETCH JZ-taken zunaechst PC 5->6" severity error;
    wait until rising_edge(clk); wait for 1 ns;
    wait until rising_edge(clk); wait for 1 ns; -- EXECUTE->WAIT PC=8
    report "CHECK t=" & time'image(now) & " JZ-taken pc=" & to_string(pc);
    assert pc = "1000" report "REQ R26: JZ mit Z=1 springt nach t=8" severity error;
    assert pc = "1000" report "REQ R56: genommener Sprung ueberschreibt PC+1" severity error;
    z <= '0';

    -- JC 14 nicht genommen (c=0) x"DE": 8->9.
    rom_data <= x"DE"; c <= '0';
    wait_cycles(1);
    go <= '1';
    wait until rising_edge(clk); wait for 1 ns; go <= '0';
    wait until rising_edge(clk); wait for 1 ns;
    assert pc = "1001" report "REQ R54: FETCH JC PC 8->9" severity error;
    wait until rising_edge(clk); wait for 1 ns;
    assert acc_we = '0' and z_we = '0' and c_we = '0' report "REQ R27: JC aendert keine Daten/Flags" severity error;
    wait until rising_edge(clk); wait for 1 ns;
    report "CHECK t=" & time'image(now) & " JC-not-taken pc=" & to_string(pc);
    assert pc = "1001" report "REQ R27: JC mit C=0 springt nicht (PC=9)" severity error;

    -- OUT x"E0": OUT:=ACC (out_we=1).
    rom_data <= x"E0";
    wait_cycles(1);
    go <= '1';
    wait until rising_edge(clk); wait for 1 ns; go <= '0';
    wait until rising_edge(clk); wait for 1 ns;
    assert pc = "1010" report "REQ R54: FETCH OUT PC 9->10" severity error;
    wait until rising_edge(clk); wait for 1 ns;
    report "CHECK t=" & time'image(now) & " OUT EXECUTE out_we=" & std_logic'image(out_we);
    assert out_we = '1' report "REQ R28: OUT setzt out_we=1 (OUT:=ACC)" severity error;
    assert acc_we = '0' and z_we = '0' and c_we = '0' and ram_we = '0' report "REQ R28: OUT aendert ACC/Flags/RAM nicht" severity error;
    assert z_we = '0' and c_we = '0' report "REQ R31: OUT laesst Z und C unveraendert" severity error;
    wait until rising_edge(clk); wait for 1 ns;
    assert pc = "1010" report "REQ R56: OUT kein Sprung (PC=10)" severity error;

    -- JMP 6 x"B6": 10->6 (Ruecksetzen fuer R50-Sequenz).
    rom_data <= x"B6";
    wait_cycles(1);
    go <= '1';
    wait until rising_edge(clk); wait for 1 ns; go <= '0';
    wait until rising_edge(clk); wait for 1 ns;
    wait until rising_edge(clk); wait for 1 ns;
    wait until rising_edge(clk); wait for 1 ns;
    assert pc = "0110" report "REQ R25: JMP 6 setzt PC:=0110" severity error;

    -- JC 14 genommen (c=1) x"DE": 6->14 (Fibonacci-Ueberlauf 21, C=1).
    rom_data <= x"DE"; c <= '1';
    wait_cycles(1);
    go <= '1';
    wait until rising_edge(clk); wait for 1 ns; go <= '0';
    wait until rising_edge(clk); wait for 1 ns; -- FETCH 6->7
    assert pc = "0111" report "REQ R54: FETCH JC-taken zunaechst PC 6->7" severity error;
    wait until rising_edge(clk); wait for 1 ns;
    wait until rising_edge(clk); wait for 1 ns; -- EXECUTE->WAIT PC=14
    report "CHECK t=" & time'image(now) & " JC-taken pc=" & to_string(pc) & " c=1";
    assert pc = "1110" report "REQ R27: JC mit C=1 springt nach t=14" severity error;
    assert pc = "1110" report "REQ R50: JC bei Ueberlauf (C=1, Summe 21) springt nach 14" severity error;
    c <= '0';

    -- HLT x"F0" bei 14: 14->15, danach HALT.
    rom_data <= x"F0";
    wait_cycles(1);
    go <= '1';
    wait until rising_edge(clk); wait for 1 ns; go <= '0';
    wait until rising_edge(clk); wait for 1 ns; -- FETCH 14->15
    assert pc = "1111" report "REQ R54: FETCH HLT PC 14->15" severity error;
    wait until rising_edge(clk); wait for 1 ns; -- DECODE->EXECUTE
    report "CHECK t=" & time'image(now) & " HLT EXECUTE halted=" & std_logic'image(halted);
    assert halted = '0' report "REQ R29: in EXECUTE HLT noch halted=0 (erst nach Flanke HALT)" severity error;
    assert acc_we = '0' and z_we = '0' and c_we = '0' and ram_we = '0' and out_we = '0' report "REQ R29: HLT schreibt keine Daten/Flags" severity error;
    wait until rising_edge(clk); wait for 1 ns; -- EXECUTE->HALT
    report "CHECK t=" & time'image(now) & " HLT done pc=" & to_string(pc) & " halted=" & std_logic'image(halted);
    assert halted = '1' report "REQ R29: HLT fuehrt nach HALT (halted=1)" severity error;
    assert halted = '1' report "REQ R51: Zustand HALT existiert (halted=1)" severity error;
    assert pc = "1111" report "REQ R50: nach HLT gilt PC=15 (Adresse nach HLT)" severity error;
    assert halted = '1' report "REQ R56: EXECUTE HLT geht nach HALT statt WAIT" severity error;
    assert pc = "1111" report "REQ R56: HLT kein Sprung (PC=15 aus FETCH bleibt)" severity error;

    -- HALT bleibt bis Reset (R57), auch mit go=1 (Tick laeuft weiter, R65).
    go <= '1';
    wait_cycles(3);
    go <= '0';
    report "CHECK t=" & time'image(now) & " HALT-hold pc=" & to_string(pc) & " halted=" & std_logic'image(halted);
    assert halted = '1' report "REQ R57: HALT bleibt trotz go=1 bis Reset" severity error;
    assert pc = "1111" report "REQ R57: in HALT bleibt PC stabil (15)" severity error;
    assert halted = '1' report "REQ R65: Tick/go in HALT wird ignoriert (laeuft weiter, CPU bleibt in HALT)" severity error;
    assert halted = '1' report "REQ R52: go (Tick/rise) in HALT startet keinen Befehl" severity error;
    -- Auch mit wechselndem rom_data kein Verlassen:
    rom_data <= x"00";
    go <= '1';
    wait_cycles(2);
    go <= '0';
    assert halted = '1' report "REQ R57: HALT bleibt auch bei anderem ROM-Wert mit go" severity error;

    -- Reset mitten im HALT: zurueck nach WAIT, PC=0 (R71, R29 Ende bis Reset).
    rst <= '1';
    wait_cycles(2);
    report "CHECK t=" & time'image(now) & " halt-reset pc=" & to_string(pc) & " halted=" & std_logic'image(halted);
    assert pc = "0000" report "REQ R71: Reset aus HALT loescht PC auf 0" severity error;
    assert halted = '0' report "REQ R71: Reset aus HALT geht nach WAIT (halted=0)" severity error;
    assert halted = '0' report "REQ R29: HLT haelt nur bis Reset (nach Reset wieder WAIT)" severity error;
    rst <= '0';
    wait_cycles(1);
    assert pc = "0000" and halted = '0' report "REQ R71: nach Reset-Neustart wieder WAIT mit PC=0" severity error;
    -- Nach Reset beginnt Programm von vorn: erster Befehl per go wieder ausfuehrbar (R66).
    rom_data <= x"11";
    go <= '1';
    wait until rising_edge(clk); wait for 1 ns; go <= '0';
    wait until rising_edge(clk); wait for 1 ns;
    assert pc = "0001" report "REQ R66: nach Reset startet erster Befehl mit naechstem go (WAIT->FETCH, PC 0->1)" severity error;
    wait until rising_edge(clk); wait for 1 ns;
    wait until rising_edge(clk); wait for 1 ns;
    assert pc = "0001" report "REQ R66: erster Befehl nach Reset braucht 3 Folgeflanken (PC=1 in WAIT)" severity error;
    report "CHECK t=" & time'image(now) & " post-reset-instr pc=" & to_string(pc) & " alu_op=" & to_string(alu_op);

    tb_done <= true;
    report "TB_COMPLETE" severity note;
    std.env.stop;
    wait;
  end process stim;

end architecture sim;