library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity control_unit is
  port (
    clk      : in  std_logic;
    rst      : in  std_logic;
    go       : in  std_logic;
    z        : in  std_logic;
    c        : in  std_logic;
    rom_data : in  std_logic_vector(7 downto 0);
    pc       : out std_logic_vector(3 downto 0);
    ram_addr : out std_logic_vector(3 downto 0);
    ram_we   : out std_logic;
    alu_op   : out std_logic_vector(2 downto 0);
    use_imm  : out std_logic;
    acc_we   : out std_logic;
    z_we     : out std_logic;
    c_we     : out std_logic;
    out_we   : out std_logic;
    halted   : out std_logic
  );
end entity control_unit;

architecture rtl of control_unit is

  -- PROMPT.md nennt die Zustaende WAIT, FETCH, DECODE, EXECUTE, HALT.
  -- WAIT ist ein reserviertes VHDL-Schluesselwort (case-insensitiv),
  -- daher S_-Praefix; Abbildung: S_WAIT=WAIT usw.
  type state_t is (S_WAIT, S_FETCH, S_DECODE, S_EXECUTE, S_HALT);
  signal state      : state_t := S_WAIT;
  signal next_state : state_t;
  signal pc_r       : std_logic_vector(3 downto 0) := (others => '0');
  signal ir_r       : std_logic_vector(7 downto 0) := (others => '0');

begin

  pc       <= pc_r;
  ram_addr <= ir_r(3 downto 0);
  halted   <= '1' when state = S_HALT else '0';

  -- Zustandsregister, PC und IR (eine Taktdomaene, synchroner Reset active high).
  p_seq : process(clk)
    variable opcode : std_logic_vector(3 downto 0);
    variable jump_taken : boolean;
  begin
    if rising_edge(clk) then
      if rst = '1' then
        state <= S_WAIT;
        pc_r  <= (others => '0');
        ir_r  <= (others => '0');
      else
        state <= next_state;
        case state is
          when S_FETCH =>
            ir_r <= rom_data;
            pc_r <= std_logic_vector(unsigned(pc_r) + 1);
          when S_EXECUTE =>
            opcode := ir_r(7 downto 4);
            jump_taken := false;
            if opcode = x"B" then
              jump_taken := true;
            elsif opcode = x"C" and z = '1' then
              jump_taken := true;
            elsif opcode = x"D" and c = '1' then
              jump_taken := true;
            end if;
            if jump_taken then
              pc_r <= ir_r(3 downto 0);
            end if;
          when others =>
            null;
        end case;
      end if;
    end if;
  end process p_seq;

  -- Naechster Zustand und Steuersignale (kombinatorisch, vollstaendig).
  p_comb : process(all)
    variable opcode : std_logic_vector(3 downto 0);
  begin
    next_state <= state;
    ram_we     <= '0';
    alu_op     <= "000";
    use_imm    <= '0';
    acc_we     <= '0';
    z_we       <= '0';
    c_we       <= '0';
    out_we     <= '0';

    opcode := ir_r(7 downto 4);

    case state is
      when S_WAIT =>
        if go = '1' then
          next_state <= S_FETCH;
        else
          next_state <= S_WAIT;
        end if;

      when S_FETCH =>
        next_state <= S_DECODE;

      when S_DECODE =>
        next_state <= S_EXECUTE;

      when S_EXECUTE =>
        next_state <= S_WAIT;
        case opcode is
          when x"0" => -- NOP
            null;
          when x"1" => -- LDI n: ACC := n; Z neu (C unveraendert)
            use_imm <= '1';
            alu_op  <= "111";
            acc_we  <= '1';
            z_we    <= '1';
          when x"2" => -- LDA a: ACC := RAM[a]; Z neu (C unveraendert)
            alu_op <= "111";
            acc_we <= '1';
            z_we   <= '1';
          when x"3" => -- STA a: RAM[a] := ACC
            ram_we <= '1';
          when x"4" => -- ADD
            alu_op <= "000";
            acc_we <= '1';
            z_we   <= '1';
            c_we   <= '1';
          when x"5" => -- SUB
            alu_op <= "001";
            acc_we <= '1';
            z_we   <= '1';
            c_we   <= '1';
          when x"6" => -- AND
            alu_op <= "010";
            acc_we <= '1';
            z_we   <= '1';
            c_we   <= '1';
          when x"7" => -- OR
            alu_op <= "011";
            acc_we <= '1';
            z_we   <= '1';
            c_we   <= '1';
          when x"8" => -- XOR
            alu_op <= "100";
            acc_we <= '1';
            z_we   <= '1';
            c_we   <= '1';
          when x"9" => -- SHL
            alu_op <= "101";
            acc_we <= '1';
            z_we   <= '1';
            c_we   <= '1';
          when x"A" => -- SHR
            alu_op <= "110";
            acc_we <= '1';
            z_we   <= '1';
            c_we   <= '1';
          when x"B" => -- JMP t
            null;
          when x"C" => -- JZ t
            null;
          when x"D" => -- JC t
            null;
          when x"E" => -- OUT: OUT := ACC
            out_we <= '1';
          when x"F" => -- HLT
            next_state <= S_HALT;
          when others =>
            null;
        end case;

      when S_HALT =>
        next_state <= S_HALT;

      when others =>
        next_state <= S_WAIT;
    end case;
  end process p_comb;

end architecture rtl;