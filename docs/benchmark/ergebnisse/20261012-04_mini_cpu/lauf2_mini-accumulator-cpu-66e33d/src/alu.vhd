library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity alu is
  generic (
    WIDTH : positive := 4
  );
  port (
    a      : in  std_logic_vector(WIDTH-1 downto 0);
    b      : in  std_logic_vector(WIDTH-1 downto 0);
    op     : in  std_logic_vector(2 downto 0);
    result : out std_logic_vector(WIDTH-1 downto 0);
    carry  : out std_logic;
    zero   : out std_logic
  );
end entity alu;

architecture rtl of alu is
  signal s_result : std_logic_vector(WIDTH-1 downto 0);
  signal s_carry  : std_logic;
begin

  p_comb: process(all)
    variable av      : unsigned(WIDTH-1 downto 0);
    variable bv      : unsigned(WIDTH-1 downto 0);
    variable sum_ext : unsigned(WIDTH downto 0);
    variable v_res   : std_logic_vector(WIDTH-1 downto 0);
    variable v_carry : std_logic;
  begin
    av := unsigned(a);
    bv := unsigned(b);
    v_carry := '0';
    v_res := (others => '0');
    case op is
      when "000" => -- ADD
        sum_ext := ('0' & av) + ('0' & bv);
        v_res := std_logic_vector(sum_ext(WIDTH-1 downto 0));
        v_carry := sum_ext(WIDTH);
      when "001" => -- SUB, C = '1' bei Borgen (a < b)
        v_res := std_logic_vector(av - bv);
        if av < bv then
          v_carry := '1';
        else
          v_carry := '0';
        end if;
      when "010" => -- AND
        v_res := a and b;
        v_carry := '0';
      when "011" => -- OR
        v_res := a or b;
        v_carry := '0';
      when "100" => -- XOR
        v_res := a xor b;
        v_carry := '0';
      when "101" => -- SHL von a
        v_res := std_logic_vector(shift_left(av, 1));
        v_carry := a(WIDTH-1);
      when "110" => -- SHR von a
        v_res := std_logic_vector(shift_right(av, 1));
        v_carry := a(0);
      when "111" => -- PASS b
        v_res := b;
        v_carry := '0';
      when others =>
        v_res := (others => '0');
        v_carry := '0';
    end case;
    s_result <= v_res;
    s_carry <= v_carry;
  end process p_comb;

  result <= s_result;
  carry  <= s_carry;
  zero   <= '1' when unsigned(s_result) = 0 else '0';

end architecture rtl;