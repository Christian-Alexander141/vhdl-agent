from bench.benchmark_api import list_tasks,get_prompt,evaluate

def simple_test ():

    erklärung="""alle aufgabe anzeigen 1 drücken 
                eine aufgabe wäheln 2 drücken 
                eine lösung bewerten 3 drücken"""

    simple_vhdl = """-- Aufgabe 1: Lauflicht, Arty S7, 100 MHz -> 1 s Tick
library ieee; use ieee.std_logic_1164.all; use ieee.numeric_std.all;
entity lauflicht is
  generic (CLK_FREQ : natural := 100_000_000; TICK_S : natural := 1);
  port (clk : in std_logic; btn : in std_logic_vector(3 downto 0);
        sw  : in std_logic_vector(3 downto 0);
        led : out std_logic_vector(3 downto 0));
end lauflicht;
architecture rtl of lauflicht is
  -- debounce BTN0: 3-stufig synchron + Zaehlerfreigabe
  signal sync : std_logic_vector(2 downto 0) := (others => '0');
  signal deb  : std_logic := '0'; signal deb_d : std_logic := '0';
  signal run_en : std_logic := '1'; -- Toggle: Start=an
  signal tick_cnt : natural range 0 to CLK_FREQ*TICK_S-1 := 0;
  signal pos : natural range 0 to 3 := 0;
  type fsm_t is (ST_STOP, ST_RUN); signal fsm : fsm_t := ST_RUN; -- Moore-FSM klein
begin
  -- Debounce: synchronisieren, stabil = 3x gleich
  process(clk) begin if rising_edge(clk) then
    sync <= sync(1 downto 0) & btn(0);
    if sync(2)=sync(1) and sync(1)=sync(0) then deb <= sync(2); end if;
    deb_d <= deb;
    if deb='1' and deb_d='0' then run_en <= not run_en; end if; -- steigende Flanke toggelt
  end if; end process;
  -- STOP haelt, RUN zaehlt tick -> Position weiter
  process(clk) begin if rising_edge(clk) then
    if run_en='0' then fsm <= ST_STOP; else fsm <= ST_RUN; end if;
    case fsm is
      when ST_RUN =>
        if tick_cnt = CLK_FREQ*TICK_S-1 then tick_cnt <= 0; pos <= (pos+1) mod 4;
        else tick_cnt <= tick_cnt+1; end if;
      when ST_STOP => tick_cnt <= tick_cnt; -- halten (Moore)
    end case;
  end if; end process;
  process(pos) begin led <= (others=>'0'); led(pos) <= '1'; end process;
end rtl;
"""
    simple_xdc = """# Arty S7 Rev.E Referenz (Digilent digilent-xdc, Arty-S7-50-Master.xdc)
set_property -dict { PACKAGE_PIN R2 IOSTANDARD SSTL135 } [get_ports { clk }]
create_clock -add -name sys_clk_pin -period 10.000 -waveform {0 5.000} [get_ports { clk }]
set_property -dict { PACKAGE_PIN H14 IOSTANDARD LVCMOS33 } [get_ports { sw[0] }]
set_property -dict { PACKAGE_PIN H18 IOSTANDARD LVCMOS33 } [get_ports { sw[1] }]
set_property -dict { PACKAGE_PIN G18 IOSTANDARD LVCMOS33 } [get_ports { sw[2] }]
set_property -dict { PACKAGE_PIN M5  IOSTANDARD SSTL135 } [get_ports { sw[3] }]
set_property -dict { PACKAGE_PIN E18 IOSTANDARD LVCMOS33 } [get_ports { led[0] }]
set_property -dict { PACKAGE_PIN F13 IOSTANDARD LVCMOS33 } [get_ports { led[1] }]
set_property -dict { PACKAGE_PIN E13 IOSTANDARD LVCMOS33 } [get_ports { led[2] }]
set_property -dict { PACKAGE_PIN H15 IOSTANDARD LVCMOS33 } [get_ports { led[3] }]
set_property -dict { PACKAGE_PIN G15 IOSTANDARD LVCMOS33 } [get_ports { btn[0] }]
set_property -dict { PACKAGE_PIN K16 IOSTANDARD LVCMOS33 } [get_ports { btn[1] }]
set_property -dict { PACKAGE_PIN J16 IOSTANDARD LVCMOS33 } [get_ports { btn[2] }]
set_property -dict { PACKAGE_PIN H13 IOSTANDARD LVCMOS33 } [get_ports { btn[3] }]
set_property INTERNAL_VREF 0.675 [get_iobanks 34]
"""
    demotask    = "task01"

    print(erklärung)
    print("select task  : ")
    print("auswahl :")

    select = input()

    if select == "1":
        print(list_tasks())
    elif select == "2":
        print("task id : ")
        task_id = input()
        print(get_prompt(f"task0{task_id}"))
    else:
        print("musterlösung für das lauflicht (task01):")
        task_id = demotask
        print(evaluate(task_id,simple_vhdl,simple_xdc))

if __name__ == "__main__":
    simple_test()
