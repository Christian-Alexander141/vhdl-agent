"""Erzeugt docs/architecture/MAS-Ablauf.drawio (zwei Seiten)."""
from xml.sax.saxutils import escape
import sys

C = {  # Farbe je Zuständigkeit: (Füllung, Rahmen)
    "user": ("#f5f5f5", "#666666"),
    "sup": ("#dae8fc", "#6c8ebf"),
    "plan": ("#e1d5e7", "#9673a6"),
    "ver": ("#d5e8d4", "#82b366"),
    "hdl": ("#fff2cc", "#d6b656"),
    "fpga": ("#ffe6cc", "#d79b00"),
    "err": ("#f8cecc", "#b85450"),
    "ok": ("#d5e8d4", "#2d7600"),
    "note": ("#ffffff", "#999999"),
}


class Page:
    def __init__(self, name, pid):
        self.name, self.pid, self.cells, self.n = name, pid, [], 0

    def _id(self):
        self.n += 1
        return f"{self.pid}{self.n}"

    def box(self, x, y, w, h, title, sub="", kind="sup", shape="rounded", size=13):
        fill, stroke = C[kind]
        label = f"<b>{title}</b>" + (f"<br><font style='font-size:{size-2}px'>{sub}</font>" if sub else "")
        styles = {
            "rounded": "rounded=1;arcSize=12;",
            "diamond": "rhombus;",
            "ellipse": "ellipse;",
            "stadium": "rounded=1;arcSize=50;",
            "note": "shape=note;size=14;",
        }
        style = (styles[shape] + f"whiteSpace=wrap;html=1;fillColor={fill};strokeColor={stroke};"
                 f"fontSize={size};strokeWidth=2;shadow=1;spacing=6;")
        cid = self._id()
        self.cells.append(
            f'<mxCell id="{cid}" value="{escape(label, {chr(34): "&quot;"})}" style="{style}" vertex="1" parent="1">'
            f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')
        return cid

    def text(self, x, y, w, h, html, size=12, align="left", border=None, fill="none"):
        cid = self._id()
        style = (f"text;html=1;whiteSpace=wrap;align={align};verticalAlign=top;fontSize={size};"
                 f"fillColor={fill};" + (f"strokeColor={border};rounded=1;" if border else "strokeColor=none;"))
        self.cells.append(
            f'<mxCell id="{cid}" value="{escape(html, {chr(34): "&quot;"})}" style="{style}" vertex="1" parent="1">'
            f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')
        return cid

    def group(self, x, y, w, h, title, color):
        cid = self._id()
        style = (f"rounded=1;arcSize=3;html=1;whiteSpace=wrap;fillColor={color};strokeColor=#bbbbbb;dashed=1;"
                 "verticalAlign=top;align=left;spacingLeft=10;spacingTop=4;fontSize=15;fontStyle=1;fontColor=#555555;")
        self.cells.insert(0,
            f'<mxCell id="{cid}" value="{escape(title)}" style="{style}" vertex="1" parent="1">'
            f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')
        return cid

    def edge(self, a, b, label="", kind="flow", ex=None, ey=None, nx=None, ny=None, points=()):
        style = "edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;endArrow=block;endFill=1;fontSize=11;labelBackgroundColor=#ffffff;"
        style += {"flow": "strokeColor=#444444;strokeWidth=2;",
                  "err": "strokeColor=#b85450;strokeWidth=2;dashed=1;",
                  "back": "strokeColor=#2d7600;strokeWidth=2;dashed=1;",
                  "loop": "strokeColor=#9673a6;strokeWidth=2;dashed=1;"}[kind]
        for key, val in (("exitX", ex), ("exitY", ey), ("entryX", nx), ("entryY", ny)):
            if val is not None:
                style += f"{key}={val};"
        pts = "".join(f'<mxPoint x="{x}" y="{y}"/>' for x, y in points)
        geo = f'<mxGeometry relative="1" as="geometry">{f"<Array as=\"points\">{pts}</Array>" if pts else ""}</mxGeometry>'
        cid = self._id()
        self.cells.append(
            f'<mxCell id="{cid}" value="{escape(label)}" style="{style}" edge="1" parent="1" source="{a}" target="{b}">{geo}</mxCell>')
        return cid

    def xml(self, w, h):
        return (f'<diagram id="{self.pid}" name="{escape(self.name)}"><mxGraphModel dx="1400" dy="900" grid="1" gridSize="10" '
                f'guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="{w}" '
                f'pageHeight="{h}" background="#ffffff" math="0" shadow="0"><root><mxCell id="0"/><mxCell id="1" parent="0"/>'
                + "".join(self.cells) + "</root></mxGraphModel></diagram>")


# ---------------------------------------------------------------- Seite 1
p = Page("1 Gesamtablauf", "a")
W = 270
p.text(40, 10, 1100, 40, "<b style='font-size:22px'>VHDL-Multiagentensystem – Gesamtablauf eines Laufs</b>"
       "<br>Modus <i>persistent</i> (echte Läufe) · Stand 2026-10-12", size=13)
p.group(20, 70, 320, 520, "① Dashboard", "#fafafa")
p.group(360, 70, 330, 520, "② Planung (Bootstrap)", "#f7f2fa")
p.group(710, 70, 330, 1400, "③ Pipeline des SupervisorAgent", "#f4f8fd")
p.group(1060, 70, 360, 1400, "④ Fehlerbehandlung & Ergebnis", "#fdf5f5")

u1 = p.box(55, 110, W, 60, "💬 Anforderung", "Benutzer schreibt im Dashboard", "user", "stadium")
u2 = p.box(55, 200, W, 100, "🔀 ChatRouter", "Art der Nachricht?", "user", "diamond")
u3 = p.box(40, 350, 140, 90, "❓ Frage", "OpenCodeProjectChat antwortet im Projekt", "user")
u4 = p.box(195, 350, 140, 90, "✏️ Änderung", "Plan mit Änderungswunsch", "user")
p.edge(u1, u2)
p.edge(u2, u3, "Frage", ex=0.25, ey=0.9, nx=0.5, ny=0)
p.edge(u2, u4, "Änderung", ex=0.75, ey=0.9, nx=0.5, ny=0)

p1 = p.box(390, 105, W, 100, "🧭 Plan erstellen (OpenCode)", "Manifest · Projektname · Einzelanforderungen R1–Rn · Reset-Konzept", "plan")
p2 = p.box(390, 230, W, 110, "✔️ Plan gültig?", "Zyklen, Ports, Zitate aus PROMPT.md", "plan", "diamond")
p4 = p.box(390, 400, W, 110, "📁 Workspace anlegen", "PROMPT.md · Skills · Board-Daten<br>eigenes Git-Repo · OpenCode-Sperre", "plan")
p.edge(u2, p1, "neues Projekt", ex=1, ey=0.5, nx=0, ny=0.5)
p.edge(p1, p2)
p.edge(p2, p1, "nein:<br>Korrektur<br>(≤ 3×)", "loop", ex=1, ey=0.5, nx=1, ny=0.5, points=[(685, 285), (685, 155)])
p.edge(p2, p4, "ja")
p.edge(u4, p1, "", "flow", ex=0.5, ey=1, nx=0, ny=0.75, points=[(265, 470), (350, 470), (350, 177)])
p.text(390, 520, W, 60, "ℹ️ Nur Anforderungsliste unvollständig? → Sammelanforderung <b>R0</b> statt Abbruch", 11, border="#cccccc", fill="#ffffff")

X = 740
stages = [
    ("🔎 Analyse", "Ziel-FPGA · Toolchain-Warnung", "sup", 60),
    ("🏗️ Architektur", "Module, Ports, Contracts · plan/requirements.md", "plan", 60),
    ("📡 UART-Integration", "nur wenn nötig", "sup", 50),
    ("🐍 Referenzmodell", "Python-Modell aus PROMPT.md · GENERICS", "ver", 60),
    ("⚙️ Implementierung", "TaskGraph · Module + Testbenches parallel (HDLAgent)", "hdl", 70),
    ("🧪 Statischer Check", "Port-Contracts · Vergleich mit Referenzmodell (generic map) · GHDL", "ver", 70),
    ("📈 Simulation", "alle Testbenches mit GHDL", "ver", 55),
    ("✅ Validierung", "Abdeckung · REQ-Gate · Mutationsanalyse · Abschlussprüfung der Anforderungen", "ver", 85),
    ("🧩 Synthese", "Cache · GHDL-Synthese des Top-Levels · Vivado (VHDL-2008, XDC, Board-Config) · Timing", "fpga", 85),
    ("⚡ FPGA flashen", "JTAG + QSPI-Flash · ohne Freigabe", "fpga", 60),
]
y, ids = 110, []
for title, sub, kind, h in stages:
    ids.append(p.box(X, y, W, h, title, sub, kind))
    y += h + 30
for a, b in zip(ids, ids[1:]):
    p.edge(a, b)
p.edge(p4, ids[0], "", ex=1, ey=0.5, nx=0, ny=0.5, points=[(705, 455), (705, 140)])
hw = p.box(X, y, W, 90, "🔌 UART-Hardware vorhanden?", "", "fpga", "diamond")
p.edge(ids[-1], hw)
ht = p.box(X, y + 130, W, 55, "🧷 Hardwaretest", "Testvektoren über UART", "fpga")
done = p.box(X, y + 230, W, 60, "🏁 Abgeschlossen", "Abschlussmeldung im Dashboard", "ok", "stadium")
p.edge(hw, ht, "ja")
p.edge(ht, done)
p.edge(hw, done, "nein", ex=0, ey=0.5, nx=0, ny=0.5, points=[(720, y + 45), (720, y + 260)])

err = p.box(1090, 560, 300, 130, "🚑 Fehlerbehandlung", "Vorfilter · Eskalation · Reparatur<br><i>Details: Seite 2</i>", "err")
for sid in ids[4:]:
    p.edge(sid, err, "", "err", ex=1, ey=0.5, nx=0, ny=0.5)
p.edge(ht, err, "", "err", ex=1, ey=0.5, nx=0, ny=0.5)
p.edge(err, ids[5], "Reparatur erfolgreich →<br>erneut prüfen", "back", ex=0.5, ey=0, nx=1, ny=0.25, points=[(1240, 665 - 145)])
blk = p.box(1090, 780, 300, 90, "⛔ Eingriff erforderlich", "Leiter erschöpft oder Werkzeug/Board fehlt · mit letztem Befund der Agenten", "err", "stadium")
p.edge(err, blk, "", "err")

p.text(1090, 105, 300, 30, "<b style='font-size:15px'>Legende</b>", 13)
items = [("sup", "SupervisorAgent"), ("plan", "Planung / ArchitectureAgent"), ("ver", "VerificationAgent / Prüfungen"),
         ("hdl", "HDLAgent"), ("fpga", "FPGAAgent / Hardware"), ("err", "DebugAgent / Fehler")]
for i, (kind, label) in enumerate(items):
    yy = 140 + i * 28
    fill, stroke = C[kind]
    cid = p._id()
    p.cells.append(f'<mxCell id="{cid}" value="" style="rounded=1;fillColor={fill};strokeColor={stroke};strokeWidth=2;" vertex="1" parent="1"><mxGeometry x="1095" y="{yy}" width="34" height="20" as="geometry"/></mxCell>')
    p.text(1137, yy - 1, 250, 22, label, 12)
p.text(1090, 315, 300, 120,
       "━━ Ablauf<br><font color='#b85450'>╍╍ Fehler → Fehlerbehandlung</font><br>"
       "<font color='#2d7600'>╍╍ nach Reparatur erneut prüfen</font><br><font color='#9673a6'>╍╍ Korrekturschleife</font><br><br>"
       "<b>Werkzeuge:</b> 🤖 OpenCode · 🔧 GHDL · 🏭 Vivado · 🎛️ Arty S7-50", 12)
page1 = p.xml(1450, 1550)

# ---------------------------------------------------------------- Seite 2
q = Page("2 Fehlerbehandlung", "b")
q.text(40, 10, 1300, 40, "<b style='font-size:22px'>Fehlerbehandlung: Vorfilter → Weitergabe → Eskalation</b>"
       "<br>jeder Fehler einer Phase durchläuft diesen Ablauf", size=13)
q.group(330, 70, 360, 1340, "Hauptweg", "#fdf5f5")
q.group(720, 70, 340, 1340, "Sonderwege", "#fafafa")
X, W = 360, 300
e1 = q.box(X, 100, W, 55, "❌ Phase meldet FAILED", "", "err", "stadium")
e2 = q.box(X, 185, W, 110, "↩️ Frühere Phase gebrochen?", "durch die letzte Reparatur", "err", "diamond")
e3 = q.box(X, 330, W, 60, "🗜️ Diagnose kompakt speichern", "Kernzeilen statt Quelltext", "sup")
e4 = q.box(X, 420, W, 85, "🔬 Vorfilter (DebugAgent)", "Kernzeilen aus GHDL/Vivado · Fehlerklasse · Herkunft · Module nur über Dateiverweise", "err")
e5 = q.box(X, 535, W, 60, "🧭 Zuständige Rolle", "route_repair()", "sup")
e6 = q.box(X, 625, W, 75, "🪜 Eskalation", "Stufe je Herkunft · bisherige Versuche + Ergebnis", "sup")
e7 = q.box(X, 730, W, 95, "👤 Ziel = Mensch?", "", "sup", "diamond")
e8 = q.box(X, 860, W, 110, "🛠️ Reparatur ausführen",
           "Neubau Bitstream · Modul neu · Plan überarbeiten · Testbench überarbeiten · fix_hdl (Anforderungen als Invariante)", "hdl")
e9 = q.box(X, 1000, W, 70, "📝 Befund lesen", "reports/repair_verdict.json · Zeitlimit: halbe Änderungen verwerfen", "sup")
e10 = q.box(X, 1100, W, 120, "⚖️ Modellstreit?", "Befund: Modell/Prüfung falsch, src/ unverändert", "ver", "diamond")
e11 = q.box(X, 1260, W, 95, "📂 Dateien geändert?", "", "sup", "diamond")
for a, b in [(e1, e2), (e3, e4), (e4, e5), (e5, e6), (e6, e7), (e8, e9), (e9, e10)]:
    q.edge(a, b)
q.edge(e2, e3, "nein")
q.edge(e7, e8, "nein")
q.edge(e10, e11, "nein")

r1 = q.box(750, 210, 280, 60, "⏪ Reparatur zurücknehmen", "src/ und tests/ wiederherstellen", "err")
r2 = q.box(750, 745, 280, 70, "⛔ Eingriff erforderlich", "Zusammenfassung + letzter Befund", "err", "stadium")
r3 = q.box(750, 1090, 280, 60, "🐍 Modell neu erzeugen", "einmal, mit Begründung", "ver")
r4 = q.box(750, 1170, 280, 60, "🔕 Vergleichstest abschalten", "für diesen Lauf, mit Warnung", "ver")
ok = q.box(750, 1350, 280, 55, "🔁 weiter bei Statischem Check", "", "ok", "stadium")
nx = q.box(40, 1270, 260, 75, "⏭️ Nächste Stufe sofort", "ohne Pipeline-Neustart, ohne erneute Synthese", "sup")
q.edge(e2, r1, "ja", ex=1, ey=0.5, nx=0, ny=0.5)
q.edge(r1, ok, "", "back", ex=1, ey=0.5, nx=1, ny=0.5, points=[(1050, 240), (1050, 1377)])
q.edge(e7, r2, "ja", ex=1, ey=0.5, nx=0, ny=0.5)
q.edge(e10, r3, "ja, Modell noch alt", ex=1, ey=0.4, nx=0, ny=0.5)
q.edge(e10, r4, "ja, Modell schon neu", ex=0.85, ey=0.75, nx=0, ny=0.5)
q.edge(r3, ok, "", "back", ex=1, ey=0.5, nx=1, ny=0.3, points=[(1040, 1120), (1040, 1366)])
q.edge(r4, ok, "", "back", ex=0.5, ey=1, nx=0.5, ny=0)
q.edge(e11, ok, "ja", "back", ex=1, ey=0.5, nx=0, ny=0.5)
q.edge(e11, nx, "nein", ex=0, ey=0.5, nx=1, ny=0.5)
q.edge(nx, e6, "", "loop", ex=0.5, ey=0, nx=0, ny=0.5, points=[(170, 662)])

q.text(1085, 100, 350, 420,
       "<b style='font-size:14px'>🪜 Eskalationsleitern</b><br><br>"
       "<b>Entwurf</b> (Syntax, Simulation, Modell, Synthese, Timing, Anforderung verletzt)<br>"
       "1–2 gezielte Reparatur → 3–4 Modul neu → 5 Architektur → 6–7 Fallback-Modell → Mensch<br><br>"
       "<b>Testbench / Abdeckung / REQ-Lücke</b><br>1–2 Reparatur → 3 Fallback-Modell → 4 Reparatur → Mensch<br><br>"
       "<b>Anforderung fehlt im Plan</b><br>1–2 Plan ergänzen → 3 Fallback-Modell → 4 → Mensch<br><br>"
       "<b>Werkzeug / Konfiguration</b> (Constraints, Bitstream-Config)<br>1 Neubau ohne Sprachmodell → 2 Reparatur mit Vivado-Kontext → 3 Fallback-Modell → Mensch<br><br>"
       "<b>Hardware / Infrastruktur</b> (Board, Kabel, Werkzeug, Anbieter)<br>sofort Mensch<br><br>"
       "<i>Modus standard (Benchmark): eine Reparatur je Fehler, Abbruch bei gleichem Fehler.</i>",
       12, border="#cccccc", fill="#ffffff")
q.text(1085, 690, 350, 200,
       "<b style='font-size:14px'>📝 Befund der Reparatur</b><br><br>"
       "<code>reports/repair_verdict.json</code><br>Ursache:<br>"
       "• design – src/ korrigiert<br>• testbench – Testbench korrigiert<br>"
       "• reference_model – Modell legt PROMPT falsch aus<br>• generated_check – erzeugte Prüfung falsch<br>"
       "• toolchain – Ursache außerhalb des Projekts<br>• specification – PROMPT unklar → offene Frage",
       12, border="#cccccc", fill="#ffffff")
page2 = q.xml(1450, 1450)

out = sys.argv[1]
with open(out, "w", encoding="utf-8") as f:
    f.write('<mxfile host="drawio" version="24.0.0">' + page1 + page2 + "</mxfile>\n")
print("geschrieben:", out)
