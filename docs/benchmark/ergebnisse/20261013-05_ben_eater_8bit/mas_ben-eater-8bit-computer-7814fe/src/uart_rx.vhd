library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity uart_rx is
  generic (
    CLKS_PER_BIT : positive := 868
  );
  port (
    clk        : in  std_logic;
    rst        : in  std_logic;
    rx_in      : in  std_logic;
    data_out   : out std_logic_vector(7 downto 0);
    data_valid : out std_logic
  );
end entity uart_rx;

architecture rtl of uart_rx is

  type state_t is (S_IDLE, S_START, S_DATA, S_STOP, S_DONE);

  signal state    : state_t := S_IDLE;
  signal clk_cnt  : natural := 0;
  signal bit_idx  : natural range 0 to 7 := 0;
  signal shifter  : std_logic_vector(7 downto 0) := (others => '0');

begin

  -- UART-Empfaenger 8N1, LSB zuerst.
  -- Startbeginn an fallender Flanke (in IDLE: rx_in = '0').
  -- Abtastung jeweils in Bitmitte; Zeichen mit falschem
  -- Startbit (Mitte /= '0') oder Stoppbit (/= '1') wird verworfen.
  -- data_valid ist genau einen Takt lang '1', data_out haelt
  -- das letzte gueltige Zeichen. Synchroner Reset, active high.
  p_seq: process(clk)
    constant START_SAMPLE : natural := (CLKS_PER_BIT - 1) / 2;
  begin
    if rising_edge(clk) then
      if rst = '1' then
        state      <= S_IDLE;
        clk_cnt    <= 0;
        bit_idx    <= 0;
        shifter    <= (others => '0');
        data_out   <= (others => '0');
        data_valid <= '0';
      else
        data_valid <= '0';
        case state is
          when S_IDLE =>
            clk_cnt <= 0;
            bit_idx <= 0;
            if rx_in = '0' then
              state <= S_START;
            end if;

          when S_START =>
            if clk_cnt = START_SAMPLE then
              clk_cnt <= 0;
              if rx_in = '0' then
                state   <= S_DATA;
                bit_idx <= 0;
              else
                state <= S_IDLE;
              end if;
            else
              clk_cnt <= clk_cnt + 1;
            end if;

          when S_DATA =>
            if clk_cnt = CLKS_PER_BIT - 1 then
              clk_cnt <= 0;
              shifter(bit_idx) <= rx_in;
              if bit_idx = 7 then
                state <= S_STOP;
              else
                bit_idx <= bit_idx + 1;
              end if;
            else
              clk_cnt <= clk_cnt + 1;
            end if;

          when S_STOP =>
            if clk_cnt = CLKS_PER_BIT - 1 then
              clk_cnt <= 0;
              if rx_in = '1' then
                state <= S_DONE;
              else
                state <= S_IDLE;
              end if;
            else
              clk_cnt <= clk_cnt + 1;
            end if;

          when S_DONE =>
            data_out   <= shifter;
            data_valid <= '1';
            state      <= S_IDLE;

          when others =>
            state <= S_IDLE;
        end case;
      end if;
    end if;
  end process p_seq;

end architecture rtl;