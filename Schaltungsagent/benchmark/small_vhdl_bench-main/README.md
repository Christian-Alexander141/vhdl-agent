# small_vhdl_bench
Ein kleiner VHDL-Benchmark aus 10 synthetisierbaren Aufgaben (Arty S7).

## API nutzen – in 3 Schritten

Voraussetzung: nur Python 3, keine Installation nötig.

```python
from bench.benchmark_api import list_tasks, get_prompt, evaluate

# 1. Anzeigen, welche Aufgaben es gibt
print(list_tasks())
# -> [{'id': 'task01', 'titel': 'Lauflicht', ...}, ...]

# 2. Prompt für eine Aufgabe holen und an dein Modell/Agent schicken
prompt = get_prompt("task01")
print(prompt)

# 3. Lösung bewerten (0–100 Punkte, bestanden ab 70)
vhdl = "... dein VHDL-Code ..."
xdc = "... dein XDC-Code ..."
ergebnis = evaluate("task01", vhdl, xdc)
print(ergebnis["score"], ergebnis["bestanden"])
```

Das war's.

## Alle Funktionen

```python
list_tasks()              # Liste aller 10 Aufgaben (id, titel, beschreibung)
get_task("task01")        # Eine Aufgabe mit Details (ohne Lösung)
get_prompt("task01")      # Fertiger Text zum Senden ans Modell (ohne Lösung)
get_next("task01")        # Nächste Aufgabe nach task01 (None = erste, Ende = None)
evaluate("task01", vhdl, xdc)  # Bewerten: vhdl als String oder {datei: inhalt}
```

Weitere Beispiele:

```python
from bench import benchmark_api as api

# Alle nacheinander durchgehen:
task = api.get_next(None)       # erste Aufgabe
while task:
    print(task["id"], task["titel"])
    task = api.get_next(task["id"])

# Nur Aufgabe ansehen (ohne Lösung):
t = api.get_task("task03")
print(t["aufgabe"])
```

## Bewertung verstehen

`evaluate()` gibt zurück:

```python
{
  "score": 85.0,       # 0 bis 100
  "bestanden": True,   # True ab 70
  "maengel": [...],    # Liste, was fehlt
  "hinweise": [...]    # Typische Fehlerquellen
}
```

Bewertet wird automatisch: Entity/Architecture, Ports, Keywords,
kein Simulations-Code (`wait for`, `after`, ...), Takt, Debounce, FSM, XDC-Pins.
Referenzlösungen bestehen immer (zum Selbst-Test im Code). 
