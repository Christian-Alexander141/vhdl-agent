library ieee;
use ieee.std_logic_1164.all;

entity register8 is
  port (
    clk : in  std_logic;
    rst : in  std_logic;
    en  : in  std_logic;
    clr : in  std_logic;
    d   : in  std_logic_vector(7 downto 0);
    q   : out std_logic_vector(7 downto 0)
  );
end entity register8;

architecture rtl of register8 is
  signal r : std_logic_vector(7 downto 0) := (others => '0');
begin
  q <= r;
  process(clk)
  begin
    if rising_edge(clk) then
      if rst = '1' or clr = '1' then
        r <= (others => '0');
      elsif en = '1' then
        r <= d;
      end if;
    end if;
  end process;
end architecture rtl;
