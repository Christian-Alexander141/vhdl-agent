library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
library std;
use std.env.all;

entity loader_tb is
end entity loader_tb;

architecture sim of loader_tb is
  constant CLK_PERIOD : time := 20 ns;

  signal clk         : std_logic := '0';
  signal rst         : std_logic := '1';
  signal rx_data     : std_logic_vector(7 downto 0) := (others => '0');
  signal rx_valid    : std_logic := '0';
  signal loader_busy : std_logic;
  signal prog_data   : std_logic_vector(127 downto 0);
  signal prog_valid  : std_logic;
  signal uart_mode   : std_logic;

  signal tb_done : boolean := false;

  -- Erwartungswerte aus PROMPT.md (Hardwaretests), nicht aus Implementierung.
  -- Abbildung: RAM(i) = prog_data(8*i+7 downto 8*i), RAM[n..15] = 0.
  constant EXP_ZERO    : std_logic_vector(127 downto 0) := (others => '0');
  constant EXP_N1_AB   : std_logic_vector(127 downto 0) := x"000000000000000000000000000000AB";
  constant EXP_N2_55AA : std_logic_vector(127 downto 0) := x"0000000000000000000000000000AA55";
  constant EXP_N2_1122 : std_logic_vector(127 downto 0) := x"00000000000000000000000000002211";
  constant EXP_FIB     : std_logic_vector(127 downto 0) := x"00010000F000601D4E1F4D1E4F7B2EE0";
  constant EXP_MUL     : std_logic_vector(127 downto 0) := x"0907000100604D2F1D4EF0E01D763C1E";
  constant EXP_CNT     : std_logic_vector(127 downto 0) := x"010000000000000000F0E061853FE055";
  constant EXP_BOR     : std_logic_vector(127 downto 0) := x"0500000000000000F0E051F0E0753F53";

begin
  clk <= not clk after CLK_PERIOD / 2 when not tb_done else '0';

  dut: entity work.loader
    port map (
      clk         => clk,
      rst         => rst,
      rx_data     => rx_data,
      rx_valid    => rx_valid,
      loader_busy => loader_busy,
      prog_data   => prog_data,
      prog_valid  => prog_valid,
      uart_mode   => uart_mode
    );

  stim: process
    procedure wait_cyc(n : positive) is
    begin
      for i in 1 to n loop
        wait until rising_edge(clk);
        wait for 1 ns;
      end loop;
    end procedure;

    procedure send_byte(b : in std_logic_vector(7 downto 0)) is
    begin
      rx_data  <= b;
      rx_valid <= '1';
      wait until rising_edge(clk);
      wait for 1 ns;
    end procedure;

    procedure idle_cyc(n : positive) is
    begin
      rx_valid <= '0';
      rx_data  <= (others => '0');
      for i in 1 to n loop
        wait until rising_edge(clk);
        wait for 1 ns;
      end loop;
    end procedure;

    procedure send_trail_ok is
    begin
      send_byte(x"53");
      send_byte(x"54");
      send_byte(x"41");
      send_byte(x"52");
      send_byte(x"54");
      send_byte(x"0A");
    end procedure;
  begin
    -- Init: synchroner Reset, active high, min. 2 Zyklen.
    rst      <= '1';
    rx_data  <= (others => '0');
    rx_valid <= '0';
    wait_cyc(3);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " reset held busy=" & std_logic'image(loader_busy)
      & " valid=" & std_logic'image(prog_valid) & " mode=" & std_logic'image(uart_mode) severity note;
    assert uart_mode = '0' report "REQ R43: bei rst=1 CPU im Board-Modus (uart_mode=0)" severity error;
    assert prog_valid = '0' report "REQ R43: bei rst=1 kein prog_valid (Lader in Ruhe)" severity error;
    assert loader_busy = '0' report "REQ R43: bei rst=1 ohne rx_valid loader_busy=0" severity error;
    assert prog_data = EXP_ZERO report "REQ R43: bei rst=1 Programmpuffer 0" severity error;
    assert uart_mode = '0' report "REQ R4: rst active-high synchron haelt Board-Modus" severity error;
    assert uart_mode = '0' report "REQ R52: im Board-Modus uart_mode=0 (kein Senden, tx bleibt 1)" severity error;
    assert uart_mode = '0' report "REQ R53: nach Reset UART-Modus aus (endet nur per Reset)" severity error;

    rst <= '0';
    wait for 1 ns;
    wait_cyc(1);
    report "CHECK t=" & time'image(now) & " nach Reset-Rel. mode=" & std_logic'image(uart_mode) severity note;
    assert uart_mode = '0' report "REQ R77: Reset fuehrt in Board-Modus zurueck (uart_mode=0)" severity error;

    -- R50: Laenge 0 (00 00 00 00) wird verworfen.
    send_byte(x"00");
    report "CHECK t=" & time'image(now) & " len0 b0 busy=" & std_logic'image(loader_busy) severity note;
    assert prog_valid = '0' report "REQ R50: Laengenbyte 0 darf kein prog_valid geben" severity error;
    assert loader_busy = '1' report "REQ R41: loader_busy=1 waehrend Rahmenempfang (Laenge)" severity error;
    send_byte(x"00");
    send_byte(x"00");
    send_byte(x"00");
    report "CHECK t=" & time'image(now) & " len0 4. Byte busy=" & std_logic'image(loader_busy)
      & " valid=" & std_logic'image(prog_valid) & " mode=" & std_logic'image(uart_mode) severity note;
    assert prog_valid = '0' report "REQ R50: Laenge 0 ausserhalb 1..16 verworfen (kein prog_valid)" severity error;
    assert uart_mode = '0' report "REQ R50: verworfener Rahmen setzt keinen UART-Modus" severity error;
    idle_cyc(1);
    report "CHECK t=" & time'image(now) & " nach len0-Verwurf busy=" & std_logic'image(loader_busy) severity note;
    assert loader_busy = '0' report "REQ R53: nach Verwerfen busy=0 (CPU laeuft weiter)" severity error;
    assert prog_valid = '0' report "REQ R50: nach Verwerfen weiter kein prog_valid" severity error;

    -- R50: Laenge mit gesetztem Hochbyte (01 01 00 00 = 257) verworfen.
    send_byte(x"01");
    send_byte(x"01");
    send_byte(x"00");
    send_byte(x"00");
    report "CHECK t=" & time'image(now) & " len-hi verworfen valid=" & std_logic'image(prog_valid) severity note;
    assert prog_valid = '0' report "REQ R50: Laenge mit b1/=0 verworfen (n muss 1..16, Rest 0)" severity error;
    assert uart_mode = '0' report "REQ R50: Hochbyte-Laenge setzt keinen UART-Modus" severity error;
    idle_cyc(1);
    assert loader_busy = '0' report "REQ R53: nach Hochbyte-Verwurf busy=0" severity error;

    -- Gueltiger Minimalrahmen n=1: 01 00 00 00, prog AB, START+LF.
    -- Mit Luecke nach 2 Laengenbytes: busy muss trotzdem 1 bleiben.
    send_byte(x"01");
    send_byte(x"00");
    rx_valid <= '0';
    rx_data  <= (others => '0');
    wait until rising_edge(clk);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " Luecke mitten im Rahmen busy=" & std_logic'image(loader_busy) severity note;
    assert loader_busy = '1' report "REQ R53: Lader haelt CPU bis Rahmenende (busy=1 trotz rx_valid=0)" severity error;
    assert loader_busy = '1' report "REQ R41: loader_busy=1 sperrt Schrittfreigabe im UART-Modus" severity error;
    assert prog_valid = '0' report "REQ R51: vor Rahmenende kein prog_valid" severity error;
    assert uart_mode = '0' report "REQ R52: vor erstem vollstaendigem Rahmen Board-Modus (kein Senden)" severity error;
    send_byte(x"00");
    send_byte(x"00");
    report "CHECK t=" & time'image(now) & " len-ok n=1" severity note;
    assert prog_valid = '0' report "REQ R50: gueltige Laenge 1.t akz. ohne prog_valid" severity error;
    send_byte(x"AB");
    report "CHECK t=" & time'image(now) & " prog AB busy=" & std_logic'image(loader_busy) severity note;
    assert prog_valid = '0' report "REQ R51: nach Programmbyte noch kein prog_valid (Trail fehlt)" severity error;
    send_byte(x"53");
    send_byte(x"54");
    send_byte(x"41");
    send_byte(x"52");
    send_byte(x"54");
    assert prog_valid = '0' report "REQ R50: vor letztem START-Zeichen kein prog_valid" severity error;
    send_byte(x"0A");
    report "CHECK t=" & time'image(now) & " DONE n=1 valid=" & std_logic'image(prog_valid)
      & " mode=" & std_logic'image(uart_mode) & " busy=" & std_logic'image(loader_busy) severity note;
    assert prog_valid = '1' report "REQ R51: vollstaendiger Rahmen setzt prog_valid=1 (ein Takt)" severity error;
    assert uart_mode = '1' report "REQ R51: vollstaendiger Rahmen startet UART-Modus mit 1 Schritt/Takt" severity error;
    assert loader_busy = '1' report "REQ R53: in S_DONE busy=1 (Rahmenabschluss)" severity error;
    assert prog_data = EXP_N1_AB report "REQ R51: RAM[0]=AB, RAM[1..15]=0 bei n=1" severity error;
    assert prog_data(7 downto 0) = x"AB" report "REQ R51: prog_data-Abbildung RAM(0)=Byte0" severity error;
    assert uart_mode = '1' report "REQ R52: im UART-Modus OI-Mikroschritte senden (uart_mode=1)" severity error;
    assert uart_mode = '1' report "REQ R75: UART-Laden erfolgreich (uart_mode=1)" severity error;
    rx_valid <= '0';
    rx_data  <= (others => '0');
    wait until rising_edge(clk);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " nach DONE valid=" & std_logic'image(prog_valid)
      & " busy=" & std_logic'image(loader_busy) & " mode=" & std_logic'image(uart_mode) severity note;
    assert prog_valid = '0' report "REQ R51: prog_valid genau einen Takt (danach 0)" severity error;
    assert loader_busy = '0' report "REQ R53: nach Rahmenende busy=0 (CPU weiter)" severity error;
    assert uart_mode = '1' report "REQ R53: UART-Modus bleibt bis Reset (nicht von selbst aus)" severity error;

    -- R4/R43: synchroner Reset aus UART-Modus, mitten im Takt gesetzt.
    wait_cyc(1);
    assert uart_mode = '1' report "REQ R53: vor Reset UART-Modus gehalten" severity error;
    wait for 2 ns;
    rst <= '1';
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " rst=1 vor Flanke mode=" & std_logic'image(uart_mode) severity note;
    assert uart_mode = '1' report "REQ R4: synchroner Reset wirkt erst mit Flanke (uart_mode noch 1)" severity error;
    assert prog_valid = '0' report "REQ R4: vor Flanke kein async Durchgriff auf prog_valid" severity error;
    wait until rising_edge(clk);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " nach Reset-Flanke mode=" & std_logic'image(uart_mode) severity note;
    assert uart_mode = '0' report "REQ R4: synchroner Reset active-high loescht uart_mode an Flanke" severity error;
    assert prog_valid = '0' report "REQ R43: bei rst=1 Lader in Ruhe (kein prog_valid)" severity error;
    assert prog_data = EXP_ZERO report "REQ R43: bei rst=1 Puffer 0" severity error;
    assert loader_busy = '0' report "REQ R43: bei rst=1 ohne rx_valid busy=0" severity error;
    wait_cyc(2);
    rst <= '0';
    wait for 1 ns;
    wait_cyc(1);
    assert uart_mode = '0' report "REQ R77: Reset in Board-Modus zurueck (Stille, tx=1 via uart_mode=0)" severity error;
    assert uart_mode = '0' report "REQ R52: nach Reset Board-Modus, kein Senden" severity error;

    -- R50/R76: Rahmen mit Laenge 17 (11 00 00 00) verwerfen.
    send_byte(x"11");
    send_byte(x"00");
    send_byte(x"00");
    send_byte(x"00");
    report "CHECK t=" & time'image(now) & " len17 valid=" & std_logic'image(prog_valid) severity note;
    assert prog_valid = '0' report "REQ R76: Rahmen mit Laenge 17 verworfen (kein prog_valid)" severity error;
    assert prog_valid = '0' report "REQ R50: Laenge 17 ausserhalb 1..16 verworfen" severity error;
    assert uart_mode = '0' report "REQ R76: verworfener 17er-Rahmen setzt keinen UART-Modus" severity error;
    idle_cyc(1);
    assert loader_busy = '0' report "REQ R53: nach 17er-Verwurf busy=0" severity error;

    -- R76: danach gesendeter gueltiger Rahmen (n=2: 55 AA) laeuft trotzdem.
    send_byte(x"02");
    send_byte(x"00");
    send_byte(x"00");
    send_byte(x"00");
    send_byte(x"55");
    send_byte(x"AA");
    send_trail_ok;
    report "CHECK t=" & time'image(now) & " DONE n=2 nach len17 mode=" & std_logic'image(uart_mode) severity note;
    assert prog_valid = '1' report "REQ R76: gueltiger Rahmen nach 17er-Verwurf laeuft (prog_valid=1)" severity error;
    assert uart_mode = '1' report "REQ R51: nach gueltigem Rahmen UART-Modus" severity error;
    assert prog_data = EXP_N2_55AA report "REQ R51: RAM[0]=55 RAM[1]=AA RAM[2..15]=0" severity error;
    assert prog_data = EXP_N2_55AA report "REQ R75: UART-Laden n=2 ok" severity error;
    rx_valid <= '0';
    rx_data  <= (others => '0');
    wait until rising_edge(clk);
    wait for 1 ns;
    assert prog_valid = '0' report "REQ R51: prog_valid nur ein Takt (n=2)" severity error;
    assert loader_busy = '0' report "REQ R41: nach Rahmen busy=0 (Freigabe wieder offen)" severity error;

    -- Zurueck in Board-Modus fuer Trail-Fehlertest.
    rst <= '1';
    wait_cyc(2);
    wait for 1 ns;
    rst <= '0';
    wait for 1 ns;
    wait_cyc(1);
    assert uart_mode = '0' report "REQ R43: Reset vor Trail-Test (Board-Modus)" severity error;

    -- R50: falsches START-Zeichen (letztes 00 statt 0A) verwirft.
    send_byte(x"02");
    send_byte(x"00");
    send_byte(x"00");
    send_byte(x"00");
    send_byte(x"11");
    send_byte(x"22");
    send_byte(x"53");
    send_byte(x"54");
    send_byte(x"41");
    send_byte(x"52");
    send_byte(x"54");
    send_byte(x"00");
    report "CHECK t=" & time'image(now) & " trail-falsch valid=" & std_logic'image(prog_valid) severity note;
    assert prog_valid = '0' report "REQ R50: falsches Zeichen in START verwirft Rahmen" severity error;
    assert uart_mode = '0' report "REQ R50: falscher Trail setzt keinen UART-Modus" severity error;
    idle_cyc(1);
    assert loader_busy = '0' report "REQ R53: nach Trail-Verwurf busy=0" severity error;
    -- Naechstes Byte wieder erstes Laengenbyte: gleicher Inhalt korrekt senden.
    send_byte(x"02");
    send_byte(x"00");
    send_byte(x"00");
    send_byte(x"00");
    send_byte(x"11");
    send_byte(x"22");
    send_trail_ok;
    report "CHECK t=" & time'image(now) & " DONE nach Trail-Repair" severity note;
    assert prog_valid = '1' report "REQ R50: naechstes Byte wieder erstes Laengenbyte (Repair laeuft)" severity error;
    assert prog_data = EXP_N2_1122 report "REQ R51: Repair-Rahmen RAM[0]=11 RAM[1]=22 Rest 0" severity error;
    rx_valid <= '0';
    rx_data  <= (others => '0');
    wait until rising_edge(clk);
    wait for 1 ns;
    assert prog_valid = '0' report "REQ R51: Repair prog_valid ein Takt" severity error;

    -- Hardwaretests als 16-Byte-Rahmen (PROMPT.md). Reset -> Board-Modus.
    rst <= '1';
    wait_cyc(2);
    wait for 1 ns;
    rst <= '0';
    wait for 1 ns;
    wait_cyc(1);
    assert uart_mode = '0' report "REQ R77: vor HW-Tests Board-Modus (kein Senden)" severity error;

    -- fibonacci_halt E02E7B4F1E4D1F4E1D6000F000000100
    send_byte(x"10");
    send_byte(x"00");
    send_byte(x"00");
    send_byte(x"00");
    send_byte(x"E0");
    send_byte(x"2E");
    send_byte(x"7B");
    send_byte(x"4F");
    send_byte(x"1E");
    send_byte(x"4D");
    send_byte(x"1F");
    send_byte(x"4E");
    send_byte(x"1D");
    send_byte(x"60");
    send_byte(x"00");
    send_byte(x"F0");
    send_byte(x"00");
    send_byte(x"00");
    send_byte(x"01");
    send_byte(x"00");
    send_trail_ok;
    report "CHECK t=" & time'image(now) & " HW fib mode=" & std_logic'image(uart_mode) severity note;
    assert prog_valid = '1' report "REQ R75: UART-Laden fibonacci_halt ok (prog_valid)" severity error;
    assert prog_data = EXP_FIB report "REQ R55: fibonacci_halt Programm E02E..0100 geladen" severity error;
    assert uart_mode = '1' report "REQ R53: nach HW-Rahmen UART-Modus" severity error;
    rx_valid <= '0';
    rx_data  <= (others => '0');
    wait until rising_edge(clk);
    wait for 1 ns;
    assert prog_valid = '0' report "REQ R51: HW fib prog_valid ein Takt" severity error;
    assert loader_busy = '0' report "REQ R41: nach HW fib busy=0" severity error;

    -- multiply_7x9, erstes Byte mit sofort-Busy-Check im UART-Modus (R53).
    rx_data  <= x"10";
    rx_valid <= '1';
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " UART-mode Erstbyte busy=" & std_logic'image(loader_busy) severity note;
    assert loader_busy = '1' report "REQ R53: erstes Rahmenbyte im UART-Modus haelt CPU sofort an" severity error;
    wait until rising_edge(clk);
    wait for 1 ns;
    send_byte(x"00");
    send_byte(x"00");
    send_byte(x"00");
    send_byte(x"1E");
    send_byte(x"3C");
    send_byte(x"76");
    send_byte(x"1D");
    send_byte(x"E0");
    send_byte(x"F0");
    send_byte(x"4E");
    send_byte(x"1D");
    send_byte(x"2F");
    send_byte(x"4D");
    send_byte(x"60");
    send_byte(x"00");
    send_byte(x"01");
    send_byte(x"00");
    send_byte(x"07");
    send_byte(x"09");
    send_trail_ok;
    report "CHECK t=" & time'image(now) & " HW mul" severity note;
    assert prog_valid = '1' report "REQ R75: UART-Laden multiply_7x9 ok" severity error;
    assert prog_data = EXP_MUL report "REQ R56: multiply_7x9 Programm 1E3C..0709 geladen" severity error;
    assert uart_mode = '1' report "REQ R53: UART-Modus bleibt ueber Rahmen (nur Reset beendet)" severity error;
    rx_valid <= '0';
    rx_data  <= (others => '0');
    wait until rising_edge(clk);
    wait for 1 ns;
    assert prog_valid = '0' report "REQ R51: HW mul prog_valid ein Takt" severity error;

    -- countdown_5 55E03F8561E0F0000000000000000001
    send_byte(x"10");
    send_byte(x"00");
    send_byte(x"00");
    send_byte(x"00");
    send_byte(x"55");
    send_byte(x"E0");
    send_byte(x"3F");
    send_byte(x"85");
    send_byte(x"61");
    send_byte(x"E0");
    send_byte(x"F0");
    send_byte(x"00");
    send_byte(x"00");
    send_byte(x"00");
    send_byte(x"00");
    send_byte(x"00");
    send_byte(x"00");
    send_byte(x"00");
    send_byte(x"00");
    send_byte(x"01");
    send_trail_ok;
    report "CHECK t=" & time'image(now) & " HW cnt" severity note;
    assert prog_valid = '1' report "REQ R75: UART-Laden countdown_5 ok" severity error;
    assert prog_data = EXP_CNT report "REQ R57: countdown_5 Programm 55E0..0001 geladen" severity error;
    rx_valid <= '0';
    rx_data  <= (others => '0');
    wait until rising_edge(clk);
    wait for 1 ns;
    assert prog_valid = '0' report "REQ R51: HW cnt prog_valid ein Takt" severity error;

    -- borrow_3_minus_5 533F75E0F051E0F00000000000000005
    send_byte(x"10");
    send_byte(x"00");
    send_byte(x"00");
    send_byte(x"00");
    send_byte(x"53");
    send_byte(x"3F");
    send_byte(x"75");
    send_byte(x"E0");
    send_byte(x"F0");
    send_byte(x"51");
    send_byte(x"E0");
    send_byte(x"F0");
    send_byte(x"00");
    send_byte(x"00");
    send_byte(x"00");
    send_byte(x"00");
    send_byte(x"00");
    send_byte(x"00");
    send_byte(x"00");
    send_byte(x"05");
    send_trail_ok;
    report "CHECK t=" & time'image(now) & " HW bor" severity note;
    assert prog_valid = '1' report "REQ R75: UART-Laden borrow_3_minus_5 ok" severity error;
    assert prog_data = EXP_BOR report "REQ R58: borrow_3_minus_5 Programm 533F..0005 geladen" severity error;
    assert uart_mode = '1' report "REQ R52: UART-Modus nach allen HW-Rahmen (Sendefreigabe)" severity error;
    rx_valid <= '0';
    rx_data  <= (others => '0');
    wait until rising_edge(clk);
    wait for 1 ns;
    assert prog_valid = '0' report "REQ R51: HW bor prog_valid ein Takt" severity error;
    assert loader_busy = '0' report "REQ R53: nach letztem HW-Rahmen busy=0" severity error;

    -- R77/R43: Reset fuehrt in Board-Modus zurueck (Stille).
    rst <= '1';
    wait until rising_edge(clk);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " final Reset mode=" & std_logic'image(uart_mode) severity note;
    assert uart_mode = '0' report "REQ R77: Reset in Board-Modus zurueck (uart_mode=0)" severity error;
    assert prog_valid = '0' report "REQ R43: finaler Reset Lader in Ruhe" severity error;
    assert uart_mode = '0' report "REQ R52: final Board-Modus, kein Senden" severity error;
    wait_cyc(2);
    rst <= '0';
    wait for 1 ns;
    wait_cyc(1);
    assert uart_mode = '0' report "REQ R77: nach Reset-Rel. weiter Board-Modus" severity error;
    assert loader_busy = '0' report "REQ R41: nach Reset busy=0" severity error;

    report "CHECK t=" & time'image(now) & " alle loader-Pruefungen fertig" severity note;
    tb_done <= true;
    report "TB_COMPLETE" severity note;
    std.env.stop(0);
    wait;
  end process stim;

end architecture sim;