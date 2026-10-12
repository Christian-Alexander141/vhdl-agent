library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity sync2 is
  generic (
    WIDTH : positive := 1
  );
  port (
    clk : in  std_logic;
    rst : in  std_logic;
    d   : in  std_logic_vector(WIDTH - 1 downto 0);
    q   : out std_logic_vector(WIDTH - 1 downto 0)
  );
end entity sync2;

architecture rtl of sync2 is
  signal s1 : std_logic_vector(WIDTH - 1 downto 0);
  signal s2 : std_logic_vector(WIDTH - 1 downto 0);
begin

  p_sync : process(clk)
  begin
    if rising_edge(clk) then
      if rst = '1' then
        s1 <= (others => '0');
        s2 <= (others => '0');
      else
        s1 <= d;
        s2 <= s1;
      end if;
    end if;
  end process p_sync;

  q <= s2;

end architecture rtl;