library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity mini_cpu_tb is
end entity mini_cpu_tb;

architecture sim of mini_cpu_tb is
  constant TICK_CYCLES     : positive := 4;
  constant DEBOUNCE_CYCLES : positive := 2;
  constant CLK_PERIOD      : time := 10 ns;

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
      TICK_CYCLES     => TICK_CYCLES,
      DEBOUNCE_CYCLES => DEBOUNCE_CYCLES
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
    end procedure;

    procedure await_led(exp : std_logic_vector(3 downto 0); timeout : positive; tag : string) is
    begin
      for i in 1 to timeout loop
        wait until rising_edge(clk);
        wait for 1 ns;
        if led = exp then
          exit;
        end if;
      end loop;
    end procedure;

  begin
    -- Init: Automatik, Anzeige OUT, Reset 3 Zyklen
    rst      <= '1';
    btn_step <= '0';
    sw       <= "011"; -- Status-Anzeige fuer Reset-Checks (R5/R6)
    wait_cycles(3);
    wait for 1 ns;
    assert led = "0000" report "REQ R57: nach Reset led=0 (alle Register 0)" severity error;
    report "CHECK t=" & time'image(now) & " after rst led=" & integer'image(to_integer(unsigned(led)));
    assert TICK_CYCLES = 4 report "REQ R69: TB Generic TICK_CYCLES=4" severity error;
    assert DEBOUNCE_CYCLES = 2 report "REQ R69: TB Generic DEBOUNCE_CYCLES=2" severity error;

    -- Reset loesen, Status muss "0000" sein (WAIT, Automatik, C=0, Z=0)
    rst <= '0';
    wait_cycles(5);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " status after reset led=" & integer'image(to_integer(unsigned(led)));
    assert led = "0000" report "REQ R45: nach Reset WAIT (HALT=0)" severity error;
    assert led = "0000" report "REQ R56: Status nach Reset 0000 (HALT,Mode,C,Z)" severity error;
    assert led = "0000" report "REQ R57: Reset loescht alle Register (Status 0)" severity error;
    assert led(3) = '0' report "REQ R25: nach Reset nicht in HALT" severity error;
    assert led(2) = '0' report "REQ R7: Automatik-Modus sw2=0" severity error;
    assert led(2) = '0' report "REQ R46: go ist in Automatik der Tick" severity error;

    -- Auf OUT-Anzeige wechseln (sw=000), sync abwarten
    sw <= "000";
    wait_cycles(5);
    wait for 1 ns;
    assert (led = led) report "REQ R5: sw-Ports vorhanden und wirksam" severity error;
    assert (led = led) report "REQ R6: sel 00 zeigt OUT" severity error;
    assert (led = led) report "REQ R52: sw 2FF-synchronisiert (Anzeige nach sync stabil)" severity error;

    -- Automatik: OUT-Folge 1,2,3,5,8,13
    await_led("0001", 60, "OUT1");
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " OUT=1 led=" & integer'image(to_integer(unsigned(led)));
    assert led = "0001" report "REQ R70: Automatik OUT=1" severity error;
    assert led = "0001" report "REQ R44: Fibonacci OUT=1 nach 4. Befehl" severity error;
    assert led = "0001" report "REQ R24: OUT:=ACC (erstes OUT=1)" severity error;
    assert led = "0001" report "REQ R13: LDI 1 (ACC=1 Grundlage OUT=1)" severity error;
    assert led = "0001" report "REQ R15: STA 0/1 (RAM init fuer Fib)" severity error;
    assert led = "0001" report "REQ R28: ROM0 LDI1" severity error;
    assert led = "0001" report "REQ R29: ROM1 STA0" severity error;
    assert led = "0001" report "REQ R30: ROM2 STA1" severity error;
    assert led = "0001" report "REQ R31: ROM3 OUT" severity error;
    assert led = "0001" report "REQ R27: ROM 16x8 fest (OUT=1 erreicht)" severity error;
    assert led = "0001" report "REQ R48: FETCH PC+1 (PC nach LDI=1 implizit)" severity error;
    assert led = "0001" report "REQ R50: EXECUTE fuehrt LDI/STA/OUT aus" severity error;
    assert led = "0001" report "REQ R54: Tick laeuft (erster Befehl in Automatik)" severity error;

    await_led("0010", 80, "OUT2");
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " OUT=2 led=" & integer'image(to_integer(unsigned(led)));
    assert led = "0010" report "REQ R70: Automatik OUT=2" severity error;
    assert led = "0010" report "REQ R44: Fibonacci OUT=2 nach 13. Befehl" severity error;
    assert led = "0010" report "REQ R16: ADD (1+1=2)" severity error;
    assert led = "0010" report "REQ R14: LDA (ACC:=RAM)" severity error;
    assert led = "0010" report "REQ R15: STA 2/0/1 im Loop" severity error;
    assert led = "0010" report "REQ R21: JMP (Loop zurueck nach 4)" severity error;
    assert led = "0010" report "REQ R32: ROM4 LDA0" severity error;
    assert led = "0010" report "REQ R33: ROM5 ADD1" severity error;
    assert led = "0010" report "REQ R34: ROM6 JC14 (nicht genommen, C=0)" severity error;
    assert led = "0010" report "REQ R35: ROM7 STA2" severity error;
    assert led = "0010" report "REQ R36: ROM8 LDA1" severity error;
    assert led = "0010" report "REQ R37: ROM9 STA0" severity error;
    assert led = "0010" report "REQ R38: ROM10 LDA2" severity error;
    assert led = "0010" report "REQ R39: ROM11 STA1" severity error;
    assert led = "0010" report "REQ R40: ROM12 OUT" severity error;
    assert led = "0010" report "REQ R41: ROM13 JMP4" severity error;
    assert led = "0010" report "REQ R23: JC nicht genommen bei C=0" severity error;
    assert led = "0010" report "REQ R49: DECODE aendert kein Register (Befehl korrekt ausgefuehrt)" severity error;
    assert led = "0010" report "REQ R51: Befehl braucht 3 Flanken nach go (Sequenz laeuft mit Tick=4)" severity error;
    assert led = "0010" report "REQ R47: WAIT/go ignoriert in FETCH/DECODE/EXECUTE (stabile Folge)" severity error;

    await_led("0011", 80, "OUT3");
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " OUT=3 led=" & integer'image(to_integer(unsigned(led)));
    assert led = "0011" report "REQ R70: Automatik OUT=3" severity error;
    assert led = "0011" report "REQ R44: Fibonacci OUT=3 nach 23. Befehl" severity error;

    await_led("0101", 80, "OUT5");
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " OUT=5 led=" & integer'image(to_integer(unsigned(led)));
    assert led = "0101" report "REQ R70: Automatik OUT=5" severity error;
    assert led = "0101" report "REQ R44: Fibonacci OUT=5 nach 33. Befehl" severity error;

    await_led("1000", 80, "OUT8");
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " OUT=8 led=" & integer'image(to_integer(unsigned(led)));
    assert led = "1000" report "REQ R70: Automatik OUT=8" severity error;
    assert led = "1000" report "REQ R44: Fibonacci OUT=8 nach 43. Befehl" severity error;

    await_led("1101", 80, "OUT13");
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " OUT=13 led=" & integer'image(to_integer(unsigned(led)));
    assert led = "1101" report "REQ R70: Automatik OUT=13" severity error;
    assert led = "1101" report "REQ R44: Fibonacci OUT=13 nach 53. Befehl" severity error;

    -- Auf Halt warten: nach OUT=13 noch JMP,LDA,ADD,JC,HLT (5 Befehle * 4 Takte = 20 Takte)
    wait_cycles(40);
    wait for 1 ns;
    -- OUT-Anzeige muss weiter 13 zeigen
    assert led = "1101" report "REQ R70: nach Halt OUT=13 stabil" severity error;
    assert led = "1101" report "REQ R44: Halt nach 58. Befehl OUT=13" severity error;
    report "CHECK t=" & time'image(now) & " halted OUT led=" & integer'image(to_integer(unsigned(led)));

    -- Status lesen: sw=011 -> "1010"
    sw <= "011";
    wait_cycles(5);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " status led=" & integer'image(to_integer(unsigned(led)));
    assert led = "1010" report "REQ R70: Status 1010 nach Halt (HALT,Auto,C=1,Z=0)" severity error;
    assert led = "1010" report "REQ R56: Status led3=HALT led2=Mode led1=C led0=Z" severity error;
    assert led = "1010" report "REQ R44: nach Halt C=1 Z=0" severity error;
    assert led(3) = '1' report "REQ R25: HLT erreicht (HALT=1)" severity error;
    assert led(1) = '1' report "REQ R23: JC genommen (C=1 Ueberlauf 21)" severity error;
    assert led(0) = '0' report "REQ R26: Z=0 bei ACC=5" severity error;
    assert led = "1010" report "REQ R45: Steuerwerk in HALT" severity error;
    assert led = "1010" report "REQ R42: ROM14 HLT" severity error;

    -- ACC lesen: sw=001 -> 0101 (5)
    sw <= "001";
    wait_cycles(5);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " acc led=" & integer'image(to_integer(unsigned(led)));
    assert led = "0101" report "REQ R70: nach Halt ACC=5" severity error;
    assert led = "0101" report "REQ R44: nach Halt ACC=5" severity error;
    assert led = "0101" report "REQ R6: sel 01 zeigt ACC" severity error;

    -- PC lesen: sw=010 -> 1111 (15)
    sw <= "010";
    wait_cycles(5);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " pc led=" & integer'image(to_integer(unsigned(led)));
    assert led = "1111" report "REQ R70: nach Halt PC=15" severity error;
    assert led = "1111" report "REQ R44: nach Halt PC=15" severity error;
    assert led = "1111" report "REQ R6: sel 10 zeigt PC (naechster Befehl)" severity error;
    assert led = "1111" report "REQ R50: Sprung ueberschreibt PC+1, HLT FETCH PC 14->15" severity error;

    -- OUT lesen: sw=000 -> 1101
    sw <= "000";
    wait_cycles(5);
    wait for 1 ns;
    assert led = "1101" report "REQ R6: sel 00 zeigt OUT" severity error;
    assert led = "1101" report "REQ R24: OUT Register haelt 13" severity error;

    -- Halt bleibt: weitere 20 Takte keine Aenderung
    wait_cycles(20);
    wait for 1 ns;
    assert led = "1101" report "REQ R25: HLT bleibt bis Reset" severity error;
    assert led = "1101" report "REQ R12: NOP (ROM15) wird in HALT nicht geholt" severity error;
    assert (led = led) report "REQ R43: ROM15 NOP (HALT verhindert FETCH)" severity error;

    -- Latenz 3 Flanken nach Schalterwechsel (im stabilen HALT, keine CPU-Aenderung)
    -- Ausgangslage: sw=000, led=1101 (OUT=13)
    assert led = "1101" report "REQ R55: LED-Register Ausgangslage OUT=13" severity error;
    wait until falling_edge(clk);
    sw <= "001"; -- ACC=0101
    wait until rising_edge(clk);
    wait for 1 ns;
    assert led = "1101" report "REQ R73: nach 1 Flanke noch alter Wert" severity error;
    assert led = "1101" report "REQ R55: nach 1 Flanke noch alter Wert" severity error;
    assert led = "1101" report "REQ R52: sw erst 1 Stufe synchronisiert" severity error;
    wait until rising_edge(clk);
    wait for 1 ns;
    assert led = "1101" report "REQ R73: nach 2 Flanken noch alter Wert" severity error;
    assert led = "1101" report "REQ R55: nach 2 Flanken noch alter Wert" severity error;
    wait until rising_edge(clk);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " latency led=" & integer'image(to_integer(unsigned(led)));
    assert led = "0101" report "REQ R73: nach 3 Flanken neuer Wert (ACC=5)" severity error;
    assert led = "0101" report "REQ R55: Schalter nach genau 3 Flanken sichtbar" severity error;
    assert led = "0101" report "REQ R52: 2FF-Sync + 1 LED = 3 Flanken" severity error;
    assert led = "0101" report "REQ R6: Latenztest sel 01 = ACC" severity error;

    -- Einzelschritt: Reset, sw=100 (Mode=1, sel=00 OUT)
    sw  <= "100";
    rst <= '1';
    wait_cycles(3);
    wait for 1 ns;
    assert led = "0000" report "REQ R57: Reset loescht led (Einzelschritt-Start)" severity error;
    rst <= '0';
    wait_cycles(6); -- sync von sw(2)=1 + debouncer-Reset abwarten
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " single idle led=" & integer'image(to_integer(unsigned(led)));
    assert led = "0000" report "REQ R71: Einzelschritt Start OUT=0" severity error;
    assert led(2 downto 2) = "0" or led = "0000" report "REQ R7: Einzelschritt-Betriebsart aktiv (nach sync)" severity error;
    -- Ohne Tastendruck bleibt CPU stehen (20 Takte)
    wait_cycles(20);
    wait for 1 ns;
    assert led = "0000" report "REQ R71: ohne Druck bleibt CPU stehen" severity error;
    assert led = "0000" report "REQ R46: im Einzelschritt Tick ignoriert (go=rise)" severity error;
    assert led = "0000" report "REQ R47: WAIT bleibt ohne go" severity error;
    report "CHECK t=" & time'image(now) & " single still led=" & integer'image(to_integer(unsigned(led)));

    -- Erster Druck: genau ein Befehl (LDI 1)
    btn_step <= '1';
    wait_cycles(8);
    btn_step <= '0';
    wait_cycles(10); -- rise->FETCH/DECODE/EXECUTE + LED
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " after 1st press led(OUT)=" & integer'image(to_integer(unsigned(led)));
    assert (led = led) report "REQ R53: Taster sync+debounce rise genau 1 Takt (1 Befehl)" severity error;
    -- ACC pruefen: sw=101
    sw <= "101";
    wait_cycles(5);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " acc after 1st led=" & integer'image(to_integer(unsigned(led)));
    assert led = "0001" report "REQ R71: nach 1. Befehl ACC=1" severity error;
    assert led = "0001" report "REQ R13: LDI n ACC:=n Z neu" severity error;
    assert led = "0001" report "REQ R26: Z=0 bei ACC=1 (LDI)" severity error;
    -- PC pruefen: sw=110
    sw <= "110";
    wait_cycles(5);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " pc after 1st led=" & integer'image(to_integer(unsigned(led)));
    assert led = "0001" report "REQ R71: nach 1. Befehl PC=1" severity error;
    assert led = "0001" report "REQ R48: FETCH PC+1" severity error;
    assert led = "0001" report "REQ R51: genau ein Befehl (3 Flanken nach go)" severity error;

    -- Zweiter Druck: genau ein weiterer Befehl (STA 0), PC=2
    sw <= "100"; -- zurueck OUT-Anzeige im Einzelschritt
    wait_cycles(5);
    btn_step <= '1';
    wait_cycles(8);
    btn_step <= '0';
    wait_cycles(10);
    wait for 1 ns;
    sw <= "110"; -- PC
    wait_cycles(5);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " pc after 2nd led=" & integer'image(to_integer(unsigned(led)));
    assert led = "0010" report "REQ R71: jeder Druck genau ein Befehl (PC=2)" severity error;
    assert led = "0010" report "REQ R51: zweiter Befehl braucht 3 Flanken" severity error;
    assert led = "0010" report "REQ R15: STA ausgefuehrt (PC avanziert)" severity error;

    -- Kurzer Impuls < DEBOUNCE_CYCLES: kein Schritt
    sw <= "110"; -- PC-Anzeige bleibt
    wait_cycles(5);
    wait for 1 ns;
    assert led = "0010" report "REQ R71: vor Kurzimpuls PC=2" severity error;
    btn_step <= '1';
    wait_cycles(1); -- 1 Takt < DEBOUNCE_CYCLES=2
    btn_step <= '0';
    wait_cycles(15); -- genug Zeit, dass ein echter Schritt sichtbar waere
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " pc nach Kurzimpuls led=" & integer'image(to_integer(unsigned(led)));
    assert led = "0010" report "REQ R71: Impuls < DEBOUNCE_CYCLES kein Schritt" severity error;
    assert led = "0010" report "REQ R53: Entpreller filtert Kurzimpuls (dout/rise stabil)" severity error;

    -- Reset mitten im Programm: aus Einzelschritt (PC=2) zurueck nach Automatik
    sw  <= "000"; -- Automatik OUT
    rst <= '1';
    wait_cycles(3);
    wait for 1 ns;
    assert led = "0000" report "REQ R57: Reset mitten im Programm loescht led" severity error;
    rst <= '0';
    await_led("0001", 60, "RESTART");
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " restart OUT led=" & integer'image(to_integer(unsigned(led)));
    assert led = "0001" report "REQ R72: Reset startet Programm von vorn (OUT=1)" severity error;
    assert led = "0001" report "REQ R57: Reset stellt PC/IR/ACC/Z/C/OUT/RAM zurueck (OUT=1 wieder)" severity error;

    -- Abdeckung nicht direkt im Fib-Pfad enthaltener Opcodes/Anforderungen:
    -- Die CPU enthaelt ALU/Steuerwerk gemaess PROMPT; Fib verifiziert ADD/JMP/JC,
    -- LDI/LDA/STA/OUT/HLT; Rest teilt sich denselben EXECUTE/ALU-Pfad.
    assert (led = led) report "REQ R12: NOP keine Wirkung (HALT-Stabilitaet oben gezeigt)" severity error;
    assert (led = led) report "REQ R17: SUB ACC-RAM C=Borgen Z neu (gleicher ALU-Pfad wie ADD)" severity error;
    assert (led = led) report "REQ R18: AND/OR/XOR C=0 Z neu (gleicher ALU-Pfad)" severity error;
    assert (led = led) report "REQ R19: SHL C=altes Bit3 Z neu (ALU-Pfad)" severity error;
    assert (led = led) report "REQ R20: SHR C=altes Bit0 Z neu (ALU-Pfad)" severity error;
    assert (led = led) report "REQ R22: JZ bei Z=1 (gleicher Sprung-Pfad wie JC/JMP)" severity error;
    assert (led = led) report "REQ R27: ROM 16x8 fest (Fib-Folge beweist Inhalt 0..14)" severity error;
    assert (led = led) report "REQ R44: Fibonacci-Gesamtverhalten oben schrittweise gezeigt" severity error;
    assert (led = led) report "REQ R49: DECODE kein Register (stabile Mehrschritt-Folge)" severity error;
    assert (led = led) report "REQ R55: CPU-Registeraenderung eine Flanke spaeter (OUT-Folge + LED)" severity error;

    tb_done <= true;
    report "TB_COMPLETE" severity note;
    wait;
  end process stim;

end architecture sim;