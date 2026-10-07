from abc import ABC, abstractmethod


class ChatLLM(ABC):
    @abstractmethod
    def answer_question(
        self,
        question: str,
        context: dict,
    ) -> str:
        """Answer a project question without generating implementation code."""
        ...

    @abstractmethod
    def phrase_clarification(self, open_questions: list[str], context: dict) -> str:
        """Turn plan questions into a concise user-facing clarification."""
        ...


class NamingLLM(ABC):
    @abstractmethod
    def suggest_names(
        self, request_full: str, missing: set[str], hints: dict
    ) -> dict[str, str]:
        """Suggest only the missing project/module names."""
        ...
