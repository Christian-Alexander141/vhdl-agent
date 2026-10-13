library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity memory is
  port (
    clk        : in  std_logic;
    rst        : in  std_logic;
    step_en    : in  std_logic;
    mi         : in  std_logic;
    ri         : in  std_logic;
    bus_in     : in  std_logic_vector(7 downto 0);
    sw_sel     : in  std_logic_vector(1 downto 0);
    load_pulse : in  std_logic;
    load_len   : in  std_logic_vector(4 downto 0);
    load_data  : in  std_logic_vector(127 downto 0);
    ram_out    : out std_logic_vector(7 downto 0);
    mar_out    : out std_logic_vector(3 downto 0)
  );
end entity memory;

architecture rtl of memory is
  type ram_t is array (0 to 15) of std_logic_vector(7 downto 0);
  constant PROG00 : ram_t := (
    x"51", x"4E", x"50", x"E0", x"2E", x"4F", x"1E", x"4D",
    x"1F", x"4E", x"1D", x"70", x"63", x"00", x"00", x"00");
  constant PROG01 : ram_t := (
    x"E0", x"2F", x"74", x"60", x"3F", x"E0", x"80", x"64",
    x"00", x"00", x"00", x"00", x"00", x"00", x"00", x"01");
  constant PROG10 : ram_t := (
    x"1E", x"3C", x"76", x"1D", x"E0", x"F0", x"4E", x"1D",
    x"2F", x"4D", x"60", x"00", x"01", x"00", x"03", x"05");
  constant PROG11 : ram_t := (
    x"5A", x"E0", x"00", x"3F", x"86", x"61", x"E0", x"F0",
    x"00", x"00", x"00", x"00", x"00", x"00", x"00", x"01");
  signal mar : std_logic_vector(3 downto 0) := (others => '0');
  signal ram : ram_t := PROG00;
begin
  mar_out <= mar;
  ram_out <= ram(to_integer(unsigned(mar)));

  process(clk)
    variable n : integer;
  begin
    if rising_edge(clk) then
      if rst = '1' then
        mar <= (others => '0');
        case sw_sel is
          when "00"   => ram <= PROG00;
          when "01"   => ram <= PROG01;
          when "10"   => ram <= PROG10;
          when others => ram <= PROG11;
        end case;
      elsif load_pulse = '1' then
        mar <= (others => '0');
        n := to_integer(unsigned(load_len));
        for i in 0 to 15 loop
          if i < n then
            ram(i) <= load_data(8*i+7 downto 8*i);
          else
            ram(i) <= (others => '0');
          end if;
        end loop;
      else
        if step_en = '1' then
          if mi = '1' then
            mar <= bus_in(3 downto 0);
          end if;
          if ri = '1' then
            ram(to_integer(unsigned(mar))) <= bus_in;
          end if;
        end if;
      end if;
    end if;
  end process;
end architecture rtl;
