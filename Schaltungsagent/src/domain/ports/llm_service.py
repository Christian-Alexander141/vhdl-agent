from abc import ABC, abstractmethod


class LLMService(ABC):
    @abstractmethod
    def analyze_request(self, user_request: str, domain: str = "vhdl") -> str:
        ...

    @abstractmethod
    def generate_code(
        self,
        prompt: str,
        context: str = "",
        temperature: float = 0.1,
    ) -> str:
        ...

    @abstractmethod
    def summarize_result(self, task_data: dict) -> str:
        ...

    @abstractmethod
    def generate_project_name(self, user_request: str) -> str:
        ...

    @abstractmethod
    def classify_request(
        self,
        user_request: str,
        projects: list[dict],
        domain: str = "vhdl",
        current_project: str | None = None,
    ) -> dict:
        """Entscheidet, ob eine Nachricht ein neues Projekt startet, ein bestehendes
        Projekt fortführt (z. B. Build erneut versuchen) oder eine Rückfrage ist.

        Gibt ein dict zurück: {"type": "new_project"|"resume"|"question",
        "project_id": str|None, "reason": str}
        """
        ...

    @abstractmethod
    def answer_question(
        self,
        user_request: str,
        context: dict,
        domain: str = "vhdl",
    ) -> str:
        """Beantwortet eine Rückfrage zum Projekt unter Nutzung von Gedächtnis und Kontext."""
        ...
