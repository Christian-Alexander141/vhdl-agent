library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
library std;
use std.env.all;

entity input_sync_tb is
end entity input_sync_tb;

architecture sim of input_sync_tb is
  constant CLK_PERIOD : time := 10 ns;

  signal clk : std_logic := '0';

  -- single-bit instance with INIT=0 (models sw/btn_step idle 0)
  signal s_in  : std_logic_vector(0 downto 0) := "0";
  signal s_out : std_logic_vector(0 downto 0);

  -- single-bit instance with INIT=1 (models uart_rx idle 1)
  signal u_in  : std_logic_vector(0 downto 0) := "1";
  signal u_out : std_logic_vector(0 downto 0);

  -- vector instance with WIDTH=4 (proves multi-bit sync)
  signal v_in  : std_logic_vector(3 downto 0) := "0110";
  signal v_out : std_logic_vector(3 downto 0);

  signal tb_done : boolean := false;
begin
  clk <= not clk after CLK_PERIOD / 2 when not tb_done else '0';

  dut_s: entity work.input_sync
    generic map (
      INIT  => 0,
      WIDTH => 1
    )
    port map (
      clk      => clk,
      data_in  => s_in,
      data_out => s_out
    );

  dut_u: entity work.input_sync
    generic map (
      INIT  => 1,
      WIDTH => 1
    )
    port map (
      clk      => clk,
      data_in  => u_in,
      data_out => u_out
    );

  dut_v: entity work.input_sync
    generic map (
      INIT  => 6,
      WIDTH => 4
    )
    port map (
      clk      => clk,
      data_in  => v_in,
      data_out => v_out
    );

  stim: process
    procedure wait_cyc(n : positive) is
    begin
      for i in 1 to n loop
        wait until rising_edge(clk);
        wait for 1 ns;
      end loop;
    end procedure;
  begin
    -- Stabiler Start: Eingaenge = INIT-Werte, kein Takt vergangen.
    s_in <= "0";
    u_in <= "1";
    v_in <= "0110";
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " init s=" & to_string(s_out) & " u=" & to_string(u_out) & " v=" & to_string(v_out) severity note;
    assert s_out = "0" report "REQ R38: Startwert 0 (sw/btn_step idle 0)" severity error;
    assert u_out = "1" report "REQ R38: Startwert 1 (uart_rx idle 1)" severity error;
    assert v_out = "0110" report "REQ R38: Startwert INIT=6 (0110) bei WIDTH=4" severity error;

    -- Konstante Eingaenge: Ausgaenge bleiben stabil (Synchronisierer laeuft, kein Reset).
    wait_cyc(2);
    report "CHECK t=" & time'image(now) & " hold s=" & to_string(s_out) & " u=" & to_string(u_out) & " v=" & to_string(v_out) severity note;
    assert s_out = "0" report "REQ R38: konstanter Eingang haelt Ausgang 0 (zwei FF, kein Reset)" severity error;
    assert u_out = "1" report "REQ R38: konstanter Eingang haelt Ausgang 1" severity error;
    assert v_out = "0110" report "REQ R38: Vektor haelt INIT bei konstantem Eingang" severity error;

    -- TC1: steigende Flanke auf s (btn_step-Modell) braucht genau 2 Takte.
    s_in <= "1";
    wait_cyc(1);
    report "CHECK t=" & time'image(now) & " s nach 1 Takt s=" & to_string(s_out) severity note;
    assert s_out = "0" report "REQ R38: nach 1 Takt noch alter Wert (erste Stufe)" severity error;
    assert s_out = "0" report "REQ R5: Tastendruck ist nach 1 Takt noch nicht am synchronisierten Ausgang" severity error;
    wait_cyc(1);
    report "CHECK t=" & time'image(now) & " s nach 2 Takten s=" & to_string(s_out) severity note;
    assert s_out = "1" report "REQ R38: nach 2 Takten neuer Wert (zweistufig synchronisiert)" severity error;
    assert s_out = "1" report "REQ R5: Tastendruck erscheint nach 2 Takten synchronisiert (btn_step-Pfad)" severity error;

    -- TC2: fallende Flanke auf u (uart_rx-Modell Startbit) braucht genau 2 Takte.
    u_in <= "0";
    wait_cyc(1);
    report "CHECK t=" & time'image(now) & " u nach 1 Takt u=" & to_string(u_out) severity note;
    assert u_out = "1" report "REQ R38: uart_rx fallende Flanke nach 1 Takt noch nicht sichtbar" severity error;
    wait_cyc(1);
    report "CHECK t=" & time'image(now) & " u nach 2 Takten u=" & to_string(u_out) severity note;
    assert u_out = "0" report "REQ R38: uart_rx Startbit (0) nach 2 Takten synchronisiert" severity error;

    -- TC3: Vektorwechsel wird bitgenau nach 2 Takten uebernommen.
    v_in <= "1101";
    wait_cyc(1);
    report "CHECK t=" & time'image(now) & " v nach 1 Takt v=" & to_string(v_out) severity note;
    assert v_out = "0110" report "REQ R38: Vektor nach 1 Takt noch alt (WIDTH=4, erste Stufe)" severity error;
    wait_cyc(1);
    report "CHECK t=" & time'image(now) & " v nach 2 Takten v=" & to_string(v_out) severity note;
    assert v_out = "1101" report "REQ R38: Vektor nach 2 Takten bitgenau uebernommen (WIDTH=4)" severity error;

    -- TC4: kurzer 1-Takt-Impuls wird verzoegert, nicht gefiltert (Unterschied zum Entpreller).
    s_in <= "0";
    wait_cyc(2);
    assert s_out = "0" report "REQ R38: Rueckkehr zu 0 nach 2 Takten" severity error;
    report "CHECK t=" & time'image(now) & " s Basis s=" & to_string(s_out) severity note;
    s_in <= "1";
    wait_cyc(1);
    s_in <= "0";
    wait_cyc(1);
    report "CHECK t=" & time'image(now) & " s Puls+2 Takte s=" & to_string(s_out) severity note;
    assert s_out = "1" report "REQ R38: 1-Takt-Impuls erscheint verzoegert am Ausgang (kein Filtern)" severity error;
    assert s_out = "1" report "REQ R5: kurzer btn_step-Pegel wird synchronisiert weitergegeben" severity error;
    wait_cyc(1);
    report "CHECK t=" & time'image(now) & " s Puls+3 Takte s=" & to_string(s_out) severity note;
    assert s_out = "0" report "REQ R38: Impulsende erscheint ebenfalls 2 Takte spaeter" severity error;

    -- TC5: Dauerbetrieb (laeuft immer): mehrere Wechsel hintereinander, je 2 Takte Latenz.
    v_in <= "0011";
    u_in <= "1";
    wait_cyc(2);
    report "CHECK t=" & time'image(now) & " cont v=" & to_string(v_out) & " u=" & to_string(u_out) severity note;
    assert v_out = "0011" report "REQ R38: Synchronisierer laeuft immer (Vektor folgt weiter)" severity error;
    assert u_out = "1" report "REQ R38: uart_rx idle 1 wird wieder synchronisiert" severity error;
    v_in <= "1010";
    wait_cyc(1);
    assert v_out = "0011" report "REQ R38: Dauerbetrieb Latenz weiter 1 Takt alt" severity error;
    wait_cyc(1);
    assert v_out = "1010" report "REQ R38: Dauerbetrieb Latenz nach 2 Takten neu" severity error;
    report "CHECK t=" & time'image(now) & " cont2 v=" & to_string(v_out) severity note;

    -- TC6: alle Bits unabhaengig (WIDTH-Nachweis, kein gemeinsamer Kurzschluss).
    v_in <= "0101";
    wait_cyc(2);
    assert v_out = "0101" report "REQ R38: Vektor 0101 bitgenau (WIDTH-Generik)" severity error;
    v_in <= "1010";
    wait_cyc(2);
    assert v_out = "1010" report "REQ R38: Vektor 1010 bitgenau (jedes Bit eigene FF-Kette)" severity error;
    report "CHECK t=" & time'image(now) & " final s=" & to_string(s_out) & " u=" & to_string(u_out) & " v=" & to_string(v_out) severity note;

    tb_done <= true;
    report "TB_COMPLETE" severity note;
    std.env.stop(0);
    wait;
  end process stim;

end architecture sim;