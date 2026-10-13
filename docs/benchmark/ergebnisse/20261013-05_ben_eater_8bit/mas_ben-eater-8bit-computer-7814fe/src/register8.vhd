library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity register8 is
  port (
    clk      : in  std_logic;
    data_in  : in  std_logic_vector(7 downto 0);
    data_out : out std_logic_vector(7 downto 0);
    load_en  : in  std_logic;
    rst      : in  std_logic
  );
end entity register8;

architecture rtl of register8 is
  signal reg : std_logic_vector(7 downto 0) := (others => '0');
begin

  p_seq: process(clk)
  begin
    if rising_edge(clk) then
      if rst = '1' then
        reg <= (others => '0');
      elsif load_en = '1' then
        reg <= data_in;
      end if;
    end if;
  end process p_seq;

  data_out <= reg;

end architecture rtl;