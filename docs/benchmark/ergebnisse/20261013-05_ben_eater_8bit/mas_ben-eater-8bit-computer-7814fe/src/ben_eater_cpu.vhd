library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity ben_eater_cpu is
  generic (
    TICK_CYCLES     : positive := 4000000;
    DEBOUNCE_CYCLES : positive := 1000000;
    CLKS_PER_BIT    : positive := 868
  );
  port (
    clk      : in  std_logic;
    rst      : in  std_logic;
    btn_step : in  std_logic;
    sw       : in  std_logic_vector(3 downto 0);
    led      : out std_logic_vector(3 downto 0);
    uart_rx  : in  std_logic;
    uart_tx  : out std_logic
  );
end entity ben_eater_cpu;

architecture rtl of ben_eater_cpu is
  -- Synchronisierte Eingaenge
  signal sw_sync_vec   : std_logic_vector(3 downto 0);
  signal btn_in_vec    : std_logic_vector(0 downto 0);
  signal btn_sync_vec  : std_logic_vector(0 downto 0);
  signal btn_synced    : std_logic;
  signal rx_in_vec     : std_logic_vector(0 downto 0);
  signal rx_sync_vec   : std_logic_vector(0 downto 0);
  signal uart_synced   : std_logic;

  -- Entpreller / Takt
  signal db_rise       : std_logic;
  signal db_dout       : std_logic;
  signal step_enable   : std_logic;

  -- Steuerwerk
  signal s_ai      : std_logic;
  signal s_ao      : std_logic;
  signal s_bi      : std_logic;
  signal s_ce      : std_logic;
  signal s_co      : std_logic;
  signal s_eo      : std_logic;
  signal s_fi      : std_logic;
  signal s_hlt     : std_logic;
  signal s_ii      : std_logic;
  signal s_io      : std_logic;
  signal s_ri      : std_logic;
  signal s_ro      : std_logic;
  signal s_su      : std_logic;
  signal s_j       : std_logic;
  signal s_mi      : std_logic;
  signal s_oi      : std_logic;
  signal s_halted  : std_logic;

  -- Gegatete Freigaben (nur bei step_enable wirksam)
  signal ce_g : std_logic;
  signal j_g  : std_logic;
  signal mi_g : std_logic;
  signal ri_g : std_logic;
  signal ai_g : std_logic;
  signal bi_g : std_logic;
  signal oi_g : std_logic;
  signal ii_g : std_logic;
  signal fi_g : std_logic;

  -- Datenpfad
  signal bus_sig     : std_logic_vector(7 downto 0);
  signal pc_val      : std_logic_vector(3 downto 0);
  signal ram_out_sig : std_logic_vector(7 downto 0);
  signal ir_val      : std_logic_vector(7 downto 0);
  signal a_val       : std_logic_vector(7 downto 0);
  signal b_val       : std_logic_vector(7 downto 0);
  signal out_val     : std_logic_vector(7 downto 0);
  signal alu_res     : std_logic_vector(7 downto 0);
  signal flag_c      : std_logic;
  signal flag_z      : std_logic;

  -- UART / Lader
  signal rx_data_sig    : std_logic_vector(7 downto 0);
  signal rx_valid_sig   : std_logic;
  signal loader_busy    : std_logic;
  signal prog_data_sig  : std_logic_vector(127 downto 0);
  signal prog_valid_sig : std_logic;
  signal uart_mode_sig  : std_logic;
  signal tx_busy_sig    : std_logic;
  signal tx_send_en     : std_logic;

  -- CPU-Clear bei UART-Rahmen (rst oder prog_valid)
  signal cpu_rst : std_logic;
begin

  cpu_rst <= rst or prog_valid_sig;

  -- Eingangssynchronisierer (laufen immer, kein Reset)
  btn_in_vec(0) <= btn_step;
  rx_in_vec(0)  <= uart_rx;

  u_sw_sync: entity work.input_sync
    generic map (
      INIT  => 0,
      WIDTH => 4
    )
    port map (
      clk      => clk,
      data_in  => sw,
      data_out => sw_sync_vec
    );

  u_btn_sync: entity work.input_sync
    generic map (
      INIT  => 0,
      WIDTH => 1
    )
    port map (
      clk      => clk,
      data_in  => btn_in_vec,
      data_out => btn_sync_vec
    );

  u_rx_sync: entity work.input_sync
    generic map (
      INIT  => 1,
      WIDTH => 1
    )
    port map (
      clk      => clk,
      data_in  => rx_in_vec,
      data_out => rx_sync_vec
    );

  btn_synced  <= btn_sync_vec(0);
  uart_synced <= rx_sync_vec(0);

  u_deb: entity work.debouncer
    generic map (
      DEBOUNCE_CYCLES => DEBOUNCE_CYCLES
    )
    port map (
      clk  => clk,
      rst  => rst,
      din  => btn_synced,
      dout => db_dout,
      rise => db_rise
    );

  u_clk: entity work.clock_ctrl
    generic map (
      TICK_CYCLES => TICK_CYCLES
    )
    port map (
      clk         => clk,
      halted      => s_halted,
      loader_busy => loader_busy,
      oi_active   => s_oi,
      rst         => rst,
      step_rise   => db_rise,
      sw_step     => sw_sync_vec(1),
      tx_busy     => tx_busy_sig,
      uart_mode   => uart_mode_sig,
      step_enable => step_enable,
      tick        => open
    );

  u_ctrl: entity work.control_unit
    port map (
      ai          => s_ai,
      ao          => s_ao,
      bi          => s_bi,
      ce          => s_ce,
      clear       => prog_valid_sig,
      clk         => clk,
      co          => s_co,
      eo          => s_eo,
      fi          => s_fi,
      flag_c      => flag_c,
      flag_z      => flag_z,
      halted      => s_halted,
      hlt         => s_hlt,
      ii          => s_ii,
      io          => s_io,
      opcode      => ir_val(7 downto 4),
      ri          => s_ri,
      ro          => s_ro,
      rst         => rst,
      step_enable => step_enable,
      su          => s_su,
      j_load      => s_j,
      mi          => s_mi,
      oi          => s_oi
    );

  -- Freigaben gelten nur im ausgefuehrten Mikroschritt
  ce_g <= s_ce and step_enable;
  j_g  <= s_j and step_enable;
  mi_g <= s_mi and step_enable;
  ri_g <= s_ri and step_enable;
  ai_g <= s_ai and step_enable;
  bi_g <= s_bi and step_enable;
  oi_g <= s_oi and step_enable;
  ii_g <= s_ii and step_enable;
  fi_g <= s_fi and step_enable;

  -- Bus-Multiplexer (keine Tri-State)
  p_bus: process(all)
  begin
    if s_co = '1' then
      bus_sig <= "0000" & pc_val;
    elsif s_ro = '1' then
      bus_sig <= ram_out_sig;
    elsif s_io = '1' then
      bus_sig <= "0000" & ir_val(3 downto 0);
    elsif s_ao = '1' then
      bus_sig <= a_val;
    elsif s_eo = '1' then
      bus_sig <= alu_res;
    else
      bus_sig <= (others => '0');
    end if;
  end process p_bus;

  u_pc: entity work.program_counter
    port map (
      ce        => ce_g,
      clk       => clk,
      data_in   => bus_sig(3 downto 0),
      j_load    => j_g,
      rst       => cpu_rst,
      count_out => pc_val
    );

  u_mem: entity work.memory
    port map (
      addr_in    => bus_sig(3 downto 0),
      clk        => clk,
      data_in    => bus_sig,
      mi_en      => mi_g,
      prog_data  => prog_data_sig,
      prog_sel   => sw_sync_vec(3 downto 2),
      prog_valid => prog_valid_sig,
      ram_out    => ram_out_sig,
      ri_en      => ri_g,
      rst        => rst
    );

  u_reg_a: entity work.register8
    port map (
      clk      => clk,
      data_in  => bus_sig,
      data_out => a_val,
      load_en  => ai_g,
      rst      => cpu_rst
    );

  u_reg_b: entity work.register8
    port map (
      clk      => clk,
      data_in  => bus_sig,
      data_out => b_val,
      load_en  => bi_g,
      rst      => cpu_rst
    );

  u_reg_out: entity work.register8
    port map (
      clk      => clk,
      data_in  => bus_sig,
      data_out => out_val,
      load_en  => oi_g,
      rst      => cpu_rst
    );

  u_reg_ir: entity work.register8
    port map (
      clk      => clk,
      data_in  => bus_sig,
      data_out => ir_val,
      load_en  => ii_g,
      rst      => cpu_rst
    );

  u_alu: entity work.alu
    port map (
      a_in       => a_val,
      b_in       => b_val,
      clk        => clk,
      carry_out  => flag_c,
      fi_en      => fi_g,
      rst        => cpu_rst,
      result_out => alu_res,
      sub        => s_su,
      zero_out   => flag_z
    );

  u_rxe: entity work.uart_rx
    generic map (
      CLKS_PER_BIT => CLKS_PER_BIT
    )
    port map (
      clk        => clk,
      rst        => rst,
      rx_in      => uart_synced,
      data_out   => rx_data_sig,
      data_valid => rx_valid_sig
    );

  u_loader: entity work.loader
    port map (
      clk         => clk,
      rst         => rst,
      rx_data     => rx_data_sig,
      rx_valid    => rx_valid_sig,
      loader_busy => loader_busy,
      prog_data   => prog_data_sig,
      prog_valid  => prog_valid_sig,
      uart_mode   => uart_mode_sig
    );

  -- Im UART-Modus sendet jeder ausgefuehrte OI-Mikroschritt den neuen
  -- OUT-Wert (Bus). Im Board-Modus bleibt send_en '0', uart_tx '1'.
  tx_send_en <= uart_mode_sig and s_oi and step_enable;

  u_txe: entity work.uart_tx
    generic map (
      CLKS_PER_BIT => CLKS_PER_BIT
    )
    port map (
      clk     => clk,
      data_in => bus_sig,
      rst     => rst,
      send_en => tx_send_en,
      busy    => tx_busy_sig,
      tx_out  => uart_tx
    );

  -- LED-Register: jeden Takt das per sw(0) gewaehlte Halbbyte von OUT
  p_led: process(clk)
  begin
    if rising_edge(clk) then
      if rst = '1' then
        led <= (others => '0');
      else
        if sw_sync_vec(0) = '0' then
          led <= out_val(3 downto 0);
        else
          led <= out_val(7 downto 4);
        end if;
      end if;
    end if;
  end process p_led;

end architecture rtl;