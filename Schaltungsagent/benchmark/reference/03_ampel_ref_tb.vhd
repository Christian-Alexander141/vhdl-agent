-- Unabhängige Referenz-Testbench (Benchmark), dem System nicht bekannt.
-- Prüft Sicherheit (je Richtung genau eine Lampe, nie beide Richtungen
-- gleichzeitig nicht-rot), Phasenfolge und Phasenlängen. Die exakte
-- Taktzählung lässt der Prompt offen, daher ±2 Takte Toleranz.
library ieee;
use ieee.std_logic_1164.all;

entity ref_ampel_tb is
end entity;

architecture sim of ref_ampel_tb is
    signal clk  : std_logic := '0';
    signal rst  : std_logic := '1';
    signal mr, my, mg, sr, sy, sg : std_logic;
    signal done : boolean := false;

    type phase_t is (P_RR, P_MG, P_MY, P_SG, P_SY, P_BAD);
    function phase_name(p : phase_t) return string is
    begin
        case p is
            when P_RR => return "allrot";
            when P_MG => return "haupt-gruen";
            when P_MY => return "haupt-gelb";
            when P_SG => return "neben-gruen";
            when P_SY => return "neben-gelb";
            when P_BAD => return "ungueltig";
        end case;
    end function;
begin
    dut: entity work.ampel port map (
        clk => clk, rst => rst,
        main_red => mr, main_yellow => my, main_green => mg,
        side_red => sr, side_yellow => sy, side_green => sg
    );
    clk <= not clk after 5 ns when not done else '0';

    process
        function classify(mr, my, mg, sr, sy, sg : std_logic) return phase_t is
            variable m, s : std_logic_vector(2 downto 0);
        begin
            m := mr & my & mg;
            s := sr & sy & sg;
            if m = "100" and s = "100" then return P_RR;
            elsif m = "001" and s = "100" then return P_MG;
            elsif m = "010" and s = "100" then return P_MY;
            elsif m = "100" and s = "001" then return P_SG;
            elsif m = "100" and s = "010" then return P_SY;
            else return P_BAD;
            end if;
        end function;

        variable cur, prev : phase_t := P_RR;
        variable run_len   : natural := 0;
        variable seen      : natural := 0;
        variable expect_next : phase_t := P_MG;

        procedure check_len(p : phase_t; n : natural) is
        begin
            case p is
                when P_MG | P_SG =>
                    assert n >= 28 and n <= 32
                        report "REF_FAIL Laenge " & phase_name(p) & " = " & integer'image(n) & " Takte (erwartet ~30)" severity error;
                when P_MY | P_SY =>
                    assert n >= 2 and n <= 6
                        report "REF_FAIL Laenge " & phase_name(p) & " = " & integer'image(n) & " Takte (erwartet ~4)" severity error;
                when P_RR =>
                    assert n <= 3
                        report "REF_FAIL Allrot-Phase " & integer'image(n) & " Takte (erwartet ~1)" severity error;
                when others => null;
            end case;
        end procedure;
    begin
        rst <= '1';
        wait until rising_edge(clk); wait until rising_edge(clk); wait for 1 ns;
        assert classify(mr, my, mg, sr, sy, sg) = P_RR
            report "REF_FAIL nach Reset nicht beide Richtungen rot" severity error;
        rst <= '0';

        prev := P_RR;
        run_len := 0;
        for cycle in 1 to 200 loop
            wait until rising_edge(clk); wait for 1 ns;
            cur := classify(mr, my, mg, sr, sy, sg);
            assert cur /= P_BAD
                report "REF_FAIL unzulaessige Lampenkombination in Takt " & integer'image(cycle) severity error;
            if cur = prev then
                run_len := run_len + 1;
            else
                -- Phase prev ist beendet: Länge (außer der ersten Allrot-Phase nach Reset) und Folge prüfen.
                if seen > 0 then
                    check_len(prev, run_len);
                end if;
                if cur = P_MG or cur = P_SG then
                    assert prev = P_RR
                        report "REF_FAIL keine Allrot-Phase vor " & phase_name(cur) severity error;
                end if;
                if cur /= P_RR then
                    assert cur = expect_next
                        report "REF_FAIL Phasenfolge: " & phase_name(cur) & " statt " & phase_name(expect_next) severity error;
                    case cur is
                        when P_MG => expect_next := P_MY;
                        when P_MY => expect_next := P_SG;
                        when P_SG => expect_next := P_SY;
                        when P_SY => expect_next := P_MG;
                        when others => null;
                    end case;
                end if;
                seen := seen + 1;
                prev := cur;
                run_len := 1;
            end if;
        end loop;
        assert seen >= 6 report "REF_FAIL kein vollstaendiger Zyklus in 200 Takten" severity error;
        report "TB_COMPLETE" severity note;
        done <= true;
        wait;
    end process;
end architecture;
