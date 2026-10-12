"""Befehlssatzmodell der Aufgabe 04: berechnet OUT-Folge, Befehlszahl und Endzustand des Demoprogramms."""
ROM = [0x11, 0x30, 0x31, 0xE0, 0x20, 0x41, 0xDE, 0x32, 0x21, 0x30, 0x22, 0x31, 0xE0, 0xB4, 0xF0, 0x00]


def run():
    pc = acc = z = c = out = 0
    ram, n, outs = [0] * 16, 0, []
    while True:
        ir = ROM[pc]
        pc = (pc + 1) % 16
        op, arg = ir >> 4, ir & 15
        n += 1
        if op == 0x1: acc = arg; z = int(acc == 0)
        elif op == 0x2: acc = ram[arg]; z = int(acc == 0)
        elif op == 0x3: ram[arg] = acc
        elif op == 0x4: s = acc + ram[arg]; c = int(s > 15); acc = s & 15; z = int(acc == 0)
        elif op == 0x5: c = int(acc < ram[arg]); acc = (acc - ram[arg]) & 15; z = int(acc == 0)
        elif op == 0x6: acc &= ram[arg]; c = 0; z = int(acc == 0)
        elif op == 0x7: acc |= ram[arg]; c = 0; z = int(acc == 0)
        elif op == 0x8: acc ^= ram[arg]; c = 0; z = int(acc == 0)
        elif op == 0x9: c = acc >> 3; acc = (acc << 1) & 15; z = int(acc == 0)
        elif op == 0xA: c = acc & 1; acc >>= 1; z = int(acc == 0)
        elif op == 0xB: pc = arg
        elif op == 0xC and z: pc = arg
        elif op == 0xD and c: pc = arg
        elif op == 0xE: out = acc; outs.append((n, out))
        elif op == 0xF: break
    return {"out_folge": outs, "befehle": n, "acc": acc, "pc": pc, "z": z, "c": c, "out": out}


if __name__ == "__main__":
    print(run())
