library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity program_rom_tb is
end entity program_rom_tb;

architecture sim of program_rom_tb is

  signal addr : std_logic_vector(3 downto 0) := (others => '0');
  signal data : std_logic_vector(7 downto 0);

begin

  dut: entity work.program_rom
    port map (
      addr => addr,
      data => data
    );

  stim: process
    variable checked : integer := 0;
  begin
    -- ROM[0] = x"11" LDI 1
    addr <= x"0"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " addr=" & to_hstring(addr) & " data=" & to_hstring(data);
    assert data = x"11" report "REQ R28: ROM[0] muss x11 (LDI 1) sein, ist " & to_hstring(data) severity error;
    checked := checked + 1;

    -- ROM[1] = x"30" STA 0
    addr <= x"1"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " addr=" & to_hstring(addr) & " data=" & to_hstring(data);
    assert data = x"30" report "REQ R29: ROM[1] muss x30 (STA 0) sein, ist " & to_hstring(data) severity error;
    checked := checked + 1;

    -- ROM[2] = x"31" STA 1
    addr <= x"2"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " addr=" & to_hstring(addr) & " data=" & to_hstring(data);
    assert data = x"31" report "REQ R30: ROM[2] muss x31 (STA 1) sein, ist " & to_hstring(data) severity error;
    checked := checked + 1;

    -- ROM[3] = x"E0" OUT
    addr <= x"3"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " addr=" & to_hstring(addr) & " data=" & to_hstring(data);
    assert data = x"E0" report "REQ R31: ROM[3] muss xE0 (OUT) sein, ist " & to_hstring(data) severity error;
    checked := checked + 1;

    -- ROM[4] = x"20" LDA 0
    addr <= x"4"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " addr=" & to_hstring(addr) & " data=" & to_hstring(data);
    assert data = x"20" report "REQ R32: ROM[4] muss x20 (LDA 0) sein, ist " & to_hstring(data) severity error;
    checked := checked + 1;

    -- ROM[5] = x"41" ADD 1
    addr <= x"5"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " addr=" & to_hstring(addr) & " data=" & to_hstring(data);
    assert data = x"41" report "REQ R33: ROM[5] muss x41 (ADD 1) sein, ist " & to_hstring(data) severity error;
    checked := checked + 1;

    -- ROM[6] = x"DE" JC 14
    addr <= x"6"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " addr=" & to_hstring(addr) & " data=" & to_hstring(data);
    assert data = x"DE" report "REQ R34: ROM[6] muss xDE (JC 14) sein, ist " & to_hstring(data) severity error;
    checked := checked + 1;

    -- ROM[7] = x"32" STA 2
    addr <= x"7"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " addr=" & to_hstring(addr) & " data=" & to_hstring(data);
    assert data = x"32" report "REQ R35: ROM[7] muss x32 (STA 2) sein, ist " & to_hstring(data) severity error;
    checked := checked + 1;

    -- ROM[8] = x"21" LDA 1
    addr <= x"8"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " addr=" & to_hstring(addr) & " data=" & to_hstring(data);
    assert data = x"21" report "REQ R36: ROM[8] muss x21 (LDA 1) sein, ist " & to_hstring(data) severity error;
    checked := checked + 1;

    -- ROM[9] = x"30" STA 0
    addr <= x"9"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " addr=" & to_hstring(addr) & " data=" & to_hstring(data);
    assert data = x"30" report "REQ R37: ROM[9] muss x30 (STA 0) sein, ist " & to_hstring(data) severity error;
    checked := checked + 1;

    -- ROM[10] = x"22" LDA 2
    addr <= x"A"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " addr=" & to_hstring(addr) & " data=" & to_hstring(data);
    assert data = x"22" report "REQ R38: ROM[10] muss x22 (LDA 2) sein, ist " & to_hstring(data) severity error;
    checked := checked + 1;

    -- ROM[11] = x"31" STA 1
    addr <= x"B"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " addr=" & to_hstring(addr) & " data=" & to_hstring(data);
    assert data = x"31" report "REQ R39: ROM[11] muss x31 (STA 1) sein, ist " & to_hstring(data) severity error;
    checked := checked + 1;

    -- ROM[12] = x"E0" OUT
    addr <= x"C"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " addr=" & to_hstring(addr) & " data=" & to_hstring(data);
    assert data = x"E0" report "REQ R40: ROM[12] muss xE0 (OUT) sein, ist " & to_hstring(data) severity error;
    checked := checked + 1;

    -- ROM[13] = x"B4" JMP 4
    addr <= x"D"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " addr=" & to_hstring(addr) & " data=" & to_hstring(data);
    assert data = x"B4" report "REQ R41: ROM[13] muss xB4 (JMP 4) sein, ist " & to_hstring(data) severity error;
    checked := checked + 1;

    -- ROM[14] = x"F0" HLT
    addr <= x"E"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " addr=" & to_hstring(addr) & " data=" & to_hstring(data);
    assert data = x"F0" report "REQ R42: ROM[14] muss xF0 (HLT) sein, ist " & to_hstring(data) severity error;
    checked := checked + 1;

    -- ROM[15] = x"00" NOP
    addr <= x"F"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " addr=" & to_hstring(addr) & " data=" & to_hstring(data);
    assert data = x"00" report "REQ R43: ROM[15] muss x00 (NOP) sein, ist " & to_hstring(data) severity error;
    checked := checked + 1;

    -- R27: 16x8-Bit-Festspeicher: alle 16 Adressen lesbar, kombinatorisch
    assert checked = 16 report "REQ R27: Programmspeicher muss 16x8 Bit fest lesbar sein, geprueft=" & integer'image(checked) severity error;
    report "CHECK t=" & time'image(now) & " checked=" & integer'image(checked);

    -- Kombinatorik-Nachweis: Adresswechsel ohne Takt wirkt sofort
    addr <= x"0"; wait for 10 ns;
    assert data = x"11" report "REQ R27: kombinatorisches Lesen verletzt bei addr=0" severity error;
    addr <= x"E"; wait for 10 ns;
    assert data = x"F0" report "REQ R27: kombinatorisches Lesen verletzt bei addr=E" severity error;

    report "TB_COMPLETE" severity note;
    std.env.stop;
    wait;
  end process stim;

end architecture sim;