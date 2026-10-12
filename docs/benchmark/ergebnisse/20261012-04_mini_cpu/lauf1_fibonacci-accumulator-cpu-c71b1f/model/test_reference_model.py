"""Pruefungen des Referenzmodells anhand von Faellen aus PROMPT.md."""

from reference_model import ReferenceModel


def _run(model, n, rst=0, btn_step=0, sw=0):
    led = None
    for _ in range(n):
        led = model.step({"rst": rst, "btn_step": btn_step, "sw": sw})["led"]
    return led


def test_reset():
    """Reset: synchroner Reset loescht alle Register, LED=0, Neustart."""
    m = ReferenceModel()
    m.reset()
    # Nach reset() ist LED 0 (alle Register 0, WAIT).
    out = m.step({"rst": 0, "btn_step": 0, "sw": 0})
    assert out["led"] == 0, out
    # Etwas laufen lassen, dann synchron resetten.
    _run(m, 60, sw=0)
    assert m._out != 0 or m._pc != 0  # Programm ist angelaufen
    out = m.step({"rst": 1, "btn_step": 0, "sw": 0})
    assert out["led"] == 0, out
    assert (m._pc, m._ir, m._acc, m._z, m._c, m._out) == (0, 0, 0, 0, 0, 0)
    assert m._ram == [0] * 16
    assert m._state == 0  # WAIT
    # Erster Befehl beginnt mit der TICK_CYCLES-ten Flanke ohne Reset.
    m.reset()
    tick = m.GENERICS["TICK_CYCLES"]
    for i in range(1, tick):
        m.step({"rst": 0, "btn_step": 0, "sw": 0})
        assert m._state == 0, (i, m._state)  # noch WAIT
    m.step({"rst": 0, "btn_step": 0, "sw": 0})
    assert m._state == 1, m._state  # FETCH an der TICK-ten Flanke


def test_automatik_fibonacci():
    """Typischer Ablauf: OUT-Folge 1,2,3,5,8,13 und Halt nach 58. Befehl."""
    m = ReferenceModel()
    m.reset()
    seen = []
    last = None
    for _ in range(300):
        led = m.step({"rst": 0, "btn_step": 0, "sw": 0})["led"]
        if led != last:
            seen.append(led)
            last = led
    # LED folgt OUT (Anzeige "00") mit einer Flanke Verzoegerung;
    # die Reihenfolge muss exakt der Fibonacci-Folge entsprechen.
    assert seen[:7] == [0, 1, 2, 3, 5, 8, 13], seen
    # Nach dem Halt bleibt OUT=13 an den LEDs stehen.
    assert seen[-1] == 13, seen
    # Endzustand nach 58. Befehl: OUT=13, ACC=5, PC=15, Z=0, C=1.
    assert m._out == 13, m._out
    assert m._acc == 5, m._acc
    assert m._pc == 15, m._pc
    assert m._z == 0, m._z
    assert m._c == 1, m._c
    assert m._state == 4  # HALT
    # Anzeigen ueber LED pruefen (jeweils 5 Takte warten, 3 sind noetig).
    assert _run(m, 5, sw=0) == 13  # OUT
    assert _run(m, 5, sw=1) == 5  # ACC
    assert _run(m, 5, sw=2) == 15  # PC (Adresse des naechsten Befehls)
    assert _run(m, 5, sw=3) == 0b1010  # Status HALT=1,Auto=0,C=1,Z=0


def test_einzelschritt_entprellung():
    """Grenzfall Einzelschritt: Stillstand ohne Druck, ein Befehl je Druck."""
    m = ReferenceModel()
    m.reset()
    # In den Einzelschritt wechseln (sw=4: Modus 1, Anzeige OUT) und
    # Synchronisierer einschwingen lassen.
    _run(m, 6, sw=4)
    pc0, acc0 = m._pc, m._acc
    # Ohne Tastendruck bleibt die CPU stehen.
    _run(m, 20, sw=4)
    assert (m._pc, m._acc) == (pc0, acc0), (m._pc, m._acc)
    # Genau ein Tastendruck (lang genug): erster Befehl LDI 1.
    _run(m, 6, btn_step=1, sw=4)
    _run(m, 10, btn_step=1, sw=4)  # Befehl zu Ende fuehren
    _run(m, 6, btn_step=0, sw=4)  # loslassen, Entpreller faellt zurueck
    assert m._acc == 1, m._acc
    assert m._pc == 1, m._pc
    # Anzeige ACC nach Schalterwechsel (sw=5) mit Latenz lesen.
    _run(m, 5, sw=5)
    assert m._led == 1, m._led
    # Grenzfall: Impuls kuerzer als DEBOUNCE_CYCLES loest keinen Schritt aus.
    pc1, acc1 = m._pc, m._acc
    m.step({"rst": 0, "btn_step": 1, "sw": 4})
    _run(m, 10, sw=4)
    assert (m._pc, m._acc) == (pc1, acc1), (m._pc, m._acc)


def test_schalter_latenz_und_reset_mitten():
    """Grenzfall Latenz (3 Flanken) und Reset mitten im Programm."""
    m = ReferenceModel()
    m.reset()
    _run(m, 300, sw=0)  # bis HALT laufen lassen (OUT=13, ACC=5)
    assert m._state == 4
    _run(m, 5, sw=0)
    assert m._led == 13, m._led
    # Auf ACC-Anzeige umschalten: nach genau 3 Flanken sichtbar.
    l1 = m.step({"rst": 0, "btn_step": 0, "sw": 1})["led"]
    l2 = m.step({"rst": 0, "btn_step": 0, "sw": 1})["led"]
    l3 = m.step({"rst": 0, "btn_step": 0, "sw": 1})["led"]
    assert (l1, l2, l3) == (13, 13, 5), (l1, l2, l3)
    # CPU-Registeraenderung ist eine Flanke spaeter sichtbar: OUT-Wechsel
    # braucht nach der EXECUTE-Flanke noch genau eine LED-Flanke. Hier
    # indirekt geprüft: Status bleibt stabil 1010.
    _run(m, 5, sw=3)
    assert m._led == 0b1010, m._led
    # Reset mitten im Programm: Programm beginnt von vorn.
    m2 = ReferenceModel()
    m2.reset()
    _run(m2, 60, sw=0)
    assert m2._out in (1, 2), m2._out  # mitten in der Folge
    m2.step({"rst": 1, "btn_step": 0, "sw": 0})
    assert m2._led == 0 and m2._pc == 0 and m2._out == 0
    _run(m2, 10, sw=0)
    assert m2._pc != 15 and m2._state != 4  # wieder angelaufen, nicht HALT
