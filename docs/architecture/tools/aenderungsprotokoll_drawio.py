"""Erzeugt docs/architecture/AENDERUNGSPROTOKOLL.drawio (Zeitleiste + Damals/Heute)."""
import sys
from xml.sax.saxutils import escape

def q(s):
    return escape(s, {'"': "&quot;"})

class Page:
    def __init__(self, name, pid):
        self.name, self.pid, self.cells, self.n = name, pid, [], 0
    def _id(self):
        self.n += 1
        return f"{self.pid}{self.n}"
    def cell(self, x, y, w, h, value, style):
        cid = self._id()
        self.cells.append(f'<mxCell id="{cid}" value="{q(value)}" style="{style}" vertex="1" parent="1">'
                          f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')
        return cid
    def edge(self, a, b, style, label=""):
        cid = self._id()
        self.cells.append(f'<mxCell id="{cid}" value="{q(label)}" style="{style}" edge="1" parent="1" source="{a}" target="{b}">'
                          f'<mxGeometry relative="1" as="geometry"/></mxCell>')
    def xml(self, w, h):
        return (f'<diagram id="{self.pid}" name="{q(self.name)}"><mxGraphModel dx="1400" dy="900" grid="1" gridSize="10" guides="1" '
                f'tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="{w}" pageHeight="{h}" '
                f'background="#ffffff" math="0" shadow="0"><root><mxCell id="0"/><mxCell id="1" parent="0"/>'
                + "".join(self.cells) + "</root></mxGraphModel></diagram>")

KIND = {  # Art der Phase: (Füllung, Rahmen, Bezeichnung)
    "konzept": ("#f5f5f5", "#666666", "Konzept"),
    "aufbau": ("#dae8fc", "#6c8ebf", "Aufbau"),
    "umbau": ("#e1d5e7", "#9673a6", "Umbau"),
    "analyse": ("#fff2cc", "#d6b656", "Messung / Analyse"),
    "fix": ("#f8cecc", "#b85450", "Korrekturen aus echten Läufen"),
    "ok": ("#d5e8d4", "#82b366", "Erfolg / Dokumentation"),
}

phases = [
    ("0", "Juli/Aug. 2026", "💡 Konzepte", "konzept", [
        "Orchestrator mit Blackboard",
        "Hermes + OpenCode in 🐳 Docker, LangChain, CrewAI",
        "lokales Steuermodell (1–7 B)",
        "Fehler → Prompt-Schleife",
        "Lernspeicher memory.md"],
     "lagacy/Architekturüberblick.png<br>lagacy/Grapische_arch (S. 2)"),
    ("1", "02.08.2026", "🚀 Erste lauffähige Version", "aufbau", [
        "Ports-und-Adapter-Architektur",
        "📚 RAG-Pipeline",
        "Ollama + OpenCode",
        "linearer Zustandsautomat:<br>ANALYZING → RAG_SEARCH → … → TESTING",
        "ein Agentenlauf, noch kein MAS"],
     "bb5e68c · workflow.drawio"),
    ("2", "15.08.2026", "🔧 GHDL-Simulation", "aufbau", [
        "erzeugter Code wird automatisch simuliert",
        "Grundlage der Reparaturschleife"],
     "45880f0"),
    ("3", "13.09.2026", "🤖 Erster Durchlauf + MAS", "aufbau", [
        "erstmals bis Vivado 🏭",
        "7 Agenten: Supervisor, Architecture, HDL, Verification, Debug, FPGA, HardwareTest",
        "Phasensteuerung durch den Supervisor"],
     "a37f1c3 · 7e20a4f"),
    ("4", "07.10.2026", "🏗️ Großer Umbau", "umbau", [
        "RAG entfernt",
        "Gates: Contracts, Abdeckung, Timing",
        "TaskGraph, parallele Worker",
        "Dashboard, ~40 Testdateien",
        "Ollama: Name, Analyse, Diagnose",
        "UART in jedem Projekt, Freigabe vor Flash"],
     "82431d7 · lagacy/aktuelle_arch"),
    ("5", "08.–09.10.2026", "📊 Messung MAS vs. OpenCode", "analyse", [
        "Benchmark mas_vs_single + small_vhdl_bench",
        "Analyse #1–#19: Worker ohne Selbstprüfung, zerstückelter Kontext, UART überall …",
        "GHDL-Selbstprüfung, Testbench-Regeln, UART nur bei Bedarf"],
     "73769ce · f746f15 · ff3c9b4"),
    ("6", "10.10.2026", "🧪 Verifikation & Ausdauer", "umbau", [
        "🐍 Referenzmodell (differentieller Test)",
        "🧬 Mutationsanalyse",
        "Ollama entfernt – nur noch OpenCode",
        "Planwiederholung mit Korrektur",
        "🪜 Eskalation statt Aufgeben"],
     "1baea08 · d6091af · #20–#27"),
    ("7", "10.–11.10.2026", "🛠️ Echte Läufe am Board", "fix", [
        "📋 Einzelanforderungen + Abschlussprüfung",
        "🚑 Vorfilter (Triage), Leitern je Herkunft",
        "⛔→✅ Freigabe vor Flash entfernt",
        "Board-Wissen nach Master-XDC",
        "Generic-Vertrag, Befund der Reparatur",
        "eigenes Git je Workspace, Zustand 1,27 MB → 0,1 MB"],
     "4a16216 · #28–#42"),
    ("8", "11.–12.10.2026", "🏁 Erster Lauf ohne Reparatur", "ok", [
        "Top-Level an die Synthese (#44)",
        "Vivado VHDL-2008, XDC nur Top-Level (#45)",
        "led-patterns-display: 7 Module, 39 Anforderungen, Mutation 1,0, Timing ok, ⚡ geflasht",
        "UML- und Ablaufdiagramme",
        "📼 Lauf-Trajektorien außerhalb des Workspaces (#46)"],
     "63a4752 · 943b9dd · fbacfdc"),
]

# ------------------------------------------------------------- Seite 1: Zeitleiste
p = Page("1 Zeitleiste", "t")
CW, GAP, X0 = 250, 20, 40
total = len(phases) * (CW + GAP)
p.cell(X0, 20, 1600, 40, "<b style='font-size:26px'>Änderungsprotokoll – VHDL-Multiagentensystem</b>"
       "<br>vom ersten Konzept (Sommer 2026) bis zum ersten Lauf ohne Reparatur (12.10.2026)",
       "text;html=1;align=left;verticalAlign=top;fontSize=14;")
# Zeitachse
axis_y = 150
start = p.cell(X0, axis_y - 2, 4, 4, "", "ellipse;fillColor=#333333;strokeColor=none;")
end = p.cell(X0 + total - 10, axis_y - 2, 4, 4, "", "ellipse;fillColor=#333333;strokeColor=none;")
p.edge(start, end, "endArrow=block;endFill=1;strokeWidth=4;strokeColor=#555555;")
for i, (num, date, title, kind, items, src) in enumerate(phases):
    fill, stroke, _ = KIND[kind]
    x = X0 + i * (CW + GAP)
    cx = x + CW / 2
    p.cell(cx - 22, axis_y - 22, 44, 44, f"<b style='font-size:18px'>{num}</b>",
           f"ellipse;html=1;fillColor={fill};strokeColor={stroke};strokeWidth=3;fontSize=16;")
    p.cell(x, axis_y - 70, CW, 40, f"<b>{date}</b>", "text;html=1;align=center;verticalAlign=bottom;fontSize=14;fontColor=#333333;")
    bullets = "".join(f"<li style='margin-bottom:4px'>{it}</li>" for it in items)
    body = (f"<div style='font-size:15px;font-weight:bold;margin-bottom:6px'>{title}</div>"
            f"<ul style='margin:0;padding-left:16px;text-align:left'>{bullets}</ul>")
    card = p.cell(x, axis_y + 50, CW, 270, body,
                  f"rounded=1;arcSize=6;html=1;whiteSpace=wrap;align=left;verticalAlign=top;spacing=10;"
                  f"fillColor={fill};strokeColor={stroke};strokeWidth=2;shadow=1;fontSize=12;")
    p.cell(x, axis_y + 328, CW, 40, f"<i>📎 {src}</i>",
           "text;html=1;align=center;verticalAlign=top;fontSize=11;fontColor=#666666;whiteSpace=wrap;")
    p.cell(cx - 1, axis_y + 22, 2, 28, "", f"fillColor={stroke};strokeColor=none;")

# Legende und Kernaussage
ly = axis_y + 395
p.cell(X0, ly, 540, 34, "<b style='font-size:15px'>Legende</b>", "text;html=1;align=left;fontSize=13;")
for j, key in enumerate(["konzept", "aufbau", "umbau", "analyse", "fix", "ok"]):
    fill, stroke, label = KIND[key]
    col, row = j % 3, j // 3
    bx, by = X0 + col * 230, ly + 36 + row * 34
    p.cell(bx, by, 34, 22, "", f"rounded=1;fillColor={fill};strokeColor={stroke};strokeWidth=2;")
    p.cell(bx + 42, by, 185, 24, label, "text;html=1;align=left;verticalAlign=middle;fontSize=12;")
p.cell(X0 + 720, ly, 1500, 90,
       "<b style='font-size:15px'>Roter Faden</b><br>"
       "Aus einem Konzept mit vielen Frameworks und lokalem Steuermodell wurde schrittweise ein Supervisor mit festen "
       "Phasen und Gates, der nur noch OpenCode nutzt. Ab Oktober zeigten Messungen und echte Läufe am Board vor allem "
       "Fehler im System selbst (Verträge zwischen Agenten, Werkzeugaufrufe, verlorene Informationen). Nach deren Behebung "
       "lief am 11.10.2026 erstmals eine Aufgabe mit 7 Modulen ohne eine einzige Reparatur bis auf das Board.",
       "rounded=1;html=1;whiteSpace=wrap;align=left;verticalAlign=top;spacing=12;fillColor=#ffffff;strokeColor=#bbbbbb;fontSize=13;")
page1 = p.xml(int(X0 * 2 + total), 680)

# ------------------------------------------------------------- Seite 2: Damals -> Heute
c = Page("2 Damals → Heute", "c")
rows = [
    ("🎛️ Steuerung", "Orchestrator / Blackboard bzw. lokales Modell (1–7 B)", "SupervisorAgent mit festen Phasen und Gates"),
    ("🤖 Sprachmodelle", "Ollama lokal + OpenCode; LangChain, CrewAI, Hermes geplant", "nur OpenCode (freie Zen-Modelle), Fallback-Modell in der Eskalation"),
    ("📚 Wissen", "RAG-Pipeline, Lernspeicher memory.md", "Skills + Board-Daten je Workspace (Board-Wissen nach Master-XDC)"),
    ("🔀 Ablauf", "linearer Automat mit RAG_SEARCH, ein Agentenlauf", "Analyse → Architektur → Referenzmodell → TaskGraph parallel → Prüfungen → Synthese → Flash"),
    ("🧭 Planung", "Architektur als YAML/Text vom LLM, deterministischer Fallback", "OpenCode-Manifest: Ports, Generics, Reset, Einzelanforderungen; Korrekturschleife"),
    ("📡 UART", "in jedem Projekt verbindlich", "nur bei Bedarf"),
    ("🧪 Verifikation", "GHDL-Simulation", "Contracts, Testbenches, Referenzmodell, Mutationsanalyse, REQ-Gate, Abschlussprüfung"),
    ("🚑 Fehler", "gleicher Fehler → Abbruch; LLM-Diagnose; HDL-Patch", "Vorfilter → zuständige Rolle → Leiter je Herkunft → Befund; Rücknahme bei Verschlechterung"),
    ("👤 Mensch", "Freigabe vor dem Flashen", "keine Freigabe; nur wenn Leiter erschöpft oder Werkzeug/Board fehlt"),
    ("🔒 Isolation", "Docker geplant", "native Sperre + eigenes Git-Repo je Workspace (Docker zurückgestellt)"),
    ("⚡ Hardware", "Flash; Hardwaretest nicht angebunden", "Flash mit korrekter Board-Konfiguration; Hardwaretest nur mit echter UART"),
]
c.cell(40, 20, 1300, 40, "<b style='font-size:26px'>Frühere Konzeption → Stand 12.10.2026</b>",
       "text;html=1;align=left;verticalAlign=top;fontSize=14;")
c.cell(260, 80, 460, 30, "<b>Damals (lagacy/)</b>", "text;html=1;align=center;fontSize=15;fontColor=#666666;")
c.cell(820, 80, 520, 30, "<b>Heute</b>", "text;html=1;align=center;fontSize=15;fontColor=#2d7600;")
y = 120
for topic, old, new in rows:
    c.cell(40, y, 200, 64, f"<b>{topic}</b>",
           "rounded=1;html=1;whiteSpace=wrap;fillColor=#dae8fc;strokeColor=#6c8ebf;strokeWidth=2;fontSize=14;")
    a = c.cell(260, y, 460, 64, old,
               "rounded=1;html=1;whiteSpace=wrap;fillColor=#f5f5f5;strokeColor=#999999;fontSize=13;fontColor=#555555;dashed=1;")
    b = c.cell(820, y, 520, 64, new,
               "rounded=1;html=1;whiteSpace=wrap;fillColor=#d5e8d4;strokeColor=#82b366;strokeWidth=2;fontSize=13;shadow=1;")
    c.edge(a, b, "endArrow=block;endFill=1;strokeWidth=3;strokeColor=#82b366;")
    y += 80
c.cell(40, y + 10, 1300, 70,
       "<b>Noch offen:</b> Lernspeicher (memory.md) · Docker-Isolation · Hardwaretest ohne UART · HDL-Reparatur über den "
       "Task-Runner mit Skills · UART-/Pmod-Pins im Board-Wissen prüfen · neue Messung MAS vs. einzelnes OpenCode",
       "rounded=1;html=1;whiteSpace=wrap;align=left;spacing=12;fillColor=#fff2cc;strokeColor=#d6b656;fontSize=13;")
page2 = c.xml(1400, y + 120)

with open(sys.argv[1], "w", encoding="utf-8") as f:
    f.write('<mxfile host="drawio" version="24.0.0">' + page1 + page2 + "</mxfile>\n")
print("geschrieben")
