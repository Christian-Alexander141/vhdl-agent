from reference_model import ReferenceModel


def _run(model, n, rst=0, btn_step=0, sw=0):
    out = None
    for _ in range(n):
        out = model.step({"rst": rst, "btn_step": btn_step, "sw": sw})
    return out


def _run_to_halt(sw=0, limit=400):
    m = ReferenceModel()
    m.reset()
    m.step({"rst": 1, "btn_step": 0, "sw": sw})
    for _ in range(limit):
        m.step({"rst": 0, "btn_step": 0, "sw": sw})
        if m.state == "HALT":
            break
    return m


def _press_once(m, sw=4, high=8, low=8):
    for _ in range(high):
        m.step({"rst": 0, "btn_step": 1, "sw": sw})
    for _ in range(low):
        m.step({"rst": 0, "btn_step": 0, "sw": sw})


def test_reset():
    m = ReferenceModel()
    m.reset()
    assert m.led == 0
    assert (m.pc, m.ir, m.acc, m.z, m.c, m.out) == (0, 0, 0, 0, 0, 0)
    assert m.ram == [0] * 16 and m.state == "WAIT"
    # Synchroner Reset ueber step(): erst mit der Flanke wird alles 0.
    _run(m, 50, sw=0)
    assert m.pc != 0 or m.acc != 0 or m.out != 0
    o = m.step({"rst": 1, "btn_step": 0, "sw": 0})
    assert o["led"] == 0
    assert (m.pc, m.acc, m.out) == (0, 0, 0)
    assert m.ram == [0] * 16 and m.state == "WAIT"
    assert (m.sw_s1, m.sw_s2, m.dout, m.rise, m.tick_cnt) == (0, 0, 0, 0, 0)
    # Statusanzeige nach Reset: HALT=0, Mode=0, C=0, Z=0 -> 0 (nach 3 Flanken).
    m.step({"rst": 1, "btn_step": 0, "sw": 3})
    m.step({"rst": 0, "btn_step": 0, "sw": 3})
    m.step({"rst": 0, "btn_step": 0, "sw": 3})
    o = m.step({"rst": 0, "btn_step": 0, "sw": 3})
    assert o["led"] == 0


def test_auto_fibonacci():
    m = ReferenceModel()
    m.reset()
    m.step({"rst": 1, "btn_step": 0, "sw": 0})
    out_at_instr = {}
    n_instr = 0
    for _ in range(ReferenceModel.SUGGESTED_CYCLES):
        before = m.state
        m.step({"rst": 0, "btn_step": 0, "sw": 0})
        if before == "EXECUTE":
            n_instr += 1
            out_at_instr[n_instr] = m.out
    # OUT-Folge aus PROMPT.md nach 4./13./23./33./43./53. Befehl.
    assert out_at_instr[4] == 1
    assert out_at_instr[13] == 2
    assert out_at_instr[23] == 3
    assert out_at_instr[33] == 5
    assert out_at_instr[43] == 8
    assert out_at_instr[53] == 13
    # 58. Befehl = HLT, danach anhalten mit OUT=13, ACC=5, PC=15, Z=0, C=1.
    assert n_instr == 58
    assert m.state == "HALT"
    assert (m.out, m.acc, m.pc, m.z, m.c) == (13, 5, 15, 0, 1)
    # Anzeige ueber display_mux + LED-Register (je 3 Flanken nach sw-Wechsel).
    for sw, expect in ((0, 13), (1, 5), (2, 15), (3, 0b1010)):
        for _ in range(4):
            o = m.step({"rst": 0, "btn_step": 0, "sw": sw})
        assert o["led"] == expect, (sw, o["led"], expect)


def test_tick_first_instruction_timing():
    # R67: Tick kombinatorisch (cnt == TICK-1); erster Befehl in Automatik mit
    # der TICK_CYCLES-ten Flanke ohne Reset (WAIT -> FETCH). Ein registrierter
    # Tick kaeme eine Flanke spaeter und ist damit falsch.
    m = ReferenceModel()
    m.reset()
    m.step({"rst": 1, "btn_step": 0, "sw": 0})
    T = m.TICK_CYCLES
    assert T >= 4
    for i in range(1, T):
        m.step({"rst": 0, "btn_step": 0, "sw": 0})
        assert m.state == "WAIT", (i, m.state)
        assert m.tick_cnt == i, (i, m.tick_cnt)
    # TICK-te Flanke ohne Reset: go=1 -> WAIT -> FETCH.
    assert m.tick_cnt == T - 1
    m.step({"rst": 0, "btn_step": 0, "sw": 0})
    assert m.state == "FETCH", m.state
    assert m.tick_cnt == 0  # Zaehler laeuft weiter (auch in FETCH).
    # Danach genau drei weitere Flanken je Befehl (FETCH, DECODE, EXECUTE).
    m.step({"rst": 0, "btn_step": 0, "sw": 0})
    assert m.state == "DECODE" and m.pc == 1
    m.step({"rst": 0, "btn_step": 0, "sw": 0})
    assert m.state == "EXECUTE"
    m.step({"rst": 0, "btn_step": 0, "sw": 0})
    assert m.state == "WAIT" and m.acc == 1 and m.pc == 1
    # Mit TICK=4 und 4 Takten je Befehl laeuft die CPU danach lueckenlos:
    # Jedes WAIT sieht tick=1 und geht sofort nach FETCH.
    assert m.tick_cnt == T - 1
    m.step({"rst": 0, "btn_step": 0, "sw": 0})
    assert m.state == "FETCH"


def test_single_step():
    m = ReferenceModel()
    m.reset()
    m.step({"rst": 1, "btn_step": 0, "sw": 4})
    _run(m, 10, sw=4)
    assert (m.pc, m.acc, m.state) == (0, 0, "WAIT")
    # Erster Druck: genau ein Befehl (LDI 1 -> ACC=1, PC=1).
    _press_once(m)
    assert (m.pc, m.acc) == (1, 1), (m.pc, m.acc)
    # Ohne Druck bleibt die CPU stehen.
    _run(m, 10, sw=4)
    assert (m.pc, m.acc) == (1, 1)
    # Zweiter Druck: STA 0 -> PC=2, ACC bleibt 1.
    _press_once(m)
    assert (m.pc, m.acc) == (2, 1)
    # Gedrueckt halten loest keinen weiteren Schritt aus (rise nur 1 Takt).
    m2 = ReferenceModel()
    m2.reset()
    m2.step({"rst": 1, "btn_step": 0, "sw": 4})
    _run(m2, 10, sw=4)
    for _ in range(20):
        m2.step({"rst": 0, "btn_step": 1, "sw": 4})
    assert (m2.pc, m2.acc) == (1, 1), (m2.pc, m2.acc)


def test_debounce_short_pulse():
    # Grenzfall: Impuls kuerzer als DEBOUNCE_CYCLES -> kein Schritt.
    m = ReferenceModel()
    m.reset()
    m.step({"rst": 1, "btn_step": 0, "sw": 4})
    _run(m, 10, sw=4)
    m.step({"rst": 0, "btn_step": 1, "sw": 4})  # 1 Takt < DEBOUNCE=2
    _run(m, 10, sw=4)
    assert (m.pc, m.acc, m.state) == (0, 0, "WAIT"), (m.pc, m.acc, m.state)


def test_switch_latency_and_mid_reset():
    m = _run_to_halt(sw=0)
    assert m.state == "HALT" and m.led == 13
    # Latenz: Schalterwechsel erst nach genau 3 Flanken an LEDs sichtbar.
    o1 = m.step({"rst": 0, "btn_step": 0, "sw": 1})
    o2 = m.step({"rst": 0, "btn_step": 0, "sw": 1})
    o3 = m.step({"rst": 0, "btn_step": 0, "sw": 1})
    o4 = m.step({"rst": 0, "btn_step": 0, "sw": 1})
    assert (o1["led"], o2["led"], o3["led"], o4["led"]) == (13, 13, 5, 5)
    # Reset mitten im Programm: beginnt von vorn.
    m2 = ReferenceModel()
    m2.reset()
    m2.step({"rst": 1, "btn_step": 0, "sw": 0})
    _run(m2, 60, sw=0)  # mitten in der Fibonacci-Folge
    assert m2.state != "HALT" and m2.pc != 0
    m2.step({"rst": 1, "btn_step": 0, "sw": 0})
    m2.step({"rst": 1, "btn_step": 0, "sw": 0})
    assert (m2.pc, m2.acc, m2.out) == (0, 0, 0) and m2.state == "WAIT"
    n = 0
    for _ in range(ReferenceModel.SUGGESTED_CYCLES):
        before = m2.state
        m2.step({"rst": 0, "btn_step": 0, "sw": 0})
        if before == "EXECUTE":
            n += 1
            if n == 4:
                assert m2.out == 1  # Programm laeuft von vorn
                break
    assert n == 4
