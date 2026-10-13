library ieee;
use ieee.std_logic_1164.all;

entity mini_cpu is
  generic (
    TICK_CYCLES     : positive := 50000000;
    DEBOUNCE_CYCLES : positive := 1000000
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
  component sync2 is
    generic (WIDTH : positive := 1);
    port (
      clk : in  std_logic;
      rst : in  std_logic;
      d   : in  std_logic_vector(WIDTH-1 downto 0);
      q   : out std_logic_vector(WIDTH-1 downto 0)
    );
  end component;
  component debouncer is
    generic (DEBOUNCE_CYCLES : positive := 1000000);
    port (
      clk  : in  std_logic;
      rst  : in  std_logic;
      din  : in  std_logic;
      dout : out std_logic;
      rise : out std_logic
    );
  end component;
  component tick_gen is
    generic (TICK_CYCLES : positive := 50000000);
    port (
      clk  : in  std_logic;
      rst  : in  std_logic;
      tick : out std_logic
    );
  end component;
  component cpu_core is
    port (
      clk       : in  std_logic;
      rst       : in  std_logic;
      go        : in  std_logic;
      out_value : out std_logic_vector(3 downto 0);
      acc       : out std_logic_vector(3 downto 0);
      pc        : out std_logic_vector(3 downto 0);
      z         : out std_logic;
      c         : out std_logic;
      halted    : out std_logic
    );
  end component;
  component display_mux is
    port (
      out_value : in  std_logic_vector(3 downto 0);
      acc       : in  std_logic_vector(3 downto 0);
      pc        : in  std_logic_vector(3 downto 0);
      z         : in  std_logic;
      c         : in  std_logic;
      halted    : in  std_logic;
      mode      : in  std_logic;
      sel       : in  std_logic_vector(1 downto 0);
      disp      : out std_logic_vector(3 downto 0)
    );
  end component;
  signal sw_sync_s  : std_logic_vector(2 downto 0) := (others => '0');
  signal btn_sync_v : std_logic_vector(0 downto 0) := (others => '0');
  signal btn_sync_s : std_logic := '0';
  signal dout_s     : std_logic := '0';
  signal rise_s     : std_logic := '0';
  signal tick_s     : std_logic := '0';
  signal go_s       : std_logic := '0';
  signal mode_s     : std_logic := '0';
  signal sel_s      : std_logic_vector(1 downto 0) := (others => '0');

  signal out_value_s : std_logic_vector(3 downto 0) := (others => '0');
  signal acc_s       : std_logic_vector(3 downto 0) := (others => '0');
  signal pc_s        : std_logic_vector(3 downto 0) := (others => '0');
  signal z_s         : std_logic := '0';
  signal c_s         : std_logic := '0';
  signal halted_s    : std_logic := '0';

  signal disp_s : std_logic_vector(3 downto 0) := (others => '0');
begin
  mode_s <= sw_sync_s(2);
  sel_s  <= sw_sync_s(1 downto 0);
  btn_sync_s <= btn_sync_v(0);

  -- go ist in Automatik der Tick, im Einzelschritt der Schrittimpuls
  go_s <= tick_s when mode_s = '0' else rise_s;

  u_sync_sw : sync2
    generic map (WIDTH => 3)
    port map (
      clk => clk,
      rst => rst,
      d   => sw,
      q   => sw_sync_s
    );

  u_sync_btn : sync2
    generic map (WIDTH => 1)
    port map (
      clk => clk,
      rst => rst,
      d(0) => btn_step,
      q   => btn_sync_v
    );

  u_deb : debouncer
    generic map (DEBOUNCE_CYCLES => DEBOUNCE_CYCLES)
    port map (
      clk  => clk,
      rst  => rst,
      din  => btn_sync_s,
      dout => dout_s,
      rise => rise_s
    );

  u_tick : tick_gen
    generic map (TICK_CYCLES => TICK_CYCLES)
    port map (
      clk  => clk,
      rst  => rst,
      tick => tick_s
    );

  u_core : cpu_core
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

  u_mux : display_mux
    port map (
      out_value => out_value_s,
      acc       => acc_s,
      pc        => pc_s,
      z         => z_s,
      c         => c_s,
      halted    => halted_s,
      mode      => mode_s,
      sel       => sel_s,
      disp      => disp_s
    );

  -- LED-Register: uebernimmt mit jeder Flanke den Anzeigewert
  process(clk)
  begin
    if rising_edge(clk) then
      if rst = '1' then
        led <= (others => '0');
      else
        led <= disp_s;
      end if;
    end if;
  end process;
end architecture rtl;
