library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity alu is
  port (
    a_in      : in  std_logic_vector(7 downto 0);
    b_in      : in  std_logic_vector(7 downto 0);
    clk       : in  std_logic;
    carry_out : out std_logic;
    fi_en     : in  std_logic;
    rst       : in  std_logic;
    result_out : out std_logic_vector(7 downto 0);
    sub       : in  std_logic;
    zero_out  : out std_logic
  );
end entity alu;

architecture rtl of alu is
  signal sum9       : unsigned(8 downto 0);
  signal carry_comb : std_logic;
  signal zero_comb  : std_logic;
  signal flag_c     : std_logic := '0';
  signal flag_z     : std_logic := '0';
begin

  p_comb: process(all)
    variable a9 : unsigned(8 downto 0);
    variable b9 : unsigned(8 downto 0);
  begin
    a9 := '0' & unsigned(a_in);
    if sub = '1' then
      b9 := ('0' & unsigned(not b_in)) + to_unsigned(1, 9);
    else
      b9 := '0' & unsigned(b_in);
    end if;
    sum9 <= a9 + b9;
  end process p_comb;

  carry_comb <= sum9(8);
  zero_comb  <= '1' when sum9(7 downto 0) = to_unsigned(0, 8) else '0';

  result_out <= std_logic_vector(sum9(7 downto 0));

  p_flags: process(clk)
  begin
    if rising_edge(clk) then
      if rst = '1' then
        flag_c <= '0';
        flag_z <= '0';
      elsif fi_en = '1' then
        flag_c <= carry_comb;
        flag_z <= zero_comb;
      end if;
    end if;
  end process p_flags;

  carry_out <= flag_c;
  zero_out  <= flag_z;

end architecture rtl;