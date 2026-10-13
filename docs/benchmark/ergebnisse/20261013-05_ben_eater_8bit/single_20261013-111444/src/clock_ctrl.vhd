library ieee;
use ieee.std_logic_1164.all;

entity clock_ctrl is
  generic (
    TICK_CYCLES : positive := 4000000
  );
  port (
    clk         : in  std_logic;
    rst         : in  std_logic;
    mode_uart   : in  std_logic;
    sw1         : in  std_logic;
    rise_in     : in  std_logic;
    halted      : in  std_logic;
    loader_busy : in  std_logic;
    oi_active   : in  std_logic;
    tx_busy     : in  std_logic;
    tick        : out std_logic;
    step_en     : out std_logic
  );
end entity clock_ctrl;

architecture rtl of clock_ctrl is
  signal cnt : integer range 0 to 2147483647 := 0;
  signal tick_i : std_logic;
begin
  process(clk)
  begin
    if rising_edge(clk) then
      if rst = '1' then
        cnt <= 0;
      else
        if cnt >= TICK_CYCLES - 1 then
          cnt <= 0;
        else
          cnt <= cnt + 1;
        end if;
      end if;
    end if;
  end process;

  tick_i <= '1' when cnt = TICK_CYCLES - 1 else '0';
  tick <= tick_i;

  process(mode_uart, sw1, rise_in, halted, loader_busy, oi_active, tx_busy, tick_i)
  begin
    if halted = '1' then
      step_en <= '0';
    elsif mode_uart = '0' then
      if sw1 = '0' then
        step_en <= tick_i;
      else
        step_en <= rise_in;
      end if;
    else
      if loader_busy = '1' then
        step_en <= '0';
      elsif oi_active = '1' and tx_busy = '1' then
        step_en <= '0';
      else
        step_en <= '1';
      end if;
    end if;
  end process;
end architecture rtl;
