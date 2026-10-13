library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity memory is
  port (
    addr_in    : in  std_logic_vector(3 downto 0);
    clk        : in  std_logic;
    data_in    : in  std_logic_vector(7 downto 0);
    mi_en      : in  std_logic;
    prog_data  : in  std_logic_vector(127 downto 0);
    prog_sel   : in  std_logic_vector(1 downto 0);
    prog_valid : in  std_logic;
    ram_out    : out std_logic_vector(7 downto 0);
    ri_en      : in  std_logic;
    rst        : in  std_logic
  );
end entity memory;

architecture rtl of memory is

  type ram_t is array (0 to 15) of std_logic_vector(7 downto 0);

  -- Feste Programme nach PROMPT.md, Adresse 0 .. 15.
  constant PROG_00 : ram_t := (
    x"51", x"4E", x"50", x"E0", x"2E", x"4F", x"1E", x"4D",
    x"1F", x"4E", x"1D", x"70", x"63", x"00", x"00", x"00"
  );
  constant PROG_01 : ram_t := (
    x"E0", x"2F", x"74", x"60", x"3F", x"E0", x"80", x"64",
    x"00", x"00", x"00", x"00", x"00", x"00", x"00", x"01"
  );
  constant PROG_10 : ram_t := (
    x"1E", x"3C", x"76", x"1D", x"E0", x"F0", x"4E", x"1D",
    x"2F", x"4D", x"60", x"00", x"01", x"00", x"03", x"05"
  );
  constant PROG_11 : ram_t := (
    x"5A", x"E0", x"00", x"3F", x"86", x"61", x"E0", x"F0",
    x"00", x"00", x"00", x"00", x"00", x"00", x"00", x"01"
  );

  -- Nach Bitstream-Laden entspricht der Zustand dem Reset mit Programm 00.
  signal mar_reg : std_logic_vector(3 downto 0) := (others => '0');
  signal ram     : ram_t := PROG_00;

begin

  -- Kombinatorisches Lesen: RO = RAM[MAR vor der Flanke].
  ram_out <= ram(to_integer(unsigned(mar_reg)));

  -- MAR + RAM in einer Clock-Domain (clk), synchroner Reset active high.
  -- RI schreibt an die Adresse im MAR vor der Flanke (mar_reg, nicht addr_in).
  p_seq : process(clk)
  begin
    if rising_edge(clk) then
      if rst = '1' then
        mar_reg <= (others => '0');
        case prog_sel is
          when "00" =>
            ram <= PROG_00;
          when "01" =>
            ram <= PROG_01;
          when "10" =>
            ram <= PROG_10;
          when "11" =>
            ram <= PROG_11;
          when others =>
            ram <= PROG_00;
        end case;
      elsif prog_valid = '1' then
        -- Vollstaendiger UART-Rahmen: RAM[0..15] := prog_data, MAR := 0.
        -- Konvention: RAM(i) = prog_data(8*i+7 downto 8*i);
        -- der Lader liefert RAM[n..15] bereits als 0.
        mar_reg <= (others => '0');
        for i in 0 to 15 loop
          ram(i) <= prog_data(8 * i + 7 downto 8 * i);
        end loop;
      else
        if mi_en = '1' then
          mar_reg <= addr_in;
        end if;
        if ri_en = '1' then
          ram(to_integer(unsigned(mar_reg))) <= data_in;
        end if;
      end if;
    end if;
  end process p_seq;

end architecture rtl;