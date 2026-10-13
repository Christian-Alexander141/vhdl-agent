library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity program_counter is
  port (
    ce        : in  std_logic;
    clk       : in  std_logic;
    data_in   : in  std_logic_vector(3 downto 0);
    j_load    : in  std_logic;
    rst       : in  std_logic;
    count_out : out std_logic_vector(3 downto 0)
  );
end entity program_counter;

architecture rtl of program_counter is
  signal cnt : unsigned(3 downto 0) := (others => '0');
begin

  p_seq: process(clk)
  begin
    if rising_edge(clk) then
      if rst = '1' then
        cnt <= (others => '0');
      elsif j_load = '1' then
        cnt <= unsigned(data_in);
      elsif ce = '1' then
        cnt <= cnt + 1;
      end if;
    end if;
  end process p_seq;

  count_out <= std_logic_vector(cnt);

end architecture rtl;