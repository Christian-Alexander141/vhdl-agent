-- Unabhängige Referenz-Testbench (Benchmark), dem System nicht bekannt.
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity ref_counter4_tb is
end entity;

architecture sim of ref_counter4_tb is
    signal clk   : std_logic := '0';
    signal rst   : std_logic := '1';
    signal en    : std_logic := '0';
    signal count : std_logic_vector(3 downto 0);
    signal done  : boolean := false;
begin
    dut: entity work.counter4 port map (clk => clk, rst => rst, en => en, count => count);
    clk <= not clk after 5 ns when not done else '0';

    process
        variable expected : natural := 0;
    begin
        rst <= '1'; en <= '1';
        wait until rising_edge(clk); wait until rising_edge(clk);
        wait for 1 ns;
        assert count = "0000" report "REF_FAIL reset: count /= 0" severity error;
        rst <= '0';
        for i in 1 to 20 loop
            wait until rising_edge(clk); wait for 1 ns;
            expected := (expected + 1) mod 16;
            assert to_integer(unsigned(count)) = expected
                report "REF_FAIL count step " & integer'image(i) & ": got " & integer'image(to_integer(unsigned(count)))
                severity error;
        end loop;
        en <= '0';
        for i in 1 to 3 loop
            wait until rising_edge(clk); wait for 1 ns;
            assert to_integer(unsigned(count)) = expected report "REF_FAIL hold with en=0" severity error;
        end loop;
        rst <= '1';
        wait until rising_edge(clk); wait for 1 ns;
        assert count = "0000" report "REF_FAIL synchronous reset" severity error;
        report "TB_COMPLETE" severity note;
        done <= true;
        wait;
    end process;
end architecture;
