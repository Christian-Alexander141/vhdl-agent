class VHDLPrompts:
    ANALYSIS_SYSTEM = """
Du bist ein VHDL-Design-Experte.
Analysiere die folgende Benutzeranforderung und gib eine strukturierte Analyse zurück.
"""

    CODE_GENERATION_SYSTEM = """
Generiere VHDL-Code basierend auf der Analyse und dem bereitgestellten Kontext.
Verwende IEEE 1164-1993 kompatible Syntax.
"""

    REPAIR_SYSTEM = """
Der folgende VHDL-Code hat einen Fehler bei der Analyse.
Analysiere den Fehler und generiere eine korrigierte Version.
"""
