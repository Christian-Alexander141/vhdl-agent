-- Unabhängige Referenz-Testbench (Benchmark), dem System nicht bekannt.
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity ref_hamming_decoder_tb is
end entity;

architecture sim of ref_hamming_decoder_tb is
    signal codeword : std_logic_vector(6 downto 0) := (others => '0');
    signal data     : std_logic_vector(3 downto 0);
    signal err      : std_logic;

    -- Bitreihenfolge laut Prompt: p1 p2 d1 p3 d2 d3 d4 (Bit 6 = p1, Bit 0 = d4)
    function encode(d : std_logic_vector(3 downto 0)) return std_logic_vector is
        variable d1, d2, d3, d4, p1, p2, p3 : std_logic;
    begin
        d1 := d(3); d2 := d(2); d3 := d(1); d4 := d(0);
        p1 := d1 xor d2 xor d4;
        p2 := d1 xor d3 xor d4;
        p3 := d2 xor d3 xor d4;
        return p1 & p2 & d1 & p3 & d2 & d3 & d4;
    end function;
begin
    dut: entity work.hamming_decoder port map (codeword => codeword, data => data, error => err);

    process
        variable cw : std_logic_vector(6 downto 0);
        variable d  : std_logic_vector(3 downto 0);
    begin
        for v in 0 to 15 loop
            d := std_logic_vector(to_unsigned(v, 4));
            cw := encode(d);
            codeword <= cw; wait for 10 ns;
            assert data = d report "REF_FAIL clean word " & integer'image(v) severity error;
            assert err = '0' report "REF_FAIL error flag on clean word " & integer'image(v) severity error;
            for b in 0 to 6 loop
                codeword <= cw xor std_logic_vector(shift_left(to_unsigned(1, 7), b)); wait for 10 ns;
                assert data = d report "REF_FAIL correction data=" & integer'image(v) & " bit=" & integer'image(b) severity error;
                assert err = '1' report "REF_FAIL error flag data=" & integer'image(v) & " bit=" & integer'image(b) severity error;
            end loop;
        end loop;
        report "TB_COMPLETE" severity note;
        wait;
    end process;
end architecture;
