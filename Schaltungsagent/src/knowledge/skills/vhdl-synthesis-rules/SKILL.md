# Skill: vhdl-synthesis-rules
# Beschreibung: VHDL synthesis coding rules, supported vocabulary, and common pitfalls.
# Lade diesen Skill, wenn VHDL-Code für die Synthese erzeugt oder geprüft wird (Entity/Architecture, Prozesse, Signale, Generics, Reset, Arithmetik).
# Quelle: eds_hdl_methodik.pdf, Kapitel 2 (S. 8–10) und Kapitel 3 (S. 11–25)

## VHDL-2008 Baseline
```vhdl
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
-- use ieee.math_real.all;  -- nur für Konstanten-Berechnung, nicht im RTL
```

## Entity / Architecture
- Entity-Name = Dateiname (klein, underscores: `src/timer.vhd` → `entity timer is`)
- Ports: `std_logic` für Skalare, `std_logic_vector(N downto 0)` für Busse
- Generics: positive Ganzzahlen für Breiten, Frequenzen, Baudraten
- Keine `buffer`-Ports, keine `inout` außer Tri-State (selten)

## Prozesse & Sensitivity Lists
```vhdl
-- Synthesizable clocked process, reset_concept = sync_active_high
p_seq: process(clk)
begin
  if rising_edge(clk) then
    if rst = '1' then
      state <= IDLE;
    else
      state <= next_state;
    end if;
  end if;
end process;

-- dasselbe mit reset_concept = async_active_high
p_seq_async: process(clk, rst)
begin
  if rst = '1' then
    state <= IDLE;
  elsif rising_edge(clk) then
    state <= next_state;
  end if;
end process;

-- Combinational process – vollständige Sensitivity List
p_comb: process(all)  -- VHDL-2008 'all' erlaubt
begin
  next_state <= state;
  case state is
    when IDLE => if start = '1' then next_state <= RUN; end if;
    when RUN  => if done  = '1' then next_state <= IDLE; end if;
  end case;
end process;
```
- **Kein `wait` in synthetisierbarem Code** (nur in Testbenches)
- **Keine Latches**: Jeder `if` braucht `else`, jeder `case` braucht `when others`
- Sensitivity List: `process(all)` (VHDL-2008) oder alle gelesenen Signale explizit

## Reset-Konvention
- Maßgeblich ist `reset_concept` in `plan/manifest.json` (aus PROMPT.md abgeleitet):
  `sync_active_high` / `sync_active_low` → Reset innerhalb von `rising_edge(clk)`;
  `async_active_high` / `async_active_low` → `rst` in der Sensitivity List; `_low` prüft `rst_n = '0'`.
- Nur wenn PROMPT.md nichts zum Reset sagt: asynchron, active-high.
- Reset **alle** State-Signale (Register, Zähler, FSM-State, Output-Register)

## Arithmetik & Typen
```vhdl
-- Richtig
signal cnt : unsigned(7 downto 0);
cnt <= cnt + 1;

-- Falsch (kein std_logic_vector Arithmetik ohne Cast)
signal cnt : std_logic_vector(7 downto 0);
cnt <= cnt + 1;  -- Fehler: keine "+" für std_logic_vector
```
- Nutze `signed`/`unsigned` aus `numeric_std`
- Keine `integer` in Ports/Interfaces – nur in Generics/Konstanten

## Generics & Konstanten
```vhdl
generic (
  CLK_FREQ_HZ : positive := 100_000_000;
  BAUD_RATE   : positive := 115_200;
  DATA_WIDTH  : positive := 8
);
```
- Instanziierung: `generic map (CLK_FREQ_HZ => 50_000_000)`

## Typische Fehler (Vermeidung)
| Fehler | Ursache | Lösung |
|---|---|---|
| Inferred Latch | `if` ohne `else`, `case` ohne `when others` | Immer vollständige Abdeckung |
| Mehrere Treiber | Signal in mehreren Prozessen zugewiesen | Ein Prozess pro Signal |
| Metastabilität | Asynchrone Eingänge ohne Synchronisierung | 2-FF-Synchronisierer für externe Signale |
| Timing-Violation | Kombinatorischer Pfad zu lang | Pipeline-Register einfügen |
| `wait` in RTL | Testbench-Konstruktion in Modul kopiert | Entfernen, nur Clock/Reset nutzen |

## FSM-Muster (Moore/Mealy)
```vhdl
type state_t is (IDLE, LOAD, RUN, DONE);
signal state, next_state : state_t;

-- Next-state logic (combinational)
p_next: process(all)
begin
  next_state <= state;
  case state is
    when IDLE  => if start = '1' then next_state <= LOAD; end if;
    when LOAD  => next_state <= RUN;
    when RUN   => if counter = MAX then next_state <= DONE; end if;
    when DONE  => next_state <= IDLE;
  end case;
end process;

-- State register (clocked)
p_state: process(clk, rst)
begin
  if rst = '1' then state <= IDLE;
  elsif rising_edge(clk) then state <= next_state; end if;
end process;

-- Output logic (Moore: nur state, Mealy: state + inputs)
output <= '1' when state = DONE else '0';
```

## Instanziierung
```vhdl
u_timer: entity work.timer
  generic map (CLK_FREQ_HZ => 50_000_000)
  port map (
    clk   => clk,
    rst   => rst,
    start => start,
    done  => done
  );
```
- `entity work.<name>` (keine `component` Declaration nötig in VHDL-93+)
- Named association (`=>`) für alle Ports/Generics