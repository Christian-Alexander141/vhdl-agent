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
begin

  p_comb: process(all)
    variable av : unsigned(WIDTH-1 downto 0);
    variable bv : unsigned(WIDTH-1 downto 0);
    variable sum_ext : unsigned(WIDTH downto 0);
    variable res_v : std_logic_vector(WIDTH-1 downto 0);
    variable carry_v : std_logic;
  begin
    av := unsigned(a);
    bv := unsigned(b);
    -- defaults (avoid latches)
    res_v := (others => '0');
    carry_v := '0';
    case op is
      when "000" => -- ADD: ACC := (ACC + RAM) mod 16; C := carry out of MSB
        sum_ext := ('0' & av) + ('0' & bv);
        res_v := std_logic_vector(sum_ext(WIDTH-1 downto 0));
        carry_v := sum_ext(WIDTH);
      when "001" => -- SUB: ACC := (ACC - RAM) mod 16; C := '1' if a < b (borrow)
        res_v := std_logic_vector(av - bv);
        if av < bv then
          carry_v := '1';
        else
          carry_v := '0';
        end if;
      when "010" => -- AND
        res_v := a and b;
        carry_v := '0';
      when "011" => -- OR
        res_v := a or b;
        carry_v := '0';
      when "100" => -- XOR
        res_v := a xor b;
        carry_v := '0';
      when "101" => -- SHL von a: links schieben, rechts '0'; C := altes MSB
        res_v := std_logic_vector(shift_left(av, 1));
        carry_v := a(WIDTH-1);
      when "110" => -- SHR von a: rechts schieben, links '0'; C := altes LSB
        res_v := std_logic_vector(shift_right(av, 1));
        carry_v := a(0);
      when "111" => -- PASS b
        res_v := b;
        carry_v := '0';
      when others =>
        res_v := (others => '0');
        carry_v := '0';
    end case;
    result <= res_v;
    carry <= carry_v;
    if res_v = std_logic_vector(to_unsigned(0, WIDTH)) then
      zero <= '1';
    else
      zero <= '0';
    end if;
  end process p_comb;

end architecture rtl;