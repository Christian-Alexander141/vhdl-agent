library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity loader is
  port (
    clk         : in  std_logic;
    rst         : in  std_logic;
    rx_data     : in  std_logic_vector(7 downto 0);
    rx_valid    : in  std_logic;
    loader_busy : out std_logic;
    prog_data   : out std_logic_vector(127 downto 0);
    prog_valid  : out std_logic;
    uart_mode   : out std_logic
  );
end entity loader;

architecture rtl of loader is

  type state_t is (S_IDLE, S_LEN, S_PROG, S_TRAIL, S_DONE);

  type buf_t is array (0 to 15) of std_logic_vector(7 downto 0);
  type trail_t is array (0 to 5) of std_logic_vector(7 downto 0);

  constant TRAIL_ROM : trail_t := (
    x"53", x"54", x"41", x"52", x"54", x"0A"
  );

  constant ZERO_BYTE : std_logic_vector(7 downto 0) := (others => '0');

  signal state         : state_t := S_IDLE;
  signal len_b0        : std_logic_vector(7 downto 0) := (others => '0');
  signal len_b1        : std_logic_vector(7 downto 0) := (others => '0');
  signal len_b2        : std_logic_vector(7 downto 0) := (others => '0');
  signal len_cnt       : integer range 0 to 4 := 0;
  signal frame_len     : integer range 0 to 16 := 0;
  signal prog_cnt      : integer range 0 to 16 := 0;
  signal trail_cnt     : integer range 0 to 6 := 0;
  signal buf           : buf_t := (others => ZERO_BYTE);
  signal uart_mode_reg : std_logic := '0';

begin

  -- Programmpuffer auf prog_data abbilden (statische Slices).
  -- Konvention wie in memory.vhd: RAM(i) = prog_data(8*i+7 downto 8*i).
  g_map : for i in 0 to 15 generate
    prog_data(8 * i + 7 downto 8 * i) <= buf(i);
  end generate g_map;

  uart_mode <= uart_mode_reg;

  -- prog_valid genau einen Takt in S_DONE (Moore).
  prog_valid <= '1' when state = S_DONE else '0';

  -- loader_busy: '1' solange ein Rahmen empfangen wird (Mitte eines Rahmens
  -- oder S_DONE), sowie im selben Takt wie das erste Laengenbyte in S_IDLE,
  -- damit die CPU im UART-Modus sofort anhaelt. In S_IDLE ohne rx_valid '0'.
  p_busy : process(all)
  begin
    if state = S_IDLE and rx_valid = '0' then
      loader_busy <= '0';
    else
      loader_busy <= '1';
    end if;
  end process p_busy;

  p_seq : process(clk)
  begin
    if rising_edge(clk) then
      if rst = '1' then
        state         <= S_IDLE;
        len_b0        <= (others => '0');
        len_b1        <= (others => '0');
        len_b2        <= (others => '0');
        len_cnt       <= 0;
        frame_len     <= 0;
        prog_cnt      <= 0;
        trail_cnt     <= 0;
        buf           <= (others => ZERO_BYTE);
        uart_mode_reg <= '0';
      else
        case state is

          when S_IDLE =>
            if rx_valid = '1' then
              len_b0  <= rx_data;
              len_cnt <= 1;
              state   <= S_LEN;
            end if;

          when S_LEN =>
            if rx_valid = '1' then
              if len_cnt = 1 then
                len_b1  <= rx_data;
                len_cnt <= 2;
              elsif len_cnt = 2 then
                len_b2  <= rx_data;
                len_cnt <= 3;
              elsif len_cnt = 3 then
                -- Viertes Laengenbyte ist rx_data (b3). Little endian:
                -- n = b0 + 256*b1 + 65536*b2 + 16777216*b3.
                -- Gueltig genau dann, wenn b1=b2=b3=0 und b0 in 1..16.
                if len_b1 = ZERO_BYTE and len_b2 = ZERO_BYTE
                   and rx_data = ZERO_BYTE
                   and unsigned(len_b0) >= to_unsigned(1, 8)
                   and unsigned(len_b0) <= to_unsigned(16, 8) then
                  frame_len <= to_integer(unsigned(len_b0));
                  prog_cnt  <= 0;
                  trail_cnt <= 0;
                  buf       <= (others => ZERO_BYTE);
                  state     <= S_PROG;
                else
                  len_cnt <= 0;
                  state   <= S_IDLE;
                end if;
              else
                len_cnt <= 0;
                state   <= S_IDLE;
              end if;
            end if;

          when S_PROG =>
            if rx_valid = '1' then
              buf(prog_cnt) <= rx_data;
              if prog_cnt + 1 = frame_len then
                trail_cnt <= 0;
                state     <= S_TRAIL;
              else
                prog_cnt <= prog_cnt + 1;
              end if;
            end if;

          when S_TRAIL =>
            if rx_valid = '1' then
              if rx_data /= TRAIL_ROM(trail_cnt) then
                -- Falsches START-Zeichen: Rahmen verwerfen, naechstes Byte
                -- ist wieder erstes Laengenbyte.
                len_cnt   <= 0;
                prog_cnt  <= 0;
                trail_cnt <= 0;
                state     <= S_IDLE;
              elsif trail_cnt = 5 then
                -- Letztes Zeichen 0A korrekt: Rahmen vollstaendig.
                uart_mode_reg <= '1';
                len_cnt       <= 0;
                prog_cnt      <= 0;
                trail_cnt     <= 0;
                state         <= S_DONE;
              else
                trail_cnt <= trail_cnt + 1;
              end if;
            end if;

          when S_DONE =>
            -- Genau einen Takt prog_valid='1' und busy='1' halten, damit
            -- memory/top die RAM-Uebernahme und das CPU-Clear im Folgetakt
            -- ausfuehren; danach in IDLE (bzw. neuer Rahmen bei rx_valid).
            if rx_valid = '1' then
              len_b0  <= rx_data;
              len_cnt <= 1;
              state   <= S_LEN;
            else
              state <= S_IDLE;
            end if;

          when others =>
            state <= S_IDLE;

        end case;
      end if;
    end if;
  end process p_seq;

end architecture rtl;