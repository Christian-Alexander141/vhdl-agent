library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity sync2 is
  generic (
    WIDTH : positive := 1
  );
  port (
    clk  : in  std_logic;
    rst  : in  std_logic;
    din  : in  std_logic_vector(WIDTH-1 downto 0);
    dout : out std_logic_vector(WIDTH-1 downto 0)
  );
end entity sync2;

architecture rtl of sync2 is
  signal stage1 : std_logic_vector(WIDTH-1 downto 0) := (others => '0');
  signal stage2 : std_logic_vector(WIDTH-1 downto 0) := (others => '0');
begin

  p_sync : process(clk)
  begin
    if rising_edge(clk) then
      if rst = '1' then
        stage1 <= (others => '0');
        stage2 <= (others => '0');
      else
        stage1 <= din;
        stage2 <= stage1;
      end if;
    end if;
  end process p_sync;

  dout <= stage2;

end architecture rtl;