"""Zyklenakkurates Python-Referenzmodell des Top-Levels 'mini_cpu'.

Ausschliesslich aus PROMPT.md abgeleitet. Es werden keine Dateien
unter src/ oder tests/ gelesen.

Abbildung der Hardware (PROMPT.md, Abschnitt "Eingaenge, Takt und Anzeige"):
- sw (3 Bit) wird mit zwei Flipflops synchronisiert; alle Regeln
  verwenden die synchronisierten Werte.
- btn_step wird mit zwei Flipflops synchronisiert und dann entprellt.
- Tick-Generator, Steuerwerk (WAIT/FETCH/DECODE/EXECUTE/HALT),
  CPU-Register (PC/IR/ACC/Z/C/OUT/RAM), Anzeigemux (kombinatorisch)
  und LED-Register.
- Synchroner Reset active high setzt alle Register auf 0,
  Steuerwerk nach WAIT.

Naheliegendste Auslegungen bei offenen Punkten (begruendet):
1. Tick als kombinatorische Funktion `tick = (tick_cnt == TICK_CYCLES-1)`:
   Nur so beginnt gemaess PROMPT "mit der TICK_CYCLES-ten steigenden
   Flanke ohne Reset (WAIT -> FETCH)". Ein registrierter Tick kaeme
   eine Flanke spaeter (TICK+1-te Flanke), weil das Steuerwerk den
   Tick der Vorflanke abtasten wuerde. Der Zaeher selbst ist ein
   Register (Reset -> 0, sonst +1 mit Ueberlauf auf 0).
2. Alle Register (Sync-Stufen, Entpreller, Tick-Zaeher, FSM, PC, IR,
   ACC, Z, C, OUT, RAM, LED) werden gleichzeitig anhand der Werte VOR
   der Flanke aktualisiert (synchrones Design). Das LED-Register
   uebernimmt daher den Mux-Wert der Vorflanke (alte CPU-/Sync-Werte).
   Dadurch ist eine Schalterumschaltung nach genau 3 Flanken sichtbar
   (2x Sync + 1x LED) und eine CPU-Registeraenderung eine Flanke
   spaeter (Mux kombinatorisch + 1x LED).
3. `go` ist kombinatorisch `tick` in Automatik bzw. der registrierte
   `rise` im Einzelschritt, jeweils mit synchronisiertem sw(2) als
   Auswahl. Die FSM tastet `go` der Vorflanke ab; in FETCH/DECODE/
   EXECUTE/HALT wird `go` ignoriert.
4. `halted` fuer die Statusanzeige ist kombinatorisch
   `(Zustand == HALT)`.
5. RAM-Lesen ist kombinatorisch aus dem alten RAM-Inhalt; ein STA in
   EXECUTE schreibt RAM[a] := altes ACC mit derselben Flanke, wird
   also erst ab der Folgeflanke lesbar.
"""

from __future__ import annotations


ROM = (
    0x11, 0x30, 0x31, 0xE0,
    0x20, 0x41, 0xDE, 0x32,
    0x21, 0x30, 0x22, 0x31,
    0xE0, 0xB4, 0xF0, 0x00,
)

_ST_WAIT = 0
_ST_FETCH = 1
_ST_DECODE = 2
_ST_EXECUTE = 3
_ST_HALT = 4


class ReferenceModel:
    """Referenzmodell von mini_cpu (siehe Modul-Docstring)."""

    SUGGESTED_CYCLES = 400
    # Kleine Zeitkonstanten, damit in SUGGESTED_CYCLES Takten jede
    # Funktion mehrfach durchlaeuft. Entspricht zugleich den Werten der
    # VHDL-Testbench (TICK_CYCLES=4, DEBOUNCE_CYCLES=2).
    GENERICS = {"TICK_CYCLES": 4, "DEBOUNCE_CYCLES": 2}

    def __init__(self, tick_cycles=None, debounce_cycles=None):
        if tick_cycles is None:
            tick_cycles = self.GENERICS["TICK_CYCLES"]
        if debounce_cycles is None:
            debounce_cycles = self.GENERICS["DEBOUNCE_CYCLES"]
        assert tick_cycles >= 1, "TICK_CYCLES muss >= 1 sein"
        assert debounce_cycles >= 1, "DEBOUNCE_CYCLES muss >= 1 sein"
        self.TICK_CYCLES = int(tick_cycles)
        self.DEBOUNCE_CYCLES = int(debounce_cycles)
        self.reset()

    def reset(self) -> None:
        """Anfangszustand (= alle Register 0, Steuerwerk WAIT)."""
        self._sw_s1 = 0
        self._sw_s2 = 0
        self._btn_s1 = 0
        self._btn_s2 = 0
        self._deb_dout = 0
        self._deb_cnt = 0
        self._deb_rise = 0
        self._tick_cnt = 0
        self._state = _ST_WAIT
        self._pc = 0
        self._ir = 0
        self._acc = 0
        self._z = 0
        self._c = 0
        self._out = 0
        self._ram = [0] * 16
        self._led = 0

    # -- interne Helfer -------------------------------------------------
    def _display(self, sel, mode, out_v, acc, pc, z, c, halted):
        if sel == 0:
            return out_v & 0xF
        if sel == 1:
            return acc & 0xF
        if sel == 2:
            return pc & 0xF
        return ((halted & 1) << 3) | ((mode & 1) << 2) | ((c & 1) << 1) | (z & 1)

    def step(self, inputs: dict) -> dict:
        """Eine steigende Taktflanke auswerten.

        inputs: Werte ALLER Eingaenge ausser clk, wie sie VOR der Flanke
        anliegen (rst wird vom Modell selbst ausgewertet).
        Rueckgabe: Werte ALLER Ausgaenge unmittelbar NACH der Flanke.
        """
        rst = int(inputs["rst"]) & 1
        btn = int(inputs["btn_step"]) & 1
        sw = int(inputs["sw"]) & 0x7

        if rst:
            # Synchroner Reset: alle Register werden 0, FSM nach WAIT.
            self._sw_s1 = 0
            self._sw_s2 = 0
            self._btn_s1 = 0
            self._btn_s2 = 0
            self._deb_dout = 0
            self._deb_cnt = 0
            self._deb_rise = 0
            self._tick_cnt = 0
            self._state = _ST_WAIT
            self._pc = 0
            self._ir = 0
            self._acc = 0
            self._z = 0
            self._c = 0
            self._out = 0
            self._ram = [0] * 16
            self._led = 0
            return {"led": 0}

        # --- alte Werte (vor der Flanke) ---
        sw_s1_old = self._sw_s1
        sw_s2_old = self._sw_s2
        btn_s1_old = self._btn_s1
        btn_s2_old = self._btn_s2
        dout_old = self._deb_dout
        cnt_old = self._deb_cnt
        tick_cnt_old = self._tick_cnt
        state_old = self._state
        pc_old = self._pc
        ir_old = self._ir
        acc_old = self._acc
        z_old = self._z
        c_old = self._c
        out_old = self._out
        ram_old = list(self._ram)
        # kombinatorische Signale der Vorflanke
        btn_sync_old = btn_s2_old
        sw_sync_old = sw_s2_old
        sel_old = sw_sync_old & 0x3
        mode_old = (sw_sync_old >> 2) & 0x1
        rise_old = self._deb_rise
        tick_old = 1 if tick_cnt_old == self.TICK_CYCLES - 1 else 0
        go_old = tick_old if mode_old == 0 else rise_old
        halted_old = 1 if state_old == _ST_HALT else 0
        disp_old = self._display(
            sel_old, mode_old, out_old, acc_old, pc_old,
            z_old, c_old, halted_old,
        )

        # --- neue Werte berechnen (gleichzeitige Uebernahme) ---
        # Synchronisierer (je zwei Flipflops)
        sw_s1_new = sw
        sw_s2_new = sw_s1_old
        btn_s1_new = btn
        btn_s2_new = btn_s1_old

        # Entpreller: din ist der synchronisierte Taster der Vorflanke
        din = btn_sync_old
        if din == dout_old:
            deb_cnt_new = 0
            deb_dout_new = dout_old
            deb_rise_new = 0
        else:
            if cnt_old == self.DEBOUNCE_CYCLES - 1:
                deb_dout_new = din
                deb_cnt_new = 0
                # rise genau einen Takt bei 0->1-Wechsel von dout
                deb_rise_new = 1 if (dout_old == 0 and din == 1) else 0
            else:
                deb_dout_new = dout_old
                deb_cnt_new = cnt_old + 1
                deb_rise_new = 0

        # Tick-Zaehler (Tick selbst kombinatorisch, siehe Docstring)
        if tick_cnt_old == self.TICK_CYCLES - 1:
            tick_cnt_new = 0
        else:
            tick_cnt_new = tick_cnt_old + 1

        # Steuerwerk + Datenpfad
        state_new = state_old
        pc_new = pc_old
        ir_new = ir_old
        acc_new = acc_old
        z_new = z_old
        c_new = c_old
        out_new = out_old
        ram_new = list(ram_old)

        if state_old == _ST_WAIT:
            state_new = _ST_FETCH if go_old == 1 else _ST_WAIT
        elif state_old == _ST_FETCH:
            ir_new = ROM[pc_old & 0xF]
            pc_new = (pc_old + 1) & 0xF
            state_new = _ST_DECODE
        elif state_old == _ST_DECODE:
            state_new = _ST_EXECUTE
        elif state_old == _ST_EXECUTE:
            opcode = (ir_old >> 4) & 0xF
            operand = ir_old & 0xF
            if opcode == 0x0:  # NOP
                pass
            elif opcode == 0x1:  # LDI n
                acc_new = operand & 0xF
                z_new = 1 if acc_new == 0 else 0
            elif opcode == 0x2:  # LDA a
                acc_new = ram_old[operand] & 0xF
                z_new = 1 if acc_new == 0 else 0
            elif opcode == 0x3:  # STA a
                ram_new[operand] = acc_old & 0xF
            elif opcode == 0x4:  # ADD a
                s = acc_old + ram_old[operand]
                acc_new = s & 0xF
                c_new = 1 if s >= 16 else 0
                z_new = 1 if acc_new == 0 else 0
            elif opcode == 0x5:  # SUB a
                c_new = 1 if acc_old < ram_old[operand] else 0
                acc_new = (acc_old - ram_old[operand]) & 0xF
                z_new = 1 if acc_new == 0 else 0
            elif opcode == 0x6:  # AND a
                acc_new = (acc_old & ram_old[operand]) & 0xF
                c_new = 0
                z_new = 1 if acc_new == 0 else 0
            elif opcode == 0x7:  # OR a
                acc_new = (acc_old | ram_old[operand]) & 0xF
                c_new = 0
                z_new = 1 if acc_new == 0 else 0
            elif opcode == 0x8:  # XOR a
                acc_new = (acc_old ^ ram_old[operand]) & 0xF
                c_new = 0
                z_new = 1 if acc_new == 0 else 0
            elif opcode == 0x9:  # SHL
                c_new = (acc_old >> 3) & 0x1
                acc_new = (acc_old << 1) & 0xF
                z_new = 1 if acc_new == 0 else 0
            elif opcode == 0xA:  # SHR
                c_new = acc_old & 0x1
                acc_new = (acc_old >> 1) & 0xF
                z_new = 1 if acc_new == 0 else 0
            elif opcode == 0xB:  # JMP t
                pc_new = operand & 0xF
            elif opcode == 0xC:  # JZ t
                if z_old == 1:
                    pc_new = operand & 0xF
            elif opcode == 0xD:  # JC t
                if c_old == 1:
                    pc_new = operand & 0xF
            elif opcode == 0xE:  # OUT
                out_new = acc_old & 0xF
            elif opcode == 0xF:  # HLT
                pass
            state_new = _ST_HALT if opcode == 0xF else _ST_WAIT
        elif state_old == _ST_HALT:
            state_new = _ST_HALT

        # LED-Register uebernimmt den Mux-Wert der Vorflanke
        led_new = disp_old & 0xF

        # --- Uebernahme ---
        self._sw_s1 = sw_s1_new
        self._sw_s2 = sw_s2_new
        self._btn_s1 = btn_s1_new
        self._btn_s2 = btn_s2_new
        self._deb_dout = deb_dout_new
        self._deb_cnt = deb_cnt_new
        self._deb_rise = deb_rise_new
        self._tick_cnt = tick_cnt_new
        self._state = state_new
        self._pc = pc_new
        self._ir = ir_new
        self._acc = acc_new
        self._z = z_new
        self._c = c_new
        self._out = out_new
        self._ram = ram_new
        self._led = led_new

        return {"led": self._led}
