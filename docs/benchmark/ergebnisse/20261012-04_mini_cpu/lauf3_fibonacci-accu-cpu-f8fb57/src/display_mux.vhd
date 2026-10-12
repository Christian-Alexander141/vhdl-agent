library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity display_mux is
  port (
    acc       : in  std_logic_vector(3 downto 0);
    c         : in  std_logic;
    disp      : out std_logic_vector(3 downto 0);
    halted    : in  std_logic;
    mode      : in  std_logic;
    out_value : in  std_logic_vector(3 downto 0);
    pc        : in  std_logic_vector(3 downto 0);
    sel       : in  std_logic_vector(1 downto 0);
    z         : in  std_logic
  );
end entity display_mux;

architecture rtl of display_mux is
begin

  p_comb: process(all)
  begin
    case sel is
      when "00" =>
        disp <= out_value;
      when "01" =>
        disp <= acc;
      when "10" =>
        disp <= pc;
      when "11" =>
        disp <= halted & mode & c & z;
      when others =>
        disp <= out_value;
    end case;
  end process p_comb;

end architecture rtl;