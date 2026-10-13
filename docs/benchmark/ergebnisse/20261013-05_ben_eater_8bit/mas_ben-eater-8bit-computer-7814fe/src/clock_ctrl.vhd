library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity clock_ctrl is
  generic (
    TICK_CYCLES : positive := 4000000
  );
  port (
    clk         : in  std_logic;
    halted      : in  std_logic;
    loader_busy : in  std_logic;
    oi_active   : in  std_logic;
    rst         : in  std_logic;
    step_rise   : in  std_logic;
    sw_step     : in  std_logic;
    tx_busy     : in  std_logic;
    uart_mode   : in  std_logic;
    step_enable : out std_logic;
    tick        : out std_logic
  );
end entity clock_ctrl;

architecture rtl of clock_ctrl is
  signal cnt    : integer range 0 to 2147483647 := 0;
  signal tick_i : std_logic := '0';
begin
  -- Tick-Generator: zaehlt 0 .. TICK_CYCLES-1, Tick beim Endstand.
  -- Laeuft immer (auch bei Halt), nur synchroner Reset setzt zurueck.
  p_tick : process(clk)
  begin
    if rising_edge(clk) then
      if rst = '1' then
        cnt <= 0;
      else
        if cnt = TICK_CYCLES - 1 then
          cnt <= 0;
        else
          cnt <= cnt + 1;
        end if;
      end if;
    end if;
  end process p_tick;

  tick_i <= '1' when cnt = TICK_CYCLES - 1 else '0';
  tick   <= tick_i;

  -- Schrittfreigabe (kombinatorisch, vollstaendig abgedeckt):
  -- Board-Modus: Tick wenn sw_step = '0', step_rise wenn sw_step = '1'.
  -- UART-Modus: jeder Takt, ausser Lader empfängt (loader_busy) oder
  -- OI aktiv waehrend Sender beschaeftigt (oi_active und tx_busy).
  -- In beiden Modi keine Freigabe bei halted = '1'.
  p_step : process(all)
  begin
    if halted = '1' then
      step_enable <= '0';
    elsif uart_mode = '1' then
      if loader_busy = '1' then
        step_enable <= '0';
      elsif oi_active = '1' and tx_busy = '1' then
        step_enable <= '0';
      else
        step_enable <= '1';
      end if;
    else
      if sw_step = '0' then
        step_enable <= tick_i;
      else
        step_enable <= step_rise;
      end if;
    end if;
  end process p_step;

end architecture rtl;