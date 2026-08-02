from jinja2 import Template

COUNTER_ENTITY_T = Template("""\
library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
use IEEE.NUMERIC_STD.ALL;

entity {{ name }} is
    Port (
        CLK     : in  STD_LOGIC;
        RESET   : in  STD_LOGIC;
        ENABLE  : in  STD_LOGIC;
        {{ additional_ports }}
        COUNT   : out STD_LOGIC_VECTOR({{ msb }} downto 0)
    );
end {{ name }};
""")

COUNTER_ARCHITECTURE_T = Template("""\
architecture Behavioral of {{ name }} is
    signal count_reg : unsigned({{ msb }} downto 0) := (others => '0');
begin
    process(CLK, RESET)
    begin
        if RESET = '1' then
            count_reg <= (others => '0');
        elsif rising_edge(CLK) then
            if ENABLE = '1' then
                count_reg <= count_reg + 1;
            end if;
        end if;
    end process;

    COUNT <= std_logic_vector(count_reg);
end Behavioral;
""")

COUNTER_TB_ENTITY_T = Template("""\
library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
use IEEE.NUMERIC_STD.ALL;

entity {{ name }}_tb is
end {{ name }}_tb;
""")

COUNTER_TB_ARCHITECTURE_T = Template("""\
architecture Behavioral of {{ name }}_tb is
    signal CLK      : STD_LOGIC := '0';
    signal RESET    : STD_LOGIC := '0';
    signal ENABLE   : STD_LOGIC := '1';
    signal COUNT    : STD_LOGIC_VECTOR({{ msb }} downto 0);

    constant CLK_PERIOD : time := 10 ns;
begin
    uut: entity work.{{ name }}
        port map (
            CLK     => CLK,
            RESET   => RESET,
            ENABLE  => ENABLE,
            COUNT   => COUNT
        );

    clk_process: process
    begin
        CLK <= '0';
        wait for CLK_PERIOD/2;
        CLK <= '1';
        wait for CLK_PERIOD/2;
    end process;

    stim_proc: process
    begin
        RESET <= '1';
        wait for 20 ns;
        RESET <= '0';
        wait for 100 ns;
        ENABLE <= '0';
        wait for 40 ns;
        ENABLE <= '1';
        wait for 80 ns;
        assert false report "Simulation finished" severity note;
        wait;
    end process;
end Behavioral;
""")

HAMMING_DECODER_T = Template("""\
library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
use IEEE.NUMERIC_STD.ALL;

entity hamming_decoder is
    Port (
        CLK        : in  STD_LOGIC;
        RESET      : in  STD_LOGIC;
        DATA_IN    : in  STD_LOGIC_VECTOR(6 downto 0);
        DATA_OUT   : out STD_LOGIC_VECTOR(3 downto 0);
        ERROR_DETECT : out STD_LOGIC;
        ERROR_CORRECT : out STD_LOGIC
    );
end hamming_decoder;

architecture Behavioral of hamming_decoder is
begin
    process(CLK, RESET)
        variable p1, p2, p4 : STD_LOGIC;
        variable syndrome   : STD_LOGIC_VECTOR(2 downto 0);
        variable corrected  : STD_LOGIC_VECTOR(6 downto 0);
    begin
        if RESET = '1' then
            DATA_OUT <= (others => '0');
            ERROR_DETECT <= '0';
            ERROR_CORRECT <= '0';
        elsif rising_edge(CLK) then
            p1 := DATA_IN(0) xor DATA_IN(2) xor DATA_IN(4) xor DATA_IN(6);
            p2 := DATA_IN(1) xor DATA_IN(2) xor DATA_IN(5) xor DATA_IN(6);
            p4 := DATA_IN(3) xor DATA_IN(4) xor DATA_IN(5) xor DATA_IN(6);

            syndrome := p4 & p2 & p1;

            corrected := DATA_IN;

            if syndrome /= "000" then
                ERROR_DETECT <= '1';
                case syndrome is
                    when "001" => corrected(0) := not DATA_IN(0);
                    when "010" => corrected(1) := not DATA_IN(1);
                    when "011" => corrected(2) := not DATA_IN(2);
                    when "100" => corrected(3) := not DATA_IN(3);
                    when "101" => corrected(4) := not DATA_IN(4);
                    when "110" => corrected(5) := not DATA_IN(5);
                    when "111" => corrected(6) := not DATA_IN(6);
                    when others => null;
                end case;
                ERROR_CORRECT <= '1';
            else
                ERROR_DETECT <= '0';
                ERROR_CORRECT <= '0';
            end if;

            DATA_OUT <= corrected(6) & corrected(5) & corrected(4) & corrected(2);
        end if;
    end process;
end Behavioral;
""")

HAMMING_TB_T = Template("""\
library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
use IEEE.NUMERIC_STD.ALL;

entity hamming_decoder_tb is
end hamming_decoder_tb;

architecture Behavioral of hamming_decoder_tb is
    signal CLK        : STD_LOGIC := '0';
    signal RESET      : STD_LOGIC := '0';
    signal DATA_IN    : STD_LOGIC_VECTOR(6 downto 0) := (others => '0');
    signal DATA_OUT   : STD_LOGIC_VECTOR(3 downto 0);
    signal ERROR_DETECT : STD_LOGIC;
    signal ERROR_CORRECT : STD_LOGIC;

    constant CLK_PERIOD : time := 10 ns;
begin
    uut: entity work.hamming_decoder
        port map (
            CLK     => CLK,
            RESET   => RESET,
            DATA_IN => DATA_IN,
            DATA_OUT => DATA_OUT,
            ERROR_DETECT => ERROR_DETECT,
            ERROR_CORRECT => ERROR_CORRECT
        );

    clk_process: process
    begin
        CLK <= '0';
        wait for CLK_PERIOD/2;
        CLK <= '1';
        wait for CLK_PERIOD/2;
    end process;

    stim_proc: process
    begin
        RESET <= '1';
        wait for 20 ns;
        RESET <= '0';
        wait for 10 ns;

        DATA_IN <= "1010101";
        wait for 10 ns;

        DATA_IN <= "1010100";
        wait for 10 ns;

        assert false report "Simulation finished" severity note;
        wait;
    end process;
end Behavioral;
""")


class VHDLTemplates:
    TEMPLATES = {
        "counter": {
            "entity": COUNTER_ENTITY_T,
            "architecture": COUNTER_ARCHITECTURE_T,
            "tb_entity": COUNTER_TB_ENTITY_T,
            "tb_architecture": COUNTER_TB_ARCHITECTURE_T,
        },
        "hamming": {
            "decoder": HAMMING_DECODER_T,
            "testbench": HAMMING_TB_T,
        },
    }

    @classmethod
    def render(cls, template_name: str, template_key: str, **kwargs) -> str:
        template = cls.TEMPLATES[template_name][template_key]
        return template.render(**kwargs)
