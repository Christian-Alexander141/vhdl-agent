library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity tick_gen is
  generic (
    TICK_CYCLES : positive := 50_000_000
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

  -- Counter range must follow generic; assert generic in valid range.
  -- PROMPT.md: TICK_CYCLES mindestens 4.
  p_cnt : process(clk)
  begin
    if rising_edge(clk) then
      if rst = '1' then
        cnt <= 0;
      elsif cnt = TICK_CYCLES - 1 then
        cnt <= 0;
      else
        cnt <= cnt + 1;
      end if;
    end if;
  end process p_cnt;

  -- Kombinatorischer Tick: genau eine Taktperiode lang '1', solange der
  -- Zaehler auf TICK_CYCLES-1 steht. Dadurch erfolgt in Automatik der
  -- erste Befehl mit der TICK_CYCLES-ten Flanke ohne Reset (WAIT -> FETCH).
  -- Laeuft immer (kein Enable, kein Halt), auch im Einzelschritt und HALT.
  tick <= '1' when (rst = '0' and cnt = TICK_CYCLES - 1) else '0';

end architecture rtl;