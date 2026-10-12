from reference_model import ReferenceModel


def _run(model, n, rst=0, btn=0, sw=0):
    led = 0
    for _ in range(n):
        led = model.step({"rst": rst, "btn_step": btn, "sw": sw})["led"]
    return led


def _read_display(model, sw_val, settle=6, btn=0):
    # In Automatik/HALT stoert settle nicht (kein/weiterer Fortschritt egal),
    # im Einzelschritt mit btn=0 bleibt die CPU stehen.
    led = 0
    for _ in range(settle):
        led = model.step({"rst": 0, "btn_step": btn, "sw": sw_val})["led"]
    return led


def _press(model, sw, hold=10, release=10):
    for _ in range(hold):
        model.step({"rst": 0, "btn_step": 1, "sw": sw})
    for _ in range(release):
        model.step({"rst": 0, "btn_step": 0, "sw": sw})


def test_reset():
    m = ReferenceModel()
    m.reset()
    # Synchroner Reset dominiert: led sofort 0, auch bei gesetzten Eingaben.
    assert m.step({"rst": 1, "btn_step": 0, "sw": 0})["led"] == 0
    assert m.step({"rst": 1, "btn_step": 1, "sw": 7})["led"] == 0
    # Nach Freigabe bleibt led zunaechst 0 (OUT=0).
    assert m.step({"rst": 0, "btn_step": 0, "sw": 0})["led"] == 0
    # Alle Register sind 0 (im Einzelschritt bleibt die CPU stehen, daher
    # Anzeige mit mode=1 pruefen): ACC=0, PC=0, Status=0100 (nur Mode=1).
    assert _read_display(m, 5, settle=6) == 0  # ACC
    assert _read_display(m, 6, settle=6) == 0  # PC
    assert _read_display(m, 7, settle=6) == 0b0100  # Status HALT=0,Mode=1,C=0,Z=0
    # Reset mitten im Programm: erst loslaufen lassen ...
    m2 = ReferenceModel()
    _run(m2, 50, sw=0)
    assert m2.step({"rst": 1, "btn_step": 0, "sw": 0})["led"] == 0
    _run(m2, 2, rst=1, sw=0)
    # ... danach ist alles wieder 0 und das Programm beginnt von vorn.
    assert _read_display(m2, 5, settle=6) == 0
    assert _read_display(m2, 6, settle=6) == 0
    assert _read_display(m2, 7, settle=6) == 0b0100
    # Von vorn: nach genuegend Automatik-Takten erscheint wieder OUT=1.
    _run(m2, 30, sw=0)
    assert _read_display(m2, 0, settle=6) == 1


def test_auto_fibonacci():
    m = ReferenceModel()
    _run(m, 2, rst=1, sw=0)
    _run(m, 2, sw=0)
    hist = []
    for _ in range(350):
        hist.append(m.step({"rst": 0, "btn_step": 0, "sw": 0})["led"])
    # OUT-Folge 1,2,3,5,8,13 muss in genau dieser Reihenfolge erstmals auftreten.
    want = [1, 2, 3, 5, 8, 13]
    seen = []
    for v in hist:
        if v in want and v not in seen:
            seen.append(v)
    assert seen == want, (seen, hist[:40])
    # Nach 58 Befehlen haelt die CPU an: OUT=13, ACC=5, PC=15, Status=1010.
    assert _read_display(m, 0, settle=6) == 13  # OUT
    assert _read_display(m, 1, settle=6) == 5  # ACC
    assert _read_display(m, 2, settle=6) == 15  # PC (Adresse nach HLT)
    assert _read_display(m, 3, settle=6) == 0b1010  # HALT=1,Mode=0,C=1,Z=0
    # Angehalten: weitere Takte aendern nichts mehr.
    assert _run(m, 20, sw=0) == 13


def test_single_step_and_debounce():
    m = ReferenceModel()
    _run(m, 2, rst=1, sw=4)
    # Einzelschritt ohne Tastendruck: CPU bleibt stehen (ACC=0, PC=0).
    _run(m, 10, sw=4)
    assert _read_display(m, 5, settle=6) == 0  # ACC in Mode=1
    assert _read_display(m, 6, settle=6) == 0  # PC in Mode=1
    # Genau ein gueltiger Druck = genau ein Befehl (LDI 1: ACC=1, PC=1).
    _press(m, 4, hold=10, release=10)
    assert _read_display(m, 5, settle=6) == 1
    assert _read_display(m, 6, settle=6) == 1
    # Impuls kuerzer als DEBOUNCE_CYCLES loest keinen Schritt aus.
    acc_before = _read_display(m, 5, settle=6)
    pc_before = _read_display(m, 6, settle=6)
    m.step({"rst": 0, "btn_step": 1, "sw": 4})
    for _ in range(10):
        m.step({"rst": 0, "btn_step": 0, "sw": 4})
    assert _read_display(m, 5, settle=6) == acc_before
    assert _read_display(m, 6, settle=6) == pc_before


def test_switch_latency_3_cycles():
    m = ReferenceModel()
    _run(m, 2, rst=1, sw=4)
    _press(m, 4, hold=10, release=10)  # ACC=1, OUT=0
    assert _read_display(m, 4, settle=6) == 0  # OUT-Anzeige
    # Umschalten auf ACC-Anzeige: nach genau 3 Flanken sichtbar.
    l1 = m.step({"rst": 0, "btn_step": 0, "sw": 5})["led"]
    l2 = m.step({"rst": 0, "btn_step": 0, "sw": 5})["led"]
    l3 = m.step({"rst": 0, "btn_step": 0, "sw": 5})["led"]
    assert l1 == 0
    assert l2 == 0
    assert l3 == 1
