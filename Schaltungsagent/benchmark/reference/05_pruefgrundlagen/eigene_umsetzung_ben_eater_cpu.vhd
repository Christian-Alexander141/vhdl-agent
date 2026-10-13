-- Eigene, vom System unabhängige Umsetzung von 05_ben_eater_8bit.md (eine Entity).
-- Dient nur als Gegenprobe für die Aufgabe und die Referenz-Testbench.
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity ben_eater_cpu is
  generic (
    TICK_CYCLES     : positive := 4_000_000;
    DEBOUNCE_CYCLES : positive := 1_000_000;
    CLKS_PER_BIT    : positive := 868
  );
  port (
    clk, rst, btn_step : in std_logic;
    sw                 : in std_logic_vector(3 downto 0);
    led                : out std_logic_vector(3 downto 0);
    uart_rx            : in std_logic;
    uart_tx            : out std_logic
  );
end entity;

architecture rtl of ben_eater_cpu is
  type ram_t is array (0 to 15) of std_logic_vector(7 downto 0);
  type presets_t is array (0 to 3) of ram_t;
  constant PRESETS : presets_t := (
    (x"51", x"4E", x"50", x"E0", x"2E", x"4F", x"1E", x"4D", x"1F", x"4E", x"1D", x"70", x"63", x"00", x"00", x"00"),
    (x"E0", x"2F", x"74", x"60", x"3F", x"E0", x"80", x"64", x"00", x"00", x"00", x"00", x"00", x"00", x"00", x"01"),
    (x"1E", x"3C", x"76", x"1D", x"E0", x"F0", x"4E", x"1D", x"2F", x"4D", x"60", x"00", x"01", x"00", x"03", x"05"),
    (x"5A", x"E0", x"00", x"3F", x"86", x"61", x"E0", x"F0", x"00", x"00", x"00", x"00", x"00", x"00", x"00", x"01"));

  -- Steuersignale (Bitpositionen wie im Original)
  constant C_HLT : natural := 15; constant C_MI : natural := 14; constant C_RI : natural := 13;
  constant C_RO  : natural := 12; constant C_IO : natural := 11; constant C_II : natural := 10;
  constant C_AI  : natural := 9;  constant C_AO : natural := 8;  constant C_EO : natural := 7;
  constant C_SU  : natural := 6;  constant C_BI : natural := 5;  constant C_OI : natural := 4;
  constant C_CE  : natural := 3;  constant C_CO : natural := 2;  constant C_J  : natural := 1;
  constant C_FI  : natural := 0;

  function bit_of(n : natural) return std_logic_vector is
    variable v : std_logic_vector(15 downto 0) := (others => '0');
  begin
    v(n) := '1';
    return v;
  end function;

  function control(opcode : std_logic_vector(3 downto 0); step : natural; c, z : std_logic) return std_logic_vector is
  begin
    if step = 0 then return bit_of(C_MI) or bit_of(C_CO); end if;
    if step = 1 then return bit_of(C_RO) or bit_of(C_II) or bit_of(C_CE); end if;
    case opcode is
      when "0001" =>
        if step = 2 then return bit_of(C_IO) or bit_of(C_MI); end if;
        if step = 3 then return bit_of(C_RO) or bit_of(C_AI); end if;
      when "0010" | "0011" =>
        if step = 2 then return bit_of(C_IO) or bit_of(C_MI); end if;
        if step = 3 then return bit_of(C_RO) or bit_of(C_BI); end if;
        if step = 4 then
          if opcode = "0011" then
            return bit_of(C_EO) or bit_of(C_AI) or bit_of(C_SU) or bit_of(C_FI);
          end if;
          return bit_of(C_EO) or bit_of(C_AI) or bit_of(C_FI);
        end if;
      when "0100" =>
        if step = 2 then return bit_of(C_IO) or bit_of(C_MI); end if;
        if step = 3 then return bit_of(C_AO) or bit_of(C_RI); end if;
      when "0101" =>
        if step = 2 then return bit_of(C_IO) or bit_of(C_AI); end if;
      when "0110" =>
        if step = 2 then return bit_of(C_IO) or bit_of(C_J); end if;
      when "0111" =>
        if step = 2 and c = '1' then return bit_of(C_IO) or bit_of(C_J); end if;
      when "1000" =>
        if step = 2 and z = '1' then return bit_of(C_IO) or bit_of(C_J); end if;
      when "1110" =>
        if step = 2 then return bit_of(C_AO) or bit_of(C_OI); end if;
      when "1111" =>
        if step = 2 then return bit_of(C_HLT); end if;
      when others => null;
    end case;
    return x"0000";
  end function;

  -- Synchronisierer (kein Reset)
  signal sw_s1, sw_s2 : std_logic_vector(3 downto 0) := (others => '0');
  signal bt_s1, bt_s2 : std_logic := '0';
  signal rx_s1, rx_s2, rx_d : std_logic := '1';

  signal db_out, rise : std_logic := '0';
  signal db_cnt : natural range 0 to DEBOUNCE_CYCLES - 1 := 0;
  signal tick_cnt : natural range 0 to TICK_CYCLES - 1 := 0;

  signal ram : ram_t := PRESETS(0);
  signal pc, mar : unsigned(3 downto 0) := (others => '0');
  signal ir, a, b, outr : std_logic_vector(7 downto 0) := (others => '0');
  signal cf, zf, halted, uart_mode : std_logic := '0';
  signal step : natural range 0 to 4 := 0;
  signal led_r : std_logic_vector(3 downto 0) := (others => '0');

  -- UART
  type rx_state_t is (RX_IDLE, RX_START, RX_DATA, RX_STOP);
  signal rx_state : rx_state_t := RX_IDLE;
  signal rx_cnt : natural range 0 to CLKS_PER_BIT - 1 := 0;
  signal rx_bit : natural range 0 to 7 := 0;
  signal rx_shift, rx_byte : std_logic_vector(7 downto 0) := (others => '0');
  signal rx_valid : std_logic := '0';
  signal tx_busy, tx_line : std_logic := '0';
  signal tx_shift : std_logic_vector(9 downto 0) := (others => '1');
  signal tx_cnt : natural range 0 to CLKS_PER_BIT - 1 := 0;
  signal tx_bits : natural range 0 to 10 := 0;

  -- Lader
  type ld_state_t is (L0, L1, L2, L3, LDATA, LSTART);
  signal ld_state : ld_state_t := L0;
  signal ld_len, ld_idx : natural range 0 to 16 := 0;
  signal ld_buf : ram_t := (others => (others => '0'));
  type start_t is array (0 to 5) of std_logic_vector(7 downto 0);
  constant START_SEQ : start_t := (x"53", x"54", x"41", x"52", x"54", x"0A");

  signal cw : std_logic_vector(15 downto 0);
  signal bus_v, alu_r : std_logic_vector(7 downto 0);
  signal alu_c, alu_z, step_en, receiving : std_logic;
begin
  led <= led_r;
  uart_tx <= '1' when tx_busy = '0' else tx_line;

  cw <= control(ir(7 downto 4), step, cf, zf);

  process(all)
    variable sum : unsigned(8 downto 0);
  begin
    if cw(C_SU) = '1' then
      sum := ('0' & unsigned(a)) + ('0' & unsigned(not b)) + 1;
    else
      sum := ('0' & unsigned(a)) + ('0' & unsigned(b));
    end if;
    alu_r <= std_logic_vector(sum(7 downto 0));
    alu_c <= sum(8);
    alu_z <= '1' when sum(7 downto 0) = 0 else '0';
  end process;

  bus_v <= ("0000" & std_logic_vector(pc)) when cw(C_CO) = '1' else
           ram(to_integer(mar)) when cw(C_RO) = '1' else
           ("0000" & ir(3 downto 0)) when cw(C_IO) = '1' else
           a when cw(C_AO) = '1' else
           alu_r when cw(C_EO) = '1' else
           (others => '0');

  receiving <= '0' when ld_state = L0 else '1';
  step_en <= '0' when halted = '1' else
             (not receiving and not (cw(C_OI) and tx_busy)) when uart_mode = '1' else
             rise when sw_s2(1) = '1' else
             '1' when tick_cnt = TICK_CYCLES - 1 else '0';

  -- Synchronisierer laufen immer
  process(clk)
  begin
    if rising_edge(clk) then
      sw_s1 <= sw; sw_s2 <= sw_s1;
      bt_s1 <= btn_step; bt_s2 <= bt_s1;
      rx_s1 <= uart_rx; rx_s2 <= rx_s1; rx_d <= rx_s2;
    end if;
  end process;

  process(clk)
    variable byte_in : std_logic_vector(7 downto 0);
    variable done : boolean;
  begin
    if rising_edge(clk) then
      if rst = '1' then
        db_out <= '0'; db_cnt <= 0; rise <= '0'; tick_cnt <= 0;
        pc <= (others => '0'); mar <= (others => '0'); ir <= (others => '0'); a <= (others => '0');
        b <= (others => '0'); outr <= (others => '0'); cf <= '0'; zf <= '0'; step <= 0;
        halted <= '0'; uart_mode <= '0'; led_r <= (others => '0');
        ram <= PRESETS(to_integer(unsigned(sw_s2(3 downto 2))));
        rx_state <= RX_IDLE; rx_valid <= '0'; tx_busy <= '0'; tx_line <= '1';
        ld_state <= L0; ld_len <= 0; ld_idx <= 0;
      else
        -- Entpreller
        rise <= '0';
        if bt_s2 = db_out then
          db_cnt <= 0;
        elsif db_cnt = DEBOUNCE_CYCLES - 1 then
          db_out <= bt_s2; db_cnt <= 0;
          if bt_s2 = '1' then rise <= '1'; end if;
        else
          db_cnt <= db_cnt + 1;
        end if;
        -- Tick
        if tick_cnt = TICK_CYCLES - 1 then tick_cnt <= 0; else tick_cnt <= tick_cnt + 1; end if;

        -- UART-Empfänger
        rx_valid <= '0';
        case rx_state is
          when RX_IDLE =>
            if rx_d = '1' and rx_s2 = '0' then rx_state <= RX_START; rx_cnt <= 0; end if;
          when RX_START =>
            if rx_cnt = CLKS_PER_BIT / 2 - 1 then
              rx_cnt <= 0;
              if rx_s2 = '0' then rx_state <= RX_DATA; rx_bit <= 0; else rx_state <= RX_IDLE; end if;
            else
              rx_cnt <= rx_cnt + 1;
            end if;
          when RX_DATA =>
            if rx_cnt = CLKS_PER_BIT - 1 then
              rx_cnt <= 0;
              rx_shift <= rx_s2 & rx_shift(7 downto 1);
              if rx_bit = 7 then rx_state <= RX_STOP; else rx_bit <= rx_bit + 1; end if;
            else
              rx_cnt <= rx_cnt + 1;
            end if;
          when RX_STOP =>
            if rx_cnt = CLKS_PER_BIT - 1 then
              rx_state <= RX_IDLE;
              if rx_s2 = '1' then rx_byte <= rx_shift; rx_valid <= '1'; end if;
            else
              rx_cnt <= rx_cnt + 1;
            end if;
        end case;

        -- UART-Sender
        if tx_busy = '1' then
          if tx_cnt = CLKS_PER_BIT - 1 then
            tx_cnt <= 0;
            if tx_bits = 9 then
              tx_busy <= '0';
            else
              tx_bits <= tx_bits + 1;
              tx_line <= tx_shift(tx_bits + 1);
            end if;
          else
            tx_cnt <= tx_cnt + 1;
          end if;
        end if;

        -- Lader
        done := false;
        if rx_valid = '1' then
          byte_in := rx_byte;
          case ld_state is
            when L0 =>
              if unsigned(byte_in) >= 1 and unsigned(byte_in) <= 16 then
                ld_len <= to_integer(unsigned(byte_in)); ld_state <= L1;
              end if;
            when L1 => if byte_in = x"00" then ld_state <= L2; else ld_state <= L0; end if;
            when L2 => if byte_in = x"00" then ld_state <= L3; else ld_state <= L0; end if;
            when L3 =>
              if byte_in = x"00" then ld_state <= LDATA; ld_idx <= 0; else ld_state <= L0; end if;
            when LDATA =>
              ld_buf(ld_idx) <= byte_in;
              if ld_idx + 1 = ld_len then ld_state <= LSTART; ld_idx <= 0; else ld_idx <= ld_idx + 1; end if;
            when LSTART =>
              if byte_in = START_SEQ(ld_idx) then
                if ld_idx = 5 then done := true; ld_state <= L0; else ld_idx <= ld_idx + 1; end if;
              else
                ld_state <= L0;
              end if;
          end case;
        end if;

        if done then
          for i in 0 to 15 loop
            if i < ld_len then ram(i) <= ld_buf(i); else ram(i) <= (others => '0'); end if;
          end loop;
          pc <= (others => '0'); mar <= (others => '0'); ir <= (others => '0'); a <= (others => '0');
          b <= (others => '0'); outr <= (others => '0'); cf <= '0'; zf <= '0'; step <= 0;
          halted <= '0'; uart_mode <= '1';
        elsif step_en = '1' then
          if cw(C_HLT) = '1' then
            halted <= '1';
          else
            if cw(C_RI) = '1' then ram(to_integer(mar)) <= bus_v; end if;
            if cw(C_MI) = '1' then mar <= unsigned(bus_v(3 downto 0)); end if;
            if cw(C_II) = '1' then ir <= bus_v; end if;
            if cw(C_AI) = '1' then a <= bus_v; end if;
            if cw(C_BI) = '1' then b <= bus_v; end if;
            if cw(C_OI) = '1' then
              outr <= bus_v;
              if uart_mode = '1' then
                tx_busy <= '1'; tx_cnt <= 0; tx_bits <= 0;
                tx_shift <= '1' & bus_v & '0'; tx_line <= '0';
              end if;
            end if;
            if cw(C_J) = '1' then pc <= unsigned(bus_v(3 downto 0)); end if;
            if cw(C_CE) = '1' then pc <= pc + 1; end if;
            if cw(C_FI) = '1' then cf <= alu_c; zf <= alu_z; end if;
            if step = 4 then step <= 0; else step <= step + 1; end if;
          end if;
        end if;

        if sw_s2(0) = '1' then led_r <= outr(7 downto 4); else led_r <= outr(3 downto 0); end if;
      end if;
    end if;
  end process;
end architecture;
