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

  signal pc_int    : std_logic_vector(3 downto 0);
  signal rom_data  : std_logic_vector(7 downto 0);
  signal ram_addr  : std_logic_vector(3 downto 0);
  signal ram_we    : std_logic;
  signal ram_dout  : std_logic_vector(3 downto 0);
  signal alu_op    : std_logic_vector(2 downto 0);
  signal use_imm   : std_logic;
  signal acc_we    : std_logic;
  signal z_we      : std_logic;
  signal c_we      : std_logic;
  signal out_we    : std_logic;
  signal halted_i  : std_logic;

  signal acc_r     : std_logic_vector(3 downto 0) := (others => '0');
  signal out_r     : std_logic_vector(3 downto 0) := (others => '0');
  signal z_r       : std_logic := '0';
  signal c_r       : std_logic := '0';

  signal alu_a      : std_logic_vector(3 downto 0);
  signal alu_b      : std_logic_vector(3 downto 0);
  signal alu_result : std_logic_vector(3 downto 0);
  signal alu_carry  : std_logic;
  signal alu_zero   : std_logic;

begin

  -- Datapath-Verdrahtung
  alu_a <= acc_r;
  -- use_imm = '1' (LDI): B-Operand ist die Konstante n = IR(3..0) = ram_addr;
  -- sonst B-Operand = RAM[a] (kombinatorisches Lesen).
  alu_b <= ram_addr when use_imm = '1' else ram_dout;

  -- Ausgaenge
  out_value <= out_r;
  acc       <= acc_r;
  pc        <= pc_int;
  z         <= z_r;
  c         <= c_r;
  halted    <= halted_i;

  -- ACC-, Flag- und OUT-Register (eine Taktdomaene, synchroner Reset active high).
  -- Uebernahme mit der Flanke EXECUTE -> WAIT (bzw. EXECUTE -> HALT bei HLT);
  -- die Steuersignale acc_we/z_we/c_we/out_we sind waehrend EXECUTE gueltig.
  p_regs : process(clk)
  begin
    if rising_edge(clk) then
      if rst = '1' then
        acc_r <= (others => '0');
        out_r <= (others => '0');
        z_r   <= '0';
        c_r   <= '0';
      else
        if acc_we = '1' then
          acc_r <= alu_result;
        end if;
        if z_we = '1' then
          z_r <= alu_zero;
        end if;
        if c_we = '1' then
          c_r <= alu_carry;
        end if;
        if out_we = '1' then
          out_r <= acc_r;
        end if;
      end if;
    end if;
  end process p_regs;

  u_control : entity work.control_unit
    port map (
      clk      => clk,
      rst      => rst,
      go       => go,
      z        => z_r,
      c        => c_r,
      rom_data => rom_data,
      pc       => pc_int,
      ram_addr => ram_addr,
      ram_we   => ram_we,
      alu_op   => alu_op,
      use_imm  => use_imm,
      acc_we   => acc_we,
      z_we     => z_we,
      c_we     => c_we,
      out_we   => out_we,
      halted   => halted_i
    );

  u_alu : entity work.alu
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

  u_rom : entity work.program_rom
    port map (
      addr => pc_int,
      data => rom_data
    );

  u_ram : entity work.data_ram
    generic map (
      ADDR_WIDTH => 4,
      DATA_WIDTH => 4
    )
    port map (
      clk  => clk,
      rst  => rst,
      we   => ram_we,
      addr => ram_addr,
      din  => acc_r,
      dout => ram_dout
    );

end architecture rtl;