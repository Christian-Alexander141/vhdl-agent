library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity control_unit is
  port (
    clk      : in  std_logic;
    rst      : in  std_logic;
    go       : in  std_logic;
    rom_data : in  std_logic_vector(7 downto 0);
    z_flag   : in  std_logic;
    c_flag   : in  std_logic;
    acc_en   : out std_logic;
    alu_b_sel: out std_logic;
    alu_op   : out std_logic_vector(2 downto 0);
    c_en     : out std_logic;
    halted   : out std_logic;
    ir       : out std_logic_vector(7 downto 0);
    out_en   : out std_logic;
    pc       : out std_logic_vector(3 downto 0);
    ram_addr : out std_logic_vector(3 downto 0);
    ram_we   : out std_logic;
    z_en     : out std_logic
  );
end entity control_unit;

architecture rtl of control_unit is

  -- WAIT is a reserved word in VHDL, therefore S_ prefix.
  -- Mapping to PROMPT.md: S_WAIT=WAIT, S_FETCH=FETCH, etc.
  type state_t is (S_WAIT, S_FETCH, S_DECODE, S_EXECUTE, S_HALT);

  signal state      : state_t;
  signal next_state : state_t;
  signal pc_reg     : std_logic_vector(3 downto 0);
  signal ir_reg     : std_logic_vector(7 downto 0);

  signal opcode     : std_logic_vector(3 downto 0);
  signal jump_taken : std_logic;

begin

  opcode <= ir_reg(7 downto 4);

  -- Jump decision (only evaluated in EXECUTE)
  p_jump: process(all)
  begin
    jump_taken <= '0';
    if state = S_EXECUTE then
      case opcode is
        when x"B" =>
          jump_taken <= '1';
        when x"C" =>
          if z_flag = '1' then
            jump_taken <= '1';
          end if;
        when x"D" =>
          if c_flag = '1' then
            jump_taken <= '1';
          end if;
        when others =>
          jump_taken <= '0';
      end case;
    end if;
  end process p_jump;

  -- Next-state logic (combinational, go only used in S_WAIT)
  p_next: process(all)
  begin
    next_state <= state;
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
        if opcode = x"F" then
          next_state <= S_HALT;
        else
          next_state <= S_WAIT;
        end if;
      when S_HALT =>
        next_state <= S_HALT;
      when others =>
        next_state <= S_WAIT;
    end case;
  end process p_next;

  -- State / PC / IR registers, synchronous active-high reset
  p_seq: process(clk)
  begin
    if rising_edge(clk) then
      if rst = '1' then
        state   <= S_WAIT;
        pc_reg  <= (others => '0');
        ir_reg  <= (others => '0');
      else
        state <= next_state;
        case state is
          when S_FETCH =>
            ir_reg <= rom_data;
            pc_reg <= std_logic_vector(unsigned(pc_reg) + 1);
          when S_EXECUTE =>
            if jump_taken = '1' then
              pc_reg <= ir_reg(3 downto 0);
            end if;
          when others =>
            null;
        end case;
      end if;
    end if;
  end process p_seq;

  -- Control-signal outputs (combinational, active only in EXECUTE)
  -- Convention: alu_b_sel = '0' selects RAM data, '1' selects immediate
  -- operand IR(3..0) (ALUSrc-like). cpu_core muxes ALU-B accordingly.
  p_out: process(all)
  begin
    -- defaults (avoid latches)
    acc_en    <= '0';
    alu_b_sel <= '0';
    alu_op    <= "000";
    c_en      <= '0';
    out_en    <= '0';
    ram_we    <= '0';
    z_en      <= '0';

    if state = S_EXECUTE then
      case opcode is
        when x"0" => -- NOP
          null;
        when x"1" => -- LDI n: ACC := n (PASS imm); Z neu; C unveraendert
          acc_en    <= '1';
          z_en      <= '1';
          alu_op    <= "111";
          alu_b_sel <= '1';
        when x"2" => -- LDA a: ACC := RAM[a] (PASS ram); Z neu
          acc_en    <= '1';
          z_en      <= '1';
          alu_op    <= "111";
          alu_b_sel <= '0';
        when x"3" => -- STA a: RAM[a] := ACC
          ram_we    <= '1';
        when x"4" => -- ADD a
          acc_en    <= '1';
          z_en      <= '1';
          c_en      <= '1';
          alu_op    <= "000";
          alu_b_sel <= '0';
        when x"5" => -- SUB a
          acc_en    <= '1';
          z_en      <= '1';
          c_en      <= '1';
          alu_op    <= "001";
          alu_b_sel <= '0';
        when x"6" => -- AND a
          acc_en    <= '1';
          z_en      <= '1';
          c_en      <= '1';
          alu_op    <= "010";
          alu_b_sel <= '0';
        when x"7" => -- OR a
          acc_en    <= '1';
          z_en      <= '1';
          c_en      <= '1';
          alu_op    <= "011";
          alu_b_sel <= '0';
        when x"8" => -- XOR a
          acc_en    <= '1';
          z_en      <= '1';
          c_en      <= '1';
          alu_op    <= "100";
          alu_b_sel <= '0';
        when x"9" => -- SHL
          acc_en    <= '1';
          z_en      <= '1';
          c_en      <= '1';
          alu_op    <= "101";
          alu_b_sel <= '0';
        when x"A" => -- SHR
          acc_en    <= '1';
          z_en      <= '1';
          c_en      <= '1';
          alu_op    <= "110";
          alu_b_sel <= '0';
        when x"B" => -- JMP t
          null;
        when x"C" => -- JZ t
          null;
        when x"D" => -- JC t
          null;
        when x"E" => -- OUT: OUT := ACC
          out_en    <= '1';
        when x"F" => -- HLT
          null;
        when others =>
          null;
      end case;
    end if;
  end process p_out;

  -- Registered-state reflections
  pc <= pc_reg;
  ir <= ir_reg;

  -- RAM address: operand of current instruction (valid in EXECUTE;
  -- RAM read is combinational, write is gated by ram_we)
  ram_addr <= ir_reg(3 downto 0);

  halted <= '1' when state = S_HALT else '0';

end architecture rtl;