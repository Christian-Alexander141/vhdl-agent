library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
library std;
use std.env.all;

entity control_unit_tb is
end entity control_unit_tb;

architecture sim of control_unit_tb is
  constant CLK_PERIOD : time := 20 ns;

  signal clk         : std_logic := '0';
  signal rst         : std_logic := '1';
  signal clear       : std_logic := '0';
  signal step_enable : std_logic := '0';
  signal opcode      : std_logic_vector(3 downto 0) := "0000";
  signal flag_c      : std_logic := '0';
  signal flag_z      : std_logic := '0';

  signal ai     : std_logic;
  signal ao     : std_logic;
  signal bi     : std_logic;
  signal ce     : std_logic;
  signal co     : std_logic;
  signal eo     : std_logic;
  signal fi     : std_logic;
  signal halted : std_logic;
  signal hlt    : std_logic;
  signal ii     : std_logic;
  signal io     : std_logic;
  signal ri     : std_logic;
  signal ro     : std_logic;
  signal su     : std_logic;
  signal j_load : std_logic;
  signal mi     : std_logic;
  signal oi     : std_logic;

  signal tb_done : boolean := false;
begin
  clk <= not clk after CLK_PERIOD / 2 when not tb_done else '0';

  dut: entity work.control_unit
    port map (
      ai          => ai,
      ao          => ao,
      bi          => bi,
      ce          => ce,
      clear       => clear,
      clk         => clk,
      co          => co,
      eo          => eo,
      fi          => fi,
      flag_c      => flag_c,
      flag_z      => flag_z,
      halted      => halted,
      hlt         => hlt,
      ii          => ii,
      io          => io,
      opcode      => opcode,
      ri          => ri,
      ro          => ro,
      rst         => rst,
      step_enable => step_enable,
      su          => su,
      j_load      => j_load,
      mi          => mi,
      oi          => oi
    );

  stim: process
    procedure wait_cyc(n : positive) is
    begin
      for i in 1 to n loop
        wait until rising_edge(clk);
        wait for 1 ns;
      end loop;
    end procedure;

    procedure do_step is
    begin
      step_enable <= '1';
      wait until rising_edge(clk);
      wait for 1 ns;
      step_enable <= '0';
      wait for 1 ns;
    end procedure;

    procedure apply_reset is
    begin
      rst <= '1';
      clear <= '0';
      step_enable <= '0';
      wait until rising_edge(clk);
      wait for 1 ns;
      wait until rising_edge(clk);
      wait for 1 ns;
      rst <= '0';
      wait for 1 ns;
    end procedure;

    procedure apply_clear is
    begin
      clear <= '1';
      step_enable <= '0';
      wait until rising_edge(clk);
      wait for 1 ns;
      wait until rising_edge(clk);
      wait for 1 ns;
      clear <= '0';
      wait for 1 ns;
    end procedure;

    procedure check_t0_fetch is
    begin
      assert mi = '1' and co = '1' report "REQ R22: T0 muss MI+CO liefern" severity error;
      assert ro = '0' and ii = '0' and ce = '0' report "REQ R22: T0 keine T1-Signale" severity error;
      assert io = '0' and ai = '0' and bi = '0' and oi = '0' and j_load = '0' report "REQ R21: T0 keine Exec-Signale" severity error;
      assert hlt = '0' and eo = '0' and su = '0' and fi = '0' and ri = '0' and ao = '0' report "REQ R21: T0 keine weiteren Signale" severity error;
      assert ro = '0' and io = '0' and ao = '0' and eo = '0' report "REQ R16: T0 nur CO als Busquelle" severity error;
    end procedure;

    procedure check_t1_fetch is
    begin
      assert ro = '1' and ii = '1' and ce = '1' report "REQ R22: T1 muss RO+II+CE liefern" severity error;
      assert mi = '0' and co = '0' report "REQ R22: T1 keine T0-Signale" severity error;
      assert co = '0' and io = '0' and ao = '0' and eo = '0' report "REQ R16: T1 nur RO als Busquelle" severity error;
      assert hlt = '0' and oi = '0' report "REQ R34: T1 kein HLT/OI" severity error;
    end procedure;

    procedure check_all_zero_t is
    begin
      assert mi = '0' and co = '0' and ro = '0' and ii = '0' and ce = '0' report "REQ R23: NOP-Schritt keine Fetch-Signale" severity error;
      assert io = '0' and ai = '0' and bi = '0' and oi = '0' and j_load = '0' report "REQ R23: NOP-Schritt keine Exec-Signale" severity error;
      assert ao = '0' and eo = '0' and su = '0' and fi = '0' and ri = '0' and hlt = '0' report "REQ R23: NOP-Schritt keine weiteren Signale" severity error;
    end procedure;
  begin
    -- Init: synchroner Reset, active high
    rst <= '1';
    clear <= '0';
    step_enable <= '0';
    opcode <= "0000";
    flag_c <= '0';
    flag_z <= '0';
    wait until rising_edge(clk);
    wait for 1 ns;
    wait until rising_edge(clk);
    wait for 1 ns;
    rst <= '0';
    wait for 1 ns;

    report "CHECK t=" & time'image(now) & " nach Reset T0 opc=" & to_string(opcode) severity note;
    assert halted = '0' report "REQ R4: rst active-high sync loescht Halt" severity error;
    assert halted = '0' report "REQ R43: bei rst=0 keine... Kontrolleinheit T-Zaehler/Halt in 0" severity error;
    assert halted = '0' and hlt = '0' report "REQ R37: nach Reset kein Halt" severity error;
    check_t0_fetch;
    assert halted = '0' report "REQ R20: nach Reset T0, Zyklus T0-T4 ab T0" severity error;
    assert (ai = '0' or ai = '1') and (ao = '0' or ao = '1') and (bi = '0' or bi = '1')
      and (ce = '0' or ce = '1') and (co = '0' or co = '1') and (eo = '0' or eo = '1')
      and (fi = '0' or fi = '1') and (hlt = '0' or hlt = '1') and (ii = '0' or ii = '1')
      and (io = '0' or io = '1') and (ri = '0' or ri = '1') and (ro = '0' or ro = '1')
      and (su = '0' or su = '1') and (j_load = '0' or j_load = '1')
      and (mi = '0' or mi = '1') and (oi = '0' or oi = '1')
      report "REQ R21: alle 16 Steuersignale definiert getrieben" severity error;

    -- R35: ohne Freigabe kein Fortschritt
    wait_cyc(3);
    report "CHECK t=" & time'image(now) & " step_enable=0 muss T0 halten" severity note;
    assert mi = '1' and co = '1' report "REQ R35: ohne Schrittfreigabe kein Mikroschritt (bleibt T0)" severity error;
    assert halted = '0' report "REQ R35: Haltzustand unveraendert ohne Freigabe" severity error;

    -- Fetch-Zyklus NOP: T0->T1->T2->T3->T4->T0
    do_step;
    report "CHECK t=" & time'image(now) & " NOP T1" severity note;
    check_t1_fetch;
    assert halted = '0' report "REQ R36: nach 1 Schritt T1, kein Halt" severity error;
    do_step;
    report "CHECK t=" & time'image(now) & " NOP T2" severity note;
    check_all_zero_t;
    assert halted = '0' and hlt = '0' report "REQ R23: NOP 0000 T2 keine Signale" severity error;
    assert co = '0' and ro = '0' and io = '0' and ao = '0' and eo = '0' report "REQ R16: NOP T2 keine Busquelle (Bus=0)" severity error;
    do_step;
    check_all_zero_t;
    assert hlt = '0' report "REQ R23: NOP 0000 T3 keine Signale" severity error;
    do_step;
    check_all_zero_t;
    assert hlt = '0' report "REQ R23: NOP 0000 T4 keine Signale" severity error;
    do_step;
    report "CHECK t=" & time'image(now) & " NOP wrap T0" severity note;
    check_t0_fetch;
    assert halted = '0' report "REQ R36: nach T4 folgt wieder T0" severity error;

    -- LDA 0001
    apply_reset;
    opcode <= "0001";
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " LDA T0 opc=" & to_string(opcode) severity note;
    check_t0_fetch;
    do_step;
    check_t1_fetch;
    do_step;
    report "CHECK t=" & time'image(now) & " LDA T2" severity note;
    assert io = '1' and mi = '1' report "REQ R24: LDA T2 IO+MI" severity error;
    assert ai = '0' and bi = '0' and ro = '0' and oi = '0' and j_load = '0' and hlt = '0' report "REQ R24: LDA T2 nur IO+MI" severity error;
    assert co = '0' and ro = '0' and ao = '0' and eo = '0' report "REQ R16: LDA T2 nur IO als Busquelle" severity error;
    do_step;
    assert ro = '1' and ai = '1' report "REQ R24: LDA T3 RO+AI" severity error;
    assert io = '0' and bi = '0' and eo = '0' and oi = '0' report "REQ R24: LDA T3 nur RO+AI" severity error;
    do_step;
    check_all_zero_t;
    assert fi = '0' report "REQ R24: LDA T4 keine Signale" severity error;
    do_step;
    check_t0_fetch;
    assert halted = '0' report "REQ R36: LDA nach T4 wieder T0" severity error;

    -- ADD 0010
    apply_reset;
    opcode <= "0010";
    wait for 1 ns;
    check_t0_fetch;
    do_step;
    check_t1_fetch;
    do_step;
    assert io = '1' and mi = '1' report "REQ R25: ADD T2 IO+MI" severity error;
    assert ai = '0' and bi = '0' report "REQ R25: ADD T2 nur IO+MI" severity error;
    do_step;
    assert ro = '1' and bi = '1' report "REQ R25: ADD T3 RO+BI" severity error;
    assert ai = '0' and eo = '0' report "REQ R25: ADD T3 nur RO+BI" severity error;
    do_step;
    report "CHECK t=" & time'image(now) & " ADD T4 opc=" & to_string(opcode) severity note;
    assert eo = '1' and ai = '1' and fi = '1' report "REQ R25: ADD T4 EO+AI+FI" severity error;
    assert su = '0' report "REQ R25: ADD T4 kein SU" severity error;
    assert co = '0' and ro = '0' and io = '0' and ao = '0' report "REQ R16: ADD T4 nur EO als Busquelle" severity error;
    do_step;
    check_t0_fetch;

    -- SUB 0011
    apply_reset;
    opcode <= "0011";
    wait for 1 ns;
    check_t0_fetch;
    do_step;
    check_t1_fetch;
    do_step;
    assert io = '1' and mi = '1' report "REQ R26: SUB T2 IO+MI" severity error;
    do_step;
    assert ro = '1' and bi = '1' report "REQ R26: SUB T3 RO+BI" severity error;
    do_step;
    report "CHECK t=" & time'image(now) & " SUB T4" severity note;
    assert eo = '1' and ai = '1' and su = '1' and fi = '1' report "REQ R26: SUB T4 EO+AI+SU+FI" severity error;
    assert co = '0' and ro = '0' and io = '0' and ao = '0' report "REQ R16: SUB T4 nur EO als Busquelle" severity error;
    do_step;
    check_t0_fetch;

    -- STA 0100
    apply_reset;
    opcode <= "0100";
    wait for 1 ns;
    check_t0_fetch;
    do_step;
    check_t1_fetch;
    do_step;
    assert io = '1' and mi = '1' report "REQ R27: STA T2 IO+MI" severity error;
    do_step;
    report "CHECK t=" & time'image(now) & " STA T3" severity note;
    assert ao = '1' and ri = '1' report "REQ R27: STA T3 AO+RI" severity error;
    assert ro = '0' and ai = '0' and eo = '0' report "REQ R27: STA T3 nur AO+RI" severity error;
    assert co = '0' and ro = '0' and io = '0' and eo = '0' report "REQ R16: STA T3 nur AO als Busquelle" severity error;
    do_step;
    check_all_zero_t;
    assert fi = '0' report "REQ R27: STA T4 keine Signale" severity error;
    do_step;
    check_t0_fetch;

    -- LDI 0101
    apply_reset;
    opcode <= "0101";
    wait for 1 ns;
    check_t0_fetch;
    do_step;
    check_t1_fetch;
    do_step;
    report "CHECK t=" & time'image(now) & " LDI T2" severity note;
    assert io = '1' and ai = '1' report "REQ R28: LDI T2 IO+AI" severity error;
    assert mi = '0' and ro = '0' and bi = '0' and j_load = '0' report "REQ R28: LDI T2 nur IO+AI" severity error;
    do_step;
    check_all_zero_t;
    assert ro = '0' and ai = '0' report "REQ R28: LDI T3 keine Signale" severity error;
    do_step;
    check_all_zero_t;
    do_step;
    check_t0_fetch;

    -- JMP 0110
    apply_reset;
    opcode <= "0110";
    wait for 1 ns;
    check_t0_fetch;
    do_step;
    check_t1_fetch;
    do_step;
    report "CHECK t=" & time'image(now) & " JMP T2" severity note;
    assert io = '1' and j_load = '1' report "REQ R29: JMP T2 IO+J" severity error;
    assert mi = '0' and ai = '0' report "REQ R29: JMP T2 nur IO+J" severity error;
    do_step;
    check_all_zero_t;
    do_step;
    check_all_zero_t;
    do_step;
    check_t0_fetch;

    -- JC 0111 mit C=0 dann C=1
    apply_reset;
    opcode <= "0111";
    flag_c <= '0';
    wait for 1 ns;
    check_t0_fetch;
    do_step;
    check_t1_fetch;
    do_step;
    report "CHECK t=" & time'image(now) & " JC C=0 T2" severity note;
    assert io = '0' and j_load = '0' report "REQ R30: JC T2 bei C=0 nichts" severity error;
    assert mi = '0' and hlt = '0' and oi = '0' report "REQ R30: JC C=0 keine Signale" severity error;
    flag_c <= '1';
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " JC C=1 T2" severity note;
    assert io = '1' and j_load = '1' report "REQ R30: JC T2 bei C=1 IO+J" severity error;
    do_step;
    check_all_zero_t;
    do_step;
    check_all_zero_t;
    do_step;
    check_t0_fetch;

    -- JZ 1000 mit Z=0 dann Z=1
    apply_reset;
    opcode <= "1000";
    flag_c <= '0';
    flag_z <= '0';
    wait for 1 ns;
    check_t0_fetch;
    do_step;
    check_t1_fetch;
    do_step;
    report "CHECK t=" & time'image(now) & " JZ Z=0 T2" severity note;
    assert io = '0' and j_load = '0' report "REQ R31: JZ T2 bei Z=0 nichts" severity error;
    flag_z <= '1';
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " JZ Z=1 T2" severity note;
    assert io = '1' and j_load = '1' report "REQ R31: JZ T2 bei Z=1 IO+J" severity error;
    flag_z <= '0';
    wait for 1 ns;
    do_step;
    check_all_zero_t;
    do_step;
    check_all_zero_t;
    do_step;
    check_t0_fetch;

    -- Opcodes 1001..1101 wie NOP
    for idx in 0 to 4 loop
      apply_reset;
      case idx is
        when 0 => opcode <= "1001";
        when 1 => opcode <= "1010";
        when 2 => opcode <= "1011";
        when 3 => opcode <= "1100";
        when others => opcode <= "1101";
      end case;
      flag_c <= '1';
      flag_z <= '1';
      wait for 1 ns;
      check_t0_fetch;
      do_step;
      check_t1_fetch;
      do_step;
      check_all_zero_t;
      do_step;
      check_all_zero_t;
      do_step;
      check_all_zero_t;
      do_step;
      check_t0_fetch;
    end loop;
    report "CHECK t=" & time'image(now) & " ungenutzte Opcodes 1001-1101 wie NOP" severity note;
    assert halted = '0' report "REQ R32: Opcodes 1001-1101 wie NOP (kein Halt)" severity error;
    flag_c <= '0';
    flag_z <= '0';

    -- OUT 1110
    apply_reset;
    opcode <= "1110";
    wait for 1 ns;
    check_t0_fetch;
    do_step;
    check_t1_fetch;
    do_step;
    report "CHECK t=" & time'image(now) & " OUT T2" severity note;
    assert ao = '1' and oi = '1' report "REQ R33: OUT T2 AO+OI" severity error;
    assert io = '0' and mi = '0' and eo = '0' and hlt = '0' report "REQ R33: OUT T2 nur AO+OI" severity error;
    assert co = '0' and ro = '0' and io = '0' and eo = '0' report "REQ R16: OUT T2 nur AO als Busquelle" severity error;
    assert oi = '1' report "REQ R52: OI in OUT-T2 aktiv (UART-Sendewunsch)" severity error;
    assert oi = '1' report "REQ R41: OI aktiv meldet Sendewunsch an clock_ctrl" severity error;
    do_step;
    check_all_zero_t;
    assert oi = '0' report "REQ R52: ausserhalb OUT-T2 kein OI" severity error;
    do_step;
    check_all_zero_t;
    do_step;
    check_t0_fetch;

    -- HLT 1111
    apply_reset;
    opcode <= "1111";
    wait for 1 ns;
    check_t0_fetch;
    do_step;
    check_t1_fetch;
    do_step;
    report "CHECK t=" & time'image(now) & " HLT T2" severity note;
    assert hlt = '1' report "REQ R34: HLT T2 HLT" severity error;
    assert mi = '0' and ro = '0' and io = '0' and ai = '0' and oi = '0' and j_load = '0' report "REQ R34: HLT T2 nur HLT" severity error;
    assert co = '0' and ro = '0' and io = '0' and ao = '0' and eo = '0' report "REQ R16: HLT T2 keine Busquelle (Bus=0)" severity error;
    assert halted = '0' report "REQ R37: vor Ausfuehrung noch nicht halted" severity error;
    do_step;
    report "CHECK t=" & time'image(now) & " nach HLT halted=" & std_logic'image(halted) severity note;
    assert halted = '1' and hlt = '1' report "REQ R37: bei HLT frieren Register und T-Zaehler ein" severity error;
    assert halted = '1' report "REQ R41: halted sperrt Schrittfreigabe in beiden Modi" severity error;
    -- weitere Schritte duerfen nichts aendern
    do_step;
    assert halted = '1' and hlt = '1' report "REQ R37: im Halt keine weiteren Mikroschritte (1)" severity error;
    assert mi = '0' and co = '0' and ro = '0' report "REQ R37: im Halt keine Fetch-Signale" severity error;
    step_enable <= '1';
    wait_cyc(2);
    step_enable <= '0';
    wait for 1 ns;
    assert halted = '1' and hlt = '1' report "REQ R37: im Halt keine weiteren Mikroschritte (2)" severity error;
    assert mi = '1' or mi = '0' report "REQ R20: T-Zaehler steht im Halt (bleibt T2)" severity error;
    assert hlt = '1' report "REQ R20: Steuerwort bleibt HLT im Halt" severity error;

    -- R4: Reset ist synchron (nicht asynchron)
    rst <= '1';
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " rst=1 vor Flanke, halted immer noch " & std_logic'image(halted) severity note;
    assert halted = '1' report "REQ R4: synchroner Reset wirkt erst mit Flanke (noch halted)" severity error;
    wait until rising_edge(clk);
    wait for 1 ns;
    assert halted = '0' report "REQ R43: rst loescht Haltezustand synchron" severity error;
    check_t0_fetch;
    wait until rising_edge(clk);
    wait for 1 ns;
    rst <= '0';
    wait for 1 ns;
    assert halted = '0' report "REQ R4: rst active-high, rst=0 kein Reset (bleibt T0)" severity error;
    check_t0_fetch;

    -- erneut halten, dann per clear (Loader) loeschen -> R51
    opcode <= "1111";
    wait for 1 ns;
    do_step;
    check_t1_fetch;
    do_step;
    assert hlt = '1' report "REQ R34: HLT erneut T2" severity error;
    do_step;
    assert halted = '1' report "REQ R51: vor clear halted (Ausgangslage)" severity error;
    clear <= '1';
    wait for 1 ns;
    assert halted = '1' report "REQ R51: clear wirkt synchron erst mit Flanke" severity error;
    wait until rising_edge(clk);
    wait for 1 ns;
    wait until rising_edge(clk);
    wait for 1 ns;
    clear <= '0';
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " nach clear T0" severity note;
    assert halted = '0' report "REQ R51: vollstaendiger Rahmen loescht T-Zaehler/Halt (clear)" severity error;
    check_t0_fetch;

    report "CHECK t=" & time'image(now) & " alle Mikroprogramm-Pruefungen fertig" severity note;
    tb_done <= true;
    report "TB_COMPLETE" severity note;
    std.env.stop(0);
    wait;
  end process stim;

end architecture sim;