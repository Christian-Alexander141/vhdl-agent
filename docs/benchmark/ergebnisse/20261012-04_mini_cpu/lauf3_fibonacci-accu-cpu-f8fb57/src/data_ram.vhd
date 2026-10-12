library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity data_ram is
  generic (
    ADDR_WIDTH : integer := 4;
    DATA_WIDTH : integer := 4
  );
  port (
    addr  : in  std_logic_vector(ADDR_WIDTH-1 downto 0);
    clk   : in  std_logic;
    rst   : in  std_logic;
    rdata : out std_logic_vector(DATA_WIDTH-1 downto 0);
    wdata : in  std_logic_vector(DATA_WIDTH-1 downto 0);
    we    : in  std_logic
  );
end entity data_ram;

architecture rtl of data_ram is
  type ram_t is array (0 to 2**ADDR_WIDTH - 1) of std_logic_vector(DATA_WIDTH-1 downto 0);
  signal mem : ram_t := (others => (others => '0'));
begin

  p_write: process(clk)
  begin
    if rising_edge(clk) then
      if rst = '1' then
        mem <= (others => (others => '0'));
      elsif we = '1' then
        mem(to_integer(unsigned(addr))) <= wdata;
      end if;
    end if;
  end process p_write;

  rdata <= mem(to_integer(unsigned(addr)));

end architecture rtl;