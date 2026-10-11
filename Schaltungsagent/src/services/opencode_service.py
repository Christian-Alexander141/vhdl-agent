import json
import os
import pty
import re
import select
import signal
import subprocess
import time
import logging
from pathlib import Path
from src.domain.ports import OpenCodeService, OpenCodeResult
from src.domain.exceptions import (
    AgentExecutionError,
    OpenCodeTimeoutError,
    OpenCodeUnavailableError,
)

logger = logging.getLogger(__name__)


NATIVE_GUARD_FILE = "opencode.json"
NATIVE_GUARD_CONFIG = {
    "$schema": "https://opencode.ai/config.json",
    "permission": {"external_directory": "deny"},
}


def ensure_native_guard(project_path: str) -> None:
    """Sperrt nativen OpenCode-Läufen den Zugriff außerhalb des Projektordners.

    OpenCode erlaubt nativ standardmäßig alles. Ein Benchmark-Lauf hat sich
    deshalb im Repo umgesehen und Dateien unter einem halluzinierten Pfad
    angelegt. Die Sperre wirkt für Read/Edit und Shell-Befehle, aber nur
    außerhalb des Git-Repos, in dem der Workspace liegt: OpenCode betrachtet
    das ganze Repo als Projekt. Workspaces gehören deshalb nicht ins Repo.
    Eine vorhandene opencode.json des Projekts bleibt unangetastet.
    """
    isolate_workspace_repo(project_path)
    path = Path(project_path) / NATIVE_GUARD_FILE
    if path.exists() or not Path(project_path).is_dir():
        return
    path.write_text(json.dumps(NATIVE_GUARD_CONFIG, indent=2) + "\n", encoding="utf-8")


def isolate_workspace_repo(project_path: str) -> None:
    """Eigenes Git-Repo für einen Workspace, der in einem anderen Git-Repo liegt.

    OpenCode nimmt das umschließende Repo als Projekt, und die Sperre
    ``external_directory`` greift erst außerhalb dieses Repos. Die Dashboard-
    Projekte liegen unter ``vhdl-agent/projects/``: Im Lauf led-pattern-display
    (2026-10-11) führte eine Reparatur ``git status`` im System-Repo aus und las
    Quellcode des MAS. Geprüft mit ``opencode debug scrap`` (OpenCode 1.18):
    Mit eigenem Repo samt Start-Commit ist der Workspace selbst das Projekt.
    """
    workspace = Path(project_path)
    if not workspace.is_dir() or (workspace / ".git").exists():
        return
    try:
        top = subprocess.run(
            ["git", "-C", str(workspace), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return  # kein git: OpenCode nutzt den Ordner selbst
    if top.returncode != 0 or Path(top.stdout.strip()).resolve() == workspace.resolve():
        return
    for args in (
        ["init", "-q"],
        ["-c", "user.name=vhdl-agent", "-c", "user.email=vhdl-agent@localhost", "-c", "commit.gpgsign=false",
         "commit", "-q", "--allow-empty", "--no-verify", "-m", "vhdl-agent workspace"],
    ):
        try:
            subprocess.run(["git", "-C", str(workspace), *args], capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            logger.warning("Could not isolate workspace %s as its own git repository", workspace)
            return
    logger.info("Workspace %s isolated as its own git repository for OpenCode", workspace)


# Wie lange das Ergebnis vollständig vorliegen muss, bevor ein Aufruf mit
# stop_when vorzeitig beendet wird.
STOP_WHEN_GRACE_SECONDS = 20.0


def _run_via_pty(
    cmd: list[str], cwd: str | None, timeout: float, stop_when=None,
) -> subprocess.CompletedProcess:
    """Führt ``cmd`` mit einem echten Pseudo-Terminal für stdin/stdout/stderr aus.

    OpenCodes CLI verhält sich ohne TTY nicht zuverlässig: Reproduziert mit
    ``subprocess.run(capture_output=True)`` – dem Mechanismus, den praktisch
    jeder Aufruf vorher verwendet hat – kann der Prozess unbegrenzt lange
    ohne jede Ausgabe hängen bleiben, selbst bei Fehlern, die an einem echten
    Terminal sofort sichtbar sind (z. B. eine Rate-Limit-Meldung des
    Providers). Diese Funktion gibt dem Kindprozess ein echtes PTY, genauso
    wie ein interaktiver Aufruf im Terminal.

    stdout und stderr werden dadurch zu einem Stream zusammengeführt (PTYs
    kennen keine getrennten Deskriptoren); das Ergebnis steht vollständig in
    ``.stdout``, ``.stderr`` bleibt leer.

    Bei Zeitüberschreitung wird die gesamte Prozessgruppe beendet – ein
    Node-Prozess kann eigene Kindprozesse gestartet haben (z. B. ein
    einmaliges npm install beim ersten Start in einem Verzeichnis), die sonst
    verwaist weiterlaufen würden.
    """
    master_fd, slave_fd = pty.openpty()
    try:
        # OpenCode wählt sein Sitzungsverzeichnis nach $PWD, nicht nach dem
        # Prozess-cwd. Ohne Anpassung erbte jeder Worker das Startverzeichnis
        # des Python-Prozesses (z. B. den Quellbaum) und arbeitete dort statt
        # im Projekt-Workspace.
        env = dict(os.environ)
        if cwd:
            env["PWD"] = str(Path(cwd).resolve())
        proc = subprocess.Popen(
            cmd, cwd=cwd, stdin=slave_fd, stdout=slave_fd, stderr=slave_fd,
            close_fds=True, start_new_session=True, env=env,
        )
    finally:
        os.close(slave_fd)

    chunks: list[bytes] = []
    deadline = time.monotonic() + timeout
    timed_out = False
    stopped_early = False
    complete_since = None
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                break
            # Ergebnis vollständig und stabil: nicht bis zum Zeitlimit warten.
            # Lauf gray-countdown 2026-10-11: die Abschlussprüfung schrieb ihr
            # Urteil nach 1,5 min und lief dann bis zum Zeitlimit (900 s).
            if stop_when is not None:
                try:
                    complete = bool(stop_when())
                except Exception:
                    complete = False
                now = time.monotonic()
                complete_since = (complete_since or now) if complete else None
                if complete_since is not None and now - complete_since >= STOP_WHEN_GRACE_SECONDS:
                    stopped_early = True
                    break
            ready, _, _ = select.select([master_fd], [], [], min(remaining, 1.0))
            if ready:
                try:
                    chunk = os.read(master_fd, 65536)
                except OSError:
                    break  # Slave-Ende geschlossen: Kindprozess ist fertig.
                if not chunk:
                    break
                chunks.append(chunk)
            if proc.poll() is not None:
                try:
                    while True:
                        chunk = os.read(master_fd, 65536)
                        if not chunk:
                            break
                        chunks.append(chunk)
                except OSError:
                    pass
                break
    finally:
        os.close(master_fd)

    output = b"".join(chunks).decode(errors="replace")

    if stopped_early and proc.poll() is None:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        return subprocess.CompletedProcess(
            cmd, 0, stdout=output + "\n[vhdl-agent] Ergebnis vollständig; OpenCode vorzeitig beendet\n", stderr="",
        )

    if timed_out and proc.poll() is None:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        raise subprocess.TimeoutExpired(cmd, timeout, output=output)

    proc.wait()
    return subprocess.CompletedProcess(cmd, proc.returncode, stdout=output, stderr="")

DEFAULT_FALLBACK_MODEL = "opencode/mimo-v2.6-flash-free"
# "opencode models" fragt bei kaltem Cache models.dev ab; das dauert in der
# Praxis 10-20s. Eigenes, grosszuegiges Zeitlimit, unabhaengig vom
# agentenbezogenen opencode.default_timeout.
MODELS_LIST_TIMEOUT = 60
QUOTA_ERROR_MARKERS = (
    "quota",
    "rate limit",
    "ratelimit",
    "usage limit",
    "monthly limit",
    "billing",
    "insufficient credits",
    "credit balance",
    "quota exceeded",
    "limit exceeded",
    "too many requests",
    "resource exhausted",
)


# (Muster in stdout/stderr, Ursache, Hinweis) – erste Übereinstimmung gewinnt.
_FAILURE_PATTERNS: tuple[tuple[tuple[str, ...], str, str], ...] = (
    (QUOTA_ERROR_MARKERS,
     "Kontingent bzw. Rate-Limit des Modell-Providers erschöpft",
     "Später erneut versuchen oder in Einstellungen → OpenCode-Modelle ein anderes Modell/Fallback-Modell wählen."),
    (("unauthorized", "status 401", "status code 401", "invalid api key", "invalid_api_key",
      "missing api key", "not authenticated", "authentication failed", "403 forbidden"),
     "Anmeldung beim Modell-Provider fehlgeschlagen",
     "Auf dem Host `opencode auth login` ausführen; im Docker-Modus zusätzlich das Zugangsdaten-Verzeichnis "
     "(Einstellungen → Agenten-Ausführung) setzen."),
    (("model not found", "unknown model", "providermodelnotfound", "no such model", "model_not_found"),
     "Das konfigurierte Modell ist beim Provider nicht verfügbar",
     "Modellnamen in Einstellungen → OpenCode-Modelle prüfen (Format provider/modell)."),
    (("enotfound", "econnrefused", "econnreset", "etimedout", "fetch failed", "network error",
      "getaddrinfo", "connection refused", "name resolution"),
     "Keine Netzwerkverbindung zum Modell-Provider",
     "Internetverbindung prüfen; im Docker-Modus darf das Netzwerk nicht auf 'none' stehen."),
    (("context length", "context window", "maximum context", "too many tokens", "prompt is too long"),
     "Auftrag überschreitet das Kontextfenster des Modells",
     "Aufgabe verkleinern oder ein Modell mit größerem Kontextfenster wählen."),
    (("permission denied", "eacces", "read-only file system", "operation not permitted"),
     "OpenCode durfte im Projektverzeichnis nicht schreiben",
     "Dateirechte des Projektordners prüfen (im Docker-Modus läuft der Container als Host-Benutzer)."),
    (("unexpected server error", "unknownerror", "internal server error", "server error", "502 bad gateway",
      "503 service unavailable", "504 gateway timeout", "bad gateway", "service unavailable"),
     "Serverfehler beim Modell-Provider (nicht auf unserer Seite behebbar)",
     "Meist vorübergehend: in ein oder zwei Minuten erneut versuchen. Tritt es wiederholt auf, "
     "in Einstellungen → OpenCode-Modelle ein anderes Modell/Provider wählen."),
)


def _tail(text: str, lines: int = 15) -> str:
    rows = [row for row in (text or "").strip().splitlines() if row.strip()]
    return "\n".join(rows[-lines:])


def _last_meaningful_line(text: str) -> str:
    """Letzte Zeile von ``text``, die selbst eine Aussage trägt.

    Die OpenCode-CLI gibt Fehler teils als eingerücktes JSON aus
    (``Error: {\n  "name": ...\n}``); die buchstäblich letzte Zeile ist dann
    nur eine schließende Klammer. Diese Funktion liest zuerst ein etwaiges
    JSON-Fehlerobjekt (Felder ``message``/``error``/``name``) und fällt sonst
    auf die letzte Zeile zurück, die mehr als Klammern/Satzzeichen enthält.
    """
    stripped = (text or "").strip()
    json_match = re.search(r"\{.*\}", stripped, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group(0))
        except (ValueError, TypeError):
            data = None
        if isinstance(data, dict):
            message = data.get("message") or (data.get("data") or {}).get("message")
            name = data.get("name") or (data.get("data") or {}).get("name")
            if message:
                return f"{name}: {message}" if name else str(message)
    rows = [row.strip() for row in stripped.splitlines() if row.strip()]
    for row in reversed(rows):
        if re.search(r"[A-Za-z0-9]", row) and row not in ("{", "}", "[", "]"):
            return row
    return rows[-1] if rows else ""


def group_models_by_provider(models: list[str]) -> dict[str, list[str]]:
    """Gruppiert ``provider/modell``-Zeichenketten fuer die Dashboard-Anzeige.

    Zeilen ohne "/" (sollte "opencode models" nicht liefern, aber defensiv
    behandelt) landen unter dem Schluessel "" ("andere").
    """
    groups: dict[str, list[str]] = {}
    for entry in models:
        provider, _, rest = entry.partition("/")
        key = provider if rest else ""
        groups.setdefault(key, []).append(entry)
    return groups


def is_provider_failure(cause: str) -> bool:
    """Ursachen, die kein HDL-Agent beheben kann (Provider, Netz, Rechte)."""
    return any(cause == known for _, known, _ in _FAILURE_PATTERNS)


def describe_opencode_failure(returncode: int, stdout: str = "", stderr: str = "") -> tuple[str, str]:
    """Ursache und Hinweis für einen fehlgeschlagenen OpenCode-Lauf."""
    output = f"{stdout or ''}\n{stderr or ''}".lower()
    for markers, cause, hint in _FAILURE_PATTERNS:
        if any(marker in output for marker in markers):
            return cause, hint
    if returncode != 0:
        last = _last_meaningful_line(stderr) or _last_meaningful_line(stdout) or "keine Ausgabe"
        return (
            f"OpenCode wurde mit Exit-Code {returncode} beendet ({last[:200]})",
            "stderr unten prüfen; den Auftrag einmal manuell mit `opencode run` im Projektordner nachstellen.",
        )
    return "", ""


def create_opencode_service(settings):
    """Create the configured OpenCode runner.

    Produktiv läuft OpenCode immer isoliert in Docker. Nur im Testmodus
    (``opencode.test_mode`` bzw. ``--test-mode``/``VHDL_AGENT_TEST_MODE``)
    wird die lokale CLI verwendet. ``use_docker`` ist veraltet und wird
    ignoriert, damit eine alte Konfiguration die Isolation nicht abschaltet.
    """
    cfg = settings.opencode
    if cfg.test_mode:
        return SubprocessOpenCodeService(
            binary=cfg.binary,
            model=cfg.model,
            default_timeout=cfg.default_timeout,
            fallback_model=cfg.fallback_model,
        )
    if not cfg.use_docker:
        logger.warning(
            "opencode.use_docker=false is ignored: outside test mode OpenCode always "
            "runs in Docker. Enable test mode for native execution."
        )
    return DockerOpenCodeService(
        isolation=cfg.docker_isolation,
        image=cfg.docker_image,
        container=cfg.docker_container,
        docker_workspace=cfg.docker_workspace,
        host_workspace=settings.resolve_path(cfg.docker_host_workspace),
        binary=cfg.docker_binary,
        model=cfg.model,
        default_timeout=cfg.default_timeout,
        fallback_model=cfg.fallback_model,
        network=cfg.docker_network,
        memory=cfg.docker_memory,
        cpus=cfg.docker_cpus,
        auth_dir=str(Path(cfg.docker_auth_dir).expanduser()) if cfg.docker_auth_dir else "",
    )


class ReconfigurableOpenCodeService(OpenCodeService):
    """Stabile Referenz für alle Komponenten; die Ausführung ist umschaltbar.

    Orchestrator, Planer und alle Agenten halten dieses eine Objekt. Eine
    Einstellungsänderung (Testmodus, Docker-Isolation, Modell ...) tauscht
    mit ``reconfigure`` nur den internen Runner aus und wirkt damit sofort
    überall – auch für bereits erzeugte Task-Runner.
    """

    def __init__(self, settings):
        self._delegate = create_opencode_service(settings)

    @property
    def delegate(self) -> OpenCodeService:
        return self._delegate

    def reconfigure(self, settings) -> None:
        self._delegate = create_opencode_service(settings)
        logger.info("OpenCode runner switched to %s", type(self._delegate).__name__)

    def execute(self, project_path: str, instruction: str, timeout_seconds: int | None = None, **kwargs) -> OpenCodeResult:
        return self._delegate.execute(project_path, instruction, timeout_seconds=timeout_seconds, **kwargs)

    def list_models(self, provider: str = "") -> list[str]:
        return self._delegate.list_models(provider)


class SubprocessOpenCodeService(OpenCodeService):
    def __init__(
        self,
        binary: str = "opencode",
        model: str | None = None,
        default_timeout: int = 600,
        fallback_model: str = DEFAULT_FALLBACK_MODEL,
    ):
        self._binary = binary
        self._model = model or DEFAULT_FALLBACK_MODEL
        self._default_timeout = default_timeout
        self._fallback_model = fallback_model or self._model

    def execute(
        self,
        project_path: str,
        instruction: str,
        timeout_seconds: int | None = None,
        stop_when=None,
    ) -> OpenCodeResult:
        timeout = timeout_seconds or self._default_timeout
        logger.info(
            "OpenCode executing: binary=%s, project=%s, timeout=%d",
            self._binary, project_path, timeout,
        )

        try:
            result = self._run(project_path, instruction, timeout, stop_when=stop_when)
            logger.info(
                "OpenCode finished: returncode=%d",
                result.returncode,
            )
            if self._should_use_fallback(result):
                logger.warning(
                    "OpenCode provider limit detected; retrying with free model %s",
                    self._fallback_model,
                )
                result = self._run(
                    project_path, instruction, timeout, self._fallback_model, stop_when=stop_when,
                )
            return OpenCodeResult(
                returncode=result.returncode,
                stdout=result.stdout or "",
                stderr=result.stderr or "",
            )

        except FileNotFoundError:
            logger.error("OpenCode binary not found: %s", self._binary)
            raise OpenCodeUnavailableError(
                f"opencode: command not found ('{self._binary}')",
                cause=f"Das OpenCode-Programm '{self._binary}' ist auf dem Host nicht installiert oder nicht im PATH.",
                hint="OpenCode installieren oder in Einstellungen → Agenten-Ausführung den Programmpfad setzen.",
                context={"Modus": "nativ (Testmodus)", "Projekt": project_path},
            ) from None

        except subprocess.TimeoutExpired as exc:
            logger.error("OpenCode timed out after %ds", timeout)
            raise OpenCodeTimeoutError(
                f"OpenCode execution timed out after {timeout}s",
                cause=f"OpenCode hat innerhalb von {timeout} s kein Ergebnis geliefert und wurde abgebrochen.",
                hint="Zeitlimit in Einstellungen → OpenCode-Modelle erhöhen oder die Aufgabe verkleinern.",
                context={
                    "Modus": "nativ (Testmodus)",
                    "Projekt": project_path,
                    "letzte Ausgabe": _tail(exc.stdout if isinstance(exc.stdout, str) else "", 10),
                },
            ) from None

    def _run(
        self,
        project_path: str,
        instruction: str,
        timeout: int,
        model: str | None = None,
        stop_when=None,
    ) -> subprocess.CompletedProcess:
        effective_model = model or self._model
        cmd = [self._binary, "run"]
        if effective_model:
            cmd.extend(["--model", effective_model])
        cmd.append(instruction)
        ensure_native_guard(project_path)
        extra = {"stop_when": stop_when} if stop_when is not None else {}
        return _run_via_pty(cmd, cwd=project_path, timeout=timeout, **extra)

    def _should_use_fallback(self, result: subprocess.CompletedProcess) -> bool:
        if result.returncode == 0 or not self._fallback_model:
            return False
        output = f"{result.stdout or ''}\n{result.stderr or ''}".lower()
        return any(marker in output for marker in QUOTA_ERROR_MARKERS)

    def list_models(self, provider: str = "") -> list[str]:
        """Verfuegbare Modelle laut ``opencode models [provider]``.

        Fuer das Modell-Dropdown im Dashboard: zeigt genau die Bezeichner,
        die ``--model`` auch akzeptiert (inkl. ``-free``-Suffix bei
        kostenlosen Modellen), statt dass Nutzer sie freihaendig abschreiben.
        """
        cmd = [self._binary, "models"] + ([provider] if provider else [])
        try:
            result = _run_via_pty(cmd, cwd=None, timeout=MODELS_LIST_TIMEOUT)
        except FileNotFoundError:
            raise OpenCodeUnavailableError(
                f"opencode: command not found ('{self._binary}')",
                cause=f"Das OpenCode-Programm '{self._binary}' ist auf dem Host nicht installiert oder nicht im PATH.",
                hint="OpenCode installieren oder in Einstellungen → Agenten-Ausführung den Programmpfad setzen.",
                context={"Modus": "nativ (Testmodus)"},
            ) from None
        except subprocess.TimeoutExpired as exc:
            raise OpenCodeTimeoutError(
                f"opencode models timed out after {MODELS_LIST_TIMEOUT}s",
                cause=f"OpenCode hat die Modell-Liste nicht innerhalb von {MODELS_LIST_TIMEOUT} s geliefert.",
                hint="Erneut versuchen; bei dauerhaftem Timeout die Internetverbindung prüfen (models.dev).",
                context={"letzte Ausgabe": _tail(exc.stdout if isinstance(exc.stdout, str) else "", 10)},
            ) from None
        if result.returncode != 0:
            cause, hint = describe_opencode_failure(result.returncode, result.stdout, result.stderr)
            raise AgentExecutionError(
                "opencode models" + (f" {provider}" if provider else "") + " failed",
                cause=cause,
                hint=hint,
                context={"Exit-Code": result.returncode, "stderr (Ende)": _tail(result.stderr, 10)},
            )
        return [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]


class DockerOpenCodeService(OpenCodeService):
    """OpenCode isoliert in Docker – ohne Rückfall auf den Host.

    ``per_task``: Jeder Auftrag startet einen eigenen, danach gelöschten
    Container. Eingebunden ist ausschließlich das Projektverzeichnis
    (``/workspace``) und optional das Zugangsdaten-Verzeichnis
    (schreibgeschützt). Der Container läuft als Host-Benutzer, ohne
    Capabilities und ohne Rechteausweitung.

    ``shared``: ``docker exec`` in einen laufenden Container, der den
    gesamten projects-Ordner eingebunden hat.
    """

    CONTAINER_HOME = "/tmp/opencode-home"
    ISOLATION_MODES = ("per_task", "shared")

    def __init__(
        self,
        container: str = "opencode-agent",
        docker_workspace: str = "/workspace",
        host_workspace: str | None = None,
        binary: str = "opencode",
        model: str | None = None,
        default_timeout: int = 600,
        fallback_model: str = DEFAULT_FALLBACK_MODEL,
        isolation: str = "per_task",
        image: str = "ghcr.io/anomalyco/opencode:latest",
        network: str = "bridge",
        memory: str = "",
        cpus: str = "",
        auth_dir: str = "",
    ):
        if isolation not in self.ISOLATION_MODES:
            raise ValueError(f"Unknown docker isolation '{isolation}', expected one of {self.ISOLATION_MODES}")
        self._isolation = isolation
        self._image = image
        self._container = container
        self._docker_workspace = docker_workspace
        self._host_workspace = Path(host_workspace).resolve() if host_workspace else None
        self._binary = binary
        self._model = model or DEFAULT_FALLBACK_MODEL
        self._default_timeout = default_timeout
        self._fallback_model = fallback_model or self._model
        self._network = network or "bridge"
        self._memory = memory
        self._cpus = cpus
        self._auth_dir = auth_dir

    def _base_run_args(self) -> list[str]:
        """Rechte-/Netz-Flags, die jeder 'per_task'-Container bekommt (ohne
        Projekt-Mount und ohne --entrypoint/Image/Args, die je Aufruf variieren)."""
        return [
            "docker", "run", "--rm", "-t",
            "--network", self._network,
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--user", f"{os.getuid()}:{os.getgid()}",
            "-e", f"HOME={self.CONTAINER_HOME}",
        ]

    def _auth_and_resource_args(self) -> list[str]:
        args: list[str] = []
        if self._auth_dir:
            args += ["-v", f"{self._auth_dir}:{self.CONTAINER_HOME}/.local/share/opencode:ro"]
        if self._memory:
            args += ["--memory", self._memory]
        if self._cpus:
            args += ["--cpus", self._cpus]
        return args

    def build_command(self, project_path: str, instruction: str, model: str | None = None) -> list[str]:
        """Docker-Befehl für einen Auftrag (ohne Ausführung, testbar)."""
        opencode_args = ["run"]
        if model or self._model:
            opencode_args.extend(["--model", model or self._model])
        opencode_args.append(instruction)

        if self._isolation == "shared":
            return [
                "docker", "exec", "-t", "-w", self._resolve_container_path(project_path),
                self._container, self._binary, *opencode_args,
            ]

        host_project = Path(project_path).resolve()
        if self._host_workspace and not (
            host_project == self._host_workspace or self._host_workspace in host_project.parents
        ):
            raise AgentExecutionError(
                f"Refusing to mount {host_project}: not inside the projects directory",
                cause=f"Aus Sicherheitsgründen wird nur Inhalt von {self._host_workspace} in Container eingebunden.",
                hint="Projekte ausschließlich im konfigurierten Projektordner anlegen.",
            )
        return (
            self._base_run_args()
            + ["-v", f"{host_project}:{self._docker_workspace}:rw", "-w", self._docker_workspace]
            + self._auth_and_resource_args()
            + ["--entrypoint", self._binary, self._image, *opencode_args]
        )

    def build_models_command(self, provider: str = "") -> list[str]:
        """Docker-Befehl zum Auflisten verfügbarer Modelle (kein Projekt-Mount nötig)."""
        opencode_args = ["models"] + ([provider] if provider else [])
        if self._isolation == "shared":
            return ["docker", "exec", "-t", self._container, self._binary, *opencode_args]
        return (
            self._base_run_args()
            + self._auth_and_resource_args()
            + ["--entrypoint", self._binary, self._image, *opencode_args]
        )

    def execute(
        self,
        project_path: str,
        instruction: str,
        timeout_seconds: int | None = None,
        stop_when=None,
    ) -> OpenCodeResult:
        timeout = timeout_seconds or self._default_timeout
        cmd = self.build_command(project_path, instruction)
        logger.info(
            "OpenCode executing in Docker (%s): project=%s, timeout=%d",
            self._isolation, project_path, timeout,
        )
        try:
            extra = {"stop_when": stop_when} if stop_when is not None else {}
            result = _run_via_pty(cmd, cwd=None, timeout=timeout, **extra)
            self._raise_on_docker_failure(result)
            logger.info("Docker OpenCode finished: returncode=%d", result.returncode)
            if self._should_use_fallback(result):
                logger.warning(
                    "OpenCode provider limit detected; retrying with free model %s",
                    self._fallback_model,
                )
                result = _run_via_pty(
                    self.build_command(project_path, instruction, self._fallback_model),
                    cwd=None, timeout=timeout,
                )
                self._raise_on_docker_failure(result)
            return OpenCodeResult(
                returncode=result.returncode,
                stdout=result.stdout or "",
                stderr=result.stderr or "",
            )
        except FileNotFoundError:
            logger.error("Docker binary not found")
            raise OpenCodeUnavailableError(
                "docker: command not found",
                cause="OpenCode läuft außerhalb des Testmodus nur isoliert in Docker, aber das Programm 'docker' fehlt.",
                hint="Docker installieren oder in Einstellungen → Agenten-Ausführung den Testmodus (nativ) wählen.",
                context={"Modus": f"Docker ({self._isolation})", "Projekt": project_path},
            ) from None
        except subprocess.TimeoutExpired as exc:
            logger.error("Docker OpenCode timed out after %ds", timeout)
            raise OpenCodeTimeoutError(
                f"OpenCode execution timed out after {timeout}s",
                cause=f"OpenCode hat im Container innerhalb von {timeout} s kein Ergebnis geliefert.",
                hint="Zeitlimit oder Speicher-/CPU-Limit in den Einstellungen erhöhen oder die Aufgabe verkleinern.",
                context={
                    "Modus": f"Docker ({self._isolation})",
                    "Projekt": project_path,
                    "letzte Ausgabe": _tail(exc.stdout if isinstance(exc.stdout, str) else "", 10),
                },
            ) from None

    def _raise_on_docker_failure(self, result: subprocess.CompletedProcess) -> None:
        """Docker-Infrastrukturfehler abbrechen statt auf den Host auszuweichen."""
        if result.returncode == 0:
            return
        stderr = (result.stderr or "").lower()
        markers = {
            "permission denied while trying to connect to the docker": (
                "Docker permission denied",
                "Der aktuelle Benutzer darf nicht auf den Docker-Socket zugreifen.",
                "Benutzer zur Gruppe 'docker' hinzufügen (sudo usermod -aG docker $USER, danach neu anmelden).",
            ),
            "cannot connect to the docker daemon": (
                "Docker daemon not running",
                "Der Docker-Dienst (bzw. Docker Desktop) läuft nicht.",
                "Docker starten (systemctl start docker oder Docker Desktop öffnen) "
                "oder in Einstellungen → Agenten-Ausführung den Testmodus wählen.",
            ),
            "unable to find image": (
                "Docker image not available",
                f"Das Image '{self._image}' ist lokal nicht vorhanden und konnte nicht geladen werden.",
                f"`docker pull {self._image}` ausführen oder den Image-Namen in den Einstellungen prüfen.",
            ),
            "no such container": (
                "Docker container not running",
                f"Der Container '{self._container}' existiert nicht.",
                "`docker compose up -d opencode` ausführen oder auf Isolation 'Pro Auftrag' umstellen.",
            ),
            "is not running": (
                "Docker container not running",
                f"Der Container '{self._container}' ist gestoppt.",
                "`docker compose up -d opencode` ausführen oder auf Isolation 'Pro Auftrag' umstellen.",
            ),
        }
        for marker, (summary, cause, hint) in markers.items():
            if marker in stderr:
                logger.error("%s", summary)
                raise OpenCodeUnavailableError(
                    f"docker: {summary}. No fallback to the host (isolation required).",
                    cause=cause,
                    hint=hint,
                    context={
                        "Modus": f"Docker ({self._isolation})",
                        "Docker-Meldung": (result.stderr or "").strip()[:500],
                    },
                )

    def _resolve_container_path(self, project_path: str) -> str:
        host_path = Path(project_path).resolve()
        if self._host_workspace and self._host_workspace in host_path.parents:
            relative_path = host_path.relative_to(self._host_workspace)
            return str(Path(self._docker_workspace) / relative_path)
        if self._host_workspace and host_path == self._host_workspace:
            return self._docker_workspace
        raise AgentExecutionError(
            f"Project path {project_path} is not under opencode.docker_host_workspace",
            cause=f"Der gemeinsame Container sieht nur {self._host_workspace}; das Projekt liegt außerhalb.",
            hint="workspace.base_dir und opencode.docker_host_workspace auf denselben Ordner setzen.",
        )

    def _should_use_fallback(self, result: subprocess.CompletedProcess) -> bool:
        if result.returncode == 0 or not self._fallback_model:
            return False
        output = f"{result.stdout or ''}\n{result.stderr or ''}".lower()
        return any(marker in output for marker in QUOTA_ERROR_MARKERS)

    def list_models(self, provider: str = "") -> list[str]:
        """Verfuegbare Modelle laut ``opencode models [provider]`` im Container.

        Nutzt dieselbe Isolation (Image/Container, Zugangsdaten) wie echte
        Auftraege; kein Rueckfall auf den Host.
        """
        cmd = self.build_models_command(provider)
        try:
            result = _run_via_pty(cmd, cwd=None, timeout=MODELS_LIST_TIMEOUT)
            self._raise_on_docker_failure(result)
        except FileNotFoundError:
            raise OpenCodeUnavailableError(
                "docker: command not found",
                cause="OpenCode läuft außerhalb des Testmodus nur isoliert in Docker, aber das Programm 'docker' fehlt.",
                hint="Docker installieren oder in Einstellungen → Agenten-Ausführung den Testmodus (nativ) wählen.",
                context={"Modus": f"Docker ({self._isolation})"},
            ) from None
        except subprocess.TimeoutExpired as exc:
            raise OpenCodeTimeoutError(
                f"opencode models timed out after {MODELS_LIST_TIMEOUT}s",
                cause=f"OpenCode hat die Modell-Liste im Container nicht innerhalb von {MODELS_LIST_TIMEOUT} s geliefert.",
                hint="Erneut versuchen; bei dauerhaftem Timeout die Internetverbindung des Containers prüfen (models.dev).",
                context={
                    "Modus": f"Docker ({self._isolation})",
                    "letzte Ausgabe": _tail(exc.stdout if isinstance(exc.stdout, str) else "", 10),
                },
            ) from None
        if result.returncode != 0:
            cause, hint = describe_opencode_failure(result.returncode, result.stdout, result.stderr)
            raise AgentExecutionError(
                "opencode models" + (f" {provider}" if provider else "") + " failed",
                cause=cause,
                hint=hint,
                context={
                    "Modus": f"Docker ({self._isolation})",
                    "Exit-Code": result.returncode,
                    "stderr (Ende)": _tail(result.stderr, 10),
                },
            )
        return [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]
