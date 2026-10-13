-- Unabhängige Referenz-Testbench (Benchmark), dem System nicht bekannt.
-- Prüft die festen Programme an den LEDs, den Einzeltakt (Mikroschritte), das
-- Laden über die UART mit den vier Hardwaretests, das Verwerfen eines ungültigen
-- Rahmens und die Rückkehr in den Board-Modus. Reihenfolge und Inhalt exakt,
-- Zeitpunkte mit Spielraum (die Aufgabe legt die UART-Taktzahlen nicht fest).
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity ref_ben_eater_cpu_tb is
end entity;

architecture sim of ref_ben_eater_cpu_tb is
  constant CPB : positive := 8;
  type bytes_t is array (natural range <>) of std_logic_vector(7 downto 0);

  signal clk      : std_logic := '0';
  signal rst      : std_logic := '1';
  signal btn_step : std_logic := '0';
  signal sw       : std_logic_vector(3 downto 0) := "0000";
  signal led      : std_logic_vector(3 downto 0);
  signal uart_rx  : std_logic := '1';
  signal uart_tx  : std_logic;
  signal done     : boolean := false;

  -- vom Testbench-Empfänger dekodierte Zeichen
  signal rx_log   : bytes_t(0 to 63) := (others => (others => '0'));
  signal rx_count : natural := 0;

  function hex_bytes(s : string) return bytes_t is
    variable r : bytes_t(0 to s'length / 2 - 1);
    function nib(ch : character) return std_logic_vector is
    begin
      case ch is
        when '0' => return "0000"; when '1' => return "0001"; when '2' => return "0010"; when '3' => return "0011";
        when '4' => return "0100"; when '5' => return "0101"; when '6' => return "0110"; when '7' => return "0111";
        when '8' => return "1000"; when '9' => return "1001"; when 'a' | 'A' => return "1010";
        when 'b' | 'B' => return "1011"; when 'c' | 'C' => return "1100"; when 'd' | 'D' => return "1101";
        when 'e' | 'E' => return "1110"; when others => return "1111";
      end case;
    end function;
  begin
    for i in r'range loop
      r(i) := nib(s(s'low + 2 * i)) & nib(s(s'low + 2 * i + 1));
    end loop;
    return r;
  end function;
begin
  dut: entity work.ben_eater_cpu
    generic map (TICK_CYCLES => 2, DEBOUNCE_CYCLES => 2, CLKS_PER_BIT => CPB)
    port map (clk => clk, rst => rst, btn_step => btn_step, sw => sw, led => led,
              uart_rx => uart_rx, uart_tx => uart_tx);

  clk <= not clk after 5 ns when not done else '0';

  -- UART-Empfänger der Testbench (8N1, Abtastung in der Bitmitte)
  receiver: process
    variable data : std_logic_vector(7 downto 0);
  begin
    loop
      wait until falling_edge(uart_tx) or done;
      exit when done;
      for i in 1 to CPB / 2 loop wait until rising_edge(clk); end loop;
      if uart_tx = '0' then
        for b in 0 to 7 loop
          for i in 1 to CPB loop wait until rising_edge(clk); end loop;
          data(b) := uart_tx;
        end loop;
        for i in 1 to CPB loop wait until rising_edge(clk); end loop;
        if uart_tx = '1' and rx_count < 64 then
          rx_log(rx_count) <= data;
          rx_count <= rx_count + 1;
        end if;
      end if;
    end loop;
    wait;
  end process;

  stimulus: process
    variable errors : natural := 0;
    variable seen   : bytes_t(0 to 15);
    variable n_seen : natural;
    variable last   : std_logic_vector(3 downto 0);
    variable start_count : natural;

    procedure cycles(n : natural) is
    begin
      for i in 1 to n loop wait until rising_edge(clk); end loop;
    end procedure;

    procedure fail(msg : string) is
    begin
      report "REF_FAIL " & msg severity error;
      errors := errors + 1;
    end procedure;

    procedure do_reset(setting : std_logic_vector(3 downto 0)) is
    begin
      sw <= setting;
      rst <= '1';
      cycles(6);
      rst <= '0';
    end procedure;

    procedure expect_led(value : std_logic_vector(3 downto 0); what : string) is
    begin
      if led /= value then
        fail(what & ": LED erwartet " & to_string(value) & ", erhalten " & to_string(led));
      end if;
    end procedure;

    procedure send_byte(b : std_logic_vector(7 downto 0)) is
    begin
      uart_rx <= '0';
      cycles(CPB);
      for i in 0 to 7 loop
        uart_rx <= b(i);
        cycles(CPB);
      end loop;
      uart_rx <= '1';
      cycles(CPB + 2);
    end procedure;

    procedure send_frame(program : bytes_t) is
      constant START_SEQ : bytes_t := hex_bytes("53544152540a");
    begin
      send_byte(std_logic_vector(to_unsigned(program'length, 8)));
      send_byte(x"00"); send_byte(x"00"); send_byte(x"00");
      for i in program'range loop send_byte(program(i)); end loop;
      for i in START_SEQ'range loop send_byte(START_SEQ(i)); end loop;
    end procedure;

    procedure expect_reply(expected : bytes_t; what : string) is
      variable first : natural := rx_count;
    begin
      for t in 1 to 20000 loop
        exit when rx_count >= first + expected'length;
        wait until rising_edge(clk);
      end loop;
      cycles(30 * CPB);  -- zusätzliche Zeichen wären jetzt angekommen
      if rx_count /= first + expected'length then
        fail(what & ": " & integer'image(rx_count - first) & " statt " & integer'image(expected'length) & " Antwortbytes");
      end if;
      for i in expected'range loop
        if first + i < rx_count and rx_log(first + i) /= expected(i) then
          fail(what & ": Byte " & integer'image(i) & " erwartet " & to_hstring(expected(i))
               & ", erhalten " & to_hstring(rx_log(first + i)));
        end if;
      end loop;
    end procedure;

    procedure press is
    begin
      btn_step <= '1';
      cycles(8);
      btn_step <= '0';
      cycles(8);
    end procedure;

    procedure led_sequence(expected : bytes_t; budget : natural; what : string) is
    begin
      n_seen := 0;
      last := led;
      for t in 1 to budget loop
        wait until rising_edge(clk);
        if led /= last then
          last := led;
          if n_seen <= expected'high then
            if led /= expected(n_seen)(3 downto 0) then
              fail(what & ": Wert " & integer'image(n_seen + 1) & " erwartet " & to_hstring(expected(n_seen)(3 downto 0))
                   & ", erhalten " & to_hstring(led));
            end if;
          else
            fail(what & ": zusätzlicher LED-Wert " & to_hstring(led));
          end if;
          n_seen := n_seen + 1;
        end if;
      end loop;
      if n_seen /= expected'length then
        fail(what & ": " & integer'image(n_seen) & " statt " & integer'image(expected'length) & " LED-Werte");
      end if;
    end procedure;
  begin
    -- 1. Programm "10" (3 x 5) im automatischen Takt: OUT = 15, danach Halt
    do_reset("1000");
    cycles(1500);
    expect_led("1111", "Programm 10, unteres Halbbyte");
    sw <= "1001";
    cycles(6);
    expect_led("0000", "Programm 10, oberes Halbbyte");
    cycles(500);
    expect_led("0000", "Programm 10 bleibt nach HLT stehen");
    if uart_tx /= '1' or rx_count /= 0 then
      fail("im Board-Modus wurde über die UART gesendet");
    end if;

    -- 2. Programm "11" (Countdown) im automatischen Takt: 10, 9, ..., 1, 0
    do_reset("1100");
    led_sequence(hex_bytes("0a090807060504030201" & "00"), 2500, "Countdown");

    -- 3. Einzeltakt: ohne Druck nichts, jeder Druck genau ein Mikroschritt
    do_reset("1110");
    cycles(100);
    expect_led("0000", "Einzeltakt ohne Tastendruck");
    for i in 1 to 7 loop press; end loop;
    expect_led("0000", "OUT nach 7 Mikroschritten");
    btn_step <= '1';  -- Prellen: ein Takt ist kürzer als DEBOUNCE_CYCLES
    cycles(1);
    btn_step <= '0';
    cycles(20);
    expect_led("0000", "Impuls kürzer als DEBOUNCE_CYCLES löst keinen Mikroschritt aus");
    press;
    expect_led("1010", "OUT nach 8 Mikroschritten (LDI 10, OUT)");
    cycles(100);
    expect_led("1010", "keine weiteren Mikroschritte ohne Druck");

    -- 4. Laden über die UART (Board-Modus mit Fibonacci läuft vorher, sendet aber nichts)
    do_reset("0000");
    cycles(200);
    if rx_count /= 0 then fail("Fibonacci im Board-Modus sendet über die UART"); end if;
    send_frame(hex_bytes("1E3C761DE0F04E1D2F4D600001000709"));
    expect_reply(hex_bytes("3f"), "multiply_7x9");
    send_frame(hex_bytes("E02E7B4F1E4D1F4E1D6000F000000100"));
    expect_reply(hex_bytes("000101020305080d1522375990"), "fibonacci_halt");
    send_frame(hex_bytes("55E03F8561E0F0000000000000000001"));
    expect_reply(hex_bytes("050403020100"), "countdown_5");
    send_frame(hex_bytes("533F75E0F051E0F00000000000000005"));
    expect_reply(hex_bytes("fe"), "borrow_3_minus_5");

    -- 5. Ungültige Länge 17 wird verworfen, ein danach gesendeter Rahmen läuft.
    --    Vollständiger Längenwert 11 00 00 00: Die Aufgabe lässt offen, ob schon das
    --    erste Längenbyte oder erst der 4-Byte-Wert geprüft wird; beide Lesarten
    --    müssen den folgenden Rahmen ausführen (geändert 2026-10-13 nach dem MAS-Lauf).
    send_byte(x"11"); send_byte(x"00"); send_byte(x"00"); send_byte(x"00");
    send_frame(hex_bytes("1E3C761DE0F04E1D2F4D600001000709"));
    expect_reply(hex_bytes("3f"), "gültiger Rahmen nach verworfener Länge 17");

    -- 6. Kürzerer Rahmen (n = 3: LDA 15, OUT, HLT): der Rest des RAM wird 0
    --    (im Rahmen davor stand in RAM[15] noch 05)
    send_frame(hex_bytes("1FE0F0"));
    expect_reply(hex_bytes("00"), "Rahmen mit 3 Bytes, RAM[15] gelöscht");

    -- 7. Reset führt in den Board-Modus zurück
    do_reset("1000");
    cycles(1500);
    start_count := rx_count;
    cycles(500);
    if rx_count /= start_count then fail("nach dem Reset wird weiter gesendet"); end if;
    expect_led("1111", "Board-Modus nach Reset (Programm 10)");

    if errors > 0 then
      report "REF_FAIL " & integer'image(errors) & " Abweichungen" severity error;
    end if;
    report "TB_COMPLETE";
    done <= true;
    wait;
  end process;
end architecture;
