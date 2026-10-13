library ieee;
use ieee.std_logic_1164.all;

entity input_sync is
  generic (
    WIDTH : positive := 1;
    INIT  : std_logic := '0'
  );
  port (
    clk   : in  std_logic;
    d_in  : in  std_logic_vector(WIDTH-1 downto 0);
    d_out : out std_logic_vector(WIDTH-1 downto 0)
  );
end entity input_sync;

architecture rtl of input_sync is
  signal s1 : std_logic_vector(WIDTH-1 downto 0) := (others => INIT);
  signal s2 : std_logic_vector(WIDTH-1 downto 0) := (others => INIT);
begin
  process(clk)
  begin
    if rising_edge(clk) then
      s1 <= d_in;
      s2 <= s1;
    end if;
  end process;
  d_out <= s2;
end architecture rtl;
