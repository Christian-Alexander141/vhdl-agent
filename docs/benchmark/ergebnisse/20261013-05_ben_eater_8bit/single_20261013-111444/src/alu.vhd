library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity alu is
  port (
    clk     : in  std_logic;
    rst     : in  std_logic;
    step_en : in  std_logic;
    a       : in  std_logic_vector(7 downto 0);
    b       : in  std_logic_vector(7 downto 0);
    su      : in  std_logic;
    fi      : in  std_logic;
    clr     : in  std_logic;
    result  : out std_logic_vector(7 downto 0);
    flag_c  : out std_logic;
    flag_z  : out std_logic
  );
end entity alu;

architecture rtl of alu is
  signal sum9 : unsigned(8 downto 0);
  signal res8 : std_logic_vector(7 downto 0);
  signal carry_c : std_logic;
  signal zero_c  : std_logic;
  signal fc : std_logic := '0';
  signal fz : std_logic := '0';
begin
  process(a, b, su)
    variable tmp : unsigned(8 downto 0);
  begin
    if su = '0' then
      tmp := ('0' & unsigned(a)) + ('0' & unsigned(b));
    else
      tmp := ('0' & unsigned(a)) + ('0' & unsigned(not b)) + to_unsigned(1, 9);
    end if;
    sum9 <= tmp;
  end process;

  res8 <= std_logic_vector(sum9(7 downto 0));
  carry_c <= sum9(8);
  zero_c <= '1' when sum9(7 downto 0) = to_unsigned(0, 8) else '0';

  result <= res8;
  flag_c <= fc;
  flag_z <= fz;

  process(clk)
  begin
    if rising_edge(clk) then
      if rst = '1' or clr = '1' then
        fc <= '0';
        fz <= '0';
      elsif step_en = '1' and fi = '1' then
        fc <= carry_c;
        fz <= zero_c;
      end if;
    end if;
  end process;
end architecture rtl;
