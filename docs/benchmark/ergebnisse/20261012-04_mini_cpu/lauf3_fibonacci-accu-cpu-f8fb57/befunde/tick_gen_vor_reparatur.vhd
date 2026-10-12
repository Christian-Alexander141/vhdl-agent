library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

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
  signal cnt : natural range 0 to 50000000 - 1;
begin

  -- Plausibilitaet: TICK_CYCLES muss zur Range passen (mindestens 4 laut PROMPT).
  assert TICK_CYCLES >= 4
    report "tick_gen: TICK_CYCLES should be >= 4"
    severity warning;
  assert TICK_CYCLES <= 50000000
    report "tick_gen: TICK_CYCLES exceeds static counter range"
    severity failure;

  p_seq : process(clk)
  begin
    if rising_edge(clk) then
      if rst = '1' then
        cnt  <= 0;
        tick <= '0';
      else
        if cnt = TICK_CYCLES - 1 then
          cnt  <= 0;
          tick <= '1';
        else
          cnt  <= cnt + 1;
          tick <= '0';
        end if;
      end if;
    end if;
  end process p_seq;

end architecture rtl;