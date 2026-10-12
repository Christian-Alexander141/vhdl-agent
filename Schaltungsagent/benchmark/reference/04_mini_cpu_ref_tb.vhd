-- Unabhängige Referenz-Testbench (Benchmark), dem System nicht bekannt.
-- Prüft das Demoprogramm (OUT-Folge und Endzustand in allen Anzeigen),
-- einen Reset mitten im Programm und den Einzelschritt mit Entprellung.
-- Die Reihenfolge der Werte wird exakt geprüft, Zeitpunkte mit Spielraum.
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity ref_mini_cpu_tb is
end entity;

architecture sim of ref_mini_cpu_tb is
    signal clk      : std_logic := '0';
    signal rst      : std_logic := '1';
    signal btn_step : std_logic := '0';
    signal sw       : std_logic_vector(2 downto 0) := "000";
    signal led      : std_logic_vector(3 downto 0);
    signal done     : boolean := false;
begin
    dut: entity work.mini_cpu
        generic map (TICK_CYCLES => 4, DEBOUNCE_CYCLES => 2)
        port map (clk => clk, rst => rst, btn_step => btn_step, sw => sw, led => led);

    clk <= not clk after 5 ns when not done else '0';

    process
        type int_array is array (natural range <>) of integer;
        constant EXPECTED : int_array := (1, 2, 3, 5, 8, 13);
        variable idx    : natural := 0;
        variable last   : std_logic_vector(3 downto 0);
        variable errors : natural := 0;

        procedure cycles(n : natural) is
        begin
            for i in 1 to n loop
                wait until rising_edge(clk);
            end loop;
        end procedure;

        procedure expect(value : std_logic_vector(3 downto 0); what : string) is
        begin
            if led /= value then
                report "REF_FAIL " & what & ": erwartet " & to_string(value)
                       & ", erhalten " & to_string(led) severity error;
                errors := errors + 1;
            end if;
        end procedure;

        procedure do_reset is
        begin
            rst <= '1';
            cycles(4);
            rst <= '0';
        end procedure;

        procedure press(high_cycles, low_cycles : natural) is
        begin
            btn_step <= '1';
            cycles(high_cycles);
            btn_step <= '0';
            cycles(low_cycles);
        end procedure;
    begin
        -- 1. Automatik, Anzeige OUT: Folge 1, 2, 3, 5, 8, 13, danach Halt.
        sw <= "000";
        do_reset;
        last := "0000";
        for i in 1 to 600 loop  -- 58 Befehle zu je 4 Takten, also rund 236 Takte
            wait until rising_edge(clk);
            if led /= last then
                if idx > EXPECTED'high then
                    report "REF_FAIL zusätzlicher OUT-Wert " & to_string(led) severity error;
                    errors := errors + 1;
                elsif to_integer(unsigned(led)) /= EXPECTED(idx) then
                    report "REF_FAIL OUT-Wert Nr. " & integer'image(idx + 1) & ": erwartet "
                           & integer'image(EXPECTED(idx)) & ", erhalten " & to_string(led) severity error;
                    errors := errors + 1;
                end if;
                idx := idx + 1;
                last := led;
            end if;
        end loop;
        if idx /= EXPECTED'length then
            report "REF_FAIL " & integer'image(idx) & " statt 6 OUT-Werten" severity error;
            errors := errors + 1;
        end if;
        expect("1101", "OUT nach dem Anhalten");
        sw <= "001";
        cycles(5);
        expect("0101", "ACC nach dem Anhalten");
        sw <= "010";
        cycles(5);
        expect("1111", "PC nach dem Anhalten");
        sw <= "011";
        cycles(5);
        expect("1010", "Status nach dem Anhalten");
        cycles(100);
        expect("1010", "Status bleibt nach dem Anhalten");

        -- 2. Reset mitten im Programm: Neustart von vorn.
        sw <= "000";
        do_reset;
        expect("0000", "OUT direkt nach dem Reset");
        cycles(100);  -- OUT steht jetzt auf 3
        expect("0011", "OUT nach 100 Takten");
        do_reset;
        expect("0000", "OUT nach dem zweiten Reset");
        cycles(30);
        expect("0001", "OUT nach dem Neustart");

        -- 3. Einzelschritt, Anzeige ACC bzw. PC.
        sw <= "101";
        do_reset;
        cycles(40);
        expect("0000", "ACC im Einzelschritt ohne Tastendruck");
        press(1, 20);
        expect("0000", "ACC nach einem Impuls kürzer als DEBOUNCE_CYCLES");
        press(10, 20);
        expect("0001", "ACC nach dem ersten Schritt (LDI 1)");
        sw <= "110";
        cycles(5);
        expect("0001", "PC nach dem ersten Schritt");
        press(10, 20);
        expect("0010", "PC nach dem zweiten Schritt");
        cycles(60);
        expect("0010", "PC ohne weiteren Tastendruck");
        sw <= "101";
        cycles(5);
        expect("0001", "ACC nach STA 0");

        if errors > 0 then
            report "REF_FAIL " & integer'image(errors) & " Abweichungen" severity error;
        end if;
        report "TB_COMPLETE";
        done <= true;
        wait;
    end process;
end architecture;
