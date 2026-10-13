library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity loader is
  port (
    clk         : in  std_logic;
    rst         : in  std_logic;
    rx_data     : in  std_logic_vector(7 downto 0);
    rx_valid    : in  std_logic;
    mode_uart   : out std_logic;
    loader_busy : out std_logic;
    load_pulse  : out std_logic;
    load_len    : out std_logic_vector(4 downto 0);
    load_data   : out std_logic_vector(127 downto 0)
  );
end entity loader;

architecture rtl of loader is
  type state_t is (S_IDLE, S_LEN1, S_LEN2, S_LEN3, S_PROG, S_TRAIL);
  signal state : state_t := S_IDLE;
  signal lb0, lb1, lb2 : std_logic_vector(7 downto 0) := (others => '0');
  type buf_t is array (0 to 15) of std_logic_vector(7 downto 0);
  signal buf : buf_t := (others => (others => '0'));
  signal frame_len : integer range 0 to 16 := 0;
  signal prog_cnt : integer range 0 to 15 := 0;
  signal trail_idx : integer range 0 to 5 := 0;
  signal mode_r : std_logic := '0';
  signal pulse_r : std_logic := '0';
  signal len_r : std_logic_vector(4 downto 0) := (others => '0');
begin
  mode_uart <= mode_r;
  load_pulse <= pulse_r;
  load_len <= len_r;
  loader_busy <= '1' when (state /= S_IDLE) or (rx_valid = '1') else '0';

  gen_data: for i in 0 to 15 generate
    load_data(8*i+7 downto 8*i) <= buf(i);
  end generate;

  process(clk)
    variable n : integer;
  begin
    if rising_edge(clk) then
      if rst = '1' then
        state <= S_IDLE;
        lb0 <= (others => '0'); lb1 <= (others => '0'); lb2 <= (others => '0');
        buf <= (others => (others => '0'));
        frame_len <= 0;
        prog_cnt <= 0;
        trail_idx <= 0;
        mode_r <= '0';
        pulse_r <= '0';
        len_r <= (others => '0');
      else
        pulse_r <= '0';
        case state is
          when S_IDLE =>
            if rx_valid = '1' then
              lb0 <= rx_data;
              state <= S_LEN1;
            end if;
          when S_LEN1 =>
            if rx_valid = '1' then
              lb1 <= rx_data;
              state <= S_LEN2;
            end if;
          when S_LEN2 =>
            if rx_valid = '1' then
              lb2 <= rx_data;
              state <= S_LEN3;
            end if;
          when S_LEN3 =>
            if rx_valid = '1' then
              -- little endian: lb0 = byte0 (LSB)
              n := to_integer(unsigned(rx_data)) * 16777216
                 + to_integer(unsigned(lb2)) * 65536
                 + to_integer(unsigned(lb1)) * 256
                 + to_integer(unsigned(lb0));
              if n >= 1 and n <= 16 then
                frame_len <= n;
                len_r <= std_logic_vector(to_unsigned(n, 5));
                prog_cnt <= 0;
                state <= S_PROG;
              else
                state <= S_IDLE;
              end if;
            end if;
          when S_PROG =>
            if rx_valid = '1' then
              buf(prog_cnt) <= rx_data;
              if prog_cnt + 1 >= frame_len then
                trail_idx <= 0;
                state <= S_TRAIL;
              else
                prog_cnt <= prog_cnt + 1;
              end if;
            end if;
          when S_TRAIL =>
            if rx_valid = '1' then
              case trail_idx is
                when 0 =>
                  if rx_data = x"53" then trail_idx <= 1; else state <= S_IDLE; end if;
                when 1 =>
                  if rx_data = x"54" then trail_idx <= 2; else state <= S_IDLE; end if;
                when 2 =>
                  if rx_data = x"41" then trail_idx <= 3; else state <= S_IDLE; end if;
                when 3 =>
                  if rx_data = x"52" then trail_idx <= 4; else state <= S_IDLE; end if;
                when 4 =>
                  if rx_data = x"54" then trail_idx <= 5; else state <= S_IDLE; end if;
                when 5 =>
                  if rx_data = x"0A" then
                    pulse_r <= '1';
                    mode_r <= '1';
                    state <= S_IDLE;
                  else
                    state <= S_IDLE;
                  end if;
                when others => state <= S_IDLE;
              end case;
            end if;
        end case;
      end if;
    end if;
  end process;
end architecture rtl;
