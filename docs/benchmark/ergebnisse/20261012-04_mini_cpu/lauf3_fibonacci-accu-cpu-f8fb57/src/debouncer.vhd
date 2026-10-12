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
    d_in : in  std_logic;
    dout : out std_logic;
    rise : out std_logic
  );
end entity debouncer;

architecture rtl of debouncer is

  -- Bitbreite, um Zaehlerstaende 0 .. DEBOUNCE_CYCLES-1 zu halten.
  function cnt_bits(n : positive) return positive is
    variable bits  : positive := 1;
    variable limit : positive := 2;
  begin
    if n <= 1 then
      return 1;
    end if;
    while limit < n loop
      limit := limit * 2;
      bits  := bits + 1;
    end loop;
    return bits;
  end function cnt_bits;

  constant CNT_WIDTH : positive := cnt_bits(DEBOUNCE_CYCLES);
  constant CNT_MAX   : unsigned(CNT_WIDTH-1 downto 0) :=
    to_unsigned(DEBOUNCE_CYCLES - 1, CNT_WIDTH);

  signal cnt    : unsigned(CNT_WIDTH-1 downto 0) := (others => '0');
  signal dout_r : std_logic := '0';
  signal rise_r : std_logic := '0';

begin

  dout <= dout_r;
  rise <= rise_r;

  -- Entpreller mit synchronem aktivem High-Reset (reset_concept=sync_active_high).
  -- d_in == dout_r       -> Zaehler 0, rise '0'.
  -- d_in /= dout_r       -> Zaehler +1; steht er schon auf DEBOUNCE_CYCLES-1,
  --                         uebernimmt dout_r den Eingang, Zaehler 0.
  -- rise ist '1' genau eine Flanke lang, wenn dout_r dabei von '0' auf '1' wechselt.
  p_seq: process(clk)
  begin
    if rising_edge(clk) then
      if rst = '1' then
        dout_r <= '0';
        rise_r <= '0';
        cnt    <= (others => '0');
      else
        if d_in = dout_r then
          cnt    <= (others => '0');
          rise_r <= '0';
        else
          if cnt = CNT_MAX then
            if dout_r = '0' and d_in = '1' then
              rise_r <= '1';
            else
              rise_r <= '0';
            end if;
            dout_r <= d_in;
            cnt    <= (others => '0');
          else
            cnt    <= cnt + 1;
            rise_r <= '0';
          end if;
        end if;
      end if;
    end if;
  end process p_seq;

end architecture rtl;