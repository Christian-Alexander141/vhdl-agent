library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity control_unit is
  port (
    clk        : in  std_logic;
    rst        : in  std_logic;
    go         : in  std_logic;
    rom_data   : in  std_logic_vector(7 downto 0);
    acc_in     : in  std_logic_vector(3 downto 0);
    ram_dout   : in  std_logic_vector(3 downto 0);
    alu_result : in  std_logic_vector(3 downto 0);
    alu_carry  : in  std_logic;
    alu_zero   : in  std_logic;
    z_in       : in  std_logic;
    c_in       : in  std_logic;
    rom_addr   : out std_logic_vector(3 downto 0);
    ram_addr   : out std_logic_vector(3 downto 0);
    ram_din    : out std_logic_vector(3 downto 0);
    ram_we     : out std_logic;
    alu_op     : out std_logic_vector(2 downto 0);
    alu_a      : out std_logic_vector(3 downto 0);
    alu_b      : out std_logic_vector(3 downto 0);
    acc_next   : out std_logic_vector(3 downto 0);
    acc_we     : out std_logic;
    z_next     : out std_logic;
    z_we       : out std_logic;
    c_next     : out std_logic;
    c_we       : out std_logic;
    out_we     : out std_logic;
    pc         : out std_logic_vector(3 downto 0);
    ir         : out std_logic_vector(7 downto 0);
    halted     : out std_logic
  );
end entity control_unit;

architecture rtl of control_unit is
  -- PROMPT.md nennt die Zustaende WAIT/FETCH/DECODE/EXECUTE/HALT.
  -- WAIT ist ein reserviertes VHDL-Wort, daher ST_-Praefix (Verhalten identisch).
  -- Reset: synchron active-high (PROMPT.md hat Vorrang vor async-Default der Skills).
  type state_t is (ST_WAIT, ST_FETCH, ST_DECODE, ST_EXECUTE, ST_HALT);

  signal state      : state_t := ST_WAIT;
  signal next_state : state_t;
  signal pc_reg     : std_logic_vector(3 downto 0) := (others => '0');
  signal pc_next    : std_logic_vector(3 downto 0);
  signal ir_reg     : std_logic_vector(7 downto 0) := (others => '0');
  signal ir_next    : std_logic_vector(7 downto 0);
begin

  pc       <= pc_reg;
  ir       <= ir_reg;
  rom_addr <= pc_reg;
  halted   <= '1' when state = ST_HALT else '0';

  p_seq : process(clk)
  begin
    if rising_edge(clk) then
      if rst = '1' then
        state   <= ST_WAIT;
        pc_reg  <= (others => '0');
        ir_reg  <= (others => '0');
      else
        state   <= next_state;
        pc_reg  <= pc_next;
        ir_reg  <= ir_next;
      end if;
    end if;
  end process p_seq;

  p_comb : process(all)
    variable opcode : std_logic_vector(3 downto 0);
    variable operand : std_logic_vector(3 downto 0);
  begin
    -- Defaults: keine Registerwirkung, keine Latches.
    next_state <= state;
    pc_next    <= pc_reg;
    ir_next    <= ir_reg;

    ram_addr <= ir_reg(3 downto 0);
    ram_din  <= acc_in;
    ram_we   <= '0';

    alu_op <= "000";
    alu_a  <= acc_in;
    alu_b  <= ram_dout;

    acc_next <= (others => '0');
    acc_we   <= '0';
    z_next   <= '0';
    z_we     <= '0';
    c_next   <= '0';
    c_we     <= '0';
    out_we   <= '0';

    opcode  := ir_reg(7 downto 4);
    operand := ir_reg(3 downto 0);

    case state is
      when ST_WAIT =>
        if go = '1' then
          next_state <= ST_FETCH;
        else
          next_state <= ST_WAIT;
        end if;

      when ST_FETCH =>
        ir_next    <= rom_data;
        pc_next    <= std_logic_vector(unsigned(pc_reg) + 1);
        next_state <= ST_DECODE;

      when ST_DECODE =>
        -- Reines Dekodieren, kein Register aendert sich.
        next_state <= ST_EXECUTE;

      when ST_EXECUTE =>
        next_state <= ST_WAIT;
        case opcode is
          when "0000" => -- NOP
            null;

          when "0001" => -- LDI n
            acc_next <= operand;
            acc_we   <= '1';
            if operand = "0000" then
              z_next <= '1';
            else
              z_next <= '0';
            end if;
            z_we <= '1';

          when "0010" => -- LDA a
            acc_next <= ram_dout;
            acc_we   <= '1';
            if ram_dout = "0000" then
              z_next <= '1';
            else
              z_next <= '0';
            end if;
            z_we <= '1';

          when "0011" => -- STA a
            ram_addr <= operand;
            ram_din  <= acc_in;
            ram_we   <= '1';

          when "0100" => -- ADD a
            alu_op   <= "000";
            alu_a    <= acc_in;
            alu_b    <= ram_dout;
            ram_addr <= operand;
            acc_next <= alu_result;
            acc_we   <= '1';
            z_next   <= alu_zero;
            z_we     <= '1';
            c_next   <= alu_carry;
            c_we     <= '1';

          when "0101" => -- SUB a
            alu_op   <= "001";
            alu_a    <= acc_in;
            alu_b    <= ram_dout;
            ram_addr <= operand;
            acc_next <= alu_result;
            acc_we   <= '1';
            z_next   <= alu_zero;
            z_we     <= '1';
            c_next   <= alu_carry;
            c_we     <= '1';

          when "0110" => -- AND a
            alu_op   <= "010";
            alu_a    <= acc_in;
            alu_b    <= ram_dout;
            ram_addr <= operand;
            acc_next <= alu_result;
            acc_we   <= '1';
            z_next   <= alu_zero;
            z_we     <= '1';
            c_next   <= '0';
            c_we     <= '1';

          when "0111" => -- OR a
            alu_op   <= "011";
            alu_a    <= acc_in;
            alu_b    <= ram_dout;
            ram_addr <= operand;
            acc_next <= alu_result;
            acc_we   <= '1';
            z_next   <= alu_zero;
            z_we     <= '1';
            c_next   <= '0';
            c_we     <= '1';

          when "1000" => -- XOR a
            alu_op   <= "100";
            alu_a    <= acc_in;
            alu_b    <= ram_dout;
            ram_addr <= operand;
            acc_next <= alu_result;
            acc_we   <= '1';
            z_next   <= alu_zero;
            z_we     <= '1';
            c_next   <= '0';
            c_we     <= '1';

          when "1001" => -- SHL
            alu_op   <= "101";
            alu_a    <= acc_in;
            alu_b    <= (others => '0');
            acc_next <= alu_result;
            acc_we   <= '1';
            z_next   <= alu_zero;
            z_we     <= '1';
            c_next   <= alu_carry;
            c_we     <= '1';

          when "1010" => -- SHR
            alu_op   <= "110";
            alu_a    <= acc_in;
            alu_b    <= (others => '0');
            acc_next <= alu_result;
            acc_we   <= '1';
            z_next   <= alu_zero;
            z_we     <= '1';
            c_next   <= alu_carry;
            c_we     <= '1';

          when "1011" => -- JMP t
            pc_next <= operand;

          when "1100" => -- JZ t
            if z_in = '1' then
              pc_next <= operand;
            end if;

          when "1101" => -- JC t
            if c_in = '1' then
              pc_next <= operand;
            end if;

          when "1110" => -- OUT
            out_we <= '1';

          when "1111" => -- HLT
            next_state <= ST_HALT;

          when others =>
            null;
        end case;

      when ST_HALT =>
        next_state <= ST_HALT;

      when others =>
        next_state <= ST_WAIT;
        pc_next    <= (others => '0');
        ir_next    <= (others => '0');
    end case;
  end process p_comb;

end architecture rtl;