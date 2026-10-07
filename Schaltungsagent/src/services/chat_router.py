"""Deterministic routing between new projects, questions, and changes."""
import re
from dataclasses import dataclass

# Anzeichen für kopierte Log-/Fehlerausgaben statt einer Hardwarebeschreibung.
# Beispiel, der zu diesem Schutz geführt hat: ein Nutzer hatte eine eigene
# Fehlermeldung (aus einem vorherigen fehlgeschlagenen Lauf) noch in der
# Zwischenablage und fügte sie versehentlich als neue Projektanforderung ein.
# Das Ergebnis war kein Fehler, sondern ein über mehrere Minuten und Gates
# hinweg "sauber" fehlgeschlagener Lauf, der aus dem Log kein Hardware-Modul
# ableiten konnte. Dieser Check fängt solche Eingaben vorher ab.
_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")
_PYTHON_TRACEBACK_RE = re.compile(r"Traceback \(most recent call last\)|File \"[^\"]+\", line \d+")
_LOG_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", re.MULTILINE)
_LOG_LEVEL_RE = re.compile(r"\[(ERROR|WARNING|WARN|INFO|DEBUG|CRITICAL)\]")
_JS_STACK_FRAME_RE = re.compile(r"^\s*at \S+ \(.+:\d+:\d+\)", re.MULTILINE)

# Eigene Diagnose-Feldbezeichner (siehe WorkflowError.__str__ in
# domain/exceptions.py). Zwei oder mehr davon zusammen kommen in einer
# echten Hardwarebeschreibung praktisch nie vor – fast immer handelt es
# sich um eine zurückkopierte eigene Fehlermeldung.
_OWN_DIAGNOSTIC_LABELS = (
    "Ursache:", "Hinweis:", "Phase:", "Erwartete Dateien:", "Laufzeit:",
    "Ausführung:", "Auftragsdatei:", "stderr (Ende):", "stdout (Ende):",
    "Exit-Code:", "Von OpenCode geänderte Dateien:",
)


def looks_like_log_or_error_dump(text: str) -> bool:
    """True, wenn ``text`` eher eine kopierte Log-/Fehlerausgabe ist als eine
    Hardwarebeschreibung.

    Bewusst als reiner Mustertreffer gehalten (keine Längen-/Zeilenzahl-
    Heuristik wie in :meth:`ChatRouter.route`) – soll ausschließlich
    versehentlich eingefügte technische Ausgaben abfangen, keine langen,
    aber echten Anforderungstexte.
    """
    if _ANSI_ESCAPE_RE.search(text) or _PYTHON_TRACEBACK_RE.search(text):
        return True
    if _LOG_TIMESTAMP_RE.search(text) and _LOG_LEVEL_RE.search(text):
        return True
    if len(_JS_STACK_FRAME_RE.findall(text)) >= 2:
        return True
    return sum(1 for label in _OWN_DIAGNOSTIC_LABELS if label in text) >= 2


@dataclass(frozen=True)
class ChatRoute:
    kind: str
    project_id: str | None = None
    message: str = ""


class ChatRouter:
    QUESTION_HINTS = (
        "?", "warum", "wieso", "was", "wie", "welche", "welcher", "erkläre",
        "erklaere", "beschreibe", "was bedeutet", "was macht",
    )
    CHANGE_HINTS = (
        "ändere", "aendere", "ändere", "korrigiere", "behebe", "repariere",
        "fixe", "fix", "passe", "ergänze", "ergaenze", "füge", "fuege", "baue",
        "nochmal", "erneut", "noch einmal", "versuch", "weiter", "fortsetzen",
        "rebuild", "docker war nicht aktiv", "docker lief nicht",
    )
    LOG_DUMP_CLARIFICATION = (
        "Dieser Text sieht nach einer kopierten Log- oder Fehlerausgabe aus, "
        "nicht nach einer Hardwarebeschreibung – daraus kann ich kein Modul "
        "ableiten. Falls das versehentlich eingefügt wurde (z. B. aus der "
        "Zwischenablage): bitte die eigentliche Aufgabe neu eingeben, z. B. "
        "„Baue eine Ampelsteuerung für das Arty S7-50“. Falls dieser Text "
        "wirklich als Grundlage dienen soll, formuliere es bitte in eigenen "
        "Worten (z. B. „Nutze genau diesen Text als Anforderung: …“)."
    )

    def route(
        self,
        request: str,
        current_project: str | None = None,
        has_attachments: bool = False,
    ) -> ChatRoute:
        if not has_attachments and looks_like_log_or_error_dump(request):
            return ChatRoute(
                "clarify",
                project_id=current_project,
                message=self.LOG_DUMP_CLARIFICATION,
            )

        if (
            not current_project
            or has_attachments
            or len(request) >= 400
            or len(request.splitlines()) >= 3
        ):
            return ChatRoute("new_project")

        lowered = request.casefold().strip()
        if any(hint in lowered for hint in self.QUESTION_HINTS):
            return ChatRoute("question", project_id=current_project)
        if any(hint in lowered for hint in self.CHANGE_HINTS):
            return ChatRoute("change", project_id=current_project)
        return ChatRoute(
            "clarify",
            project_id=current_project,
            message=(
                f"Soll ich ein neues Projekt starten oder das Projekt "
                f"{current_project} ändern?"
            ),
        )
