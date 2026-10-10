import json
import asyncio
import logging
import threading
import os
import time
import uuid
from pathlib import Path
from contextlib import asynccontextmanager

import yaml

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.config import load_config, load_fpga_registry
from src.domain.event_bus import EventBus
from src.domain.models import Event, EventType
from src.domain.domain_registry import DomainRegistry
from src.services.project_chat import OpenCodeProjectChat
from src.services.name_resolver import NameResolver
from src.services.chat_router import ChatRouter
from src.services.artifact_generator import VHDLArtifactGenerator
from src.services.filesystem_service import LocalFileSystemService
from src.services.opencode_service import (
    ReconfigurableOpenCodeService,
    group_models_by_provider,
)
from src.domain.exceptions import WorkflowError
from src.services.settings_store import (
    SettingsValidationError,
    apply_settings_update,
    editable_settings,
    persist_settings_update,
    restart_required,
)
from src.services.eda_tools import detect_eda_tools, open_project_in_tool
from src.infrastructure.validation.ghdl_validator import GHDLValidator
from src.infrastructure.synthesis import VivadoBitstreamService, VivadoFlashService
from src.orchestrator.supervisor_orchestrator import SupervisorOrchestrator

logger = logging.getLogger(__name__)

ALLOWED_UPLOAD_EXTENSIONS = {
    ".vhd", ".vhdl", ".zip", ".md", ".txt",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg",
}
MAX_UPLOAD_SIZE = 50 * 1024 * 1024

settings = load_config()
event_bus = EventBus()
ws_clients: list[WebSocket] = []
ws_loop: asyncio.AbstractEventLoop | None = None

DomainRegistry.discover(settings.domains.search_paths)

artifact_gen = VHDLArtifactGenerator()
fs = LocalFileSystemService(
    base_dir=settings.resolve_path(settings.workspace.base_dir),
    cleanup_ttl_hours=settings.workspace.cleanup_ttl_hours,
    max_workspaces=settings.workspace.max_workspaces,
)
opencode = ReconfigurableOpenCodeService(settings)
chat_assistant = OpenCodeProjectChat(opencode)

validator = GHDLValidator(
    ghdl_binary=settings.ghdl.binary,
    timeout_seconds=settings.ghdl.timeout_seconds,
)

# Bitstream-Service (Vivado)
fpga_registry = load_fpga_registry()
bitstream_service = VivadoBitstreamService(
    vivado_binary=settings.vivado.binary,
    settings_script=settings.vivado.settings_script,
    timeout_seconds=settings.vivado.timeout_seconds,
    fpga_registry=fpga_registry,
)

# Flash-Services erstellen (basierend auf Board-Profil)
from src.services.flash_service import OpenFPGALoaderFlashService

vivado_flash = VivadoFlashService(
    vivado_binary=settings.vivado.binary,
    settings_script=settings.vivado.settings_script,
    timeout_seconds=settings.flash.timeout_seconds,
)
openfpgaloader_flash = OpenFPGALoaderFlashService(
    binary="openFPGALoader",
    timeout_seconds=settings.flash.timeout_seconds,
)

# Default Flash-Service basierend auf konfiguriertem FPGA
default_fpga = settings.synthesis.default_fpga
fpga_config = fpga_registry.get(default_fpga)
if fpga_config and fpga_config.programmer == "openfpgaloader":
    flash_service = openfpgaloader_flash
else:
    flash_service = vivado_flash

# Flash-Services als Dict für den Orchestrator
flash_services = {
    "vivado": vivado_flash,
    "openfpgaloader": openfpgaloader_flash,
}

orchestrator = SupervisorOrchestrator(
    artifact_generator=artifact_gen,
    filesystem_service=fs,
    opencode_service=opencode,
    event_publisher=event_bus,
    validation_service=validator,
    bitstream_service=bitstream_service,
    flash_service=flash_service,
    flash_services=flash_services,
    fpga_registry=fpga_registry,
    max_repair_iterations=settings.opencode.max_repair_iterations,
    cleanup_on_failure=settings.workspace.cleanup_on_failure,
    cleanup_temp_files=settings.workspace.cleanup_temp_files,
    require_approval=True,
    name_resolver=NameResolver(),
    plan_timeout_seconds=settings.opencode.plan_timeout_seconds,
    max_prompt_bytes=settings.limits.max_prompt_bytes,
    settings=settings,
)

active_tasks: dict[str, dict] = {}
chat_router = ChatRouter()


def _project_chat_context(project_id: str) -> dict:
    workspace = Path(fs.workspace_path(project_id))
    state_path = workspace / "design_state.yaml"
    state = {}
    if state_path.is_file():
        try:
            state = yaml.safe_load(state_path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            logger.warning("Could not load chat context for %s", project_id)
    return {
        "project_id": project_id,
        "workspace": str(workspace) if workspace.is_dir() else "",
        "status": state.get("current_stage", "unknown"),
        "state": state,
        "generated_files": (state.get("implementation") or {}).get("generated_files", []),
        "manifest": (state.get("metadata") or {}).get("plan_manifest", {}),
    }


async def route_chat_message(
    user_request: str,
    domain: str = "vhdl",
    current_project: str | None = None,
    *,
    upload_dir: str | None = None,
    has_attachments: bool = False,
    callback=None,
) -> dict:
    route = chat_router.route(
        user_request,
        current_project,
        has_attachments=has_attachments,
    )
    if route.kind == "question":
        answer = await asyncio.to_thread(
            chat_assistant.answer_question,
            user_request,
            _project_chat_context(route.project_id or ""),
        )
        return {"type": "question", "project_id": route.project_id, "answer": answer}
    if route.kind == "clarify":
        return {"type": "clarification", "project_id": route.project_id, "answer": route.message}
    return await orchestrator.handle_chat_async(
        user_request,
        domain=domain,
        current_project=route.project_id if route.kind == "change" else None,
        upload_dir=upload_dir,
        callback=callback,
    )


def normalize_open_code_model(value: str | None) -> str:
    """Trimmt Leerraum um einen Modellbezeichner, ändert ihn sonst nicht.

    Modell-IDs von Providern sind oft case-sensitiv (z. B. Markennamen wie
    "Nemotron") oder enthalten bewusst Unterstriche. Früher wurde hier alles
    nach dem "/" force-lowercase gemacht und "_"/Leerzeichen zu "-"
    umgeschrieben - das konnte eine gültige ID in eine nicht mehr beim
    Provider auffindbare umwandeln, ohne dass das im Dashboard auffiel
    (der gespeicherte, bereits verstümmelte Wert wurde einfach zurückgezeigt).
    """
    if value is None:
        return ""
    cleaned = str(value).strip()
    if not cleaned:
        return ""
    if "/" in cleaned:
        provider, model = cleaned.split("/", 1)
        return f"{provider.strip()}/{model.strip()}"
    return cleaned


def update_runtime_settings(payload: dict) -> dict:
    """Wendet Dashboard-Einstellungen an und speichert nur geänderte Felder."""

    opencode_cfg = payload.get("opencode") or {}
    for key in ("model", "fallback_model"):
        if key in opencode_cfg:
            opencode_cfg[key] = normalize_open_code_model(opencode_cfg[key]) or getattr(settings.opencode, key)

    changes = apply_settings_update(settings, payload)
    persist_settings_update(Path(settings._config_dir) / "config.yaml", changes)

    if any(section == "opencode" for section, _, _ in changes):
        # Ein gemeinsames Objekt für Planer, Orchestrator und alle Agenten:
        # nur den internen Runner tauschen, damit die Änderung überall greift.
        opencode.reconfigure(settings)
    return {
        "changed": [f"{s}.{n}" for s, n, _ in changes],
        "restart_required": restart_required(changes),
    }


def broadcast_sync(event: Event) -> None:
    global ws_loop
    if ws_loop and ws_loop.is_running():
        asyncio.run_coroutine_threadsafe(_async_broadcast(event), ws_loop)


async def _async_broadcast(event: Event) -> None:
    message = json.dumps(event.to_dict(), ensure_ascii=False)
    dead_clients: list[WebSocket] = []
    for ws in list(ws_clients):
        try:
            await ws.send_text(message)
        except Exception:
            dead_clients.append(ws)
    for ws in dead_clients:
        if ws in ws_clients:
            ws_clients.remove(ws)


class TaskRequest(BaseModel):
    user_request: str
    domain: str = "vhdl"


class ChatRequest(BaseModel):
    user_request: str
    domain: str = "vhdl"
    current_project: str | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global ws_loop
    ws_loop = asyncio.get_running_loop()
    event_bus.on_event(broadcast_sync)
    yield
    event_bus.remove_listener(broadcast_sync)
    ws_loop = None


dashboard_dir = Path(__file__).parent / "dashboard"

app = FastAPI(
    title="AI Engineer Platform API",
    version="2.0.0",
    lifespan=lifespan,
)

if dashboard_dir.exists():
    app.mount("/static", StaticFiles(directory=str(dashboard_dir)), name="dashboard")


@app.get("/")
async def get_dashboard():
    index_path = dashboard_dir / "index.html"
    if index_path.exists():
        return HTMLResponse(index_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Dashboard not found</h1>")


@app.get("/api/settings")
async def get_settings():
    data = editable_settings(settings)
    data["_meta"]["test_mode_forced_by_environment"] = os.environ.get(
        "VHDL_AGENT_TEST_MODE", ""
    ).lower() in {"1", "true", "yes", "on"}
    data["_meta"]["opencode_runner"] = type(opencode.delegate).__name__
    return JSONResponse(data)


# "opencode models" dauert kalt 10-20s; Ergebnis kurz cachen, damit das
# Dashboard nicht bei jedem Oeffnen der Einstellungen erneut wartet.
_models_cache: dict[str, dict] = {}
_MODELS_CACHE_TTL_SECONDS = 600


@app.get("/api/opencode/models")
async def list_opencode_models(provider: str = "", refresh: bool = False):
    cache_key = provider or "*"
    cached = _models_cache.get(cache_key)
    now = time.monotonic()
    if cached and not refresh and (now - cached["fetched_at"]) < _MODELS_CACHE_TTL_SECONDS:
        return JSONResponse({**cached["payload"], "cached": True})
    try:
        models = await asyncio.to_thread(opencode.list_models, provider)
    except WorkflowError as exc:
        logger.warning("Listing OpenCode models failed: %s", exc)
        return JSONResponse({"error": str(exc), "hint": exc.hint}, status_code=502)
    except Exception as exc:
        logger.exception("Listing OpenCode models failed")
        return JSONResponse({"error": str(exc)}, status_code=502)
    payload = {
        "models": models,
        "by_provider": group_models_by_provider(models),
        "runner": type(opencode.delegate).__name__,
    }
    _models_cache[cache_key] = {"payload": payload, "fetched_at": now}
    return JSONResponse({**payload, "cached": False})


@app.post("/api/settings")
async def save_settings(payload: dict):
    try:
        result = update_runtime_settings(payload)
    except SettingsValidationError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except Exception as exc:
        logger.exception("Failed to update settings")
        return JSONResponse({"error": str(exc)}, status_code=500)
    return JSONResponse({"status": "ok", **result, "opencode": {"model": settings.opencode.model}})


@app.get("/api/tasks")
async def get_tasks():
    running = orchestrator.list_tasks()
    return JSONResponse({
        "completed": list(active_tasks.values()),
        "running": running,
    })


@app.get("/api/tasks/{task_id}")
async def get_task(task_id: str):
    task = active_tasks.get(task_id)
    status = orchestrator.get_task_status(task_id)
    if task is None and status is None:
        return JSONResponse({"error": "Task not found"}, status_code=404)
    if task:
        return JSONResponse(task)
    return JSONResponse(status)


@app.post("/api/task")
async def create_task(req: TaskRequest):
    def on_complete(result: dict):
        active_tasks[result["task_id"]] = result

    task_id = orchestrator.execute_async(
        req.user_request,
        req.domain,
        callback=on_complete,
    )

    return JSONResponse({
        "task_id": task_id,
        "status": "QUEUED",
        "message": "Task queued for execution",
    })


@app.post("/api/task/sync")
async def create_task_sync(req: TaskRequest):
    result = orchestrator.execute(req.user_request, req.domain)
    active_tasks[result["task_id"]] = result
    return JSONResponse(result)


@app.post("/api/chat")
async def chat_message(req: ChatRequest):
    """Chat-Eingang: unterscheidet neue Projekte, Fortsetzungen und Rückfragen
    und pflegt das projektbezogene Gedächtnis (memory.md).

    Rückfragen werden direkt beantwortet; neue Projekte und Fortsetzungen laufen
    asynchron und streamen ihren Fortschritt über WebSocket."""
    def on_complete(result: dict):
        if result.get("task_id"):
            active_tasks[result["task_id"]] = result

    try:
        result = await route_chat_message(
            req.user_request,
            domain=req.domain,
            current_project=req.current_project,
            callback=on_complete,
        )
    except Exception as e:
        logger.exception("Chat request failed")
        return JSONResponse({
            "error": str(e),
            "type": "error",
            "task_id": req.current_project or "",
            "answer": f"Fehler: {e}",
        }, status_code=500)

    if result.get("task_id") and result.get("status") not in ("QUEUED", "ANSWERED"):
        active_tasks[result["task_id"]] = result
    return JSONResponse(result)


def save_uploads(files: list[UploadFile]) -> str:
    """Speichert hochgeladene Dateien in einem Staging-Ordner und liefert dessen
    Pfad. Erlaubt sind VHDL-, ZIP-, Markdown-, Text- und Bilddateien."""
    upload_root = Path(settings.resolve_path(settings.workspace.base_dir)) / "_uploads"
    session = uuid.uuid4().hex[:12]
    session_dir = upload_root / session
    session_dir.mkdir(parents=True, exist_ok=True)

    for upload in files:
        name = Path(upload.filename or "").name
        if not name or Path(name).suffix.lower() not in ALLOWED_UPLOAD_EXTENSIONS:
            logger.warning("Upload-Datei übersprungen (nicht erlaubt): %s", upload.filename)
            continue
        dest = session_dir / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        size = 0
        try:
            with dest.open("wb") as out:
                while chunk := upload.file.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_UPLOAD_SIZE:
                        logger.warning("Upload-Datei zu groß, verworfen: %s", name)
                        dest.unlink(missing_ok=True)
                        break
                    out.write(chunk)
        except OSError as e:
            logger.warning("Upload fehlgeschlagen für %s: %s", name, e)
        finally:
            upload.file.close()

    return str(session_dir)


@app.post("/api/chat/upload")
async def chat_message_upload(
    user_request: str = Form(""),
    domain: str = Form("vhdl"),
    current_project: str | None = Form(None),
    files: list[UploadFile] = File(default_factory=list),
):
    """Chat-Eingang mit Datei-Upload: Bilder, ZIP-, Markdown-, Text- und VHDL-Dateien.
    Wenn der Nutzer „ex" im Prompt wünscht, werden hochgeladene VHDL-Dateien direkt
    in das Projekt integriert und bei Bedarf vervollständigt."""
    if not user_request.strip() and not files:
        return JSONResponse({
            "type": "error",
            "answer": "Bitte eine Aufgabe beschreiben oder Dateien hochladen.",
        }, status_code=400)

    upload_dir = save_uploads(files)

    def on_complete(result: dict):
        if result.get("task_id"):
            active_tasks[result["task_id"]] = result

    try:
        result = await route_chat_message(
            user_request,
            domain=domain,
            current_project=current_project,
            upload_dir=upload_dir,
            has_attachments=bool(files),
            callback=on_complete,
        )
    except Exception as e:
        logger.exception("Chat upload request failed")
        return JSONResponse({
            "error": str(e),
            "type": "error",
            "task_id": current_project or "",
            "answer": f"Fehler: {e}",
        }, status_code=500)

    if result.get("task_id") and result.get("status") not in ("QUEUED", "ANSWERED"):
        active_tasks[result["task_id"]] = result
    return JSONResponse(result)


@app.get("/api/domains")
async def list_domains():
    return JSONResponse({
        "domains": DomainRegistry.list_domains(),
        "default": settings.domains.default,
    })


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    ws_clients.append(ws)
    logger.info("WebSocket client connected")
    try:
        while True:
            data = await ws.receive_text()
            try:
                msg = json.loads(data)
                action = msg.get("action")
                if action == "run_task":
                    request = msg.get("request", "")
                    domain = msg.get("domain", settings.domains.default)
                    result = orchestrator.execute(request, domain)
                    actual_status = result.get("status", "UNKNOWN")
                    event_type = "TASK_FAILED" if actual_status == "FAILED" else "TASK_COMPLETED"
                    await ws.send_text(json.dumps({
                        "event_type": event_type,
                        "payload": result,
                    }, ensure_ascii=False))
                elif action == "chat":
                    request = msg.get("request", "")
                    domain = msg.get("domain", settings.domains.default)
                    current_project = msg.get("current_project")
                    try:
                        result = await route_chat_message(
                            request,
                            domain=domain,
                            current_project=current_project,
                        )
                    except Exception as e:
                        logger.exception("WebSocket chat failed")
                        result = {
                            "type": "error",
                            "task_id": current_project or "",
                            "answer": f"Fehler: {e}",
                            "error": str(e),
                        }
                    await ws.send_text(json.dumps({
                        "event_type": "CHAT_RESPONSE",
                        "payload": result,
                    }, ensure_ascii=False))
            except json.JSONDecodeError:
                await ws.send_text(json.dumps({
                    "event_type": "ERROR",
                    "payload": {"message": "Invalid JSON"},
                }))
    except WebSocketDisconnect:
        ws_clients.remove(ws)
        logger.info("WebSocket client disconnected")
    except Exception as e:
        if ws in ws_clients:
            ws_clients.remove(ws)
        logger.error("WebSocket error: %s", e)


@app.get("/api/debug")
async def debug():
    return {
        "ws_clients": len(ws_clients),
        "events_logged": len(event_bus.get_events()),
        "active_tasks": len(active_tasks),
        "domains": DomainRegistry.list_domains(),
    }


@app.post("/api/cleanup")
async def cleanup_workspaces():
    removed = fs.cleanup_expired()
    return JSONResponse({"removed": removed})


@app.get("/api/projects")
async def list_projects():
    projects_dir = Path(settings.resolve_path(settings.workspace.base_dir))
    projects = []
    if projects_dir.is_dir():
        for entry in sorted(projects_dir.iterdir()):
            if not entry.is_dir() or entry.name.startswith("_"):
                continue
            state_file = entry / "state.json"
            info = {"name": entry.name}
            if state_file.exists():
                try:
                    state = json.loads(state_file.read_text(encoding="utf-8"))
                except Exception:
                    state = {}
                info.update({
                    "task_id": state.get("task_id", entry.name),
                    "status": state.get("status", "UNKNOWN"),
                    "request": state.get("request", ""),
                    "created_at": state.get("created_at", ""),
                    "updated_at": state.get("updated_at", ""),
                    "workspace": state.get("workspace", ""),
                    "generated_files": state.get("generated_files", []),
                    "error_message": state.get("error_message", ""),
                    "approval": state.get("approval", None),
                })
            design_state_file = entry / "design_state.yaml"
            if design_state_file.exists():
                try:
                    import yaml
                    design_state = yaml.safe_load(
                        design_state_file.read_text(encoding="utf-8")
                    ) or {}
                    current_stage = design_state.get("current_stage")
                    if isinstance(current_stage, dict):
                        current_stage = current_stage.get("value")
                    if current_stage:
                        info["status"] = current_stage
                except Exception:
                    logger.warning("Could not read design state for %s", entry.name)
            projects.append(info)
    projects.sort(key=lambda p: p.get("created_at", ""), reverse=True)
    return JSONResponse({"projects": projects})


@app.get("/api/projects/{project}")
async def get_project(project: str):
    projects_dir = Path(settings.resolve_path(settings.workspace.base_dir))
    project_dir = projects_dir / project
    if not project_dir.is_dir():
        return JSONResponse({"error": "Project not found"}, status_code=404)
    state_file = project_dir / "state.json"
    state = {}
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
        except Exception as e:
            state = {"error": str(e)}
    design_state_file = project_dir / "design_state.yaml"
    if design_state_file.exists():
        try:
            import yaml
            design_state = yaml.safe_load(
                design_state_file.read_text(encoding="utf-8")
            ) or {}
            current_stage = design_state.get("current_stage")
            if isinstance(current_stage, dict):
                current_stage = current_stage.get("value")
            if current_stage:
                state["status"] = current_stage
        except Exception:
            logger.warning("Could not read design state for %s", project)
    files = []
    for p in project_dir.rglob("*"):
        if p.is_file() and p.name != "state.json":
            files.append(str(p.relative_to(project_dir)))
    memory = ""
    memory_file = project_dir / "memory.md"
    if memory_file.is_file():
        try:
            memory = memory_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            memory = ""
    return JSONResponse({"name": project, "state": state, "files": sorted(files), "memory": memory})


@app.get("/api/projects/{project}/memory")
async def get_project_memory(project: str):
    projects_dir = Path(settings.resolve_path(settings.workspace.base_dir))
    project_dir = projects_dir / project
    if not project_dir.is_dir():
        return JSONResponse({"error": "Project not found"}, status_code=404)
    memory_file = project_dir / "memory.md"
    content = ""
    if memory_file.is_file():
        try:
            content = memory_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            content = ""
    return JSONResponse({"name": project, "memory": content})


@app.delete("/api/projects/{project}")
async def delete_project(project: str):
    """Löscht ausschließlich das angegebene Projekt (Workspace-Verzeichnis)."""
    projects_dir = Path(settings.resolve_path(settings.workspace.base_dir)).resolve()
    project_dir = (projects_dir / project).resolve()
    if (
        project_dir == projects_dir
        or project_dir == projects_dir.parent
        or not str(project_dir).startswith(str(projects_dir) + os.sep)
        or project.startswith("_")
    ):
        return JSONResponse({"error": "Invalid project name"}, status_code=400)
    if not project_dir.is_dir():
        return JSONResponse({"error": "Project not found"}, status_code=404)

    name = project_dir.name
    active_tasks.pop(name, None)
    fs.delete_workspace(name)
    logger.info("Project deleted: %s", name)
    return JSONResponse({"deleted": name})


class OpenToolRequest(BaseModel):
    tool: str


class ApprovalRequest(BaseModel):
    feedback: str = ""


@app.post("/api/projects/{task_id}/approve")
async def approve_project(task_id: str, body: ApprovalRequest):
    """Genehmigt den Bitstream für das Flashen auf das FPGA."""
    ok = orchestrator.approve_task(task_id, body.feedback)
    if not ok:
        return JSONResponse(
            {"error": "Task not found or not awaiting approval"},
            status_code=404,
        )
    return JSONResponse({"approved": True, "task_id": task_id})


@app.post("/api/projects/{task_id}/reject")
async def reject_project(task_id: str, body: ApprovalRequest):
    """Lehnt den Bitstream ab und sendet Feedback für Reparatur."""
    ok = orchestrator.reject_task(task_id, body.feedback)
    if not ok:
        return JSONResponse(
            {"error": "Task not found or not awaiting approval"},
            status_code=404,
        )
    return JSONResponse({"rejected": True, "task_id": task_id, "feedback": body.feedback})


@app.get("/api/eda-tools")
async def list_eda_tools():
    return JSONResponse({"tools": detect_eda_tools()})


@app.post("/api/projects/{project}/open-tool")
async def open_project_tool(project: str, body: OpenToolRequest):
    projects_dir = Path(settings.resolve_path(settings.workspace.base_dir)).resolve()
    project_dir = (projects_dir / project).resolve()
    if (
        project_dir == projects_dir
        or project_dir == projects_dir.parent
        or not str(project_dir).startswith(str(projects_dir) + os.sep)
    ):
        return JSONResponse({"error": "Invalid project name"}, status_code=400)
    if not project_dir.is_dir():
        return JSONResponse({"error": "Project not found"}, status_code=404)

    ok, message = open_project_in_tool(body.tool, project_dir)
    if not ok:
        logger.warning("Open project in tool failed: %s - %s", project, message)
        return JSONResponse({"error": message}, status_code=400)
    logger.info("Opened project %s in %s", project, body.tool)
    return JSONResponse({"ok": True, "message": message})


@app.get("/api/projects/{project}/file")
async def get_project_file(project: str, path: str = ""):
    projects_dir = Path(settings.resolve_path(settings.workspace.base_dir)).resolve()
    project_dir = (projects_dir / project).resolve()
    if not project_dir.is_dir() or not str(project_dir).startswith(str(projects_dir) + os.sep):
        return JSONResponse({"error": "Project not found"}, status_code=404)
    full = (project_dir / path).resolve()
    if not str(full).startswith(str(project_dir) + os.sep):
        return JSONResponse({"error": "Invalid path"}, status_code=400)
    if not full.is_file() or full.name == "state.json":
        return JSONResponse({"error": "File not found"}, status_code=404)
    content = full.read_text(encoding="utf-8", errors="replace")
    return JSONResponse({"path": path, "content": content})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.api_server:app",
        host=settings.dashboard.host,
        port=settings.dashboard.port,
        reload=True,
    )
