from reference_model import ReferenceModel


def _step(m, btn=0, rst=0, sw=0, rx=1):
    return m.step({"btn_step": btn, "rst": rst, "sw": sw, "uart_rx": rx})


def _reset_with_sw(m, sw, cycles=10):
    out = None
    for _ in range(cycles):
        out = _step(m, rst=1, sw=sw)
    return out


def _run_idle(m, n, sw=0):
    out = None
    for _ in range(n):
        out = _step(m, sw=sw)
    return out


def _press_once(m, sw, hold=10, release=10):
    for _ in range(hold):
        _step(m, btn=1, sw=sw)
    for _ in range(release):
        _step(m, btn=0, sw=sw)


def _send_bytes(m, data, sw=0):
    cpb = m.CLKS_PER_BIT
    for byte in data:
        bits = [0] + [(byte >> i) & 1 for i in range(8)] + [1]
        for b in bits:
            for _ in range(cpb):
                _step(m, sw=sw, rx=b)
    # Kein Nachlauf hier: Der Empfaenger braucht noch 1-2 Takte fuer
    # Valid/Lader-Fertigstellung; diese Takte liefert _collect_tx mit
    # rx=1, waehrend es gleichzeitig uart_tx abtastet (sonst ginge das
    # erste OI-Zeichen verloren).


def _frame(n_prog_bytes):
    n = len(n_prog_bytes)
    hdr = [n & 0xFF, (n >> 8) & 0xFF, (n >> 16) & 0xFF, (n >> 24) & 0xFF]
    return hdr + list(n_prog_bytes) + [0x53, 0x54, 0x41, 0x52, 0x54, 0x0A]


def _collect_tx(m, sw, want, max_cycles=20000):
    cpb = m.CLKS_PER_BIT
    got = []
    prev = 1
    # aktuellen Leitungspegel einmal lesen
    out = _step(m, sw=sw, rx=1)
    prev = out["uart_tx"]
    cycles = 0
    while cycles < max_cycles and len(got) < want:
        out = _step(m, sw=sw, rx=1)
        cycles += 1
        tx = out["uart_tx"]
        if prev == 1 and tx == 0:
            # Startbit erkannt (erster 0-Takt bereits verbraucht)
            # zu Bit0-Mitte vorspulen
            for _ in range(cpb + cpb // 2):
                out = _step(m, sw=sw, rx=1)
                cycles += 1
            val = 0
            # Bit0 wurde in der letzten Flanke schon abgetastet? Wir lesen jetzt:
            val |= (out["uart_tx"] & 1) << 0
            for i in range(1, 8):
                for _ in range(cpb):
                    out = _step(m, sw=sw, rx=1)
                    cycles += 1
                val |= (out["uart_tx"] & 1) << i
            # Stoppbit-Mitte
            for _ in range(cpb):
                out = _step(m, sw=sw, rx=1)
                cycles += 1
            assert out["uart_tx"] == 1, "Stoppbit muss 1 sein"
            got.append(val & 0xFF)
            prev = 1
            # Kein Extra-Wait: naechster Schritt des Loop tastet Idle/Start
            # Takt fuer Takt ab (sonst wuerde ein direkt folgender Start
            # uebersprungen).
        else:
            prev = tx
    return got


def test_reset():
    m = ReferenceModel()
    m.reset()
    # Reset halten mit Programm 0: LED 0, TX idle
    for _ in range(10):
        out = _step(m, rst=1, sw=0)
        assert out["led"] == 0
        assert out["uart_tx"] == 1
    # Synchronisierer-Startwerte: nach reset() ohne Flanke keine Ausgabe noetig;
    # nach Release und Idle bleibt TX im Board-Modus auf 1
    _run_idle(m, 20, sw=0)
    out = _step(m, sw=0)
    assert out["uart_tx"] == 1


def test_board_multiply_halt():
    # Festprogramm "10" (sw3:2=10): OUT=15, danach Halt. Beide Halbbytes.
    m = ReferenceModel()
    _reset_with_sw(m, sw=0b1000)
    _run_idle(m, 600, sw=0b1000)
    out = _step(m, sw=0b1000)
    assert out["led"] == 0xF  # unteres Halbbyte von 15
    # Halt: weitere Takte aendern nichts
    for _ in range(30):
        out = _step(m, sw=0b1000)
        assert out["led"] == 0xF
    # oberes Halbbyte waehlen (sw0=1), Sync + LED-Latenz abwarten
    _run_idle(m, 10, sw=0b1001)
    out = _step(m, sw=0b1001)
    assert out["led"] == 0x0


def test_single_step_no_press_no_progress():
    # Programm "11", Einzeltakt (sw1=1): ohne Druck kein Fortschritt,
    # nach genau 8 Druecken steht 10 in OUT (unteres Halbbyte A).
    m = ReferenceModel()
    sw = 0b1110  # prog 11, single-step, low
    _reset_with_sw(m, sw=sw)
    _run_idle(m, 20, sw=sw)
    out = _step(m, sw=sw)
    assert out["led"] == 0
    for _ in range(8):
        _press_once(m, sw=sw)
    _run_idle(m, 5, sw=sw)
    out = _step(m, sw=sw)
    assert out["led"] == 0xA


def test_uart_borrow_3_minus_5():
    # Hardwaretest borrow_3_minus_5: Antwort FE (PROMPT.md)
    m = ReferenceModel()
    _reset_with_sw(m, sw=0)
    prog = bytes.fromhex("533F75E0F051E0F00000000000000005")
    _send_bytes(m, _frame(list(prog)), sw=0)
    got = _collect_tx(m, sw=0, want=1)
    assert got == [0xFE], got


def test_uart_invalid_length_then_valid():
    # Grenzfall: Rahmen mit Laenge 17 wird verworfen, danach laeuft ein
    # gueltiger Rahmen trotzdem (PROMPT.md Testbench-Forderung).
    # Nach Spec wird sofort verworfen und das naechste Byte ist wieder
    # erstes Laengenbyte; daher genuegt als Bad-Frame der ungueltige
    # Laengen-Header (volle Bad-Frames mit Prog/Magic wuerden als
    # Folge-Garbage geparst, exakte Bytezahl nicht vorgegeben).
    m = ReferenceModel()
    _reset_with_sw(m, sw=0)
    _send_bytes(m, [17, 0, 0, 0], sw=0)
    # danach gueltig: countdown_5 -> 05 04 03 02 01 00
    prog = bytes.fromhex("55E03F8561E0F0000000000000000001")
    _send_bytes(m, _frame(list(prog)), sw=0)
    got = _collect_tx(m, sw=0, want=6)
    assert got == [0x05, 0x04, 0x03, 0x02, 0x01, 0x00], got
