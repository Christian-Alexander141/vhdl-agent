library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity debouncer is
  generic (
    DEBOUNCE_CYCLES : positive := 1000000
  );
  port (
    clk  : in  std_logic;
    rst  : in  std_logic;
    din  : in  std_logic;
    dout : out std_logic;
    rise : out std_logic
  );
end entity debouncer;

architecture rtl of debouncer is
  signal r_dout : std_logic := '0';
  signal r_rise : std_logic := '0';
  signal cnt    : natural range 0 to 2147483647 := 0;
begin

  dout <= r_dout;
  rise <= r_rise;

  p_seq : process(clk)
  begin
    if rising_edge(clk) then
      if rst = '1' then
        r_dout <= '0';
        r_rise <= '0';
        cnt    <= 0;
      else
        if din = r_dout then
          cnt    <= 0;
          r_rise <= '0';
        else
          if cnt = DEBOUNCE_CYCLES - 1 then
            cnt <= 0;
            if r_dout = '0' then
              -- din muss hier '1' sein (din /= dout)
              r_dout <= din;
              r_rise <= '1';
            else
              r_dout <= din;
              r_rise <= '0';
            end if;
          else
            cnt    <= cnt + 1;
            r_rise <= '0';
          end if;
        end if;
      end if;
    end if;
  end process p_seq;

end architecture rtl;