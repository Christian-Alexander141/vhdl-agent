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
  component control_unit is
    port (
      clk       : in  std_logic;
      rst       : in  std_logic;
      go        : in  std_logic;
      z_in      : in  std_logic;
      c_in      : in  std_logic;
      rom_data  : in  std_logic_vector(7 downto 0);
      pc_out    : out std_logic_vector(3 downto 0);
      ir_out    : out std_logic_vector(7 downto 0);
      halted    : out std_logic;
      alu_op    : out std_logic_vector(2 downto 0);
      use_imm   : out std_logic;
      ram_addr  : out std_logic_vector(3 downto 0);
      ram_we    : out std_logic;
      acc_we    : out std_logic;
      out_we    : out std_logic;
      flag_z_we : out std_logic;
      flag_c_we : out std_logic
    );
  end component;
  component program_rom is
    port (
      addr : in  std_logic_vector(3 downto 0);
      data : out std_logic_vector(7 downto 0)
    );
  end component;
  component data_ram is
    generic (
      ADDR_WIDTH : positive := 4;
      DATA_WIDTH : positive := 4
    );
    port (
      clk  : in  std_logic;
      rst  : in  std_logic;
      we   : in  std_logic;
      addr : in  std_logic_vector(ADDR_WIDTH-1 downto 0);
      din  : in  std_logic_vector(DATA_WIDTH-1 downto 0);
      dout : out std_logic_vector(DATA_WIDTH-1 downto 0)
    );
  end component;
  component alu is
    generic (
      WIDTH : positive := 4
    );
    port (
      a      : in  std_logic_vector(WIDTH-1 downto 0);
      b      : in  std_logic_vector(WIDTH-1 downto 0);
      op     : in  std_logic_vector(2 downto 0);
      result : out std_logic_vector(WIDTH-1 downto 0);
      carry  : out std_logic;
      zero   : out std_logic
    );
  end component;
  signal pc_s       : std_logic_vector(3 downto 0) := (others => '0');
  signal ir_s       : std_logic_vector(7 downto 0) := (others => '0');
  signal halted_s   : std_logic := '0';
  signal alu_op_s   : std_logic_vector(2 downto 0) := (others => '0');
  signal use_imm_s  : std_logic := '0';
  signal ram_addr_s : std_logic_vector(3 downto 0) := (others => '0');
  signal ram_we_s   : std_logic := '0';
  signal acc_we_s   : std_logic := '0';
  signal out_we_s   : std_logic := '0';
  signal fz_we_s    : std_logic := '0';
  signal fc_we_s    : std_logic := '0';

  signal acc_r : std_logic_vector(3 downto 0) := (others => '0');
  signal z_r   : std_logic := '0';
  signal c_r   : std_logic := '0';
  signal out_r : std_logic_vector(3 downto 0) := (others => '0');

  signal rom_data_s : std_logic_vector(7 downto 0) := (others => '0');
  signal ram_dout_s : std_logic_vector(3 downto 0) := (others => '0');
  signal alu_b_s    : std_logic_vector(3 downto 0) := (others => '0');
  signal alu_res_s  : std_logic_vector(3 downto 0) := (others => '0');
  signal alu_c_s    : std_logic := '0';
  signal alu_z_s    : std_logic := '0';
begin
  out_value <= out_r;
  acc       <= acc_r;
  pc        <= pc_s;
  z         <= z_r;
  c         <= c_r;
  halted    <= halted_s;

  u_ctrl : control_unit
    port map (
      clk       => clk,
      rst       => rst,
      go        => go,
      z_in      => z_r,
      c_in      => c_r,
      rom_data  => rom_data_s,
      pc_out    => pc_s,
      ir_out    => ir_s,
      halted    => halted_s,
      alu_op    => alu_op_s,
      use_imm   => use_imm_s,
      ram_addr  => ram_addr_s,
      ram_we    => ram_we_s,
      acc_we    => acc_we_s,
      out_we    => out_we_s,
      flag_z_we => fz_we_s,
      flag_c_we => fc_we_s
    );

  u_rom : program_rom
    port map (
      addr => pc_s,
      data => rom_data_s
    );

  u_ram : data_ram
    generic map (
      ADDR_WIDTH => 4,
      DATA_WIDTH => 4
    )
    port map (
      clk  => clk,
      rst  => rst,
      we   => ram_we_s,
      addr => ram_addr_s,
      din  => acc_r,
      dout => ram_dout_s
    );

  -- ALU B-Mux: immediate vs RAM
  alu_b_s <= ir_s(3 downto 0) when use_imm_s = '1' else ram_dout_s;

  u_alu : alu
    generic map (
      WIDTH => 4
    )
    port map (
      a      => acc_r,
      b      => alu_b_s,
      op     => alu_op_s,
      result => alu_res_s,
      carry  => alu_c_s,
      zero   => alu_z_s
    );

  -- Datapath registers: ACC, Z, C, OUT
  process(clk)
  begin
    if rising_edge(clk) then
      if rst = '1' then
        acc_r <= (others => '0');
        z_r   <= '0';
        c_r   <= '0';
        out_r <= (others => '0');
      else
        if acc_we_s = '1' then
          acc_r <= alu_res_s;
        end if;
        if fz_we_s = '1' then
          z_r <= alu_z_s;
        end if;
        if fc_we_s = '1' then
          c_r <= alu_c_s;
        end if;
        if out_we_s = '1' then
          out_r <= acc_r;
        end if;
      end if;
    end if;
  end process;
end architecture rtl;
