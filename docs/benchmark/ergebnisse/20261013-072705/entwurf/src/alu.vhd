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
  process(a, b, op)
    variable au   : unsigned(WIDTH-1 downto 0);
    variable bu   : unsigned(WIDTH-1 downto 0);
    variable sum  : unsigned(WIDTH downto 0);
    variable res  : std_logic_vector(WIDTH-1 downto 0);
    variable c    : std_logic;
  begin
    au := unsigned(a);
    bu := unsigned(b);
    c  := '0';
    case op is
      when "000" => -- ADD
        sum := ('0' & au) + ('0' & bu);
        res := std_logic_vector(sum(WIDTH-1 downto 0));
        c   := sum(WIDTH);
      when "001" => -- SUB: ACC - RAM, C=1 wenn Borgen (a<b)
        sum := ('0' & au) - ('0' & bu);
        res := std_logic_vector(sum(WIDTH-1 downto 0));
        if au < bu then
          c := '1';
        else
          c := '0';
        end if;
      when "010" => -- AND
        res := a and b;
        c   := '0';
      when "011" => -- OR
        res := a or b;
        c   := '0';
      when "100" => -- XOR
        res := a xor b;
        c   := '0';
      when "101" => -- SHL von a
        c   := a(WIDTH-1);
        res := a(WIDTH-2 downto 0) & '0';
      when "110" => -- SHR von a
        c   := a(0);
        res := '0' & a(WIDTH-1 downto 1);
      when others => -- "111" PASS b
        res := b;
        c   := '0';
    end case;
    result <= res;
    carry  <= c;
    if unsigned(res) = 0 then
      zero <= '1';
    else
      zero <= '0';
    end if;
  end process;
end architecture rtl;
