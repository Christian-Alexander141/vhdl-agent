"""Erzeugt docs/Aufgabe05_Ben-Eater-8Bit.pdf aus docs/benchmark/ergebnisse/20261013-05_ben_eater_8bit.

Aufruf (aus dem Repo-Wurzelverzeichnis):
    python3 docs/benchmark/tools/aufgabe05_dokumentation.py
Benötigt Chromium für den PDF-Druck; Layout und Hilfsfunktionen wie bei Aufgabe 04.
"""
import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from aufgabe04_dokumentation import CSS, code, de, e, mmss, schedule, svg_gantt, table  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
RESULTS = REPO / "docs/benchmark/ergebnisse/20261013-05_ben_eater_8bit"
MAS = RESULTS / "mas_ben-eater-8bit-computer-7814fe"
OUT_PDF = REPO / "docs/Aufgabe05_Ben-Eater-8Bit.pdf"

SIGNALS = [
    ("HLT", "Takt anhalten"), ("MI", "MAR := Bus(3..0)"), ("RI", "RAM[MAR] := Bus"), ("RO", "RAM[MAR] auf den Bus"),
    ("IO", "IR(3..0) auf den Bus"), ("II", "IR := Bus"), ("AI", "A := Bus"), ("AO", "A auf den Bus"),
    ("EO", "ALU-Ergebnis auf den Bus"), ("SU", "ALU subtrahiert"), ("BI", "B := Bus"), ("OI", "OUT := Bus"),
    ("CE", "PC := PC + 1"), ("CO", "PC auf den Bus"), ("J", "PC := Bus(3..0)"), ("FI", "Flags := C, Z der ALU"),
]
MICROCODE = [
    ("NOP", "0000", "", "", ""), ("LDA a", "0001", "IO MI", "RO AI", ""), ("ADD a", "0010", "IO MI", "RO BI", "EO AI FI"),
    ("SUB a", "0011", "IO MI", "RO BI", "EO AI SU FI"), ("STA a", "0100", "IO MI", "AO RI", ""),
    ("LDI n", "0101", "IO AI", "", ""), ("JMP t", "0110", "IO J", "", ""), ("JC t", "0111", "IO J, wenn C = 1", "", ""),
    ("JZ t", "1000", "IO J, wenn Z = 1", "", ""), ("OUT", "1110", "AO OI", "", ""), ("HLT", "1111", "HLT", "", ""),
]
PRESETS = [
    ("00", "Fibonacci (Original)", "51 4E 50 E0 2E 4F 1E 4D 1F 4E 1D 70 63 00 00 00",
     "0, 1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, dann Neustart"),
    ("01", "Zählen", "E0 2F 74 60 3F E0 80 64 00 00 00 00 00 00 00 01", "0 … 255, zurück bis 0, wieder hinauf"),
    ("10", "Multiplikation 3 × 5", "1E 3C 76 1D E0 F0 4E 1D 2F 4D 60 00 01 00 03 05", "15, dann HLT"),
    ("11", "Countdown mit NOP", "5A E0 00 3F 86 61 E0 F0 00 00 00 00 00 00 00 01", "10, 9, …, 1, 0, dann HLT"),
]
UART_TESTS = [
    ("fibonacci_halt", "E02E7B4F1E4D1F4E1D6000F000000100", "000101020305080d1522375990", "Fibonacci, HLT beim Überlauf (JC)"),
    ("multiply_7x9", "1E3C761DE0F04E1D2F4D600001000709", "3f", "7 × 9 durch Addition"),
    ("countdown_5", "55E03F8561E0F0000000000000000001", "050403020100", "SUB, JZ"),
    ("borrow_3_minus_5", "533F75E0F051E0F00000000000000005", "fe", "SUB mit Borgen, JC nicht genommen"),
]
MUTANTS = [
    "JC prüft Z statt C", "SUB-Carry invertiert", "6 statt 5 Mikroschritte", "Lader löscht den RAM-Rest nicht",
    "UART-Ausgabe auch im Board-Modus", "HLT wirkt wie NOP", "keine Entprellung", "LED-Halbbytes vertauscht",
    "Länge 17 angenommen", "RI schreibt an Busadresse statt MAR-Adresse", "OUT wartet nicht auf den Sender",
]
COMPARISON = [
    ("Dauer bis simulierter Entwurf", "ca. 40 min", "<b>8,4 min</b>"),
    ("Dauer bis Hardwaretest bestanden", "<b>45:44 min</b> in einem Lauf", "ca. 14,5 min (Synthese, Flash, Test nachgezogen)"),
    ("OpenCode-Aufrufe (Modellzeit)", "27 (57,4 min)", "1 (8,4 min)"),
    ("Reparaturen", "0", "–"),
    ("Module (12 vorgegeben)", "12", "12"),
    ("Testbenches", "12 je Modul + Top", "1 (Top, 444 Zeilen)"),
    ("Referenz-Testbench (neutrale Fassung)", "bestanden", "bestanden"),
    ("Strenge Lesart „Verwerfen ab dem ersten Längenbyte“", "nicht erfüllt", "nicht erfüllt"),
    ("Taktgenauer Vergleich mit dem Referenzmodell", "bestanden (im Lauf)", "4 von 4 Zufallsfolgen"),
    ("Mutationsquote (10 Mutanten)", "0,9", "0,9"),
    ("Hardwaretest am Board (4 UART-Programme)", "<b>4/4, automatisch im Lauf</b>", "4/4"),
    ("Timing (WNS)", "+3,10 ns", "+3,01 ns"),
    ("LUTs / Flipflops", "399 / 508", "428 / 479"),
    ("Einzelanforderungen mit Nachweis", "78, unabhängig bewertet", "keine"),
]


def ts(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def mas_phases() -> dict:
    events = [json.loads(line) for line in (MAS / "events.jsonl").read_text().splitlines()]
    stage = {}
    for ev in events:
        if ev["event_type"] in ("STAGE_STARTED", "STAGE_FINISHED"):
            stage[(ev["event_type"], ev["payload"]["stage"])] = ts(ev["timestamp"])
    first = lambda kind: next(ts(ev["timestamp"]) for ev in events if ev["event_type"] == kind)
    minutes = lambda a, b: (b - a).total_seconds() / 60
    log = (MAS / "server.log").read_text(errors="replace")
    plan = [datetime.strptime(m, "%Y-%m-%d %H:%M:%S") for m in re.findall(
        r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) .*OPENCODE_(?:CALL stage=plan|RESULT \{'stage': 'plan')", log, re.M)]
    return {
        "Planung": (plan[1] - plan[0]).total_seconds() / 60,
        "Referenzmodell": minutes(stage[("STAGE_STARTED", "IMPLEMENTING")], first("REFERENCE_MODEL_CREATED")),
        "Module und Testbenches": minutes(first("REFERENCE_MODEL_CREATED"), first("IMPLEMENTATION_GRAPH_COMPLETED")),
        "Prüfungen": minutes(stage[("STAGE_STARTED", "STATIC_CHECK")], stage[("STAGE_FINISHED", "VALIDATING")]),
        "Synthese": minutes(stage[("STAGE_STARTED", "SYNTHESIZING")], stage[("STAGE_FINISHED", "SYNTHESIZING")]),
        "Flashen": minutes(stage[("STAGE_STARTED", "FPGA_PROGRAMMING")], stage[("STAGE_FINISHED", "FPGA_PROGRAMMING")]),
        "Hardwaretest": minutes(stage[("STAGE_STARTED", "HARDWARE_TESTING")], first("TASK_COMPLETED")),
    }


COLORS = {"Planung": "#8fb3d9", "Referenzmodell": "#b9d7a8", "Module und Testbenches": "#f2c46d",
          "Prüfungen": "#c9a6d9", "Synthese": "#7fc4c0", "Flashen": "#bbbbbb", "Hardwaretest": "#e88b7d"}


def svg_phase_bar(phases: dict) -> str:
    scale, x, parts = 13.0, 0, []
    for name, minutes in phases.items():
        w = max(minutes * scale, 3)
        parts.append(f'<rect x="{x}" y="0" width="{w}" height="24" fill="{COLORS[name]}" stroke="#fff"/>')
        if w > 26:
            parts.append(f'<text x="{x + w / 2}" y="16" text-anchor="middle" font-size="9">{de(minutes)}</text>')
        x += w
    parts.append(f'<text x="{x + 6}" y="16" font-size="10">{de(sum(phases.values()))} min</text>')
    lx = 0
    for name, color in COLORS.items():
        parts.append(f'<rect x="{lx}" y="34" width="11" height="11" fill="{color}"/>'
                     f'<text x="{lx + 15}" y="44" font-size="9.5">{name}</text>')
        lx += 15 + len(name) * 5.2 + 10
    return f'<svg viewBox="0 0 730 52" width="100%" font-family="DejaVu Sans, sans-serif">{"".join(parts)}</svg>'


def svg_architecture() -> str:
    """Bus in der Mitte, Baugruppen links und rechts wie im Original-Aufbau."""
    def box(x, y, w, h, title, sub, fill, side):
        bus_x = 360
        conn = (f'<line x1="{x + w}" y1="{y + h / 2}" x2="{bus_x - 14}" y2="{y + h / 2}" stroke="#555" stroke-width="2"/>'
                if side == "l" else
                f'<line x1="{bus_x + 14}" y1="{y + h / 2}" x2="{x}" y2="{y + h / 2}" stroke="#555" stroke-width="2"/>')
        return (conn + f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="{fill}" stroke="#555"/>'
                f'<text x="{x + w / 2}" y="{y + 18}" text-anchor="middle" font-weight="700" font-size="11.5">{title}</text>'
                f'<text x="{x + w / 2}" y="{y + 33}" text-anchor="middle" font-size="9.5">{sub}</text>')
    parts = ['<rect x="346" y="10" width="28" height="380" fill="#dbe8f6" stroke="#2b4f7c"/>',
             '<text x="360" y="405" text-anchor="middle" font-size="11" font-weight="700">Bus (8 Bit, Multiplexer)</text>']
    left = [("clock_ctrl", "Tick, Einzeltakt, Halt", "#eeeeee"), ("program_counter", "PC, 4 Bit", "#f8d7c4"),
            ("memory", "MAR + RAM 16 × 8, Programme", "#d5ecd4"), ("register8 (IR)", "Befehlsregister", "#f8d7c4"),
            ("control_unit", "T0–T4, Mikrocode, HLT", "#f8d7c4")]
    right = [("register8 (A)", "Akkumulator", "#fde9c8"), ("alu", "Addierer/Subtrahierer, Flags", "#fde9c8"),
             ("register8 (B)", "Operand", "#fde9c8"), ("register8 (OUT)", "Ausgabe, LEDs", "#fde9c8"),
             ("uart_rx · loader · uart_tx", "Programm laden, Bytes senden", "#e4ddf2")]
    for i, (t, s, f) in enumerate(left):
        parts.append(box(70, 20 + i * 75, 210, 48, t, s, f, "l"))
    for i, (t, s, f) in enumerate(right):
        parts.append(box(440, 20 + i * 75, 230, 48, t, s, f, "r"))
    parts.append('<path d="M175,388 L175,410" stroke="#999" stroke-dasharray="3,3"/>')
    return f'<svg viewBox="0 0 740 415" width="100%" font-family="DejaVu Sans, sans-serif">{"".join(parts)}</svg>'


def build_html() -> str:
    phases = mas_phases()
    log = (MAS / "server.log").read_text(errors="replace")
    sched_run = {"schedule": schedule({"log": log})}
    order = sorted(sched_run["schedule"], key=lambda n: sched_run["schedule"][n][0])
    manifest = json.loads((MAS / "plan/manifest.json").read_text())
    loader_excerpt = "\n".join(
        line for line in (MAS / "src/loader.vhd").read_text().splitlines()
        if "len_cnt = 3" in line or "len_b1 = ZERO_BYTE" in line or "unsigned(len_b0) >= " in line
        or "unsigned(len_b0) <= " in line)
    sections = []
    sections.append(f"""
    <div class="title">
      <h1>Benchmark-Aufgabe 05<br>Ben-Eater-8-Bit-Rechner</h1>
      <div class="subtitle">Originalgetreuer Nachbau des 8-Bit-Breadboard-Computers mit UART-Lader – Aufgabe,
      Prüfgrundlagen, Vorbereitung der Hardwarestrecke und Vergleich MAS gegen einen einzelnen OpenCode-Aufruf</div>
      <table class="meta">
        <tr><td><b>Stand</b></td><td>13.10.2026</td></tr>
        <tr><td><b>Aufgabe</b></td><td><code>Schaltungsagent/benchmark/prompts/05_ben_eater_8bit.md</code></td></tr>
        <tr><td><b>Referenz-Testbench</b></td><td><code>Schaltungsagent/benchmark/reference/05_ben_eater_8bit_ref_tb.vhd</code></td></tr>
        <tr><td><b>Ergebnisse</b></td><td><code>docs/benchmark/ergebnisse/20261013-05_ben_eater_8bit/</code></td></tr>
        <tr><td><b>Modell</b></td><td>opencode/muse-spark-1.3-contributor-free (beide Varianten)</td></tr>
        <tr><td><b>Zielhardware</b></td><td>Digilent Arty S7-50, Vivado 2026.1, USB-UART 115 200 Baud</td></tr>
      </table>
      <div class="box"><b>Ergebnis in Kürze.</b> Das MAS setzte den Rechner mit zwölf Modulen ohne Reparatur
      um und bestand als erster Lauf des Projekts einen <b>automatischen Hardwaretest am Board</b>: vier
      Programme wurden über die UART in den geflashten Rechner geladen, alle Antworten stimmten
      (45:44 min). Ein einzelner OpenCode-Aufruf mit demselben Modell löste die Aufgabe in
      8,4 Minuten ebenso korrekt. Vor den Läufen deckte die Vorbereitung drei Fehler der Hardwarestrecke auf
      (#58–#60), ohne deren Behebung kein Hardwaretest möglich gewesen wäre.</div>
      <h3>Inhalt</h3>
      <ol class="toc"><li>Ziel und Einordnung</li><li>Aufgabenstellung</li><li>Programme und erwartetes Verhalten</li>
      <li>Prüfgrundlagen</li><li>Vorbereitung der Hardwarestrecke</li><li>Versuchsaufbau</li>
      <li>Ergebnisse</li><li>Unschärfe beim Verwerfen von Laderahmen</li><li>Einordnung</li>
      <li>Grenzen</li><li>Ablage und Reproduktion</li></ol>
    </div>""")

    sections.append(f"""
    <h2 class="pagebreak">1 Ziel und Einordnung</h2>
    <p>Aufgabe 04 (4-Bit-Akkumulator-CPU) zeigte, dass das MAS eine kleine, frei spezifizierte CPU bis aufs Board
    bringt. Aufgabe 05 ist der nächste Schritt: ein <b>bereits existierendes, gut dokumentiertes System</b>, damit die
    Entwurfsqualität an einem Original gemessen werden kann. Gewählt wurde der 8-Bit-Breadboard-Computer von Ben
    Eater, eine weit verbreitete Umsetzung der SAP-1-Architektur aus Malvino/Brown. Er hat einen gemeinsamen
    8-Bit-Bus, Register A und B, eine ALU mit Carry- und Zero-Flag, 16 Byte RAM, ein Befehlsregister, einen
    Befehlszähler, ein Ausgaberegister und ein mikroprogrammiertes Steuerwerk mit 16 Steuersignalen und fünf
    Mikroschritten je Befehl.</p>
    <p>Vorgegeben wurde die Endversion mit Flags-Register und bedingten Sprüngen, <b>originalgetreu</b>: Architektur,
    Steuersignale und Mikroprogramm folgen Ben Eaters veröffentlichtem Mikrocode (<code>microcode-eeprom-with-flags</code>).
    Weil das Repository keine Lizenz angibt, beschreibt die Aufgabe die Tabelle mit eigenen Worten und Quellenangabe,
    ohne Code zu übernehmen. Angepasst wurde nur, was auf dem FPGA anders sein muss: Takterzeugung, Programmierung,
    Anzeige. Programme lassen sich zusätzlich über die USB-UART laden – im Protokoll des Hardwaretests des Systems,
    damit erstmals ein <b>automatischer Hardwaretest</b> möglich ist.</p>

    <h2>2 Aufgabenstellung</h2>
    <h3>2.1 Architektur</h3>
    <div class="fig">{svg_architecture()}</div>
    <p class="caption">Abbildung 1: Baugruppen und Bus wie im Original-Aufbau (links Steuer- und Speicherseite, rechts
    Rechenwerk und Ausgabe), mit den Modulnamen der Aufgabe. Den Bus treibt genau die im Steuerwort aktive Quelle
    (CO, RO, IO, AO, EO), sonst ist er 0.</p>
    <h3>2.2 Steuersignale und Mikroprogramm</h3>
    {table(["Signal", "Wirkung", "Signal", "Wirkung"], [[f"<code>{a}</code>", e(b), f"<code>{c}</code>", e(d)] for (a, b), (c, d) in zip(SIGNALS[:8], SIGNALS[8:])], "compact")}
    <p>Alle Befehle holen in T0 mit <code>MI CO</code> und in T1 mit <code>RO II CE</code>; danach:</p>
    {table(["Befehl", "Opcode", "T2", "T3", "T4"], [[f"<code>{a}</code>", f"<code>{b}</code>", e(c), e(d), e(f)] for a, b, c, d, f in MICROCODE], "compact")}
    <p>Opcodes 1001–1101 wirken wie NOP. Ein Mikroschritt wird mit der Taktflanke ausgeführt, an der die
    Schrittfreigabe aktiv ist; alle Register übernehmen gleichzeitig, Bus und ALU arbeiten mit den Werten vor der
    Flanke. Nach T4 folgt T0. HLT ändert kein Register und hält die CPU bis zum Reset oder bis ein Programm über die
    UART geladen wird. Die ALU addiert bzw. bildet A + (not B) + 1; das Carry ist der Übertrag aus Bit 7 (bei SUB also
    „kein Borgen“), Zero zeigt ein Ergebnis von 0.</p>
    """)

    sections.append(f"""
    <h3>2.3 Schnittstelle, Takt und UART</h3>
    {table(["Port / Generic", "Board", "Bedeutung"], [
        ["clk", "R2, 100 MHz", "Systemtakt"], ["rst", "BTN0", "synchroner Reset; lädt das mit SW3/SW2 gewählte Programm"],
        ["btn_step", "BTN1", "Einzeltakt: ein Mikroschritt je Druck (entprellt)"],
        ["sw(0)", "SW0", "LED-Anzeige: unteres bzw. oberes Halbbyte von OUT"],
        ["sw(1)", "SW1", "Takt: automatisch (TICK_CYCLES, Standard 25 Mikroschritte/s) oder Einzeltakt"],
        ["sw(3 downto 2)", "SW3, SW2", "festes Programm beim Reset"], ["led(3 downto 0)", "LD5 … LD2", "Halbbyte von OUT"],
        ["uart_rx / uart_tx", "V12 / R12", "USB-UART 8N1, CLKS_PER_BIT (Standard 868 = 115 200 Baud)"],
    ], "compact")}
    <p><b>Ladeprotokoll</b> (wie der Hardwaretest des Systems sendet): 4 Bytes Länge n (little endian, 1..16),
    n Programmbytes, dann „START“ und Zeilenvorschub. Danach steht das Programm im RAM (Rest 0), alle Register sind 0,
    und die CPU läuft im <b>UART-Modus</b> mit einem Mikroschritt je Takt; jedes OUT sendet den Wert als Byte zurück
    (ein OUT wartet, bis der Sender frei ist). Im Board-Modus sendet die CPU nichts. Der UART-Modus endet nur mit dem
    Reset; ein neuer Rahmen hält die CPU an, bis er vollständig ist.</p>
    <h3>2.4 Module</h3>
    <p>Zwölf Entities, je eine Datei: <code>input_sync</code>, <code>debouncer</code>, <code>clock_ctrl</code>,
    <code>program_counter</code>, <code>register8</code> (A, B, OUT, IR), <code>alu</code> (mit Flags),
    <code>memory</code> (MAR, RAM, feste Programme), <code>control_unit</code> (Mikroschrittzähler, Mikrocode, Halt),
    <code>uart_rx</code>, <code>uart_tx</code>, <code>loader</code> und das Top-Level <code>ben_eater_cpu</code> mit dem
    Bus-Multiplexer. Gefordert ist eine Top-Testbench mit kleinen Generics (TICK_CYCLES = 2, DEBOUNCE_CYCLES = 2,
    CLKS_PER_BIT = 8).</p>

    <h2 class="pagebreak">3 Programme und erwartetes Verhalten</h2>
    <p>Alle Programme wurden vorab mit einem Python-Modell auf Mikroschritt-Ebene ausgeführt
    (<code>05_pruefgrundlagen/mikroschritt_modell.py</code>). Zusammen nutzen sie alle elf Befehle.</p>
    {table(["SW3/SW2", "Programm", "RAM 0–15 (hex)", "OUT"], [[a, e(b), f"<code>{c}</code>", e(d)] for a, b, c, d in PRESETS], "compact")}
    <p>Vier Programme dienen als Hardwaretest über die UART (Antwort = alle OUT-Werte in Reihenfolge):</p>
    {table(["Test", "Programm (hex)", "Antwort (hex)", "prüft"], [[f"<code>{a}</code>", f"<code>{b}</code>", f"<code>{c}</code>", e(d)] for a, b, c, d in UART_TESTS], "compact")}

    <h2>4 Prüfgrundlagen</h2>
    <ul>
      <li><b>Mikroschritt-Modell</b> (Python) nach der Original-Tabelle; erzeugt die erwarteten Folgen.</li>
      <li><b>Eigene Umsetzung</b> (eine Entity, <code>eigene_umsetzung_ben_eater_cpu.vhd</code>) als Gegenprobe der
      Aufgabe, der Referenz-Testbench und der Hardwarestrecke.</li>
      <li><b>Referenz-Testbench</b> (dem System unbekannt): Programme „10“ und „11“ an den LEDs, Einzeltakt
      (genau ein Mikroschritt je Druck, kein Schritt durch einen 1-Takt-Impuls), die vier UART-Tests, Verwerfen einer
      ungültigen Länge, Löschen des RAM-Rests, keine UART-Ausgabe im Board-Modus, Rückkehr in den Board-Modus.
      Sie erkennt alle elf absichtlich eingebauten Fehler:</li>
    </ul>
    {table(["eingebauter Fehler", "erkannt"], [[e(m), "ja"] for m in MUTANTS], "compact")}
    """)

    sections.append(f"""
    <h2 class="pagebreak">5 Vorbereitung der Hardwarestrecke</h2>
    <p>Für den automatischen Hardwaretest musste die Kette PC → USB-UART → FPGA → zurück zum ersten Mal wirklich
    funktionieren. Der Abgleich mit der offiziellen Digilent-Master-XDC des Arty S7-50 und ein Probelauf deckten drei
    Fehler im System auf, die vorher nie aufgefallen waren, weil noch kein Lauf eine UART hatte:</p>
    {table(["#", "Befund", "Maßnahme"], [
        ["58", "UART-Richtungen im Board-Wissen und im Skill vertauscht (Eingang ist V12, Ausgang R12); der XDC-Generator kannte keine UART-Pins (uart_rx ohne Pin → Vivado-Abbruch); Pmod-Listen mit Taster-, RGB- und Analog-Pins.",
         "Wissen, Skill und Generator nach der Master-XDC korrigiert"],
        ["59", "Das System hätte seine eigene UART-Echo-Brücke in jeden Entwurf mit eigener UART eingebaut.",
         "keine Brücke, wenn das Top-Level selbst UART-Ports hat"],
        ["60", "pyserial war keine Abhängigkeit und nicht installiert; der UART-Port war nicht gesetzt – der Hardwaretest konnte nie laufen.",
         "Abhängigkeit, Konfiguration; Probelauf mit der eigenen Umsetzung: 4/4 am Board"],
    ], "compact")}

    <h2>6 Versuchsaufbau</h2>
    <ul>
      <li><b>MAS:</b> Server wie mit <code>start.py</code>, Aufgabe über <code>POST /api/chat</code> wie aus dem
      Dashboard, ohne Eingriff bis zum Ende einschließlich Flash und Hardwaretest (Stand <code>6f7f985</code>).</li>
      <li><b>Single:</b> ein OpenCode-Aufruf über den Benchmark (<code>--variants single --opencode-timeout 3600</code>);
      Synthese, Flash und derselbe Hardwaretest danach mit dem FPGAAgent und dem HardwareTestAgent des Systems.</li>
      <li>Beide mit demselben Modell; je ein Lauf.</li>
    </ul>

    <h2>7 Ergebnisse</h2>
    {table(["", "MAS", "Single"], [[f"<b>{e(a)}</b>", b, c] for a, b, c in COMPARISON], "compact")}
    <h3>7.1 Ablauf des MAS-Laufs</h3>
    <div class="fig">{svg_phase_bar(phases)}</div>
    <p class="caption">Abbildung 2: Abschnitte des MAS-Laufs in Minuten. Der Plan enthielt alle zwölf Module,
    {len(manifest.get("requirements", []))} Einzelanforderungen, die vier Hardwaretests und eine Prüfanleitung; die
    UART-Brücke des Systems wurde übersprungen (#59).</p>
    """)

    sections.append(f"""
    <h3>7.2 Implementierung der Module</h3>
    <div class="fig">{svg_gantt(sched_run, order, scale=21.0)}</div>
    <p class="caption">Abbildung 3: Modul und Testbench je Modul (Minuten ab Beginn der Implementierung, zwei
    Worker). Rot: das Steuerwerk <code>control_unit</code>. Alle Module außer dem Top-Level sind voneinander
    unabhängig; die Reihenfolge folgt deshalb der Portzahl (#48), das Top-Level startet, sobald die übrigen elf
    fertig sind. Am längsten brauchte der Lader.</p>

    <h2>8 Unschärfe beim Verwerfen von Laderahmen</h2>
    <p>Die Aufgabe sagt: „Weicht ein Byte ab (Länge außerhalb 1..16, falsches Zeichen in START), wird der Rahmen
    verworfen und das nächste Byte wieder als erstes Längenbyte gelesen.“ Gemeint war eine byteweise Prüfung schon
    des ersten Längenbytes. <b>Beide</b> Entwürfe prüfen die Länge als 4-Byte-Wert erst nach dem vierten Byte:</p>
    {code(loader_excerpt)}
    <p>Die ursprüngliche Referenz-Testbench sendete nur das Byte <code>0x11</code>; danach ging der folgende Rahmen bei
    beiden Entwürfen verloren. Da der Wortlaut beide Lesarten zulässt, wurde die Testbench vor der Auswertung von
    Single neutral gefasst: Sie sendet den vollständigen ungültigen Längenwert <code>11 00 00 00</code>, den beide
    Lesarten verwerfen müssen. Alle elf Fehlervarianten werden weiterhin erkannt. Bemerkenswert: Die unabhängige
    Abschlussprüfung des MAS bewertete die Anforderung als erfüllt, die MAS-Testbench prüfte genau den vollständigen
    4-Byte-Fall – das System war in sich konsistent, die Aufgabe nicht eindeutig. Lehre für künftige Aufgaben:
    Fehlerverhalten von Protokollen mit einem Beispiel festlegen.</p>

    <h2>9 Einordnung</h2>
    <p><b>Korrektheit:</b> Gleichstand, wie schon bei Aufgabe 04. Beide Entwürfe bestehen die Referenz-Testbench, den
    taktgenauen Modellvergleich und den Hardwaretest am Board; beide erreichen eine Mutationsquote von 0,9 und
    erfüllen das Timing mit ähnlichem Ressourcenbedarf (eigene Umsetzung zum Vergleich: 390 LUTs / 434 Flipflops,
    WNS +3,09 ns). <b>Aufwand:</b> Single war etwa fünfmal schneller bis zum simulierten Entwurf und brauchte ein
    Siebtel der Modellzeit. <b>Mehrwert des MAS:</b> der vollständige Weg bis zum bestandenen Hardwaretest in einem
    Lauf ohne Zusatzschritte, eine Testbench je Modul (Single: eine, wenn auch umfangreiche) und eine begründete
    Bewertung jeder Einzelanforderung.</p>
    <div class="box">Über beide Aufgaben hinweg: Bei genau spezifizierten Aufgaben mit vorgegebener Modulstruktur
    löst ein einzelner Aufruf dieses Modells die Aufgabe ebenso korrekt und deutlich schneller. Das MAS gewinnt
    nicht bei der Lösungsquote, sondern bei Nachweisbarkeit und Durchgängigkeit. Ob es bei unschärfer spezifizierten
    oder größeren Aufgaben mehr leistet, ist offen; ein Lauf je Variante ist eine Stichprobe.</div>

    <h2>10 Grenzen</h2>
    <ul>
      <li>Je ein Lauf je Variante; Ergebnisse freier Modelle streuen zwischen Läufen.</li>
      <li>Der Hardwaretest prüft nur gültige Rahmen und vier Programme; Fehlerverhalten des Laders und der
      Einzeltakt am Board sind nur in der Simulation geprüft.</li>
      <li>Die Single-Variante endet im Benchmark nach der Simulation; Synthese, Flash und Hardwaretest wurden mit den
      Werkzeugen des Systems nachgezogen.</li>
      <li>Die Aufgabe war beim Verwerfen von Laderahmen nicht eindeutig (Abschnitt 8).</li>
    </ul>

    <h2>11 Ablage und Reproduktion</h2>
    {table(["Pfad", "Inhalt"], [
        ["<code>Schaltungsagent/benchmark/prompts/05_ben_eater_8bit.md</code>", "Aufgabe"],
        ["<code>Schaltungsagent/benchmark/reference/05_ben_eater_8bit_ref_tb.vhd</code>", "Referenz-Testbench"],
        ["<code>Schaltungsagent/benchmark/reference/05_pruefgrundlagen/</code>", "Mikroschritt-Modell, eigene Umsetzung, Gegenprobe"],
        ["<code>docs/benchmark/ergebnisse/20261013-05_ben_eater_8bit/</code>", "MAS- und Single-Entwurf, Berichte, Ereignisse, Log, Trajektorie, Vergleich"],
        ["<code>docs/benchmark/ergebnisse/20261013-111444/</code>", "Benchmark-Kennzahlen des Single-Laufs"],
        ["<code>docs/benchmark/tools/aufgabe05_dokumentation.py</code>", "erzeugt dieses Dokument"],
    ], "compact")}
    <h3>Literatur und Quellen</h3>
    <ul>
      <li>B. Eater: Build an 8-bit computer from scratch (Video-Reihe und Unterlagen), eater.net/8bit; Mikrocode:
      github.com/beneater/eeprom-programmer, <code>microcode-eeprom-with-flags</code>.</li>
      <li>A. P. Malvino, J. A. Brown: Digital Computer Electronics, 3. Aufl., Glencoe/McGraw-Hill, 1993 (SAP-1).</li>
      <li>Digilent: Arty-S7-50-Master.xdc, github.com/Digilent/digilent-xdc.</li>
      <li>Y. Kim, X. Liu u. a. (Google Research): Towards a Science of Scaling Agent Systems. arXiv:2512.08296, 2025.</li>
    </ul>
    """)
    return f"""<!doctype html><html lang="de"><head><meta charset="utf-8"><title>Benchmark-Aufgabe 05 – Ben-Eater-Rechner</title>
    <style>{CSS}</style></head><body>{"".join(sections)}</body></html>"""


def main():
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "aufgabe05.html"
        page.write_text(build_html(), encoding="utf-8")
        subprocess.run(["chromium", "--headless", "--no-sandbox", "--disable-gpu", "--no-pdf-header-footer",
                        f"--print-to-pdf={OUT_PDF}", page.as_uri()], check=True, capture_output=True)
    print(OUT_PDF)


if __name__ == "__main__":
    main()
