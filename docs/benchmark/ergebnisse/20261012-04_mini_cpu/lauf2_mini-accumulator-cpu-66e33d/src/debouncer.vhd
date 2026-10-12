library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity debouncer is
  generic (
    DEBOUNCE_CYCLES : positive := 1_000_000
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

  -- PROMPT.md: synchroner Reset active-high (hat Vorrang vor dem
  -- async-Default aus vhdl-synthesis-rules; Widerspruch steht bereits
  -- in plan/manifest.json open_questions).
  -- Verhalten: Eingang == dout -> Zaehler 0. Sonst hochzaehlen; steht
  -- der Zaehler dabei schon auf DEBOUNCE_CYCLES-1, dout <= din und
  -- Zaehler 0. rise ist '1' genau mit der Flanke, mit der dout von
  -- '0' auf '1' wechselt, sonst '0' (genau einen Takt lang '1').
  p_deb : process(clk)
  begin
    if rising_edge(clk) then
      if rst = '1' then
        dout_r <= '0';
        rise_r <= '0';
        cnt    <= 0;
      elsif din = dout_r then
        cnt    <= 0;
        rise_r <= '0';
      else
        if cnt = DEBOUNCE_CYCLES - 1 then
          if dout_r = '0' and din = '1' then
            rise_r <= '1';
          else
            rise_r <= '0';
          end if;
          dout_r <= din;
          cnt    <= 0;
        else
          cnt    <= cnt + 1;
          rise_r <= '0';
        end if;
      end if;
    end if;
  end process p_deb;

  dout <= dout_r;
  rise <= rise_r;

end architecture rtl;