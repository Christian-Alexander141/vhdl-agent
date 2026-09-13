import json
import logging
import os
import re
from pathlib import Path
from src.domain.ports import LLMService
from src.domain_plugins.vhdl.prompts import VHDLPrompts
from src.services.project_namer import slugify, sanitize

logger = logging.getLogger(__name__)


def _extract_json(text: str) -> dict:
    """Extrahiert robust ein JSON-Objekt aus einer LLM-Antwort."""
    text = (text or "").strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    return {}


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

    def generate_project_name(self, user_request: str) -> str:
        return slugify(user_request)

    def classify_request(
        self,
        user_request: str,
        projects: list[dict],
        domain: str = "vhdl",
        current_project: str | None = None,
    ) -> dict:
        logger.info("LLM stub classifying request: %s", user_request)
        lowered = (user_request or "").lower().strip()
        resume_hints = ("nochmal", "erneut", "noch einmal", "versuch", "retry", "weiter",
                        "weiterbauen", "weitermachen", "fortsetzen", "nochmals", "rebuild",
                        "docker war nicht aktiv", "docker lief nicht", "repariere",
                        "behebe", "fehler beheben", "baue es nochmal", "nochmal bauen")
        question_hints = ("?", "was", "wie", "warum", "wo", "welche", "welcher", "erkläre",
                          "erklären", "kannst du", "könntest du", "wieso", "wozu", "wann",
                          "was macht", "was ist", "zeig mir", "beschreibe", "was bedeutet")

        if any(hint in lowered for hint in resume_hints):
            target = current_project or (projects[-1]["id"] if projects else None)
            return {
                "type": "resume",
                "project_id": target,
                "reason": "Folge-/Wiederholungsanweisung erkannt",
            }

        project = None
        for p in projects:
            if p["id"] in user_request or p["id"] in lowered:
                project = p["id"]
                break
        if project is None and current_project:
            project = current_project

        if any(hint in lowered for hint in question_hints):
            return {
                "type": "question",
                "project_id": project,
                "reason": "Rückfrage erkannt",
            }

        if project:
            return {
                "type": "resume",
                "project_id": project,
                "reason": "Bezug auf bestehendes Projekt",
            }

        return {
            "type": "new_project",
            "project_id": None,
            "reason": "Neue Projektanfrage",
        }

    def answer_question(
        self,
        user_request: str,
        context: dict,
        domain: str = "vhdl",
    ) -> str:
        logger.info("LLM stub answering question: %s", user_request)
        memory = context.get("memory", "")
        status = context.get("status", "UNKNOWN")
        files = context.get("generated_files", [])
        return (
            f"Antwort (Stub) zur Frage: {user_request}\n"
            f"Projektstatus: {status}, Dateien: {len(files)}.\n"
            f"Gedächtnis: {memory[:200]}"
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
            # langchain-ollama's invoke() does not accept a temperature kwarg here;
            # the model is configured with temperature at construction time.
            response = llm.invoke(full_prompt)
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

    def generate_project_name(self, user_request: str) -> str:
        llm = self._get_llm()
        if llm is None:
            return slugify(user_request)

        prompt = (
            "Gib einen kurzen, aussagekräftigen Projektnamen fuer die folgende "
            "Ingenieur-Aufgabe. Antworte NUR mit einem einzelnen Wort oder einer "
            "kurzen Wortfolge in Kleinbuchstaben (Wörter durch Bindestrich getrennt), "
            "maximal 40 Zeichen, ohne Erklärung, ohne Punkt.\n\n"
            f"Aufgabe: {user_request}\n\nProjektname:"
        )
        try:
            response = str(llm.invoke(prompt)).strip()
            name = sanitize(response)
            if name:
                return name
        except Exception as e:
            logger.error("Project name generation failed: %s", e)
        return slugify(user_request)

    def classify_request(
        self,
        user_request: str,
        projects: list[dict],
        domain: str = "vhdl",
        current_project: str | None = None,
    ) -> dict:
        llm = self._get_llm()
        if llm is None:
            return StubLLMService().classify_request(
                user_request, projects, domain, current_project
            )

        project_lines = "\n".join(
            f"- id: {p.get('id', '')} | Anfrage: {p.get('request', '')} | "
            f"Status: {p.get('status', '')}"
            for p in projects
        ) or "- (keine Projekte vorhanden)"

        system = VHDLPrompts.CLASSIFY_SYSTEM
        prompt = (
            f"{system}\n\n"
            f"Verfügbare Projekte:\n{project_lines}\n"
            f"Aktuell geladenes Projekt (Kontext): {current_project or 'keins'}\n\n"
            f"Benutzernachricht: {user_request}\n\n"
            "Antworte NUR mit dem JSON-Objekt:"
        )
        try:
            response = str(llm.invoke(prompt)).strip()
            decision = _extract_json(response)
        except Exception as e:
            logger.error("Request classification failed: %s", e)
            decision = {}

        ctype = decision.get("type", "new_project")
        if ctype not in ("new_project", "resume", "question"):
            ctype = "new_project"
        pid = decision.get("project_id") or current_project
        if ctype != "new_project" and pid not in [p["id"] for p in projects]:
            pid = current_project or (projects[-1]["id"] if projects else None)
            if ctype == "resume" and not pid:
                ctype = "new_project"
        return {
            "type": ctype,
            "project_id": pid if ctype != "new_project" else None,
            "reason": decision.get("reason", ""),
        }

    def answer_question(
        self,
        user_request: str,
        context: dict,
        domain: str = "vhdl",
    ) -> str:
        llm = self._get_llm()
        if llm is None:
            return StubLLMService().answer_question(user_request, context, domain)

        system = VHDLPrompts.ANSWER_SYSTEM if domain == "vhdl" else (
            "Beantworte die folgende Frage zum Projekt."
        )
        memory = context.get("memory", "") or "(kein Gedächtnis vorhanden)"
        state = context.get("state", {})
        files = "\n".join(f"- {f}" for f in state.get("generated_files", [])) or "- (keine)"

        prompt = (
            f"{system}\n\n"
            f"## Projekt-Gedächtnis (memory.md)\n{memory}\n\n"
            f"## Projektzustand\n"
            f"Status: {state.get('status', 'UNKNOWN')}\n"
            f"Ursprüngliche Anfrage: {state.get('request', '')}\n"
            f"Dateien:\n{files}\n\n"
            f"## Frage\n{user_request}\n\n"
            "Antwort:"
        )
        try:
            response = llm.invoke(prompt)
            return str(response).strip()
        except Exception as e:
            logger.error("Question answering failed: %s", e)
            return f"Entschuldigung, die Antwort konnte nicht generiert werden: {e}"
