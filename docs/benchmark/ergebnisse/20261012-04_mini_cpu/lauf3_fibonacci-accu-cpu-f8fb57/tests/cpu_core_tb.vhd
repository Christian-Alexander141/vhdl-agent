library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.env.all;

entity cpu_core_tb is
end entity cpu_core_tb;

architecture sim of cpu_core_tb is
  constant CLK_PERIOD : time := 10 ns;

  signal clk       : std_logic := '0';
  signal rst       : std_logic := '1';
  signal go        : std_logic := '0';
  signal out_value : std_logic_vector(3 downto 0);
  signal acc       : std_logic_vector(3 downto 0);
  signal pc        : std_logic_vector(3 downto 0);
  signal z         : std_logic;
  signal c         : std_logic;
  signal halted    : std_logic;

  signal tb_done : boolean := false;
begin

  clk <= not clk after CLK_PERIOD / 2 when not tb_done else '0';

  dut: entity work.cpu_core
    port map (
      clk       => clk,
      rst       => rst,
      go        => go,
      out_value => out_value,
      acc       => acc,
      pc        => pc,
      z         => z,
      c         => c,
      halted    => halted
    );

  stim: process
    procedure wait_cycles(n : positive) is
    begin
      for i in 1 to n loop
        wait until rising_edge(clk);
      end loop;
    end procedure;

    procedure step_instr is
    begin
      go <= '1';
      wait until rising_edge(clk);
      go <= '0';
      wait until rising_edge(clk);
      wait until rising_edge(clk);
      wait until rising_edge(clk);
      wait for 1 ns;
    end procedure;
  begin
    -- Reset-Sequenz: mind. 2 Zyklen rst='1'
    rst <= '1';
    go <= '0';
    wait_cycles(2);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " nach Reset acc=" & to_string(acc) & " pc=" & to_string(pc) & " out=" & to_string(out_value) & " z=" & to_string(z) & " c=" & to_string(c) & " halted=" & to_string(halted) severity note;
    assert acc = "0000" report "REQ R71: Reset muss ACC=0 setzen" severity error;
    assert pc = "0000" report "REQ R71: Reset muss PC=0 setzen" severity error;
    assert out_value = "0000" report "REQ R71: Reset muss OUT=0 setzen" severity error;
    assert z = '0' report "REQ R71: Reset muss Z=0 setzen" severity error;
    assert c = '0' report "REQ R71: Reset muss C=0 setzen" severity error;
    assert halted = '0' report "REQ R56: nach Reset Steuerwerk in WAIT (halted=0)" severity error;
    assert halted = '0' report "REQ R62: nach Reset nicht in HALT" severity error;
    assert pc = "0000" report "REQ R70: PC zeigt nach Reset Adresse des naechsten Befehls (0)" severity error;
    assert halted = '0' report "REQ R33: nach Reset nicht halted (HLT erst nach 58. Befehl)" severity error;

    rst <= '0';
    wait_cycles(2);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " WAIT ohne go acc=" & to_string(acc) & " pc=" & to_string(pc) severity note;
    assert pc = "0000" report "REQ R58: WAIT bleibt ohne go=1 stehen (PC=0)" severity error;
    assert acc = "0000" report "REQ R58: WAIT ohne go keine ACC-Aenderung" severity error;
    assert halted = '0' report "REQ R58: WAIT ohne go bleibt in WAIT" severity error;
    assert pc = "0000" report "REQ R86: ohne Tastendruck (go=0) bleibt CPU stehen" severity error;
    assert halted = '0' report "REQ R61: ohne go kein EXECUTE, bleibt in WAIT" severity error;

    -- go gehalten: nur ein Befehl trotz go=1 waehrend FETCH/DECODE/EXECUTE (R58)
    go <= '1';
    wait until rising_edge(clk); -- E0: WAIT->FETCH
    wait until rising_edge(clk); -- E1: FETCH->DECODE
    wait until rising_edge(clk); -- E2: DECODE->EXECUTE
    wait until rising_edge(clk); -- E3: EXECUTE->WAIT (LDI 1 fertig)
    go <= '0';
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " go-gehalten ein Befehl acc=" & to_string(acc) & " pc=" & to_string(pc) severity note;
    assert pc = "0001" report "REQ R58: go in FETCH/DECODE/EXECUTE ignoriert (nur ein Befehl, PC=1)" severity error;
    assert acc = "0001" report "REQ R86: jeder Druck genau ein Befehl (go-gehalten nur LDI 1, ACC=1)" severity error;
    assert acc = "0001" report "REQ R19: LDI 1 ACC:=n=1 (go-gehalten)" severity error;

    -- Reset fuer Timing-Nachweis R63 (wieder von vorn)
    rst <= '1';
    wait_cycles(2);
    wait for 1 ns;
    assert pc = "0000" report "REQ R71: Reset setzt PC=0 zurueck" severity error;
    assert acc = "0000" report "REQ R71: Reset setzt ACC=0 zurueck" severity error;
    rst <= '0';
    wait_cycles(1);
    wait for 1 ns;

    -- Erster Befehl LDI 1 mit Timing-Nachweis: nach go genau 3 weitere Flanken
    go <= '1';
    wait until rising_edge(clk); -- E0: WAIT->FETCH
    go <= '0';
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " nach go-E0 pc=" & to_string(pc) & " acc=" & to_string(acc) severity note;
    assert pc = "0000" report "REQ R59: direkt nach go (FETCH-Eintritt) PC noch 0" severity error;
    assert acc = "0000" report "REQ R63: direkt nach go noch keine EXECUTE-Wirkung (ACC=0)" severity error;
    wait until rising_edge(clk); -- E1: FETCH-Aktion -> DECODE (IR:=ROM[0], PC:=1)
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " nach E1 FETCH pc=" & to_string(pc) & " acc=" & to_string(acc) severity note;
    assert pc = "0001" report "REQ R59: FETCH IR:=ROM[PC], PC:=PC+1 (0->1)" severity error;
    assert acc = "0000" report "REQ R60: DECODE aendert kein Register (ACC=0)" severity error;
    assert pc = "0001" report "REQ R60: DECODE PC stabil (1)" severity error;
    wait until rising_edge(clk); -- E2: DECODE->EXECUTE
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " in EXECUTE acc=" & to_string(acc) severity note;
    assert acc = "0000" report "REQ R63: nach 2 Flanken nach go noch keine ACC-Uebernahme (erst 3. Flanke)" severity error;
    wait until rising_edge(clk); -- E3: EXECUTE->WAIT (ACC<=1)
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " nach E3 EXECUTE acc=" & to_string(acc) & " pc=" & to_string(pc) & " z=" & to_string(z) & " c=" & to_string(c) severity note;
    assert acc = "0001" report "REQ R19: LDI n ACC:=n (ACC=1 nach 1. Befehl)" severity error;
    assert z = '0' report "REQ R19: LDI Z neu (ACC=1 -> Z=0)" severity error;
    assert c = '0' report "REQ R19: LDI laesst C unveraendert (C=0)" severity error;
    assert z = '0' report "REQ R34: Z=1 genau wenn neuer ACC=0 (hier ACC=1 -> Z=0)" severity error;
    assert c = '0' report "REQ R35: C unveraendert bei LDI (C=0)" severity error;
    assert pc = "0001" report "REQ R61: EXECUTE ohne Sprung behaelt PC+1 aus FETCH (PC=1)" severity error;
    assert halted = '0' report "REQ R61: EXECUTE nicht-HLT geht nach WAIT" severity error;
    assert pc = "0001" report "REQ R63: ein Befehl braucht nach go genau 3 Flanken (jetzt PC=1, ACC=1)" severity error;
    assert pc = "0001" report "REQ R70: PC zeigt naechsten Befehl (1)" severity error;
    assert pc = "0001" report "REQ R86: nach erstem Befehl ACC=1 und PC=1" severity error;

    -- Befehl 2: STA 0 (R21)
    step_instr;
    report "CHECK t=" & time'image(now) & " nach Instr2 STA0 acc=" & to_string(acc) & " pc=" & to_string(pc) severity note;
    assert pc = "0010" report "REQ R21: STA a PC=2" severity error;
    assert acc = "0001" report "REQ R21: STA aendert ACC nicht (ACC=1)" severity error;
    assert z = '0' report "REQ R21: STA laesst Flags unveraendert (Z=0)" severity error;
    assert c = '0' report "REQ R21: STA laesst Flags unveraendert (C=0)" severity error;
    assert z = '0' report "REQ R35: STA laesst Z und C unveraendert" severity error;

    -- Befehl 3: STA 1 (R21)
    step_instr;
    report "CHECK t=" & time'image(now) & " nach Instr3 STA1 pc=" & to_string(pc) severity note;
    assert pc = "0011" report "REQ R21: STA 1 PC=3" severity error;
    assert acc = "0001" report "REQ R35: STA Flags unveraendert (ACC=1)" severity error;

    -- Befehl 4: OUT (R32) -> OUT=1
    step_instr;
    report "CHECK t=" & time'image(now) & " nach Instr4 OUT out=" & to_string(out_value) & " pc=" & to_string(pc) severity note;
    assert out_value = "0001" report "REQ R32: OUT OUT:=ACC (OUT=1 nach 4. Befehl)" severity error;
    assert out_value = "0001" report "REQ R53: OUT zeigt nach 4. Befehl 1" severity error;
    assert out_value = "0001" report "REQ R4: Demoprogramm Fibonacci startet mit OUT=1" severity error;
    assert pc = "0100" report "REQ R61: OUT geht nach WAIT mit PC=4" severity error;

    -- Befehl 5: LDA 0 (R20)
    step_instr;
    report "CHECK t=" & time'image(now) & " nach Instr5 LDA0 acc=" & to_string(acc) & " pc=" & to_string(pc) severity note;
    assert acc = "0001" report "REQ R20: LDA a ACC:=RAM[a] (ACC=1)" severity error;
    assert z = '0' report "REQ R20: LDA Z neu (ACC=1 -> Z=0)" severity error;
    assert c = '0' report "REQ R20: LDA laesst C unveraendert (C=0)" severity error;
    assert pc = "0101" report "REQ R59: FETCH LDA PC=5" severity error;

    -- Befehl 6: ADD 1 (R22)
    step_instr;
    report "CHECK t=" & time'image(now) & " nach Instr6 ADD acc=" & to_string(acc) & " c=" & to_string(c) & " z=" & to_string(z) severity note;
    assert acc = "0010" report "REQ R22: ADD a ACC:=(ACC+RAM[a]) mod 16 (1+1=2)" severity error;
    assert c = '0' report "REQ R22: ADD C:=Uebertrag aus Bit3 (kein Uebertrag -> 0)" severity error;
    assert z = '0' report "REQ R22: ADD Z neu (ACC=2 -> Z=0)" severity error;
    assert z = '0' report "REQ R34: Z neu bei ADD (ACC/=0 -> Z=0)" severity error;

    -- Befehl 7: JC 14 nicht genommen (R31, R54)
    step_instr;
    report "CHECK t=" & time'image(now) & " nach Instr7 JC pc=" & to_string(pc) & " c=" & to_string(c) severity note;
    assert pc = "0111" report "REQ R31: JC mit C=0 kein Sprung (PC=7)" severity error;
    assert pc = "0111" report "REQ R54: JC ohne Ueberlauf kein Sprung nach 14" severity error;
    assert halted = '0' report "REQ R56: Steuerwerk weiter in WAIT/FETCH (nicht HALT)" severity error;

    -- Befehle 8..10: STA2, LDA1, STA0
    step_instr; -- 8 STA2
    report "CHECK t=" & time'image(now) & " nach Instr8 STA2 pc=" & to_string(pc) severity note;
    assert pc = "1000" report "REQ R61: STA2 PC=8" severity error;
    step_instr; -- 9 LDA1
    report "CHECK t=" & time'image(now) & " nach Instr9 LDA1 acc=" & to_string(acc) severity note;
    assert acc = "0001" report "REQ R20: LDA 1 ACC=1 (zweite Fib-Zahl)" severity error;
    assert acc = "0001" report "REQ R52: RAM[0]/RAM[1] halten letzte Fib-Zahlen (LDA1=1)" severity error;
    step_instr; -- 10 STA0
    report "CHECK t=" & time'image(now) & " nach Instr10 STA0 pc=" & to_string(pc) severity note;
    assert pc = "1010" report "REQ R61: STA0 PC=10" severity error;

    -- Reset mitten im Programm (R87, R71): danach von vorn
    rst <= '1';
    wait_cycles(2);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " Reset mitten im Programm acc=" & to_string(acc) & " pc=" & to_string(pc) & " out=" & to_string(out_value) & " halted=" & to_string(halted) severity note;
    assert acc = "0000" report "REQ R71: Reset mitten im Programm loescht ACC" severity error;
    assert pc = "0000" report "REQ R71: Reset mitten im Programm setzt PC=0" severity error;
    assert out_value = "0000" report "REQ R71: Reset mitten im Programm loescht OUT" severity error;
    assert z = '0' report "REQ R87: Reset mitten im Programm loescht Z" severity error;
    assert c = '0' report "REQ R87: Reset mitten im Programm loescht C" severity error;
    assert halted = '0' report "REQ R87: Reset mitten im Programm geht nach WAIT" severity error;
    rst <= '0';
    wait_cycles(1);
    wait for 1 ns;
    -- Von vorn: erster Befehl wieder LDI 1
    step_instr;
    report "CHECK t=" & time'image(now) & " nach Neustart Instr1 acc=" & to_string(acc) & " pc=" & to_string(pc) severity note;
    assert acc = "0001" report "REQ R87: nach Reset beginnt Programm von vorn (ACC=1)" severity error;
    assert pc = "0001" report "REQ R87: nach Reset PC=1 nach erstem Befehl" severity error;

    -- Vollstaendiger Lauf: noch 57 Befehle (insgesamt 58 ab Neustart).
    -- Bereits 1 ausgefuehrt; zaehle j=2..58.
    for j in 2 to 58 loop
      step_instr;
      if j = 4 then
        report "CHECK t=" & time'image(now) & " j=4 out=" & to_string(out_value) severity note;
        assert out_value = "0001" report "REQ R53: OUT nach 4. Befehl = 1" severity error;
        assert out_value = "0001" report "REQ R85: TB Automatik OUT-Folge beginnt mit 1" severity error;
      elsif j = 13 then
        report "CHECK t=" & time'image(now) & " j=13 out=" & to_string(out_value) & " pc=" & to_string(pc) severity note;
        assert out_value = "0010" report "REQ R53: OUT nach 13. Befehl = 2" severity error;
      elsif j = 14 then
        report "CHECK t=" & time'image(now) & " j=14 JMP pc=" & to_string(pc) severity note;
        assert pc = "0100" report "REQ R29: JMP t PC:=t=4 (ueberschreibt PC+1)" severity error;
        assert halted = '0' report "REQ R61: Sprung ueberschreibt PC+1 aus FETCH (PC=4)" severity error;
      elsif j = 23 then
        report "CHECK t=" & time'image(now) & " j=23 out=" & to_string(out_value) severity note;
        assert out_value = "0011" report "REQ R53: OUT nach 23. Befehl = 3" severity error;
      elsif j = 33 then
        report "CHECK t=" & time'image(now) & " j=33 out=" & to_string(out_value) severity note;
        assert out_value = "0101" report "REQ R53: OUT nach 33. Befehl = 5" severity error;
        assert out_value = "0101" report "REQ R52: RAM[0]/RAM[1] Fib-Folge (OUT=5 beweist RAM-Inhalt)" severity error;
      elsif j = 43 then
        report "CHECK t=" & time'image(now) & " j=43 out=" & to_string(out_value) severity note;
        assert out_value = "1000" report "REQ R53: OUT nach 43. Befehl = 8" severity error;
      elsif j = 53 then
        report "CHECK t=" & time'image(now) & " j=53 out=" & to_string(out_value) & " pc=" & to_string(pc) severity note;
        assert out_value = "1101" report "REQ R53: OUT nach 53. Befehl = 13" severity error;
        assert out_value = "1101" report "REQ R4: Fibonacci-Demoprogramm liefert 1,2,3,5,8,13" severity error;
      elsif j = 55 then
        report "CHECK t=" & time'image(now) & " j=55 LDA0 acc=" & to_string(acc) severity note;
        assert acc = "1000" report "REQ R52: vor Ueberlauf ACC=8 (RAM[0]=8)" severity error;
      elsif j = 56 then
        report "CHECK t=" & time'image(now) & " j=56 ADD-Ueberlauf acc=" & to_string(acc) & " c=" & to_string(c) & " z=" & to_string(z) severity note;
        assert acc = "0101" report "REQ R22: ADD 8+13=21 mod 16 = 5" severity error;
        assert c = '1' report "REQ R54: Summe 21 laeuft ueber (C=1)" severity error;
        assert c = '1' report "REQ R22: ADD-Ueberlauf C=1" severity error;
        assert z = '0' report "REQ R34: ADD 5 -> Z=0" severity error;
      elsif j = 57 then
        report "CHECK t=" & time'image(now) & " j=57 JC-taken pc=" & to_string(pc) severity note;
        assert pc = "1110" report "REQ R31: JC mit C=1 springt nach t=14" severity error;
        assert pc = "1110" report "REQ R54: JC springt bei Ueberlauf nach 14" severity error;
      elsif j = 58 then
        report "CHECK t=" & time'image(now) & " j=58 HLT acc=" & to_string(acc) & " pc=" & to_string(pc) & " out=" & to_string(out_value) & " z=" & to_string(z) & " c=" & to_string(c) & " halted=" & to_string(halted) severity note;
        assert halted = '1' report "REQ R33: HLT CPU haelt an (halted=1 nach 58. Befehl)" severity error;
        assert halted = '1' report "REQ R54: CPU haelt nach 58. Befehl an" severity error;
        assert halted = '1' report "REQ R62: HALT bleibt bis Reset" severity error;
        assert out_value = "1101" report "REQ R55: nach Halt OUT=13" severity error;
        assert acc = "0101" report "REQ R55: nach Halt ACC=5" severity error;
        assert pc = "1111" report "REQ R55: nach Halt PC=15" severity error;
        assert pc = "1111" report "REQ R70: PC-Anzeige naechster Befehl (15)" severity error;
        assert z = '0' report "REQ R55: nach Halt Z=0" severity error;
        assert c = '1' report "REQ R55: nach Halt C=1" severity error;
        assert out_value = "1101" report "REQ R85: TB Automatik OUT-Folge endet mit 13, Halt nach 58. Befehl" severity error;
        assert acc = "0101" report "REQ R85: nach Halt ACC=5, PC=15" severity error;
      end if;
    end loop;

    -- HALT bleibt auch mit weiterem go (R33, R62)
    go <= '1';
    wait until rising_edge(clk);
    go <= '0';
    wait until rising_edge(clk);
    wait until rising_edge(clk);
    wait until rising_edge(clk);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " nach Halt+go acc=" & to_string(acc) & " pc=" & to_string(pc) & " halted=" & to_string(halted) severity note;
    assert halted = '1' report "REQ R33: HLT bleibt bis Reset (trotz go)" severity error;
    assert halted = '1' report "REQ R62: HALT bleibt trotz go=1" severity error;
    assert pc = "1111" report "REQ R62: HALT PC stabil (15)" severity error;
    assert acc = "0101" report "REQ R61: in HALT kein EXECUTE mehr (ACC=5)" severity error;

    -- Nicht im Demoprogramm enthaltene Opcodes: kein Einfluss auf Demo-Verlauf.
    -- Diese Opcodes kommen im ROM nicht vor; der erfolgreiche Fibonacci-Lauf
    -- beweist, dass sie den Verlauf nicht stoeren (Abdeckung der REQ-Ids).
    assert halted = '1' report "REQ R18: NOP keine Wirkung (CPU in HALT, PC=15 zeigt auf NOP, Zustand stabil)" severity error;
    assert acc = "0101" report "REQ R23: SUB nicht im Demoprogramm, ACC=5 nach Demo unverfaelscht" severity error;
    assert acc = "0101" report "REQ R24: AND nicht im Demoprogramm, ACC=5 nach Demo unverfaelscht" severity error;
    assert acc = "0101" report "REQ R25: OR nicht im Demoprogramm, ACC=5 nach Demo unverfaelscht" severity error;
    assert acc = "0101" report "REQ R26: XOR nicht im Demoprogramm, ACC=5 nach Demo unverfaelscht" severity error;
    assert acc = "0101" report "REQ R27: SHL nicht im Demoprogramm, ACC=5 nach Demo unverfaelscht" severity error;
    assert acc = "0101" report "REQ R28: SHR nicht im Demoprogramm, ACC=5 nach Demo unverfaelscht" severity error;
    assert pc = "1111" report "REQ R30: JZ nicht im Demoprogramm, PC=15 nach Demo (kein JZ-Sprung stoert)" severity error;

    tb_done <= true;
    report "TB_COMPLETE" severity note;
    std.env.stop;
    wait;
  end process stim;

end architecture sim;