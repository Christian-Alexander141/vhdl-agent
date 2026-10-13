library ieee;
use ieee.std_logic_1164.all;

entity uart_tx is
  generic (
    CLKS_PER_BIT : positive := 868
  );
  port (
    clk      : in  std_logic;
    rst      : in  std_logic;
    data_in  : in  std_logic_vector(7 downto 0);
    send     : in  std_logic;
    tx       : out std_logic;
    busy     : out std_logic
  );
end entity uart_tx;

architecture rtl of uart_tx is
  type state_t is (S_IDLE, S_START, S_DATA, S_STOP);
  signal state : state_t := S_IDLE;
  signal cnt : integer range 0 to 2147483647 := 0;
  signal bit_idx : integer range 0 to 7 := 0;
  signal shreg : std_logic_vector(7 downto 0) := (others => '0');
begin
  -- combinatorial outputs: exact bit lengths
  process(state, shreg, bit_idx)
  begin
    case state is
      when S_IDLE => tx <= '1';
      when S_START => tx <= '0';
      when S_DATA => tx <= shreg(bit_idx);
      when S_STOP => tx <= '1';
    end case;
  end process;
  busy <= '0' when state = S_IDLE else '1';

  process(clk)
  begin
    if rising_edge(clk) then
      if rst = '1' then
        state <= S_IDLE;
        cnt <= 0;
        bit_idx <= 0;
        shreg <= (others => '0');
      else
        case state is
          when S_IDLE =>
            cnt <= 0;
            bit_idx <= 0;
            if send = '1' then
              shreg <= data_in;
              state <= S_START;
            end if;
          when S_START =>
            if cnt >= CLKS_PER_BIT - 1 then
              cnt <= 0;
              state <= S_DATA;
              bit_idx <= 0;
            else
              cnt <= cnt + 1;
            end if;
          when S_DATA =>
            if cnt >= CLKS_PER_BIT - 1 then
              cnt <= 0;
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
            else
              cnt <= cnt + 1;
            end if;
        end case;
      end if;
    end if;
  end process;
end architecture rtl;
