library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
library std;
use std.env.all;

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
  begin
    -- R36: Adresse 0: x"11" (LDI 1)
    addr <= x"0"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " addr=" & to_hstring(addr) & " data=" & to_hstring(data);
    assert data = x"11" report "REQ R36: ROM addr 0 must be x11, got " & to_hstring(data) severity error;

    -- R37: Adresse 1: x"30" (STA 0)
    addr <= x"1"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " addr=" & to_hstring(addr) & " data=" & to_hstring(data);
    assert data = x"30" report "REQ R37: ROM addr 1 must be x30, got " & to_hstring(data) severity error;

    -- R38: Adresse 2: x"31" (STA 1)
    addr <= x"2"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " addr=" & to_hstring(addr) & " data=" & to_hstring(data);
    assert data = x"31" report "REQ R38: ROM addr 2 must be x31, got " & to_hstring(data) severity error;

    -- R39: Adresse 3: x"E0" (OUT)
    addr <= x"3"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " addr=" & to_hstring(addr) & " data=" & to_hstring(data);
    assert data = x"E0" report "REQ R39: ROM addr 3 must be xE0, got " & to_hstring(data) severity error;

    -- R40: Adresse 4: x"20" (LDA 0)
    addr <= x"4"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " addr=" & to_hstring(addr) & " data=" & to_hstring(data);
    assert data = x"20" report "REQ R40: ROM addr 4 must be x20, got " & to_hstring(data) severity error;

    -- R41: Adresse 5: x"41" (ADD 1)
    addr <= x"5"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " addr=" & to_hstring(addr) & " data=" & to_hstring(data);
    assert data = x"41" report "REQ R41: ROM addr 5 must be x41, got " & to_hstring(data) severity error;

    -- R42: Adresse 6: x"DE" (JC 14)
    addr <= x"6"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " addr=" & to_hstring(addr) & " data=" & to_hstring(data);
    assert data = x"DE" report "REQ R42: ROM addr 6 must be xDE, got " & to_hstring(data) severity error;

    -- R43: Adresse 7: x"32" (STA 2)
    addr <= x"7"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " addr=" & to_hstring(addr) & " data=" & to_hstring(data);
    assert data = x"32" report "REQ R43: ROM addr 7 must be x32, got " & to_hstring(data) severity error;

    -- R44: Adresse 8: x"21" (LDA 1)
    addr <= x"8"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " addr=" & to_hstring(addr) & " data=" & to_hstring(data);
    assert data = x"21" report "REQ R44: ROM addr 8 must be x21, got " & to_hstring(data) severity error;

    -- R45: Adresse 9: x"30" (STA 0)
    addr <= x"9"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " addr=" & to_hstring(addr) & " data=" & to_hstring(data);
    assert data = x"30" report "REQ R45: ROM addr 9 must be x30, got " & to_hstring(data) severity error;

    -- R46: Adresse 10: x"22" (LDA 2)
    addr <= x"A"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " addr=" & to_hstring(addr) & " data=" & to_hstring(data);
    assert data = x"22" report "REQ R46: ROM addr 10 must be x22, got " & to_hstring(data) severity error;

    -- R47: Adresse 11: x"31" (STA 1)
    addr <= x"B"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " addr=" & to_hstring(addr) & " data=" & to_hstring(data);
    assert data = x"31" report "REQ R47: ROM addr 11 must be x31, got " & to_hstring(data) severity error;

    -- R48: Adresse 12: x"E0" (OUT)
    addr <= x"C"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " addr=" & to_hstring(addr) & " data=" & to_hstring(data);
    assert data = x"E0" report "REQ R48: ROM addr 12 must be xE0, got " & to_hstring(data) severity error;

    -- R49: Adresse 13: x"B4" (JMP 4)
    addr <= x"D"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " addr=" & to_hstring(addr) & " data=" & to_hstring(data);
    assert data = x"B4" report "REQ R49: ROM addr 13 must be xB4, got " & to_hstring(data) severity error;

    -- R50: Adresse 14: x"F0" (HLT)
    addr <= x"E"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " addr=" & to_hstring(addr) & " data=" & to_hstring(data);
    assert data = x"F0" report "REQ R50: ROM addr 14 must be xF0, got " & to_hstring(data) severity error;

    -- R51: Adresse 15: x"00" (NOP)
    addr <= x"F"; wait for 10 ns;
    report "CHECK t=" & time'image(now) & " addr=" & to_hstring(addr) & " data=" & to_hstring(data);
    assert data = x"00" report "REQ R51: ROM addr 15 must be x00, got " & to_hstring(data) severity error;

    -- R4: festes Fibonacci-Demoprogramm: Opcode-Folge pruefen (kombinatorisch gelesen)
    -- Erste Anweisung LDI (Opcode 1), letzte belegte HLT (Opcode F), danach NOP (Opcode 0).
    addr <= x"0"; wait for 10 ns;
    assert data(7 downto 4) = x"1" report "REQ R4: demo program must start with LDI opcode 1, got " & to_hstring(data) severity error;
    addr <= x"E"; wait for 10 ns;
    assert data(7 downto 4) = x"F" report "REQ R4: demo program must hold HLT at addr 14, got " & to_hstring(data) severity error;
    addr <= x"F"; wait for 10 ns;
    assert data = x"00" report "REQ R4: demo program must end with NOP at addr 15, got " & to_hstring(data) severity error;
    report "CHECK t=" & time'image(now) & " R4 demo program opcodes verified";

    report "TB_COMPLETE" severity note;
    stop;
    wait;
  end process stim;

end architecture sim;