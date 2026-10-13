library ieee;
use ieee.std_logic_1164.all;

entity control_unit is
  port (
    clk     : in  std_logic;
    rst     : in  std_logic;
    step_en : in  std_logic;
    opcode  : in  std_logic_vector(3 downto 0);
    flag_c  : in  std_logic;
    flag_z  : in  std_logic;
    clr     : in  std_logic;
    hlt     : out std_logic;
    mi      : out std_logic;
    ri      : out std_logic;
    ro      : out std_logic;
    io      : out std_logic;
    ii      : out std_logic;
    ai      : out std_logic;
    ao      : out std_logic;
    eo      : out std_logic;
    su      : out std_logic;
    bi      : out std_logic;
    oi      : out std_logic;
    ce      : out std_logic;
    co      : out std_logic;
    j       : out std_logic;
    fi      : out std_logic;
    halted  : out std_logic
  );
end entity control_unit;

architecture rtl of control_unit is
  signal step : integer range 0 to 4 := 0;
  signal halted_r : std_logic := '0';
  signal s_hlt, s_mi, s_ri, s_ro, s_io, s_ii, s_ai, s_ao,
         s_eo, s_su, s_bi, s_oi, s_ce, s_co, s_j, s_fi : std_logic;
begin
  hlt <= s_hlt; mi <= s_mi; ri <= s_ri; ro <= s_ro; io <= s_io;
  ii <= s_ii; ai <= s_ai; ao <= s_ao; eo <= s_eo; su <= s_su;
  bi <= s_bi; oi <= s_oi; ce <= s_ce; co <= s_co; j <= s_j; fi <= s_fi;
  halted <= halted_r;

  process(step, opcode, flag_c, flag_z)
  begin
    s_hlt <= '0'; s_mi <= '0'; s_ri <= '0'; s_ro <= '0'; s_io <= '0';
    s_ii <= '0'; s_ai <= '0'; s_ao <= '0'; s_eo <= '0'; s_su <= '0';
    s_bi <= '0'; s_oi <= '0'; s_ce <= '0'; s_co <= '0'; s_j <= '0'; s_fi <= '0';
    if step = 0 then
      s_mi <= '1'; s_co <= '1';
    elsif step = 1 then
      s_ro <= '1'; s_ii <= '1'; s_ce <= '1';
    else
      case opcode is
        when "0000" => null;
        when "0001" =>
          if step = 2 then s_io <= '1'; s_mi <= '1';
          elsif step = 3 then s_ro <= '1'; s_ai <= '1';
          end if;
        when "0010" =>
          if step = 2 then s_io <= '1'; s_mi <= '1';
          elsif step = 3 then s_ro <= '1'; s_bi <= '1';
          elsif step = 4 then s_eo <= '1'; s_ai <= '1'; s_fi <= '1';
          end if;
        when "0011" =>
          if step = 2 then s_io <= '1'; s_mi <= '1';
          elsif step = 3 then s_ro <= '1'; s_bi <= '1';
          elsif step = 4 then s_eo <= '1'; s_ai <= '1'; s_su <= '1'; s_fi <= '1';
          end if;
        when "0100" =>
          if step = 2 then s_io <= '1'; s_mi <= '1';
          elsif step = 3 then s_ao <= '1'; s_ri <= '1';
          end if;
        when "0101" =>
          if step = 2 then s_io <= '1'; s_ai <= '1'; end if;
        when "0110" =>
          if step = 2 then s_io <= '1'; s_j <= '1'; end if;
        when "0111" =>
          if step = 2 and flag_c = '1' then s_io <= '1'; s_j <= '1'; end if;
        when "1000" =>
          if step = 2 and flag_z = '1' then s_io <= '1'; s_j <= '1'; end if;
        when "1110" =>
          if step = 2 then s_ao <= '1'; s_oi <= '1'; end if;
        when "1111" =>
          if step = 2 then s_hlt <= '1'; end if;
        when others => null;
      end case;
    end if;
  end process;

  process(clk)
  begin
    if rising_edge(clk) then
      if rst = '1' or clr = '1' then
        step <= 0;
        halted_r <= '0';
      elsif step_en = '1' then
        if s_hlt = '1' then
          halted_r <= '1';
        else
          if step = 4 then
            step <= 0;
          else
            step <= step + 1;
          end if;
        end if;
      end if;
    end if;
  end process;
end architecture rtl;
