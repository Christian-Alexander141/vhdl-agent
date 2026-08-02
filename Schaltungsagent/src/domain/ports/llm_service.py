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
