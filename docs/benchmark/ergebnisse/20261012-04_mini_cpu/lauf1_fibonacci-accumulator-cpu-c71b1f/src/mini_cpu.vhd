library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity mini_cpu is
  generic (
    TICK_CYCLES     : positive := 50_000_000;
    DEBOUNCE_CYCLES : positive := 1_000_000
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

  signal sw_sync   : std_logic_vector(2 downto 0);
  signal btn_d     : std_logic_vector(0 downto 0);
  signal btn_q     : std_logic_vector(0 downto 0);
  signal btn_sync  : std_logic;
  signal db_dout   : std_logic;
  signal step_rise : std_logic;
  signal tick_sig  : std_logic;
  signal go_sig    : std_logic;

  signal out_value_sig : std_logic_vector(3 downto 0);
  signal acc_sig       : std_logic_vector(3 downto 0);
  signal pc_sig        : std_logic_vector(3 downto 0);
  signal z_sig         : std_logic;
  signal c_sig         : std_logic;
  signal halted_sig    : std_logic;

  signal disp_sig : std_logic_vector(3 downto 0);
  signal led_r    : std_logic_vector(3 downto 0);

begin

  btn_d   <= (0 => btn_step);
  btn_sync <= btn_q(0);

  -- go: in Automatik der Tick, im Einzelschritt der Schrittimpuls (R52).
  -- Verwendet einsynchronisierte Werte (R59).
  go_sig <= tick_sig when sw_sync(2) = '0' else step_rise;

  u_sync_sw : entity work.sync2
    generic map (
      WIDTH => 3
    )
    port map (
      clk => clk,
      rst => rst,
      d   => sw,
      q   => sw_sync
    );

  u_sync_btn : entity work.sync2
    generic map (
      WIDTH => 1
    )
    port map (
      clk => clk,
      rst => rst,
      d   => btn_d,
      q   => btn_q
    );

  u_deb : entity work.debouncer
    generic map (
      DEBOUNCE_CYCLES => DEBOUNCE_CYCLES
    )
    port map (
      clk  => clk,
      rst  => rst,
      din  => btn_sync,
      dout => db_dout,
      rise => step_rise
    );

  u_tick : entity work.tick_gen
    generic map (
      TICK_CYCLES => TICK_CYCLES
    )
    port map (
      clk  => clk,
      rst  => rst,
      tick => tick_sig
    );

  u_core : entity work.cpu_core
    port map (
      clk       => clk,
      rst       => rst,
      go        => go_sig,
      out_value => out_value_sig,
      acc       => acc_sig,
      pc        => pc_sig,
      z         => z_sig,
      c         => c_sig,
      halted    => halted_sig
    );

  u_mux : entity work.display_mux
    port map (
      sel       => sw_sync(1 downto 0),
      mode      => sw_sync(2),
      out_value => out_value_sig,
      acc       => acc_sig,
      pc        => pc_sig,
      z         => z_sig,
      c         => c_sig,
      halted    => halted_sig,
      disp      => disp_sig
    );

  -- LED-Register: uebernimmt jede Taktflanke den Anzeigewert (R67),
  -- synchroner Reset active high auf 0 (R71).
  p_led : process(clk)
  begin
    if rising_edge(clk) then
      if rst = '1' then
        led_r <= (others => '0');
      else
        led_r <= disp_sig;
      end if;
    end if;
  end process p_led;

  led <= led_r;

end architecture rtl;