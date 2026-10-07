library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
use IEEE.NUMERIC_STD.ALL;

entity bootstrap_tb is
end entity bootstrap_tb;

architecture tb of bootstrap_tb is

    constant CLK_PERIOD : time := 10 ns;

    signal clk  : std_logic := '0';
    signal rst  : std_logic := '0';
    signal data_out : std_logic_vector(7 downto 0);
    signal uart_rx : std_logic := '0';
    signal uart_tx : std_logic;

begin

    uut: entity work.bootstrap
        port map (
            clk => clk,
            rst => rst,
            data_out => data_out,
            uart_rx => uart_rx,
            uart_tx => uart_tx
        );

    clk_process: process
    begin
        clk <= '0';
        wait for CLK_PERIOD/2;
        clk <= '1';
        wait for CLK_PERIOD/2;
    end process;

    stim_process: process
    begin
        rst <= '1';
        wait for 2 * CLK_PERIOD;

        rst <= '0';
        wait for CLK_PERIOD;

        uart_rx <= '1';
        wait for CLK_PERIOD * 8;

        uart_rx <= '0';
        wait for CLK_PERIOD * 8;

        uart_rx <= '1';
        wait for CLK_PERIOD * 8;

        wait;
    end process;

    check_process: process
    begin
        wait for 2 * CLK_PERIOD after rst'event;

        if data_out /= "00000000" then
            assert false
                report "FAIL: data_out not initialized to zero after reset"
                severity error;
        end if;

        wait for 256 * CLK_PERIOD;

        if data_out /= "00000001" then
            assert false
                report "FAIL: data_out not incremented correctly"
                severity error;
        end if;

        assert false
            report "TB_COMPLETE"
            severity note;
        wait;
    end process;

end architecture tb;