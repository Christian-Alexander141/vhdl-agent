"""Python-Referenzmodell des Top-Levels ben_eater_cpu, ausschliesslich aus PROMPT.md.

Nur Python-Standardbibliothek. Schnittstelle gemaess Task-Datei.
Simuliert mit GENERICS (kleine Werte); ReferenceModel() ohne Argumente.
"""

# Auslegungsentscheidungen zu offenen Punkten aus PROMPT.md
# ("Die genaue Taktzahl von Empfang, Laden und Senden ist nicht vorgegeben"):
# - Tick = 1 genau dann, wenn der Tick-Zaehler auf TICK_CYCLES-1 steht
#   (kombinatorisch aus dem Register vor der Flanke; danach Wrap auf 0).
# - Alle Register (auch LED, Sync, Debounce, Tick, UART, Lader) werden
#   gleichzeitig mit der Flanke aus Vor-Flanken-Werten berechnet.
#   Regeln nutzen die synchronisierten Werte VOR der Flanke (Stufe 2 alt).
# - Synchronisierer laufen immer (auch bei rst=1), Start 0 bzw. 1 bei uart_rx.
# - RAM-Programmauswahl bei Reset nutzt sw(3:2) synchronisiert vor der Flanke.
# - LED uebernimmt pro Flanke das gewaehlte Halbbyte von OUT vor der Flanke
#   (ein Takt Verzoegerung nach OUT-Aenderung); bei rst=1 wird LED 0.
# - UART-RX tastet Startmitte bei CLKS_PER_BIT//2 und Daten/Stopp jeweils nach
#   vollen CLKS_PER_BIT Takten ab (Mitte grob). Nur Reihenfolge/Inhalt zaehlt.
# - UART-TX sendet Start(0)+8 Daten LSB-first+Stopp(1) zu je CLKS_PER_BIT Takten.
# - Lader-busy = Rahmen in Arbeit (>=1 Byte des aktuellen Rahmens gepuffert,
#   noch nicht komplett/verworfen). Blockiert die CPU nur im UART-Modus.
# - OI-Trigger sendet den neuen OUT-Wert (= Bus vor der Flanke, da OI:=Bus).
# - HLT friert bei Ausfuehrung alle Register inkl. T-Zaehler ein (T bleibt
#   stehen) und setzt halted; weiter geht es nur per Reset oder UART-Laden.
# - Loader-Fertigstellung ueberschreibt im selben Takt alle CPU-Register mit 0,
#   setzt UART-Modus; gelaufen wird ab Folgetakt mit 1 Schritt/Takt.
# - Verworfen: Puffer leer, naechstes Byte ist wieder erstes Laengenbyte.


class ReferenceModel:
    SUGGESTED_CYCLES = 400
    GENERICS = {"TICK_CYCLES": 4, "DEBOUNCE_CYCLES": 2, "CLKS_PER_BIT": 4}

    # Feste Programme nach PROMPT.md, Adresse 0..15
    FIXED = {
        0: [0x51, 0x4E, 0x50, 0xE0, 0x2E, 0x4F, 0x1E, 0x4D,
            0x1F, 0x4E, 0x1D, 0x70, 0x63, 0x00, 0x00, 0x00],
        1: [0xE0, 0x2F, 0x74, 0x60, 0x3F, 0xE0, 0x80, 0x64,
            0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01],
        2: [0x1E, 0x3C, 0x76, 0x1D, 0xE0, 0xF0, 0x4E, 0x1D,
            0x2F, 0x4D, 0x60, 0x00, 0x01, 0x00, 0x03, 0x05],
        3: [0x5A, 0xE0, 0x00, 0x3F, 0x86, 0x61, 0xE0, 0xF0,
            0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01],
    }
    START_MAGIC = [0x53, 0x54, 0x41, 0x52, 0x54, 0x0A]

    def __init__(self):
        self.TICK_CYCLES = int(self.GENERICS["TICK_CYCLES"])
        self.DEBOUNCE_CYCLES = int(self.GENERICS["DEBOUNCE_CYCLES"])
        self.CLKS_PER_BIT = int(self.GENERICS["CLKS_PER_BIT"])
        self.reset()

    # -- Anfangszustand: entspricht Reset mit Programm 0 (PROMPT.md) --
    def reset(self) -> None:
        self._sw1 = 0
        self._sw2 = 0
        self._btn1 = 0
        self._btn2 = 0
        self._rx1 = 1
        self._rx2 = 1
        self._deb_dout = 0
        self._deb_cnt = 0
        self._rise = 0
        self._tick = 0
        self._pc = 0
        self._mar = 0
        self._ir = 0
        self._a = 0
        self._b = 0
        self._out = 0
        self._c = 0
        self._z = 0
        self._t = 0
        self._halted = False
        self._ram = list(self.FIXED[0])
        self._led = 0
        self._tx_line = 1
        self._uart_mode = False
        # UART RX
        self._rx_state = "idle"  # idle/start/data/stop
        self._rx_cnt = 0
        self._rx_bit = 0
        self._rx_shift = 0
        self._rx_data = 0
        self._rx_valid = 0
        # UART TX
        self._tx_state = "idle"
        self._tx_cnt = 0
        self._tx_bit = 0
        self._tx_shift = 0
        # Lader
        self._len_buf = []
        self._prog_n = None
        self._prog_buf = []
        self._start_idx = 0
        self._phase = "len"  # len/prog/start

    def _loader_busy(self) -> bool:
        # Rahmen in Arbeit: irgendetwas gepuffert
        if self._phase == "len":
            return len(self._len_buf) > 0
        return True

    def _control_word(self):
        op = (self._ir >> 4) & 0xF
        t = self._t
        c = self._c
        z = self._z
        cw = {"HLT": 0, "MI": 0, "RI": 0, "RO": 0, "IO": 0, "II": 0,
              "AI": 0, "AO": 0, "EO": 0, "SU": 0, "BI": 0, "OI": 0,
              "CE": 0, "CO": 0, "J": 0, "FI": 0}
        if t == 0:
            cw["MI"] = 1
            cw["CO"] = 1
        elif t == 1:
            cw["RO"] = 1
            cw["II"] = 1
            cw["CE"] = 1
        elif t == 2:
            if op == 0x1:
                cw["IO"] = 1
                cw["MI"] = 1
            elif op == 0x2:
                cw["IO"] = 1
                cw["MI"] = 1
            elif op == 0x3:
                cw["IO"] = 1
                cw["MI"] = 1
            elif op == 0x4:
                cw["IO"] = 1
                cw["MI"] = 1
            elif op == 0x5:
                cw["IO"] = 1
                cw["AI"] = 1
            elif op == 0x6:
                cw["IO"] = 1
                cw["J"] = 1
            elif op == 0x7:
                if c == 1:
                    cw["IO"] = 1
                    cw["J"] = 1
            elif op == 0x8:
                if z == 1:
                    cw["IO"] = 1
                    cw["J"] = 1
            elif op == 0xE:
                cw["AO"] = 1
                cw["OI"] = 1
            elif op == 0xF:
                cw["HLT"] = 1
            # 0x0, 0x9..0xD: nichts
        elif t == 3:
            if op == 0x1:
                cw["RO"] = 1
                cw["AI"] = 1
            elif op == 0x2:
                cw["RO"] = 1
                cw["BI"] = 1
            elif op == 0x3:
                cw["RO"] = 1
                cw["BI"] = 1
            elif op == 0x4:
                cw["AO"] = 1
                cw["RI"] = 1
        elif t == 4:
            if op == 0x2:
                cw["EO"] = 1
                cw["AI"] = 1
                cw["FI"] = 1
            elif op == 0x3:
                cw["EO"] = 1
                cw["AI"] = 1
                cw["SU"] = 1
                cw["FI"] = 1
        return cw

    def step(self, inputs: dict) -> dict:
        btn_in = int(inputs["btn_step"]) & 1
        rst_in = int(inputs["rst"]) & 1
        sw_in = int(inputs["sw"]) & 0xF
        rx_in = int(inputs["uart_rx"]) & 1

        TICK = self.TICK_CYCLES
        DEB = self.DEBOUNCE_CYCLES
        CPB = self.CLKS_PER_BIT

        # Vor-Flanken-Werte
        sw_s = self._sw2 & 0xF
        btn_s = self._btn2 & 1
        rxs = self._rx2 & 1

        tick = 1 if self._tick == TICK - 1 else 0
        rise = self._rise & 1
        cw = self._control_word()
        oi = cw["OI"]
        hlt_sig = cw["HLT"]
        halted = self._halted
        uart_mode = self._uart_mode
        loader_busy = self._loader_busy()
        tx_busy = (self._tx_state != "idle")

        if halted:
            step_en = False
        else:
            if not uart_mode:
                if ((sw_s >> 1) & 1) == 0:
                    step_en = (tick == 1)
                else:
                    step_en = (rise == 1)
            else:
                if loader_busy:
                    step_en = False
                elif oi and tx_busy:
                    step_en = False
                else:
                    step_en = True

        # ALU aus Vor-Flanken-Werten
        a = self._a
        b = self._b
        if cw["SU"]:
            total = a + ((~b) & 0xFF) + 1
        else:
            total = a + b
        alu_res = total & 0xFF
        carry = 1 if total > 0xFF else 0
        zero = 1 if alu_res == 0 else 0

        # Bus-Multiplexer
        if cw["CO"]:
            bus = self._pc & 0xF
        elif cw["RO"]:
            bus = self._ram[self._mar & 0xF] & 0xFF
        elif cw["IO"]:
            bus = self._ir & 0x0F
        elif cw["AO"]:
            bus = a & 0xFF
        elif cw["EO"]:
            bus = alu_res
        else:
            bus = 0

        # --- UART-RX naechster Zustand (Abtastung von rxs vor der Flanke) ---
        n_rx_state = self._rx_state
        n_rx_cnt = self._rx_cnt
        n_rx_bit = self._rx_bit
        n_rx_shift = self._rx_shift
        n_rx_data = self._rx_data
        n_rx_valid = 0  # Puls, nur bei gueltigem Stopp eine Flanke 1
        if self._rx_state == "idle":
            if rxs == 0:
                n_rx_state = "start"
                n_rx_cnt = 0
        elif self._rx_state == "start":
            half = CPB // 2
            if self._rx_cnt >= half:
                # Mitte des Startbits abtasten
                if rxs != 0:
                    n_rx_state = "idle"
                    n_rx_cnt = 0
                else:
                    n_rx_state = "data"
                    n_rx_cnt = 0
                    n_rx_bit = 0
                    n_rx_shift = 0
            else:
                n_rx_cnt = self._rx_cnt + 1
        elif self._rx_state == "data":
            if self._rx_cnt >= CPB - 1:
                bit = rxs & 1
                n_rx_shift = (self._rx_shift | (bit << self._rx_bit)) & 0xFF
                if self._rx_bit >= 7:
                    n_rx_state = "stop"
                    n_rx_cnt = 0
                else:
                    n_rx_bit = self._rx_bit + 1
                    n_rx_cnt = 0
            else:
                n_rx_cnt = self._rx_cnt + 1
        elif self._rx_state == "stop":
            if self._rx_cnt >= CPB - 1:
                if rxs == 1:
                    n_rx_data = self._rx_shift & 0xFF
                    n_rx_valid = 1
                n_rx_state = "idle"
                n_rx_cnt = 0
            else:
                n_rx_cnt = self._rx_cnt + 1

        cur_rx_valid = self._rx_valid
        cur_rx_data = self._rx_data & 0xFF

        # --- Lader: naechster Zustand aus cur_rx_valid (Vor-Flanke) ---
        n_phase = self._phase
        n_len = list(self._len_buf)
        n_n = self._prog_n
        n_prog = list(self._prog_buf)
        n_sidx = self._start_idx
        completion = False
        if cur_rx_valid == 1:
            if self._phase == "len":
                n_len = self._len_buf + [cur_rx_data]
                if len(n_len) == 4:
                    n = (n_len[0] | (n_len[1] << 8) | (n_len[2] << 16) | (n_len[3] << 24))
                    if n < 1 or n > 16:
                        n_len = []
                        n_phase = "len"
                        n_n = None
                        n_prog = []
                        n_sidx = 0
                    else:
                        n_phase = "prog"
                        n_n = n
                        n_prog = []
                        n_sidx = 0
                        n_len = []
                else:
                    n_phase = "len"
            elif self._phase == "prog":
                n_prog = self._prog_buf + [cur_rx_data]
                if n_n is not None and len(n_prog) >= n_n:
                    n_phase = "start"
                    n_sidx = 0
            elif self._phase == "start":
                exp = self.START_MAGIC[self._start_idx]
                if cur_rx_data != exp:
                    n_phase = "len"
                    n_len = []
                    n_n = None
                    n_prog = []
                    n_sidx = 0
                else:
                    if self._start_idx >= 5:
                        completion = True
                    else:
                        n_sidx = self._start_idx + 1

        # --- UART-TX naechster Zustand ---
        # Trigger: ausgefuehrter OI-Schritt im UART-Modus
        trigger = (step_en and oi == 1 and uart_mode
                   and not halted and hlt_sig == 0)
        n_tx_state = self._tx_state
        n_tx_cnt = self._tx_cnt
        n_tx_bit = self._tx_bit
        n_tx_shift = self._tx_shift
        n_tx_line = self._tx_line
        if self._tx_state == "idle":
            if trigger:
                n_tx_state = "start"
                n_tx_cnt = 0
                n_tx_shift = bus & 0xFF
                n_tx_line = 0
            else:
                n_tx_line = 1
        elif self._tx_state == "start":
            n_tx_line = 0
            if self._tx_cnt >= CPB - 1:
                n_tx_state = "data"
                n_tx_cnt = 0
                n_tx_bit = 0
                n_tx_line = (self._tx_shift >> 0) & 1
            else:
                n_tx_cnt = self._tx_cnt + 1
        elif self._tx_state == "data":
            n_tx_line = (self._tx_shift >> self._tx_bit) & 1
            if self._tx_cnt >= CPB - 1:
                if self._tx_bit >= 7:
                    n_tx_state = "stop"
                    n_tx_cnt = 0
                    n_tx_line = 1
                else:
                    n_tx_bit = self._tx_bit + 1
                    n_tx_cnt = 0
            else:
                n_tx_cnt = self._tx_cnt + 1
        elif self._tx_state == "stop":
            n_tx_line = 1
            if self._tx_cnt >= CPB - 1:
                n_tx_state = "idle"
                n_tx_cnt = 0
                n_tx_line = 1
            else:
                n_tx_cnt = self._tx_cnt + 1
        # Board-Modus: Sender bleibt idle/1 (kein Trigger moeglich, da
        # trigger uart_mode verlangt; falls dennoch busy, laeuft er zu Ende,
        # nach Reset wird er in idle gezwungen).

        # --- CPU / Speicher naechste Werte ---
        if rst_in == 1:
            sel = (sw_s >> 2) & 0x3
            n_ram = list(self.FIXED[sel])
            n_pc, n_mar, n_ir = 0, 0, 0
            n_a, n_b, n_out = 0, 0, 0
            n_c, n_z = 0, 0
            n_t = 0
            n_halted = False
            n_mode = False
            n_tick = 0
            n_dout, n_dcnt, n_rise = 0, 0, 0
            n_led = 0
            # RX/TX/Lader in Ruhe
            n_rx_state, n_rx_cnt, n_rx_bit = "idle", 0, 0
            n_rx_shift, n_rx_data, n_rx_valid = 0, 0, 0
            n_tx_state, n_tx_cnt, n_tx_bit = "idle", 0, 0
            n_tx_shift, n_tx_line = 0, 1
            n_phase, n_len, n_n, n_prog, n_sidx = "len", [], None, [], 0
        elif completion:
            prog = list(n_prog)
            nn = int(n_n)
            n_ram = prog + [0] * (16 - nn)
            n_pc, n_mar, n_ir = 0, 0, 0
            n_a, n_b, n_out = 0, 0, 0
            n_c, n_z = 0, 0
            n_t = 0
            n_halted = False
            n_mode = True
            # Lader zurueck in Ruhe (naechstes Byte = neuer Rahmen)
            n_phase, n_len, n_n, n_prog, n_sidx = "len", [], None, [], 0
            # Tick/Deb/LED/RX/TX laufen normal weiter (unten berechnet)
            if tick:
                n_tick = 0
            else:
                n_tick = self._tick + 1
            # Debounce mit btn_s
            if btn_s == self._deb_dout:
                n_dout = self._deb_dout
                n_dcnt = 0
            else:
                if self._deb_cnt >= DEB - 1:
                    n_dout = btn_s
                    n_dcnt = 0
                else:
                    n_dout = self._deb_dout
                    n_dcnt = self._deb_cnt + 1
            n_rise = 1 if (self._deb_dout == 0 and n_dout == 1) else 0
            # LED aus OUT vor der Flanke
            if (sw_s & 1) == 0:
                n_led = self._out & 0xF
            else:
                n_led = (self._out >> 4) & 0xF
        else:
            n_mode = uart_mode
            # RAM-Schreiben
            n_ram = list(self._ram)
            # Default: CPU-Register halten
            n_pc, n_mar, n_ir = self._pc, self._mar, self._ir
            n_a, n_b, n_out = self._a, self._b, self._out
            n_c, n_z = self._c, self._z
            n_t = self._t
            n_halted = halted
            if step_en and hlt_sig == 1:
                n_halted = True
                # T und Register frieren ein
            elif step_en:
                if cw["MI"]:
                    n_mar = bus & 0xF
                if cw["II"]:
                    n_ir = bus & 0xFF
                if cw["AI"]:
                    n_a = bus & 0xFF
                if cw["BI"]:
                    n_b = bus & 0xFF
                if cw["OI"]:
                    n_out = bus & 0xFF
                if cw["CE"] and cw["J"]:
                    n_pc = bus & 0xF  # kommt nicht vor; J gewinnt
                elif cw["CE"]:
                    n_pc = (self._pc + 1) % 16
                elif cw["J"]:
                    n_pc = bus & 0xF
                if cw["FI"]:
                    n_c = carry
                    n_z = zero
                if cw["RI"]:
                    n_ram[self._mar & 0xF] = bus & 0xFF
                n_t = (self._t + 1) % 5
            # Tick/Debounce/LED laufen immer
            if tick:
                n_tick = 0
            else:
                n_tick = self._tick + 1
            if btn_s == self._deb_dout:
                n_dout = self._deb_dout
                n_dcnt = 0
            else:
                if self._deb_cnt >= DEB - 1:
                    n_dout = btn_s
                    n_dcnt = 0
                else:
                    n_dout = self._deb_dout
                    n_dcnt = self._deb_cnt + 1
            n_rise = 1 if (self._deb_dout == 0 and n_dout == 1) else 0
            if (sw_s & 1) == 0:
                n_led = self._out & 0xF
            else:
                n_led = (self._out >> 4) & 0xF

        # Synchronisierer laufen immer (kein Reset)
        n_sw1 = sw_in
        n_sw2 = self._sw1
        n_btn1 = btn_in
        n_btn2 = self._btn1
        n_rxs1 = rx_in
        n_rxs2 = self._rx1

        # Zustand uebernehmen
        self._sw1, self._sw2 = n_sw1, n_sw2
        self._btn1, self._btn2 = n_btn1, n_btn2
        self._rx1, self._rx2 = n_rxs1, n_rxs2
        self._deb_dout, self._deb_cnt, self._rise = n_dout, n_dcnt, n_rise
        self._tick = n_tick
        self._pc, self._mar, self._ir = n_pc, n_mar, n_ir
        self._a, self._b, self._out = n_a, n_b, n_out
        self._c, self._z = n_c, n_z
        self._t = n_t
        self._halted = bool(n_halted)
        self._ram = n_ram
        self._led = n_led & 0xF
        self._tx_line = n_tx_line & 1
        self._uart_mode = bool(n_mode)
        self._rx_state, self._rx_cnt = n_rx_state, n_rx_cnt
        self._rx_bit, self._rx_shift = n_rx_bit, n_rx_shift
        self._rx_data, self._rx_valid = n_rx_data, n_rx_valid
        self._tx_state, self._tx_cnt = n_tx_state, n_tx_cnt
        self._tx_bit, self._tx_shift = n_tx_bit, n_tx_shift
        self._len_buf, self._prog_n = n_len, n_n
        self._prog_buf, self._start_idx, self._phase = n_prog, n_sidx, n_phase

        return {"led": self._led & 0xF, "uart_tx": self._tx_line & 1}
