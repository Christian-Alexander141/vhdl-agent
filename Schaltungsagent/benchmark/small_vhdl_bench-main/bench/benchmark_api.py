"""Kleiner VHDL-Benchmark (Arty S7) fuer ein Multiagentensystem.

Enthält:
- 10 Aufgaben als Prompt-fertige Dicts
- Referenz-VHDL (mögliche Lösung), Constraints (offizielle Arty-S7-Pins),
  Fehlerquellen-Hinweise
- API zum nacheinander Abfragen: list_tasks / get_task / get_prompt / get_next
- Deterministische Bewertung: evaluate(task_id, vhdl, xdc) -> Score 0..100

Offizielle Pin-Quelle: Digilent digilent-xdc, Arty-S7-50-Master.xdc (Rev. E):
  CLK100MHZ=R2 (SSTL135, 100 MHz), CLK12MHZ=F14,
  sw[0]=H14, sw[1]=H18, sw[2]=G18, sw[3]=M5 (SSTL135 + INTERNAL_VREF 0.675),
  led[0]=E18, led[1]=F13, led[2]=E13, led[3]=H15 (Sch=led[2..5]),
  btn[0]=G15, btn[1]=K16, btn[2]=J16, btn[3]=H13.
  Taster/Schalter aktiv-high. Board hat real nur 4 mono-LEDs (kein LED0..LED5!).
"""
from __future__ import annotations
import json
import os
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TASKS_JSON = os.path.join(BASE_DIR, "tasks.json")

GEMEINSAME_VORGABEN = """Gemeinsame Vorgaben:
- Zielhardware: Digilent Arty S7 (Spartan-7, Rev. E).
- VHDL, synthesefähig, modular, wiederverwendbar, aussagekräftige Kommentare.
- Vivado Flash Service verwenden, aber nicht selbst flashen.
- Keine alten Projekte wiederverwenden; jede Aufgabe neu implementieren.
- Keine erfundenen FPGA-Pins: nur offizielle Arty-S7-XDC-Pins (siehe Constraints).
- Keine Simulation-only-Konstrukte (kein 'wait for', kein 'after <Zeit>', keine files).
- std_logic / std_logic_vector (+ numeric_std) verwenden, kein 'bit' für Top-Ports.
- Taster/Schalter aktiv-high, LEDs aktiv-high (1 = an).
- Board-Realität: 100-MHz-Takt (CLK100MHZ, Pin R2), 4x LED, 4x SW, 4x BTN.
  Aufgaben, die LED0..LED5 oder 50 MHz fordern, auf led[0..3] bzw. 100 MHz abbilden und dokumentieren."""

# Offizielle Pins (Name -> (PACKAGE_PIN, IOSTANDARD))
OFFICIAL_PINS = {
    "CLK100MHZ": ("R2", "SSTL135"),
    "CLK12MHZ": ("F14", "LVCMOS33"),
    "sw[0]": ("H14", "LVCMOS33"),
    "sw[1]": ("H18", "LVCMOS33"),
    "sw[2]": ("G18", "LVCMOS33"),
    "sw[3]": ("M5", "SSTL135"),
    "led[0]": ("E18", "LVCMOS33"),
    "led[1]": ("F13", "LVCMOS33"),
    "led[2]": ("E13", "LVCMOS33"),
    "led[3]": ("H15", "LVCMOS33"),
    "btn[0]": ("G15", "LVCMOS33"),
    "btn[1]": ("K16", "LVCMOS33"),
    "btn[2]": ("J16", "LVCMOS33"),
    "btn[3]": ("H13", "LVCMOS33"),
}
ALLOWED_PIN_NUMBERS = {pin for pin, _std in OFFICIAL_PINS.values()}
PIN_TO_STD = {pin: std for _n, (pin, std) in OFFICIAL_PINS.items()}

XDC_REF = """# Arty S7 Rev.E Referenz (Digilent digilent-xdc, Arty-S7-50-Master.xdc)
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

# ---------------------------------------------------------------- Referenz-VHDL
REF_T01 = """-- Aufgabe 1: Lauflicht, Arty S7, 100 MHz -> 1 s Tick
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

REF_T02 = """-- Aufgabe 2: 4-Bit Gray-Zaehler 0..9, Arty S7
library ieee; use ieee.std_logic_1164.all; use ieee.numeric_std.all;
entity gray_counter is
  generic (CLK_FREQ : natural := 100_000_000);
  port (clk : in std_logic; btn : in std_logic_vector(3 downto 0);
        sw : in std_logic_vector(3 downto 0);
        led : out std_logic_vector(3 downto 0));
end gray_counter;
architecture rtl of gray_counter is
  signal tick : std_logic := '0'; signal c : natural range 0 to CLK_FREQ-1 := 0;
  signal bin : unsigned(3 downto 0) := (others=>'0');
  signal sync : std_logic_vector(2 downto 0) := (others=>'0');
  signal rst : std_logic;
begin
  -- BTN0 entprellt als synchroner Reset (aktiv-high)
  process(clk) begin if rising_edge(clk) then sync <= sync(1 downto 0) & btn(0); end if; end process;
  rst <= '1' when sync(2)=sync(1) and sync(1)=sync(0) and sync(2)='1' else '0';
  -- 1-s-Taktteilung
  process(clk) begin if rising_edge(clk) then
    tick <= '0';
    if c = CLK_FREQ-1 then c <= 0; tick <= '1'; else c <= c+1; end if;
  end if; end process;
  -- Binaer 0..9, dann Gray = bin xor (bin>>1)
  process(clk) begin if rising_edge(clk) then
    if rst='1' then bin <= (others=>'0');
    elsif tick='1' then
      if bin = 9 then bin <= (others=>'0'); else bin <= bin+1; end if;
    end if;
  end if; end process;
  led <= std_logic_vector(bin xor ('0' & bin(3 downto 1))); -- Gray-Code
end rtl;
"""

REF_T03 = """-- Aufgabe 3: 4-Bit-Addierer + Arty-Top (SW=a, BTN=b, LED=summe)
library ieee; use ieee.std_logic_1164.all; use ieee.numeric_std.all;
entity adder4 is
  port (a, b : in std_logic_vector(3 downto 0);
        sum : out std_logic_vector(3 downto 0); cout : out std_logic);
end adder4;
architecture rtl of adder4 is
  signal tmp : unsigned(4 downto 0);
begin
  tmp <= ('0' & unsigned(a)) + ('0' & unsigned(b)); -- rein kombinatorisch, synthesefaehig
  sum <= std_logic_vector(tmp(3 downto 0)); cout <= tmp(4);
end rtl;
-- Top fuer Arty S7: Uebertrag auf led(3) ODER als Blinken? Hier: Summe auf led, Cout verworfen/doku.
library ieee; use ieee.std_logic_1164.all;
entity top_adder is
  port (clk : in std_logic; sw : in std_logic_vector(3 downto 0);
        btn : in std_logic_vector(3 downto 0); led : out std_logic_vector(3 downto 0));
end top_adder;
architecture rtl of top_adder is
  component adder4 port (a,b: in std_logic_vector(3 downto 0);
    sum: out std_logic_vector(3 downto 0); cout: out std_logic); end component;
  signal s : std_logic_vector(3 downto 0); signal co : std_logic;
begin
  u: adder4 port map (a=>sw, b=>btn, sum=>s, cout=>co);
  led <= s; -- Hinweis: Cout geht mangels 5. LED verloren -> Doku; Alternative RGB-LED
end rtl;
"""

REF_T04_SRAM = """-- Aufgabe 4: parametrisches synchrones SRAM, read-before-write, tau-Pipeline
library ieee; use ieee.std_logic_1164.all; use ieee.numeric_std.all;
entity sram is
  generic (data_bits : natural := 4; addr_bits : natural := 4; tau_cycles : natural := 1);
  port (clk : in std_logic;
        address : in unsigned(addr_bits-1 downto 0);   -- SW0..SW3, SW0=LSB
        data_in : in signed(data_bits-1 downto 0);     -- BTN0..BTN3
        data_out: out signed(data_bits-1 downto 0));   -- LED, MSB->LED3 (Board hat nur 4 LEDs)
end sram;
architecture rtl of sram is
  type ram_t is array (0 to 2**addr_bits-1) of signed(data_bits-1 downto 0);
  signal ram : ram_t := (others => (others => '0'));
  -- Pipeline tau_cycles
  type pipe_t is array (0 to 15) of signed(data_bits-1 downto 0);
  signal pipe : pipe_t := (others => (others => '0'));
begin
  assert tau_cycles>=1 and tau_cycles<=16 report "tau_cycles ausserhalb 1..16" severity failure;
  process(clk) -- read-before-write: erst lesen (alter Wert), dann ggf. schreiben
    variable rdata : signed(data_bits-1 downto 0);
  begin if rising_edge(clk) then
    rdata := ram(to_integer(address)); -- alter Wert
    if data_in /= to_signed(0, data_bits) then
      ram(to_integer(address)) <= data_in; -- synchroner Write
    end if;
    pipe(0) <= rdata; -- in Pipeline schieben
    for i in 1 to 15 loop
      if i < tau_cycles then pipe(i) <= pipe(i-1); end if;
    end loop;
  end if; end process;
  data_out <= pipe(tau_cycles-1); -- permanent getrieben, kein Tri-State
end rtl;
"""
REF_T04_TB = """-- tb_ram: Testfaelle Schreiben/Lesen, R/W-gleichzeitig, read-before-write, tau
library ieee; use ieee.std_logic_1164.all; use ieee.numeric_std.all;
entity tb_ram is end tb_ram;
architecture sim of tb_ram is
  signal clk: std_logic:='0'; signal addr: unsigned(3 downto 0):=(others=>'0');
  signal di, dout: signed(3 downto 0):=(others=>'0');
  component sram generic (data_bits,addr_bits,tau_cycles: natural);
    port (clk: in std_logic; address: in unsigned(3 downto 0);
      data_in: in signed(3 downto 0); data_out: out signed(3 downto 0)); end component;
begin
  dut: sram generic map (4,4,1) port map (clk,addr,di,dout);
  clk <= not clk after 5 ns; -- nur Testbench, kein Synthese-Code
  process begin
    addr <= x"3"; di <= to_signed(5,4); wait until rising_edge(clk); wait until rising_edge(clk);
    di <= to_signed(0,4); wait until rising_edge(clk); wait until rising_edge(clk);
    assert dout=to_signed(5,4) report "Schreiben/Lesen fail" severity error; -- Schreiben/Lesen
    di <= to_signed(-3,4); wait until rising_edge(clk); -- gleichzeitig R/W: dout muss ALT sein
    assert dout=to_signed(5,4) report "read-before-write fail" severity error;
    wait until rising_edge(clk); wait; -- tau-Verzoegerung pruefen
  end process;
end sim;
"""

REF_T05_TIMER = """-- Aufgabe 5b: timer (load/load_value/ready), 31 Bit fuer 1.5e9 Takte
library ieee; use ieee.std_logic_1164.all; use ieee.numeric_std.all;
entity timer is
  port (clock: in std_logic; reset: in std_logic; load: in std_logic;
        load_value: in unsigned(30 downto 0); ready: out std_logic);
end timer;
architecture rtl of timer is
  signal cnt: unsigned(30 downto 0) := (others=>'0'); signal active: std_logic:='0';
begin
  process(clock) begin if rising_edge(clock) then
    if reset='1' then cnt<=(others=>'0'); active<='0'; ready<='0';
    elsif load='1' then cnt<=load_value; active<='1'; ready<='0';
    elsif active='1' then
      if cnt=0 then ready<='1'; active<='0'; else cnt<=cnt-1; ready<='0'; end if;
    else ready<='0'; end if;
  end if; end process;
end rtl;
"""
REF_T05_CONTROL = """-- Aufgabe 5c: control, Moore-FSM 8 Phasen (30s/2s/4s bei 100 MHz)
library ieee; use ieee.std_logic_1164.all; use ieee.numeric_std.all;
entity control is
  port (clock: in std_logic; reset: in std_logic; enable: in std_logic; ready: in std_logic;
        load: out std_logic; load_value: out unsigned(30 downto 0);
        rot_1, gelb_1, gruen_1, rot_2, gelb_2, gruen_2: out std_logic);
end control;
architecture rtl of control is
  type st_t is (P1,P2,P3,P4,P5,P6,P7,P8); signal st: st_t:=P1; signal armed: std_logic:='0';
  constant S30: unsigned(30 downto 0) := to_unsigned(1500000000-1,31); -- 30s@100MHz (real)
  constant S4 : unsigned(30 downto 0) := to_unsigned(200000000-1,31); -- 4s (Aufgabe: 200M)
  constant S2 : unsigned(30 downto 0) := to_unsigned(100000000-1,31); -- 2s (Aufgabe: 100M)
begin
  process(clock) begin if rising_edge(clock) then
    if reset='1' then st<=P1; armed<='0'; load<='0';
    elsif enable='1' then
      load<='0';
      if armed='0' then -- Phase laden
        armed<='1'; load<='1';
        case st is when P1=>load_value<=S30; when P2=>load_value<=S2;
          when P3=>load_value<=S4; when P4=>load_value<=S2; when P5=>load_value<=S30;
          when P6=>load_value<=S2; when P7=>load_value<=S4; when others=>load_value<=S2; end case;
      elsif ready='1' then -- naechste Phase (Moore: Ausgaenge nur von st)
        armed<='0';
        case st is when P1=>st<=P2; when P2=>st<=P3; when P3=>st<=P4; when P4=>st<=P5;
          when P5=>st<=P6; when P6=>st<=P7; when P7=>st<=P8; when others=>st<=P1; end case;
      end if;
    end if;
  end if; end process;
  process(st) begin -- Moore-Ausgaenge konstant pro Phase
    (rot_1,gelb_1,gruen_1,rot_2,gelb_2,gruen_2) <= ('0','0','0','0','0','0');
    case st is
      when P1 => gruen_1<='1'; rot_2<='1'; when P2 => gelb_1<='1'; rot_2<='1';
      when P3 => rot_1<='1'; rot_2<='1'; when P4 => rot_1<='1'; rot_2<='1'; gelb_2<='1';
      when P5 => rot_1<='1'; gruen_2<='1'; when P6 => rot_1<='1'; gelb_2<='1';
      when P7 => rot_1<='1'; rot_2<='1'; when others => rot_1<='1'; rot_2<='1';
    end case;
  end process;
end rtl;
"""
REF_T05_TOP = """-- Aufgabe 5a: ampel Top (SW0=Reset, SW1=Enable, LED0..3=Phasen; Board hat nur 4 LEDs!)
library ieee; use ieee.std_logic_1164.all; use ieee.numeric_std.all;
entity ampel is
  port (clk: in std_logic; sw: in std_logic_vector(3 downto 0);
        btn: in std_logic_vector(3 downto 0); led: out std_logic_vector(3 downto 0));
end ampel;
architecture rtl of ampel is
  component control port (clock,reset,enable,ready: in std_logic; load: out std_logic;
    load_value: out unsigned(30 downto 0);
    rot_1,gelb_1,gruen_1,rot_2,gelb_2,gruen_2: out std_logic); end component;
  component timer port (clock,reset,load: in std_logic;
    load_value: in unsigned(30 downto 0); ready: out std_logic); end component;
  signal ld, rdy: std_logic; signal lv: unsigned(30 downto 0);
  signal r1,y1,g1,r2,y2,g2: std_logic;
begin
  c: control port map (clk, sw(0), sw(1), rdy, ld, lv, r1,y1,g1,r2,y2,g2);
  t: timer port map (clk, sw(0), ld, lv, rdy);
  -- 6 Signale -> 4 LEDs: HS-Gruen, HS-Gelb/Rot, QS-Gruen, QS-Gelb/Rot (Doku!)
  led(0)<=g1; led(1)<=y1 or r1; led(2)<=g2; led(3)<=y2 or r2;
end rtl;
"""

REF_T06 = """-- Aufgabe 6: 4-Bit Up/Down-Zaehler mit Bediensteuerung
library ieee; use ieee.std_logic_1164.all; use ieee.numeric_std.all;
entity updown is
  port (clk: in std_logic; sw: in std_logic_vector(3 downto 0);
        btn: in std_logic_vector(3 downto 0); led: out std_logic_vector(3 downto 0));
  -- SW0=Richtung(1=up), SW1=Enable, SW2=Schritt(1=2), SW3=Auto/Manuell
  -- BTN0=Reset, BTN1=Start/Stop, BTN2=manUp, BTN3=manDown
end updown;
architecture rtl of updown is
  signal cnt: unsigned(3 downto 0):=(others=>'0');
  signal tick: std_logic:='0'; signal div: natural range 0 to 100_000_000-1:=0;
  signal bsync: std_logic_vector(3 downto 0):=(others=>'0');
  signal bdeb: std_logic_vector(3 downto 0):=(others=>'0');
  signal bprev: std_logic_vector(3 downto 0):=(others=>'0');
  signal edge: std_logic_vector(3 downto 0);
  signal running: std_logic:='0'; signal step: natural range 1 to 2;
begin
  step <= 2 when sw(2)='1' else 1; -- Schrittweite
  process(clk) begin if rising_edge(clk) then -- Debounce: 2-stufig + Flanke
    bsync <= btn; bdeb <= bsync; bprev <= bdeb;
  end if; end process;
  edge <= bdeb and not bprev; -- steigende Flanken
  process(clk) begin if rising_edge(clk) then -- 1-s-Taktteilung
    tick<='0'; if div=100_000_000-1 then div<=0; tick<='1'; else div<=div+1; end if;
  end if; end process;
  process(clk) begin if rising_edge(clk) then
    if edge(0)='1' then cnt<=(others=>'0'); -- Reset
    elsif edge(1)='1' and sw(3)='1' then running <= not running; end if; -- Start/Stop Auto
    if sw(3)='1' then -- Automatik
      if running='1' and sw(1)='1' and tick='1' then
        if sw(0)='1' then cnt<=cnt+step; else cnt<=cnt-step; end if; -- zyklisch (wrap)
      end if;
    else -- manuell
      if edge(2)='1' then cnt<=cnt+step; end if;
      if edge(3)='1' then cnt<=cnt-step; end if;
    end if;
  end if; end process;
  led <= std_logic_vector(cnt);
end rtl;
"""

REF_T07 = """-- Aufgabe 7: Wuerfel 1..6, LFSR + FSM
library ieee; use ieee.std_logic_1164.all; use ieee.numeric_std.all;
entity wuerfel is
  port (clk: in std_logic; sw: in std_logic_vector(3 downto 0);
        btn: in std_logic_vector(3 downto 0); led: out std_logic_vector(3 downto 0));
  -- BTN0=Wuerfeln, BTN1=Reset, BTN2=Auto, BTN3=Schritt; SW0=Tempo; LED0-2=Zahl-1 binaer, LED3=aktiv
end wuerfel;
architecture rtl of wuerfel is
  type st_t is (IDLE, ROLL, DONE); signal st: st_t:=IDLE;
  signal lfsr: unsigned(3 downto 0):="1011"; -- Seed/=0, kein Lockup
  signal val: natural range 1 to 6 := 1;
  signal tick: std_logic:='0'; signal div: natural:=0;
  signal b: std_logic_vector(3 downto 0):=(others=>'0'); signal bp: std_logic_vector(3 downto 0):=(others=>'0');
  signal edge: std_logic_vector(3 downto 0); signal auto: std_logic:='0';
  signal anim: natural range 0 to 15:=0;
begin
  process(clk) begin if rising_edge(clk) then b<=btn; bp<=b; end if; end process; -- Debounce einfach
  edge <= b and not bp;
  process(clk) -- Tempo: SW0=0 langsam (~5Hz), 1=schnell (~20Hz)
    variable lim: natural;
  begin if rising_edge(clk) then
    lim := 20_000_000 when sw(0)='0' else 5_000_000; tick<='0';
    if div>=lim then div<=0; tick<='1'; else div<=div+1; end if;
  end if; end process;
  process(clk) -- LFSR x^4+x+1, laeuft frei; 1..6 via mod
    variable fb: std_logic;
  begin if rising_edge(clk) then
    if edge(1)='1' then st<=IDLE; val<=1; auto<='0';
    else
      fb := lfsr(3) xor lfsr(2); -- Polynom
      if tick='1' or st=ROLL then lfsr <= lfsr(2 downto 0) & fb; end if;
      if edge(2)='1' then auto <= not auto; end if;
      case st is
        when IDLE => if edge(0)='1' or edge(3)='1' or auto='1' then st<=ROLL; anim<=10; end if;
        when ROLL =>
          if tick='1' then
            val <= (to_integer(lfsr) mod 6)+1; -- immer 1..6 begrenzt
            if anim=0 then st<=DONE; else anim<=anim-1; end if;
          end if;
        when DONE => if edge(0)='1' or auto='1' then st<=ROLL; anim<=10; end if;
      end case;
    end if;
  end if; end process;
  led(2 downto 0) <= std_logic_vector(to_unsigned(val-1,3)); -- Zahl binaer (0..5)
  led(3) <= '1' when st=ROLL else '0'; -- Wuerfelvorgang aktiv
end rtl;
"""

REF_T08 = """-- Aufgabe 8: Codeschloss, Moore-FSM, Sollcode 1010, max 3 Versuche
library ieee; use ieee.std_logic_1164.all; use ieee.numeric_std.all;
entity schloss is
  generic (CODE: std_logic_vector(3 downto 0):="1010");
  port (clk: in std_logic; sw: in std_logic_vector(3 downto 0);
        btn: in std_logic_vector(3 downto 0); led: out std_logic_vector(3 downto 0));
  -- BTN0=Confirm, BTN1=Reset/Lock, BTN2=Retry, BTN3=Service; LED0=lock, LED1=busy, LED2=open, LED3=err
end schloss;
architecture rtl of schloss is
  type st_t is (LOCKED, CHECK, OPEN, FAIL, BLOCKED); signal st: st_t:=LOCKED;
  signal fails: natural range 0 to 3:=0;
  signal tmo: natural range 0 to 100_000_000*10:=0; -- 10 s Timeout
  signal b, bp: std_logic_vector(3 downto 0):=(others=>'0'); signal edge: std_logic_vector(3 downto 0);
begin
  process(clk) begin if rising_edge(clk) then b<=btn; bp<=b; end if; end process; -- Debounce
  edge <= b and not bp; -- nur steigende Flanken
  process(clk) begin if rising_edge(clk) then
    if edge(1)='1' then st<=LOCKED; fails<=0; tmo<=0; -- Reset/Lock
    else case st is
      when LOCKED =>
        tmo<=0;
        if edge(3)='1' then st<=OPEN; -- Service/Testmodus
        elsif edge(0)='1' or edge(2)='1' then st<=CHECK; end if;
      when CHECK => -- ein Takt pruefen (Moore: LED1 an)
        if sw=CODE then st<=OPEN; fails<=0; tmo<=0;
        else
          if fails+1>=3 then st<=BLOCKED; else st<=FAIL; end if;
          fails<=fails+1;
        end if;
      when FAIL => if edge(2)='1' or edge(0)='1' then st<=CHECK; end if; -- naechster Versuch
      when OPEN => -- Timeout 10 s -> verriegeln
        if tmo>=100_000_000*10-1 then st<=LOCKED; tmo<=0; else tmo<=tmo+1; end if;
      when BLOCKED => null; -- nur BTN1 entsperrt
    end case; end if;
  end if; end process;
  led(0)<='1' when st=LOCKED else '0'; led(1)<='1' when st=CHECK or st=FAIL else '0';
  led(2)<='1' when st=OPEN else '0'; led(3)<='1' when st=BLOCKED or st=FAIL else '0';
end rtl;
"""

REF_T09 = """-- Aufgabe 9: 4-Bit Countdown 0..15 s, 1-s-Takt
library ieee; use ieee.std_logic_1164.all; use ieee.numeric_std.all;
entity countdown is
  port (clk: in std_logic; sw: in std_logic_vector(3 downto 0);
        btn: in std_logic_vector(3 downto 0); led: out std_logic_vector(3 downto 0));
  -- SW=Startwert, BTN0=Laden, BTN1=Start/Stop, BTN2=Reset, BTN3=Pause
end countdown;
architecture rtl of countdown is
  signal val: unsigned(3 downto 0):=(others=>'0');
  signal run: std_logic:='0'; signal tick1s: std_logic:='0';
  signal div: natural range 0 to 100_000_000-1:=0;
  signal blink: std_logic:='0'; signal bdiv: natural range 0 to 25_000_000-1:=0;
  signal b,bp: std_logic_vector(3 downto 0):=(others=>'0'); signal edge: std_logic_vector(3 downto 0);
begin
  process(clk) begin if rising_edge(clk) then b<=btn; bp<=b; end if; end process;
  edge <= b and not bp;
  process(clk) begin if rising_edge(clk) then -- 1-s-Takt
    tick1s<='0'; if div=100_000_000-1 then div<=0; tick1s<='1'; else div<=div+1; end if;
    if bdiv=25_000_000-1 then bdiv<=0; blink<=not blink; else bdiv<=bdiv+1; end if; -- Blink ~4Hz
  end if; end process;
  process(clk) begin if rising_edge(clk) then -- reproduzierbar: Laden setzt run=0
    if edge(2)='1' then val<=(others=>'0'); run<='0';
    elsif edge(0)='1' then val<=unsigned(sw); run<='0';
    elsif edge(1)='1' then
      if val/=0 then run <= not run; end if;
    elsif edge(3)='1' then run<='0'; -- Pause
    elsif run='1' and tick1s='1' then
      if val=0 then run<='0'; else val<=val-1; if val=1 then run<='0'; end if; end if;
    end if;
  end if; end process;
  led <= std_logic_vector(val) when (val/=0 or blink='1') else "0000"; -- bei Ablauf blinken->0/aus
end rtl;
"""

REF_T10 = """-- Aufgabe 10: 2-Etagen-Aufzug, Moore-FSM + Timer
library ieee; use ieee.std_logic_1164.all; use ieee.numeric_std.all;
entity aufzug is
  port (clk: in std_logic; sw: in std_logic_vector(3 downto 0);
        btn: in std_logic_vector(3 downto 0); led: out std_logic_vector(3 downto 0));
  -- SW0=ReqEG, SW1=ReqOG, SW2=Tuermodus, SW3=Auto; BTN0=Start, BTN1=Stop, BTN2=Reset, BTN3=NotAus/Quit
  -- LED0=Etage(0=EG,1=OG), LED1=Bewegung, LED2=TuerAuf, LED3=NotAus
end aufzug;
architecture rtl of aufzug is
  type st_t is (EG_AUF, EG_ZU, HOCH, OG_AUF, OG_ZU, RUNTER, NOTAUS);
  signal st, nxt: st_t:=EG_AUF;
  signal cnt: natural range 0 to 200_000_000-1:=0; -- 2 s Timer @100MHz
  signal done: std_logic:='0';
  signal req_eg, req_og: std_logic:='0'; -- zwischengespeichert
  signal b,bp: std_logic_vector(3 downto 0):=(others=>'0'); signal edge: std_logic_vector(3 downto 0);
begin
  process(clk) begin if rising_edge(clk) then b<=btn; bp<=b; end if; end process;
  edge <= b and not bp;
  process(clk) begin if rising_edge(clk) then -- Anfragen latchen
    if sw(0)='1' then req_eg<='1'; end if; if sw(1)='1' then req_og<='1'; end if;
    if edge(2)='1' then req_eg<='0'; req_og<='0'; st<=EG_AUF; end if; -- Reset
    if edge(3)='1' then if st=NOTAUS then st<=EG_AUF; else st<=NOTAUS; end if; end if; -- NotAus/Quit
  end if; end process;
  process(clk) begin if rising_edge(clk) then -- Timer 2 s
    done<='0';
    if st=EG_AUF or st=EG_ZU or st=HOCH or st=OG_AUF or st=OG_ZU or st=RUNTER then
      if cnt=200_000_000-1 then cnt<=0; done<='1'; else cnt<=cnt+1; end if;
    else cnt<=0; end if;
  end if; end process;
  process(clk) begin if rising_edge(clk) then -- FSM (Moore)
    if st=NOTAUS then null;
    else case st is
      when EG_AUF => if done='1' then st<=EG_ZU; end if;
      when EG_ZU => if done='1' then
          if req_og='1' then st<=HOCH; req_og<='0'; elsif req_eg='1' then req_eg<='0'; st<=EG_AUF; end if;
        elsif edge(0)='1' and (sw(3)='1' or req_og='1') then st<=HOCH; end if;
      when HOCH => if done='1' then st<=OG_AUF; end if;
      when OG_AUF => if done='1' then st<=OG_ZU; end if;
      when OG_ZU => if done='1' then
          if req_eg='1' then st<=RUNTER; req_eg<='0'; elsif req_og='1' then req_og<='0'; st<=OG_AUF; end if;
        elsif edge(0)='1' and (sw(3)='1' or req_eg='1') then st<=RUNTER; end if;
      when RUNTER => if done='1' then st<=EG_AUF; end if;
      when others => st<=EG_AUF;
    end case;
    if edge(1)='1' then null; end if; -- Stop: Timer anhalten (vereinfacht: ignoriert, Doku)
    end if;
  end if; end process;
  led(0) <= '1' when (st=OG_AUF or st=OG_ZU or st=RUNTER) else '0';
  led(1) <= '1' when (st=HOCH or st=RUNTER) else '0';
  led(2) <= '1' when (st=EG_AUF or st=OG_AUF) else '0';
  led(3) <= '1' when st=NOTAUS else '0';
end rtl;
"""

# ---------------------------------------------------------------- Task-Liste
def _t(id_, titel, beschreibung, aufgabe, referenz_vhdl, constraints,
       fehlerquellen, pflicht_ports, required_keywords,
       need_debounce, need_fsm, need_clock=True):
    return {
        "id": id_, "titel": titel,
        "beschreibung": beschreibung, "aufgabe": aufgabe,
        "referenz_vhdl": referenz_vhdl, "constraints": constraints,
        "fehlerquellen": fehlerquellen,
        "pflicht_ports": pflicht_ports, "required_keywords": required_keywords,
        "need_debounce": need_debounce, "need_fsm": need_fsm,
        "need_clock": need_clock,
    }


TASKS = [
    _t("task01", "Lauflicht",
       "4-LED-Lauflicht mit 1-s-Takt, BTN0 Start/Stop-Toggle, entprellt.",
       "Erstelle VHDL für ein Lauflicht auf dem Digilent Arty S7: LED5 bis LED2 werden zyklisch "
       "nacheinander aktiviert (Board-Realität: auf led[0..3] abbilden). Gut sichtbare Verzögerung "
       "(z.B. 1 s via Zähler). BTN0 stoppt an aktueller LED; Loslassen+Drücken setzt fort (Toggle). "
       "Entity mit LED-/Taster-Ports, kleiner Zustandsautomat, std_logic/vector, BTN0 entprellen. "
       "Synthesefähig, modular, wiederverwendbar.",
       REF_T01, XDC_REF,
       ["Board hat nur 4 LEDs: LED5..LED2/LED0..LED5 nicht 1:1 übernehmbar, Abbildung doku-pflichtig.",
        "BTN ohne Debounce loslassen -> Mehrfach-Toggle.",
        "Erfundene Pins statt H14/H18/G18/M5/E18/F13/E13/H15/G15/K16/J16/H13/R2.",
        "'wait for'/'after'-Delays statt Zähler (nicht synthesefähig).",
        "Flanke statt Pegel für Toggle vergessen -> Dauer-Stop."],
       ["clk", "btn", "led"], ["rising_edge", "mod", "run_en"],
       True, True),
    _t("task02", "4-Bit-Gray-Code-Zähler",
       "Automatischer Gray-Zähler 0..9 mit Reset BTN0, Anzeige auf LEDs.",
       "Erstelle VHDL für 4-Bit-Gray-Code-Zähler Arty S7: automatischer Start, Gray 0000..1001 (0-9) "
       "dann 0000. Ausgabe auf LED5-LED2 (real: led[0..3]). Optional Binärwert. BTN0=Reset auf 0000, "
       "entprellt. Entity+Architecture, Zählerlogik/kleiner FSM, std_logic/vector, Kommentare, synthesefähig.",
       REF_T02, XDC_REF,
       ["Falsche Gray-Folge (binär statt Gray: Gray=bin xor bin>>1).",
        "9->10 statt 9->0 (nur 0..9 gefordert).",
        "Asynchroner Reset ohne Sync -> Metastabilität.",
        "1-s-Teiler mit falscher Taktbasis (50 statt 100 MHz)."],
       ["clk", "btn", "led"], ["xor", "bin", "tick"],
       True, False),
    _t("task03", "4-Bit-Addierer",
       "Rein kombinatorischer 4-Bit-Addierer mit Arty-Top (SW=a, BTN=b, LED=Summe).",
       "Implementiere 4-Bit-Addierer in VHDL für Arty S7 (gemeinsame Vorgaben, fpgagent-Prompt, "
       "Vivado Flash Service, neu implementieren, synthesefähig/sauber). Empfehlung: adder4 (a,b->sum,cout) "
       "+ Top (sw->a, btn->b, led->sum; Cout-Problem bei nur 4 LEDs dokumentieren).",
       REF_T03, XDC_REF,
       ["Cout unterschlagen ohne Doku (nur 4 LEDs).",
        "BTN direkt als statisches b ohne Hinweis (Taster prellen/halten).",
        "Vorzeichenfehler: signed/unsigned gemischt ohne numeric_std.",
        "Latch durch unvollständige case/if-Zuweisung."],
       ["clk", "sw", "btn", "led"], ["adder4", "unsigned", "cout", "sum"],
       False, False, need_clock=False),
    _t("task04", "Parametrisches synchrones SRAM",
       "SRAM data_bits=4/addr_bits=4/tau=1, read-before-write, Pipeline, inkl. Testbench.",
       "Erstelle parametrische SRAM-Implementierung (Generics data_bits=4, addr_bits=4, tau_cycles=1). "
       "Ports: clk, address SW0..3, data_in BTN0..3, data_out LED. Verhalten: pro rising_edge lesen, "
       "Ausgabe nach tau Takten; data_in/=0 -> synchron schreiben; R/W-gleichzeitig = read-before-write; "
       "data_out permanent, kein Tri-State; ram_t + to_integer; tau als Pipeline; Debounce empfohlen; "
       "Kommentare zu read-before-write. Lieferung sram.vhd + tb_ram.vhd mit Tests (R/W, R/W-gleichzeitig, "
       "read-before-write, tau).",
       {"sram.vhd": REF_T04_SRAM, "tb_ram.vhd": REF_T04_TB}, XDC_REF,
       ["Write-vor-Read implementiert statt read-before-write.",
        "data_out mit Tri-State/'Z' (auf FPGA innen unzulässig).",
        "tau als 'after'-Delay statt Register-Pipeline.",
        "to_integer ohne numeric_std / falscher Adressbereich.",
        "BTN-Schreiben ohne Entprellung -> Mehrfach-Write."],
       ["clk", "address", "data_in", "data_out"],
       ["ram_t", "to_integer", "tau_cycles", "rising_edge", "read-before-write"],
       False, False),
    _t("task05", "Ampelsteuerung",
       "Hierarchie ampel/control/timer, Moore-FSM 8 Phasen, 30/4/2 s, 31-Bit-Timer.",
       "VHDL-Ampel Übung 5 für Arty S7, Hierarchie ampel(control,timer). LED0=RotHS..LED5=GrünQS "
       "(real: 6 Signale auf 4 LEDs abbilden+doku). SW0=Reset, SW1=Start/Enable. Board-Takt real 100 MHz "
       "(Aufgabe nennt 50 MHz/1.5e9 Takte -> anpassen+doku). Timer>=1.5e9 Takte (31 Bit), "
       "Ports clock/reset/load/load_value/ready. Moore-FSM Phasen 1..8 (Grün/Rot 30s, Gelb/Rot 2s, "
       "Rot/Rot 4s, Rot/RotGelb 2s, Rot/Grün 30s, Rot/Gelb 2s, Rot/Rot 4s, ->1). Dateien ampel/control/timer.vhd "
       "+ XDC. Abnahme: SW0 Reset, SW1 Start, LED=Phase, Phasenwechsel, Vivado-synthesefähig. Doku: Dateien, "
       "SW, LED, XDC, Timer/FSM.",
       {"ampel.vhd": REF_T05_TOP, "control.vhd": REF_T05_CONTROL, "timer.vhd": REF_T05_TIMER},
       XDC_REF,
       ["Timer zu schmal (<31 Bit) -> Überlauf bei 1.5e9; 50-MHz-Werte ungeprüft für 100 MHz übernommen.",
        "Mealy statt Moore (LED flackert bei ready).",
        "6 LEDs 1:1 gefordert, Board hat 4 -> ohne Abbildung undurchführbar.",
        "load/ready-Handshake ohne armed-Flag -> Timer-Reload-Loop.",
        "Reset nur FSM oder nur Timer -> inkonsistente Phase."],
       ["clock", "clk", "reset", "sw", "load", "ready", "led"],
       ["moore", "load_value", "ready", "rot_1", "gruen_2"],
       False, True),
    _t("task06", "4-Bit-Up/Down-Zähler",
       "Synchroner Zähler mit Richtung/Enable/Schritt/Auto, Tasterbedienung, Wrap.",
       "4-Bit synchroner Up/Down-Zähler Arty S7: SW0=Richtung(0 down/1 up), SW1=Enable, SW2=Schritt(1/2), "
       "SW3=Auto/Manuell, BTN0=Reset, BTN1=Start/Stop Auto, BTN2=manUp, BTN3=manDown, LED0..3=Stand binär. "
       "Automatik 1-s-Teilung, Buttons entprellen+Flanken, Überlauf zyklisch, modular (Zähler/Debounce/Bedienlogik).",
       REF_T06, XDC_REF,
       ["Schritt 2 als +2 ohne Wrap-Denken (15+2 muss 1 sein, unsigned regelt).",
        "Manuell-Taster als Pegel statt Flanke -> Dauerzählen.",
        "Auto/Manuell vermischt (BTN2 wirkt auch in Auto).",
        "Debounce fehlt -> Reset/Start prellt mehrfach."],
       ["clk", "sw", "btn", "led"], ["rising_edge", "running", "step", "tick"],
       True, False),
    _t("task07", "Elektronischer Würfel (LFSR)",
       "Würfel 1..6 mit LFSR, FSM, Animation, Auto-Modus, LED-Anzeige.",
       "Digitaler Würfel 1..6 mit FSM+pseudo-Zufall (LFSR): BTN0=Würfeln, BTN1=Reset, BTN2=Auto, BTN3=Schritt, "
       "SW0=Tempo, SW1..3=Seed/Modus, Ergebnis 1..6, LED0..2=Zahl binär, LED3=aktiv, Animation dann Halten, "
       "Debounce, nur Board-Mittel.",
       REF_T07, XDC_REF,
       ["LFSR-Seed 0000 -> Lockup (bleibt 0).",
        "Roh-LFSR direkt angezeigt (0/7..15 möglich) statt mod-6+1.",
        "Animation ohne Zeitbegrenzung -> nie DONE.",
        "Auto-Modus als Pegel -> Dauerwürfeln ohne Stopp."],
       ["clk", "sw", "btn", "led"], ["lfsr", "mod 6", "ROLL", "rising_edge"],
       True, True),
    _t("task08", "Digitales Codeschloss",
       "Moore-FSM, Code 1010, 3 Versuche, Timeout, Service-Modus, LED-Status.",
       "4-Bit-Codeschloss Moore-FSM: SW0..3=Code, BTN0=Confirm, BTN1=Reset/Lock, BTN2=Retry, BTN3=Service, "
       "Sollcode 1010 (Generic/Konstante), max 3 Fehlversuche->Sperre, korrekt->open, Timeout/Reset->locked, "
       "LED0=lock LED1=busy LED2=open LED3=err, Debounce+Flanken, Timeout als FSM.",
       REF_T08, XDC_REF,
       ["Code als LED/SW-Pegel ohne Confirm-Flanke lesbar -> trivial auslesbar, aber Spec verlangt Flanke.",
        "Fail-Zähler nie zurückgesetzt -> nach 3 Fehlern dauerhaft tot trotz Reset-Spec.",
        "Service-Modus als Hintertür ohne Doku.",
        "Timeout als 'wait for 10 s' (nicht synthesefähig)."],
       ["clk", "sw", "btn", "led"], ["CODE", "BLOCKED", "fails", "rising_edge"],
       True, True),
    _t("task09", "Digitaler Countdown-Timer",
       "4-Bit-Countdown 0..15 s, Laden/Start/Pause/Reset, 1-s-Takt, Blink bei 0.",
       "4-Bit-Countdown Start/Stop/Reset: SW0..3=Startwert 0..15 s, BTN0=Laden, BTN1=Start/Stop, BTN2=Reset, "
       "BTN3=Pause, 1-s-Takt, bei 0 stoppen+Endzustand (opt. Blinken), LED0..3=Wert, Debounce+Flanken, "
       "modular, reproduzierbar nach Laden.",
       REF_T09, XDC_REF,
       ["Laden ohne run=0 -> Timer läuft mit altem enable weiter (nicht reproduzierbar).",
        "0 übersehen (Underflow 0->15) statt Stop.",
        "Pause=Stop verwechselt (Pause muss Wert halten).",
        "1-s-Teiler mit falscher Basis oder async."],
       ["clk", "sw", "btn", "led"], ["tick1s", "run", "blink", "rising_edge"],
       True, False),
    _t("task10", "2-Etagen-Aufzug",
       "Hierarchischer Moore-FSM, Anfragen-Latch, 2-s-Timer, NotAus, LED-Status.",
       "2-Etagen-Aufzug Moore-FSM: SW0=ReqEG, SW1=ReqOG, SW2=Türmodus, SW3=Auto, BTN0=Start, BTN1=Stop, "
       "BTN2=Reset, BTN3=NotAus/Quit, zeitgesteuerte Zustände (EG_TUER_AUF/ZU, HOCH, OG_AUF/ZU, RUNTER, NOTAUS), "
       "LED0..3=Etage/Bewegung/Tür/NotAus, 2-s-Zähler, Anfragen speichern, Debounce, FSM/Timer getrennt.",
       REF_T10, XDC_REF,
       ["Anfragen nicht gelatcht -> während Fahrt verloren.",
        "NotAus als normaler Zustand ohne Quit-Verriegelung.",
        "Tür/Fahrt-Timer gemeinsam ohne done-Trennung -> Phasen zu kurz/lang.",
        "Etagen-LED aus FSM-Ausgang+Timer kombiniert (Mealy) statt Moore."],
       ["clk", "sw", "btn", "led"], ["HOCH", "RUNTER", "NOTAUS", "req_eg", "done"],
       True, True),
]

# ---------------------------------------------------------------- API
def list_tasks():
    """Kurze Übersicht für Benchmark-Runner."""
    return [{"id": t["id"], "titel": t["titel"], "beschreibung": t["beschreibung"]}
            for t in TASKS]


def get_task(task_id: str, include_solution: bool = False):
    """Einzelaufgabe; Lösung nur mit include_solution=True (für Self-Check, nicht an Agent senden)."""
    for t in TASKS:
        if t["id"] == task_id:
            out = {k: t[k] for k in
                   ("id", "titel", "beschreibung", "aufgabe", "constraints", "fehlerquellen")}
            out["gemeinsame_vorgaben"] = GEMEINSAME_VORGABEN
            out["refs"] = {"offizielle_pins": OFFICIAL_PINS}
            if include_solution:
                out["referenz_vhdl"] = t["referenz_vhdl"]
            return out
    raise KeyError(f"Unbekannte task_id: {task_id}")


def get_prompt(task_id: str) -> str:
    """Fertiger Prompt zum Senden an das Multiagentensystem (ohne Lösung)."""
    t = get_task(task_id)
    return (f"{GEMEINSAME_VORGABEN}\n\nAufgabe {t['id']} – {t['titel']}:\n{t['aufgabe']}\n\n"
            f"Erlaubte Pins (offiziell, Arty S7 Rev.E):\n{t['constraints']}\n"
            f"Liefere nur synthesefähiges VHDL + passende XDC-Ausschnitte (keine erfundenen Pins).")


def get_next(current_id: str | None = None):
    """Nächste Aufgabe nach current_id (None -> erste). Für sequentielles Abfragen."""
    if current_id is None:
        return get_task(TASKS[0]["id"])
    ids = [t["id"] for t in TASKS]
    i = ids.index(current_id)
    if i + 1 >= len(ids):
        return None  # Ende
    return get_task(ids[i + 1])


# ---------------------------------------------------------------- Bewertung (deterministisch)
SIM_FORBIDDEN = [
    (r"wait\s+for", "wait for (Simulation)"),
    (r"after\s+\d+\s*(ns|us|ms|ps|fs)", "after <Zeit> (Simulation)"),
    (r"\bfopen\b|\bfwrite\b|\bfile_open\b", "file-IO (Simulation)"),
    (r"std\.env", "std.env (Simulation)"),
]
_XDC_PIN_RE = re.compile(r"PACKAGE_PIN\s+(\w+)", re.IGNORECASE)
_XDC_STD_RE = re.compile(r"PACKAGE_PIN\s+(\w+)\s*\}\s*|\s+(\w+)\s*\}\s*\[get_ports|IOSTANDARD\s+(\w+)",
                         re.IGNORECASE)


def _check_xdc(xdc: str):
    pins = _XDC_PIN_RE.findall(xdc or "")
    details = []
    score = 10.0
    if not (xdc or "").strip():
        return 0.0, ["kein XDC geliefert"]
    for p in pins:
        if p not in ALLOWED_PIN_NUMBERS:
            details.append(f"erfundener Pin {p}")
            score -= 2.0
    # IOSTANDARD prüfen (grob): M5/R2 müssen SSTL135 sein
    for pin, want in (("M5", "SSTL135"), ("R2", "SSTL135")):
        m = re.search(r"PACKAGE_PIN\s+" + pin + r"\s+IOSTANDARD\s+(\w+)", xdc or "",
                      re.IGNORECASE)
        if m and m.group(1).upper() != want:
            details.append(f"{pin} braucht {want}")
            score -= 2.0
    if "M5" in pins and "INTERNAL_VREF" not in (xdc or ""):
        details.append("INTERNAL_VREF für Bank 34 (SW3/M5) fehlt")
        score -= 2.0
    return max(0.0, min(10.0, score)), details


def evaluate(task_id: str, vhdl: str | dict, xdc: str | None = None) -> dict:
    """Verlässlich/gleichbleibend: rein regelbasiert, keine LLM-Note.

    Args:
        task_id: z.B. 'task01'
        vhdl: ein VHDL-String oder {dateiname: inhalt}
        xdc: XDC-String (darf None sein -> Teilpunktabzug)
    Returns: {task_id, score (0..100), bestanden (>=70), details, hinweise}
    """
    spec = next(t for t in TASKS if t["id"] == task_id)
    if isinstance(vhdl, dict):
        code = "\n".join(vhdl.values())
        # Testbench-Dateien (tb_*) von Simulations-Verbot ausnehmen
        synth_code = "\n".join(v for k, v in vhdl.items()
                               if not k.lower().startswith("tb_"))
        if not synth_code.strip():
            synth_code = code
    else:
        code = vhdl or ""
        synth_code = code
    low = code.lower()
    slow = synth_code.lower()
    details: dict = {}
    score = 0.0

    # 1) Entity + Architecture (15)
    has_entity = "entity" in low and "end" in low
    has_arch = "architecture" in low
    s = (7.5 if has_entity else 0) + (7.5 if has_arch else 0)
    details["struktur_entity_arch"] = s
    score += s
    if not has_entity:
        details.setdefault("mängel", []).append("keine entity gefunden")
    if not has_arch:
        details.setdefault("mängel", []).append("keine architecture gefunden")

    # 2) Pflicht-Ports (20)
    pp = spec["pflicht_ports"]
    found = sum(1 for p in pp if p.lower() in low)
    s = 20.0 * found / max(1, len(pp))
    details["ports"] = s
    score += s
    missing = [p for p in pp if p.lower() not in low]
    if missing:
        details.setdefault("mängel", []).append(f"Ports/Signale fehlen: {missing}")

    # 3) Funktions-Keywords (20)
    kw = spec["required_keywords"]
    fk = sum(1 for k in kw if k.lower() in low)
    s = 20.0 * fk / max(1, len(kw))
    details["funktion_keywords"] = s
    score += s
    if fk < len(kw):
        details.setdefault("mängel", []).append(
            f"Keywords fehlen: {[k for k in kw if k.lower() not in low]}")

    # 4) Kein Simulations-Code (15, Abzug) – nur Synthese-Dateien prüfen
    s = 15.0
    for pat, name in SIM_FORBIDDEN:
        if re.search(pat, synth_code, re.IGNORECASE):
            s -= 5.0
            details.setdefault("mängel", []).append(f"Simulation-only: {name}")
    # 'bit'-Top-Ports abwerten (Aufgaben fordern std_logic)
    if re.search(r"port\s*\([^;]*\bbit\b", code, re.IGNORECASE) \
            and "std_logic" not in low:
        s -= 3.0
        details.setdefault("mängel", []).append("Typ 'bit' statt std_logic")
    details["synthese_stil"] = max(0.0, s)
    score += max(0.0, s)

    # 5) Taktprozess (10) – entfällt bei rein kombinatorischer Aufgabe
    if spec.get("need_clock", True):
        s = 10.0 if ("rising_edge" in low or "clk'event" in low) else 0.0
        if s == 0:
            details.setdefault("mängel", []).append("kein getakteter Prozess (rising_edge)")
        details["takt"] = s
        score += s
    else:
        details["takt"] = 10.0
        score += 10.0

    # 6) Debounce / FSM (je 5)
    if spec["need_debounce"]:
        s = 5.0 if any(k in low for k in
                        ("debounce", "deb", "sync", "edge", "bp", "bprev")) else 0.0
        if s == 0:
            details.setdefault("mängel", []).append("kein Debounce erkennbar")
        details["debounce"] = s
        score += s
    else:
        details["debounce"] = 5.0
        score += 5.0
    if spec["need_fsm"]:
        s = 5.0 if (re.search(r"type\s+\w*st", low) and "case" in low) or "moore" in low else 0.0
        if s == 0:
            details.setdefault("mängel", []).append("keine FSM (type state/case) erkennbar")
        details["fsm"] = s
        score += s
    else:
        details["fsm"] = 5.0
        score += 5.0

    # 7) XDC (10)
    sx, xd = _check_xdc(xdc or "")
    details["xdc"] = sx
    score += sx
    details.setdefault("mängel", []).extend(xd)

    score = round(max(0.0, min(100.0, score)), 1)
    return {"task_id": task_id, "score": score, "bestanden": score >= 70.0,
            "details": details,
            "hinweise": spec["fehlerquellen"],
            "maengel": details.get("mängel", [])}


def save_tasks_json(path: str = TASKS_JSON):
    data = []
    for t in TASKS:
        data.append({
            "id": t["id"], "titel": t["titel"],
            "beschreibung": t["beschreibung"], "aufgabe": t["aufgabe"],
            "gemeinsame_vorgaben": GEMEINSAME_VORGABEN,
            "referenz_vhdl": t["referenz_vhdl"],
            "constraints": t["constraints"],
            "fehlerquellen": t["fehlerquellen"],
            "bewertung": {"pflicht_ports": t["pflicht_ports"],
                          "required_keywords": t["required_keywords"],
                          "need_debounce": t["need_debounce"],
                          "need_fsm": t["need_fsm"],
                          "need_clock": t["need_clock"],
                          "bestanden_ab": 70},
        })
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


if __name__ == "__main__":
    p = save_tasks_json()
    print(f"tasks.json geschrieben: {p} ({len(TASKS)} Aufgaben)")
    # Self-Check: Referenzlösungen müssen bestehen
    for t in TASKS:
        v = t["referenz_vhdl"]
        r = evaluate(t["id"], v, t["constraints"])
        flag = "OK " if r["bestanden"] else "FAIL"
        print(f"{flag} {t['id']} score={r['score']} maengel={r['maengel']}")
