library ieee;
use ieee.std_logic_1164.all;

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
  signal sw_s : std_logic_vector(3 downto 0);
  signal btn_in_v, btn_out_v : std_logic_vector(0 downto 0);
  signal rx_in_v, rx_out_v : std_logic_vector(0 downto 0);
  signal btn_s : std_logic;
  signal rx_s : std_logic;
  signal btn_dout : std_logic;
  signal btn_rise : std_logic;

  signal mode_uart : std_logic;
  signal loader_busy : std_logic;
  signal load_pulse : std_logic;
  signal load_len : std_logic_vector(4 downto 0);
  signal load_data : std_logic_vector(127 downto 0);

  signal tick_i : std_logic;
  signal step_en : std_logic;
  signal halted : std_logic;

  signal pc_out : std_logic_vector(3 downto 0);
  signal mar_out : std_logic_vector(3 downto 0);
  signal ram_out : std_logic_vector(7 downto 0);
  signal ir_q, a_q, b_q, out_q : std_logic_vector(7 downto 0);
  signal alu_res : std_logic_vector(7 downto 0);
  signal flag_c, flag_z : std_logic;

  signal s_hlt, s_mi, s_ri, s_ro, s_io, s_ii, s_ai, s_ao,
         s_eo, s_su, s_bi, s_oi, s_ce, s_co, s_j, s_fi : std_logic;

  signal bus_v : std_logic_vector(7 downto 0);

  signal rx_data : std_logic_vector(7 downto 0);
  signal rx_valid : std_logic;
  signal tx_busy : std_logic;
  signal tx_send : std_logic;
  signal tx_line : std_logic;
  signal led_r : std_logic_vector(3 downto 0) := (others => '0');

  signal en_ii, en_ai, en_bi, en_oi : std_logic;
begin
  led <= led_r;
  uart_tx <= tx_line;

  u_sw_sync: entity work.input_sync
    generic map (WIDTH => 4, INIT => '0')
    port map (clk => clk, d_in => sw, d_out => sw_s);

  u_btn_sync: entity work.input_sync
    generic map (WIDTH => 1, INIT => '0')
    port map (clk => clk, d_in => btn_in_v, d_out => btn_out_v);
  -- btn sync wiring via intermediate: input is btn_step
  -- (use explicit mapping to avoid confusion)
  btn_in_v(0) <= btn_step;
  btn_s <= btn_out_v(0);

  u_rx_sync: entity work.input_sync
    generic map (WIDTH => 1, INIT => '1')
    port map (clk => clk, d_in => rx_in_v, d_out => rx_out_v);
  rx_in_v(0) <= uart_rx;
  rx_s <= rx_out_v(0);

  u_deb: entity work.debouncer
    generic map (DEBOUNCE_CYCLES => DEBOUNCE_CYCLES)
    port map (clk => clk, rst => rst, din => btn_s, dout => btn_dout, rise => btn_rise);

  u_rx: entity work.uart_rx
    generic map (CLKS_PER_BIT => CLKS_PER_BIT)
    port map (clk => clk, rst => rst, rx => rx_s, data => rx_data, valid => rx_valid);

  u_loader: entity work.loader
    port map (clk => clk, rst => rst, rx_data => rx_data, rx_valid => rx_valid,
              mode_uart => mode_uart, loader_busy => loader_busy,
              load_pulse => load_pulse, load_len => load_len, load_data => load_data);

  u_clk: entity work.clock_ctrl
    generic map (TICK_CYCLES => TICK_CYCLES)
    port map (clk => clk, rst => rst, mode_uart => mode_uart, sw1 => sw_s(1),
              rise_in => btn_rise, halted => halted, loader_busy => loader_busy,
              oi_active => s_oi, tx_busy => tx_busy, tick => tick_i, step_en => step_en);

  u_pc: entity work.program_counter
    port map (clk => clk, rst => rst, step_en => step_en, ce => s_ce, j => s_j,
              j_data => bus_v(3 downto 0), clr => load_pulse, pc_out => pc_out);

  en_ii <= s_ii and step_en;
  en_ai <= s_ai and step_en;
  en_bi <= s_bi and step_en;
  en_oi <= s_oi and step_en;

  u_ir: entity work.register8
    port map (clk => clk, rst => rst, en => en_ii, clr => load_pulse, d => bus_v, q => ir_q);

  u_a: entity work.register8
    port map (clk => clk, rst => rst, en => en_ai, clr => load_pulse, d => bus_v, q => a_q);

  u_b: entity work.register8
    port map (clk => clk, rst => rst, en => en_bi, clr => load_pulse, d => bus_v, q => b_q);

  u_out: entity work.register8
    port map (clk => clk, rst => rst, en => en_oi, clr => load_pulse, d => bus_v, q => out_q);

  u_alu: entity work.alu
    port map (clk => clk, rst => rst, step_en => step_en, a => a_q, b => b_q,
              su => s_su, fi => s_fi, clr => load_pulse, result => alu_res,
              flag_c => flag_c, flag_z => flag_z);

  u_mem: entity work.memory
    port map (clk => clk, rst => rst, step_en => step_en, mi => s_mi, ri => s_ri,
              bus_in => bus_v, sw_sel => sw_s(3 downto 2), load_pulse => load_pulse,
              load_len => load_len, load_data => load_data, ram_out => ram_out, mar_out => mar_out);

  u_ctrl: entity work.control_unit
    port map (clk => clk, rst => rst, step_en => step_en, opcode => ir_q(7 downto 4),
              flag_c => flag_c, flag_z => flag_z, clr => load_pulse,
              hlt => s_hlt, mi => s_mi, ri => s_ri, ro => s_ro, io => s_io, ii => s_ii,
              ai => s_ai, ao => s_ao, eo => s_eo, su => s_su, bi => s_bi, oi => s_oi,
              ce => s_ce, co => s_co, j => s_j, fi => s_fi, halted => halted);

  process(s_co, s_ro, s_io, s_ao, s_eo, pc_out, ram_out, ir_q, a_q, alu_res)
  begin
    if s_co = '1' then
      bus_v <= "0000" & pc_out;
    elsif s_ro = '1' then
      bus_v <= ram_out;
    elsif s_io = '1' then
      bus_v <= "0000" & ir_q(3 downto 0);
    elsif s_ao = '1' then
      bus_v <= a_q;
    elsif s_eo = '1' then
      bus_v <= alu_res;
    else
      bus_v <= (others => '0');
    end if;
  end process;

  tx_send <= mode_uart and step_en and s_oi;

  u_tx: entity work.uart_tx
    generic map (CLKS_PER_BIT => CLKS_PER_BIT)
    port map (clk => clk, rst => rst, data_in => bus_v, send => tx_send, tx => tx_line, busy => tx_busy);

  process(clk)
  begin
    if rising_edge(clk) then
      if rst = '1' then
        led_r <= (others => '0');
      else
        if sw_s(0) = '0' then
          led_r <= out_q(3 downto 0);
        else
          led_r <= out_q(7 downto 4);
        end if;
      end if;
    end if;
  end process;

end architecture rtl;
