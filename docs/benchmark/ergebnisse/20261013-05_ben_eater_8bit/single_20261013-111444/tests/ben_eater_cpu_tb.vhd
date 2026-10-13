library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.env.all;

entity ben_eater_cpu_tb is
end entity ben_eater_cpu_tb;

architecture tb of ben_eater_cpu_tb is
  constant CLK_PERIOD : time := 10 ns;
  constant TICK_CYCLES_TB : positive := 2;
  constant DEBOUNCE_TB : positive := 2;
  constant CLKS_PER_BIT_TB : positive := 8;

  signal clk : std_logic := '0';
  signal rst : std_logic := '0';
  signal btn_step : std_logic := '0';
  signal sw : std_logic_vector(3 downto 0) := (others => '0');
  signal led : std_logic_vector(3 downto 0);
  signal uart_rx : std_logic := '1';
  signal uart_tx : std_logic;

  signal snoop_data : std_logic_vector(7 downto 0);
  signal snoop_valid : std_logic;

  signal stop_clk : boolean := false;
begin
  dut: entity work.ben_eater_cpu
    generic map (
      TICK_CYCLES => TICK_CYCLES_TB,
      DEBOUNCE_CYCLES => DEBOUNCE_TB,
      CLKS_PER_BIT => CLKS_PER_BIT_TB
    )
    port map (
      clk => clk, rst => rst, btn_step => btn_step, sw => sw,
      led => led, uart_rx => uart_rx, uart_tx => uart_tx
    );

  snoop: entity work.uart_rx
    generic map (CLKS_PER_BIT => CLKS_PER_BIT_TB)
    port map (clk => clk, rst => rst, rx => uart_tx, data => snoop_data, valid => snoop_valid);

  clkgen: process
  begin
    while not stop_clk loop
      clk <= '0';
      wait for CLK_PERIOD/2;
      clk <= '1';
      wait for CLK_PERIOD/2;
    end loop;
    wait;
  end process;

  main: process
    procedure wait_cycles(n : natural) is
    begin
      for i in 1 to n loop
        wait until rising_edge(clk);
      end loop;
    end;

    procedure do_reset is
    begin
      rst <= '1';
      btn_step <= '0';
      uart_rx <= '1';
      wait_cycles(12);
      rst <= '0';
      wait_cycles(6);
    end;

    procedure uart_send_byte(b : std_logic_vector(7 downto 0)) is
    begin
      -- start bit
      uart_rx <= '0';
      wait_cycles(CLKS_PER_BIT_TB);
      for i in 0 to 7 loop
        uart_rx <= b(i);
        wait_cycles(CLKS_PER_BIT_TB);
      end loop;
      uart_rx <= '1';
      wait_cycles(CLKS_PER_BIT_TB);
      -- inter-byte gap
      wait_cycles(CLKS_PER_BIT_TB*2);
    end;

    procedure uart_send_frame(prog : std_logic_vector; nbytes : integer) is
      variable nb : integer;
      variable bb : std_logic_vector(7 downto 0);
    begin
      nb := nbytes;
      -- length little endian 4 bytes
      bb := std_logic_vector(to_unsigned(nb mod 256, 8));
      uart_send_byte(bb);
      bb := std_logic_vector(to_unsigned((nb/256) mod 256, 8));
      uart_send_byte(bb);
      uart_send_byte(x"00");
      uart_send_byte(x"00");
      for i in 0 to nbytes-1 loop
        bb := prog(8*i+7 downto 8*i);
        uart_send_byte(bb);
      end loop;
      uart_send_byte(x"53"); -- S
      uart_send_byte(x"54"); -- T
      uart_send_byte(x"41"); -- A
      uart_send_byte(x"52"); -- R
      uart_send_byte(x"54"); -- T
      uart_send_byte(x"0A"); -- LF
    end;

    procedure uart_recv_byte(data_out : out std_logic_vector(7 downto 0); success : out boolean; timeout_cycles : natural := 20000) is
      variable t : natural := 0;
    begin
      success := false;
      -- wait for snoop valid pulse (hardware UART receiver)
      while t < timeout_cycles loop
        wait until rising_edge(clk);
        t := t + 1;
        if snoop_valid = '1' then
          data_out := snoop_data;
          success := true;
          exit;
        end if;
      end loop;
      if not success then
        data_out := (others => '0');
      else
        -- wait for valid to go low to avoid double-counting same byte
        wait until rising_edge(clk);
      end if;
    end;

    procedure check_no_tx(cycles : natural) is
      variable bad : boolean := false;
    begin
      for i in 1 to cycles loop
        wait until rising_edge(clk);
        if uart_tx /= '1' then
          bad := true;
        end if;
      end loop;
      report "CHECK t=" & time'image(now) & " no_tx led=" & to_hstring(led) & " tx=" & to_string(uart_tx);
      assert not bad report "FAIL: uart_tx not idle in board mode" severity error;
    end;

    procedure wait_led_eq(val : std_logic_vector(3 downto 0); timeout : natural; ok : out boolean) is
    begin
      ok := false;
      for i in 1 to timeout loop
        wait until rising_edge(clk);
        if led = val then
          ok := true;
          exit;
        end if;
      end loop;
      report "CHECK t=" & time'image(now) & " wait_led_eq exp=" & to_hstring(val) & " got=" & to_hstring(led);
    end;

    variable ok : boolean;
    variable rb : std_logic_vector(7 downto 0);
    variable succ : boolean;
    -- programs as flat vectors (byte0 in bits 7..0)
    variable prog_fib_halt : std_logic_vector(127 downto 0);
    variable prog_mul79 : std_logic_vector(127 downto 0);
    variable prog_cd5 : std_logic_vector(127 downto 0);
    variable prog_borrow : std_logic_vector(127 downto 0);
    variable exp_fib : std_logic_vector(8*13-1 downto 0);
  begin
    -- build programs
    -- fib_halt: E0 2E 7B 4F 1E 4D 1F 4E 1D 60 00 F0 00 00 01 00
    prog_fib_halt(7 downto 0)   := x"E0";
    prog_fib_halt(15 downto 8)  := x"2E";
    prog_fib_halt(23 downto 16) := x"7B";
    prog_fib_halt(31 downto 24) := x"4F";
    prog_fib_halt(39 downto 32) := x"1E";
    prog_fib_halt(47 downto 40) := x"4D";
    prog_fib_halt(55 downto 48) := x"1F";
    prog_fib_halt(63 downto 56) := x"4E";
    prog_fib_halt(71 downto 64) := x"1D";
    prog_fib_halt(79 downto 72) := x"60";
    prog_fib_halt(87 downto 80) := x"00";
    prog_fib_halt(95 downto 88) := x"F0";
    prog_fib_halt(103 downto 96) := x"00";
    prog_fib_halt(111 downto 104) := x"00";
    prog_fib_halt(119 downto 112) := x"01";
    prog_fib_halt(127 downto 120) := x"00";

    prog_mul79(7 downto 0)   := x"1E";
    prog_mul79(15 downto 8)  := x"3C";
    prog_mul79(23 downto 16) := x"76";
    prog_mul79(31 downto 24) := x"1D";
    prog_mul79(39 downto 32) := x"E0";
    prog_mul79(47 downto 40) := x"F0";
    prog_mul79(55 downto 48) := x"4E";
    prog_mul79(63 downto 56) := x"1D";
    prog_mul79(71 downto 64) := x"2F";
    prog_mul79(79 downto 72) := x"4D";
    prog_mul79(87 downto 80) := x"60";
    prog_mul79(95 downto 88) := x"00";
    prog_mul79(103 downto 96) := x"01";
    prog_mul79(111 downto 104) := x"00";
    prog_mul79(119 downto 112) := x"07";
    prog_mul79(127 downto 120) := x"09";

    prog_cd5(7 downto 0)   := x"55";
    prog_cd5(15 downto 8)  := x"E0";
    prog_cd5(23 downto 16) := x"3F";
    prog_cd5(31 downto 24) := x"85";
    prog_cd5(39 downto 32) := x"61";
    prog_cd5(47 downto 40) := x"E0";
    prog_cd5(55 downto 48) := x"F0";
    prog_cd5(63 downto 56) := x"00";
    prog_cd5(71 downto 64) := x"00";
    prog_cd5(79 downto 72) := x"00";
    prog_cd5(87 downto 80) := x"00";
    prog_cd5(95 downto 88) := x"00";
    prog_cd5(103 downto 96) := x"00";
    prog_cd5(111 downto 104) := x"00";
    prog_cd5(119 downto 112) := x"00";
    prog_cd5(127 downto 120) := x"01";

    prog_borrow(7 downto 0)   := x"53";
    prog_borrow(15 downto 8)  := x"3F";
    prog_borrow(23 downto 16) := x"75";
    prog_borrow(31 downto 24) := x"E0";
    prog_borrow(39 downto 32) := x"F0";
    prog_borrow(47 downto 40) := x"51";
    prog_borrow(55 downto 48) := x"E0";
    prog_borrow(63 downto 56) := x"F0";
    prog_borrow(71 downto 64) := x"00";
    prog_borrow(79 downto 72) := x"00";
    prog_borrow(87 downto 80) := x"00";
    prog_borrow(95 downto 88) := x"00";
    prog_borrow(103 downto 96) := x"00";
    prog_borrow(111 downto 104) := x"00";
    prog_borrow(119 downto 112) := x"00";
    prog_borrow(127 downto 120) := x"05";

    -- ============ TEST 1: program 10 (mult 3x5, OUT=15, halt) ============
    report "TEST prog10 start t=" & time'image(now);
    sw <= "1000"; -- prog10, auto, lower
    wait_cycles(4);
    do_reset;
    -- in board mode nothing sent: check idle for 200 cycles while program runs?
    -- wait for OUT=15 (lower F)
    wait_led_eq(x"F", 20000, ok);
    assert ok report "FAIL prog10: OUT=15 (led F) not reached" severity error;
    report "CHECK t=" & time'image(now) & " prog10 OUT=15 led=" & to_hstring(led);
    -- upper halfbyte should be 0
    sw <= "1001";
    wait_cycles(6);
    report "CHECK t=" & time'image(now) & " prog10 upper led=" & to_hstring(led);
    assert led = x"0" report "FAIL prog10 upper nibble not 0" severity error;
    sw <= "1000";
    wait_cycles(6);
    assert led = x"F" report "FAIL prog10 lower not stable F" severity error;
    -- halt: stay stable
    wait_cycles(200);
    report "CHECK t=" & time'image(now) & " prog10 halt led=" & to_hstring(led);
    assert led = x"F" report "FAIL prog10: not halted (led changed)" severity error;
    -- board mode sends nothing
    check_no_tx(300);

    -- ============ TEST 2: program 11 countdown 10..0 ============
    report "TEST prog11 start t=" & time'image(now);
    sw <= "1100"; -- prog11 auto lower
    wait_cycles(4);
    do_reset;
    -- expect sequence 10..0 on lower nibble: A,9,8,7,6,5,4,3,2,1,0
    wait_led_eq(x"A", 20000, ok);
    assert ok report "FAIL prog11: 10 (A) not reached" severity error;
    report "CHECK t=" & time'image(now) & " prog11 got 10 led=" & to_hstring(led);
    -- check upper of 10 is 0
    sw <= "1101";
    wait_cycles(6);
    report "CHECK t=" & time'image(now) & " prog11 upper of 10 led=" & to_hstring(led);
    assert led = x"0" report "FAIL prog11 upper of 10 not 0" severity error;
    sw <= "1100";
    wait_cycles(6);
    -- now expect 9..0 in order (10 may already have passed, wait for 9)
    wait_led_eq(x"9", 20000, ok);
    assert ok report "FAIL prog11: 9 not reached" severity error;
    report "CHECK t=" & time'image(now) & " prog11 got 9";
    wait_led_eq(x"8", 20000, ok);
    assert ok report "FAIL prog11: 8 not reached" severity error;
    wait_led_eq(x"7", 20000, ok);
    assert ok report "FAIL prog11: 7 not reached" severity error;
    wait_led_eq(x"6", 20000, ok);
    assert ok report "FAIL prog11: 6 not reached" severity error;
    wait_led_eq(x"5", 20000, ok);
    assert ok report "FAIL prog11: 5 not reached" severity error;
    wait_led_eq(x"4", 20000, ok);
    assert ok report "FAIL prog11: 4 not reached" severity error;
    wait_led_eq(x"3", 20000, ok);
    assert ok report "FAIL prog11: 3 not reached" severity error;
    wait_led_eq(x"2", 20000, ok);
    assert ok report "FAIL prog11: 2 not reached" severity error;
    wait_led_eq(x"1", 20000, ok);
    assert ok report "FAIL prog11: 1 not reached" severity error;
    wait_led_eq(x"0", 20000, ok);
    assert ok report "FAIL prog11: 0 not reached" severity error;
    report "CHECK t=" & time'image(now) & " prog11 got 0..10 sequence";
    wait_cycles(200);
    assert led = x"0" report "FAIL prog11: not halted at 0" severity error;
    -- upper at halt is 0
    sw <= "1101";
    wait_cycles(6);
    assert led = x"0" report "FAIL prog11 upper at 0 not 0" severity error;
    sw <= "1100";
    wait_cycles(6);

    -- ============ TEST 3: single step, no press = no step; 8 presses -> 10 ============
    report "TEST singlestep start t=" & time'image(now);
    sw <= "1110"; -- prog11, single step, lower
    wait_cycles(4);
    do_reset;
    wait_cycles(30);
    report "CHECK t=" & time'image(now) & " singlestep idle led=" & to_hstring(led);
    assert led = x"0" report "FAIL singlestep: moved without press" severity error;
    -- 7 presses -> still 0
    for p in 1 to 7 loop
      btn_step <= '1';
      wait_cycles(12);
      btn_step <= '0';
      wait_cycles(12);
      wait_cycles(4);
      report "CHECK t=" & time'image(now) & " press " & integer'image(p) & " led=" & to_hstring(led);
    end loop;
    assert led = x"0" report "FAIL singlestep: after 7 presses OUT should still be 0" severity error;
    -- 8th press -> 10 (A)
    btn_step <= '1';
    wait_cycles(12);
    btn_step <= '0';
    wait_cycles(12);
    wait_cycles(4);
    report "CHECK t=" & time'image(now) & " after 8 presses led=" & to_hstring(led);
    assert led = x"A" report "FAIL singlestep: after 8 presses OUT should be 10 (A)" severity error;
    -- one more check: upper should be 0 after switching
    sw <= "1111";
    wait_cycles(6);
    assert led = x"0" report "FAIL singlestep upper not 0" severity error;
    sw <= "1110";
    wait_cycles(6);

    -- ============ TEST 4: UART hardware tests ============
    -- go back to auto board briefly then load via UART
    report "TEST uart fib_halt start t=" & time'image(now);
    -- ensure auto mode low for loader? loader works in any mode; keep sw auto lower prog00
    sw <= "0000";
    wait_cycles(4);
    do_reset;
    -- board mode: no tx
    check_no_tx(100);
    -- send fibonacci_halt (16 bytes), expect 13 bytes
    uart_send_frame(prog_fib_halt, 16);
    -- receive 13 bytes: 00 01 01 02 03 05 08 0d 15 22 37 59 90
    for i in 0 to 12 loop
      uart_recv_byte(rb, succ, 30000);
      report "CHECK t=" & time'image(now) & " fib byte " & integer'image(i) & " got=" & to_hstring(rb);
      assert succ report "FAIL fib_halt: timeout waiting byte" severity error;
      case i is
        when 0 => assert rb = x"00" report "FAIL fib byte0" severity error;
        when 1 => assert rb = x"01" report "FAIL fib byte1" severity error;
        when 2 => assert rb = x"01" report "FAIL fib byte2" severity error;
        when 3 => assert rb = x"02" report "FAIL fib byte3" severity error;
        when 4 => assert rb = x"03" report "FAIL fib byte4" severity error;
        when 5 => assert rb = x"05" report "FAIL fib byte5" severity error;
        when 6 => assert rb = x"08" report "FAIL fib byte6" severity error;
        when 7 => assert rb = x"0D" report "FAIL fib byte7" severity error;
        when 8 => assert rb = x"15" report "FAIL fib byte8" severity error;
        when 9 => assert rb = x"22" report "FAIL fib byte9" severity error;
        when 10 => assert rb = x"37" report "FAIL fib byte10" severity error;
        when 11 => assert rb = x"59" report "FAIL fib byte11" severity error;
        when 12 => assert rb = x"90" report "FAIL fib byte12" severity error;
        when others => null;
      end case;
    end loop;

    report "TEST uart mul79 start t=" & time'image(now);
    uart_send_frame(prog_mul79, 16);
    uart_recv_byte(rb, succ, 30000);
    report "CHECK t=" & time'image(now) & " mul79 got=" & to_hstring(rb);
    assert succ report "FAIL mul79 timeout" severity error;
    assert rb = x"3F" report "FAIL mul79 expected 3F" severity error;

    report "TEST uart countdown5 start t=" & time'image(now);
    uart_send_frame(prog_cd5, 16);
    for i in 0 to 5 loop
      uart_recv_byte(rb, succ, 30000);
      report "CHECK t=" & time'image(now) & " cd5 byte " & integer'image(i) & " got=" & to_hstring(rb);
      assert succ report "FAIL cd5 timeout" severity error;
      case i is
        when 0 => assert rb = x"05" report "FAIL cd5 byte0" severity error;
        when 1 => assert rb = x"04" report "FAIL cd5 byte1" severity error;
        when 2 => assert rb = x"03" report "FAIL cd5 byte2" severity error;
        when 3 => assert rb = x"02" report "FAIL cd5 byte3" severity error;
        when 4 => assert rb = x"01" report "FAIL cd5 byte4" severity error;
        when 5 => assert rb = x"00" report "FAIL cd5 byte5" severity error;
        when others => null;
      end case;
    end loop;

    report "TEST uart borrow start t=" & time'image(now);
    uart_send_frame(prog_borrow, 16);
    uart_recv_byte(rb, succ, 30000);
    report "CHECK t=" & time'image(now) & " borrow got=" & to_hstring(rb);
    assert succ report "FAIL borrow timeout" severity error;
    assert rb = x"FE" report "FAIL borrow expected FE" severity error;

    -- ============ TEST 5: invalid length 17 discarded, valid still runs ============
    report "TEST invalid len17 start t=" & time'image(now);
    uart_send_byte(x"11");
    uart_send_byte(x"00");
    uart_send_byte(x"00");
    uart_send_byte(x"00");
    wait_cycles(300);
    -- no output expected from invalid frame; check no byte available with short timeout
    uart_recv_byte(rb, succ, 2000);
    report "CHECK t=" & time'image(now) & " invalid frame no output succ=" & to_string(succ);
    assert not succ report "FAIL invalid frame should produce no output" severity error;
    -- now valid frame (multiply again) must still run
    uart_send_frame(prog_mul79, 16);
    uart_recv_byte(rb, succ, 30000);
    report "CHECK t=" & time'image(now) & " after invalid mul79 got=" & to_hstring(rb);
    assert succ report "FAIL after-invalid valid frame timeout" severity error;
    assert rb = x"3F" report "FAIL after-invalid valid frame expected 3F" severity error;

    -- ============ TEST 6: reset returns to board mode, board sends nothing ============
    report "TEST reset-to-board start t=" & time'image(now);
    sw <= "0000";
    wait_cycles(4);
    do_reset;
    check_no_tx(500);
    -- fibonacci prog00 should run: wait for led 1 (second value) to prove board mode running
    wait_led_eq(x"1", 20000, ok);
    assert ok report "FAIL reset-to-board: fibonacci not running (led 01 missing)" severity error;
    report "CHECK t=" & time'image(now) & " board fib running led=" & to_hstring(led);
    check_no_tx(200);

    report "TB_COMPLETE" severity note;
    stop_clk <= true;
    wait;
  end process;
end architecture tb;
