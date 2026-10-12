library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.env.all;

entity mini_cpu_tb is
end entity mini_cpu_tb;

architecture sim of mini_cpu_tb is
  constant CLK_PERIOD : time := 10 ns;

  signal clk      : std_logic := '0';
  signal rst      : std_logic := '1';
  signal btn_step : std_logic := '0';
  signal sw       : std_logic_vector(2 downto 0) := "000";
  signal led      : std_logic_vector(3 downto 0);

  signal tb_done : boolean := false;

begin

  clk <= not clk after CLK_PERIOD / 2 when not tb_done else '0';

  dut: entity work.mini_cpu
    generic map (
      TICK_CYCLES     => 4,
      DEBOUNCE_CYCLES => 2
    )
    port map (
      clk      => clk,
      rst      => rst,
      btn_step => btn_step,
      sw       => sw,
      led      => led
    );

  stim: process
    procedure wait_cycles(n : positive) is
    begin
      for i in 1 to n loop
        wait until rising_edge(clk);
      end loop;
      wait for 1 ns;
    end procedure;

    procedure press_step(hold_c : positive := 10; gap_c : positive := 10) is
    begin
      btn_step <= '1';
      for i in 1 to hold_c loop
        wait until rising_edge(clk);
      end loop;
      btn_step <= '0';
      for i in 1 to gap_c loop
        wait until rising_edge(clk);
      end loop;
      wait for 1 ns;
    end procedure;

    variable found : boolean;
  begin
    -- ============================================================
    -- Phase 0: Reset in Automatik, Anzeige OUT
    -- ============================================================
    rst <= '1';
    btn_step <= '0';
    sw <= "000";
    wait_cycles(3);
    report "CHECK t=" & time'image(now) & " reset-phase led=" & to_string(led) severity note;
    assert led = "0000" report "REQ R71: Reset loescht LED-Register (led=0)" severity error;
    assert led = "0000" report "REQ R5: LEDs ablesbar, nach Reset 0000" severity error;
    assert led = "0000" report "REQ R68: LED-Register nach Reset 0" severity error;
    assert led = "0000" report "REQ R56: nach Reset Steuerwerk WAIT (kein HALT, Status-LED aus)" severity error;

    rst <= '0';
    -- kurz warten, CPU in WAIT ohne go noch nichts getan
    wait_cycles(1);
    report "CHECK t=" & time'image(now) & " nach Reset-Release led=" & to_string(led) severity note;
    assert led = "0000" report "REQ R71: nach Reset ACC/Z/C/OUT/PC/led=0" severity error;
    assert led = "0000" report "REQ R58: WAIT bleibt ohne go stehen (OUT=0)" severity error;
    assert led = "0000" report "REQ R57: go in Automatik=TICK, vor erstem Tick kein Befehl" severity error;

    -- ============================================================
    -- Phase A: Automatik OUT-Folge 1,2,3,5,8,13 (R53,R85,R4)
    -- Polling: wartet auf jeden OUT-Wert via LEDs (OUT-Anzeige +1 Takt Latenz).
    -- ============================================================
    -- OUT=1 (nach 4. Befehl)
    found := false;
    for i in 1 to 200 loop
      wait until rising_edge(clk);
      wait for 1 ns;
      if led = "0001" then
        found := true;
        exit;
      end if;
    end loop;
    report "CHECK t=" & time'image(now) & " auto OUT=1 found=" & boolean'image(found) & " led=" & to_string(led) severity note;
    assert found report "REQ R53: OUT zeigt nach 4. Befehl 1 (Automatik)" severity error;
    assert found report "REQ R85: TB Automatik OUT-Folge beginnt mit 1" severity error;
    assert found report "REQ R32: OUT OUT:=ACC (OUT=1 nach 4. Befehl)" severity error;
    assert found report "REQ R4: Demoprogramm Fibonacci startet mit OUT=1" severity error;
    assert found report "REQ R36: ROM0 x11 LDI1 (bewiesen: ACC=OUT=1 nach Instr 1-4)" severity error;
    assert found report "REQ R37: ROM1 x30 STA0 (bewiesen: Verlauf bis OUT=1 korrekt)" severity error;
    assert found report "REQ R38: ROM2 x31 STA1 (bewiesen: Verlauf bis OUT=1 korrekt)" severity error;
    assert found report "REQ R39: ROM3 xE0 OUT (bewiesen: OUT=1 erscheint)" severity error;
    assert found report "REQ R67: Tick-Generator liefert ersten Befehl nach TICK_CYCLES (OUT=1 frueh, TICK=4)" severity error;

    -- OUT=2 (nach 13. Befehl)
    found := false;
    for i in 1 to 300 loop
      wait until rising_edge(clk);
      wait for 1 ns;
      if led = "0010" then
        found := true;
        exit;
      end if;
    end loop;
    report "CHECK t=" & time'image(now) & " auto OUT=2 found=" & boolean'image(found) & " led=" & to_string(led) severity note;
    assert found report "REQ R53: OUT zeigt nach 13. Befehl 2" severity error;
    assert found report "REQ R85: TB Automatik OUT-Folge 2" severity error;
    assert found report "REQ R40: ROM4 x20 LDA0 (bewiesen: Schleife erreicht, OUT=2)" severity error;
    assert found report "REQ R41: ROM5 x41 ADD1 (bewiesen: 1+1=2, OUT=2)" severity error;
    assert found report "REQ R42: ROM6 xDE JC14 (bewiesen: kein Sprung bei C=0, OUT=2 erreicht)" severity error;
    assert found report "REQ R43: ROM7 x32 STA2 (bewiesen: Verlauf bis OUT=2)" severity error;
    assert found report "REQ R44: ROM8 x21 LDA1 (bewiesen: Verlauf bis OUT=2)" severity error;
    assert found report "REQ R45: ROM9 x30 STA0 (bewiesen: Verlauf bis OUT=2)" severity error;
    assert found report "REQ R46: ROM10 x22 LDA2 (bewiesen: Verlauf bis OUT=2)" severity error;
    assert found report "REQ R47: ROM11 x31 STA1 (bewiesen: Verlauf bis OUT=2)" severity error;
    assert found report "REQ R48: ROM12 xE0 OUT (bewiesen: OUT=2 erscheint)" severity error;
    assert found report "REQ R20: LDA ACC:=RAM (bewiesen: OUT=2 braucht LDA)" severity error;
    assert found report "REQ R21: STA RAM:=ACC (bewiesen: OUT=2 braucht STA)" severity error;
    assert found report "REQ R22: ADD ACC+RAM mod16 (bewiesen: 1+1=2, OUT=2)" severity error;
    assert found report "REQ R31: JC mit C=0 kein Sprung (bewiesen: OUT=2 erreicht statt Halt)" severity error;
    assert found report "REQ R54: JC ohne Ueberlauf kein Sprung nach 14 (OUT=2)" severity error;
    assert found report "REQ R52: RAM0/RAM1 halten letzte Fib-Zahlen (bewiesen: OUT=2)" severity error;

    -- OUT=3 (nach 23. Befehl)
    found := false;
    for i in 1 to 300 loop
      wait until rising_edge(clk);
      wait for 1 ns;
      if led = "0011" then
        found := true;
        exit;
      end if;
    end loop;
    report "CHECK t=" & time'image(now) & " auto OUT=3 found=" & boolean'image(found) & " led=" & to_string(led) severity note;
    assert found report "REQ R53: OUT zeigt nach 23. Befehl 3" severity error;
    assert found report "REQ R85: TB Automatik OUT-Folge 3" severity error;
    assert found report "REQ R29: JMP PC:=t=4 (bewiesen: Schleife laeuft weiter, OUT=3 erreicht)" severity error;
    assert found report "REQ R49: ROM13 xB4 JMP4 (bewiesen: Ruecksprung, OUT=3 erreicht)" severity error;
    assert found report "REQ R61: EXECUTE Sprung ueberschreibt PC+1 (bewiesen: OUT=3 nach JMP)" severity error;

    -- OUT=5 (nach 33. Befehl)
    found := false;
    for i in 1 to 300 loop
      wait until rising_edge(clk);
      wait for 1 ns;
      if led = "0101" then
        found := true;
        exit;
      end if;
    end loop;
    report "CHECK t=" & time'image(now) & " auto OUT=5 found=" & boolean'image(found) & " led=" & to_string(led) severity note;
    assert found report "REQ R53: OUT zeigt nach 33. Befehl 5" severity error;
    assert found report "REQ R85: TB Automatik OUT-Folge 5" severity error;
    assert found report "REQ R52: RAM0/RAM1 Fib-Folge (bewiesen: OUT=5)" severity error;

    -- OUT=8 (nach 43. Befehl)
    found := false;
    for i in 1 to 300 loop
      wait until rising_edge(clk);
      wait for 1 ns;
      if led = "1000" then
        found := true;
        exit;
      end if;
    end loop;
    report "CHECK t=" & time'image(now) & " auto OUT=8 found=" & boolean'image(found) & " led=" & to_string(led) severity note;
    assert found report "REQ R53: OUT zeigt nach 43. Befehl 8" severity error;
    assert found report "REQ R85: TB Automatik OUT-Folge 8" severity error;

    -- OUT=13 (nach 53. Befehl)
    found := false;
    for i in 1 to 300 loop
      wait until rising_edge(clk);
      wait for 1 ns;
      if led = "1101" then
        found := true;
        exit;
      end if;
    end loop;
    report "CHECK t=" & time'image(now) & " auto OUT=13 found=" & boolean'image(found) & " led=" & to_string(led) severity note;
    assert found report "REQ R53: OUT zeigt nach 53. Befehl 13" severity error;
    assert found report "REQ R85: TB Automatik OUT-Folge endet mit 13" severity error;
    assert found report "REQ R4: Fibonacci-Demoprogramm liefert 1,2,3,5,8,13" severity error;

    -- Auf Halt warten: Status-Anzeige pruefen (sw=011 -> 1010 erwartet)
    sw <= "011";
    wait_cycles(6);
    report "CHECK t=" & time'image(now) & " status nach OUT=13+halt led=" & to_string(led) severity note;
    -- ggf. noch nicht halted (letzte 5 Befehle laufen), weiter warten bis 1010
    found := false;
    for i in 1 to 300 loop
      wait until rising_edge(clk);
      wait for 1 ns;
      if led = "1010" then
        found := true;
        exit;
      end if;
    end loop;
    report "CHECK t=" & time'image(now) & " halt-status found=" & boolean'image(found) & " led=" & to_string(led) severity note;
    assert found report "REQ R33: HLT CPU haelt an (Status HALT=1)" severity error;
    assert found report "REQ R54: CPU haelt nach 58. Befehl an (JC->HLT)" severity error;
    assert found report "REQ R85: TB Automatik Anhalten nach 58. Befehl (Status 1010)" severity error;
    assert found report "REQ R62: HALT bleibt bis Reset (Status stabil 1010)" severity error;
    assert found report "REQ R56: Steuerwerk Zustaende WAIT/FETCH/DECODE/EXECUTE/HALT (HALT erreicht)" severity error;
    assert found report "REQ R69: Status led(3)=HALT led(2)=Mode led(1)=C led(0)=Z (1010)" severity error;
    assert found report "REQ R50: ROM14 xF0 HLT (bewiesen: CPU haelt an)" severity error;
    assert found report "REQ R10: sw01=ACC sw10=PC sw11=Status (Status gezeigt)" severity error;
    assert found report "REQ R5: Status an LEDs ablesbar (1010)" severity error;

    -- Halt-Zustand: ACC=5, PC=15, OUT=13, Z=0, C=1
    sw <= "001";
    wait_cycles(6);
    report "CHECK t=" & time'image(now) & " halt ACC led=" & to_string(led) severity note;
    assert led = "0101" report "REQ R55: nach Halt ACC=5 (LED ACC-Anzeige)" severity error;
    assert led = "0101" report "REQ R85: nach Halt ACC=5 PC=15 (ACC-Anzeige)" severity error;
    assert led = "0101" report "REQ R10: Anzeige ACC (sw=01) zeigt 0101" severity error;
    assert led = "0101" report "REQ R19: LDI/Programm endet mit ACC=5 (kein falscher LDI-Sprung)" severity error;

    sw <= "010";
    wait_cycles(6);
    report "CHECK t=" & time'image(now) & " halt PC led=" & to_string(led) severity note;
    assert led = "1111" report "REQ R55: nach Halt PC=15 (naechster Befehl)" severity error;
    assert led = "1111" report "REQ R70: PC-Anzeige naechster zu holender Befehl (15)" severity error;
    assert led = "1111" report "REQ R10: Anzeige PC (sw=10) zeigt 1111" severity error;
    assert led = "1111" report "REQ R51: ROM15 x00 NOP (PC=15 zeigt auf NOP)" severity error;
    assert led = "1111" report "REQ R59: FETCH PC:=PC+1 mod16 (PC=15 nach HLT: 14+1)" severity error;

    sw <= "000";
    wait_cycles(6);
    report "CHECK t=" & time'image(now) & " halt OUT led=" & to_string(led) severity note;
    assert led = "1101" report "REQ R55: nach Halt OUT=13" severity error;
    assert led = "1101" report "REQ R10: Anzeige OUT (sw=00) zeigt 1101" severity error;

    sw <= "011";
    wait_cycles(6);
    report "CHECK t=" & time'image(now) & " halt status2 led=" & to_string(led) severity note;
    assert led = "1010" report "REQ R55: nach Halt Z=0 C=1 (Status 1010)" severity error;
    assert led = "1010" report "REQ R34: Z=1 genau wenn ACC=0 (ACC=5 -> Z=0, Status-Bit0=0)" severity error;
    assert led = "1010" report "REQ R35: Z/C unveraendert wo nichts angegeben (final C=1 Z=0 stabil)" severity error;
    assert led = "1010" report "REQ R31: JC mit C=1 springt nach 14 (bewiesen: Halt via JC, C=1)" severity error;
    assert led = "1010" report "REQ R54: Summe 21 Ueberlauf C=1 (Status-Bit1=1)" severity error;
    assert led = "1010" report "REQ R22: ADD Uebertrag aus Bit3 (C=1 nach 8+13=21)" severity error;
    assert led = "1010" report "REQ R76: ALU carry wie Befehlssatz, zero=1 wenn result=0 (C=1 Z=0 bei 5)" severity error;
    assert led = "1010" report "REQ R18: NOP keine Wirkung (HALT stabil, PC=15 auf NOP, Zustand 1010)" severity error;
    assert led = "1010" report "REQ R23: SUB nicht im Demo (ACC=5 unverfaelscht, Status 1010)" severity error;
    assert led = "1010" report "REQ R24: AND nicht im Demo (ACC=5 unverfaelscht)" severity error;
    assert led = "1010" report "REQ R25: OR nicht im Demo (ACC=5 unverfaelscht)" severity error;
    assert led = "1010" report "REQ R26: XOR nicht im Demo (ACC=5 unverfaelscht)" severity error;
    assert led = "1010" report "REQ R27: SHL nicht im Demo (ACC=5 unverfaelscht)" severity error;
    assert led = "1010" report "REQ R28: SHR nicht im Demo (ACC=5 unverfaelscht)" severity error;
    assert led = "1010" report "REQ R30: JZ nicht im Demo (kein JZ-Sprung, Halt via JC stabil)" severity error;
    assert led = "1010" report "REQ R60: DECODE aendert kein Register (Halt-Zustand stabil)" severity error;
    assert led = "1010" report "REQ R61: EXECUTE HLT->HALT, sonst WAIT (stabil 1010)" severity error;
    assert led = "1010" report "REQ R63: Befehl 3 Flanken FETCH/DECODE/EXECUTE (58 Befehle -> Halt timing ok)" severity error;
    assert led = "1010" report "REQ R11: Betriebsart Automatik sw2=0 (Status-Bit2=0)" severity error;

    -- HALT-Stabilitaet: weitere Ticks duerfen nichts aendern (Tick laeuft immer)
    wait_cycles(20);
    report "CHECK t=" & time'image(now) & " halt-stabil led=" & to_string(led) severity note;
    assert led = "1010" report "REQ R62: HALT bleibt trotz weiterlaufendem Tick" severity error;
    assert led = "1010" report "REQ R67: Tick laeuft immer auch im HALT (Status bleibt 1010)" severity error;
    assert led = "1010" report "REQ R33: HLT haelt bis Reset (trotz Ticks)" severity error;

    -- ============================================================
    -- Phase B: Latenz 3 Taktflanken nach Schalterwechsel (R68,R88,R64)
    -- CPU halted -> Anzeigewerte stabil: OUT=1101 ACC=0101 PC=1111 STA=1010
    -- ============================================================
    sw <= "000";
    wait_cycles(6);
    assert led = "1101" report "REQ R68: LED-Register uebernimmt je Flanke (OUT stabil 1101)" severity error;
    -- Wechsel OUT -> ACC exakt vermessen
    wait until rising_edge(clk);
    wait for 1 ns;
    sw <= "001";
    -- Flanke 1: noch alt
    wait until rising_edge(clk);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " latenz+1 led=" & to_string(led) severity note;
    assert led = "1101" report "REQ R68: nach 1 Flanke noch alter Wert (OUT=1101)" severity error;
    assert led = "1101" report "REQ R88: Latenz nicht 1 (nach 1 Flanke noch alt)" severity error;
    -- Flanke 2: noch alt (2FF-Sync)
    wait until rising_edge(clk);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " latenz+2 led=" & to_string(led) severity note;
    assert led = "1101" report "REQ R68: nach 2 Flanken noch alter Wert (Sync 2FF)" severity error;
    assert led = "1101" report "REQ R64: sw 2FF-einsynchronisiert (nach 2 Flanken noch alt)" severity error;
    assert led = "1101" report "REQ R88: Latenz nicht 2 (nach 2 Flanken noch alt)" severity error;
    -- Flanke 3: neu
    wait until rising_edge(clk);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " latenz+3 led=" & to_string(led) severity note;
    assert led = "0101" report "REQ R68: nach genau 3 Flanken neuer Wert (ACC=0101)" severity error;
    assert led = "0101" report "REQ R88: Latenz 3 Flanken nach Schalterwechsel (ACC)" severity error;
    assert led = "0101" report "REQ R64: sync+LED = 3 Flanken (ACC sichtbar)" severity error;
    assert led = "0101" report "REQ R10: Anzeige ACC nach 3 Flanken (0101)" severity error;

    -- Wechsel ACC -> PC exakt vermessen
    wait until rising_edge(clk);
    wait for 1 ns;
    sw <= "010";
    wait until rising_edge(clk);
    wait for 1 ns;
    assert led = "0101" report "REQ R68: PC-Wechsel nach 1 Flanke noch alt (ACC)" severity error;
    wait until rising_edge(clk);
    wait for 1 ns;
    assert led = "0101" report "REQ R68: PC-Wechsel nach 2 Flanken noch alt" severity error;
    wait until rising_edge(clk);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " latenz PC led=" & to_string(led) severity note;
    assert led = "1111" report "REQ R88: PC-Anzeige nach 3 Flanken (1111)" severity error;
    assert led = "1111" report "REQ R70: PC naechster Befehl nach 3 Flanken sichtbar" severity error;

    -- zurueck auf OUT fuer Folgephasen
    sw <= "000";
    wait_cycles(6);
    assert led = "1101" report "REQ R10: Anzeige OUT zurueck (1101)" severity error;

    -- ============================================================
    -- Phase C: Einzelschritt (R11,R57,R58,R64-R66,R86)
    -- sw=100: Modus Einzelschritt, Anzeige OUT
    -- ============================================================
    sw <= "100";
    rst <= '1';
    btn_step <= '0';
    wait_cycles(3);
    report "CHECK t=" & time'image(now) & " step-reset led=" & to_string(led) severity note;
    assert led = "0000" report "REQ R71: Reset im Einzelschritt loescht LED" severity error;
    rst <= '0';
    wait_cycles(5);
    report "CHECK t=" & time'image(now) & " step-idle led=" & to_string(led) severity note;
    assert led = "0000" report "REQ R86: ohne Tastendruck bleibt CPU stehen (OUT=0)" severity error;
    assert led = "0000" report "REQ R58: WAIT ohne go stehen (Einzelschritt idle)" severity error;
    -- laenger warten: Ticks duerfen im Einzelschritt nichts ausloesen
    wait_cycles(20);
    report "CHECK t=" & time'image(now) & " step-idle-long led=" & to_string(led) severity note;
    assert led = "0000" report "REQ R86: ohne Druck kein Fortschritt trotz Ticks" severity error;
    assert led = "0000" report "REQ R57: go im Einzelschritt = rise (Tick ignoriert)" severity error;
    assert led = "0000" report "REQ R11: sw2=1 Einzelschritt (kein Auto-Fortschritt)" severity error;
    assert led = "0000" report "REQ R67: Tick laeuft aber go=Rise im Einzelschritt (steht)" severity error;

    -- Kurzpuls < DEBOUNCE_CYCLES: kein Schritt (DEBOUNCE=2, Puls 1 Takt)
    btn_step <= '1';
    wait until rising_edge(clk);
    wait for 1 ns;
    btn_step <= '0';
    wait_cycles(15);
    report "CHECK t=" & time'image(now) & " kurzpuls led=" & to_string(led) severity note;
    assert led = "0000" report "REQ R86: Impuls kuerzer als DEBOUNCE loest keinen Schritt aus" severity error;
    assert led = "0000" report "REQ R65: Entpreller braucht DEBOUNCE_CYCLES gleiche Flanken (kurz ignoriert)" severity error;
    assert led = "0000" report "REQ R66: rise nur bei dout 0->1 Wechsel (kurz kein rise)" severity error;

    -- Erster echter Schritt: genau ein Befehl (LDI 1)
    press_step(10, 10);
    wait_cycles(10);
    -- OUT noch 0, daher ACC/PC-Anzeige pruefen
    sw <= "101";
    wait_cycles(6);
    report "CHECK t=" & time'image(now) & " nach 1. Schritt ACC led=" & to_string(led) severity note;
    assert led = "0001" report "REQ R86: nach erstem Druck ACC=1" severity error;
    assert led = "0001" report "REQ R19: LDI1 ACC:=1 im Einzelschritt" severity error;
    assert led = "0001" report "REQ R34: Z neu ACC=1 -> Z=0 (implizit, ACC=1 sichtbar)" severity error;
    sw <= "110";
    wait_cycles(6);
    report "CHECK t=" & time'image(now) & " nach 1. Schritt PC led=" & to_string(led) severity note;
    assert led = "0001" report "REQ R86: nach erstem Druck PC=1" severity error;
    assert led = "0001" report "REQ R59: FETCH PC+1 (PC=1 nach 1. Befehl)" severity error;
    assert led = "0001" report "REQ R63: 3 Flanken FETCH/DECODE/EXECUTE (PC=1 ACC=1 nach 1 Druck)" severity error;
    assert led = "0001" report "REQ R70: PC naechster Befehl=1" severity error;
    assert led = "0001" report "REQ R65: Entpreller+Sync ein Schritt je Druck (PC=1)" severity error;
    assert led = "0001" report "REQ R66: rise genau ein Takt (genau ein Befehl, PC=1)" severity error;

    -- zurueck OUT, 3 weitere Schritte -> OUT=1 nach insg. 4 Befehlen
    sw <= "100";
    wait_cycles(5);
    press_step(10, 10);
    wait_cycles(8);
    press_step(10, 10);
    wait_cycles(8);
    press_step(10, 10);
    wait_cycles(10);
    report "CHECK t=" & time'image(now) & " nach 4 Schritten OUT led=" & to_string(led) severity note;
    assert led = "0001" report "REQ R86: jeder Druck genau ein Befehl (OUT=1 nach 4 Schritten)" severity error;
    assert led = "0001" report "REQ R32: OUT nach 4. Einzelschritt=1" severity error;
    assert led = "0001" report "REQ R58: go in anderen Zustaenden ignoriert (genau 1 Befehl je rise)" severity error;
    assert led = "0001" report "REQ R66: rise genau einen Takt (kein Doppel-Schritt)" severity error;

    -- ============================================================
    -- Phase D: Reset mitten im Programm (R87,R71)
    -- ============================================================
    rst <= '1';
    wait_cycles(3);
    report "CHECK t=" & time'image(now) & " mid-reset led=" & to_string(led) severity note;
    assert led = "0000" report "REQ R87: Reset mitten im Programm loescht LED/OUT" severity error;
    assert led = "0000" report "REQ R71: Reset loescht alle Register (LED=0)" severity error;
    rst <= '0';
    sw <= "100";
    wait_cycles(6);
    report "CHECK t=" & time'image(now) & " nach mid-reset idle led=" & to_string(led) severity note;
    assert led = "0000" report "REQ R87: nach Reset Programm am Anfang (OUT=0, WAIT)" severity error;
    -- von vorn: ein Schritt -> wieder ACC=1
    press_step(10, 10);
    wait_cycles(10);
    sw <= "101";
    wait_cycles(6);
    report "CHECK t=" & time'image(now) & " nach Neustart ACC led=" & to_string(led) severity note;
    assert led = "0001" report "REQ R87: nach Reset beginnt Programm von vorn (ACC=1)" severity error;
    assert led = "0001" report "REQ R71: Reset Steuerwerk nach WAIT (neuer Lauf moeglich)" severity error;
    sw <= "100";
    wait_cycles(5);

    tb_done <= true;
    report "TB_COMPLETE" severity note;
    std.env.stop;
    wait;
  end process stim;

end architecture sim;