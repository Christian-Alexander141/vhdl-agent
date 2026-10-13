library ieee;
use ieee.std_logic_1164.all;

entity tick_gen is
  generic (
    TICK_CYCLES : positive := 50000000
  );
  port (
    clk  : in  std_logic;
    rst  : in  std_logic;
    tick : out std_logic
  );
end entity tick_gen;

architecture rtl of tick_gen is
  signal cnt : natural := 0;
begin
  process(clk)
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
  end process;

  tick <= '1' when cnt = TICK_CYCLES - 1 else '0';
end architecture rtl;
