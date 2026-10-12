library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity sync2_tb is
end entity sync2_tb;

architecture sim of sync2_tb is
  constant WIDTH      : positive := 4;
  constant CLK_PERIOD : time := 10 ns;

  signal clk     : std_logic := '0';
  signal rst     : std_logic := '1';
  signal d       : std_logic_vector(WIDTH-1 downto 0) := (others => '0');
  signal q       : std_logic_vector(WIDTH-1 downto 0);
  signal tb_done : boolean := false;

begin

  clk <= not clk after CLK_PERIOD / 2 when not tb_done else '0';

  dut: entity work.sync2
    generic map (
      WIDTH => WIDTH
    )
    port map (
      clk => clk,
      rst => rst,
      d   => d,
      q   => q
    );

  stim: process
    procedure wait_cycles(n : positive) is
    begin
      for i in 1 to n loop
        wait until rising_edge(clk);
      end loop;
    end procedure;
  begin
    -- Reset-Sequenz: 2 Zyklen rst='1', dann rst='0' (PROMPT: synchron, active high)
    d <= (others => '0');
    rst <= '1';
    wait_cycles(2);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " nach Reset d=" & to_string(d) & " q=" & to_string(q) severity note;
    assert q = "0000" report "REQ R71: nach Reset muss q=0 sein (alle Register 0)" severity error;

    -- Reset dominiert Eingang: d ungleich 0 waehrend Reset -> q bleibt 0
    d <= "1111";
    wait until rising_edge(clk);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " Reset dominant d=" & to_string(d) & " q=" & to_string(q) severity note;
    assert q = "0000" report "REQ R71: waehrend Reset muss q=0 bleiben trotz d=1111" severity error;

    -- Reset loesen, Pipeline mit Nullen spuelen
    rst <= '0';
    d <= "0000";
    wait until rising_edge(clk);
    wait for 1 ns;
    wait until rising_edge(clk);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " nach Reset-Release d=" & to_string(d) & " q=" & to_string(q) severity note;
    assert q = "0000" report "REQ R71: nach Reset-Release mit d=0 muss q=0 bleiben" severity error;

    -- R64: zweistufige Latenz, Vektorwechsel 0000 -> 1111
    wait until rising_edge(clk); -- Referenzflanke Eref
    d <= "1111";
    report "CHECK t=" & time'image(now) & " set d=1111" severity note;
    wait until rising_edge(clk); -- E1: eine Flanke spaeter
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " nach 1 Flanke d=" & to_string(d) & " q=" & to_string(q) severity note;
    assert q = "0000" report "REQ R64: nach 1 Flanke muss q noch alt (0000) sein, nicht 1-stufig" severity error;
    wait until rising_edge(clk); -- E2: zwei Flanken spaeter
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " nach 2 Flanken d=" & to_string(d) & " q=" & to_string(q) severity note;
    assert q = "1111" report "REQ R64: nach 2 Flanken muss q neu (1111) sein (2 Flipflops)" severity error;

    -- R64: naechster Vektorwechsel 1111 -> 1010, alle Bits unabhaengig
    wait until rising_edge(clk);
    d <= "1010";
    report "CHECK t=" & time'image(now) & " set d=1010" severity note;
    wait until rising_edge(clk);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " nach 1 Flanke d=" & to_string(d) & " q=" & to_string(q) severity note;
    assert q = "1111" report "REQ R64: nach 1 Flanke muss q noch 1111 sein" severity error;
    wait until rising_edge(clk);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " nach 2 Flanken d=" & to_string(d) & " q=" & to_string(q) severity note;
    assert q = "1010" report "REQ R64: nach 2 Flanken muss q=1010 sein (jedes Bit synchronisiert)" severity error;

    -- R65: Einzelbit-Wechsel (btn_step-Pfad, 1 Bit) 1010 -> 1011 (nur Bit 0)
    wait until rising_edge(clk);
    d <= "1011";
    report "CHECK t=" & time'image(now) & " set d=1011 (nur Bit0 kippt)" severity note;
    wait until rising_edge(clk);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " nach 1 Flanke d=" & to_string(d) & " q=" & to_string(q) severity note;
    assert q = "1010" report "REQ R65: Einzelbit muss ebenfalls 2 Flanken brauchen (nach 1 noch alt)" severity error;
    wait until rising_edge(clk);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " nach 2 Flanken d=" & to_string(d) & " q=" & to_string(q) severity note;
    assert q = "1011" report "REQ R65: Einzelbit nach 2 Flanken uebernommen (btn_step 2FF)" severity error;

    -- R64: Wechsel 1011 -> 0100 (mehrere Bits kippen)
    wait until rising_edge(clk);
    d <= "0100";
    wait until rising_edge(clk);
    wait for 1 ns;
    assert q = "1011" report "REQ R64: Mehrbitwechsel nach 1 Flanke noch alt" severity error;
    wait until rising_edge(clk);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " Mehrbit d=" & to_string(d) & " q=" & to_string(q) severity note;
    assert q = "0100" report "REQ R64: Mehrbitwechsel nach 2 Flanken neu (0100)" severity error;

    -- stabiler Eingang bleibt stabil am Ausgang
    wait until rising_edge(clk);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " stabil d=" & to_string(d) & " q=" & to_string(q) severity note;
    assert q = "0100" report "REQ R64: stabiler Eingang muss stabil am Ausgang bleiben" severity error;
    wait until rising_edge(clk);
    wait for 1 ns;
    assert q = "0100" report "REQ R64: stabiler Eingang muss weiter stabil bleiben" severity error;

    -- R71: synchroner Reset mitten im Betrieb (q ungleich 0)
    -- q ist 0100, d ist 0100; Reset zwischen zwei Flanken setzen
    rst <= '1';
    wait for 2 ns; -- mitten im Takt, vor naechster Flanke
    report "CHECK t=" & time'image(now) & " Reset gesetzt (async-Abstand) d=" & to_string(d) & " q=" & to_string(q) severity note;
    assert q = "0100" report "REQ R71: synchroner Reset darf nicht asynchron wirken (q bleibt bis Flanke)" severity error;
    wait until rising_edge(clk);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " nach Reset-Flanke d=" & to_string(d) & " q=" & to_string(q) severity note;
    assert q = "0000" report "REQ R71: nach Reset-Flanke muss q=0 sein (alle Register 0)" severity error;
    wait until rising_edge(clk);
    wait for 1 ns;
    assert q = "0000" report "REQ R71: bei gehaltenem Reset bleibt q=0" severity error;

    -- Reset loesen, Resynchronisation braucht wieder 2 Flanken
    rst <= '0';
    -- d steht noch auf 0100, q muss nach 2 Flanken wieder 0100 werden
    wait until rising_edge(clk);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " nach Release+1 d=" & to_string(d) & " q=" & to_string(q) severity note;
    assert q = "0000" report "REQ R64: nach Reset-Release nach 1 Flanke noch 0 (2-stufig)" severity error;
    wait until rising_edge(clk);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " nach Release+2 d=" & to_string(d) & " q=" & to_string(q) severity note;
    assert q = "0100" report "REQ R64: nach Reset-Release nach 2 Flanken wieder d (0100)" severity error;

    -- Programm-von-vorn-Pendant: auf 0 zurueck und erneut Latenz pruefen
    wait until rising_edge(clk);
    d <= "0000";
    wait until rising_edge(clk);
    wait for 1 ns;
    assert q = "0100" report "REQ R64: Rueckwechsel nach 1 Flanke noch alt" severity error;
    wait until rising_edge(clk);
    wait for 1 ns;
    assert q = "0000" report "REQ R64: Rueckwechsel nach 2 Flanken neu (0000)" severity error;

    tb_done <= true;
    report "TB_COMPLETE" severity note;
    wait;
  end process stim;

end architecture sim;