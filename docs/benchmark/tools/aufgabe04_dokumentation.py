"""Erzeugt docs/Aufgabe04_Mini-CPU.pdf aus docs/benchmark/ergebnisse/20261012-04_mini_cpu.

Aufruf (aus dem Repo-Wurzelverzeichnis):
    python3 docs/benchmark/tools/aufgabe04_dokumentation.py
Benötigt Chromium für den PDF-Druck; alle Diagramme sind eingebettetes SVG.
"""
import html
import json
import re
import subprocess
import sys
import tempfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
RESULTS = REPO / "docs/benchmark/ergebnisse/20261012-04_mini_cpu"
PROMPT = REPO / "Schaltungsagent/benchmark/prompts/04_mini_cpu.md"
REF_TB = REPO / "Schaltungsagent/benchmark/reference/04_mini_cpu_ref_tb.vhd"
OUT_PDF = REPO / "docs/Aufgabe04_Mini-CPU.pdf"

e = html.escape


def de(x, digits=1) -> str:
    """Zahl mit deutschem Dezimalkomma."""
    if isinstance(x, (int, float)):
        return f"{x:.{digits}f}".replace(".", ",")
    return str(x)


def mmss(minutes: float) -> str:
    total = round(minutes * 60)
    return f"{total // 60}:{total % 60:02d}"


# --------------------------------------------------------------------------- Daten
def load_runs() -> list[dict]:
    runs = []
    for folder in sorted(RESULTS.glob("lauf*_*")):
        data = json.loads((folder / "kennzahlen.json").read_text())
        data["folder"] = folder
        data["event_list"] = [json.loads(line) for line in (folder / "events.jsonl").read_text().splitlines()]
        data["log"] = (folder / "server.log").read_text(errors="replace")
        data["phases"] = phases(data)
        data["schedule"] = schedule(data)
        runs.append(data)
    return runs


def ts(event: dict) -> datetime:
    return datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))


def phases(run: dict) -> dict:
    """Minuten je Abschnitt: Planung, Referenzmodell, Module, Prüfungen, Fehlerbehandlung, Synthese, Flash."""
    ev = run["event_list"]
    first = lambda kind, **kw: next(x for x in ev if x["event_type"] == kind and all(x["payload"].get(k) == v for k, v in kw.items()))
    impl_start = ts(first("STAGE_STARTED", stage="IMPLEMENTING"))
    model_done = ts(first("REFERENCE_MODEL_CREATED"))
    graph_done = ts(first("IMPLEMENTATION_GRAPH_COMPLETED"))
    synth_start = ts(first("SYNTHESIS_STARTED"))
    flash_start = ts(first("FLASH_STARTED"))
    done = ts(first("TASK_COMPLETED"))
    checks = sum(run["stage_min"].get(s, 0) for s in ("STATIC_CHECK", "SIMULATING", "VALIDATING"))
    between = (synth_start - graph_done).total_seconds() / 60
    return {
        "Planung": run["plan_min"],
        "Referenzmodell": (model_done - impl_start).total_seconds() / 60,
        "Module und Testbenches": (graph_done - model_done).total_seconds() / 60,
        "Prüfungen": checks,
        "Fehlerbehandlung": max(between - checks, 0),
        "Synthese": (flash_start - synth_start).total_seconds() / 60,
        "Flashen": (done - flash_start).total_seconds() / 60,
    }


def schedule(run: dict) -> dict:
    """Zeitfenster je Modul (Modul + Testbench) relativ zum Start der Implementierung, in Minuten."""
    windows = defaultdict(lambda: [None, None])
    starts = {}
    for line in run["log"].splitlines():
        m = re.match(r"\d{4}-\d\d-\d\d (\d\d):(\d\d):(\d\d)", line)
        if not m:
            continue
        t = int(m.group(1)) * 60 + int(m.group(2)) + int(m.group(3)) / 60
        call = re.search(r"OPENCODE_CALL stage=(implement_module|implement_testbench) .*task_id=(\w+?)_[0-9a-f]{8}$", line)
        if call:
            starts[call.group(2) + call.group(1)] = t
            w = windows[call.group(2)]
            w[0] = t if w[0] is None else min(w[0], t)
        result = re.search(r"OPENCODE_RESULT \{'stage': '(implement_module|implement_testbench)', 'task_id': '(\w+?)_[0-9a-f]{8}'", line)
        if result:
            w = windows[result.group(2)]
            w[1] = t if w[1] is None else max(w[1], t)
    origin = min(w[0] for w in windows.values())
    return {name: (w[0] - origin, w[1] - origin) for name, w in windows.items() if None not in w}


# --------------------------------------------------------------------------- SVG
def svg_hierarchy() -> str:
    box = lambda x, y, w, h, title, sub, fill: (
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="{fill}" stroke="#555"/>'
        f'<text x="{x + w / 2}" y="{y + 17}" text-anchor="middle" font-weight="700" font-size="12">{title}</text>'
        f'<text x="{x + w / 2}" y="{y + 32}" text-anchor="middle" font-size="9.5" fill="#333">{sub}</text>')
    parts = [box(260, 8, 200, 42, "mini_cpu", "Top-Level, LED-Register", "#dbe8f6")]
    level1 = [("sync2 (sw)", "2-FF, WIDTH=3", "#eeeeee"), ("sync2 (btn)", "2-FF, WIDTH=1", "#eeeeee"),
              ("debouncer", "dout, rise", "#eeeeee"), ("tick_gen", "TICK_CYCLES", "#eeeeee"),
              ("cpu_core", "ACC, Z, C, OUT", "#fde9c8"), ("display_mux", "Anzeigeauswahl", "#eeeeee")]
    for i, (t, s, f) in enumerate(level1):
        x = 10 + i * 118
        parts.append(f'<line x1="360" y1="50" x2="{x + 52}" y2="80" stroke="#777"/>')
        parts.append(box(x, 80, 104, 42, t, s, f))
    level2 = [("control_unit", "FSM, PC, IR", "#f8d7c4"), ("alu", "Rechenwerk", "#f8d7c4"),
              ("program_rom", "16 × 8 Bit", "#d5ecd4"), ("data_ram", "16 × 4 Bit", "#d5ecd4")]
    for i, (t, s, f) in enumerate(level2):
        x = 300 + i * 112 - 110
        parts.append(f'<line x1="{10 + 4 * 118 + 52}" y1="122" x2="{x + 52}" y2="152" stroke="#777"/>')
        parts.append(box(x, 152, 104, 42, t, s, f))
    return f'<svg viewBox="0 0 720 200" width="100%" font-family="DejaVu Sans, sans-serif">{"".join(parts)}</svg>'


def svg_fsm() -> str:
    states = {"WAIT": (60, 70), "FETCH": (210, 70), "DECODE": (360, 70), "EXECUTE": (510, 70), "HALT": (660, 70)}
    parts = ['<defs><marker id="a" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">'
             '<path d="M0,0 L8,4 L0,8 z" fill="#444"/></marker></defs>']
    for name, (x, y) in states.items():
        fill = "#fde9c8" if name == "HALT" else "#dbe8f6"
        parts.append(f'<ellipse cx="{x}" cy="{y}" rx="52" ry="24" fill="{fill}" stroke="#555"/>'
                     f'<text x="{x}" y="{y + 4}" text-anchor="middle" font-weight="700" font-size="12">{name}</text>')
    arrow = lambda x1, y1, x2, y2, label, ly: (
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#444" marker-end="url(#a)"/>'
        f'<text x="{(x1 + x2) / 2}" y="{ly}" text-anchor="middle" font-size="10">{label}</text>')
    parts.append(arrow(112, 70, 156, 70, "go", 62))
    parts.append(arrow(262, 70, 306, 70, "IR, PC+1", 62))
    parts.append(arrow(412, 70, 456, 70, "", 62))
    parts.append(arrow(562, 70, 606, 70, "HLT", 62))
    parts.append('<path d="M510,94 C510,140 60,140 60,96" fill="none" stroke="#444" marker-end="url(#a)"/>'
                 '<text x="285" y="136" text-anchor="middle" font-size="10">sonst: Befehl ausgeführt, zurück nach WAIT</text>')
    parts.append('<text x="60" y="28" text-anchor="middle" font-size="10">kein go: bleiben</text>'
                 '<text x="660" y="28" text-anchor="middle" font-size="10">bis Reset</text>')
    return f'<svg viewBox="0 0 720 150" width="100%" font-family="DejaVu Sans, sans-serif">{"".join(parts)}</svg>'


PHASE_COLORS = {"Planung": "#8fb3d9", "Referenzmodell": "#b9d7a8", "Module und Testbenches": "#f2c46d",
                "Prüfungen": "#c9a6d9", "Fehlerbehandlung": "#e88b7d", "Synthese": "#7fc4c0", "Flashen": "#bbbbbb"}


def svg_phases(runs: list[dict]) -> str:
    scale = 12.0  # Pixel je Minute
    parts, y = [], 10
    for run in runs:
        parts.append(f'<text x="0" y="{y + 15}" font-size="11" font-weight="700">{e(run["label"])}</text>')
        x = 100
        for name, minutes in run["phases"].items():
            w = minutes * scale
            if w <= 0:
                continue
            parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="22" fill="{PHASE_COLORS[name]}" stroke="#fff"/>')
            if w > 26:
                parts.append(f'<text x="{x + w / 2}" y="{y + 15}" text-anchor="middle" font-size="9">{de(minutes)}</text>')
            x += w
        parts.append(f'<text x="{x + 6}" y="{y + 15}" font-size="10">{de(run["duration_min"])} min</text>')
        y += 34
    lx = 0
    for name, color in PHASE_COLORS.items():
        parts.append(f'<rect x="{lx}" y="{y + 4}" width="11" height="11" fill="{color}"/>'
                     f'<text x="{lx + 15}" y="{y + 14}" font-size="9.5">{name}</text>')
        lx += 15 + len(name) * 5.2 + 10
    return f'<svg viewBox="0 0 730 {y + 24}" width="100%" font-family="DejaVu Sans, sans-serif">{"".join(parts)}</svg>'


def svg_gantt(run: dict, order: list[str], scale: float = 23.0) -> str:
    # scale: Pixel je Minute
    sched = run["schedule"]
    critical = {"control_unit", "cpu_core", "mini_cpu"}
    parts, y = [], 4
    for name in order:
        if name not in sched:
            continue
        start, end = sched[name]
        fill = "#e88b7d" if name in critical else "#8fb3d9"
        parts.append(f'<text x="0" y="{y + 12}" font-size="10">{name}</text>'
                     f'<rect x="{100 + start * scale}" y="{y}" width="{max((end - start) * scale, 2)}" height="15" fill="{fill}"/>')
        y += 19
    end_all = max(end for _, end in sched.values())
    for minute in range(0, int(end_all) + 2, 2):
        x = 100 + minute * scale
        parts.append(f'<line x1="{x}" y1="0" x2="{x}" y2="{y}" stroke="#ddd"/>'
                     f'<text x="{x}" y="{y + 12}" text-anchor="middle" font-size="9">{minute}</text>')
    parts.append(f'<text x="{100 + end_all * scale + 4}" y="{y - 4}" font-size="10" font-weight="700">'
                 f'{de(end_all)} min</text>')
    return f'<svg viewBox="0 0 730 {y + 18}" width="100%" font-family="DejaVu Sans, sans-serif">{"".join(parts)}</svg>'


# --------------------------------------------------------------------------- Inhalt
ISA = [
    ("0", "NOP", "keine Wirkung", "–"), ("1", "LDI n", "ACC := n", "Z"),
    ("2", "LDA a", "ACC := RAM[a]", "Z"), ("3", "STA a", "RAM[a] := ACC", "–"),
    ("4", "ADD a", "ACC := (ACC + RAM[a]) mod 16", "Z, C (Übertrag)"),
    ("5", "SUB a", "ACC := (ACC − RAM[a]) mod 16", "Z, C (Borgen)"),
    ("6–8", "AND/OR/XOR a", "bitweise mit RAM[a]", "Z, C := 0"),
    ("9", "SHL", "ACC links, '0' nachschieben", "Z, C := altes Bit 3"),
    ("A", "SHR", "ACC rechts, '0' nachschieben", "Z, C := altes Bit 0"),
    ("B", "JMP t", "PC := t", "–"), ("C", "JZ t", "PC := t, wenn Z = 1", "–"),
    ("D", "JC t", "PC := t, wenn C = 1", "–"), ("E", "OUT", "OUT := ACC", "–"),
    ("F", "HLT", "anhalten bis Reset", "–"),
]
ROM = [("0", "11", "LDI 1", "ACC = 1"), ("1", "30", "STA 0", "a := 1"), ("2", "31", "STA 1", "b := 1"),
       ("3", "E0", "OUT", "OUT = 1"), ("4", "20", "LDA 0", "Schleife: ACC := a"),
       ("5", "41", "ADD 1", "ACC := a + b"), ("6", "DE", "JC 14", "Überlauf → Ende"),
       ("7", "32", "STA 2", "s := a + b"), ("8", "21", "LDA 1", ""), ("9", "30", "STA 0", "a := b"),
       ("10", "22", "LDA 2", ""), ("11", "31", "STA 1", "b := s"), ("12", "E0", "OUT", "neue Zahl ausgeben"),
       ("13", "B4", "JMP 4", ""), ("14", "F0", "HLT", "Ende"), ("15", "00", "NOP", "")]
OUT_SEQUENCE = [(4, 1, 2.0), (13, 2, 6.5), (23, 3, 11.5), (33, 5, 16.5), (43, 8, 21.5), (53, 13, 26.5)]
BOARD_CHECKS = [
    ("alle Schalter unten, BTN0", "OUT", "0001, 0010, 0011, 0101, 1000, 1101 (etwa alle 5 s), Halt nach rund 29 s", "1101"),
    ("SW0 oben", "ACC", "ändert sich zweimal je Sekunde", "0101"),
    ("SW1 oben", "PC", "Adresse des nächsten Befehls", "1111"),
    ("SW1 und SW0 oben", "Status (HALT, Modus, C, Z)", "LD5 geht beim Halt an", "1010"),
    ("SW2 oben, BTN1 drücken", "gewählte Anzeige", "genau ein Befehl je Druck", "–"),
]
FINDINGS = [
    ("48", "Planung der parallelen Arbeit: kritischer Pfad zuerst, Start sobald Abhängigkeiten fertig",
     "Module und Testbenches 20,5 statt 24,5 min; cpu_core startet nach 6:18 statt 13:09 min"),
    ("49", "task_graph.json ohne Kopien der Aufgabeneingaben", "28 KB statt 1,06 MB"),
    ("50", "Abschlussereignis ohne Projektzustand, Lebenszeichen nach 60 s Stille",
     "56 statt 163 KB Ereignisverkehr, 20 statt 103 Lebenszeichen, Abschlussereignis 1 statt 101 KB"),
    ("51", "OpenCode-Protokoll mit echter Auftragsgröße und Dauer", "z. B. prompt_length 5944 statt immer 7516"),
    ("52", "Testbenches auch für Zwischenmodule mit eigener Logik", "cpu_core_tb; Mutationsquote 1,0"),
    ("53", "Reset-Konvention der Skills folgt dem Manifest", "keine offene Reset-Frage mehr im Plan"),
    ("54", "Trajektorie mit Planung, Modell, Modellwechsel und Endstand der Quellen", "im Kontrolllauf vollständig erfasst"),
    ("55", "Prüfanleitung fürs Board aus dem Plan in der Abschlussmeldung", "6 Schritte; siehe #57"),
    ("56", "Anbieterausfall als Infrastrukturfehler, Planung stoppt danach; Checkpoint zählt nicht als OpenCode-Änderung",
     "ohne #56: 13 min Eskalation ohne Aussicht im ersten Kontrolllauf"),
    ("57", "Prüfanleitung wird von der Abschlussprüfung gegengeprüft",
     "im Kontrolllauf waren in 2 Schritten SW0/SW1 vertauscht (vor #57)"),
]


CSS = """
    @page { size: A4; margin: 18mm 17mm 20mm 17mm;
            @bottom-center { content: counter(page) " / " counter(pages); font: 9pt 'DejaVu Sans', sans-serif; color:#666; } }
    @page :first { @bottom-center { content: none; } }
    body { font-family: 'DejaVu Sans', 'Liberation Sans', sans-serif; font-size: 10pt; line-height: 1.42; color: #1d1d1d; }
    h1 { font-size: 22pt; margin: 0 0 4mm 0; color: #1f3d63; }
    h2 { font-size: 14pt; color: #1f3d63; border-bottom: 1.5px solid #1f3d63; padding-bottom: 1mm; margin-top: 9mm; break-after: avoid; }
    h3 { font-size: 11.5pt; color: #2b4f7c; margin-top: 6mm; break-after: avoid; }
    p, li { text-align: justify; hyphens: auto; }
    table { border-collapse: collapse; width: 100%; margin: 3mm 0 4mm 0; font-size: 9pt; break-inside: avoid; }
    th { background: #e4ecf5; text-align: left; padding: 1.5mm 2mm; border: 1px solid #c7d3e0; }
    td { padding: 1.2mm 2mm; border: 1px solid #d6dde6; vertical-align: top; }
    table.compact td, table.compact th { padding: 0.8mm 1.6mm; }
    pre { background: #f5f6f8; border: 1px solid #dde1e6; padding: 2.5mm; font-size: 8.3pt; line-height: 1.3; white-space: pre-wrap; break-inside: avoid; }
    code { font-family: 'DejaVu Sans Mono', monospace; font-size: 8.8pt; }
    .title { margin-top: 35mm; }
    .subtitle { font-size: 13pt; color: #444; margin-bottom: 14mm; }
    .meta td { border: none; padding: 0.6mm 2mm 0.6mm 0; font-size: 10pt; }
    .box { background: #f1f6fb; border-left: 4px solid #2b6cb0; padding: 3mm 4mm; margin: 4mm 0; break-inside: avoid; }
    .warn { background: #fdf3ec; border-left-color: #d9822b; }
    .fig { margin: 3mm 0 1mm 0; break-inside: avoid; }
    .caption { font-size: 8.5pt; color: #555; margin: 0 0 4mm 0; }
    .pagebreak { break-before: page; }
    .toc li { margin: 0.6mm 0; }
    """


def table(headers, rows, cls="") -> str:
    head = "".join(f"<th>{e(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows)
    return f'<table class="{cls}"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def code(text: str) -> str:
    return f"<pre>{e(text)}</pre>"


def vhdl_body(path: Path) -> str:
    lines = [l for l in path.read_text().splitlines() if not l.strip().startswith("--")]
    start = next(i for i, l in enumerate(lines) if l.strip().startswith("p_seq"))
    end = next(i for i, l in enumerate(lines) if i > start and l.strip().startswith("end process"))
    return "\n".join(lines[start:end + 1])


def build_html(runs: list[dict]) -> str:
    r1, r2, r3 = runs
    order = ["control_unit", "alu", "data_ram", "program_rom", "display_mux", "cpu_core",
             "debouncer", "sync2", "tick_gen", "mini_cpu"]
    order_r1 = sorted(r1["schedule"], key=lambda n: r1["schedule"][n][0])
    tick_before = vhdl_body(r3["folder"] / "befunde/tick_gen_vor_reparatur.vhd")
    verdict = json.loads((r3["folder"] / "reports/repair_verdict.json").read_text())
    result_rows = []
    keys = [
        ("Projekt", lambda r: f'<code>{e(r["project"])}</code>'),
        ("Codestand", lambda r: f'<code>{r["commit"]}</code> ({e(r["note"])})'),
        ("Gesamtdauer", lambda r: f'{mmss(r["duration_min"])} min'),
        ("Ergebnis", lambda r: r["status"]),
        ("Reparaturen", lambda r: str(r["repairs"])),
        ("OpenCode-Aufrufe (Summe)", lambda r: f'{r["opencode_calls"]} ({de(r["opencode_min"])} min)'),
        ("Einzelanforderungen", lambda r: f'{r["requirements"]}; Abschlussprüfung: alle erfüllt'),
        ("Testbenches", lambda r: str(len(r["testbenches"])) + (" (mit cpu_core_tb)" if "cpu_core_tb" in r["testbenches"] else "")),
        ("Mutationsquote", lambda r: de(r["mutation_score"])),
        ("Timing (WNS)", lambda r: f'+{de(r["wns_ns"], 2)} ns'),
        ("LUTs / Flipflops", lambda r: f'{r["luts"]} / {r["registers"]}'),
        ("Referenz-Testbench", lambda r: r["reference_testbench"]),
        ("Board", lambda r: "SRAM + QSPI geflasht" if r["flashed"] else "nicht geflasht"),
        ("Ereignisse (Lebenszeichen)", lambda r: f'{r["events"]} ({r["heartbeats"]}), {r["event_traffic_kb"]} KB'),
        ("task_graph.json", lambda r: f'{r["task_graph_kb"]} KB'),
    ]
    for label, fn in keys:
        result_rows.append([f"<b>{e(label)}</b>"] + [fn(r) for r in runs])

    phase_rows = [[e(name)] + [de(r["phases"][name]) for r in runs] for name in PHASE_COLORS]
    phase_rows.append(["<b>Summe</b>"] + [f'<b>{de(r["duration_min"])}</b>' for r in runs])

    css = CSS
    out_rows = [[str(n), str(v), f'{v:04b}', de(t)] for n, v, t in OUT_SEQUENCE]
    sections = []

    sections.append(f"""
    <div class="title">
      <h1>Benchmark-Aufgabe 04<br>4-Bit-Akkumulator-CPU</h1>
      <div class="subtitle">Entwurfsaufgabe, Prüfgrundlagen und Ergebnisse von drei realen Läufen des
      VHDL-Multiagentensystems bis zum Flashen auf das Arty S7-50</div>
      <table class="meta">
        <tr><td><b>Stand</b></td><td>12.10.2026</td></tr>
        <tr><td><b>Aufgabe</b></td><td><code>Schaltungsagent/benchmark/prompts/04_mini_cpu.md</code></td></tr>
        <tr><td><b>Referenz-Testbench</b></td><td><code>Schaltungsagent/benchmark/reference/04_mini_cpu_ref_tb.vhd</code></td></tr>
        <tr><td><b>Ergebnisse</b></td><td><code>docs/benchmark/ergebnisse/20261012-04_mini_cpu/</code></td></tr>
        <tr><td><b>Modell</b></td><td>opencode/muse-spark-1.3-contributor-free (Fallback: mimo-v2.6-flash-free)</td></tr>
        <tr><td><b>Zielhardware</b></td><td>Digilent Arty S7-50 (xc7s50csga324-1), Vivado 2026.1</td></tr>
      </table>
      <div class="box"><b>Ergebnis in Kürze.</b> Alle drei Läufe erzeugten ohne menschlichen Eingriff einen
      funktionsfähigen Entwurf mit zehn Modulen, bestanden alle Prüfungen des Systems und die unabhängige
      Referenz-Testbench, erfüllten das Timing und wurden auf das Board geflasht; die LED-Ausgabe hat der
      Benutzer am Board bestätigt. Die ersten beiden Läufe ({mmss(r1["duration_min"])} und {mmss(r2["duration_min"])} min)
      kamen ohne Reparatur aus. Aus ihnen wurden zehn Verbesserungen abgeleitet (#48–#57); der Kontrolllauf
      ({mmss(r3["duration_min"])} min) bestätigt sie und zeigt, dass der differentielle Test eine Abweichung von einem
      Takt findet, die die Referenz-Testbench mit ihrem Spielraum nicht sieht.</div>
      <h3>Inhalt</h3>
      <ol class="toc">
        <li>Ziel und Einordnung</li><li>Aufgabenstellung</li><li>Erwartetes Verhalten</li>
        <li>Prüfgrundlagen</li><li>Versuchsaufbau</li><li>Ergebnisse der drei Läufe</li>
        <li>Verlauf der einzelnen Läufe</li><li>Befunde und Verbesserungen</li>
        <li>Vergleich mit einem einzelnen OpenCode-Aufruf</li><li>Grenzen</li><li>Ablage und Reproduktion</li>
      </ol>
    </div>""")

    sections.append(f"""
    <h2 class="pagebreak">1 Ziel und Einordnung</h2>
    <p>Die Benchmark-Aufgaben 01–03 (Zähler, Hamming-Decoder, Ampel) bestehen aus einem bis drei Modulen.
    Aufgabe 04 prüft, ob das Multiagentensystem (MAS) eine deutlich größere, hierarchische Schaltung von der
    Anforderung bis zur Hardware umsetzen kann. Gewählt wurde eine kleine Akkumulator-CPU als Vorstufe einer
    8-Bit-CPU: Sie enthält die drei Grundbausteine eines Rechners – <b>Rechenwerk</b> (ALU mit Flags),
    <b>Steuerwerk</b> (Befehlsablauf mit Befehlszähler und Befehlsregister) und <b>Speicher</b> (Programm- und
    Datenspeicher) – und arbeitet mit 4 Bit breiten Daten, damit jedes Ergebnis direkt an den vier LEDs des
    Boards ablesbar ist.</p>
    <p>Zwei Anforderungen bestimmten die Formulierung: Erstens muss das Ergebnis am Board <b>von einem Menschen
    nachvollziehbar</b> sein (festes Demoprogramm mit bekannter LED-Folge, wählbare Anzeige, Einzelschritt).
    Zweitens muss die Aufgabe <b>taktgenau eindeutig</b> sein, weil das MAS einen differentiellen Test gegen ein
    ausführbares Referenzmodell durchführt, das mit zufälligen Eingangsfolgen Takt für Takt vergleicht. Jede
    Latenz (Synchronisierer, Entprellung, Tick, Befehlsphasen, LED-Register) ist deshalb ausdrücklich festgelegt.</p>
    <h2>2 Aufgabenstellung</h2>
    <p>Der vollständige Wortlaut steht in <code>04_mini_cpu.md</code>; hier die Bestandteile in Tabellenform.</p>
    <h3>2.1 Schnittstelle und Board-Belegung</h3>
    {table(["Port", "Typ", "Board", "Bedeutung"], [
        ["clk", "in std_logic", "R2, 100 MHz", "Systemtakt"],
        ["rst", "in std_logic", "BTN0 (G15)", "synchroner Reset, active high"],
        ["btn_step", "in std_logic", "BTN1 (K16)", "Einzelschritt"],
        ["sw(1 downto 0)", "in", "SW0, SW1", "Anzeige: 00 OUT, 01 ACC, 10 PC, 11 Status"],
        ["sw(2)", "in", "SW2", "0 Automatik (ein Befehl je Tick), 1 Einzelschritt"],
        ["led(3 downto 0)", "out", "LD5 … LD2", "Anzeigewert, led(0) = LD2"],
        ["TICK_CYCLES", "Generic", "–", "Standard 50 000 000 (2 Befehle/s), mindestens 4"],
        ["DEBOUNCE_CYCLES", "Generic", "–", "Standard 1 000 000 (10 ms)"],
    ], "compact")}
    <h3>2.2 Befehlssatz</h3>
    <p>Befehlswort 8 Bit: Opcode in Bit 7..4, Operand (Adresse a, Konstante n oder Sprungziel t) in Bit 3..0.
    Akkumulator ACC, Befehlszähler PC und Ausgaberegister OUT haben 4 Bit, das Befehlsregister IR 8 Bit;
    Z und C sind Flag-Register. „Z“ bedeutet: Z := 1 genau dann, wenn der neue ACC-Wert 0 ist. Nicht
    genannte Flags bleiben unverändert – auch C bei LDI und LDA.</p>
    {table(["Opcode", "Befehl", "Wirkung", "Flags"], [[f"<code>{a}</code>", f"<code>{b}</code>", e(c), e(d)] for a, b, c, d in ISA], "compact")}
    <h3>2.3 Demoprogramm im Programmspeicher</h3>
    <p>RAM[0] und RAM[1] halten die letzten beiden Fibonacci-Zahlen a und b. Jeder Schleifendurchlauf
    berechnet a + b, gibt die Summe aus und verschiebt das Paar. Läuft die Summe über (21 &gt; 15), setzt ADD
    das Carry, JC springt zum HLT.</p>
    {table(["Adresse", "Wort", "Befehl", "Bedeutung"], [[a, f"<code>x\"{b}\"</code>", f"<code>{c}</code>", e(d)] for a, b, c, d in ROM], "compact")}
    <h3>2.4 Steuerwerk</h3>
    <div class="fig">{svg_fsm()}</div>
    <p class="caption">Abbildung 1: Zustandsautomat des Steuerwerks. go ist in Automatik der Tick, im
    Einzelschritt der entprellte Tastendruck; in anderen Zuständen als WAIT wird go ignoriert.</p>
    <p>Ein Befehl braucht nach go genau drei weitere Taktflanken: FETCH lädt IR := ROM[PC] und erhöht PC,
    DECODE ändert kein Register, EXECUTE führt den Befehl aus (ein Sprung überschreibt das PC + 1 aus FETCH).</p>
    <h3>2.5 Eingänge, Takt und Anzeige</h3>
    <ul>
      <li><b>Synchronisierung:</b> sw und btn_step je über zwei Flipflops.</li>
      <li><b>Entprellung:</b> Register dout und Zähler; dout übernimmt den Eingang mit der DEBOUNCE_CYCLES-ten
      aufeinanderfolgenden Flanke, an der Eingang und dout verschieden sind. Der Schrittimpuls rise ist ein
      Register und genau einen Takt lang 1, beginnend mit der Flanke, an der dout von 0 auf 1 wechselt.</li>
      <li><b>Tick:</b> Zähler 0 … TICK_CYCLES−1, Tick beim Zählerstand TICK_CYCLES−1 für genau einen Takt; der erste
      Befehl beginnt nach dem Reset mit der TICK_CYCLES-ten steigenden Flanke.</li>
      <li><b>Anzeige:</b> led ist ein Register; eine Schalteränderung ist nach genau drei Flanken sichtbar, eine
      Registeränderung der CPU eine Flanke später. Status: led(3) HALT, led(2) Betriebsart, led(1) C, led(0) Z.</li>
      <li><b>Reset:</b> alle Register einschließlich der 16 RAM-Zellen werden 0, das Steuerwerk geht nach WAIT.</li>
    </ul>
    <h3>2.6 Modulstruktur</h3>
    <div class="fig">{svg_hierarchy()}</div>
    <p class="caption">Abbildung 2: Vorgegebene Hierarchie (zwei Ebenen, zehn Entities, je eine Datei
    <code>src/&lt;entity&gt;.vhd</code>). Orange: Rechen- und Steuerwerk, grün: Speicher.</p>
    <p>Gefordert ist außerdem eine Testbench <code>tests/mini_cpu_tb.vhd</code> mit TICK_CYCLES = 4 und
    DEBOUNCE_CYCLES = 2, die die OUT-Folge, das Anhalten, den Einzelschritt mit Entprellung, einen Reset mitten
    im Programm und die Latenz von drei Flanken nach einer Schalteränderung prüft.</p>
    """)

    sections.append(f"""
    <h2 class="pagebreak">3 Erwartetes Verhalten</h2>
    <p>Das Demoprogramm wurde vorab mit einem Befehlssatzmodell in Python ausgeführt
    (<code>pruefgrundlagen/befehlssatz_modell.py</code>). Die CPU führt 58 Befehle aus und hält dann an; bei
    2 Befehlen je Sekunde ergeben sich folgende Ausgaben:</p>
    {table(["nach Befehl Nr.", "OUT (dezimal)", "LEDs LD5…LD2", "Zeit nach Reset [s]"], out_rows, "compact")}
    <p>Endzustand nach dem HLT (58. Befehl, nach rund 29 s): OUT = 13 (1101), ACC = 5 (0101; 8 + 13 = 21 ≡ 5),
    PC = 15 (1111, nach dem Holen des HLT an Adresse 14), Z = 0, C = 1, Status in Automatik 1010.</p>
    <h3>3.1 Prüfanleitung fürs Board</h3>
    {table(["Einstellung", "Anzeige", "Beobachtung", "nach dem Halt"], [[e(a), e(b), e(c), f"<code>{d}</code>"] for a, b, c, d in BOARD_CHECKS], "compact")}
    <div class="box">Nach BTN0 beginnt das Programm von vorn. Im Einzelschritt (SW2 oben) zeigt die ACC-Anzeige
    nach dem ersten Druck 0001, die PC-Anzeige 0001; ein kurzes Prellen löst keinen Schritt aus.</div>

    <h2>4 Prüfgrundlagen</h2>
    <h3>4.1 Unabhängige Referenz-Testbench</h3>
    <p><code>04_mini_cpu_ref_tb.vhd</code> ist dem System unbekannt und prüft nur über die Ports der
    Top-Level-Entity: die Folge der OUT-Werte (Reihenfolge exakt, Zeitpunkte mit Spielraum), den Endzustand in
    allen vier Anzeigen, das dauerhafte Anhalten, einen Reset mitten im Programm sowie den Einzelschritt
    (kein Schritt ohne Druck, keiner durch einen 1-Takt-Impuls, je Druck genau ein Befehl). Sie wurde gegen eine
    eigene, vom System unabhängige Umsetzung geprüft (<code>pruefgrundlagen/eigene_umsetzung_mini_cpu.vhd</code>)
    und gegen sechs absichtlich fehlerhafte Varianten:</p>
    {table(["eingebauter Fehler", "erkannt"], [
        ["ADD setzt kein Carry (kein Halt)", "ja – zusätzliche OUT-Werte"],
        ["rise auch beim Loslassen der Taste", "ja – PC nach dem ersten/zweiten Schritt"],
        ["keine Entprellung", "ja – Schritt durch 1-Takt-Impuls"],
        ["HLT ohne Wirkung", "ja – zusätzliche OUT-Werte"],
        ["Z und C in der Statusanzeige vertauscht", "ja – Status nach dem Anhalten"],
        ["LDA löscht C", "nein – mit dem festen Programm an den Ports nicht beobachtbar"],
    ], "compact")}
    <p>Grenze: Weil das Programm fest im ROM steht, sind Fehler in Befehlen, die das Demoprogramm nicht in der
    kritischen Reihenfolge nutzt, von außen nicht sichtbar. Die Testbench toleriert außerdem bewusst Abweichungen
    im Zeitverhalten; taktgenaue Prüfung leistet der differentielle Test des Systems.</p>
    <h3>4.2 Referenzmodelle des Systems</h3>
    <p>Das MAS lässt vor der Implementierung ein Python-Referenzmodell aus PROMPT.md schreiben und vergleicht den
    Entwurf in einer erzeugten Testbench Takt für Takt damit (TICK_CYCLES = 4, DEBOUNCE_CYCLES = 2, zufällige
    Eingangsfolgen mit Reset-Fenstern). Jedes in den Läufen erzeugte Modell wurde während des Laufs, ohne
    Eingriff, gegen die eigene Umsetzung geprüft: alle stimmten mit 4 bis 7 Zufallsfolgen à 400 Takten überein,
    auch das im Kontrolllauf nach einem Modellstreit neu erzeugte.</p>
    """)

    sections.append(f"""
    <h2 class="pagebreak">5 Versuchsaufbau</h2>
    <ul>
      <li><b>Eingang:</b> Server wie mit <code>start.py</code>, Aufgabe als <code>POST /api/chat</code> mit dem Wortlaut
      von <code>04_mini_cpu.md</code> – derselbe Weg wie aus dem Dashboard. Ein zweiter WebSocket-Client schrieb
      alle Ereignisse mit.</li>
      <li><b>Kein Eingriff:</b> Während der Läufe wurde weder am Systemcode noch im Projekt etwas geändert;
      Beobachtungen (Gegenprobe der Referenzmodelle, Lesen von Logs) liefen in Kopien.</li>
      <li><b>Einstellungen:</b> <code>repair_policy: persistent</code>, zwei parallele HDL-Worker, Zeitlimit
      900 s je OpenCode-Aufruf, Synthese mit Timing-Gate, Flash in SRAM und QSPI. Kein UART, also kein
      automatischer Hardwaretest.</li>
      <li><b>Codestände:</b> Lauf 1 und 2 mit <code>af7d863</code> (vor den Verbesserungen), Kontrolllauf mit
      <code>256a317</code> (Verbesserungen #48–#56; #57 entstand aus diesem Lauf).</li>
    </ul>
    <h2>6 Ergebnisse der drei Läufe</h2>
    {table(["", "Lauf 1", "Lauf 2", "Kontrolllauf"], result_rows, "compact")}
    <h3>6.1 Dauer der Abschnitte</h3>
    <div class="fig">{svg_phases(runs)}</div>
    <p class="caption">Abbildung 3: Dauer der Abschnitte in Minuten. „Fehlerbehandlung“ ist die Zeit zwischen
    Implementierung und Synthese, die nicht auf die Prüfungen selbst entfällt (Diagnose, Reparatur, Neuerzeugung
    des Modells).</p>
    {table(["Abschnitt [min]", "Lauf 1", "Lauf 2", "Kontrolllauf"], phase_rows, "compact")}
    <p>Die Implementierung der zehn Module samt Testbenches dominiert jeden Lauf. Zwischen Lauf 1/2 und dem
    Kontrolllauf sank sie trotz einer zusätzlichen Testbench von 24,5 bzw. 22,0 auf 20,5 Minuten (Abschnitt 8).
    Prüfungen dauern dank GHDL und vorzeitig endender Abschlussprüfung nur 2–3 Minuten, Synthese und Flashen
    zusammen rund 5,5 Minuten.</p>
    <h3>6.2 Ablauf der Implementierung</h3>
    <div class="fig">{svg_gantt(r1, order_r1)}</div>
    <p class="caption">Abbildung 4a: Lauf 1 – paketweise Planung (Minuten ab Beginn der Implementierung,
    rot: kritischer Pfad control_unit → cpu_core → mini_cpu). control_unit startet als viertes Modul, cpu_core
    erst, nachdem das ganze erste Paket fertig ist.</p>
    <div class="fig">{svg_gantt(r3, order)}</div>
    <p class="caption">Abbildung 4b: Kontrolllauf – kritischer Pfad zuerst (#48). control_unit startet sofort,
    cpu_core sobald seine vier Abhängigkeiten fertig sind; die übrigen Blattmodule füllen die freien Worker.</p>
    """)

    sections.append(f"""
    <h2 class="pagebreak">7 Verlauf der einzelnen Läufe</h2>
    <h3>7.1 Lauf 1 (<code>{e(r1["project"])}</code>)</h3>
    <p>Planung im ersten Versuch (2:39 min) mit {r1["requirements"]} Einzelanforderungen. Implementierung,
    statischer Check, Simulation, Mutationsanalyse (Quote {de(r1["mutation_score"])}) und Abschlussprüfung ohne Befund,
    Synthese mit WNS +{de(r1["wns_ns"], 2)} ns, Flash in SRAM und QSPI. Keine Reparatur. Beobachtet wurden die
    Verbesserungspunkte #48–#55 (Planung der Worker, 1,06 MB große <code>task_graph.json</code>, 101 KB großes
    Abschlussereignis, irreführende Auftragsgröße im Log, fehlende Testbench für cpu_core, Reset-Rückfrage
    aus einem Skill, Lücken in der Trajektorie, fehlende Prüfanleitung).</p>
    <h3>7.2 Lauf 2 (<code>{e(r2["project"])}</code>)</h3>
    <p>Wiederholung mit gleichem Codestand: gleiche Dauer (38,0 min), wieder ohne Reparatur. Unterschiede zeigen
    die Streuung des Sprachmodells: {r2["requirements"]} statt {r1["requirements"]} Einzelanforderungen,
    Mutationsquote {de(r2["mutation_score"])} statt {de(r1["mutation_score"])}, cpu_core diesmal als „sequential“
    eingestuft – und trotzdem ohne eigene Testbench, womit die tatsächliche Ursache gefunden war (Regel im
    HDLAgent, #52). Den auf das Board geflashten Entwurf dieses Laufs hat der Benutzer geprüft: die LED-Ausgabe
    stimmt.</p>
    <h3>7.3 Abgebrochener Kontrolllauf</h3>
    <div class="box warn">Ein erster Kontrolllauf mit den Verbesserungen #48–#55 (<code>fibonacci-accu-cpu-588373</code>)
    endete als BLOCKED: Gegen 16:43 lehnte der Anbieter hinter OpenCode Zen beide freien Modelle ab
    (<code>Upstream request failed: Invalid credential</code>, Gegenprobe außerhalb des Systems identisch, Dauer
    rund 1,5 h). Das System stufte den Ausfall als Entwurfsfehler ein und lief 13 Minuten lang die
    Eskalationsleiter hoch; die Planung startete nach dem ersten Ausfall noch vier weitere Module. Außerdem zeigte
    sich ein Folgefehler von #48 (Checkpoint als „Änderung durch OpenCode“). Behoben als #56; der Lauf ist nicht
    in den Kennzahlen enthalten.</div>
    <h3>7.4 Kontrolllauf (<code>{e(r3["project"])}</code>)</h3>
    <p>Planung mit Prüfanleitung (6 Schritte) und ohne offene Fragen; control_unit startete zuerst, cpu_core
    nach 6:18 min und bekam eine eigene Testbench. Der statische Check meldete dann eine Abweichung vom
    Referenzmodell: Bei Takt 27 erwartete das Modell in der PC-Anzeige 0011, der Entwurf zeigte 0010 – der
    ganze Ablauf lag einen Takt zurück. Ursache war <code>tick_gen</code>, das den Tick als Register erzeugte,
    also einen Takt nach dem Zählerstand TICK_CYCLES−1:</p>
    {code(tick_before)}
    <p>Die erste Reparatur fand die Stelle, bewertete sie aber falsch („reference_model … assumes combinational
    tick … DUT correctly shows pc=2“). Nach der Regel aus #40 wurde daraufhin das Referenzmodell mit diesem
    Befund neu erzeugt. Das neue Modell prüfte die Behauptung, wies sie unter Verweis auf den Wortlaut der
    Anforderung zurück und blieb bei der aufgabengetreuen Zeitfolge. Die zweite Reparatur korrigierte daraufhin
    den Entwurf:</p>
    {code(verdict["reason"])}
    {code("tick <= '1' when cnt = TICK_CYCLES - 1 else '0';")}
    <p>Damit hat der Mechanismus „Modellstreit“ einen Entwurfsfehler nicht zum Modellfehler umgedeutet; die Runde
    kostete rund 13 Minuten. Am Board wäre der Fehler unsichtbar gewesen (10 ns), und auch die Referenz-Testbench
    mit ihrem Spielraum hätte ihn nicht erkannt. Danach Mutationsquote {de(r3["mutation_score"])},
    {r3["requirements"]} von {r3["requirements"]} Anforderungen erfüllt, WNS +{de(r3["wns_ns"], 2)} ns, Flash. Die
    Abschlussmeldung enthielt die Prüfanleitung – mit vertauschten Schaltern für ACC und PC in zwei Schritten,
    was zu #57 führte.</p>
    """)

    sections.append(f"""
    <h2 class="pagebreak">8 Befunde und Verbesserungen</h2>
    <p>Die Nummern entsprechen Abschnitt 15.1 in <code>docs/doku.html</code>, wo Anlass, Maßnahme, Dateien und
    Tests ausführlich stehen. Die Wirkung ist im Kontrolllauf gemessen bzw. mit den Dauern aus Lauf 1
    nachgerechnet.</p>
    {table(["#", "Maßnahme", "gemessene Wirkung"], [[n, e(a), e(b)] for n, a, b in FINDINGS], "compact")}
    <p><b>Planung nach dem kritischen Pfad (#48).</b> Mit den gemessenen Dauern aus Lauf 1 ergibt die neue
    Planung 21,2 statt 24,5 Minuten für die Module. Eine rein abhängigkeitsgesteuerte Planung ohne Priorität wäre
    mit 25,4 Minuten sogar langsamer gewesen als die alte paketweise; entscheidend ist die Regel „längste Kette
    zuerst“ (Listenplanung nach Hu 1961, Übersicht Kwok/Ahmad 1999).</p>
    <p><b>Testbench für cpu_core (#52).</b> Zwischenmodule mit eigener Logik bekommen jetzt eine Testbench;
    das kostet einen OpenCode-Aufruf (hier 2:19 min) und hob die Mutationsquote im Kontrolllauf auf 1,0.</p>
    <p><b>Modellstreit.</b> Die Regel aus #40 (Modell einmal neu erzeugen, erst beim zweiten Streit abschalten)
    hat sich bewährt: Das neu erzeugte Modell ist ein Schiedsrichter, der die Aufgabe liest, nicht den Entwurf.</p>


    <h2 class="pagebreak">9 Vergleich mit einem einzelnen OpenCode-Aufruf</h2>
    <p>Am 13.10.2026 wurde dieselbe Aufgabe mit demselben Modell als <b>ein einziger OpenCode-Aufruf</b> gelöst
    (Benchmark-Variante <code>single</code>, Lauf <code>20261013-072705</code>, Zeitlimit 3600 s). Der Auftrag
    lautet sinngemäß: PROMPT.md vollständig umsetzen, eine Testbench für das Top-Level schreiben, selbst mit
    GHDL prüfen und alle Fehler beheben. Synthese und Flash gehören nicht zur Variante; sie wurden danach auf
    einer Kopie mit dem FPGAAgent des MAS ausgeführt (gleiche Werkzeugkette), damit der Entwurf am Board
    geprüft werden kann.</p>
    {table(["", "Single", "MAS (Lauf 1 / 2 / Kontrolllauf)"], [
        ["Dauer bis simulierter Entwurf", "<b>4,6 min</b>, 1 Aufruf", "ca. 30 / 31 / 40 min, 22–24 Aufrufe"],
        ["Dauer bis Board", "<b>ca. 10,5 min</b> (mit Synthese und Flash)", "37,7 / 38,0 / 47,1 min"],
        ["Module (10 vorgegeben)", "10", "10 / 10 / 10"],
        ["Testbenches", "1 (Top-Level)", "9 / 9 / 10"],
        ["Unabhängige Referenz-Testbench", "bestanden", "bestanden (alle drei)"],
        ["Taktgenauer Vergleich mit den drei MAS-Referenzmodellen (je 4 Zufallsfolgen)", "12 von 12 übereinstimmend",
         "Kontrolllauf: Abweichung von einem Takt gefunden und behoben"],
        ["Mutationsquote (Mutationsanalyse des MAS, 10 Mutanten)", "0,7", "0,9 / 0,7 / 1,0"],
        ["Timing (WNS)", "+4,69 ns", "+3,76 / +3,14 / +3,77 ns"],
        ["LUTs / Flipflops", "106 / 149", "95/151, 108/149, 93/151"],
        ["Einzelanforderungen mit Nachweis", "keine", "91 / 74 / 91, unabhängig bewertet"],
    ], "compact")}
    <p><b>Korrektheit:</b> Gleichstand. Der Einzelaufruf schrieb alle zehn Module in rund drei Minuten, die
    Testbench in vier, und der Entwurf ist taktgenau richtig – auch an der Stelle, an der das MAS im
    Kontrolllauf zunächst einen Takt zu spät lag. <b>Aufwand:</b> Single war etwa achtmal schneller und brauchte
    einen statt 22–24 Aufrufe. <b>Nachweise:</b> Hier liegt der Vorteil des MAS. Die einzige Testbench von Single
    ließ drei von zehn Mutanten durch, darunter einen HLT-Befehl ohne Wirkung; das MAS liefert je Modul eine
    Testbench, ein unabhängiges Referenzmodell und eine begründete Bewertung jeder Einzelanforderung.</p>
    <div class="box">Einordnung: Bei dieser sehr genau spezifizierten, eng gekoppelten Aufgabe zeigt sich keine
    Überlegenheit des MAS bei der Lösungsquote; das deckt sich mit Befunden, nach denen Multi-Agenten-Systeme
    bei sequenziellen, gekoppelten Aufgaben eher schaden (Kim, Liu u. a. 2025). Der Mehrwert des MAS liegt in
    Nachweisbarkeit und Robustheit (Prüfungen, Reparatur, Weg bis zur Hardware ohne Zusatzschritte). Ob es
    darüber hinaus mehr leistet, müssen schwächer spezifizierte oder größere Aufgaben und mehrere Wiederholungen
    zeigen; ein Single-Lauf ist eine Stichprobe.</div>

    <h2>10 Grenzen</h2>
    <ul>
      <li>Ob die LEDs am Board stimmen, prüft das System nicht selbst (kein UART); die Prüfanleitung muss ein
      Mensch abarbeiten und ist ein gegengeprüftes Sprachmodell-Urteil (#55, #57).</li>
      <li>Drei Läufe mit einem freien Modell sind keine statistische Aussage; Anforderungszahl, Testgüte und
      Dauer streuen zwischen Läufen.</li>
      <li>Die Referenz-Testbench prüft das feste Demoprogramm über die Ports; Fehler in selten genutzten
      Befehlsvarianten und Abweichungen um einzelne Takte erkennt sie nicht.</li>
      <li>Anbieterausfälle beendet das System mit einer Meldung (#56); es wartet nicht selbst, bis der Anbieter
      wieder erreichbar ist.</li>
      <li>Eine echte 8-Bit-CPU (8-Bit-Datenpfad, größerer Speicher, UART-Testprogramm) steht noch aus.</li>
    </ul>

    <h2>11 Ablage und Reproduktion</h2>
    {table(["Pfad", "Inhalt"], [
        ["<code>Schaltungsagent/benchmark/prompts/04_mini_cpu.md</code>", "Aufgabe"],
        ["<code>Schaltungsagent/benchmark/reference/04_mini_cpu_ref_tb.vhd</code>", "unabhängige Referenz-Testbench"],
        ["<code>docs/benchmark/ergebnisse/20261012-04_mini_cpu/</code>", "results.csv, summary.json, meta.json, HINWEIS.md"],
        ["<code>… /laufN_&lt;projekt&gt;/</code>", "Plan, Quellen, Testbenches, Modell, Berichte, Ereignisse, Log, Trajektorie, Kennzahlen"],
        ["<code>… /pruefgrundlagen/</code>", "Befehlssatzmodell (Python) und eigene Vergleichsumsetzung (VHDL)"],
        ["<code>docs/benchmark/ergebnisse/20261013-072705/</code>", "Vergleichslauf Single: Kennzahlen, Entwurf, Synthese"],
        ["<code>docs/benchmark/tools/aufgabe04_dokumentation.py</code>", "erzeugt dieses Dokument"],
    ], "compact")}
    {code('''# Referenz-Testbench gegen einen gesicherten Entwurf (Beispiel Lauf 1)
cd "$(mktemp -d)"
ghdl -i --std=08 <repo>/docs/benchmark/ergebnisse/20261012-04_mini_cpu/lauf1_*/src/*.vhd \\
     <repo>/Schaltungsagent/benchmark/reference/04_mini_cpu_ref_tb.vhd
ghdl -m --std=08 ref_mini_cpu_tb && ghdl -r --std=08 ref_mini_cpu_tb --stop-time=1ms --assert-level=error''')}
    <h3>Literatur</h3>
    <ul>
      <li>T. C. Hu: Parallel Sequencing and Assembly Line Problems. Operations Research 9(6), 1961, S. 841–848.</li>
      <li>Y.-K. Kwok, I. Ahmad: Static Scheduling Algorithms for Allocating Directed Task Graphs to Multiprocessors.
      ACM Computing Surveys 31(4), 1999, S. 406–471.</li>
      <li>E. T. Barr, M. Harman, P. McMinn, M. Shahbaz, S. Yoo: The Oracle Problem in Software Testing: A Survey.
      IEEE Transactions on Software Engineering 41(5), 2015, S. 507–525.</li>
      <li>Y. Kim, X. Liu u. a. (Google Research): Towards a Science of Scaling Agent Systems. arXiv:2512.08296, 2025.</li>
      <li>J. Pan u. a.: Training Software Engineering Agents and Verifiers with SWE-Gym. arXiv:2412.21139, 2024.</li>
    </ul>
    """)
    return f"""<!doctype html><html lang="de"><head><meta charset="utf-8"><title>Benchmark-Aufgabe 04 – Mini-CPU</title>
    <style>{css}</style></head><body>{"".join(sections)}</body></html>"""


def main():
    runs = load_runs()
    assert len(runs) == 3, f"erwartet drei Läufe, gefunden {len(runs)}"
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "aufgabe04.html"
        page.write_text(build_html(runs), encoding="utf-8")
        subprocess.run(["chromium", "--headless", "--no-sandbox", "--disable-gpu", "--no-pdf-header-footer",
                        f"--print-to-pdf={OUT_PDF}", page.as_uri()], check=True, capture_output=True)
        if len(sys.argv) > 1:
            Path(sys.argv[1]).write_text(page.read_text(encoding="utf-8"), encoding="utf-8")
    print(OUT_PDF)


if __name__ == "__main__":
    main()
