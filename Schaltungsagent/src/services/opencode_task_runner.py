"""File-based OpenCode handoff that preserves the user's complete prompt."""
from __future__ import annotations

import hashlib
import logging
import os
import re
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from src.domain import yaml_io

from src.domain.exceptions import OpenCodeDeliveryError, WorkflowError
from src.services.opencode_service import describe_opencode_failure, is_provider_failure

logger = logging.getLogger(__name__)
DEFAULT_MAX_PROMPT_BYTES = 200_000

# AP11: Knowledge mandatory line per stage
STAGE_SKILLS: dict[str, list[str]] = {
    "plan": ["vhdl-synthesis-rules", "arty-s7-50-board"],
    "implement_module": ["vhdl-synthesis-rules", "vhdl-fsm"],
    "implement_testbench": ["vhdl-testbench", "vhdl-synthesis-rules"],
    "implement_top": ["vhdl-synthesis-rules", "arty-s7-50-board"],
    "implement_project": ["vhdl-synthesis-rules", "vhdl-fsm", "vhdl-testbench"],
    "reference_model": [],
    "review_and_fix": ["ghdl-vivado-errors", "vhdl-synthesis-rules", "arty-s7-50-board"],
}

KNOWLEDGE_LINE_TPL = (
    "\n\n---\nLies zuerst diese Datei(en) direkt mit dem Read-Tool (NICHT über "
    "ein Skill-Tool – dessen Namensraum enthält diese projektspezifischen IDs "
    "nicht und ein Versuch schlägt fehl, kostet Zeit und Kontext): {paths}. "
    "Bei Widerspruch zwischen einer dieser Dateien und PROMPT.md gilt PROMPT.md; "
    "trage den Widerspruch in open_questions bzw. reports/review.md ein. "
    "Schreibe danach in .opencode_tasks/{task_id}.done.md eine Zeile "
    "`skills: <gelesene ids>`."
)


class PromptIntegrityError(RuntimeError):
    pass


@dataclass
class OpenCodeDelivery:
    ok: bool
    stage: str
    files: dict[str, str] = field(default_factory=dict)
    stdout: str = ""
    stderr: str = ""
    reason: str = ""
    prompt_sha256: str = ""
    # Diagnose für den Fehlerfall
    returncode: int | None = None
    hint: str = ""
    file_status: dict[str, str] = field(default_factory=dict)
    changed_files: list[str] = field(default_factory=list)
    task_file: str = ""
    duration_s: float = 0.0
    runner: str = ""
    exception: Exception | None = None

    def error(self, subject: str) -> Exception:
        """Ausnahme mit Ursache, Hinweis und Kontext für diese Lieferung.

        War schon der OpenCode-Aufruf selbst ein strukturierter Fehler
        (Docker fehlt, Zeitlimit ...), wird dieser mit Kontext angereichert
        zurückgegeben, statt ihn zu überdecken.
        """
        context = {
            "Phase": self.stage,
            "Erwartete Dateien": ", ".join(f"{name} ({state})" for name, state in self.file_status.items()),
            "Exit-Code": self.returncode,
            "Laufzeit": f"{self.duration_s:.1f} s" if self.duration_s else "",
            "Ausführung": self.runner,
            "Auftragsdatei": self.task_file,
            "Von OpenCode geänderte Dateien": ", ".join(self.changed_files[:15]) or "keine",
            "stderr (Ende)": _tail(self.stderr),
            "stdout (Ende)": _tail(self.stdout, 10),
        }
        if isinstance(self.exception, WorkflowError):
            self.exception.message = f"{subject}: {self.exception.message}"
            self.exception.context = {**{k: v for k, v in context.items() if v not in (None, "", [])},
                                      **self.exception.context}
            return self.exception
        return OpenCodeDeliveryError(
            f"{subject}: OpenCode hat {', '.join(self.file_status) or 'das Ergebnis'} nicht gültig geliefert",
            cause=self.reason or "unbekannt",
            hint=self.hint,
            context=context,
            failure_type="infrastructure" if is_provider_failure(self.reason) else "",
        )


def _accepts(function, name: str) -> bool:
    """Nimmt die Funktion den Parameter an? (Test-Doubles kennen stop_when nicht.)"""
    import inspect

    try:
        parameters = inspect.signature(function).parameters
    except (TypeError, ValueError):
        return False
    return name in parameters or any(p.kind == p.VAR_KEYWORD for p in parameters.values())


def _tail(text: str, lines: int = 15) -> str:
    rows = [row for row in (text or "").strip().splitlines() if row.strip()]
    return "\n".join(rows[-lines:])


_IGNORED_SNAPSHOT_PARTS = {
    # ".opencode_tasks" sind unsere eigenen Auftragsdateien, ".opencode" ist
    # OpenCodes eigenes Arbeitsverzeichnis: enthaelt .opencode/skills (von uns
    # provisioniert, bereits vor dem Snapshot stabil) und, sobald OpenCode den
    # (nativen) Skill-Mechanismus oder sein Plugin-System beruehrt, ein
    # mehrere Megabyte grosses .opencode/node_modules. Ohne diesen Eintrag
    # taucht z. B. ".opencode/node_modules/.bin/..." als "von OpenCode
    # geänderte Datei" in Fehlermeldungen auf und verschleiert die echte
    # Ursache (siehe Bugreport: "manifest.json fehlt" zeigte nur
    # node_modules-Dateien statt eines Hinweises auf das eigentliche Problem).
    ".opencode_tasks", ".opencode", "opencode.json",
    ".git", "build", "__pycache__", "node_modules",
}


# Ein Aufruf, der so kurz läuft, mit Exit-Code 0 endet und gar nichts schreibt,
# ist kein Lösungsversuch, sondern ein vorzeitiger Abbruch des Modells (im
# Benchmark beobachtet: Antwort endete nach 24 s mitten im Satz). Einmal
# wiederholen statt sofort Reparatur oder Abbruch auszulösen.
EARLY_STOP_RETRY_SECONDS = 180


def _ended_prematurely(result, changed: list[str], duration: float, root: Path, expected_files: list[str]) -> bool:
    if result.returncode != 0 or changed or duration >= EARLY_STOP_RETRY_SECONDS:
        return False
    cause, _ = describe_opencode_failure(result.returncode, result.stdout or "", result.stderr or "")
    if cause and is_provider_failure(cause):  # Rate-Limit o. Ä.: Wiederholen hilft nicht
        return False
    return any(not (root / name).is_file() for name in expected_files)


_SYSTEM_STATE_FILES = {"task_graph.json", "task_graph.json.tmp", "design_state.yaml", "design_state.yaml.tmp"}


def _snapshot(workspace: Path) -> dict[str, float]:
    """Änderungszeitpunkte aller Projektdateien (ohne Auftrags-/Build-Ordner)."""
    result = {}
    if not workspace.is_dir():
        return result
    for path in workspace.rglob("*"):
        rel = path.relative_to(workspace)
        if rel.parts and rel.parts[0] in _IGNORED_SNAPSHOT_PARTS:
            continue
        if path.name.startswith(".") and path.name.endswith(".tmp"):
            continue  # kurzlebige Datei aus atomic_write_text
        if rel.as_posix() in _SYSTEM_STATE_FILES:
            # Schreibt der Supervisor, auch während ein anderer Worker läuft
            # (Checkpoint je fertiger Aufgabe, #48). Als "von OpenCode geändert"
            # verhinderte das die Wiederholung früh beendeter Aufrufe.
            continue
        if path.is_file():
            try:
                result[rel.as_posix()] = path.stat().st_mtime
            except OSError:
                pass
    return result


def _check_vhdl_file(path: Path, relative_path: str) -> tuple[str, str, str]:
    """(Status, Ursache, Hinweis) für eine erwartete Datei."""
    if not path.is_file():
        return "fehlt", f"{relative_path} wurde nicht geschrieben", ""
    content = path.read_text(encoding="utf-8", errors="replace")
    if not content.strip():
        return "leer", f"{relative_path} ist leer", "Das Modell hat die Datei angelegt, aber keinen Code geschrieben."
    if path.suffix.lower() not in {".vhd", ".vhdl"}:
        return "ok", "", ""
    if "```" in content:
        return ("Markdown", f"{relative_path} enthält einen Markdown-Codeblock (```) statt reinem VHDL",
                "Das Modell hat seine Chat-Antwort in die Datei geschrieben; anderes Modell wählen oder erneut versuchen.")
    expected_entity = path.stem
    entities = re.findall(r"\bentity\s+(\w+)\s+is\b", content, re.IGNORECASE)
    if not any(name.lower() == expected_entity.lower() for name in entities):
        found = ", ".join(entities) or "keine"
        return ("falsche Entity", f"{relative_path} enthält Entity '{found}' statt '{expected_entity}'",
                "Entity-Name muss dem Dateinamen bzw. Modulnamen aus der Architektur entsprechen.")
    if not re.search(r"\barchitecture\s+\w+\s+of\s+", content, re.IGNORECASE):
        return ("ohne Architecture", f"{relative_path} enthält keine architecture",
                "Das Modell hat nur die Entity-Deklaration geliefert.")
    return "ok", "", ""


_STATE_LOCKS: dict[str, threading.Lock] = {}
_STATE_LOCKS_GUARD = threading.Lock()


def _state_lock(path: Path) -> threading.Lock:
    key = str(Path(path).resolve())
    with _STATE_LOCKS_GUARD:
        return _STATE_LOCKS.setdefault(key, threading.Lock())


def atomic_write_text(path: Path, content: str) -> None:
    """Schreibt über eine Temporärdatei im selben Ordner und ersetzt atomar.

    Leser sehen so immer entweder die alte oder die neue Datei, nie eine halbe.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


class PromptStore:
    def __init__(self, max_prompt_bytes: int = DEFAULT_MAX_PROMPT_BYTES):
        self.max_prompt_bytes = max_prompt_bytes

    @staticmethod
    def _state_path(workspace: Path) -> Path:
        return workspace / "design_state.yaml"

    def save(self, workspace: str, request_full: str) -> str:
        raw = request_full.encode("utf-8")
        if len(raw) > self.max_prompt_bytes:
            raise ValueError(
                f"Prompt is {len(raw)} bytes; limit is {self.max_prompt_bytes} bytes"
            )
        root = Path(workspace)
        root.mkdir(parents=True, exist_ok=True)
        prompt_path = root / "PROMPT.md"
        if prompt_path.exists():
            if prompt_path.read_bytes() != raw:
                raise PromptIntegrityError("PROMPT.md already contains a different request")
        else:
            prompt_path.write_bytes(raw)
        digest = hashlib.sha256(raw).hexdigest()
        self._save_digest(root, digest)
        return digest

    def verify(self, workspace: str) -> str:
        root = Path(workspace)
        prompt_path = root / "PROMPT.md"
        if not prompt_path.is_file():
            raise PromptIntegrityError("PROMPT.md is missing")
        raw = prompt_path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        state_path = self._state_path(root)
        with _state_lock(state_path):
            state = self._read_state(state_path)
        expected = (state.get("metadata") or {}).get("prompt_sha256")
        if expected and expected != digest:
            raise PromptIntegrityError("PROMPT.md hash does not match design_state metadata")
        if not expected:
            self._save_digest(root, digest)
        return digest

    def _save_digest(self, root: Path, digest: str) -> None:
        # Parallele Worker riefen das für jeden Auftrag gleichzeitig auf und
        # lasen dabei halb geschriebene Dateien (PromptIntegrityError, Benchmark
        # 20261010-091252). Daher: serialisiert, nur bei Bedarf, atomar.
        path = self._state_path(root)
        with _state_lock(path):
            state = self._read_state(path)
            metadata = state.setdefault("metadata", {})
            if metadata.get("prompt_sha256") == digest:
                return
            metadata["prompt_sha256"] = digest
            atomic_write_text(path, yaml_io.dump(state, allow_unicode=True))

    @staticmethod
    def _read_state(path: Path) -> dict:
        if not path.is_file():
            return {}
        try:
            return yaml_io.load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            raise PromptIntegrityError(f"Could not read state metadata from {path}")


class OpenCodeTaskRunner:
    def __init__(
        self,
        opencode_service,
        *,
        event_publisher=None,
        max_prompt_bytes: int = DEFAULT_MAX_PROMPT_BYTES,
    ):
        self._opencode = opencode_service
        self._events = event_publisher
        self._prompts = PromptStore(max_prompt_bytes)

    def run(
        self,
        *,
        workspace: str,
        request_full: str,
        stage: str,
        task_instruction: str,
        expected_files: list[str],
        task_id: str = "",
        timeout_seconds: int | None = None,
        skills_dir: str = ".opencode/skills",
        stop_when=None,
    ) -> OpenCodeDelivery:
        digest = self._prompts.save(workspace, request_full)
        if self._prompts.verify(workspace) != digest:
            raise PromptIntegrityError("Prompt integrity check failed before OpenCode call")

        task_token = re.sub(r"[^a-zA-Z0-9_-]", "_", task_id)[:40] or uuid.uuid4().hex[:12]

        # AP11: Append knowledge mandatory line
        skills = STAGE_SKILLS.get(stage, [])
        if skills:
            paths = ", ".join(f"{skills_dir}/{skill_id}/SKILL.md" for skill_id in skills)
            knowledge_line = KNOWLEDGE_LINE_TPL.format(
                paths=paths,
                task_id=task_token,
            )
            task_instruction = task_instruction + knowledge_line

        from src.domain.agents.requirements import task_instruction_suffix

        task_instruction = task_instruction + task_instruction_suffix(workspace, stage)

        task_dir = Path(workspace) / ".opencode_tasks"
        task_dir.mkdir(parents=True, exist_ok=True)
        task_path = task_dir / f"{task_token}_{stage}.md"
        task_path.write_text(task_instruction, encoding="utf-8")
        short_instruction = (
            f"Lies PROMPT.md vollständig sowie .opencode_tasks/{task_path.name} "
            "vollständig und führe die Aufgabe aus. Schreibe Ergebnisse direkt "
            "in die dort genannten Dateien."
        )
        # prompt_length ist der Auftrag selbst (.opencode_tasks/…), request_length
        # PROMPT.md. Früher stand hier für jeden Aufruf die Länge von PROMPT.md
        # (Lauf mini_cpu: 22-mal 7516), die tatsächliche Auftragsgröße fehlte.
        sizes = {"prompt_length": len(task_instruction), "request_length": len(request_full)}
        logger.info(
            "OPENCODE_CALL stage=%s prompt_length=%d request_length=%d task_id=%s",
            stage, sizes["prompt_length"], sizes["request_length"], task_id,
        )
        root = Path(workspace)
        before = _snapshot(root)
        runner = type(getattr(self._opencode, "delegate", self._opencode)).__name__
        runner = {"DockerOpenCodeService": "Docker", "SubprocessOpenCodeService": "nativ (Testmodus)"}.get(runner, runner)
        started = time.monotonic()
        base = {
            "stage": stage, "prompt_sha256": digest, "runner": runner,
            "task_file": task_path.relative_to(root).as_posix(),
        }
        attempt = 0
        while True:
            attempt += 1
            attempt_started = time.monotonic()
            try:
                extra = {"stop_when": stop_when} if stop_when and _accepts(self._opencode.execute, "stop_when") else {}
                result = self._opencode.execute(
                    workspace, short_instruction, timeout_seconds=timeout_seconds, **extra
                )
            except Exception as exc:
                cause = getattr(exc, "cause", "") or str(exc)
                self._emit(stage, task_id, digest, sizes, False, cause, time.monotonic() - started)
                return OpenCodeDelivery(
                    ok=False, stderr=str(exc), reason=cause, hint=getattr(exc, "hint", ""),
                    exception=exc, duration_s=time.monotonic() - started,
                    file_status={name: "nicht erzeugt" for name in expected_files}, **base,
                )
            after = _snapshot(root)
            changed = sorted(name for name, mtime in after.items() if before.get(name) != mtime)
            if attempt < 2 and _ended_prematurely(
                result, changed, time.monotonic() - attempt_started, root, expected_files,
            ):
                logger.warning(
                    "OPENCODE_EARLY_STOP stage=%s task_id=%s: Modell endete nach %.0f s ohne "
                    "Datei (Exit 0); einmalige Wiederholung", stage, task_id,
                    time.monotonic() - attempt_started,
                )
                self._emit(stage, task_id, digest, sizes, False,
                           "early stop without output; retrying once", time.monotonic() - attempt_started)
                continue
            break
        duration = time.monotonic() - started

        files: dict[str, str] = {}
        file_status: dict[str, str] = {}
        problems: list[tuple[str, str]] = []
        for relative_path in expected_files:
            path = root / relative_path
            status, cause, hint = _check_vhdl_file(path, relative_path)
            file_status[relative_path] = status
            if status == "ok":
                files[relative_path] = path.read_text(encoding="utf-8")
            else:
                problems.append((cause, hint))

        success = bool(result.returncode == 0 and len(files) == len(expected_files))
        reason, hint = "", ""
        if not success:
            process_cause, process_hint = describe_opencode_failure(
                result.returncode, result.stdout or "", result.stderr or ""
            )
            if process_cause:
                # Prozessfehler (Kontingent, Anmeldung, Exit-Code) erklären fehlende Dateien.
                reason, hint = process_cause, process_hint
            elif problems:
                reason = "; ".join(cause for cause, _ in problems)
                hint = next((h for _, h in problems if h), "")
                missing = [name for name, state in file_status.items() if state == "fehlt"]
                if missing:
                    others = [name for name in changed if name not in expected_files]
                    if others:
                        reason += f" – OpenCode hat stattdessen {', '.join(others[:5])} geändert"
                        hint = hint or "Ziel-Dateiname weicht ab; Modulnamen in der Architektur und in der Antwort vergleichen."
                    else:
                        reason += " – OpenCode endete ohne Fehler, hat aber keine Projektdatei geschrieben"
                        hint = hint or ("Das Modell hat vermutlich nur geantwortet statt die Datei zu schreiben; "
                                        "stdout prüfen oder ein anderes Modell wählen.")
            else:
                reason = "OpenCode did not write every expected file"
        self._emit(stage, task_id, digest, sizes, success, reason, duration)
        return OpenCodeDelivery(
            ok=success,
            files=files,
            stdout=result.stdout or "",
            stderr=result.stderr or "",
            reason=reason,
            hint=hint,
            returncode=result.returncode,
            file_status=file_status,
            changed_files=changed,
            duration_s=duration,
            **base,
        )

    def _emit(
        self, stage: str, task_id: str, digest: str, sizes: dict,
        success: bool, reason: str, duration_s: float,
    ) -> None:
        payload = {
            "stage": stage,
            "task_id": task_id,
            "prompt_sha256": digest,
            **sizes,
            "duration_s": round(duration_s, 1),
            "success": success,
            "reason": reason,
        }
        logger.info("OPENCODE_RESULT %s", payload)
        if self._events:
            try:
                from src.domain.models.events import EventType

                self._events.publish_event(EventType.OPENCODE_CALL, task_id, payload)
            except Exception:
                logger.exception("Could not publish OPENCODE_CALL event")