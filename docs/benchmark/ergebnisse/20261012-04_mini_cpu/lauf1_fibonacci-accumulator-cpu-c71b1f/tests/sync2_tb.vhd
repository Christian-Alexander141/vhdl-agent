library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
library std;
use std.env.all;

entity sync2_tb is
end entity sync2_tb;

architecture sim of sync2_tb is
  constant CLK_PERIOD : time := 10 ns;

  signal clk     : std_logic := '0';
  signal rst     : std_logic := '1';
  signal tb_done : boolean := false;

  -- 3-Bit-Instanz (stellt sw(2 downto 0) dar, R59)
  signal d3 : std_logic_vector(2 downto 0) := (others => '0');
  signal q3 : std_logic_vector(2 downto 0);

  -- 1-Bit-Instanz (stellt btn_step dar, R60)
  signal d1 : std_logic_vector(0 downto 0) := (others => '0');
  signal q1 : std_logic_vector(0 downto 0);
begin
  clk <= not clk after CLK_PERIOD / 2 when not tb_done else '0';

  dut3: entity work.sync2
    generic map (
      WIDTH => 3
    )
    port map (
      clk => clk,
      rst => rst,
      d   => d3,
      q   => q3
    );

  dut1: entity work.sync2
    generic map (
      WIDTH => 1
    )
    port map (
      clk => clk,
      rst => rst,
      d   => d1,
      q   => q1
    );

  stim: process
    procedure wait_cycles(n : in positive) is
    begin
      for i in 1 to n loop
        wait until rising_edge(clk);
        wait for 1 ns;
      end loop;
    end procedure;
  begin
    -- Reset: 2 Zyklen aktiv (synchron, active high, PROMPT-md).
    rst <= '1';
    d3  <= (others => '0');
    d1  <= (others => '0');
    wait_cycles(2);
    report "CHECK t=" & time'image(now) & " reset-hold q3=" & integer'image(to_integer(unsigned(q3))) & " q1=" & integer'image(to_integer(unsigned(q1)));
    assert q3 = "000" report "REQ R71: nach Reset muessen Synchronisierer 0 sein (q3=0)" severity error;
    assert q1 = "0" report "REQ R71: nach Reset muss Synchronisierer 0 sein (q1=0)" severity error;

    -- Reset loesen, Eingang stabil 0.
    rst <= '0';
    wait_cycles(2);
    report "CHECK t=" & time'image(now) & " idle q3=" & integer'image(to_integer(unsigned(q3))) & " q1=" & integer'image(to_integer(unsigned(q1)));
    assert q3 = "000" report "REQ R71: nach Reset-loesen bleibt q 0 bei d=0" severity error;
    assert q1 = "0" report "REQ R71: nach Reset-loesen bleibt q1 0 bei d=0" severity error;

    -- Neuen Wert anlegen: 2-stufige Latenz pruefen (R59 sw, R60 btn).
    d3 <= "101";
    d1 <= "1";
    -- Kein kombinatorischer Durchgriff: kurz nach Aenderung (ohne Flanke) noch alt.
    wait for 2 ns;
    report "CHECK t=" & time'image(now) & " comb q3=" & integer'image(to_integer(unsigned(q3))) & " q1=" & integer'image(to_integer(unsigned(q1)));
    assert q3 = "000" report "REQ R59: sw-Synchronisierer ist registriert, kein Kombinatorik-Durchgriff" severity error;
    assert q1 = "0" report "REQ R60: btn-Synchronisierer ist registriert, kein Kombinatorik-Durchgriff" severity error;

    -- Nach genau 1 Flanke noch alter Wert (beweist 2 Flipflops, nicht 1).
    wait_cycles(1);
    report "CHECK t=" & time'image(now) & " 1stage q3=" & integer'image(to_integer(unsigned(q3))) & " q1=" & integer'image(to_integer(unsigned(q1)));
    assert q3 = "000" report "REQ R59: nach 1 Flanke noch alter Wert (zwei Flipflops, Latenz 2)" severity error;
    assert q1 = "0" report "REQ R60: nach 1 Flanke noch alter Wert (zwei Flipflops, Latenz 2)" severity error;

    -- Nach 2. Flanke neuer Wert (alle Regeln verwenden synchronisierte Werte).
    wait_cycles(1);
    report "CHECK t=" & time'image(now) & " 2stage q3=" & integer'image(to_integer(unsigned(q3))) & " q1=" & integer'image(to_integer(unsigned(q1)));
    assert q3 = "101" report "REQ R59: nach 2 Flanken synchronisierter sw-Wert q=101" severity error;
    assert q1 = "1" report "REQ R60: nach 2 Flanken synchronisierter btn-Wert q=1" severity error;

    -- Stabiler Eingang: Wert bleibt.
    wait_cycles(2);
    report "CHECK t=" & time'image(now) & " stable q3=" & integer'image(to_integer(unsigned(q3))) & " q1=" & integer'image(to_integer(unsigned(q1)));
    assert q3 = "101" report "REQ R59: stabiler sw-Eingang bleibt synchronisiert erhalten" severity error;
    assert q1 = "1" report "REQ R60: stabiler btn-Eingang bleibt synchronisiert erhalten" severity error;

    -- Zweiter Vektorwechsel (bitweise Unabhaengigkeit, WIDTH=3).
    d3 <= "011";
    d1 <= "0";
    wait_cycles(1);
    report "CHECK t=" & time'image(now) & " chg1 q3=" & integer'image(to_integer(unsigned(q3))) & " q1=" & integer'image(to_integer(unsigned(q1)));
    assert q3 = "101" report "REQ R59: bei Wechsel nach 1 Flanke noch alter Vektor" severity error;
    assert q1 = "1" report "REQ R60: bei Wechsel nach 1 Flanke noch alter Wert" severity error;
    wait_cycles(1);
    report "CHECK t=" & time'image(now) & " chg2 q3=" & integer'image(to_integer(unsigned(q3))) & " q1=" & integer'image(to_integer(unsigned(q1)));
    assert q3 = "011" report "REQ R59: nach 2 Flanken neuer sw-Vektor q=011" severity error;
    assert q1 = "0" report "REQ R60: nach 2 Flanken neuer btn-Wert q=0" severity error;

    -- Alle Bits kippen: 000 -> 111 (WIDTH generisch, jedes Bit synchronisiert).
    d3 <= "111";
    d1 <= "1";
    wait_cycles(1);
    assert q3 = "011" report "REQ R59: Vollwechsel nach 1 Flanke noch alt" severity error;
    assert q1 = "0" report "REQ R60: Vollwechsel nach 1 Flanke noch alt" severity error;
    wait_cycles(1);
    report "CHECK t=" & time'image(now) & " full q3=" & integer'image(to_integer(unsigned(q3))) & " q1=" & integer'image(to_integer(unsigned(q1)));
    assert q3 = "111" report "REQ R59: nach 2 Flanken alle Bits synchronisiert (111)" severity error;
    assert q1 = "1" report "REQ R60: nach 2 Flanken Einzelbit synchronisiert (1)" severity error;

    -- Synchroner Reset mitten im Betrieb: vor der naechsten Flanke noch alt
    -- (beweist synchron, nicht asynchron), nach der Flanke 0.
    rst <= '1';
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " rst-async-check q3=" & integer'image(to_integer(unsigned(q3)));
    assert q3 = "111" report "REQ R71: Reset ist synchron, vor Flanke bleibt q erhalten" severity error;
    assert q1 = "1" report "REQ R71: Reset ist synchron, vor Flanke bleibt q1 erhalten" severity error;
    wait_cycles(1);
    report "CHECK t=" & time'image(now) & " rst-edge q3=" & integer'image(to_integer(unsigned(q3))) & " q1=" & integer'image(to_integer(unsigned(q1)));
    assert q3 = "000" report "REQ R71: synchroner Reset mitten im Betrieb loescht Synchronisierer (q3=0)" severity error;
    assert q1 = "0" report "REQ R71: synchroner Reset mitten im Betrieb loescht Synchronisierer (q1=0)" severity error;
    -- Zweite Reset-Flanke: bleibt 0 obwohl d /= 0.
    wait_cycles(1);
    assert q3 = "000" report "REQ R71: waehrend Reset bleibt q 0 trotz d/=0" severity error;
    assert q1 = "0" report "REQ R71: waehrend Reset bleibt q1 0 trotz d/=0" severity error;

    -- Reset loesen bei anliegendem d: beide Stufen waren 0, braucht wieder 2 Flanken.
    rst <= '0';
    wait_cycles(1);
    report "CHECK t=" & time'image(now) & " post-rst1 q3=" & integer'image(to_integer(unsigned(q3))) & " q1=" & integer'image(to_integer(unsigned(q1)));
    assert q3 = "000" report "REQ R71: nach Reset braucht es wieder volle 2 Flanken (nach 1 noch 0)" severity error;
    assert q1 = "0" report "REQ R71: nach Reset braucht q1 wieder volle 2 Flanken (nach 1 noch 0)" severity error;
    wait_cycles(1);
    report "CHECK t=" & time'image(now) & " post-rst2 q3=" & integer'image(to_integer(unsigned(q3))) & " q1=" & integer'image(to_integer(unsigned(q1)));
    assert q3 = "111" report "REQ R59: nach Reset synchronisiert sw wieder nach 2 Flanken" severity error;
    assert q1 = "1" report "REQ R60: nach Reset synchronisiert btn wieder nach 2 Flanken" severity error;
    assert q3 = "111" report "REQ R71: nach Reset beginnt Pipeline von vorn (beide Stufen waren 0)" severity error;

    tb_done <= true;
    report "TB_COMPLETE" severity note;
    std.env.stop;
    wait;
  end process stim;

end architecture sim;