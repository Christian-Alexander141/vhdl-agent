library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity input_sync is
  generic (
    INIT  : integer := 0;
    WIDTH : integer := 1
  );
  port (
    clk      : in  std_logic;
    data_in  : in  std_logic_vector(WIDTH - 1 downto 0);
    data_out : out std_logic_vector(WIDTH - 1 downto 0)
  );
end entity input_sync;

architecture rtl of input_sync is
  constant C_INIT : std_logic_vector(WIDTH - 1 downto 0) :=
    std_logic_vector(to_unsigned(INIT, WIDTH));
  signal sync1 : std_logic_vector(WIDTH - 1 downto 0) := C_INIT;
  signal sync2 : std_logic_vector(WIDTH - 1 downto 0) := C_INIT;
begin

  p_sync : process(clk)
  begin
    if rising_edge(clk) then
      sync1 <= data_in;
      sync2 <= sync1;
    end if;
  end process p_sync;

  data_out <= sync2;

end architecture rtl;