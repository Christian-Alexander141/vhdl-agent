library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity mini_cpu is
  generic (
    DEBOUNCE_CYCLES : positive := 1_000_000;
    TICK_CYCLES     : positive := 50_000_000
  );
  port (
    clk      : in  std_logic;
    rst      : in  std_logic;
    btn_step : in  std_logic;
    sw       : in  std_logic_vector(2 downto 0);
    led      : out std_logic_vector(3 downto 0)
  );
end entity mini_cpu;

architecture rtl of mini_cpu is
  signal sw_sync_s     : std_logic_vector(2 downto 0);
  signal btn_din_s     : std_logic_vector(0 downto 0);
  signal btn_sync_s    : std_logic_vector(0 downto 0);
  signal btn_synced    : std_logic;
  signal deb_dout_s    : std_logic;
  signal deb_rise_s    : std_logic;
  signal tick_s        : std_logic;
  signal go_s          : std_logic;
  signal out_value_s   : std_logic_vector(3 downto 0);
  signal acc_s         : std_logic_vector(3 downto 0);
  signal pc_s          : std_logic_vector(3 downto 0);
  signal z_s           : std_logic;
  signal c_s           : std_logic;
  signal halted_s      : std_logic;
  signal disp_s        : std_logic_vector(3 downto 0);
  signal led_r         : std_logic_vector(3 downto 0);
begin

  led <= led_r;

  btn_din_s(0) <= btn_step;
  btn_synced   <= btn_sync_s(0);

  -- PROMPT.md: synchroner Reset active-high (hat Vorrang vor dem
  -- async-Default aus vhdl-synthesis-rules).
  -- sw wird mit zwei Flipflops einsynchronisiert; alle Regeln nutzen
  -- die synchronisierten Werte.
  u_sync_sw : entity work.sync2
    generic map (
      WIDTH => 3
    )
    port map (
      clk  => clk,
      rst  => rst,
      din  => sw,
      dout => sw_sync_s
    );

  -- btn_step wird mit zwei Flipflops einsynchronisiert und dann entprellt.
  u_sync_btn : entity work.sync2
    generic map (
      WIDTH => 1
    )
    port map (
      clk  => clk,
      rst  => rst,
      din  => btn_din_s,
      dout => btn_sync_s
    );

  u_deb : entity work.debouncer
    generic map (
      DEBOUNCE_CYCLES => DEBOUNCE_CYCLES
    )
    port map (
      clk  => clk,
      rst  => rst,
      din  => btn_synced,
      dout => deb_dout_s,
      rise => deb_rise_s
    );

  u_tick : entity work.tick_gen
    generic map (
      TICK_CYCLES => TICK_CYCLES
    )
    port map (
      clk  => clk,
      rst  => rst,
      tick => tick_s
    );

  -- go ist in Automatik der Tick, im Einzelschritt der Schrittimpuls.
  -- Betriebsart = einsynchronisiertes sw(2).
  go_s <= tick_s when sw_sync_s(2) = '0' else deb_rise_s;

  u_core : entity work.cpu_core
    port map (
      clk       => clk,
      rst       => rst,
      go        => go_s,
      out_value => out_value_s,
      acc       => acc_s,
      pc        => pc_s,
      z         => z_s,
      c         => c_s,
      halted    => halted_s
    );

  u_mux : entity work.display_mux
    port map (
      sel       => sw_sync_s(1 downto 0),
      mode      => sw_sync_s(2),
      out_value => out_value_s,
      acc       => acc_s,
      pc        => pc_s,
      z         => z_s,
      c         => c_s,
      halted    => halted_s,
      disp      => disp_s
    );

  -- LED-Register: uebernimmt mit jeder steigenden Taktflanke den
  -- ausgewaehlten Anzeigewert; synchroner Reset loescht auf 0.
  -- Dadurch ist eine Schalteränderung nach genau 3 Flanken sichtbar
  -- (2x sync + 1x led), eine CPU-Registeraenderung eine Flanke spaeter.
  p_led : process(clk)
  begin
    if rising_edge(clk) then
      if rst = '1' then
        led_r <= (others => '0');
      else
        led_r <= disp_s;
      end if;
    end if;
  end process p_led;

end architecture rtl;