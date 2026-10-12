library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.env.all;

entity sync2_tb is
end entity sync2_tb;

architecture sim of sync2_tb is
  constant WIDTH      : positive := 3;
  constant CLK_PERIOD : time := 10 ns;

  signal clk     : std_logic := '0';
  signal rst     : std_logic := '1';
  signal din     : std_logic_vector(WIDTH-1 downto 0) := (others => '0');
  signal dout    : std_logic_vector(WIDTH-1 downto 0);
  signal tb_done : boolean := false;

begin
  clk <= not clk after CLK_PERIOD / 2 when not tb_done else '0';

  dut: entity work.sync2
    generic map (WIDTH => WIDTH)
    port map (
      clk  => clk,
      rst  => rst,
      din  => din,
      dout => dout
    );

  stim: process
    procedure wait_cycles(n : positive) is
    begin
      for i in 1 to n loop
        wait until rising_edge(clk);
      end loop;
      wait for 1 ns; -- DUT-Ausgaenge setzen lassen (Delta-Race vermeiden)
    end procedure;
  begin
    -- Reset sequence: min. 2 Zyklen rst='1'
    rst <= '1';
    din <= (others => '0');
    wait_cycles(2);
    assert dout = "000"
      report "REQ R57: dout nach Reset 0, ist " & integer'image(to_integer(unsigned(dout)))
      severity error;
    report "CHECK t=" & time'image(now) & " nach Reset dout=" & integer'image(to_integer(unsigned(dout)));

    rst <= '0';
    wait_cycles(2);
    assert dout = "000"
      report "REQ R57: dout nach Reset-Release weiter 0"
      severity error;
    report "CHECK t=" & time'image(now) & " nach Release dout=" & integer'image(to_integer(unsigned(dout)));

    -- R52: sw-Pfad, 2 Flipflops -> Latenz exakt 2 Flanken
    din <= "101";
    wait_cycles(1);
    assert dout = "000"
      report "REQ R52: nach 1 Flanke noch alter Wert, dout=" & integer'image(to_integer(unsigned(dout)))
      severity error;
    report "CHECK t=" & time'image(now) & " 1 Flanke dout=" & integer'image(to_integer(unsigned(dout)));
    wait_cycles(1);
    assert dout = "101"
      report "REQ R52: nach 2 Flanken neuer Wert 5, dout=" & integer'image(to_integer(unsigned(dout)))
      severity error;
    report "CHECK t=" & time'image(now) & " 2 Flanken dout=" & integer'image(to_integer(unsigned(dout)));

    -- Vektorwechsel
    din <= "010";
    wait_cycles(1);
    assert dout = "101"
      report "REQ R52: Wechsel nach 1 Flanke noch alt"
      severity error;
    wait_cycles(1);
    assert dout = "010"
      report "REQ R52: Wechsel nach 2 Flanken neu (2)"
      severity error;
    report "CHECK t=" & time'image(now) & " Wechsel dout=" & integer'image(to_integer(unsigned(dout)));

    -- R53: btn_step-Pfad (1-Bit-Verhalten, hier Bit0), pro Bit unabhaengig
    din <= "011";
    wait_cycles(1);
    assert dout = "010"
      report "REQ R53: btn-Pfad nach 1 Flanke noch alt"
      severity error;
    wait_cycles(1);
    assert dout = "011"
      report "REQ R53: btn-Pfad nach 2 Flanken neu (nur Bit0 gekippt)"
      severity error;
    report "CHECK t=" & time'image(now) & " Einzelbit dout=" & integer'image(to_integer(unsigned(dout)));

    -- Reset mitten im Betrieb (R57): nur 1 Flanke nach din-Wechsel warten,
    -- dann Reset -> beide Stufen muessen 0 werden
    din <= "111";
    wait_cycles(1);
    assert dout = "011"
      report "REQ R57: vor Mid-Reset noch alter Wert"
      severity error;
    rst <= '1';
    wait_cycles(2);
    assert dout = "000"
      report "REQ R57: Mid-Reset loescht Synchronisierer"
      severity error;
    report "CHECK t=" & time'image(now) & " mid-reset dout=" & integer'image(to_integer(unsigned(dout)));
    rst <= '0';
    din <= (others => '0');
    wait_cycles(2);
    assert dout = "000"
      report "REQ R57: nach Mid-Reset wieder 0"
      severity error;

    tb_done <= true;
    report "TB_COMPLETE" severity note;
    stop;
    wait;
  end process stim;

end architecture sim;