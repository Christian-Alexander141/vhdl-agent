library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.env.all;

entity program_rom_tb is
end entity program_rom_tb;

architecture sim of program_rom_tb is
  signal addr : std_logic_vector(3 downto 0) := (others => '0');
  signal data : std_logic_vector(7 downto 0);

  signal tb_done : boolean := false;
begin

  dut: entity work.program_rom
    port map (
      addr => addr,
      data => data
    );

  stim: process
  begin
    -- R32: Adresse 0 -> x"11" (LDI 1)
    addr <= x"0"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " addr=" & to_string(addr) & " data=" & to_string(data);
    assert data = x"11" report "REQ R32: ROM-Adresse 0 muss x11 (LDI 1) enthalten, ist=" & to_string(data) severity error;

    -- R33: Adresse 1 -> x"30" (STA 0)
    addr <= x"1"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " addr=" & to_string(addr) & " data=" & to_string(data);
    assert data = x"30" report "REQ R33: ROM-Adresse 1 muss x30 (STA 0) enthalten, ist=" & to_string(data) severity error;

    -- R34: Adresse 2 -> x"31" (STA 1)
    addr <= x"2"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " addr=" & to_string(addr) & " data=" & to_string(data);
    assert data = x"31" report "REQ R34: ROM-Adresse 2 muss x31 (STA 1) enthalten, ist=" & to_string(data) severity error;

    -- R35: Adresse 3 -> x"E0" (OUT)
    addr <= x"3"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " addr=" & to_string(addr) & " data=" & to_string(data);
    assert data = x"E0" report "REQ R35: ROM-Adresse 3 muss xE0 (OUT) enthalten, ist=" & to_string(data) severity error;

    -- R36: Adresse 4 -> x"20" (LDA 0)
    addr <= x"4"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " addr=" & to_string(addr) & " data=" & to_string(data);
    assert data = x"20" report "REQ R36: ROM-Adresse 4 muss x20 (LDA 0) enthalten, ist=" & to_string(data) severity error;

    -- R37: Adresse 5 -> x"41" (ADD 1)
    addr <= x"5"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " addr=" & to_string(addr) & " data=" & to_string(data);
    assert data = x"41" report "REQ R37: ROM-Adresse 5 muss x41 (ADD 1) enthalten, ist=" & to_string(data) severity error;

    -- R38: Adresse 6 -> x"DE" (JC 14)
    addr <= x"6"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " addr=" & to_string(addr) & " data=" & to_string(data);
    assert data = x"DE" report "REQ R38: ROM-Adresse 6 muss xDE (JC 14) enthalten, ist=" & to_string(data) severity error;

    -- R39: Adresse 7 -> x"32" (STA 2)
    addr <= x"7"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " addr=" & to_string(addr) & " data=" & to_string(data);
    assert data = x"32" report "REQ R39: ROM-Adresse 7 muss x32 (STA 2) enthalten, ist=" & to_string(data) severity error;

    -- R40: Adresse 8 -> x"21" (LDA 1)
    addr <= x"8"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " addr=" & to_string(addr) & " data=" & to_string(data);
    assert data = x"21" report "REQ R40: ROM-Adresse 8 muss x21 (LDA 1) enthalten, ist=" & to_string(data) severity error;

    -- R41: Adresse 9 -> x"30" (STA 0)
    addr <= x"9"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " addr=" & to_string(addr) & " data=" & to_string(data);
    assert data = x"30" report "REQ R41: ROM-Adresse 9 muss x30 (STA 0) enthalten, ist=" & to_string(data) severity error;

    -- R42: Adresse 10 -> x"22" (LDA 2)
    addr <= x"A"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " addr=" & to_string(addr) & " data=" & to_string(data);
    assert data = x"22" report "REQ R42: ROM-Adresse 10 muss x22 (LDA 2) enthalten, ist=" & to_string(data) severity error;

    -- R43: Adresse 11 -> x"31" (STA 1)
    addr <= x"B"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " addr=" & to_string(addr) & " data=" & to_string(data);
    assert data = x"31" report "REQ R43: ROM-Adresse 11 muss x31 (STA 1) enthalten, ist=" & to_string(data) severity error;

    -- R44: Adresse 12 -> x"E0" (OUT)
    addr <= x"C"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " addr=" & to_string(addr) & " data=" & to_string(data);
    assert data = x"E0" report "REQ R44: ROM-Adresse 12 muss xE0 (OUT) enthalten, ist=" & to_string(data) severity error;

    -- R45: Adresse 13 -> x"B4" (JMP 4)
    addr <= x"D"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " addr=" & to_string(addr) & " data=" & to_string(data);
    assert data = x"B4" report "REQ R45: ROM-Adresse 13 muss xB4 (JMP 4) enthalten, ist=" & to_string(data) severity error;

    -- R46: Adresse 14 -> x"F0" (HLT)
    addr <= x"E"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " addr=" & to_string(addr) & " data=" & to_string(data);
    assert data = x"F0" report "REQ R46: ROM-Adresse 14 muss xF0 (HLT) enthalten, ist=" & to_string(data) severity error;

    -- R47: Adresse 15 -> x"00" (NOP)
    addr <= x"F"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " addr=" & to_string(addr) & " data=" & to_string(data);
    assert data = x"00" report "REQ R47: ROM-Adresse 15 muss x00 (NOP) enthalten, ist=" & to_string(data) severity error;

    -- Kombinatorisches Lesen: schneller Adresswechsel ohne Takt
    addr <= x"0"; wait for 1 ns;
    assert data = x"11" report "REQ R32: kombinatorisches Lesen Adresse 0 muss sofort x11 liefern" severity error;
    addr <= x"E"; wait for 1 ns;
    report "CHECK t=" & time'image(now) & " comb addr=" & to_string(addr) & " data=" & to_string(data);
    assert data = x"F0" report "REQ R46: kombinatorisches Lesen Adresse 14 muss sofort xF0 liefern" severity error;
    addr <= x"5"; wait for 1 ns;
    assert data = x"41" report "REQ R37: kombinatorisches Lesen Adresse 5 muss sofort x41 liefern" severity error;

    tb_done <= true;
    assert false report "TB_COMPLETE" severity note;
    std.env.stop;
    wait;
  end process stim;

end architecture sim;