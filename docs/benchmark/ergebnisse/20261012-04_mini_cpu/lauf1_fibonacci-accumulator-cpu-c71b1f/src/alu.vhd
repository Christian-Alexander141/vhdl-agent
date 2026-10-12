library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity alu is
  generic (
    WIDTH : positive := 4
  );
  port (
    a      : in  std_logic_vector(WIDTH - 1 downto 0);
    b      : in  std_logic_vector(WIDTH - 1 downto 0);
    op     : in  std_logic_vector(2 downto 0);
    result : out std_logic_vector(WIDTH - 1 downto 0);
    carry  : out std_logic;
    zero   : out std_logic
  );
end entity alu;

architecture rtl of alu is
begin

  p_comb: process(all)
    variable av      : unsigned(WIDTH - 1 downto 0);
    variable bv      : unsigned(WIDTH - 1 downto 0);
    variable sum_ext : unsigned(WIDTH downto 0);
    variable res_v   : std_logic_vector(WIDTH - 1 downto 0);
    variable c_v     : std_logic;
  begin
    av := unsigned(a);
    bv := unsigned(b);
    -- Defaults (kein Latch, alle Opcodes abgedeckt)
    res_v := (others => '0');
    c_v := '0';
    case op is
      when "000" => -- ADD: ACC + RAM mod 2**WIDTH, C = Uebertrag
        sum_ext := ('0' & av) + ('0' & bv);
        res_v := std_logic_vector(sum_ext(WIDTH - 1 downto 0));
        c_v := sum_ext(WIDTH);
      when "001" => -- SUB: ACC - RAM mod 2**WIDTH, C = Borrow (1 wenn a < b)
        res_v := std_logic_vector(av - bv);
        if av < bv then
          c_v := '1';
        else
          c_v := '0';
        end if;
      when "010" => -- AND
        res_v := a and b;
        c_v := '0';
      when "011" => -- OR
        res_v := a or b;
        c_v := '0';
      when "100" => -- XOR
        res_v := a xor b;
        c_v := '0';
      when "101" => -- SHL von a: links schieben, rechts '0', C = altes Bit WIDTH-1
        c_v := a(WIDTH - 1);
        if WIDTH = 1 then
          res_v := (others => '0');
        else
          res_v := a(WIDTH - 2 downto 0) & '0';
        end if;
      when "110" => -- SHR von a: rechts schieben, links '0', C = altes Bit 0
        c_v := a(0);
        if WIDTH = 1 then
          res_v := (others => '0');
        else
          res_v := '0' & a(WIDTH - 1 downto 1);
        end if;
      when "111" => -- PASS b
        res_v := b;
        c_v := '0';
      when others =>
        res_v := (others => '0');
        c_v := '0';
    end case;
    result <= res_v;
    carry <= c_v;
    if res_v = std_logic_vector(to_unsigned(0, WIDTH)) then
      zero <= '1';
    else
      zero <= '0';
    end if;
  end process p_comb;

end architecture rtl;