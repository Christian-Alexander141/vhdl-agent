# Skill: vhdl-fsm
# Beschreibung: Moore/Mealy FSM patterns, state encoding, output logic.
# Lade diesen Skill, wenn ein endlicher Automat (FSM) entworfen oder implementiert wird – z. B. Steuerwerke, Protokoll-Handler, Sequenzer.
# Quelle: eds_hdl_methodik.pdf, Kapitel 3.9, 4.2, 4.3 (S. 19, 26–29)

## Zustands-Typ
```vhdl
type state_t is (IDLE, INIT, RUN, WAIT_ACK, DONE, ERROR);
-- Oder für komplexere Automaten:
type state_t is (
  S_RESET, S_CONFIG, S_IDLE,
  S_TX_START, S_TX_DATA, S_TX_STOP,
  S_RX_START, S_RX_DATA, S_RX_STOP
);
```
- Enumeration Type (keine `integer`/`std_logic_vector` für States)
- Namen: sprechend, Großbuchstaben mit Unterstrich

## Moore-Automat (Ausgang nur vom State)
```vhdl
-- Next-state logic
p_next: process(all)
begin
  next_state <= state;
  case state is
    when IDLE     => if start = '1' then next_state <= INIT; end if;
    when INIT     => next_state <= RUN;
    when RUN      => if done_int = '1' then next_state <= DONE; end if;
    when WAIT_ACK => if ack = '1' then next_state <= IDLE; end if;
    when DONE     => next_state <= WAIT_ACK;
    when ERROR    => if rst = '1' then next_state <= IDLE; end if;
    when others   => next_state <= ERROR;
  end case;
end process;

-- State register
p_state: process(clk, rst)
begin
  if rst = '1' then state <= IDLE;
  elsif rising_edge(clk) then state <= next_state; end if;
end process;

-- Output logic (registered outputs → Moore)
p_out: process(clk, rst)
begin
  if rst = '1' then
    busy <= '0'; done <= '0'; error_flag <= '0';
  elsif rising_edge(clk) then
    busy     <= (state = INIT or state = RUN);
    done     <= (state = DONE);
    error_flag <= (state = ERROR);
  end if;
end process;
```
- Ausgänge **registriert** (geclockt) → glatte Signale, kein Glitch
- `when others` Pflicht für vollständige Abdeckung

## Mealy-Automat (Ausgang vom State + Inputs)
```vhdl
-- Output logic (combinational, depends on inputs)
p_out: process(all)
begin
  -- Defaults
  tx_valid <= '0'; tx_data <= (others => '0');
  case state is
    when S_TX_DATA =>
      tx_valid <= '1';
      tx_data  <= shifter(7 downto 0);
    when others => null;
  end case;
end process;
```
- Nur für **kombinatorische** Ausgänge, die sofort auf Inputs reagieren müssen
- Vorsicht: Mealy-Ausgänge können Glitches haben → für externe Interfaces oft Moore bevorzugen

## State-Encoding
- Standard: `type state_t is (...);` → Tool wählt Encoding (one-hot, binary, gray)
- Explizit (falls Timing kritisch):
```vhdl
attribute enum_encoding : string;
attribute enum_encoding of state_t : type is "one_hot";  -- oder "gray"
```

## Reset & Initialisierung
```vhdl
p_state: process(clk, rst)
begin
  if rst = '1' then
    state <= S_RESET;  -- definierter Startzustand
  elsif rising_edge(clk) then
    state <= next_state;
  end if;
end process;
```
- Asynchroner Reset auf definierten Start-State (`IDLE`, `S_RESET`, `RESET`)
- Alle Output-Register im selben Prozess zurücksetzen

## Timer / Counter im FSM
```vhdl
-- Im State-Register-Prozess oder separatem Prozess
p_timer: process(clk, rst)
begin
  if rst = '1' then
    timer <= (others => '0');
  elsif rising_edge(clk) then
    if state = RUN then
      timer <= timer + 1;
    else
      timer <= (others => '0');
    end if;
  end if;
end process;

-- Transition nutzt Timer
when RUN => if timer = TIMEOUT_CYCLES then next_state <= TIMEOUT; end if;
```
- Timer nur in relevanten States laufen lassen (Stromsparen, saubere Logik)

## Hierarchische FSMs
- Haupt-FSM ruft Sub-FSMs auf (z. B. UART-TX/RX als Sub-Module)
- Interface über `start`/`done`/`busy`/`error` Signale
- Sub-FSMs bekommen eigenen `clk`/`rst` vom Top-Level

## Testbench für FSM
```vhdl
-- Stimuli: State-Transitions durch Input-Sequenzen triggern
p_stim: process
begin
  rst <= '1'; start <= '0'; wait for 20 ns;
  rst <= '0'; wait for 10 ns;
  start <= '1'; wait for 10 ns;  -- IDLE -> INIT
  start <= '0'; wait for 100 ns; -- durchläuft RUN -> DONE -> WAIT_ACK
  ack <= '1'; wait for 10 ns;    -- WAIT_ACK -> IDLE
  ack <= '0'; wait;
end process;

-- Assertions auf State-Signale (wenn sichtbar) oder Outputs
assert (busy = '1') report "FSM should be busy" severity error;
```
- Teste alle Übergänge, besonders Fehlerpfade (`ERROR` State)
- `TB_COMPLETE` Marker am Ende

## Typische Fehler
| Fehler | Symptom | Fix |
|---|---|---|
| Fehlende `when others` | Latch / Simulationsmismatch | Immer `when others => next_state <= ERROR;` |
| Kombinatorische Schleife | `next_state` liest `next_state` | Nur `state` und `inputs` lesen |
| Reset vergisst Outputs | Outputs bleiben nach Reset aktiv | Alle Outputs in `p_state`/`p_out` zurücksetzen |
| Mealy-Glitch nach außen | Externes Modul sieht Flimmern | Moore-Ausgänge registrieren oder synchronisieren |