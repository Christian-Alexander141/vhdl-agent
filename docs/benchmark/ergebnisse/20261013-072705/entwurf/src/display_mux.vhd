library ieee;
use ieee.std_logic_1164.all;

entity display_mux is
  port (
    out_value : in  std_logic_vector(3 downto 0);
    acc       : in  std_logic_vector(3 downto 0);
    pc        : in  std_logic_vector(3 downto 0);
    z         : in  std_logic;
    c         : in  std_logic;
    halted    : in  std_logic;
    mode      : in  std_logic;
    sel       : in  std_logic_vector(1 downto 0);
    disp      : out std_logic_vector(3 downto 0)
  );
end entity display_mux;

architecture rtl of display_mux is
begin
  process(out_value, acc, pc, z, c, halted, mode, sel)
  begin
    case sel is
      when "00" =>
        disp <= out_value;
      when "01" =>
        disp <= acc;
      when "10" =>
        disp <= pc;
      when others => -- "11" Status
        disp <= halted & mode & c & z;
    end case;
  end process;
end architecture rtl;
