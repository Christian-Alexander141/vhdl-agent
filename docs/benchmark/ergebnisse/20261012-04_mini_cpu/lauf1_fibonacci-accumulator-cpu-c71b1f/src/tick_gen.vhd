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
  signal cnt_r : natural := 0;
begin

  -- Kombinatorischer Tick: '1' genau wenn Zaehler auf TICK_CYCLES-1 steht.
  -- Dadurch liegt der Tick in dem Takt vor der Flanke, die WAIT -> FETCH
  -- ausloest, und der erste Befehl beginnt mit der TICK_CYCLES-ten
  -- steigenden Flanke ohne Reset (PROMPT.md R64/R66).
  tick <= '1' when cnt_r = TICK_CYCLES - 1 else '0';

  -- Synchroner Reset, active high (PROMPT.md R71). Zaehlt 0 .. TICK_CYCLES-1,
  -- laeuft immer (auch in Einzelschritt/HALT, R65).
  p_seq : process(clk)
  begin
    if rising_edge(clk) then
      if rst = '1' then
        cnt_r <= 0;
      elsif cnt_r = TICK_CYCLES - 1 then
        cnt_r <= 0;
      else
        cnt_r <= cnt_r + 1;
      end if;
    end if;
  end process p_seq;

end architecture rtl;