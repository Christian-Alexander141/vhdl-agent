library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity data_ram is
  generic (
    ADDR_WIDTH : integer := 4;
    DATA_WIDTH : integer := 4
  );
  port (
    clk  : in  std_logic;
    rst  : in  std_logic;
    we   : in  std_logic;
    addr : in  std_logic_vector(ADDR_WIDTH - 1 downto 0);
    din  : in  std_logic_vector(DATA_WIDTH - 1 downto 0);
    dout : out std_logic_vector(DATA_WIDTH - 1 downto 0)
  );
end entity data_ram;

architecture rtl of data_ram is
  type ram_t is array (0 to 2**ADDR_WIDTH - 1) of std_logic_vector(DATA_WIDTH - 1 downto 0);
  signal mem : ram_t;
begin

  p_mem : process(clk)
  begin
    if rising_edge(clk) then
      if rst = '1' then
        for i in mem'range loop
          mem(i) <= (others => '0');
        end loop;
      elsif we = '1' then
        mem(to_integer(unsigned(addr))) <= din;
      end if;
    end if;
  end process p_mem;

  dout <= mem(to_integer(unsigned(addr)));

end architecture rtl;