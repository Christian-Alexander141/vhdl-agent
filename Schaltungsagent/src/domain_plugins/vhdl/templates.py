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
        wait for 1 ns;

        -- Nach dem Reset muss der Zaehler bei 0 stehen.
        assert COUNT = std_logic_vector(to_unsigned(0, {{ msb }} + 1))
            report "COUNT not zero after reset, actual="
                   & integer'image(to_integer(unsigned(COUNT)))
            severity error;

        -- 10 Taktflanken mit ENABLE='1': COUNT muss 10 erreichen.
        for i in 1 to 10 loop
            wait until rising_edge(CLK);
        end loop;
        wait for 1 ns;

        assert COUNT = std_logic_vector(to_unsigned(10, {{ msb }} + 1))
            report "COUNT mismatch after 10 cycles, actual="
                   & integer'image(to_integer(unsigned(COUNT)))
            severity error;

        -- Bei ENABLE='0' darf der Zaehler nicht weiterlaufen.
        ENABLE <= '0';
        wait until rising_edge(CLK);
        wait until rising_edge(CLK);
        wait for 1 ns;

        assert COUNT = std_logic_vector(to_unsigned(10, {{ msb }} + 1))
            report "COUNT changed while disabled, actual="
                   & integer'image(to_integer(unsigned(COUNT)))
            severity error;

        -- Nach erneutem ENABLE='1' muss der Zaehler weiterzaehlen.
        ENABLE <= '1';
        for i in 1 to 3 loop
            wait until rising_edge(CLK);
        end loop;
        wait for 1 ns;

        assert COUNT = std_logic_vector(to_unsigned(13, {{ msb }} + 1))
            report "COUNT mismatch after 3 more cycles, actual="
                   & integer'image(to_integer(unsigned(COUNT)))
            severity error;

        assert false report "TB_COMPLETE" severity note;
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

    -- Unabhaengige Referenz: Hamming-(7,4)-Encoder.
    -- Die Referenzlogik ist bewusst vom DUT (Decoder) getrennt, damit sich
    -- identische Fehler in DUT und Testbench nicht gegenseitig maskieren.
    -- Bitbelegung: bit0=P1, bit1=P2, bit2=D1, bit3=P4, bit4=D2, bit5=D3, bit6=D4
    function hamming_encode(data : std_logic_vector(3 downto 0))
        return std_logic_vector is
        variable d1, d2, d3, d4 : std_logic;
        variable p1, p2, p4     : std_logic;
        variable code           : std_logic_vector(6 downto 0);
    begin
        d1 := data(0);
        d2 := data(1);
        d3 := data(2);
        d4 := data(3);
        p1 := d1 xor d2 xor d4;
        p2 := d1 xor d3 xor d4;
        p4 := d2 xor d3 xor d4;
        code(0) := p1;
        code(1) := p2;
        code(2) := d1;
        code(3) := p4;
        code(4) := d2;
        code(5) := d3;
        code(6) := d4;
        return code;
    end function;

    -- Formatiert einen STD_LOGIC_VECTOR als Binaerstring (MSB links).
    -- VHDL-93-kompatibel; to_string() gibt es erst ab VHDL-2008.
    function slv_to_string(vec : std_logic_vector) return string is
        variable result : string(1 to vec'length);
    begin
        for i in vec'range loop
            if vec(i) = '1' then
                result(vec'length - i) := '1';
            else
                result(vec'length - i) := '0';
            end if;
        end loop
        return result;
    end function;

    -- Prueft ein einzelnes Testergebnis des DUT. Bei Abweichung wird eine
    -- Assertion mit severity error ausgeloest, die GHDL zum Abbruch mit
    -- Exit-Code != 0 bringt. Die Report-Meldungen sind strukturiert
    -- ("FAIL CASE data=.. bit=.. code=.. ..."), damit der Validator den
    -- fehlgeschlagenen Testfall für den Repair-Agenten extrahieren kann.
    procedure check_case(
        data_val      : in integer;
        error_bit     : in integer;
        expected_data : in std_logic_vector(3 downto 0);
        expected_err  : in std_logic
    ) is
    begin
        wait until rising_edge(CLK);
        wait for 1 ns;

        assert DATA_OUT = expected_data
            report "FAIL CASE data=" & integer'image(data_val)
                   & " bit=" & integer'image(error_bit)
                   & " code=" & slv_to_string(DATA_IN)
                   & " DATA_OUT expected="
                   & integer'image(to_integer(unsigned(expected_data)))
                   & " actual=" & integer'image(to_integer(unsigned(DATA_OUT)))
            severity error;

        assert ERROR_DETECT = expected_err
            report "FAIL CASE data=" & integer'image(data_val)
                   & " bit=" & integer'image(error_bit)
                   & " code=" & slv_to_string(DATA_IN)
                   & " ERROR_DETECT expected=" & std_logic'image(expected_err)
                   & " actual=" & std_logic'image(ERROR_DETECT)
            severity error;

        assert ERROR_CORRECT = expected_err
            report "FAIL CASE data=" & integer'image(data_val)
                   & " bit=" & integer'image(error_bit)
                   & " code=" & slv_to_string(DATA_IN)
                   & " ERROR_CORRECT expected=" & std_logic'image(expected_err)
                   & " actual=" & std_logic'image(ERROR_CORRECT)
            severity error;
    end procedure;
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
        variable code          : std_logic_vector(6 downto 0);
        variable expected_data : std_logic_vector(3 downto 0);
        variable test_count    : integer := 0;
    begin
        RESET <= '1';
        wait for 20 ns;
        RESET <= '0';
        wait for 10 ns;

        -- Alle 16 moeglichen 4-Bit-Datenwoerter.
        for data_val in 0 to 15 loop
            expected_data := std_logic_vector(to_unsigned(data_val, 4));

            -- Fall 1: fehlerfreies Codewort.
            -- Erwartung: DATA_OUT = Datenwort, ERROR_DETECT = '0',
            --            ERROR_CORRECT = '0'
            code := hamming_encode(expected_data);
            DATA_IN <= code;
            check_case(data_val, -1, expected_data, '0');
            test_count := test_count + 1;

            -- Fall 2: alle 7 Einzelbitfehler.
            -- Erwartung: DATA_OUT = Datenwort, ERROR_DETECT = '1',
            --            ERROR_CORRECT = '1'
            for error_bit in 0 to 6 loop
                code := hamming_encode(expected_data);
                code(error_bit) := not code(error_bit);
                DATA_IN <= code;
                check_case(data_val, error_bit, expected_data, '1');
                test_count := test_count + 1;
            end loop;
        end loop;

        -- 16 Datenwoerter x (1 fehlerfreier Fall + 7 Einzelbitfehler) = 128.
        -- Hinweis: Hamming-(7,4) kann genau einen Einzelbitfehler korrigieren.
        -- Zwei-Bit-Fehler koennen nicht zuverlaessig korrigiert werden und
        -- werden daher nicht als korrigierbar erwartet.
        assert test_count = 128
            report "Only " & integer'image(test_count)
                   & " of 128 test cases executed"
            severity error;

        assert false report "TB_COMPLETE" severity note;
        wait;
    end process;
end Behavioral;
""")

ARTY_RUNNING_LIGHT_ENTITY_T = Template("""\
library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
use IEEE.NUMERIC_STD.ALL;

entity led_running_light is
    Generic (
        CLK_FREQ_HZ   : positive := 100_000_000;  -- Systemtakt in Hz (Arty S7-50: 100 MHz)
        LED_COUNT     : positive := 4;            -- Anzahl LEDs auf dem Board
        BLINK_HZ      : positive := 2             -- Lauflicht-Geschwindigkeit in Hz
    );
    Port (
        CLK   : in  STD_LOGIC;                    -- 100 MHz Systemtakt (Pin E3)
        RESET : in  STD_LOGIC;                    -- Aktiver-High Reset (BTN0 / CPU_RESET)
        LED   : out STD_LOGIC_VECTOR(LED_COUNT-1 downto 0)  -- 4 User LEDs (LD0-LD3)
    );
end led_running_light;
""")

ARTY_RUNNING_LIGHT_ARCH_T = Template("""\
architecture Behavioral of led_running_light is

    -- Clock-Divider: Erzeugt einen langsamen Takt aus dem 100 MHz Systemtakt
    constant DIV_VALUE : natural := CLK_FREQ_HZ / (2 * BLINK_HZ * LED_COUNT) - 1;
    signal div_cnt   : natural range 0 to DIV_VALUE := 0;
    signal slow_clk  : STD_LOGIC := '0';

    -- LED-Shift-Register für Lauflicht
    signal led_reg   : STD_LOGIC_VECTOR(LED_COUNT-1 downto 0) := (0 => '1', others => '0');

begin

    -- Clock Divider Prozess
    clk_div_proc: process(CLK, RESET)
    begin
        if RESET = '1' then
            div_cnt  <= 0;
            slow_clk <= '0';
        elsif rising_edge(CLK) then
            if div_cnt = DIV_VALUE then
                div_cnt  <= 0;
                slow_clk <= not slow_clk;
            else
                div_cnt <= div_cnt + 1;
            end if;
        end if;
    end process clk_div_proc;

    -- Lauflicht-Shift-Register
    led_shift_proc: process(slow_clk, RESET)
    begin
        if RESET = '1' then
            led_reg <= (0 => '1', others => '0');
        elsif rising_edge(slow_clk) then
            led_reg <= led_reg(LED_COUNT-2 downto 0) & led_reg(LED_COUNT-1);
        end if;
    end process led_shift_proc;

    LED <= led_reg;

end Behavioral;
""")

ARTY_RUNNING_LIGHT_TB_ENTITY_T = Template("""\
library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
use IEEE.NUMERIC_STD.ALL;

entity led_running_light_tb is
end led_running_light_tb;
""")

ARTY_RUNNING_LIGHT_TB_ARCH_T = Template("""\
architecture Behavioral of led_running_light_tb is

    constant CLK_FREQ_HZ : positive := 100_000_000;
    constant LED_COUNT   : positive := 4;
    constant BLINK_HZ    : positive := 100_000;  -- Schneller für Simulation (100 kHz -> ~25 kHz pro LED)

    constant CLK_PERIOD  : time := 1 sec / CLK_FREQ_HZ;
    constant DIV_VALUE   : natural := CLK_FREQ_HZ / (2 * BLINK_HZ * LED_COUNT) - 1;
    -- Anzahl schneller Taktzyklen pro langsamer Takt-Halbperiode
    constant SLOW_HALF_CYCLES : natural := DIV_VALUE + 1;
    -- Anzahl schneller Taktzyklen pro vollständiger langsamer Taktperiode
    constant SLOW_FULL_CYCLES : natural := 2 * SLOW_HALF_CYCLES;

    signal CLK   : STD_LOGIC := '0';
    signal RESET : STD_LOGIC := '0';
    signal LED   : STD_LOGIC_VECTOR(LED_COUNT-1 downto 0);

    type led_sequence_t is array (0 to LED_COUNT-1) of STD_LOGIC_VECTOR(LED_COUNT-1 downto 0);
    constant EXPECTED_SEQ : led_sequence_t := (
        0 => "0001",
        1 => "0010",
        2 => "0100",
        3 => "1000"
    );

    -- Formatiert einen STD_LOGIC_VECTOR als Binaerstring (MSB links).
    -- VHDL-93-kompatibel; to_string() gibt es erst ab VHDL-2008.
    function slv_to_string(vec : std_logic_vector) return string is
        variable result : string(1 to vec'length);
    begin
        for i in vec'range loop
            if vec(i) = '1' then
                result(vec'length - i) := '1';
            else
                result(vec'length - i) := '0';
            end if;
        end loop;
        return result;
    end function;

    -- Hilfsprozedur: Warte auf n schnelle Taktflanken
    procedure wait_cycles(n : natural) is
    begin
        for i in 1 to n loop
            wait until rising_edge(CLK);
        end loop;
    end procedure;

begin

    uut: entity work.led_running_light
        generic map (
            CLK_FREQ_HZ => CLK_FREQ_HZ,
            LED_COUNT   => LED_COUNT,
            BLINK_HZ    => BLINK_HZ
        )
        port map (
            CLK   => CLK,
            RESET => RESET,
            LED   => LED
        );

    -- 100 MHz Taktgenerator
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
        wait_cycles(20);
        RESET <= '0';
        wait_cycles(2);

        -- Nach Reset: LED = "0001" (Initialwert, Position 0)
        assert LED = "0001"
            report "Initial LED state wrong after reset: " & slv_to_string(LED)
            severity error;

        -- Erste rising_edge(slow_clk) nach SLOW_HALF_CYCLES (125 Zyklen nach Reset-Ende)
        wait_cycles(SLOW_HALF_CYCLES);
        assert LED = "0010"
            report "First shift failed: expected 0010 got " & slv_to_string(LED)
            severity error;

        -- Weitere rising_edges alle SLOW_FULL_CYCLES (250 Zyklen)
        -- 2. Flanke -> Position 2 (0100)
        wait_cycles(SLOW_FULL_CYCLES);
        assert LED = "0100"
            report "Second shift failed: expected 0100 got " & slv_to_string(LED)
            severity error;

        -- 3. Flanke -> Position 3 (1000)
        wait_cycles(SLOW_FULL_CYCLES);
        assert LED = "1000"
            report "Third shift failed: expected 1000 got " & slv_to_string(LED)
            severity error;

        -- 4. Flanke -> Position 0 (0001, Wraparound)
        wait_cycles(SLOW_FULL_CYCLES);
        assert LED = "0001"
            report "Wraparound failed: expected 0001 got " & slv_to_string(LED)
            severity error;

        -- Test Reset während Laufbetrieb
        RESET <= '1';
        wait_cycles(10);
        RESET <= '0';
        wait_cycles(2);
        -- Nach Reset wieder Initialzustand (Position 0)
        assert LED = "0001"
            report "LED state wrong after mid-run reset: " & slv_to_string(LED)
            severity error;
        -- Erste Flanke nach Reset -> Position 1
        wait_cycles(SLOW_HALF_CYCLES);
        assert LED = "0010"
            report "First shift after reset failed: " & slv_to_string(LED)
            severity error;

        assert false report "TB_COMPLETE" severity note;
        wait;
    end process;

end Behavioral;
""")

ARTY_RUNNING_LIGHT_TB_T = Template("""\
library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
use IEEE.NUMERIC_STD.ALL;

entity led_running_light_tb is
end led_running_light_tb;

architecture Behavioral of led_running_light_tb is

    constant CLK_FREQ_HZ : positive := 100_000_000;
    constant LED_COUNT   : positive := 4;
    constant BLINK_HZ    : positive := 100_000;  -- Schneller für Simulation (100 kHz -> ~25 kHz pro LED)

    constant CLK_PERIOD  : time := 1 sec / CLK_FREQ_HZ;
    constant DIV_VALUE   : natural := CLK_FREQ_HZ / (2 * BLINK_HZ * LED_COUNT) - 1;
    -- Anzahl schneller Taktzyklen pro langsamer Takt-Halbperiode
    constant SLOW_HALF_CYCLES : natural := DIV_VALUE + 1;
    -- Anzahl schneller Taktzyklen pro vollständiger langsamer Taktperiode
    constant SLOW_FULL_CYCLES : natural := 2 * SLOW_HALF_CYCLES;

    signal CLK   : STD_LOGIC := '0';
    signal RESET : STD_LOGIC := '0';
    signal LED   : STD_LOGIC_VECTOR(LED_COUNT-1 downto 0);

    type led_sequence_t is array (0 to LED_COUNT-1) of STD_LOGIC_VECTOR(LED_COUNT-1 downto 0);
    constant EXPECTED_SEQ : led_sequence_t := (
        0 => "0001",
        1 => "0010",
        2 => "0100",
        3 => "1000"
    );

    -- Formatiert einen STD_LOGIC_VECTOR als Binaerstring (MSB links).
    -- VHDL-93-kompatibel; to_string() gibt es erst ab VHDL-2008.
    function slv_to_string(vec : std_logic_vector) return string is
        variable result : string(1 to vec'length);
    begin
        for i in vec'range loop
            if vec(i) = '1' then
                result(vec'length - i) := '1';
            else
                result(vec'length - i) := '0';
            end if;
        end loop;
        return result;
    end function;

    -- Hilfsprozedur: Warte auf n schnelle Taktflanken
    procedure wait_cycles(n : natural) is
    begin
        for i in 1 to n loop
            wait until rising_edge(CLK);
        end loop;
    end procedure;

begin

    uut: entity work.led_running_light
        generic map (
            CLK_FREQ_HZ => CLK_FREQ_HZ,
            LED_COUNT   => LED_COUNT,
            BLINK_HZ    => BLINK_HZ
        )
        port map (
            CLK   => CLK,
            RESET => RESET,
            LED   => LED
        );

    -- 100 MHz Taktgenerator
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
        wait_cycles(20);
        RESET <= '0';
        wait_cycles(2);

        -- Nach Reset: LED = "0001" (Initialwert, Position 0)
        assert LED = "0001"
            report "Initial LED state wrong after reset: " & slv_to_string(LED)
            severity error;

        -- Erste rising_edge(slow_clk) nach SLOW_HALF_CYCLES (125 Zyklen nach Reset-Ende)
        wait_cycles(SLOW_HALF_CYCLES);
        assert LED = "0010"
            report "First shift failed: expected 0010 got " & slv_to_string(LED)
            severity error;

        -- Weitere rising_edges alle SLOW_FULL_CYCLES (250 Zyklen)
        -- 2. Flanke -> Position 2 (0100)
        wait_cycles(SLOW_FULL_CYCLES);
        assert LED = "0100"
            report "Second shift failed: expected 0100 got " & slv_to_string(LED)
            severity error;

        -- 3. Flanke -> Position 3 (1000)
        wait_cycles(SLOW_FULL_CYCLES);
        assert LED = "1000"
            report "Third shift failed: expected 1000 got " & slv_to_string(LED)
            severity error;

        -- 4. Flanke -> Position 0 (0001, Wraparound)
        wait_cycles(SLOW_FULL_CYCLES);
        assert LED = "0001"
            report "Wraparound failed: expected 0001 got " & slv_to_string(LED)
            severity error;

        -- Test Reset während Laufbetrieb
        RESET <= '1';
        wait_cycles(10);
        RESET <= '0';
        wait_cycles(2);
        -- Nach Reset wieder Initialzustand (Position 0)
        assert LED = "0001"
            report "LED state wrong after mid-run reset: " & slv_to_string(LED)
            severity error;
        -- Erste Flanke nach Reset -> Position 1
        wait_cycles(SLOW_HALF_CYCLES);
        assert LED = "0010"
            report "First shift after reset failed: " & slv_to_string(LED)
            severity error;

        assert false report "TB_COMPLETE" severity note;
        wait;
    end process;

end Behavioral;
""")

ARTY_S7_50_XDC_T = Template("""## Arty S7-50 Constraints for led_running_light
## Board: Digilent Arty S7-50
## FPGA: Xilinx Spartan-7 XC7S50-CSGA324-1

## System Clock: 100 MHz (Pin E3)
set_property -dict { PACKAGE_PIN E3   IOSTANDARD LVCMOS33 } [get_ports CLK]
create_clock -period 10.000 -name sys_clk_pin -waveform {0.000 5.000} [get_ports CLK]

## Active-High Reset: BTN0 / CPU_RESET (Pin D17)
set_property -dict { PACKAGE_PIN D17  IOSTANDARD LVCMOS33 } [get_ports RESET]

## User LEDs (LD0-LD3)
## LD0 (Pin H17), LD1 (Pin K15), LD2 (Pin J15), LD3 (Pin H15)
set_property -dict { PACKAGE_PIN H17  IOSTANDARD LVCMOS33 } [get_ports {LED[0]}]
set_property -dict { PACKAGE_PIN K15  IOSTANDARD LVCMOS33 } [get_ports {LED[1]}]
set_property -dict { PACKAGE_PIN J15  IOSTANDARD LVCMOS33 } [get_ports {LED[2]}]
set_property -dict { PACKAGE_PIN H15  IOSTANDARD LVCMOS33 } [get_ports {LED[3]}]

## Optional: Verhindere DRC-Warnungen für ungenutzte Pins
# set_property SEVERITY {Warning} [get_drc_checks NSTD-1]
# set_property SEVERITY {Warning} [get_drc_checks UCIO-1]
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
        "arty_running_light": {
            "entity": ARTY_RUNNING_LIGHT_ENTITY_T,
            "architecture": ARTY_RUNNING_LIGHT_ARCH_T,
            "tb_entity": ARTY_RUNNING_LIGHT_TB_ENTITY_T,
            "tb_architecture": ARTY_RUNNING_LIGHT_TB_ARCH_T,
            "testbench": ARTY_RUNNING_LIGHT_TB_T,
            "xdc": ARTY_S7_50_XDC_T,
        },
    }

    @classmethod
    def render(cls, template_name: str, template_key: str, **kwargs) -> str:
        template = cls.TEMPLATES[template_name][template_key]
        return template.render(**kwargs)
