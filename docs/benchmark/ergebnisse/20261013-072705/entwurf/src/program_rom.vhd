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
  type rom_t is array (0 to 15) of std_logic_vector(7 downto 0);
  constant ROM : rom_t := (
    0  => x"11",
    1  => x"30",
    2  => x"31",
    3  => x"E0",
    4  => x"20",
    5  => x"41",
    6  => x"DE",
    7  => x"32",
    8  => x"21",
    9  => x"30",
    10 => x"22",
    11 => x"31",
    12 => x"E0",
    13 => x"B4",
    14 => x"F0",
    15 => x"00"
  );
begin
  data <= ROM(to_integer(unsigned(addr)));
end architecture rtl;
