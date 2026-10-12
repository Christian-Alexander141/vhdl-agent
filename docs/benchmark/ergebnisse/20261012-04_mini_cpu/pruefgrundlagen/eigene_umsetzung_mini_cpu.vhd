-- Eigene, vom System unabhängige Umsetzung von 04_mini_cpu.md (eine Entity, ein Prozess).
-- Dient nur als Gegenprobe: für die Referenz-Testbench und die vom System erzeugten Referenzmodelle.
library ieee; use ieee.std_logic_1164.all; use ieee.numeric_std.all;
entity mini_cpu is
  generic (TICK_CYCLES : positive := 50_000_000; DEBOUNCE_CYCLES : positive := 1_000_000);
  port (clk, rst, btn_step : in std_logic; sw : in std_logic_vector(2 downto 0); led : out std_logic_vector(3 downto 0));
end entity;
architecture rtl of mini_cpu is
  type rom_t is array (0 to 15) of std_logic_vector(7 downto 0);
  constant ROM : rom_t := (x"11",x"30",x"31",x"E0",x"20",x"41",x"DE",x"32",x"21",x"30",x"22",x"31",x"E0",x"B4",x"F0",x"00");
  type ram_t is array (0 to 15) of unsigned(3 downto 0);
  type st_t is (S_WAIT, S_FETCH, S_DECODE, S_EXECUTE, S_HALT);
  signal sw1, sw2 : std_logic_vector(2 downto 0);
  signal b1, b2, dout, rise : std_logic;
  signal dcnt : natural range 0 to DEBOUNCE_CYCLES - 1;
  signal tcnt : natural range 0 to TICK_CYCLES - 1;
  signal st : st_t; signal pc, acc, outr : unsigned(3 downto 0); signal ir : std_logic_vector(7 downto 0);
  signal z, c : std_logic; signal ram : ram_t; signal led_r : std_logic_vector(3 downto 0);
begin
  led <= led_r;
  process(clk)
    variable go : std_logic; variable a : natural; variable s : unsigned(4 downto 0); variable v : unsigned(3 downto 0); variable halted : std_logic;
  begin
    if rising_edge(clk) then
      if rst = '1' then
        sw1 <= (others => '0'); sw2 <= (others => '0'); b1 <= '0'; b2 <= '0'; dout <= '0'; rise <= '0'; dcnt <= 0; tcnt <= 0;
        st <= S_WAIT; pc <= (others => '0'); acc <= (others => '0'); outr <= (others => '0'); ir <= (others => '0');
        z <= '0'; c <= '0'; ram <= (others => (others => '0')); led_r <= (others => '0');
      else
        sw1 <= sw; sw2 <= sw1; b1 <= btn_step; b2 <= b1;
        rise <= '0';
        if b2 = dout then dcnt <= 0;
        elsif dcnt = DEBOUNCE_CYCLES - 1 then dout <= b2; dcnt <= 0; if b2 = '1' then rise <= '1'; end if;
        else dcnt <= dcnt + 1; end if;
        if tcnt = TICK_CYCLES - 1 then tcnt <= 0; else tcnt <= tcnt + 1; end if;
        if sw2(2) = '0' then go := '1' when tcnt = TICK_CYCLES - 1 else '0'; else go := rise; end if;
        a := to_integer(unsigned(ir(3 downto 0)));
        case st is
          when S_WAIT => if go = '1' then st <= S_FETCH; end if;
          when S_FETCH => ir <= ROM(to_integer(pc)); pc <= pc + 1; st <= S_DECODE;
          when S_DECODE => st <= S_EXECUTE;
          when S_EXECUTE =>
            st <= S_WAIT;
            case ir(7 downto 4) is
              when x"1" => acc <= unsigned(ir(3 downto 0)); z <= '1' when unsigned(ir(3 downto 0)) = 0 else '0';
              when x"2" => acc <= ram(a); z <= '1' when ram(a) = 0 else '0';
              when x"3" => ram(a) <= acc;
              when x"4" => s := ('0' & acc) + ('0' & ram(a)); acc <= s(3 downto 0); c <= s(4); z <= '1' when s(3 downto 0) = 0 else '0';
              when x"5" => v := acc - ram(a); acc <= v; c <= '1' when acc < ram(a) else '0'; z <= '1' when v = 0 else '0';
              when x"6" => v := acc and ram(a); acc <= v; c <= '0'; z <= '1' when v = 0 else '0';
              when x"7" => v := acc or ram(a); acc <= v; c <= '0'; z <= '1' when v = 0 else '0';
              when x"8" => v := acc xor ram(a); acc <= v; c <= '0'; z <= '1' when v = 0 else '0';
              when x"9" => v := acc(2 downto 0) & '0'; acc <= v; c <= acc(3); z <= '1' when v = 0 else '0';
              when x"A" => v := '0' & acc(3 downto 1); acc <= v; c <= acc(0); z <= '1' when v = 0 else '0';
              when x"B" => pc <= unsigned(ir(3 downto 0));
              when x"C" => if z = '1' then pc <= unsigned(ir(3 downto 0)); end if;
              when x"D" => if c = '1' then pc <= unsigned(ir(3 downto 0)); end if;
              when x"E" => outr <= acc;
              when x"F" => st <= S_HALT;
              when others => null;
            end case;
          when S_HALT => null;
        end case;
        halted := '1' when st = S_HALT else '0';
        case sw2(1 downto 0) is
          when "00" => led_r <= std_logic_vector(outr);
          when "01" => led_r <= std_logic_vector(acc);
          when "10" => led_r <= std_logic_vector(pc);
          when others => led_r <= halted & sw2(2) & c & z;
        end case;
      end if;
    end if;
  end process;
end architecture;
