"""Mikroschritt-Modell des Ben-Eater-8-Bit-Rechners (Endversion mit Flags).

Steuerwort-Tabelle nach Ben Eater, microcode-eeprom-with-flags (GitHub beneater/eeprom-programmer).
Ein Aufruf von step() entspricht einer Taktflanke des Originals bzw. einem freigegebenen Mikroschritt.
"""
HLT, MI, RI, RO, IO, II, AI, AO, EO, SU, BI, OI, CE, CO, J, FI = (1 << i for i in range(15, -1, -1))
NAMES = ["HLT", "MI", "RI", "RO", "IO", "II", "AI", "AO", "EO", "SU", "BI", "OI", "CE", "CO", "J", "FI"]

FETCH = [MI | CO, RO | II | CE]
EXEC = {
    0x0: [],                                   # NOP
    0x1: [IO | MI, RO | AI],                   # LDA a
    0x2: [IO | MI, RO | BI, EO | AI | FI],     # ADD a
    0x3: [IO | MI, RO | BI, EO | AI | SU | FI],  # SUB a
    0x4: [IO | MI, AO | RI],                   # STA a
    0x5: [IO | AI],                            # LDI n
    0x6: [IO | J],                             # JMP t
    0x7: [],                                   # JC t (IO|J, wenn C = 1)
    0x8: [],                                   # JZ t (IO|J, wenn Z = 1)
    0xE: [AO | OI],                            # OUT
    0xF: [HLT],                                # HLT
}
MNEMONIC = {0x0: "NOP", 0x1: "LDA", 0x2: "ADD", 0x3: "SUB", 0x4: "STA", 0x5: "LDI", 0x6: "JMP",
            0x7: "JC", 0x8: "JZ", 0xE: "OUT", 0xF: "HLT"}


def control_word(opcode: int, step: int, c: int, z: int) -> int:
    if step < 2:
        return FETCH[step]
    words = list(EXEC.get(opcode, []))
    if (opcode == 0x7 and c) or (opcode == 0x8 and z):
        words = [IO | J]
    index = step - 2
    return words[index] if index < len(words) else 0


def alu(a: int, b: int, subtract: bool) -> tuple[int, int, int]:
    total = a + ((~b) & 0xFF) + 1 if subtract else a + b
    result = total & 0xFF
    return result, (total >> 8) & 1, int(result == 0)


class Computer:
    STEPS = 5  # T0..T4, danach wieder T0 (Original: Schrittzähler wird bei T5 zurückgesetzt)

    def __init__(self, program: list[int]):
        self.ram = (list(program) + [0] * 16)[:16]
        self.pc = self.mar = self.ir = self.a = self.b = self.out = 0
        self.c = self.z = 0
        self.step_no = 0
        self.halted = False
        self.outputs: list[int] = []
        self.microsteps = 0

    def cw(self) -> int:
        return control_word(self.ir >> 4, self.step_no, self.c, self.z)

    def step(self) -> None:
        if self.halted:
            return
        cw = self.cw()
        if cw & HLT:
            self.halted = True  # Takt steht; kein Register ändert sich
            return
        result, carry, zero = alu(self.a, self.b, bool(cw & SU))
        sources = [(CO, self.pc), (RO, self.ram[self.mar]), (IO, self.ir & 0x0F), (AO, self.a), (EO, result)]
        active = [v for flag, v in sources if cw & flag]
        assert len(active) <= 1, f"Buskonflikt bei Steuerwort {cw:016b}"
        bus = active[0] if active else 0
        mar, pc = self.mar, self.pc
        if cw & RI:
            self.ram[mar] = bus
        if cw & MI:
            self.mar = bus & 0x0F
        if cw & II:
            self.ir = bus
        if cw & AI:
            self.a = bus
        if cw & BI:
            self.b = bus
        if cw & OI:
            self.out = bus
            self.outputs.append(bus)
        if cw & J:
            self.pc = bus & 0x0F
        if cw & CE:
            self.pc = (pc + 1) & 0x0F
        if cw & FI:
            self.c, self.z = carry, zero
        self.step_no = (self.step_no + 1) % self.STEPS
        self.microsteps += 1

    def run(self, max_microsteps: int = 200_000, max_outputs: int | None = None) -> "Computer":
        while not self.halted and self.microsteps < max_microsteps:
            if max_outputs is not None and len(self.outputs) >= max_outputs:
                break
            self.step()
        return self


def assemble(lines: dict[int, tuple]) -> list[int]:
    """{Adresse: ("LDA", 14) | ("DATA", 7)} -> 16 Bytes."""
    codes = {v: k for k, v in MNEMONIC.items()}
    ram = [0] * 16
    for address, (op, *arg) in lines.items():
        value = arg[0] if arg else 0
        ram[address] = value & 0xFF if op == "DATA" else (codes[op] << 4) | (value & 0x0F)
    return ram


# --- Programme -------------------------------------------------------------------
PRESETS = {
    0: ("Fibonacci (Ben Eater, Neustart beim Überlauf)", assemble({
        0: ("LDI", 1), 1: ("STA", 14), 2: ("LDI", 0), 3: ("OUT",), 4: ("ADD", 14), 5: ("STA", 15),
        6: ("LDA", 14), 7: ("STA", 13), 8: ("LDA", 15), 9: ("STA", 14), 10: ("LDA", 13),
        11: ("JC", 0), 12: ("JMP", 3)})),
    1: ("Zählen 0..255 und zurück", assemble({
        0: ("OUT",), 1: ("ADD", 15), 2: ("JC", 4), 3: ("JMP", 0),
        4: ("SUB", 15), 5: ("OUT",), 6: ("JZ", 0), 7: ("JMP", 4), 15: ("DATA", 1)})),
    2: ("Multiplikation 3 × 5", assemble({
        0: ("LDA", 14), 1: ("SUB", 12), 2: ("JC", 6), 3: ("LDA", 13), 4: ("OUT",), 5: ("HLT",),
        6: ("STA", 14), 7: ("LDA", 13), 8: ("ADD", 15), 9: ("STA", 13), 10: ("JMP", 0),
        12: ("DATA", 1), 13: ("DATA", 0), 14: ("DATA", 3), 15: ("DATA", 5)})),
    3: ("Countdown 10..0 mit NOP", assemble({
        0: ("LDI", 10), 1: ("OUT",), 2: ("NOP",), 3: ("SUB", 15), 4: ("JZ", 6), 5: ("JMP", 1),
        6: ("OUT",), 7: ("HLT",), 15: ("DATA", 1)})),
}

UART_TESTS = {
    "fibonacci_halt": assemble({
        0: ("OUT",), 1: ("ADD", 14), 2: ("JC", 11), 3: ("STA", 15), 4: ("LDA", 14), 5: ("STA", 13),
        6: ("LDA", 15), 7: ("STA", 14), 8: ("LDA", 13), 9: ("JMP", 0), 11: ("HLT",), 14: ("DATA", 1)}),
    "multiply_7x9": assemble({
        0: ("LDA", 14), 1: ("SUB", 12), 2: ("JC", 6), 3: ("LDA", 13), 4: ("OUT",), 5: ("HLT",),
        6: ("STA", 14), 7: ("LDA", 13), 8: ("ADD", 15), 9: ("STA", 13), 10: ("JMP", 0),
        12: ("DATA", 1), 13: ("DATA", 0), 14: ("DATA", 7), 15: ("DATA", 9)}),
    "countdown_5": assemble({
        0: ("LDI", 5), 1: ("OUT",), 2: ("SUB", 15), 3: ("JZ", 5), 4: ("JMP", 1), 5: ("OUT",), 6: ("HLT",),
        15: ("DATA", 1)}),
    "borrow_3_minus_5": assemble({
        0: ("LDI", 3), 1: ("SUB", 15), 2: ("JC", 5), 3: ("OUT",), 4: ("HLT",), 5: ("LDI", 1), 6: ("OUT",),
        7: ("HLT",), 15: ("DATA", 5)}),
}


if __name__ == "__main__":
    for key, (name, ram) in PRESETS.items():
        m = Computer(ram).run(max_outputs=600)
        print(f"P{key} {name}: {' '.join(f'{b:02X}' for b in ram)}")
        print(f"   Ausgaben ({len(m.outputs)}): {m.outputs[:40]}{' …' if len(m.outputs) > 40 else ''}"
              f" | angehalten={m.halted} nach {m.microsteps} Mikroschritten")
    for name, ram in UART_TESTS.items():
        m = Computer(ram).run()
        print(f"UART {name}: {''.join(f'{b:02X}' for b in ram)} -> {bytes(m.outputs).hex()} "
              f"(halted={m.halted}, {m.microsteps} Mikroschritte)")
