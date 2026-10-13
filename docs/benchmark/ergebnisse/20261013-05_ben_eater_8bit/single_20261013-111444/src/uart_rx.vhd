library ieee;
use ieee.std_logic_1164.all;

entity uart_rx is
  generic (
    CLKS_PER_BIT : positive := 868
  );
  port (
    clk   : in  std_logic;
    rst   : in  std_logic;
    rx    : in  std_logic;
    data  : out std_logic_vector(7 downto 0);
    valid : out std_logic
  );
end entity uart_rx;

architecture rtl of uart_rx is
  type state_t is (S_IDLE, S_START, S_DATA, S_STOP);
  signal state : state_t := S_IDLE;
  signal cnt : integer range 0 to 2147483647 := 0;
  signal bit_idx : integer range 0 to 7 := 0;
  signal shift : std_logic_vector(7 downto 0) := (others => '0');
  signal data_r : std_logic_vector(7 downto 0) := (others => '0');
  signal valid_r : std_logic := '0';
begin
  data <= data_r;
  valid <= valid_r;

  process(clk)
    variable half : integer;
  begin
    if rising_edge(clk) then
      if rst = '1' then
        state <= S_IDLE;
        cnt <= 0;
        bit_idx <= 0;
        shift <= (others => '0');
        data_r <= (others => '0');
        valid_r <= '0';
      else
        half := CLKS_PER_BIT / 2;
        if half < 1 then half := 1; end if;
        valid_r <= '0';
        case state is
          when S_IDLE =>
            cnt <= 0;
            if rx = '0' then
              state <= S_START;
            end if;
          when S_START =>
            if cnt >= half - 1 then
              cnt <= 0;
              if rx = '0' then
                state <= S_DATA;
                bit_idx <= 0;
              else
                state <= S_IDLE;
              end if;
            else
              cnt <= cnt + 1;
            end if;
          when S_DATA =>
            if cnt >= CLKS_PER_BIT - 1 then
              cnt <= 0;
              shift(bit_idx) <= rx;
              if bit_idx = 7 then
                state <= S_STOP;
              else
                bit_idx <= bit_idx + 1;
              end if;
            else
              cnt <= cnt + 1;
            end if;
          when S_STOP =>
            if cnt >= CLKS_PER_BIT - 1 then
              cnt <= 0;
              state <= S_IDLE;
              if rx = '1' then
                data_r <= shift;
                valid_r <= '1';
              end if;
            else
              cnt <= cnt + 1;
            end if;
        end case;
      end if;
    end if;
  end process;
end architecture rtl;
