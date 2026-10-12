"""Python-Referenzmodell des Top-Levels 'mini_cpu' (PROMPT.md).

Abbildung der Hardware auf Takte (eine step()-Flanke = eine steigende Taktflanke):
- sync2 (2 Flipflops) je fuer sw (3 Bit) und btn_step (1 Bit), synchroner Reset -> 0.
- debouncer mit dout-Register, Zaehler und rise-Register gemaess PROMPT.md.
- tick_gen: Zaehler 0..TICK_CYCLES-1, Tick = (Zaehler == TICK_CYCLES-1) kombinatorisch.
  Begruendung: Nur so beginnt in Automatik der erste Befehl "mit der
  TICK_CYCLES-ten steigenden Flanke ohne Reset (WAIT -> FETCH)". Ein
  registrierter Tick waere eine Flanke spaeter (WAIT->FETCH erst an der
  (TICK_CYCLES+1)-ten Flanke, z. B. 5. statt 4. bei TICK=4) und widerspricht
  damit dem Wortlaut "beim Zaehlerstand TICK_CYCLES-1 einen Tick" (R67).
  Kritisch geprueft: Ein als korrekt behaupteter registrierter Tick
  (WAIT->FETCH an 5. Flanke, DUT zeigt pc=2/led=0010 wo das Modell pc=3/
  led=0011 erwartet) wurde anhand PROMPT.md verworfen – PROMPT.md hat Vorrang,
  das Modell bleibt kombinatorisch.
- Steuerwerk WAIT/FETCH/DECODE/EXECUTE/HALT, go = tick (Automatik) bzw. rise
  (Einzelschritt, einsynchronisiertes sw(2)). Alle Registeraktualisierungen
  erfolgen gleichzeitig auf Basis der Werte VOR der Flanke (non-blocking).
- display_mux kombinatorisch, led-Register uebernimmt pro Flanke den Mux-Wert.
  Daher: Schalterwechsel nach genau 3 Flanken sichtbar, CPU-Registeraenderung
  eine Flanke spaeter.
- Synchroner Reset (active high): bei rst==1 VOR der Flanke werden mit der
  Flanke ALLE Register 0 / WAIT (wie in PROMPT.md aufgezaehlt).

Nur Python-Standardbibliothek.
"""

ROM = [0x11, 0x30, 0x31, 0xE0, 0x20, 0x41, 0xDE, 0x32,
       0x21, 0x30, 0x22, 0x31, 0xE0, 0xB4, 0xF0, 0x00]


def _alu(a, b, op):
    """Rechenwerk wie in PROMPT.md (WIDTH=4). Gibt (result, carry, zero)."""
    a &= 0xF
    b &= 0xF
    if op == 0b000:  # ADD
        s = a + b
        result = s & 0xF
        carry = 1 if s > 0xF else 0
    elif op == 0b001:  # SUB
        result = (a - b) & 0xF
        carry = 1 if a < b else 0
    elif op == 0b010:  # AND
        result = a & b
        carry = 0
    elif op == 0b011:  # OR
        result = a | b
        carry = 0
    elif op == 0b100:  # XOR
        result = a ^ b
        carry = 0
    elif op == 0b101:  # SHL von a
        carry = (a >> 3) & 1
        result = (a << 1) & 0xF
    elif op == 0b110:  # SHR von a
        carry = a & 1
        result = (a >> 1) & 0xF
    else:  # 0b111 PASS b
        result = b
        carry = 0
    zero = 1 if result == 0 else 0
    return result, carry, zero


class ReferenceModel:
    GENERICS = {"TICK_CYCLES": 4, "DEBOUNCE_CYCLES": 2}
    # Mit TICK=4 braucht ein Befehl minimal 4 Takte; 58 Befehle brauchen
    # ca. 232 Takte + Synchronisierer/Anzeige-Latenz. 400 Takte lassen jeden
    # Vorgang (Automatik-Volllauf bis HALT, Einzelschritt, Reset, Mux-Latenz)
    # mehrfach durchlaufen. DEBOUNCE=2 ist der kleinste Wert, der Prellen
    # (kurzer 1-Takt-Impuls -> kein Schritt) noch von gueltigem Druck
    # unterscheidet.
    SUGGESTED_CYCLES = 400

    def __init__(self):
        self.TICK_CYCLES = self.GENERICS["TICK_CYCLES"]
        self.DEBOUNCE_CYCLES = self.GENERICS["DEBOUNCE_CYCLES"]
        self.reset()

    def reset(self) -> None:
        # Anfangszustand = alle Register 0, Steuerwerk WAIT (wie nach
        # synchronem Reset, PROMPT.md "Reset: Alle Register werden 0 ...").
        self.sw_s1 = 0
        self.sw_s2 = 0
        self.btn_s1 = 0
        self.btn_s2 = 0
        self.dout = 0
        self.db_cnt = 0
        self.rise = 0
        self.tick_cnt = 0
        self.state = "WAIT"
        self.pc = 0
        self.ir = 0
        self.acc = 0
        self.z = 0
        self.c = 0
        self.out = 0
        self.ram = [0] * 16
        self.led = 0

    def _tick(self):
        return 1 if self.tick_cnt == self.TICK_CYCLES - 1 else 0

    def _halted(self):
        return 1 if self.state == "HALT" else 0

    def _disp(self):
        mode = (self.sw_s2 >> 2) & 1
        sel = self.sw_s2 & 0x3
        if sel == 0:
            return self.out & 0xF
        elif sel == 1:
            return self.acc & 0xF
        elif sel == 2:
            return self.pc & 0xF
        else:
            return ((self._halted() << 3) | (mode << 2)
                    | ((self.c & 1) << 1) | (self.z & 1)) & 0xF

    def step(self, inputs: dict) -> dict:
        rst = int(inputs.get("rst", 0)) & 1
        btn = int(inputs.get("btn_step", 0)) & 1
        sw = int(inputs.get("sw", 0)) & 0x7

        # Kombinatorik auf Basis der Werte VOR der Flanke.
        tick = self._tick()
        mode = (self.sw_s2 >> 2) & 1
        go = tick if mode == 0 else (self.rise & 1)
        disp = self._disp()
        din = self.btn_s2 & 1

        if rst == 1:
            self.sw_s1 = 0
            self.sw_s2 = 0
            self.btn_s1 = 0
            self.btn_s2 = 0
            self.dout = 0
            self.db_cnt = 0
            self.rise = 0
            self.tick_cnt = 0
            self.state = "WAIT"
            self.pc = 0
            self.ir = 0
            self.acc = 0
            self.z = 0
            self.c = 0
            self.out = 0
            self.ram = [0] * 16
            self.led = 0
            return {"led": self.led}

        # Naechste Werte (gleichzeitig, non-blocking).
        sw_s1_n = sw
        sw_s2_n = self.sw_s1 & 0x7
        btn_s1_n = btn
        btn_s2_n = self.btn_s1 & 1
        tick_cnt_n = 0 if tick else (self.tick_cnt + 1)

        # Entpreller.
        if din == self.dout:
            db_cnt_n = 0
            dout_n = self.dout
        else:
            if self.db_cnt == self.DEBOUNCE_CYCLES - 1:
                dout_n = din
                db_cnt_n = 0
            else:
                dout_n = self.dout
                db_cnt_n = self.db_cnt + 1
        rise_n = 1 if (self.dout == 0 and dout_n == 1) else 0

        # Steuerwerk + Datenpfad.
        state_n = self.state
        pc_n = self.pc
        ir_n = self.ir
        acc_n = self.acc
        z_n = self.z
        c_n = self.c
        out_n = self.out
        ram_n = list(self.ram)

        if self.state == "WAIT":
            state_n = "FETCH" if go == 1 else "WAIT"
        elif self.state == "FETCH":
            ir_n = ROM[self.pc] & 0xFF
            pc_n = (self.pc + 1) & 0xF
            state_n = "DECODE"
        elif self.state == "DECODE":
            state_n = "EXECUTE"
        elif self.state == "EXECUTE":
            opcode = (self.ir >> 4) & 0xF
            operand = self.ir & 0xF
            if opcode == 0x0:  # NOP
                pass
            elif opcode == 0x1:  # LDI n
                acc_n = operand
                z_n = 1 if operand == 0 else 0
            elif opcode == 0x2:  # LDA a
                acc_n = ram_n[operand] & 0xF
                z_n = 1 if acc_n == 0 else 0
            elif opcode == 0x3:  # STA a
                ram_n[operand] = self.acc & 0xF
            elif opcode == 0x4:  # ADD a
                res, car, _ = _alu(self.acc, ram_n[operand], 0b000)
                acc_n = res
                c_n = car
                z_n = 1 if res == 0 else 0
            elif opcode == 0x5:  # SUB a
                res, car, _ = _alu(self.acc, ram_n[operand], 0b001)
                acc_n = res
                c_n = car
                z_n = 1 if res == 0 else 0
            elif opcode == 0x6:  # AND a
                res, car, _ = _alu(self.acc, ram_n[operand], 0b010)
                acc_n = res
                c_n = car
                z_n = 1 if res == 0 else 0
            elif opcode == 0x7:  # OR a
                res, car, _ = _alu(self.acc, ram_n[operand], 0b011)
                acc_n = res
                c_n = car
                z_n = 1 if res == 0 else 0
            elif opcode == 0x8:  # XOR a
                res, car, _ = _alu(self.acc, ram_n[operand], 0b100)
                acc_n = res
                c_n = car
                z_n = 1 if res == 0 else 0
            elif opcode == 0x9:  # SHL
                res, car, _ = _alu(self.acc, 0, 0b101)
                acc_n = res
                c_n = car
                z_n = 1 if res == 0 else 0
            elif opcode == 0xA:  # SHR
                res, car, _ = _alu(self.acc, 0, 0b110)
                acc_n = res
                c_n = car
                z_n = 1 if res == 0 else 0
            elif opcode == 0xB:  # JMP t
                pc_n = operand
            elif opcode == 0xC:  # JZ t
                if self.z == 1:
                    pc_n = operand
            elif opcode == 0xD:  # JC t
                if self.c == 1:
                    pc_n = operand
            elif opcode == 0xE:  # OUT
                out_n = self.acc & 0xF
            elif opcode == 0xF:  # HLT
                state_n = "HALT"
                # Register unveraendert.
                self.sw_s1, self.sw_s2 = sw_s1_n, sw_s2_n
                self.btn_s1, self.btn_s2 = btn_s1_n, btn_s2_n
                self.dout, self.db_cnt, self.rise = dout_n, db_cnt_n, rise_n
                self.tick_cnt = tick_cnt_n
                self.state = state_n
                self.pc, self.ir = pc_n, ir_n
                self.acc, self.z, self.c, self.out = acc_n, z_n, c_n, out_n
                self.ram = ram_n
                self.led = disp & 0xF
                return {"led": self.led}
            state_n = "WAIT"
        elif self.state == "HALT":
            state_n = "HALT"

        led_n = disp & 0xF

        self.sw_s1, self.sw_s2 = sw_s1_n, sw_s2_n
        self.btn_s1, self.btn_s2 = btn_s1_n, btn_s2_n
        self.dout, self.db_cnt, self.rise = dout_n, db_cnt_n, rise_n
        self.tick_cnt = tick_cnt_n
        self.state = state_n
        self.pc, self.ir = pc_n, ir_n
        self.acc, self.z, self.c, self.out = acc_n, z_n, c_n, out_n
        self.ram = ram_n
        self.led = led_n
        return {"led": self.led}
