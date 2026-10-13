library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity ben_eater_cpu_tb is
end entity ben_eater_cpu_tb;

architecture sim of ben_eater_cpu_tb is
  constant CLK_PERIOD : time := 10 ns;   -- 100 MHz Boardtakt
  constant BIT_TIME   : time := 80 ns;   -- CLKS_PER_BIT=8 * 10 ns
  constant RX_TIMEOUT : time := 30 us;

  signal clk      : std_logic := '0';
  signal rst      : std_logic := '1';
  signal btn_step : std_logic := '0';
  signal sw       : std_logic_vector(3 downto 0) := "0000";
  signal led      : std_logic_vector(3 downto 0);
  signal uart_rx  : std_logic := '1';
  signal uart_tx  : std_logic;

  signal tb_done : boolean := false;

  type byte_array_t is array (natural range <>) of std_logic_vector(7 downto 0);

  -- Hardwaretest-Vektoren aus PROMPT.md (Programme und erwartete Antworten)
  constant PROG_FIB_HALT : byte_array_t(0 to 15) := (
    x"E0", x"2E", x"7B", x"4F", x"1E", x"4D", x"1F", x"4E",
    x"1D", x"60", x"00", x"F0", x"00", x"00", x"01", x"00");
  constant EXP_FIB : byte_array_t(0 to 12) := (
    x"00", x"01", x"01", x"02", x"03", x"05", x"08",
    x"0D", x"15", x"22", x"37", x"59", x"90");
  constant PROG_MUL79 : byte_array_t(0 to 15) := (
    x"1E", x"3C", x"76", x"1D", x"E0", x"F0", x"4E", x"1D",
    x"2F", x"4D", x"60", x"00", x"01", x"00", x"07", x"09");
  constant EXP_MUL : byte_array_t(0 to 0) := (0 => x"3F");
  constant PROG_CD5 : byte_array_t(0 to 15) := (
    x"55", x"E0", x"3F", x"85", x"61", x"E0", x"F0", x"00",
    x"00", x"00", x"00", x"00", x"00", x"00", x"00", x"01");
  constant EXP_CD5 : byte_array_t(0 to 5) := (
    x"05", x"04", x"03", x"02", x"01", x"00");
  constant PROG_BOR : byte_array_t(0 to 15) := (
    x"53", x"3F", x"75", x"E0", x"F0", x"51", x"E0", x"F0",
    x"00", x"00", x"00", x"00", x"00", x"00", x"00", x"05");
  constant EXP_BOR : byte_array_t(0 to 0) := (0 => x"FE");
  -- Endlosschleife OUT / JMP 0 (gibt dauerhaft OUT aus, endet nie mit HLT)
  constant PROG_LOOP : byte_array_t(0 to 1) := (x"E0", x"60");
  -- LDI 5, dann Opcode 1001 (muss wie NOP wirken), OUT, HLT
  constant PROG_NOP9 : byte_array_t(0 to 3) := (x"55", x"90", x"E0", x"F0");
  constant TRAIL : byte_array_t(0 to 5) := (
    x"53", x"54", x"41", x"52", x"54", x"0A");  -- "START" + LF

  function hex4(nib : std_logic_vector(3 downto 0)) return string is
    variable c : character;
  begin
    case nib is
      when "0000" => c := '0';
      when "0001" => c := '1';
      when "0010" => c := '2';
      when "0011" => c := '3';
      when "0100" => c := '4';
      when "0101" => c := '5';
      when "0110" => c := '6';
      when "0111" => c := '7';
      when "1000" => c := '8';
      when "1001" => c := '9';
      when "1010" => c := 'A';
      when "1011" => c := 'B';
      when "1100" => c := 'C';
      when "1101" => c := 'D';
      when "1110" => c := 'E';
      when "1111" => c := 'F';
      when others => c := 'X';
    end case;
    return (1 => c);
  end function hex4;

  function hex8(b : std_logic_vector(7 downto 0)) return string is
  begin
    return hex4(b(7 downto 4)) & hex4(b(3 downto 0));
  end function hex8;

begin
  clk <= not clk after CLK_PERIOD / 2 when not tb_done else '0';

  dut: entity work.ben_eater_cpu
    generic map (
      TICK_CYCLES     => 2,
      DEBOUNCE_CYCLES => 2,
      CLKS_PER_BIT    => 8
    )
    port map (
      clk      => clk,
      rst      => rst,
      btn_step => btn_step,
      sw       => sw,
      led      => led,
      uart_rx  => uart_rx,
      uart_tx  => uart_tx
    );

  stim: process
    variable b        : std_logic_vector(7 downto 0);
    variable n        : integer;
    variable t0, t1   : time;

    procedure wait_cycles(k : positive) is
    begin
      for i in 1 to k loop
        wait until rising_edge(clk);
      end loop;
    end procedure wait_cycles;

    procedure do_reset is
    begin
      rst <= '1';
      wait_cycles(10);
      rst <= '0';
      wait_cycles(3);
    end procedure do_reset;

    procedure press_once is
    begin
      btn_step <= '1';
      wait_cycles(12);
      btn_step <= '0';
      wait_cycles(12);
    end procedure press_once;

    procedure uart_send_byte(v : std_logic_vector(7 downto 0)) is
    begin
      uart_rx <= '0';                       -- Startbit
      wait for BIT_TIME;
      for i in 0 to 7 loop                  -- 8 Datenbits, LSB zuerst
        uart_rx <= v(i);
        wait for BIT_TIME;
      end loop;
      uart_rx <= '1';                       -- Stoppbit
      wait for BIT_TIME;
      wait for CLK_PERIOD * 4;              -- Luecke zwischen Zeichen
    end procedure uart_send_byte;

    -- Ein Zeichen mit defektem Stoppbit (Stopp = '0'): muss verworfen werden.
    procedure uart_send_byte_bad_stop(v : std_logic_vector(7 downto 0)) is
    begin
      uart_rx <= '0';
      wait for BIT_TIME;
      for i in 0 to 7 loop
        uart_rx <= v(i);
        wait for BIT_TIME;
      end loop;
      uart_rx <= '0';                       -- defektes Stoppbit
      wait for BIT_TIME;
      uart_rx <= '1';
      wait for CLK_PERIOD * 4;
    end procedure uart_send_byte_bad_stop;

    procedure uart_send_frame(prog : byte_array_t) is
      variable len : std_logic_vector(7 downto 0);
    begin
      len := std_logic_vector(to_unsigned(prog'length, 8));
      uart_send_byte(len);
      uart_send_byte(x"00");
      uart_send_byte(x"00");
      uart_send_byte(x"00");
      for i in prog'range loop
        uart_send_byte(prog(i));
      end loop;
      for i in TRAIL'range loop
        uart_send_byte(TRAIL(i));
      end loop;
      -- Keine Warteluecke: das erste Antwortzeichen beginnt wenige Takte
      -- nach dem Rahmen; der Aufrufer wartet sofort auf das Startbit.
    end procedure uart_send_frame;

    procedure uart_recv_byte(v : out std_logic_vector(7 downto 0)) is
      variable r : std_logic_vector(7 downto 0);
    begin
      wait until falling_edge(uart_tx) for RX_TIMEOUT;
      assert uart_tx = '0'
        report "REQ R75: UART-Antwortbyte fehlt (Timeout beim Startbit)"
        severity error;
      wait for BIT_TIME * 3 / 2;            -- Mitte von Datenbit 0
      for i in 0 to 7 loop
        r(i) := uart_tx;
        wait for BIT_TIME;
      end loop;
      -- Abtastpunkt liegt jetzt in der Stoppbit-Mitte
      assert uart_tx = '1'
        report "REQ R49: UART-Stoppbit ist nicht '1'"
        severity error;
      v := r;
    end procedure uart_recv_byte;

    procedure wait_led(exp : std_logic_vector(3 downto 0); tmax : time) is
    begin
      wait until led = exp for tmax;
    end procedure wait_led;

  begin
    -- ================================================================
    -- 1) Fibonacci-Festprogramm "00" im automatischen Takt (sw = 0000)
    -- ================================================================
    wait_cycles(10);  -- rst='1' liegt von Beginn an (Power-on)
    assert led = "0000" report "REQ R4: synchroner Reset active high loescht led" severity error;
    assert led = "0000" report "REQ R43: bei rst=1 sind alle Register/LED in 0/Ruhe" severity error;
    assert uart_tx = '1' report "REQ R43: bei rst=1 ist der UART-Sender in Ruhe (tx=1)" severity error;
    rst <= '0';
    wait_cycles(3);

    wait_led("0001", 30 us);
    assert led = "0001" report "REQ R44: Power-on-/Reset-Zustand startet Fibonacci (Programm 00)" severity error;
    assert led = "0001" report "REQ R45: Fibonacci-Festprogramm 00 laeuft (erstes OUT=1)" severity error;
    assert led = "0001" report "REQ R16: Bus-Multiplexer liefert Operanden/Ergebnisse korrekt" severity error;
    assert led = "0001" report "REQ R21: Steuerwerk erzeugt wirksame Steuersignale (Fetch+LDI+OUT)" severity error;
    assert led = "0001" report "REQ R22: Fetch in T0 (MI+CO) und T1 (RO+II+CE)" severity error;
    assert led = "0001" report "REQ R28: LDI n in T2 (IO+AI)" severity error;
    assert led = "0001" report "REQ R33: OUT-Befehl in T2 (AO+OI)" severity error;
    report "CHECK t=" & time'image(now) & " fib led=" & hex4(led) severity note;
    wait_led("0010", 30 us);
    assert led = "0010" report "REQ R25: ADD a (T2 IO+MI, T3 RO+BI, T4 EO+AI+FI), 1+1=2" severity error;
    assert led = "0010" report "REQ R19: Flags-Register uebernimmt bei FI Carry/Zero der ALU" severity error;
    wait_led("0011", 30 us);
    assert led = "0011" report "REQ R27: STA a (T2 IO+MI, T3 AO+RI) speichert Zwischensummen" severity error;
    assert led = "0011" report "REQ R35: Mikroschritte wirken gleichzeitig mit Vor-Flanken-Werten (RI nutzt MAR vor Flanke)" severity error;
    wait_led("0101", 30 us);
    assert led = "0101" report "REQ R24: LDA a (T2 IO+MI, T3 RO+AI), OUT=5" severity error;
    wait_led("1000", 30 us);
    assert led = "1000" report "REQ R18: ALU addiert (A+B) mod 256, 5+3=8, Carry/Zero korrekt" severity error;
    assert led = "1000" report "REQ R36: Mikroschrittzaehler rueckt nach jedem Schritt vor (T4->T0)" severity error;
    assert led = "1000" report "REQ R29: JMP t in T2 (IO+J)" severity error;
    report "CHECK t=" & time'image(now) & " fib led=" & hex4(led) severity note;

    -- oberes Halbbyte: OUT=8 -> oben 0
    sw <= "0001";
    wait_cycles(10);
    assert led = "0000" report "REQ R7: sw(0)=1 zeigt oberes OUT-Halbbyte" severity error;
    assert led = "0000" report "REQ R42: led-Register uebernimmt jeden Takt das gewaehlte Halbbyte" severity error;
    report "CHECK t=" & time'image(now) & " fib-upper led=" & hex4(led) severity note;

    -- ================================================================
    -- 2) Zaehl-Festprogramm "01" (sw = 0100), Anfang 1,2,3
    -- ================================================================
    sw <= "0100";
    wait_cycles(6);
    do_reset;
    assert led = "0000" report "REQ R9: sw(3 downto 2) waehlt das Reset-Programm (Zaehlen gestartet, OUT=0)" severity error;
    wait_led("0001", 30 us);
    assert led = "0001" report "REQ R46: Zaehl-Festprogramm 01 zaehlt aufwaerts (OUT=1)" severity error;
    wait_led("0010", 30 us);
    assert led = "0010" report "REQ R46: Zaehl-Festprogramm 01 (OUT=2)" severity error;
    assert led = "0010" report "REQ R30: JC t springt nur bei C=1 (kein Carry beim Hochzaehlen)" severity error;
    wait_led("0011", 30 us);
    assert led = "0011" report "REQ R46: Zaehl-Festprogramm 01 (OUT=3)" severity error;
    report "CHECK t=" & time'image(now) & " count led=" & hex4(led) severity note;

    -- ================================================================
    -- 3) Multiplikation "10" (sw = 1000): OUT=15, danach Halt
    -- ================================================================
    sw <= "1000";
    wait_cycles(6);
    do_reset;
    n := 0;
    for i in 1 to 5000 loop
      exit when led = "1111";
      wait until rising_edge(clk);
      n := n + 1;
    end loop;
    assert led = "1111" report "REQ R47: Multiplikation 3x5 zeigt OUT=15" severity error;
    assert led = "1111" report "REQ R9: sw(3 downto 2)=10 waehlt Programm 10" severity error;
    assert led = "1111" report "REQ R8: sw(1)=0 waehlt automatischen Takt (ein Mikroschritt je Tick)" severity error;
    assert led = "1111" report "REQ R26: SUB a mit SU+FI, Borrow-Pfad (Schleifenabbruch bei C=0)" severity error;
    assert led = "1111" report "REQ R30: JC t genommen bei C=1 und uebergangen bei C=0" severity error;
    assert led = "1111" report "REQ R41: Schrittfreigabe ist Tick im Board-Modus (Auto-Takt laeuft)" severity error;
    assert n < 2000 report "REQ R40: Tick-Generator pulst schnell (TICK_CYCLES=2)" severity error;
    assert n < 2000 report "REQ R72: Testbench-Generics TICK_CYCLES=2, DEBOUNCE_CYCLES=2, CLKS_PER_BIT=8 (schneller Fortschritt)" severity error;
    assert led = "1111" report "REQ R73: Programm 10 im Auto-Takt: OUT=15" severity error;
    report "CHECK t=" & time'image(now) & " mul15 led=" & hex4(led) & " cycles=" & integer'image(n) severity note;
    -- oberes Halbbyte von 15 ist 0
    sw <= "1001";
    wait_cycles(10);
    assert led = "0000" report "REQ R7: sw(0)=1 zeigt oberes Halbbyte von OUT=15 (0)" severity error;
    sw <= "1000";
    wait_cycles(5);
    -- HLT: keine Aenderung mehr
    wait_cycles(200);
    assert led = "1111" report "REQ R34: HLT in T2 haelt die CPU an (OUT bleibt 15)" severity error;
    assert led = "1111" report "REQ R37: bei HLT frieren alle Register und der T-Zaehler ein" severity error;
    -- Board-Modus sendet nichts
    wait until uart_tx = '0' for 5 us;
    assert uart_tx = '1' report "REQ R52: im Board-Modus bleibt uart_tx=1 (kein Senden)" severity error;
    assert uart_tx = '1' report "REQ R77: im Board-Modus wird nichts gesendet" severity error;
    report "CHECK t=" & time'image(now) & " mul-halt led=" & hex4(led) severity note;

    -- ================================================================
    -- 4) Countdown "11" (sw = 1100): Folge 10..0, danach Halt
    -- ================================================================
    sw <= "1100";
    wait_cycles(6);
    do_reset;
    wait_led("1010", 30 us);
    assert led = "1010" report "REQ R48: Countdown-Programm 11 startet mit OUT=10" severity error;
    assert led = "1010" report "REQ R28: LDI 10 laedt A" severity error;
    assert led = "1010" report "REQ R73: Programm 11 im Auto-Takt: OUT=10" severity error;
    report "CHECK t=" & time'image(now) & " cd led=" & hex4(led) severity note;
    -- oberes Halbbyte von 10 ist 0
    sw <= "1101";
    wait_cycles(10);
    assert led = "0000" report "REQ R7: oberes Halbbyte von OUT=10 ist 0" severity error;
    assert led = "0000" report "REQ R42: led folgt dem OUT-Wert ueber sw(0)-Mux" severity error;
    sw <= "1100";
    wait_cycles(5);
    wait_led("1001", 30 us);
    assert led = "1001" report "REQ R48: Countdown OUT=9" severity error;
    wait_led("1000", 30 us);
    assert led = "1000" report "REQ R48: Countdown OUT=8" severity error;
    wait_led("0111", 30 us);
    assert led = "0111" report "REQ R23: NOP 0000 hat keine weiteren Signale (Zaehler laeuft weiter)" severity error;
    wait_led("0110", 30 us);
    assert led = "0110" report "REQ R48: Countdown OUT=6" severity error;
    wait_led("0101", 30 us);
    assert led = "0101" report "REQ R48: Countdown OUT=5" severity error;
    wait_led("0100", 30 us);
    assert led = "0100" report "REQ R48: Countdown OUT=4" severity error;
    wait_led("0011", 30 us);
    assert led = "0011" report "REQ R48: Countdown OUT=3" severity error;
    wait_led("0010", 30 us);
    assert led = "0010" report "REQ R48: Countdown OUT=2" severity error;
    wait_led("0001", 30 us);
    assert led = "0001" report "REQ R48: Countdown OUT=1" severity error;
    assert led = "0001" report "REQ R26: SUB erniedrigt A (1-1=0 im letzten Schritt)" severity error;
    wait_led("0000", 30 us);
    assert led = "0000" report "REQ R48: Countdown OUT=0, danach Halt" severity error;
    assert led = "0000" report "REQ R31: JZ t springt nur bei Z=1 (Schleifenende bei A=0)" severity error;
    report "CHECK t=" & time'image(now) & " cd-end led=" & hex4(led) severity note;
    wait_cycles(200);
    assert led = "0000" report "REQ R34: HLT nach Countdown (OUT bleibt 0)" severity error;
    assert led = "0000" report "REQ R37: Haltezustand friert CPU bis Reset/UART-Programm ein" severity error;

    -- ================================================================
    -- 5) Einzeltakt (sw = 1110): kein Druck -> kein Fortschritt,
    --    8 Druecke -> OUT=10 (exakt ein Mikroschritt je Druck)
    -- ================================================================
    sw <= "1110";
    wait_cycles(6);
    do_reset;
    wait_cycles(20);
    assert led = "0000" report "REQ R5: im Einzeltakt ohne Tastendruck kein Mikroschritt" severity error;
    assert led = "0000" report "REQ R8: sw(1)=1 waehlt Einzeltakt ueber btn_step" severity error;
    -- 1-Takt-Stoerimpuls darf keinen Schritt ausloesen (Sync + Entpreller)
    wait until falling_edge(clk);
    btn_step <= '1';
    wait until falling_edge(clk);
    btn_step <= '0';
    wait_cycles(20);
    assert led = "0000" report "REQ R38: Eingangs-Synchronisierer (2 FF) filtern kurze Impulse" severity error;
    assert led = "0000" report "REQ R39: Entpreller braucht DEBOUNCE_CYCLES stabile Takte (1-Takt-Puls -> kein rise)" severity error;
    -- 7 Druecke: Fetch + LDI ohne OUT -> OUT bleibt 0
    for i in 1 to 7 loop
      press_once;
    end loop;
    assert led = "0000" report "REQ R5: jeder Druck genau ein Mikroschritt (nach 7 Schritten noch kein OUT)" severity error;
    assert led = "0000" report "REQ R20: T-Zaehler T0..T4 aus Opcode+Flags (nach 7 Schritten: T3 ohne OUT-Signal)" severity error;
    assert led = "0000" report "REQ R36: T-Zaehler rueckt pro Druck genau eins weiter" severity error;
    press_once;  -- 8. Druck: T2 von OUT -> OUT=10
    assert led = "1010" report "REQ R74: im Einzeltakt steht 10 nach genau 8 Druecken in OUT" severity error;
    assert led = "1010" report "REQ R5: 8. Druck fuehrt 8. Mikroschritt aus (OUT=10)" severity error;
    assert led = "1010" report "REQ R22: Fetch T0/T1 + OUT-T2 in exakt 8 Mikroschritten" severity error;
    assert led = "1010" report "REQ R33: OUT-Befehl (AO+OI) im 8. Mikroschritt" severity error;
    assert led = "1010" report "REQ R39: Entpreller liefert genau einen rise je Tastendruck" severity error;
    report "CHECK t=" & time'image(now) & " single-step led=" & hex4(led) severity note;

    -- ================================================================
    -- 6) UART: fibonacci_halt (13 Antwortbytes)
    -- ================================================================
    sw <= "0000";
    wait_cycles(6);
    do_reset;
    uart_send_frame(PROG_FIB_HALT);
    t0 := now;
    for i in EXP_FIB'range loop
      if i = 0 then
        wait until falling_edge(uart_tx) for RX_TIMEOUT;
        assert uart_tx = '0' report "REQ R51: nach vollem Rahmen startet der UART-Modus (erstes OUT kommt)" severity error;
        assert (now - t0) < 5 us report "REQ R41: im UART-Modus ein Mikroschritt je Takt (schnelles erstes Zeichen)" severity error;
        t0 := now;  -- fallende Flanke des Startbits
        wait for BIT_TIME * 3 / 2;
        for k in 0 to 7 loop
          b(k) := uart_tx;
          wait for BIT_TIME;
        end loop;
        assert uart_tx = '1' report "REQ R49: UART 8N1 mit Stoppbit 1 (erstes Zeichen)" severity error;
        t1 := now;  -- Stoppbit-Mitte: 1,5 + 7 + 1 = 9,5 Bitzeiten = 760 ns
        assert (t1 - t0) >= 750 ns and (t1 - t0) <= 770 ns
          report "REQ R72: CLKS_PER_BIT=8 (9,5 Bit * 80 ns = 760 ns)" severity error;
      else
        uart_recv_byte(b);
      end if;
      assert b = EXP_FIB(i)
        report "REQ R55: fibonacci_halt Byte " & integer'image(i) &
               " erwartet " & hex8(EXP_FIB(i)) & " erhalten " & hex8(b)
        severity error;
    end loop;
    assert b = EXP_FIB(EXP_FIB'right)
      report "REQ R75: UART-Laden mit Hardwaretests, Antwortbytes auf uart_tx (fibonacci vollstaendig)"
      severity error;
    report "CHECK t=" & time'image(now) & " fib-uart last=" & hex8(b) severity note;

    -- ================================================================
    -- 7) UART: multiply_7x9 -> 3f
    -- ================================================================
    uart_send_frame(PROG_MUL79);
    uart_recv_byte(b);
    assert b = x"3F" report "REQ R56: multiply_7x9 antwortet 3f (7*9=63), erhalten " & hex8(b) severity error;
    report "CHECK t=" & time'image(now) & " mul79=" & hex8(b) severity note;

    -- ================================================================
    -- 8) UART: countdown_5 -> 05 04 03 02 01 00
    -- ================================================================
    uart_send_frame(PROG_CD5);
    for i in EXP_CD5'range loop
      uart_recv_byte(b);
      assert b = EXP_CD5(i)
        report "REQ R57: countdown_5 Byte " & integer'image(i) &
               " erwartet " & hex8(EXP_CD5(i)) & " erhalten " & hex8(b)
        severity error;
    end loop;
    report "CHECK t=" & time'image(now) & " cd5 last=" & hex8(b) severity note;

    -- ================================================================
    -- 9) UART: borrow_3_minus_5 -> fe
    -- ================================================================
    uart_send_frame(PROG_BOR);
    uart_recv_byte(b);
    assert b = x"FE" report "REQ R58: borrow_3_minus_5 antwortet fe (3-5 mod 256), erhalten " & hex8(b) severity error;
    assert b = x"FE" report "REQ R18: SUB mit SU: (A+(not B)+1) mod 256, Carry=0 bei A<B" severity error;
    assert b = x"FE" report "REQ R19: FI uebernimmt C=0/Z=0, JC wird nicht genommen" severity error;
    report "CHECK t=" & time'image(now) & " borrow=" & hex8(b) severity note;

    -- ================================================================
    -- 10) Zeichen mit defektem Stoppbit wird verworfen;
    --     danach laeuft ein gueltiger Rahmen trotzdem
    -- ================================================================
    uart_send_byte_bad_stop(x"55");
    report "CHECK t=" & time'image(now) & " bad-stop gesendet" severity note;
    uart_send_frame(PROG_MUL79);
    uart_recv_byte(b);
    assert b = x"3F" report "REQ R49: Zeichen mit falschem Stoppbit verworfen (Folgerahmen ok), erhalten " & hex8(b) severity error;

    -- ================================================================
    -- 11) Rahmen mit Laenge 17 wird verworfen, danach gueltiger Rahmen
    -- ================================================================
    uart_send_byte(x"11");  -- Laenge 17: ausserhalb 1..16
    uart_send_byte(x"00");
    uart_send_byte(x"00");
    uart_send_byte(x"00");
    wait for CLK_PERIOD * 20;
    wait until uart_tx = '0' for 2 us;
    assert uart_tx = '1' report "REQ R50: Rahmen mit n=17 verworfen (kein Neustart, kein Zeichen)" severity error;
    assert uart_tx = '1' report "REQ R76: Laenge-17-Rahmen verworfen (keine Antwort)" severity error;
    report "CHECK t=" & time'image(now) & " len17 discarded" severity note;
    uart_send_frame(PROG_CD5);
    uart_recv_byte(b);
    assert b = x"05" report "REQ R76: nach verworfenem Rahmen laeuft gueltiger Rahmen (countdown erstes Byte 05), erhalten " & hex8(b) severity error;
    for i in 1 to EXP_CD5'right loop
      uart_recv_byte(b);
      assert b = EXP_CD5(i)
        report "REQ R50: Laderahmen LE-Laenge + n Bytes + START-LF (Folgebyte " & integer'image(i) & ")"
        severity error;
    end loop;
    report "CHECK t=" & time'image(now) & " after-invalid last=" & hex8(b) severity note;

    -- ================================================================
    -- 12) Erstes Rahmenbyte im UART-Modus haelt CPU an (Endlos-OUT)
    -- ================================================================
    uart_send_frame(PROG_LOOP);
    uart_recv_byte(b);
    assert b = x"00" report "REQ R53: Endlos-OUT-Programm sendet im UART-Modus (00), erhalten " & hex8(b) severity error;
    -- nur erstes Laengenbyte des neuen Rahmens senden -> CPU muss anhalten
    uart_send_byte(x"10");  -- n=16, Rest folgt spaeter
    report "CHECK t=" & time'image(now) & " first len byte sent, CPU muss halten" severity note;
    wait until falling_edge(uart_tx) for 2 us;
    assert uart_tx = '1' report "REQ R53: erstes Rahmenbyte haelt CPU bis Rahmenende an (kein Zeichen)" severity error;
    -- Rahmen vervollstaendigen (Rest von multiply_7x9)
    uart_send_byte(x"00");
    uart_send_byte(x"00");
    uart_send_byte(x"00");
    for i in PROG_MUL79'range loop
      uart_send_byte(PROG_MUL79(i));
    end loop;
    for i in TRAIL'range loop
      uart_send_byte(TRAIL(i));
    end loop;
    uart_recv_byte(b);
    assert b = x"3F" report "REQ R53: nach vollstaendigem Rahmen laeuft neues Programm (3f), erhalten " & hex8(b) severity error;
    report "CHECK t=" & time'image(now) & " resume=" & hex8(b) severity note;

    -- ================================================================
    -- 13) Opcode 1001 verhaelt sich wie NOP (LDI 5, 0x90, OUT, HLT)
    -- ================================================================
    uart_send_frame(PROG_NOP9);
    uart_recv_byte(b);
    assert b = x"05" report "REQ R32: Opcodes 1001-1101 wie NOP (Antwort 05), erhalten " & hex8(b) severity error;
    report "CHECK t=" & time'image(now) & " nop9=" & hex8(b) severity note;

    -- ================================================================
    -- 14) Reset fuehrt in den Board-Modus zurueck (Fibonacci, tx=1)
    -- ================================================================
    sw <= "0000";
    wait_cycles(6);
    rst <= '1';
    wait_cycles(10);
    assert uart_tx = '1' report "REQ R43: Reset setzt UART-Sender zurueck (tx=1)" severity error;
    assert led = "0000" report "REQ R4: Reset wirkt synchron active high" severity error;
    rst <= '0';
    wait_cycles(3);
    wait until uart_tx = '0' for 5 us;
    assert uart_tx = '1' report "REQ R77: Reset fuehrt in den Board-Modus zurueck (Stille auf tx)" severity error;
    wait_led("0001", 30 us);
    assert led = "0001" report "REQ R77: nach Reset laeuft wieder das Fibonacci-Festprogramm" severity error;
    report "CHECK t=" & time'image(now) & " back-to-board led=" & hex4(led) severity note;

    -- ================================================================
    -- Ende
    -- ================================================================
    report "TB_COMPLETE" severity note;
    tb_done <= true;
    std.env.stop(0);
    wait;
  end process stim;

end architecture sim;