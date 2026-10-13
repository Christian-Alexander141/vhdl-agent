library ieee;
use ieee.std_logic_1164.all;

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
  signal dout_r : std_logic := '0';
  signal rise_r : std_logic := '0';
  signal cnt    : natural := 0;
begin
  process(clk)
  begin
    if rising_edge(clk) then
      if rst = '1' then
        dout_r <= '0';
        rise_r <= '0';
        cnt    <= 0;
      else
        if din = dout_r then
          cnt    <= 0;
          rise_r <= '0';
        else
          if cnt = DEBOUNCE_CYCLES - 1 then
            cnt <= 0;
            if dout_r = '0' and din = '1' then
              rise_r <= '1';
            else
              rise_r <= '0';
            end if;
            dout_r <= din;
          else
            cnt    <= cnt + 1;
            rise_r <= '0';
          end if;
        end if;
      end if;
    end if;
  end process;

  dout <= dout_r;
  rise <= rise_r;
end architecture rtl;
