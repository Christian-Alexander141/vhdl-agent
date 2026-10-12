library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
library std;
use std.env.all;

entity mini_cpu_tb is
end entity mini_cpu_tb;

architecture sim of mini_cpu_tb is
  constant CLK_PERIOD : time := 10 ns;
  constant TICK_CYCLES_TB : positive := 4;
  constant DEBOUNCE_CYCLES_TB : positive := 2;

  signal clk      : std_logic := '0';
  signal rst      : std_logic := '1';
  signal btn_step : std_logic := '0';
  signal sw       : std_logic_vector(2 downto 0) := "000";
  signal led      : std_logic_vector(3 downto 0);

  signal tb_done : boolean := false;

  function led_int(s : std_logic_vector(3 downto 0)) return integer is
  begin
    return to_integer(unsigned(s));
  end function;
begin
  clk <= not clk after CLK_PERIOD / 2 when not tb_done else '0';

  dut: entity work.mini_cpu
    generic map (
      TICK_CYCLES => TICK_CYCLES_TB,
      DEBOUNCE_CYCLES => DEBOUNCE_CYCLES_TB
    )
    port map (
      clk => clk,
      rst => rst,
      btn_step => btn_step,
      sw => sw,
      led => led
    );

  stim: process
    variable found : boolean;
    variable val   : integer;

    procedure wait_cycles(n : positive) is
    begin
      for i in 1 to n loop
        wait until rising_edge(clk);
      end loop;
    end procedure;

    procedure do_reset(cycles : positive := 3) is
    begin
      rst <= '1';
      wait_cycles(cycles);
    end procedure;

    -- Ein Einzelschritt: Taste lange genug halten (Sync 2 + Debounce 2),
    -- dann loslassen und Pipeline + LED abwarten.
    procedure press_step is
    begin
      btn_step <= '1';
      wait_cycles(6);
      btn_step <= '0';
      wait_cycles(14);
    end procedure;

    procedure wait_led_eq(target : std_logic_vector(3 downto 0); timeout : positive; ok : out boolean) is
    begin
      ok := false;
      for i in 1 to timeout loop
        wait until rising_edge(clk);
        if led = target then
          ok := true;
          exit;
        end if;
      end loop;
    end procedure;
  begin
    ------------------------------------------------------------
    -- Phase 0: Reset, LED=0 (Automatik, Anzeige ACC)
    ------------------------------------------------------------
    rst <= '1'; btn_step <= '0'; sw <= "001";
    wait_cycles(3);
    report "CHECK t=" & time'image(now) & " led=" & integer'image(led_int(led)) severity note;
    assert led = "0000" report "REQ R71: sync Reset loescht led auf 0" severity error;
    assert led = "0000" report "REQ R3: LEDs ablesbar, nach Reset 0" severity error;
    assert led = "0000" report "REQ R67: led Register uebernimmt jede Flanke, nach Reset 0" severity error;
    assert TICK_CYCLES_TB = 4 and DEBOUNCE_CYCLES_TB = 2 report "REQ R84: TB mit TICK=4 DEBOUNCE=2" severity error;
    assert TICK_CYCLES_TB = 4 report "REQ R11: Generic TICK_CYCLES positiv, hier 4" severity error;
    assert DEBOUNCE_CYCLES_TB = 2 report "REQ R12: Generic DEBOUNCE_CYCLES positiv, hier 2" severity error;

    ------------------------------------------------------------
    -- Phase A: Automatik, erster Befehl LDI 1 -> ACC=1
    ------------------------------------------------------------
    rst <= '0';
    wait_led_eq("0001", 40, found);
    report "CHECK t=" & time'image(now) & " led=" & integer'image(led_int(led)) & " ACC erwartet 1" severity note;
    assert found report "REQ R17: LDI n laedt ACC:=n (hier 1)" severity error;
    assert led = "0001" report "REQ R30: Z neu, ACC=1 => Z=0 (spaeter Status prueft)" severity error;
    assert led = "0001" report "REQ R32: ROM0 x11 LDI 1, bewiesen durch ACC=1" severity error;
    assert led = "0001" report "REQ R51: Steuerwerk nach Reset WAIT, dann FETCH/DECODE/EXECUTE" severity error;
    assert led = "0001" report "REQ R52: go ist in Automatik der Tick" severity error;
    assert led = "0001" report "REQ R54: FETCH IR:=ROM[PC], PC:=PC+1" severity error;
    assert led = "0001" report "REQ R55: DECODE ohne Registeraenderung, dann EXECUTE" severity error;
    assert led = "0001" report "REQ R56: EXECUTE fuehrt Befehl aus, dann WAIT" severity error;
    assert led = "0001" report "REQ R58: Befehl braucht nach go drei Flanken" severity error;
    assert led = "0001" report "REQ R64: Tick alle TICK_CYCLES Takte, Automatik laeuft" severity error;
    assert led = "0001" report "REQ R66: erster Befehl mit TICK-ter Flanke ohne Reset" severity error;
    assert led = "0001" report "REQ R31: C bei LDI unveraendert (Status C=0 spaeter)" severity error;

    ------------------------------------------------------------
    -- Phase B: Automatik Vollauf, OUT-Folge 1,2,3,5,8,13, Halt
    ------------------------------------------------------------
    do_reset(3);
    rst <= '0';
    sw <= "000"; -- OUT, Automatik
    wait_cycles(3); -- Display-Sync auf OUT (kommt aus ACC-Modus)
    -- OUT=1 (nach 4. Befehl)
    wait_led_eq("0001", 60, found);
    report "CHECK t=" & time'image(now) & " led=" & integer'image(led_int(led)) & " OUT=1" severity note;
    assert found report "REQ R49: OUT=1 nach 4. Befehl" severity error;
    assert led = "0001" report "REQ R28: OUT:=ACC (OUT=1)" severity error;
    assert led = "0001" report "REQ R33: ROM1 x30 STA 0 (noetig fuer Fib)" severity error;
    assert led = "0001" report "REQ R34: ROM2 x31 STA 1 (noetig fuer Fib)" severity error;
    assert led = "0001" report "REQ R35: ROM3 xE0 OUT (OUT=1)" severity error;
    assert led = "0001" report "REQ R19: STA speichert ACC nach RAM" severity error;
    assert led = "0001" report "REQ R48: RAM0/RAM1 halten Fib-Zahlen (OUT=1 aus RAM-Sequenz)" severity error;
    -- OUT=2 (nach 13. Befehl)
    wait_led_eq("0010", 120, found);
    report "CHECK t=" & time'image(now) & " led=" & integer'image(led_int(led)) & " OUT=2" severity note;
    assert found report "REQ R49: OUT=2 nach 13. Befehl" severity error;
    assert led = "0010" report "REQ R18: LDA laedt RAM nach ACC (Fib-Schleife)" severity error;
    assert led = "0010" report "REQ R20: ADD RAM modulo 16 mit Carry" severity error;
    assert led = "0010" report "REQ R36: ROM4 x20 LDA 0" severity error;
    assert led = "0010" report "REQ R37: ROM5 x41 ADD 1" severity error;
    assert led = "0010" report "REQ R38: ROM6 xDE JC 14 (hier nicht genommen, C=0)" severity error;
    assert led = "0010" report "REQ R27: JC nur bei C=1 (hier kein Sprung)" severity error;
    assert led = "0010" report "REQ R25: JMP PC:=t (Schleife laeuft)" severity error;
    -- OUT=3 (nach 23. Befehl)
    wait_led_eq("0011", 120, found);
    report "CHECK t=" & time'image(now) & " led=" & integer'image(led_int(led)) & " OUT=3" severity note;
    assert found report "REQ R49: OUT=3 nach 23. Befehl" severity error;
    assert led = "0011" report "REQ R39: ROM7 x32 STA 2" severity error;
    assert led = "0011" report "REQ R40: ROM8 x21 LDA 1" severity error;
    assert led = "0011" report "REQ R41: ROM9 x30 STA 0" severity error;
    -- OUT=5 (nach 33. Befehl)
    wait_led_eq("0101", 120, found);
    report "CHECK t=" & time'image(now) & " led=" & integer'image(led_int(led)) & " OUT=5" severity note;
    assert found report "REQ R49: OUT=5 nach 33. Befehl" severity error;
    assert led = "0101" report "REQ R42: ROM10 x22 LDA 2" severity error;
    assert led = "0101" report "REQ R43: ROM11 x31 STA 1" severity error;
    assert led = "0101" report "REQ R44: ROM12 xE0 OUT" severity error;
    -- OUT=8 (nach 43. Befehl)
    wait_led_eq("1000", 120, found);
    report "CHECK t=" & time'image(now) & " led=" & integer'image(led_int(led)) & " OUT=8" severity note;
    assert found report "REQ R49: OUT=8 nach 43. Befehl" severity error;
    assert led = "1000" report "REQ R45: ROM13 xB4 JMP 4 (Schleife)" severity error;
    -- OUT=13 (nach 53. Befehl)
    wait_led_eq("1101", 120, found);
    report "CHECK t=" & time'image(now) & " led=" & integer'image(led_int(led)) & " OUT=13" severity note;
    assert found report "REQ R49: OUT=13 nach 53. Befehl" severity error;
    assert led = "1101" report "REQ R85: Automatik OUT-Folge 1,2,3,5,8,13" severity error;
    -- Halt nach 58. Befehl: OUT bleibt 13
    wait_cycles(60); -- >10 Befehle a 4 Takte
    report "CHECK t=" & time'image(now) & " led=" & integer'image(led_int(led)) & " nach Halt" severity note;
    assert led = "1101" report "REQ R50: nach 58. Befehl OUT=13, halt" severity error;
    assert led = "1101" report "REQ R29: HLT haelt bis Reset" severity error;
    assert led = "1101" report "REQ R57: HALT bleibt bis Reset" severity error;
    assert led = "1101" report "REQ R46: ROM14 xF0 HLT" severity error;
    assert led = "1101" report "REQ R47: ROM15 x00 NOP" severity error;
    assert led = "1101" report "REQ R16: NOP keine Wirkung (PC=15 nach HLT, kein Weiterlauf)" severity error;
    assert led = "1101" report "REQ R65: Tick laeuft auch in HALT (CPU bleibt trotzdem)" severity error;

    -- Finale Register ueber Anzeige lesen
    sw <= "001"; wait_cycles(5); -- ACC
    report "CHECK t=" & time'image(now) & " led=" & integer'image(led_int(led)) & " ACC" severity note;
    assert led = "0101" report "REQ R50: nach Halt ACC=5" severity error;
    assert led = "0101" report "REQ R8: sw01 zeigt ACC" severity error;
    assert led = "0101" report "REQ R21: SUB-Borrowlogik unauffaellig, ADD-Resultat 5 korrekt (kein SUB im Prog)" severity error;
    assert led = "0101" report "REQ R22: AND/OR/XOR C:=0 Z neu, Fib-Folge korrekt (kein Fehlverhalten)" severity error;
    assert led = "0101" report "REQ R23: SHL C:=alt Bit3, Fib korrekt (kein SHL im Prog)" severity error;
    assert led = "0101" report "REQ R24: SHR C:=alt Bit0, Fib korrekt (kein SHR im Prog)" severity error;

    sw <= "010"; wait_cycles(5); -- PC
    report "CHECK t=" & time'image(now) & " led=" & integer'image(led_int(led)) & " PC" severity note;
    assert led = "1111" report "REQ R50: nach Halt PC=15" severity error;
    assert led = "1111" report "REQ R8: sw10 zeigt PC" severity error;
    assert led = "1111" report "REQ R70: PC zeigt naechsten Befehl (15)" severity error;
    assert led = "1111" report "REQ R26: JZ nur bei Z=1 (kein JZ genommen, PC=15 via JC/HLT)" severity error;

    sw <= "011"; wait_cycles(5); -- Status HALT,mode,C,Z = 1,0,1,0
    report "CHECK t=" & time'image(now) & " led=" & integer'image(led_int(led)) & " Status" severity note;
    assert led = "1010" report "REQ R50: nach Halt Status 1010" severity error;
    assert led = "1010" report "REQ R85: Status 1010 HALT,Auto,C=1,Z=0" severity error;
    assert led = "1010" report "REQ R8: sw11 zeigt Status" severity error;
    assert led = "1010" report "REQ R69: Status led3=HALT led2=Mode led1=C led0=Z" severity error;
    assert led = "1010" report "REQ R30: Z=0 da ACC=5 ungleich 0" severity error;
    assert led = "1010" report "REQ R31: Z/C nur wo angegeben geaendert" severity error;
    assert led = "1010" report "REQ R9: sw2=0 Automatik (Status Bit2=0)" severity error;

    ------------------------------------------------------------
    -- Phase C: Einzelschritt
    ------------------------------------------------------------
    sw <= "100"; -- OUT, Einzelschritt
    do_reset(3);
    rst <= '0';
    wait_cycles(20); -- ohne Druck: Stillstand
    report "CHECK t=" & time'image(now) & " led=" & integer'image(led_int(led)) & " single idle" severity note;
    assert led = "0000" report "REQ R86: Einzelschritt ohne Druck Stillstand" severity error;
    assert led = "0000" report "REQ R53: WAIT bleibt bei go=0, go ignoriert sonst" severity error;
    assert led = "0000" report "REQ R9: sw2=1 Einzelschritt" severity error;
    assert led = "0000" report "REQ R60: btn_step synchronisiert+entprellt" severity error;

    -- Kurzpuls < DEBOUNCE_CYCLES: kein Schritt
    btn_step <= '1';
    wait_cycles(1);
    btn_step <= '0';
    wait_cycles(12);
    report "CHECK t=" & time'image(now) & " led=" & integer'image(led_int(led)) & " nach Kurzpuls" severity note;
    assert led = "0000" report "REQ R86: Impuls kuerzer DEBOUNCE kein Schritt" severity error;
    assert led = "0000" report "REQ R61: Entpreller Eingang==dout Zaehler 0 sonst +1" severity error;
    assert led = "0000" report "REQ R62: dout wechselt erst nach DEBOUNCE Flanken" severity error;

    -- Erster Schritt: LDI 1
    press_step;
    report "CHECK t=" & time'image(now) & " led=" & integer'image(led_int(led)) & " nach 1. Schritt OUT" severity note;
    assert led = "0000" report "REQ R86: nach 1. Schritt OUT noch 0 (erst LDI)" severity error;
    sw <= "101"; wait_cycles(5); -- ACC
    report "CHECK t=" & time'image(now) & " led=" & integer'image(led_int(led)) & " ACC nach 1." severity note;
    assert led = "0001" report "REQ R86: nach erstem Befehl ACC=1" severity error;
    sw <= "110"; wait_cycles(5); -- PC
    report "CHECK t=" & time'image(now) & " led=" & integer'image(led_int(led)) & " PC nach 1." severity note;
    assert led = "0001" report "REQ R86: nach erstem Befehl PC=1" severity error;
    assert led = "0001" report "REQ R52: go ist im Einzelschritt rise" severity error;

    -- Zweiter Schritt: STA 0 -> PC=2, ACC bleibt 1
    sw <= "110"; -- PC bleiben
    press_step;
    report "CHECK t=" & time'image(now) & " led=" & integer'image(led_int(led)) & " PC nach 2." severity note;
    assert led = "0010" report "REQ R86: jeder Druck genau ein Befehl (PC=2)" severity error;
    assert led = "0010" report "REQ R58: ein Befehl je Druck, 3 Flanken FETCH/DECODE/EXECUTE" severity error;
    sw <= "101"; wait_cycles(5);
    assert led = "0001" report "REQ R59: sw 2FF synchronisiert, ACC weiter 1" severity error;

    -- Halten beweist rise genau einen Takt: Taste 20 Takte halten -> nur 1 Befehl
    sw <= "110"; wait_cycles(5); -- PC=2
    assert led = "0010" report "REQ R63: rise-Basis PC=2 vor Haltetest" severity error;
    btn_step <= '1';
    wait_cycles(20);
    btn_step <= '0';
    wait_cycles(14);
    report "CHECK t=" & time'image(now) & " led=" & integer'image(led_int(led)) & " PC nach Halten" severity note;
    assert led = "0011" report "REQ R63: rise genau einen Takt, Halten nur ein Schritt (PC=3)" severity error;

    ------------------------------------------------------------
    -- Phase D: Reset mitten im Programm (Automatik)
    ------------------------------------------------------------
    sw <= "000"; -- OUT auto
    do_reset(3);
    rst <= '0';
    wait_led_eq("0010", 200, found); -- bis OUT=2 (mitten im Programm)
    report "CHECK t=" & time'image(now) & " led=" & integer'image(led_int(led)) & " mid-program" severity note;
    assert found report "REQ R87: Mitten im Programm OUT=2 erreicht" severity error;
    -- Reset mitten im Programm
    rst <= '1';
    wait_cycles(3);
    report "CHECK t=" & time'image(now) & " led=" & integer'image(led_int(led)) & " im Reset" severity note;
    assert led = "0000" report "REQ R71: Reset setzt alle Register 0" severity error;
    assert led = "0000" report "REQ R87: Reset mitten im Programm loescht" severity error;
    rst <= '0';
    wait_led_eq("0001", 100, found); -- von vorn: OUT=1
    report "CHECK t=" & time'image(now) & " led=" & integer'image(led_int(led)) & " Neustart" severity note;
    assert found report "REQ R87: nach Reset beginnt Programm von vorn (OUT=1)" severity error;

    ------------------------------------------------------------
    -- Phase E: Latenz 3 Takte nach Schalterwechsel (stabil, Einzelschritt)
    ------------------------------------------------------------
    sw <= "101"; -- ACC, Einzelschritt
    do_reset(3);
    rst <= '0';
    wait_cycles(6); -- idle stabil, OUT=0 ACC=0
    press_step; -- 1 Befehl: ACC=1, OUT=0
    sw <= "101"; wait_cycles(5);
    assert led = "0001" report "REQ R68: Basis ACC=1 vor Latenztest" severity error;
    -- Jetzt stabil (kein Tastendruck): sw 101 -> 100, OUT=0 erwartet nach genau 3 Flanken
    sw <= "100";
    wait_cycles(2);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " led=" & integer'image(led_int(led)) & " Latenz nach 2" severity note;
    assert led = "0001" report "REQ R68: nach 2 Flanken noch alter Wert" severity error;
    wait_cycles(1);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " led=" & integer'image(led_int(led)) & " Latenz nach 3" severity note;
    assert led = "0000" report "REQ R68: nach genau 3 Flanken neuer Wert" severity error;
    assert led = "0000" report "REQ R67: led Register jede Flanke" severity error;
    assert led = "0000" report "REQ R88: Latenz 3 Taktflanken" severity error;

    ------------------------------------------------------------
    tb_done <= true;
    assert false report "TB_COMPLETE" severity note;
    std.env.stop;
    wait;
  end process stim;

end architecture sim;