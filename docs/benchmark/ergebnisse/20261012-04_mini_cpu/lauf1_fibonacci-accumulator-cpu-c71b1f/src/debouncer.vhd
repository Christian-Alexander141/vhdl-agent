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
  signal dout_r : std_logic := '0';
  signal rise_r : std_logic := '0';
  signal cnt_r  : natural := 0;
begin

  dout <= dout_r;
  rise <= rise_r;

  -- Synchroner Reset, active high (PROMPT.md).
  -- Zaehlregel: Eingang = dout -> Zaehler 0; sonst +1; bei
  -- DEBOUNCE_CYCLES-1 Uebernahme und Zaehler 0. rise ist genau einen
  -- Takt '1' bei dout-Wechsel 0 -> 1.
  p_seq : process(clk)
  begin
    if rising_edge(clk) then
      if rst = '1' then
        dout_r <= '0';
        rise_r <= '0';
        cnt_r  <= 0;
      else
        if din = dout_r then
          cnt_r  <= 0;
          rise_r <= '0';
        else
          if cnt_r = DEBOUNCE_CYCLES - 1 then
            if dout_r = '0' then
              rise_r <= din;
            else
              rise_r <= '0';
            end if;
            dout_r <= din;
            cnt_r  <= 0;
          else
            cnt_r  <= cnt_r + 1;
            rise_r <= '0';
          end if;
        end if;
      end if;
    end if;
  end process p_seq;

end architecture rtl;