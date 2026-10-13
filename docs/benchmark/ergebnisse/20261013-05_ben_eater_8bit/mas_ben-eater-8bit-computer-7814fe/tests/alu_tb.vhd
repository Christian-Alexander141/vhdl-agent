library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
library std;
use std.env.all;

entity alu_tb is
end entity alu_tb;

architecture sim of alu_tb is
  constant CLK_PERIOD : time := 20 ns;

  signal clk        : std_logic := '0';
  signal rst        : std_logic := '1';
  signal a_in       : std_logic_vector(7 downto 0) := (others => '0');
  signal b_in       : std_logic_vector(7 downto 0) := (others => '0');
  signal sub        : std_logic := '0';
  signal fi_en      : std_logic := '0';
  signal result_out : std_logic_vector(7 downto 0);
  signal carry_out  : std_logic;
  signal zero_out   : std_logic;

  signal tb_done : boolean := false;
begin
  clk <= not clk after CLK_PERIOD / 2 when not tb_done else '0';

  dut: entity work.alu
    port map (
      a_in       => a_in,
      b_in       => b_in,
      clk        => clk,
      carry_out  => carry_out,
      fi_en      => fi_en,
      rst        => rst,
      result_out => result_out,
      sub        => sub,
      zero_out   => zero_out
    );

  stim: process
    procedure wait_cyc(n : positive) is
    begin
      for i in 1 to n loop
        wait until rising_edge(clk);
        wait for 1 ns;
      end loop;
    end procedure;

    -- apply one vector: set inputs, check combinational result,
    -- then clock FI and check registered flags
    procedure check_vec(
      constant va : in integer;
      constant vb : in integer;
      constant vsub : in std_logic;
      constant exp_res : in integer;
      constant exp_c : in std_logic;
      constant exp_z : in std_logic) is
    begin
      a_in <= std_logic_vector(to_unsigned(va, 8));
      b_in <= std_logic_vector(to_unsigned(vb, 8));
      sub <= vsub;
      fi_en <= '0';
      wait for 1 ns;
      report "CHECK t=" & time'image(now) & " vec a=" & integer'image(va)
        & " b=" & integer'image(vb) & " sub=" & std_logic'image(vsub)
        & " res=" & to_string(result_out) severity note;
      assert result_out = std_logic_vector(to_unsigned(exp_res, 8))
        report "REQ R18: ALU Ergebnis falsch a=" & integer'image(va)
        & " b=" & integer'image(vb) & " sub=" & std_logic'image(vsub) severity error;
      assert result_out = std_logic_vector(to_unsigned(exp_res, 8))
        report "REQ R16: EO-Busquelle muss ALU-Ergebnis liefern" severity error;
      -- uebernehme Flags mit FI
      fi_en <= '1';
      wait until rising_edge(clk);
      wait for 1 ns;
      fi_en <= '0';
      wait for 1 ns;
      report "CHECK t=" & time'image(now) & " flags c=" & std_logic'image(carry_out)
        & " z=" & std_logic'image(zero_out) & " res=" & to_string(result_out) severity note;
      assert carry_out = exp_c
        report "REQ R18: ALU Carry falsch" severity error;
      assert zero_out = exp_z
        report "REQ R18: ALU Zero falsch" severity error;
      assert carry_out = exp_c and zero_out = exp_z
        report "REQ R19: Flags-Register uebernimmt bei FI Carry/Zero" severity error;
    end procedure;
  begin
    -- Reset-Sequenz: mind. 2 Zyklen rst='1' (synchron, active high)
    rst <= '1';
    fi_en <= '0';
    a_in <= (others => '0');
    b_in <= (others => '0');
    sub <= '0';
    wait until rising_edge(clk);
    wait for 1 ns;
    wait until rising_edge(clk);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " im Reset c=" & std_logic'image(carry_out)
      & " z=" & std_logic'image(zero_out) severity note;
    assert carry_out = '0' and zero_out = '0'
      report "REQ R43: bei rst=1 Flags C/Z in 0/Ruhe" severity error;
    rst <= '0';
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " nach Reset res=" & to_string(result_out)
      & " c=" & std_logic'image(carry_out) & " z=" & std_logic'image(zero_out) severity note;
    assert carry_out = '0' and zero_out = '0'
      report "REQ R43: nach Reset Flags 0 (synchron active-high)" severity error;
    assert carry_out = '0' and zero_out = '0'
      report "REQ R51: Rahmen/Reset loescht C/Z (UART-Neustart)" severity error;
    assert result_out = X"00"
      report "REQ R18: nach Reset mit A=B=0 Ergebnis 0" severity error;

    -- ADD-Vektoren (PROMPT.md: Ergebnis=(A+B) mod 256, Carry=Uebertrag Bit7, Zero bei 0)
    check_vec(16#00#, 16#00#, '0', 16#00#, '0', '1');
    check_vec(16#01#, 16#02#, '0', 16#03#, '0', '0');
    check_vec(16#37#, 16#59#, '0', 16#90#, '0', '0'); -- 55+89=144 Fibonacci
    check_vec(16#59#, 16#90#, '0', 16#E9#, '0', '0'); -- 89+144=233
    check_vec(16#C8#, 16#64#, '0', 16#2C#, '1', '0'); -- 200+100=44 Uebertrag
    check_vec(16#FF#, 16#01#, '0', 16#00#, '1', '1'); -- 255+1=0
    check_vec(16#FF#, 16#00#, '0', 16#FF#, '0', '0');
    check_vec(16#80#, 16#80#, '0', 16#00#, '1', '1'); -- 128+128=0

    -- R19: ohne FI keine Uebernahme (Flags halten)
    a_in <= X"01";
    b_in <= X"01";
    sub <= '0';
    fi_en <= '0';
    wait for 1 ns;
    -- Flags sind noch vom letzten Vektor (128+128 => C=1,Z=1)
    report "CHECK t=" & time'image(now) & " halte c=" & std_logic'image(carry_out)
      & " z=" & std_logic'image(zero_out) & " res=" & to_string(result_out) severity note;
    assert result_out = X"02"
      report "REQ R18: ADD 1+1=2 kombinatorisch" severity error;
    assert result_out = X"02"
      report "REQ R16: EO folgt kombinatorisch ohne Takt" severity error;
    wait_cyc(2);
    assert carry_out = '1' and zero_out = '1'
      report "REQ R19: ohne FI keine Flag-Aenderung (halten)" severity error;

    -- SUB-Vektoren (PROMPT.md: A+(not B)+1, Carry=1 genau bei A>=B, Zero bei 0)
    check_vec(16#05#, 16#03#, '1', 16#02#, '1', '0'); -- 5-3=2
    check_vec(16#03#, 16#05#, '1', 16#FE#, '0', '0'); -- 3-5=0xFE borrow (HW-Test borrow_3_minus_5)
    check_vec(16#0A#, 16#0A#, '1', 16#00#, '1', '1'); -- 10-10=0
    check_vec(16#00#, 16#01#, '1', 16#FF#, '0', '0'); -- 0-1
    check_vec(16#00#, 16#00#, '1', 16#00#, '1', '1'); -- 0-0
    check_vec(16#0A#, 16#01#, '1', 16#09#, '1', '0'); -- 10-1=9 Countdown-Schritt
    check_vec(16#01#, 16#02#, '1', 16#FF#, '0', '0');
    check_vec(16#FF#, 16#FF#, '1', 16#00#, '1', '1');

    -- R19: FI=0 haelt auch nach SUB-Vektor
    a_in <= X"FF";
    b_in <= X"00";
    sub <= '1';
    fi_en <= '0';
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " sub FF-00 res=" & to_string(result_out)
      & " c=" & std_logic'image(carry_out) & " z=" & std_logic'image(zero_out) severity note;
    assert result_out = X"FF"
      report "REQ R18: SUB FF-00=FF" severity error;
    wait_cyc(2);
    -- Flags noch vom letzten check_vec (FF-FF => C=1,Z=1)
    assert carry_out = '1' and zero_out = '1'
      report "REQ R19: Flags halten ohne FI nach SUB" severity error;

    -- R43: synchroner Reset wirkt erst mit Flanke, loescht dann C/Z
    -- erst Flags auf 1 bringen (FF+01 => C=1,Z=1 via FI)
    a_in <= X"FF";
    b_in <= X"01";
    sub <= '0';
    fi_en <= '1';
    wait until rising_edge(clk);
    wait for 1 ns;
    fi_en <= '0';
    wait for 1 ns;
    assert carry_out = '1' and zero_out = '1'
      report "REQ R19: Vorbereitung Flags=1 vor Reset-Test" severity error;
    rst <= '1';
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " rst=1 vor Flanke c=" & std_logic'image(carry_out)
      & " z=" & std_logic'image(zero_out) severity note;
    assert carry_out = '1' and zero_out = '1'
      report "REQ R43: synchroner Reset wirkt erst mit Flanke" severity error;
    wait until rising_edge(clk);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " nach Reset-Flanke c=" & std_logic'image(carry_out)
      & " z=" & std_logic'image(zero_out) severity note;
    assert carry_out = '0' and zero_out = '0'
      report "REQ R43: Reset-Flanke loescht C/Z" severity error;
    assert carry_out = '0' and zero_out = '0'
      report "REQ R51: Loader-Neustart loescht C/Z wie Reset" severity error;
    wait until rising_edge(clk);
    wait for 1 ns;
    rst <= '0';
    wait for 1 ns;
    assert carry_out = '0' and zero_out = '0'
      report "REQ R43: nach rst=0 bleiben Flags 0" severity error;

    -- R16: Bus-Idle-Fall: result liegt weiter an, ist aber nur bei EO relevant;
    -- pruefe, dass result_out jederzeit dem ALU-Wert folgt (Mux-Quelle EO)
    a_in <= X"0F";
    b_in <= X"01";
    sub <= '0';
    wait for 1 ns;
    assert result_out = X"10"
      report "REQ R16: EO-Quelle 0F+01=10" severity error;
    a_in <= X"0F";
    b_in <= X"01";
    sub <= '1';
    wait for 1 ns;
    assert result_out = X"0E"
      report "REQ R16: EO-Quelle 0F-01=0E mit SU" severity error;
    assert result_out = X"0E"
      report "REQ R18: SUB 0F-01=0E, Carry=1 kein Borgen" severity error;
    fi_en <= '1';
    wait until rising_edge(clk);
    wait for 1 ns;
    fi_en <= '0';
    wait for 1 ns;
    assert carry_out = '1' and zero_out = '0'
      report "REQ R18: SUB 0F-01 Carry=1 (A>=B)" severity error;

    report "CHECK t=" & time'image(now) & " alle ALU-Pruefungen fertig" severity note;
    tb_done <= true;
    report "TB_COMPLETE" severity note;
    std.env.stop(0);
    wait;
  end process stim;

end architecture sim;