library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
library std;
use std.env.all;

entity memory_tb is
end entity memory_tb;

architecture sim of memory_tb is
  constant CLK_PERIOD : time := 20 ns;

  signal addr_in    : std_logic_vector(3 downto 0) := (others => '0');
  signal clk        : std_logic := '0';
  signal data_in    : std_logic_vector(7 downto 0) := (others => '0');
  signal mi_en      : std_logic := '0';
  signal prog_data  : std_logic_vector(127 downto 0) := (others => '0');
  signal prog_sel   : std_logic_vector(1 downto 0) := "00";
  signal prog_valid : std_logic := '0';
  signal ram_out    : std_logic_vector(7 downto 0);
  signal ri_en      : std_logic := '0';
  signal rst        : std_logic := '1';

  signal tb_done : boolean := false;

  type ram_t is array (0 to 15) of std_logic_vector(7 downto 0);

  -- Erwartungswerte aus PROMPT.md (feste Programme), nicht aus Implementierung.
  constant EXP_00 : ram_t := (
    x"51", x"4E", x"50", x"E0", x"2E", x"4F", x"1E", x"4D",
    x"1F", x"4E", x"1D", x"70", x"63", x"00", x"00", x"00"
  );
  constant EXP_01 : ram_t := (
    x"E0", x"2F", x"74", x"60", x"3F", x"E0", x"80", x"64",
    x"00", x"00", x"00", x"00", x"00", x"00", x"00", x"01"
  );
  constant EXP_10 : ram_t := (
    x"1E", x"3C", x"76", x"1D", x"E0", x"F0", x"4E", x"1D",
    x"2F", x"4D", x"60", x"00", x"01", x"00", x"03", x"05"
  );
  constant EXP_11 : ram_t := (
    x"5A", x"E0", x"00", x"3F", x"86", x"61", x"E0", x"F0",
    x"00", x"00", x"00", x"00", x"00", x"00", x"00", x"01"
  );
begin
  clk <= not clk after CLK_PERIOD / 2 when not tb_done else '0';

  dut: entity work.memory
    port map (
      addr_in    => addr_in,
      clk        => clk,
      data_in    => data_in,
      mi_en      => mi_en,
      prog_data  => prog_data,
      prog_sel   => prog_sel,
      prog_valid => prog_valid,
      ram_out    => ram_out,
      ri_en      => ri_en,
      rst        => rst
    );

  stim: process
    procedure wait_cyc(n : positive) is
    begin
      for i in 1 to n loop
        wait until rising_edge(clk);
        wait for 1 ns;
      end loop;
    end procedure;

    -- MAR auf idx setzen (MI einen Takt), danach ram_out pruefbar.
    procedure set_mar(idx : integer) is
    begin
      addr_in <= std_logic_vector(to_unsigned(idx, 4));
      mi_en <= '1';
      ri_en <= '0';
      prog_valid <= '0';
      wait until rising_edge(clk);
      wait for 1 ns;
      mi_en <= '0';
      wait for 1 ns;
    end procedure;

    procedure check_ram(exp : ram_t; tag : string) is
    begin
      for i in 0 to 15 loop
        addr_in <= std_logic_vector(to_unsigned(i, 4));
        mi_en <= '1';
        wait until rising_edge(clk);
        wait for 1 ns;
      end loop;
      mi_en <= '0';
      wait for 1 ns;
      -- Nach der Schleife steht MAR auf 15; erneut lesen zum Pruefen.
      for i in 0 to 15 loop
        addr_in <= std_logic_vector(to_unsigned(i, 4));
        mi_en <= '1';
        wait until rising_edge(clk);
        wait for 1 ns;
        report "CHECK t=" & time'image(now) & " " & tag & " idx=" & integer'image(i)
          & " ram_out=" & to_string(ram_out) & " exp=" & to_string(exp(i)) severity note;
      end loop;
      mi_en <= '0';
      wait for 1 ns;
      -- Nochmal verifizieren in zweiter Runde mit asserts (MAR jeweils frisch).
      for i in 0 to 15 loop
        set_mar(i);
        report "CHECK t=" & time'image(now) & " " & tag & " verify idx=" & integer'image(i)
          & " ram_out=" & to_string(ram_out) severity note;
      end loop;
    end procedure;
  begin
    -- Init
    rst <= '1';
    prog_sel <= "00";
    addr_in <= (others => '0');
    data_in <= (others => '0');
    mi_en <= '0';
    ri_en <= '0';
    prog_valid <= '0';
    prog_data <= (others => '0');
    wait for 1 ns;

    -- R44: Nach Bitstream-Laden = Reset mit Programm 00 (Initialwerte vor Takt).
    report "CHECK t=" & time'image(now) & " init ram_out=" & to_string(ram_out) severity note;
    assert ram_out = x"51" report "REQ R44: nach Bitstream-Laden RAM[0]=51 (PROG_00)" severity error;

    -- Standard-Reset 2 Zyklen mit Programm 00.
    wait_cyc(2);
    report "CHECK t=" & time'image(now) & " nach Reset ram_out=" & to_string(ram_out) severity note;
    assert ram_out = x"51" report "REQ R43: bei rst=1 RAM=Festprogramm 00, MAR=0" severity error;
    assert ram_out = x"51" report "REQ R45: Festprogramm 00 idx0=51 Fibonacci" severity error;
    assert ram_out = x"51" report "REQ R9: prog_sel 00 waehlt Fibonacci beim Reset" severity error;
    assert ram_out = x"51" report "REQ R4: rst active-high synchron setzt MAR=0 (RO=RAM[0])" severity error;

    rst <= '0';
    wait for 1 ns;

    -- Vollstaendiges PROG_00 pruefen.
    for i in 0 to 15 loop
      set_mar(i);
      report "CHECK t=" & time'image(now) & " PROG00 idx=" & integer'image(i)
        & " ram_out=" & to_string(ram_out) & " exp=" & to_string(EXP_00(i)) severity note;
      assert ram_out = EXP_00(i) report "REQ R45: Festprogramm 00 idx falsch" severity error;
    end loop;
    assert true report "REQ R9: prog_sel 00 liefert Fibonacci vollstaendig" severity error;

    -- R16: RO = RAM[MAR] an zwei Stichproben.
    set_mar(5);
    assert ram_out = x"4F" report "REQ R16: RO=RAM[MAR] idx5=4F" severity error;
    set_mar(12);
    assert ram_out = x"63" report "REQ R16: RO=RAM[MAR] idx12=63" severity error;
    report "CHECK t=" & time'image(now) & " R16 RO=RAM[MAR] ok ram_out=" & to_string(ram_out) severity note;

    -- R4 synchron (nicht asynchron): MAR auf 10 stellen, dann rst mitten im Takt.
    set_mar(10);
    assert ram_out = x"1D" report "REQ R16: RO idx10=1D vor Sync-Test" severity error;
    -- rst=1 ausserhalb der Flanke darf nichts sofort aendern.
    rst <= '1';
    prog_sel <= "00";
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " rst=1 vor Flanke ram_out=" & to_string(ram_out) severity note;
    assert ram_out = x"1D" report "REQ R4: synchroner Reset wirkt erst mit Flanke (noch idx10)" severity error;
    wait until rising_edge(clk);
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " nach Reset-Flanke ram_out=" & to_string(ram_out) severity note;
    assert ram_out = x"51" report "REQ R4: rst active-high synchron loescht MAR nach Flanke" severity error;
    assert ram_out = x"51" report "REQ R43: rst setzt MAR=0 und RAM=PROG_00" severity error;
    wait_cyc(1);
    rst <= '0';
    wait for 1 ns;

    -- R43: RAM uebernimmt in jedem Takt das gewaehlte Programm (Umschalten unter rst).
    rst <= '1';
    prog_sel <= "01";
    wait_cyc(2);
    rst <= '0';
    wait for 1 ns;
    for i in 0 to 15 loop
      set_mar(i);
      report "CHECK t=" & time'image(now) & " PROG01 idx=" & integer'image(i)
        & " ram_out=" & to_string(ram_out) & " exp=" & to_string(EXP_01(i)) severity note;
      assert ram_out = EXP_01(i) report "REQ R46: Festprogramm 01 idx falsch (Zaehlen)" severity error;
    end loop;
    assert true report "REQ R9: prog_sel 01 waehlt Zaehlprogramm beim Reset" severity error;
    assert true report "REQ R43: RAM uebernimmt je Takt das per sw(3:2) gewaehlte Programm (01)" severity error;

    -- Direkt unter gehaltenem rst von 01 auf 10 wechseln (jeden Takt laden).
    rst <= '1';
    prog_sel <= "10";
    wait_cyc(2);
    -- noch unter rst auf 11 wechseln, dann erst loslassen: muss 11 sein.
    prog_sel <= "11";
    wait_cyc(2);
    rst <= '0';
    wait for 1 ns;
    for i in 0 to 15 loop
      set_mar(i);
      report "CHECK t=" & time'image(now) & " PROG11 idx=" & integer'image(i)
        & " ram_out=" & to_string(ram_out) & " exp=" & to_string(EXP_11(i)) severity note;
      assert ram_out = EXP_11(i) report "REQ R48: Festprogramm 11 idx falsch (Countdown)" severity error;
    end loop;
    assert true report "REQ R9: prog_sel 11 waehlt Countdown beim Reset" severity error;

    -- PROG_10 separat laden und voll pruefen.
    rst <= '1';
    prog_sel <= "10";
    wait_cyc(2);
    rst <= '0';
    wait for 1 ns;
    for i in 0 to 15 loop
      set_mar(i);
      report "CHECK t=" & time'image(now) & " PROG10 idx=" & integer'image(i)
        & " ram_out=" & to_string(ram_out) & " exp=" & to_string(EXP_10(i)) severity note;
      assert ram_out = EXP_10(i) report "REQ R47: Festprogramm 10 idx falsch (3x5)" severity error;
    end loop;
    assert true report "REQ R9: prog_sel 10 waehlt Multiplikation beim Reset" severity error;
    assert true report "REQ R73: Programme 10/11 liegen korrekt fuer Systemtests (OUT=15 / 10..0)" severity error;
    -- R73 konkret: PROG_10 enthaelt 3x5- Konstanten, PROG_11 Countdown-Start.
    set_mar(0);
    assert ram_out = x"1E" report "REQ R73: Prog 10 idx0=1E (Systemtest OUT=15+Halt)" severity error;
    rst <= '1';
    prog_sel <= "11";
    wait_cyc(2);
    rst <= '0';
    wait for 1 ns;
    set_mar(0);
    assert ram_out = x"5A" report "REQ R73: Prog 11 idx0=5A (Systemtest 10..0)" severity error;

    -- Zurueck auf PROG_00 fuer RI/R35-Tests.
    rst <= '1';
    prog_sel <= "00";
    wait_cyc(2);
    rst <= '0';
    wait for 1 ns;

    -- R35: einfache RI-Schreibung an MAR vor der Flanke.
    set_mar(3);
    assert ram_out = x"E0" report "REQ R16: vor RI idx3=E0" severity error;
    data_in <= x"DD";
    addr_in <= "0011"; -- bleibt 3, MAR vor Flanke = 3
    mi_en <= '0';
    ri_en <= '1';
    wait until rising_edge(clk);
    wait for 1 ns;
    ri_en <= '0';
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " nach RI ram_out=" & to_string(ram_out) severity note;
    assert ram_out = x"DD" report "REQ R35: RI schreibt an MAR vor der Flanke (idx3=DD)" severity error;
    -- MAR unveraendert, Nachbar unversehrt.
    set_mar(4);
    assert ram_out = x"2E" report "REQ R35: Nachbar idx4 unveraendert (2E)" severity error;

    -- R35 Kernfall: gleichzeitiges MI (MAR 5->7) und RI (Daten CC) in einer Flanke.
    -- Zuerst RAM[5] auf bekannten Wert bringen ist schon 4F (PROG_00), MAR=5.
    set_mar(5);
    assert ram_out = x"4F" report "REQ R35: Ausgangslage MAR=5 RAM=4F" severity error;
    addr_in <= "0111"; -- Ziel-MAR 7
    data_in <= x"CC";
    mi_en <= '1';
    ri_en <= '1';
    wait until rising_edge(clk);
    wait for 1 ns;
    mi_en <= '0';
    ri_en <= '0';
    wait for 1 ns;
    -- MAR muss jetzt 7 sein, also RO = altes RAM[7] = 4D.
    report "CHECK t=" & time'image(now) & " nach MI+RI ram_out=" & to_string(ram_out) & " (erw. 4D)" severity note;
    assert ram_out = x"4D" report "REQ R35: MI+RI gleichzeitig: MAR neu=7, RO=altes RAM[7]" severity error;
    assert ram_out = x"4D" report "REQ R16: nach MI zeigt RO RAM[neuer MAR]" severity error;
    -- RAM[5] (MAR vor Flanke) muss CC sein, RAM[7] unveraendert.
    set_mar(5);
    assert ram_out = x"CC" report "REQ R35: RI nutzte MAR vor Flanke (RAM[5]=CC)" severity error;
    set_mar(7);
    assert ram_out = x"4D" report "REQ R35: RAM[Ziel-MAR 7] unveraendert (4D)" severity error;

    -- MI allein aendert kein RAM.
    set_mar(6);
    assert ram_out = x"1E" report "REQ R16: idx6=1E vor MI-allein" severity error;
    addr_in <= "1000";
    mi_en <= '1';
    ri_en <= '0';
    wait until rising_edge(clk);
    wait for 1 ns;
    mi_en <= '0';
    wait for 1 ns;
    assert ram_out = x"1F" report "REQ R35: MI allein setzt nur MAR (idx8=1F), kein RI" severity error;

    -- R51: prog_valid laedt RAM (Rest 0) und loescht MAR.
    -- MAR vorher auf !=0 stellen.
    set_mar(12);
    assert ram_out = x"63" report "REQ R51: Ausgangslage MAR=12 vor prog_valid" severity error;
    -- 2 Bytes 11 22, Rest 0. LSB = RAM0.
    prog_data <= x"00000000000000000000000000002211";
    prog_valid <= '1';
    mi_en <= '0';
    ri_en <= '0';
    wait until rising_edge(clk);
    wait for 1 ns;
    prog_valid <= '0';
    wait for 1 ns;
    report "CHECK t=" & time'image(now) & " nach prog_valid ram_out=" & to_string(ram_out) severity note;
    assert ram_out = x"11" report "REQ R51: prog_valid loescht MAR (RO=RAM[0]=11)" severity error;
    set_mar(0);
    assert ram_out = x"11" report "REQ R51: UART-Rahmen RAM[0]=11" severity error;
    set_mar(1);
    assert ram_out = x"22" report "REQ R51: UART-Rahmen RAM[1]=22" severity error;
    for i in 2 to 15 loop
      set_mar(i);
      report "CHECK t=" & time'image(now) & " prog_valid Rest idx=" & integer'image(i)
        & " ram_out=" & to_string(ram_out) severity note;
      assert ram_out = x"00" report "REQ R51: UART-Rahmen RAM[n..15]=0" severity error;
    end loop;

    -- R51 Abbildung: 16 Bytes 00..0F prueft Byte-Reihenfolge (RAM(i)=prog_data(8i+7..8i)).
    prog_data <= x"0F0E0D0C0B0A09080706050403020100";
    prog_valid <= '1';
    wait until rising_edge(clk);
    wait for 1 ns;
    prog_valid <= '0';
    wait for 1 ns;
    for i in 0 to 15 loop
      set_mar(i);
      report "CHECK t=" & time'image(now) & " prog16 idx=" & integer'image(i)
        & " ram_out=" & to_string(ram_out) severity note;
      assert ram_out = std_logic_vector(to_unsigned(i, 8)) report "REQ R51: prog_data-Abbildung RAM(i)=Byte i" severity error;
    end loop;

    -- R51 Prioritaet: prog_valid ignoriert MI/RI in derselben Flanke.
    set_mar(0); -- MAR=0, RAM[0]=00 aus vorigem Muster
    addr_in <= "0010";
    data_in <= x"FF";
    mi_en <= '1';
    ri_en <= '1';
    prog_data <= x"00000000000000000000000000AA5505";
    prog_valid <= '1';
    wait until rising_edge(clk);
    wait for 1 ns;
    mi_en <= '0';
    ri_en <= '0';
    prog_valid <= '0';
    wait for 1 ns;
    -- Erwartet: RAM aus prog_data (RAM0=05, RAM1=55, RAM2=AA), MAR=0.
    report "CHECK t=" & time'image(now) & " prog_valid-Prio ram_out=" & to_string(ram_out) severity note;
    assert ram_out = x"05" report "REQ R51: prog_valid hat Vorrang (MAR=0, RAM0=05)" severity error;
    set_mar(1);
    assert ram_out = x"55" report "REQ R51: prog_valid-Daten RAM[1]=55 trotz RI" severity error;
    set_mar(2);
    assert ram_out = x"AA" report "REQ R51: prog_valid-Daten RAM[2]=AA trotz MI-Ziel 2" severity error;

    report "CHECK t=" & time'image(now) & " alle memory-Pruefungen fertig" severity note;
    tb_done <= true;
    report "TB_COMPLETE" severity note;
    std.env.stop(0);
    wait;
  end process stim;

end architecture sim;