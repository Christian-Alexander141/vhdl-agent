library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity program_counter is
  port (
    clk    : in  std_logic;
    rst    : in  std_logic;
    step_en: in  std_logic;
    ce     : in  std_logic;
    j      : in  std_logic;
    j_data : in  std_logic_vector(3 downto 0);
    clr    : in  std_logic;
    pc_out : out std_logic_vector(3 downto 0)
  );
end entity program_counter;

architecture rtl of program_counter is
  signal pc : unsigned(3 downto 0) := (others => '0');
begin
  pc_out <= std_logic_vector(pc);
  process(clk)
  begin
    if rising_edge(clk) then
      if rst = '1' or clr = '1' then
        pc <= (others => '0');
      elsif step_en = '1' then
        if j = '1' then
          pc <= unsigned(j_data);
        elsif ce = '1' then
          pc <= pc + 1;
        end if;
      end if;
    end if;
  end process;
end architecture rtl;
