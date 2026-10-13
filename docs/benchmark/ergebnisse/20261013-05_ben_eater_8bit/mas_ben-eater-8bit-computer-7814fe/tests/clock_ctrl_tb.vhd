library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity clock_ctrl_tb is
end entity clock_ctrl_tb;

architecture sim of clock_ctrl_tb is
  constant CLK_PERIOD     : time := 10 ns;
  constant TICK_CYCLES_TB : positive := 4;

  signal clk         : std_logic := '0';
  signal halted      : std_logic := '0';
  signal loader_busy : std_logic := '0';
  signal oi_active   : std_logic := '0';
  signal rst         : std_logic := '1';
  signal step_rise   : std_logic := '0';
  signal sw_step     : std_logic := '0';
  signal tx_busy     : std_logic := '0';
  signal uart_mode   : std_logic := '0';
  signal step_enable : std_logic;
  signal tick        : std_logic;

  signal tb_done : boolean := false;
begin
  clk <= not clk after CLK_PERIOD / 2 when not tb_done else '0';

  dut: entity work.clock_ctrl
    generic map (
      TICK_CYCLES => TICK_CYCLES_TB
    )
    port map (
      clk         => clk,
      halted      => halted,
      loader_busy => loader_busy,
      oi_active   => oi_active,
      rst         => rst,
      step_rise   => step_rise,
      sw_step     => sw_step,
      tx_busy     => tx_busy,
      uart_mode   => uart_mode,
      step_enable => step_enable,
      tick        => tick
    );

  stim: process
    procedure wait_cycles(n : positive) is
    begin
      for i in 1 to n loop
        wait until rising_edge(clk);
      end loop;
    end procedure;
  begin
    -- Reset sequence (min. 2 Zyklen rst='1')
    halted      <= '0';
    loader_busy <= '0';
    oi_active   <= '0';
    rst         <= '1';
    step_rise   <= '0';
    sw_step     <= '0';
    tx_busy     <= '0';
    uart_mode   <= '0';
    wait_cycles(3);
    wait for 1 ns;
    report "CHECK reset held t=" & time'image(now) & " tick=" & std_logic'image(tick)
      & " step_enable=" & std_logic'image(step_enable) severity note;
    assert tick = '0'
      report "REQ R4: tick muss im synchronen Reset 0 sein (Zaehler gehalten)" severity error;
    assert tick = '0'
      report "REQ R43: Tick-Zaehler muss bei rst=1 in 0/Ruhe stehen" severity error;
    assert step_enable = '0'
      report "REQ R41: Board-Auto step_enable=tick muss im Reset 0 sein" severity error;

    -- Reset loesen
    rst <= '0';

    -- R40: Tick-Periode 4 (tick genau 1 Takt je 4 Takte)
    for k in 1 to 8 loop
      wait until rising_edge(clk);
      wait for 1 ns;
      report "CHECK R40 k=" & integer'image(k) & " t=" & time'image(now)
        & " tick=" & std_logic'image(tick) severity note;
      if (k mod 4) = 3 then
        assert tick = '1'
          report "REQ R40: Tick muss bei TICK_CYCLES=4 an Kante " & integer'image(k) & " =1 sein" severity error;
      else
        assert tick = '0'
          report "REQ R40: Tick muss an Kante " & integer'image(k) & " =0 sein" severity error;
      end if;
    end loop;

    -- R8/R41 Board-Auto: sw_step=0 -> step_enable = tick (rise wird ignoriert)
    uart_mode <= '0';
    halted    <= '0';
    sw_step   <= '0';
    step_rise <= '0';
    wait for 2 ns;
    for k in 1 to 8 loop
      wait until rising_edge(clk);
      wait for 1 ns;
      report "CHECK auto k=" & integer'image(k) & " tick=" & std_logic'image(tick)
        & " step_enable=" & std_logic'image(step_enable) severity note;
      assert step_enable = tick
        report "REQ R8: Board-Auto step_enable muss = tick sein (Kante " & integer'image(k) & ")" severity error;
    end loop;
    assert step_enable = tick
      report "REQ R41: Board-Modus sw_step=0: Freigabe muss Tick sein" severity error;
    -- rise=1 darf im Auto-Modus nichts aendern
    step_rise <= '1';
    wait for 2 ns;
    for k in 1 to 4 loop
      wait until rising_edge(clk);
      wait for 1 ns;
      assert step_enable = tick
        report "REQ R41: Board-Auto muss step_rise ignorieren (Kante " & integer'image(k) & ")" severity error;
    end loop;
    step_rise <= '0';
    wait for 2 ns;

    -- R8/R41 Board-Einzeltakt: sw_step=1 -> step_enable = step_rise (tick egal)
    sw_step <= '1';
    step_rise <= '0';
    wait for 2 ns;
    report "CHECK single rise=0 t=" & time'image(now)
      & " tick=" & std_logic'image(tick) & " se=" & std_logic'image(step_enable) severity note;
    assert step_enable = '0'
      report "REQ R8: Einzeltakt step_enable muss bei rise=0 gleich 0 sein" severity error;
    step_rise <= '1';
    wait for 2 ns;
    report "CHECK single rise=1 t=" & time'image(now)
      & " tick=" & std_logic'image(tick) & " se=" & std_logic'image(step_enable) severity note;
    assert step_enable = '1'
      report "REQ R8: Einzeltakt step_enable muss bei rise=1 gleich 1 sein" severity error;
    -- tick=1 darf im Einzeltakt nichts erzwingen: warte tick=1, rise=0 -> 0
    step_rise <= '0';
    wait until tick = '1' for 1 us;
    assert tick = '1'
      report "REQ R40: Timeout beim Warten auf tick=1 (Einzeltakt-Check)" severity error;
    wait for 1 ns;
    report "CHECK single bei tick=1 rise=0 t=" & time'image(now)
      & " se=" & std_logic'image(step_enable) severity note;
    assert step_enable = '0'
      report "REQ R41: Board-Einzeltakt muss tick ignorieren (rise=0 -> 0 trotz tick=1)" severity error;
    step_rise <= '1';
    wait for 2 ns;
    assert step_enable = '1'
      report "REQ R41: Board-Einzeltakt rise=1 -> 1 (unabhaengig von tick)" severity error;
    step_rise <= '0';
    sw_step   <= '0';
    wait for 2 ns;

    -- R37: halted=1 sperrt in beiden Modi
    halted <= '1';
    uart_mode <= '0';
    sw_step <= '0';
    step_rise <= '1';
    wait for 2 ns;
    for k in 1 to 5 loop
      wait until rising_edge(clk);
      wait for 1 ns;
      report "CHECK halt board k=" & integer'image(k) & " tick=" & std_logic'image(tick)
        & " se=" & std_logic'image(step_enable) severity note;
      assert step_enable = '0'
        report "REQ R37: bei HLT muss step_enable=0 sein (Board, Kante " & integer'image(k) & ")" severity error;
    end loop;
    sw_step <= '1';
    step_rise <= '1';
    wait for 2 ns;
    assert step_enable = '0'
      report "REQ R37: bei HLT muss step_enable=0 sein (Einzeltakt, rise=1)" severity error;
    uart_mode <= '1';
    loader_busy <= '0';
    oi_active <= '0';
    tx_busy <= '0';
    wait for 2 ns;
    assert step_enable = '0'
      report "REQ R37: bei HLT muss step_enable=0 sein (UART-Modus, alles frei)" severity error;
    halted <= '0';
    uart_mode <= '0';
    sw_step <= '0';
    step_rise <= '0';
    wait for 2 ns;

    -- R41: UART-Modus Wahrheitstabelle
    uart_mode <= '1';
    halted <= '0';
    loader_busy <= '0'; oi_active <= '0'; tx_busy <= '0';
    wait for 2 ns;
    report "CHECK uart frei t=" & time'image(now) & " se=" & std_logic'image(step_enable) severity note;
    assert step_enable = '1'
      report "REQ R41: UART-Modus frei muss step_enable=1 sein" severity error;
    oi_active <= '0'; tx_busy <= '1';
    wait for 2 ns;
    assert step_enable = '1'
      report "REQ R41: UART-Modus oi=0 tx=1 muss step_enable=1 sein" severity error;
    oi_active <= '1'; tx_busy <= '0';
    wait for 2 ns;
    assert step_enable = '1'
      report "REQ R41: UART-Modus oi=1 tx=0 muss step_enable=1 sein" severity error;
    oi_active <= '1'; tx_busy <= '1';
    wait for 2 ns;
    report "CHECK uart oi+busy t=" & time'image(now) & " se=" & std_logic'image(step_enable) severity note;
    assert step_enable = '0'
      report "REQ R41: UART-Modus oi=1 und tx_busy=1 muss step_enable=0 sein" severity error;
    loader_busy <= '1'; oi_active <= '0'; tx_busy <= '0';
    wait for 2 ns;
    assert step_enable = '0'
      report "REQ R41: UART-Modus loader_busy=1 muss step_enable=0 sein" severity error;
    loader_busy <= '1'; oi_active <= '1'; tx_busy <= '1';
    wait for 2 ns;
    assert step_enable = '0'
      report "REQ R41: UART-Modus loader_busy=1 bleibt 0 auch bei oi+busy" severity error;
    -- Unabhaengigkeit von Tick/rise im UART-Modus
    loader_busy <= '0'; oi_active <= '0'; tx_busy <= '0';
    step_rise <= '1'; sw_step <= '1';
    wait for 2 ns;
    for k in 1 to 5 loop
      wait until rising_edge(clk);
      wait for 1 ns;
      assert step_enable = '1'
        report "REQ R41: UART-Modus frei bleibt 1 unabhaengig von Tick/rise (Kante " & integer'image(k) & ")" severity error;
    end loop;
    step_rise <= '0'; sw_step <= '0';

    -- R53: erstes Rahmenbyte (loader_busy) haelt CPU im UART-Modus an
    uart_mode <= '1';
    loader_busy <= '1';
    wait for 2 ns;
    report "CHECK R53 busy t=" & time'image(now) & " se=" & std_logic'image(step_enable) severity note;
    assert step_enable = '0'
      report "REQ R53: Rahmenempfang (loader_busy) muss CPU im UART-Modus anhalten" severity error;
    loader_busy <= '0';
    wait for 2 ns;
    assert step_enable = '1'
      report "REQ R53: nach Rahmenende/Verwerfen muss CPU im UART-Modus weiterlaufen" severity error;
    uart_mode <= '0';
    wait for 2 ns;

    -- R4: Synchronitaet des Resets (kein async Durchgriff)
    uart_mode <= '0'; halted <= '0'; sw_step <= '0';
    loader_busy <= '0'; oi_active <= '0'; tx_busy <= '0'; step_rise <= '0';
    wait until tick = '1' for 1 us;
    assert tick = '1'
      report "REQ R40: Timeout beim Warten auf tick=1 (Sync-Check)" severity error;
    wait for 2 ns; -- Mitte des Tick-Taktes, nicht an der Flanke
    rst <= '1';
    wait for 1 ns; -- noch vor der naechsten Flanke: sync Reset darf noch nicht wirken
    report "CHECK sync-rst t=" & time'image(now) & " tick=" & std_logic'image(tick) severity note;
    assert tick = '1'
      report "REQ R4: synchroner Reset darf tick vor der Flanke nicht aendern" severity error;
    wait until rising_edge(clk);
    wait for 1 ns;
    report "CHECK nach sync-rst-Flanke t=" & time'image(now) & " tick=" & std_logic'image(tick) severity note;
    assert tick = '0'
      report "REQ R4: synchroner Reset active high muss Zaehler an der Flanke loeschen" severity error;

    -- R43: Reset-Halten und deterministischer Neustart
    rst <= '1';
    wait_cycles(3);
    wait for 1 ns;
    assert tick = '0'
      report "REQ R43: Tick-Zaehler bleibt bei gehaltenem rst auf 0" severity error;
    rst <= '0';
    for k in 1 to 4 loop
      wait until rising_edge(clk);
      wait for 1 ns;
      report "CHECK restart k=" & integer'image(k) & " tick=" & std_logic'image(tick) severity note;
      if (k mod 4) = 3 then
        assert tick = '1'
          report "REQ R43: nach Reset muss Tick nach 3 Takten wieder pulsen (Kante " & integer'image(k) & ")" severity error;
      else
        assert tick = '0'
          report "REQ R43: nach Reset kein Frueh-Tick an Kante " & integer'image(k) severity error;
      end if;
    end loop;

    tb_done <= true;
    report "TB_COMPLETE" severity note;
    wait;
  end process stim;

end architecture sim;