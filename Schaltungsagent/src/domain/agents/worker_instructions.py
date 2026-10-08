"""Gemeinsame Bausteine für OpenCode-Worker-Aufträge.

Ein einzelner OpenCode-Lauf kompiliert und simuliert selbst und kennt den
ganzen Entwurf. Die MAS-Worker bekamen beides nicht: keine Aufforderung zur
GHDL-Selbstprüfung, keine echten Entities der Nachbarmodule und keine
Kenntnis der Abnahmeregeln des GHDL-Validators (Marker, Simulationszeit).
"""
import re
from pathlib import Path

from src.domain.agents.test_plan import _strip_comments
from src.infrastructure.validation.ghdl_validator import TB_COMPLETE_MARKER

# Muss zu VHDLTestDefinitions.DEFAULT (run_flags) passen.
SIM_STOP_TIME = "1ms"

TESTBENCH_RULES = (
    "Abnahmeregeln der Testbench (der GHDL-Validator prüft genau diese):\n"
    f"- Simulation mit --stop-time={SIM_STOP_TIME}: die Testbench muss in weniger "
    f"als {SIM_STOP_TIME} Simulationszeit fertig sein. Lange Zeiten (Timer, Sekunden, "
    "Baudraten) über Generics des DUT herunterskalieren.\n"
    "- Jede Prüfung als assert ... report \"...\" severity error; ein Fehlschlag "
    "beendet die Simulation (--assert-level=error).\n"
    f"- Am Ende genau einmal: report \"{TB_COMPLETE_MARKER}\" severity note; danach "
    "std.env.stop oder wait; – ohne diesen Marker gilt die Simulation als abgebrochen.\n"
    "- Erwartungswerte aus PROMPT.md bzw. den Golden-Model-Vektoren ableiten, "
    "nicht aus der Implementierung abschreiben.\n"
    "- An wichtigen Prüfpunkten den Zustand ausgeben, z. B. "
    "report \"CHECK t=\" & time'image(now) & \" sig=\" & to_string(sig); "
    "das macht Fehlschläge für eine spätere Reparatur nachvollziehbar."
)


def ghdl_selfcheck(files: list[str], workdir: str, tb_entity: str = "") -> str:
    """Konkrete GHDL-Befehle, mit denen ein Worker sein Ergebnis selbst prüft.

    ``workdir`` muss pro Auftrag eindeutig sein: parallele Worker würden
    sonst dieselbe work-obj08.cf-Bibliothek gleichzeitig beschreiben.
    """
    text = (
        "Prüfe dein Ergebnis selbst mit GHDL, bevor du endest, und behebe jeden "
        "gemeldeten Fehler (Reihenfolge: Abhängigkeiten zuerst):\n"
        f"  mkdir -p {workdir} && ghdl -a --std=08 --workdir={workdir} {' '.join(files)}\n"
    )
    if tb_entity:
        text += (
            f"  ghdl -r --std=08 --workdir={workdir} {tb_entity} "
            f"--stop-time={SIM_STOP_TIME} --assert-level=error\n"
            f"Die Simulation muss mit Exit-Code 0 enden und {TB_COMPLETE_MARKER} ausgeben.\n"
        )
    text += f"Nutze genau dieses --workdir ({workdir}); andere Worker arbeiten parallel."
    return text


_ENTITY_BLOCK = re.compile(r"\bentity\s+(\w+)\s+is\b.*?\bend\b[^;]*;", re.IGNORECASE | re.DOTALL)


def entity_declarations(workspace: str, names: list[str]) -> str:
    """Tatsächliche Entity-Deklarationen bereits erzeugter Module aus src/."""
    blocks = []
    for name in names:
        for ext in (".vhd", ".vhdl"):
            path = Path(workspace) / "src" / f"{name}{ext}"
            if not path.is_file():
                continue
            match = _ENTITY_BLOCK.search(_strip_comments(path.read_text(errors="replace")))
            if match and match.group(1).lower() == name.lower():
                blocks.append(match.group(0).strip())
            break
    return "\n\n".join(blocks)
