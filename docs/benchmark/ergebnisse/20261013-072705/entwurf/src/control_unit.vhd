library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity control_unit is
  port (
    clk      : in  std_logic;
    rst      : in  std_logic;
    go       : in  std_logic;
    z_in     : in  std_logic;
    c_in     : in  std_logic;
    rom_data : in  std_logic_vector(7 downto 0);
    pc_out   : out std_logic_vector(3 downto 0);
    ir_out   : out std_logic_vector(7 downto 0);
    halted   : out std_logic;
    alu_op   : out std_logic_vector(2 downto 0);
    use_imm  : out std_logic;
    ram_addr : out std_logic_vector(3 downto 0);
    ram_we   : out std_logic;
    acc_we   : out std_logic;
    out_we   : out std_logic;
    flag_z_we : out std_logic;
    flag_c_we : out std_logic
  );
end entity control_unit;

architecture rtl of control_unit is
  type state_t is (WAIT_ST, FETCH_ST, DECODE_ST, EXECUTE_ST, HALT_ST);
  signal state : state_t := WAIT_ST;
  signal pc_r  : unsigned(3 downto 0) := (others => '0');
  signal ir_r  : std_logic_vector(7 downto 0) := (others => '0');
begin
  pc_out <= std_logic_vector(pc_r);
  ir_out <= ir_r;
  halted <= '1' when state = HALT_ST else '0';

  -- FSM + PC/IR
  process(clk)
    variable opcode : std_logic_vector(3 downto 0);
    variable target : unsigned(3 downto 0);
  begin
    if rising_edge(clk) then
      if rst = '1' then
        state <= WAIT_ST;
        pc_r  <= (others => '0');
        ir_r  <= (others => '0');
      else
        case state is
          when WAIT_ST =>
            if go = '1' then
              state <= FETCH_ST;
            end if;
          when FETCH_ST =>
            ir_r  <= rom_data;
            pc_r  <= pc_r + 1;
            state <= DECODE_ST;
          when DECODE_ST =>
            state <= EXECUTE_ST;
          when EXECUTE_ST =>
            opcode := ir_r(7 downto 4);
            target := unsigned(ir_r(3 downto 0));
            -- jump overwrites PC+1 from FETCH
            if opcode = "1011" then
              pc_r <= target;
            elsif opcode = "1100" and z_in = '1' then
              pc_r <= target;
            elsif opcode = "1101" and c_in = '1' then
              pc_r <= target;
            end if;
            if opcode = "1111" then
              state <= HALT_ST;
            else
              state <= WAIT_ST;
            end if;
          when HALT_ST =>
            state <= HALT_ST;
        end case;
      end if;
    end if;
  end process;

  -- combinatorial control signals for datapath (valid in EXECUTE)
  process(state, ir_r, z_in, c_in)
    variable opcode : std_logic_vector(3 downto 0);
  begin
    opcode := ir_r(7 downto 4);
    -- defaults
    alu_op    <= "111";
    use_imm   <= '0';
    ram_addr  <= ir_r(3 downto 0);
    ram_we    <= '0';
    acc_we    <= '0';
    out_we    <= '0';
    flag_z_we <= '0';
    flag_c_we <= '0';

    if state = EXECUTE_ST then
      case opcode is
        when "0000" => -- NOP
          null;
        when "0001" => -- LDI
          alu_op    <= "111";
          use_imm   <= '1';
          acc_we    <= '1';
          flag_z_we <= '1';
        when "0010" => -- LDA
          alu_op    <= "111";
          use_imm   <= '0';
          acc_we    <= '1';
          flag_z_we <= '1';
        when "0011" => -- STA
          ram_we <= '1';
        when "0100" => -- ADD
          alu_op    <= "000";
          acc_we    <= '1';
          flag_z_we <= '1';
          flag_c_we <= '1';
        when "0101" => -- SUB
          alu_op    <= "001";
          acc_we    <= '1';
          flag_z_we <= '1';
          flag_c_we <= '1';
        when "0110" => -- AND
          alu_op    <= "010";
          acc_we    <= '1';
          flag_z_we <= '1';
          flag_c_we <= '1';
        when "0111" => -- OR
          alu_op    <= "011";
          acc_we    <= '1';
          flag_z_we <= '1';
          flag_c_we <= '1';
        when "1000" => -- XOR
          alu_op    <= "100";
          acc_we    <= '1';
          flag_z_we <= '1';
          flag_c_we <= '1';
        when "1001" => -- SHL
          alu_op    <= "101";
          acc_we    <= '1';
          flag_z_we <= '1';
          flag_c_we <= '1';
        when "1010" => -- SHR
          alu_op    <= "110";
          acc_we    <= '1';
          flag_z_we <= '1';
          flag_c_we <= '1';
        when "1011" => -- JMP
          null;
        when "1100" => -- JZ
          null;
        when "1101" => -- JC
          null;
        when "1110" => -- OUT
          out_we <= '1';
        when others => -- "1111" HLT
          null;
      end case;
    end if;
  end process;
end architecture rtl;
