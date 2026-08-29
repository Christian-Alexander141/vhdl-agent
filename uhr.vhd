library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
use IEEE.NUMERIC_STD.ALL;

entity uhr is
    Port (
        CLK     : in  STD_LOGIC;
        RESET   : in  STD_LOGIC;
        ENABLE  : in  STD_LOGIC;
        
        SECONDS : out STD_LOGIC_VECTOR(5 downto 0);
        MINUTES : out STD_LOGIC_VECTOR(5 downto 0);
        HOURS   : out STD_LOGIC_VECTOR(4 downto 0)
    );
end uhr;

architecture Behavioral of uhr is
    signal sec_reg  : unsigned(5 downto 0) := (others => '0');
    signal min_reg  : unsigned(5 downto 0) := (others => '0');
    signal hour_reg : unsigned(4 downto 0) := (others => '0');
begin
    process(CLK)
    begin
        if rising_edge(CLK) then
            if RESET = '1' then
                sec_reg  <= (others => '0');
                min_reg  <= (others => '0');
                hour_reg <= (others => '0');
            elsif ENABLE = '1' then
                if sec_reg = to_unsigned(59, 6) then
                    sec_reg <= (others => '0');
                    if min_reg = to_unsigned(59, 6) then
                        min_reg <= (others => '0');
                        if hour_reg = to_unsigned(23, 5) then
                            hour_reg <= (others => '0');
                        else
                            hour_reg <= hour_reg + 1;
                        end if;
                    else
                        min_reg <= min_reg + 1;
                    end if;
                else
                    sec_reg <= sec_reg + 1;
                end if;
            end if;
        end if;
    end process;

    SECONDS <= std_logic_vector(sec_reg);
    MINUTES <= std_logic_vector(min_reg);
    HOURS   <= std_logic_vector(hour_reg);
end Behavioral;