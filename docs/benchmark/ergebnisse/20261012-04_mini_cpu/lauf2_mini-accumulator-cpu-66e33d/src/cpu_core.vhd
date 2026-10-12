library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity cpu_core is
  port (
    clk       : in  std_logic;
    rst       : in  std_logic;
    go        : in  std_logic;
    out_value : out std_logic_vector(3 downto 0);
    acc       : out std_logic_vector(3 downto 0);
    pc        : out std_logic_vector(3 downto 0);
    z         : out std_logic;
    c         : out std_logic;
    halted    : out std_logic
  );
end entity cpu_core;

architecture rtl of cpu_core is
  signal acc_reg : std_logic_vector(3 downto 0) := (others => '0');
  signal z_reg   : std_logic := '0';
  signal c_reg   : std_logic := '0';
  signal out_reg : std_logic_vector(3 downto 0) := (others => '0');

  signal rom_addr_s   : std_logic_vector(3 downto 0);
  signal rom_data_s   : std_logic_vector(7 downto 0);
  signal ram_addr_s   : std_logic_vector(3 downto 0);
  signal ram_din_s    : std_logic_vector(3 downto 0);
  signal ram_dout_s   : std_logic_vector(3 downto 0);
  signal ram_we_s     : std_logic;
  signal alu_op_s     : std_logic_vector(2 downto 0);
  signal alu_a_s      : std_logic_vector(3 downto 0);
  signal alu_b_s      : std_logic_vector(3 downto 0);
  signal alu_result_s : std_logic_vector(3 downto 0);
  signal alu_carry_s  : std_logic;
  signal alu_zero_s   : std_logic;
  signal acc_next_s   : std_logic_vector(3 downto 0);
  signal acc_we_s     : std_logic;
  signal z_next_s     : std_logic;
  signal z_we_s       : std_logic;
  signal c_next_s     : std_logic;
  signal c_we_s       : std_logic;
  signal out_we_s     : std_logic;
  signal pc_s         : std_logic_vector(3 downto 0);
  signal ir_s         : std_logic_vector(7 downto 0);
  signal halted_s     : std_logic;
begin

  out_value <= out_reg;
  acc       <= acc_reg;
  pc        <= pc_s;
  z         <= z_reg;
  c         <= c_reg;
  halted    <= halted_s;

  -- ACC-, Flag- und OUT-Register, synchroner Reset active-high (PROMPT.md).
  p_regs : process(clk)
  begin
    if rising_edge(clk) then
      if rst = '1' then
        acc_reg <= (others => '0');
        z_reg   <= '0';
        c_reg   <= '0';
        out_reg <= (others => '0');
      else
        if acc_we_s = '1' then
          acc_reg <= acc_next_s;
        end if;
        if z_we_s = '1' then
          z_reg <= z_next_s;
        end if;
        if c_we_s = '1' then
          c_reg <= c_next_s;
        end if;
        if out_we_s = '1' then
          out_reg <= acc_reg;
        end if;
      end if;
    end if;
  end process p_regs;

  u_control : entity work.control_unit
    port map (
      clk        => clk,
      rst        => rst,
      go         => go,
      rom_data   => rom_data_s,
      acc_in     => acc_reg,
      ram_dout   => ram_dout_s,
      alu_result => alu_result_s,
      alu_carry  => alu_carry_s,
      alu_zero   => alu_zero_s,
      z_in       => z_reg,
      c_in       => c_reg,
      rom_addr   => rom_addr_s,
      ram_addr   => ram_addr_s,
      ram_din    => ram_din_s,
      ram_we     => ram_we_s,
      alu_op     => alu_op_s,
      alu_a      => alu_a_s,
      alu_b      => alu_b_s,
      acc_next   => acc_next_s,
      acc_we     => acc_we_s,
      z_next     => z_next_s,
      z_we       => z_we_s,
      c_next     => c_next_s,
      c_we       => c_we_s,
      out_we     => out_we_s,
      pc         => pc_s,
      ir         => ir_s,
      halted     => halted_s
    );

  u_alu : entity work.alu
    generic map (
      WIDTH => 4
    )
    port map (
      a      => alu_a_s,
      b      => alu_b_s,
      op     => alu_op_s,
      result => alu_result_s,
      carry  => alu_carry_s,
      zero   => alu_zero_s
    );

  u_rom : entity work.program_rom
    port map (
      addr => rom_addr_s,
      data => rom_data_s
    );

  u_ram : entity work.data_ram
    generic map (
      ADDR_WIDTH => 4,
      DATA_WIDTH => 4
    )
    port map (
      clk  => clk,
      rst  => rst,
      we   => ram_we_s,
      addr => ram_addr_s,
      din  => ram_din_s,
      dout => ram_dout_s
    );

end architecture rtl;