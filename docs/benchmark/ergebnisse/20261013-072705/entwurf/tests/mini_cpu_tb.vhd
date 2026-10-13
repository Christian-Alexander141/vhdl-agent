library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
library std;
use std.env.all;

entity mini_cpu_tb is
end entity mini_cpu_tb;

architecture sim of mini_cpu_tb is
  signal clk : std_logic := '0';
  signal rst : std_logic := '1';
  signal btn_step : std_logic := '0';
  signal sw  : std_logic_vector(2 downto 0) := "000";
  signal led : std_logic_vector(3 downto 0);

  constant CLK_PERIOD : time := 10 ns;

  procedure wait_cycles(n : natural; signal c : in std_logic) is
  begin
    for i in 1 to n loop
      wait until rising_edge(c);
    end loop;
  end procedure;
begin
  dut : entity work.mini_cpu
    generic map (
      TICK_CYCLES => 4,
      DEBOUNCE_CYCLES => 2
    )
    port map (
      clk => clk,
      rst => rst,
      btn_step => btn_step,
      sw => sw,
      led => led
    );

  clk_gen : process
  begin
    while now < 900 us loop
      clk <= '0';
      wait for CLK_PERIOD/2;
      clk <= '1';
      wait for CLK_PERIOD/2;
    end loop;
    wait;
  end process;

  stim : process
    variable found : boolean;
    variable cnt   : natural;
  begin
    -- Init: Reset in Automatik, Anzeige OUT
    rst <= '1';
    btn_step <= '0';
    sw <= "000";
    wait_cycles(5, clk);
    rst <= '0';
    report "CHECK t=" & time'image(now) & " reset released, auto start" severity note;

    -- Automatik: OUT-Folge 1,2,3,5,8,13
    -- warte auf 0001
    found := false;
    for i in 1 to 300 loop
      wait until rising_edge(clk);
      wait for 1 ns;
      if led = "0001" then
        found := true;
        exit;
      end if;
    end loop;
    report "CHECK t=" & time'image(now) & " led=" & to_string(led) & " expect 0001" severity note;
    assert found and led = "0001" report "AUTO OUT=1 missing" severity error;

    wait_cycles(2, clk);
    found := false;
    for i in 1 to 300 loop
      wait until rising_edge(clk);
      wait for 1 ns;
      if led = "0010" then
        found := true;
        exit;
      end if;
    end loop;
    report "CHECK t=" & time'image(now) & " led=" & to_string(led) & " expect 0010" severity note;
    assert found and led = "0010" report "AUTO OUT=2 missing" severity error;

    wait_cycles(2, clk);
    found := false;
    for i in 1 to 300 loop
      wait until rising_edge(clk);
      wait for 1 ns;
      if led = "0011" then
        found := true;
        exit;
      end if;
    end loop;
    report "CHECK t=" & time'image(now) & " led=" & to_string(led) & " expect 0011" severity note;
    assert found and led = "0011" report "AUTO OUT=3 missing" severity error;

    wait_cycles(2, clk);
    found := false;
    for i in 1 to 300 loop
      wait until rising_edge(clk);
      wait for 1 ns;
      if led = "0101" then
        found := true;
        exit;
      end if;
    end loop;
    report "CHECK t=" & time'image(now) & " led=" & to_string(led) & " expect 0101" severity note;
    assert found and led = "0101" report "AUTO OUT=5 missing" severity error;

    wait_cycles(2, clk);
    found := false;
    for i in 1 to 300 loop
      wait until rising_edge(clk);
      wait for 1 ns;
      if led = "1000" then
        found := true;
        exit;
      end if;
    end loop;
    report "CHECK t=" & time'image(now) & " led=" & to_string(led) & " expect 1000" severity note;
    assert found and led = "1000" report "AUTO OUT=8 missing" severity error;

    wait_cycles(2, clk);
    found := false;
    for i in 1 to 300 loop
      wait until rising_edge(clk);
      wait for 1 ns;
      if led = "1101" then
        found := true;
        exit;
      end if;
    end loop;
    report "CHECK t=" & time'image(now) & " led=" & to_string(led) & " expect 1101" severity note;
    assert found and led = "1101" report "AUTO OUT=13 missing" severity error;

    -- auf HALT warten (noch 5 Befehle: JMP,LDA,ADD,JC,HLT = 20 Takte + Reserve)
    wait_cycles(40, clk);

    -- Status pruefen (HALT, Automatik, C=1, Z=0 => 1010)
    sw <= "011";
    wait_cycles(5, clk);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " status led=" & to_string(led) severity note;
    assert led = "1010" report "STATUS after HALT expected 1010" severity error;

    -- ACC = 5
    sw <= "001";
    wait_cycles(5, clk);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " acc led=" & to_string(led) severity note;
    assert led = "0101" report "ACC after HALT expected 0101" severity error;

    -- PC = 15
    sw <= "010";
    wait_cycles(5, clk);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " pc led=" & to_string(led) severity note;
    assert led = "1111" report "PC after HALT expected 1111" severity error;

    -- OUT = 13
    sw <= "000";
    wait_cycles(5, clk);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " out led=" & to_string(led) severity note;
    assert led = "1101" report "OUT after HALT expected 1101" severity error;

    -- Latenz 3 Taktflanken nach Schalterwechsel (CPU haelt an, Register stabil)
    -- aktuell sw=000 OUT=1101, wechsle zu ACC=0101
    wait until rising_edge(clk);
    wait for 1 ns;
    sw <= "001";
    -- 1. Flanke danach: noch alt
    wait until rising_edge(clk);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " latency1 led=" & to_string(led) severity note;
    assert led = "1101" report "LATENCY cycle1 must show old value" severity error;
    -- 2. Flanke: noch alt
    wait until rising_edge(clk);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " latency2 led=" & to_string(led) severity note;
    assert led = "1101" report "LATENCY cycle2 must show old value" severity error;
    -- 3. Flanke: neu
    wait until rising_edge(clk);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " latency3 led=" & to_string(led) severity note;
    assert led = "0101" report "LATENCY cycle3 must show new value" severity error;
    -- 4. Flanke: bleibt neu
    wait until rising_edge(clk);
    wait for 1 ns;
    assert led = "0101" report "LATENCY cycle4 must stay new" severity error;

    -- zweite Latenzpruefung ACC -> PC
    wait until rising_edge(clk);
    wait for 1 ns;
    sw <= "010";
    wait until rising_edge(clk);
    wait for 1 ns;
    assert led = "0101" report "LATENCY2 cycle1 old" severity error;
    wait until rising_edge(clk);
    wait for 1 ns;
    assert led = "0101" report "LATENCY2 cycle2 old" severity error;
    wait until rising_edge(clk);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " latency2-3 led=" & to_string(led) severity note;
    assert led = "1111" report "LATENCY2 cycle3 new PC=15" severity error;

    -- Reset mitten im Programm: zurueck auf OUT/Auto, Reset, OUT=1 muss wiederkommen
    sw <= "000";
    wait_cycles(3, clk);
    rst <= '1';
    wait_cycles(3, clk);
    rst <= '0';
    report "CHECK t=" & time'image(now) & " second run after reset" severity note;
    found := false;
    for i in 1 to 300 loop
      wait until rising_edge(clk);
      wait for 1 ns;
      if led = "0001" then
        found := true;
        exit;
      end if;
    end loop;
    report "CHECK t=" & time'image(now) & " restart led=" & to_string(led) severity note;
    assert found report "RESET restart: OUT=1 not seen" severity error;

    -- mitten im Programm resetten (nach ca. 20 Takten, sicher vor HALT)
    wait_cycles(20, clk);
    rst <= '1';
    wait_cycles(3, clk);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " mid-program reset asserted led=" & to_string(led) severity note;
    rst <= '0';
    found := false;
    for i in 1 to 300 loop
      wait until rising_edge(clk);
      wait for 1 ns;
      if led = "0001" then
        found := true;
        exit;
      end if;
    end loop;
    report "CHECK t=" & time'image(now) & " after mid-reset led=" & to_string(led) severity note;
    assert found report "MID-PROGRAM RESET: program did not restart" severity error;

    -- Einzelschritt
    sw <= "100"; -- Einzelschritt, OUT
    rst <= '1';
    wait_cycles(3, clk);
    rst <= '0';
    wait_cycles(6, clk); -- Sync von sw(2) + LED abwarten
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " single-step idle led=" & to_string(led) severity note;
    assert led = "0000" report "SINGLE idle OUT must be 0" severity error;
    -- ohne Tastendruck stehen bleiben
    wait_cycles(20, clk);
    wait for 1 ns;
    assert led = "0000" report "SINGLE without press must stay" severity error;

    -- ACC und PC sind 0 im Stillstand
    sw <= "101"; -- single, ACC
    wait_cycles(5, clk);
    wait for 1 ns;
    assert led = "0000" report "SINGLE idle ACC must be 0" severity error;
    sw <= "110"; -- single, PC
    wait_cycles(5, clk);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " single idle pc led=" & to_string(led) severity note;
    assert led = "0000" report "SINGLE idle PC must be 0" severity error;
    sw <= "100"; -- zurueck OUT
    wait_cycles(5, clk);

    -- erster Druck: genau ein Befehl (LDI 1)
    btn_step <= '1';
    wait_cycles(10, clk);
    btn_step <= '0';
    wait_cycles(15, clk);
    -- ACC muss 1 sein
    sw <= "101";
    wait_cycles(5, clk);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " after 1st press acc led=" & to_string(led) severity note;
    assert led = "0001" report "SINGLE after 1st press ACC=1" severity error;
    -- PC muss 1 sein
    sw <= "110";
    wait_cycles(5, clk);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " after 1st press pc led=" & to_string(led) severity note;
    assert led = "0001" report "SINGLE after 1st press PC=1" severity error;

    -- zweiter Druck: genau ein weiterer Befehl (STA 0 -> PC=2)
    sw <= "110";
    wait_cycles(3, clk);
    btn_step <= '1';
    wait_cycles(10, clk);
    btn_step <= '0';
    wait_cycles(15, clk);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " after 2nd press pc led=" & to_string(led) severity note;
    assert led = "0010" report "SINGLE after 2nd press PC=2" severity error;

    -- kurzer Impuls < DEBOUNCE_CYCLES darf keinen Schritt ausloesen
    btn_step <= '1';
    wait until rising_edge(clk);
    btn_step <= '0';
    wait_cycles(15, clk);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " after short pulse pc led=" & to_string(led) severity note;
    assert led = "0010" report "SHORT pulse must not step" severity error;

    report "TB_COMPLETE" severity note;
    stop(0);
    wait;
  end process;
end architecture sim;
