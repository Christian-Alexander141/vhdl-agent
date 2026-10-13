library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity uart_tx is
  generic (
    CLKS_PER_BIT : positive := 868
  );
  port (
    clk     : in  std_logic;
    data_in : in  std_logic_vector(7 downto 0);
    rst     : in  std_logic;
    send_en : in  std_logic;
    busy    : out std_logic;
    tx_out  : out std_logic
  );
end entity uart_tx;

architecture rtl of uart_tx is
  type state_t is (IDLE, TX_START, TX_DATA, TX_STOP);
  signal state    : state_t := IDLE;
  signal cnt      : integer range 0 to 2147483647 := 0;
  signal bit_idx  : integer range 0 to 7 := 0;
  signal shift    : std_logic_vector(7 downto 0) := (others => '0');
  signal send_prev : std_logic := '0';
begin

  -- busy ist '1' waehrend des gesamten Rahmens (Start + 8 Daten + Stopp).
  -- Es wird ueber das registrierte state-Signal gebildet und ist daher
  -- erst den Takt nach send_en aktiv: Der OI-Mikroschritt, der das Senden
  -- ausloest, wird noch ausgefuehrt, danach sperrt clock_ctrl (oi+busy).
  busy <= '0' when state = IDLE else '1';

  -- Moore-Ausgaenge: tx_out haengt nur von registrierten Signalen ab,
  -- daher glitchfrei und exakt CLKS_PER_BIT Takte je Bit.
  p_out : process(all)
  begin
    case state is
      when IDLE =>
        tx_out <= '1';
      when TX_START =>
        tx_out <= '0';
      when TX_DATA =>
        tx_out <= shift(bit_idx);
      when TX_STOP =>
        tx_out <= '1';
    end case;
  end process p_out;

  p_seq : process(clk)
  begin
    if rising_edge(clk) then
      if rst = '1' then
        state     <= IDLE;
        cnt       <= 0;
        bit_idx   <= 0;
        shift     <= (others => '0');
        send_prev <= '0';
      else
        case state is
          when IDLE =>
            if send_en = '1' and send_prev = '0' then
              -- Steigende Flanke von send_en: neues Zeichen latchen.
              -- Flankenauswertung verhindert Doppelstart, wenn send_en
              -- als Pegel (OI & Modus) ueber die Sperrzeit hinaus ansteht.
              shift   <= data_in;
              state   <= TX_START;
              cnt     <= 0;
            end if;
            send_prev <= send_en;

          when TX_START =>
            send_prev <= send_en;
            if cnt = CLKS_PER_BIT - 1 then
              state   <= TX_DATA;
              cnt     <= 0;
              bit_idx <= 0;
            else
              cnt <= cnt + 1;
            end if;

          when TX_DATA =>
            send_prev <= send_en;
            if cnt = CLKS_PER_BIT - 1 then
              if bit_idx = 7 then
                state <= TX_STOP;
                cnt   <= 0;
              else
                bit_idx <= bit_idx + 1;
                cnt     <= 0;
              end if;
            else
              cnt <= cnt + 1;
            end if;

          when TX_STOP =>
            send_prev <= send_en;
            if cnt = CLKS_PER_BIT - 1 then
              state <= IDLE;
              cnt   <= 0;
            else
              cnt <= cnt + 1;
            end if;
        end case;
      end if;
    end if;
  end process p_seq;

end architecture rtl;