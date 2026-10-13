library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity control_unit is
  port (
    ai          : out std_logic;
    ao          : out std_logic;
    bi          : out std_logic;
    ce          : out std_logic;
    clear       : in  std_logic;
    clk         : in  std_logic;
    co          : out std_logic;
    eo          : out std_logic;
    fi          : out std_logic;
    flag_c      : in  std_logic;
    flag_z      : in  std_logic;
    halted      : out std_logic;
    hlt         : out std_logic;
    ii          : out std_logic;
    io          : out std_logic;
    opcode      : in  std_logic_vector(3 downto 0);
    ri          : out std_logic;
    ro          : out std_logic;
    rst         : in  std_logic;
    step_enable : in  std_logic;
    su          : out std_logic;
    j_load      : out std_logic;
    mi          : out std_logic;
    oi          : out std_logic
  );
end entity control_unit;

architecture rtl of control_unit is
  type t_state_t is (T0, T1, T2, T3, T4);
  signal t_state    : t_state_t;
  signal halted_reg : std_logic;
begin

  halted <= halted_reg;

  p_seq: process(clk)
  begin
    if rising_edge(clk) then
      if rst = '1' or clear = '1' then
        t_state    <= T0;
        halted_reg <= '0';
      elsif halted_reg = '1' then
        null;
      elsif step_enable = '1' then
        if t_state = T2 and opcode = "1111" then
          halted_reg <= '1';
        else
          case t_state is
            when T0 => t_state <= T1;
            when T1 => t_state <= T2;
            when T2 => t_state <= T3;
            when T3 => t_state <= T4;
            when T4 => t_state <= T0;
          end case;
        end if;
      end if;
    end if;
  end process p_seq;

  p_comb: process(all)
  begin
    ai     <= '0';
    ao     <= '0';
    bi     <= '0';
    ce     <= '0';
    co     <= '0';
    eo     <= '0';
    fi     <= '0';
    hlt    <= '0';
    ii     <= '0';
    io     <= '0';
    ri     <= '0';
    ro     <= '0';
    su     <= '0';
    j_load <= '0';
    mi     <= '0';
    oi     <= '0';

    case t_state is
      when T0 =>
        mi <= '1';
        co <= '1';
      when T1 =>
        ro <= '1';
        ii <= '1';
        ce <= '1';
      when T2 =>
        case opcode is
          when "0001" | "0010" | "0011" | "0100" =>
            io <= '1';
            mi <= '1';
          when "0101" =>
            io <= '1';
            ai <= '1';
          when "0110" =>
            io     <= '1';
            j_load <= '1';
          when "0111" =>
            if flag_c = '1' then
              io     <= '1';
              j_load <= '1';
            end if;
          when "1000" =>
            if flag_z = '1' then
              io     <= '1';
              j_load <= '1';
            end if;
          when "1110" =>
            ao <= '1';
            oi <= '1';
          when "1111" =>
            hlt <= '1';
          when others =>
            null;
        end case;
      when T3 =>
        case opcode is
          when "0001" =>
            ro <= '1';
            ai <= '1';
          when "0010" | "0011" =>
            ro <= '1';
            bi <= '1';
          when "0100" =>
            ao <= '1';
            ri <= '1';
          when others =>
            null;
        end case;
      when T4 =>
        case opcode is
          when "0010" =>
            eo <= '1';
            ai <= '1';
            fi <= '1';
          when "0011" =>
            eo <= '1';
            ai <= '1';
            su <= '1';
            fi <= '1';
          when others =>
            null;
        end case;
    end case;
  end process p_comb;

end architecture rtl;