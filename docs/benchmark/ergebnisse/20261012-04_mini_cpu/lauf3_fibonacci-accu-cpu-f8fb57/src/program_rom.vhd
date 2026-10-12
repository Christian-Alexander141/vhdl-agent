library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity program_rom is
  port (
    addr : in  std_logic_vector(3 downto 0);
    data : out std_logic_vector(7 downto 0)
  );
end entity program_rom;

architecture rtl of program_rom is
begin

  p_comb: process(all)
  begin
    case addr is
      when x"0"   => data <= x"11";
      when x"1"   => data <= x"30";
      when x"2"   => data <= x"31";
      when x"3"   => data <= x"E0";
      when x"4"   => data <= x"20";
      when x"5"   => data <= x"41";
      when x"6"   => data <= x"DE";
      when x"7"   => data <= x"32";
      when x"8"   => data <= x"21";
      when x"9"   => data <= x"30";
      when x"A"   => data <= x"22";
      when x"B"   => data <= x"31";
      when x"C"   => data <= x"E0";
      when x"D"   => data <= x"B4";
      when x"E"   => data <= x"F0";
      when x"F"   => data <= x"00";
      when others => data <= x"00";
    end case;
  end process p_comb;

end architecture rtl;