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

  signal acc_reg      : std_logic_vector(3 downto 0);
  signal out_reg      : std_logic_vector(3 downto 0);
  signal z_reg        : std_logic;
  signal c_reg        : std_logic;

  signal ir_sig       : std_logic_vector(7 downto 0);
  signal pc_sig       : std_logic_vector(3 downto 0);
  signal rom_data_sig : std_logic_vector(7 downto 0);

  signal ram_addr_sig : std_logic_vector(3 downto 0);
  signal ram_rdata    : std_logic_vector(3 downto 0);
  signal ram_we_sig   : std_logic;

  signal alu_a      : std_logic_vector(3 downto 0);
  signal alu_b      : std_logic_vector(3 downto 0);
  signal alu_op     : std_logic_vector(2 downto 0);
  signal alu_b_sel  : std_logic;
  signal alu_result : std_logic_vector(3 downto 0);
  signal alu_carry  : std_logic;
  signal alu_zero   : std_logic;

  signal acc_en_sig : std_logic;
  signal c_en_sig   : std_logic;
  signal z_en_sig   : std_logic;
  signal out_en_sig : std_logic;
  signal halted_sig : std_logic;

begin

  -- ALU-B-Multiplexer: '0' = RAM-Daten, '1' = Immediate IR(3..0)
  p_alu_b_mux: process(all)
  begin
    if alu_b_sel = '1' then
      alu_b <= ir_sig(3 downto 0);
    else
      alu_b <= ram_rdata;
    end if;
  end process p_alu_b_mux;

  alu_a <= acc_reg;

  -- ACC / Z / C / OUT-Register, synchroner Reset active high
  p_regs: process(clk)
  begin
    if rising_edge(clk) then
      if rst = '1' then
        acc_reg <= (others => '0');
        z_reg   <= '0';
        c_reg   <= '0';
        out_reg <= (others => '0');
      else
        if acc_en_sig = '1' then
          acc_reg <= alu_result;
        end if;
        if z_en_sig = '1' then
          z_reg <= alu_zero;
        end if;
        if c_en_sig = '1' then
          c_reg <= alu_carry;
        end if;
        if out_en_sig = '1' then
          out_reg <= acc_reg;
        end if;
      end if;
    end if;
  end process p_regs;

  u_control: entity work.control_unit
    port map (
      clk       => clk,
      rst       => rst,
      go        => go,
      rom_data  => rom_data_sig,
      z_flag    => z_reg,
      c_flag    => c_reg,
      acc_en    => acc_en_sig,
      alu_b_sel => alu_b_sel,
      alu_op    => alu_op,
      c_en      => c_en_sig,
      halted    => halted_sig,
      ir        => ir_sig,
      out_en    => out_en_sig,
      pc        => pc_sig,
      ram_addr  => ram_addr_sig,
      ram_we    => ram_we_sig,
      z_en      => z_en_sig
    );

  u_alu: entity work.alu
    generic map (
      WIDTH => 4
    )
    port map (
      a      => alu_a,
      b      => alu_b,
      op     => alu_op,
      result => alu_result,
      carry  => alu_carry,
      zero   => alu_zero
    );

  u_rom: entity work.program_rom
    port map (
      addr => pc_sig,
      data => rom_data_sig
    );

  u_ram: entity work.data_ram
    generic map (
      ADDR_WIDTH => 4,
      DATA_WIDTH => 4
    )
    port map (
      addr  => ram_addr_sig,
      clk   => clk,
      rst   => rst,
      rdata => ram_rdata,
      wdata => acc_reg,
      we    => ram_we_sig
    );

  acc       <= acc_reg;
  out_value <= out_reg;
  pc        <= pc_sig;
  z         <= z_reg;
  c         <= c_reg;
  halted    <= halted_sig;

end architecture rtl;