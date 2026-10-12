"""Python-Referenzmodell des Top-Levels 'mini_cpu' (PROMPT.md).

Nur anhand von PROMPT.md geschrieben; keine Kenntnis von src/ oder tests/.
Abbildung auf Taktflanken: step() wird einmal pro steigender Taktflanke
aufgerufen. inputs enthaelt die Werte ALLER Eingaenge ausser clk, wie sie
VOR der Flanke anliegen (einschliesslich rst). Rueckgabe sind ALLE Ausgaenge
unmittelbar NACH der Flanke.
"""

# Zustands-Codierung des Steuerwerks
_WAIT = 0
_FETCH = 1
_DECODE = 2
_EXECUTE = 3
_HALT = 4

_ROM = (
    0x11,  # 0: LDI 1
    0x30,  # 1: STA 0
    0x31,  # 2: STA 1
    0xE0,  # 3: OUT
    0x20,  # 4: LDA 0
    0x41,  # 5: ADD 1
    0xDE,  # 6: JC 14
    0x32,  # 7: STA 2
    0x21,  # 8: LDA 1
    0x30,  # 9: STA 0
    0x22,  # 10: LDA 2
    0x31,  # 11: STA 1
    0xE0,  # 12: OUT
    0xB4,  # 13: JMP 4
    0xF0,  # 14: HLT
    0x00,  # 15: NOP
)


class ReferenceModel:
    """Zyklengenaues Modell von mini_cpu."""

    SUGGESTED_CYCLES = 400
    GENERICS = {"TICK_CYCLES": 4, "DEBOUNCE_CYCLES": 2}

    def __init__(self, generics=None):
        # Naheliegendste Auslegung: Ohne Argumente gelten genau die kleinen
        # Werte aus GENERICS (TICK=4 minimum nach PROMPT, DEBOUNCE=2 wie in
        # der Testbench-Beschreibung), damit in SUGGESTED_CYCLES Takten das
        # komplette Fibonacci-Programm (58 Befehle * 4 Takte = 232 Takte)
        # plus Einzelschritt-/Anzeigepruefungen mehrfach durchlaufen kann.
        # Nicht aufgefuehrte Generics behalten ihren Standardwert (hier gibt
        # es keine weiteren; WIDTH/ADDR/DATA sind fest 4 bzw. 3/4 Bit).
        g = generics if generics is not None else dict(self.GENERICS)
        self.TICK_CYCLES = int(g.get("TICK_CYCLES", 50000000))
        self.DEBOUNCE_CYCLES = int(g.get("DEBOUNCE_CYCLES", 1000000))
        assert self.TICK_CYCLES >= 1
        assert self.DEBOUNCE_CYCLES >= 1
        self.reset()

    def reset(self) -> None:
        # Anfangszustand = Zustand nach synchronem Reset (PROMPT: alle
        # Register 0, Steuerwerk nach WAIT).
        self._sw_s1 = 0
        self._sw_s2 = 0
        self._b_s1 = 0
        self._b_s2 = 0
        self._deb_dout = 0
        self._deb_cnt = 0
        self._deb_rise = 0
        self._tick_cnt = 0
        self._state = _WAIT
        self._pc = 0
        self._ir = 0
        self._acc = 0
        self._z = 0
        self._c = 0
        self._out = 0
        self._ram = [0] * 16
        self._led = 0

    def _tick(self) -> int:
        # Naheliegendste Auslegung: tick ist kombinatorisch
        # (tick = (zaehler == TICK_CYCLES-1)), denn nur so beginnt in
        # Automatik der erste Befehl mit der TICK_CYCLES-ten Flanke ohne
        # Reset (PROMPT). Ein registrierter Tick kaeme eine Flanke spaeter.
        # Der Zaehler laeuft immer (auch Einzelschritt/HALT).
        return 1 if self._tick_cnt == self.TICK_CYCLES - 1 else 0

    def _display(self) -> int:
        # Kombinatorische Anzeigeauswahl aus synchronisierten Schaltern und
        # aktuellem CPU-Zustand (wird vom LED-Register eine Flanke spaeter
        # uebernommen; Schalter daher nach 3 Flanken sichtbar).
        sel = self._sw_s2 & 0x3
        mode = (self._sw_s2 >> 2) & 0x1
        halted = 1 if self._state == _HALT else 0
        if sel == 0:
            return self._out & 0xF
        if sel == 1:
            return self._acc & 0xF
        if sel == 2:
            return self._pc & 0xF
        return ((halted << 3) | (mode << 2) | ((self._c & 1) << 1) | (self._z & 1)) & 0xF

    def step(self, inputs: dict) -> dict:
        rst = int(inputs["rst"]) & 1
        btn = int(inputs["btn_step"]) & 1
        sw = int(inputs["sw"]) & 0x7

        if rst == 1:
            # Synchroner Reset active-high: mit dieser Flanke wird alles 0.
            self.reset()
            return {"led": self._led}

        # --- Alte Werte merken (alle Register wechseln gleichzeitig) ---
        sw_s1 = self._sw_s1
        sw_s2 = self._sw_s2
        b_s1 = self._b_s1
        b_s2 = self._b_s2
        deb_dout = self._deb_dout
        deb_cnt = self._deb_cnt
        tick_cnt = self._tick_cnt
        state = self._state
        pc = self._pc
        ir = self._ir
        acc = self._acc
        z = self._z
        c = self._c
        out = self._out
        ram = list(self._ram)

        tick = 1 if tick_cnt == self.TICK_CYCLES - 1 else 0
        mode = (sw_s2 >> 2) & 0x1
        rise = self._deb_rise
        go = rise if mode == 1 else tick
        disp = self._display()

        # --- Synchronisierer (zwei Flipflops) ---
        sw_s1_n = sw
        sw_s2_n = sw_s1
        b_s1_n = btn
        b_s2_n = b_s1

        # --- Entpreller: din ist synchronisiertes btn (alter Wert vor Flanke) ---
        din = b_s2
        if din == deb_dout:
            deb_dout_n = deb_dout
            deb_cnt_n = 0
        else:
            if deb_cnt == self.DEBOUNCE_CYCLES - 1:
                deb_dout_n = din
                deb_cnt_n = 0
            else:
                deb_dout_n = deb_dout
                deb_cnt_n = deb_cnt + 1
        # rise ist Register: genau einen Takt '1' bei 0->1-Wechsel von dout.
        deb_rise_n = 1 if (deb_dout_n == 1 and deb_dout == 0) else 0

        # --- Tick-Zaehler ---
        if tick_cnt == self.TICK_CYCLES - 1:
            tick_cnt_n = 0
        else:
            tick_cnt_n = tick_cnt + 1

        # --- Steuerwerk + Datenpfad ---
        state_n = state
        pc_n = pc
        ir_n = ir
        acc_n = acc
        z_n = z
        c_n = c
        out_n = out
        ram_n = ram

        if state == _WAIT:
            # go wird nur in WAIT beachtet, sonst ignoriert.
            state_n = _FETCH if go == 1 else _WAIT
        elif state == _FETCH:
            ir_n = _ROM[pc] & 0xFF
            pc_n = (pc + 1) % 16
            state_n = _DECODE
        elif state == _DECODE:
            # Nur dekodieren, kein Register aendert sich.
            state_n = _EXECUTE
        elif state == _EXECUTE:
            opcode = (ir >> 4) & 0xF
            operand = ir & 0xF
            if opcode == 0x0:  # NOP
                state_n = _WAIT
            elif opcode == 0x1:  # LDI n (C unveraendert)
                acc_n = operand & 0xF
                z_n = 1 if acc_n == 0 else 0
                state_n = _WAIT
            elif opcode == 0x2:  # LDA a (C unveraendert)
                acc_n = ram[operand] & 0xF
                z_n = 1 if acc_n == 0 else 0
                state_n = _WAIT
            elif opcode == 0x3:  # STA a
                ram_n[operand] = acc & 0xF
                state_n = _WAIT
            elif opcode == 0x4:  # ADD a
                s = acc + ram[operand]
                acc_n = s % 16
                c_n = 1 if s >= 16 else 0
                z_n = 1 if acc_n == 0 else 0
                state_n = _WAIT
            elif opcode == 0x5:  # SUB a (C=1 bei Borgen)
                c_n = 1 if acc < ram[operand] else 0
                acc_n = (acc - ram[operand]) % 16
                z_n = 1 if acc_n == 0 else 0
                state_n = _WAIT
            elif opcode == 0x6:  # AND a
                acc_n = (acc & ram[operand]) & 0xF
                c_n = 0
                z_n = 1 if acc_n == 0 else 0
                state_n = _WAIT
            elif opcode == 0x7:  # OR a
                acc_n = (acc | ram[operand]) & 0xF
                c_n = 0
                z_n = 1 if acc_n == 0 else 0
                state_n = _WAIT
            elif opcode == 0x8:  # XOR a
                acc_n = (acc ^ ram[operand]) & 0xF
                c_n = 0
                z_n = 1 if acc_n == 0 else 0
                state_n = _WAIT
            elif opcode == 0x9:  # SHL
                c_n = (acc >> 3) & 0x1
                acc_n = ((acc << 1) & 0xF)
                z_n = 1 if acc_n == 0 else 0
                state_n = _WAIT
            elif opcode == 0xA:  # SHR
                c_n = acc & 0x1
                acc_n = ((acc >> 1) & 0xF)
                z_n = 1 if acc_n == 0 else 0
                state_n = _WAIT
            elif opcode == 0xB:  # JMP t
                pc_n = operand & 0xF
                state_n = _WAIT
            elif opcode == 0xC:  # JZ t
                if z == 1:
                    pc_n = operand & 0xF
                state_n = _WAIT
            elif opcode == 0xD:  # JC t
                if c == 1:
                    pc_n = operand & 0xF
                state_n = _WAIT
            elif opcode == 0xE:  # OUT
                out_n = acc & 0xF
                state_n = _WAIT
            elif opcode == 0xF:  # HLT
                state_n = _HALT
        elif state == _HALT:
            state_n = _HALT

        # --- LED-Register: uebernimmt kombinatorischen Anzeigewert ---
        led_n = disp & 0xF

        self._sw_s1 = sw_s1_n
        self._sw_s2 = sw_s2_n
        self._b_s1 = b_s1_n
        self._b_s2 = b_s2_n
        self._deb_dout = deb_dout_n
        self._deb_cnt = deb_cnt_n
        self._deb_rise = deb_rise_n
        self._tick_cnt = tick_cnt_n
        self._state = state_n
        self._pc = pc_n & 0xF
        self._ir = ir_n & 0xFF
        self._acc = acc_n & 0xF
        self._z = z_n & 1
        self._c = c_n & 1
        self._out = out_n & 0xF
        self._ram = [v & 0xF for v in ram_n]
        self._led = led_n & 0xF

        return {"led": self._led}
