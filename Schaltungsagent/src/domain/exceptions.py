"""Fehlerklassen des Workflows.

Alle Fehler können neben der Meldung eine **Ursache**, einen **Hinweis** zur
Behebung und strukturierten **Kontext** tragen. ``str(exc)`` liefert daraus
einen mehrzeiligen, lesbaren Text – so erscheint die Ursache gleichermaßen
im Log, im Traceback, in den Diagnosen und im Dashboard.
"""


class WorkflowError(Exception):
    def __init__(
        self,
        message: str = "",
        *,
        cause: str = "",
        hint: str = "",
        context: dict | None = None,
        failure_type: str = "",
    ):
        super().__init__(message)
        self.message = message
        self.cause = cause
        self.hint = hint
        # Fehlerklasse für das Reparatur-Routing (z. B. "infrastructure").
        self.failure_type = failure_type
        self.context = {k: v for k, v in (context or {}).items() if v not in (None, "", [], {})}

    def __str__(self) -> str:
        lines = [self.message]
        if self.cause:
            lines.append(f"  Ursache: {self.cause}")
        if self.hint:
            lines.append(f"  Hinweis: {self.hint}")
        for key, value in self.context.items():
            text = value if isinstance(value, str) else repr(value)
            if "\n" in text:
                indented = "\n".join(f"      {line}" for line in text.rstrip().splitlines())
                lines.append(f"  {key}:\n{indented}")
            else:
                lines.append(f"  {key}: {text}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "type": type(self).__name__,
            "message": self.message,
            "cause": self.cause,
            "hint": self.hint,
            "failure_type": self.failure_type,
            "context": self.context,
        }


class LLMError(WorkflowError):
    pass


class ArtifactError(WorkflowError):
    pass


class WorkspaceError(WorkflowError):
    pass


class AgentExecutionError(WorkflowError):
    pass


class OpenCodeUnavailableError(AgentExecutionError):
    """OpenCode kann gar nicht gestartet werden (Programm, Docker, Image fehlt)."""

    def __init__(self, message: str = "", **kwargs):
        kwargs.setdefault("failure_type", "infrastructure")
        super().__init__(message, **kwargs)


class OpenCodeTimeoutError(AgentExecutionError):
    """OpenCode hat das Zeitlimit überschritten und wurde abgebrochen."""

    def __init__(self, message: str = "", **kwargs):
        kwargs.setdefault("failure_type", "infrastructure")
        super().__init__(message, **kwargs)


class OpenCodeDeliveryError(AgentExecutionError):
    """OpenCode lief, hat aber die erwartete(n) Datei(en) nicht gültig geliefert."""


class StateMachineError(WorkflowError):
    pass


class ConfigurationError(WorkflowError):
    pass
