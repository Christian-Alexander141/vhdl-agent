import logging
import os
from pathlib import Path
from src.domain.ports import LLMService
from src.domains.vhdl.prompts import VHDLPrompts

logger = logging.getLogger(__name__)


class StubLLMService(LLMService):
    def analyze_request(self, user_request: str, domain: str = "vhdl") -> str:
        logger.info("LLM stub analyzing request: %s (domain=%s)", user_request, domain)
        return f"Analyzed: {user_request}"

    def generate_code(self, prompt: str, context: str = "", temperature: float = 0.1) -> str:
        logger.info("LLM stub generating code")
        return ""

    def summarize_result(self, task_data: dict) -> str:
        status = task_data.get("status", "UNKNOWN")
        files = task_data.get("generated_files", [])
        return (
            f"Task {task_data.get('task_id', '?')} finished with status {status}. "
            f"Generated {len(files)} file(s)."
        )


def _load_api_key(key_file: str = "") -> str:
    if key_file:
        path = Path(key_file)
    else:
        path = Path(__file__).resolve().parents[2] / "RAG_Chatbot-main" / "zugangsdaten.txt"
    if not path.exists():
        return ""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("OLLAMA_API_KEY="):
            return line.split("=", 1)[1].strip()
    return ""


class OllamaLLMService(LLMService):
    def __init__(
        self,
        model: str = "gpt-oss:120b-cloud",
        base_url: str = "",
        temperature: float = 0.1,
        max_tokens: int = 4096,
        api_key_file: str = "",
    ):
        self._model = model
        self._base_url = base_url
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._api_key = _load_api_key(api_key_file)
        self._llm = None

    def _get_llm(self):
        if self._llm is not None:
            return self._llm
        try:
            from langchain_ollama import OllamaLLM
        except ImportError:
            logger.warning("langchain-ollama not installed, falling back to stub")
            return None

        kwargs = {"model": self._model, "temperature": self._temperature}

        if self._api_key:
            kwargs["base_url"] = "https://ollama.com"
            import httpx
            kwargs["http_client"] = httpx.Client(
                headers={"Authorization": f"Bearer {self._api_key}"}
            )
        elif self._base_url:
            kwargs["base_url"] = self._base_url

        try:
            self._llm = OllamaLLM(**kwargs)
        except Exception as e:
            logger.warning("Failed to create OllamaLLM: %s", e)
            self._llm = None
        return self._llm

    def analyze_request(self, user_request: str, domain: str = "vhdl") -> str:
        logger.info("LLM analyzing request: %s (domain=%s)", user_request, domain)
        llm = self._get_llm()
        if llm is None:
            return f"Analyzed: {user_request}"

        if domain == "vhdl":
            system = VHDLPrompts.ANALYSIS_SYSTEM
        else:
            system = "Analyze the following engineering request."

        prompt = f"{system}\n\nRequest: {user_request}\n\nAnalysis:"
        try:
            response = llm.invoke(prompt)
            return str(response).strip()
        except Exception as e:
            logger.error("LLM analysis failed: %s", e)
            return f"Analyzed: {user_request}"

    def generate_code(
        self,
        prompt: str,
        context: str = "",
        temperature: float = 0.1,
    ) -> str:
        logger.info("LLM generating code (prompt length=%d)", len(prompt))
        llm = self._get_llm()
        if llm is None:
            return ""

        full_prompt = f"{context}\n\n{prompt}" if context else prompt
        try:
            response = llm.invoke(full_prompt, temperature=temperature)
            return str(response).strip()
        except Exception as e:
            logger.error("LLM code generation failed: %s", e)
            return ""

    def summarize_result(self, task_data: dict) -> str:
        llm = self._get_llm()
        if llm is None:
            status = task_data.get("status", "UNKNOWN")
            files = task_data.get("generated_files", [])
            return (
                f"Task {task_data.get('task_id', '?')} finished with status {status}. "
                f"Generated {len(files)} file(s)."
            )

        prompt = (
            f"Summarize the following engineering task result:\n"
            f"Status: {task_data.get('status')}\n"
            f"Files: {task_data.get('generated_files', [])}\n"
            f"Iterations: {task_data.get('iterations')}\n"
            f"Summary:"
        )
        try:
            response = llm.invoke(prompt)
            return str(response).strip()
        except Exception:
            return f"Task {task_data.get('task_id', '?')} completed."
