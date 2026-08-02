import json
import asyncio
import logging
import threading
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.config import load_config
from src.domain.event_bus import EventBus
from src.domain.models import Event, EventType
from src.api.rag_router import router as rag_router
from src.domain.domain_registry import DomainRegistry
from src.services.llm_service import OllamaLLMService
from src.services.rag_service import VHDLRAGService
from src.services.artifact_generator import VHDLArtifactGenerator
from src.services.filesystem_service import LocalFileSystemService
from src.services.opencode_service import SubprocessOpenCodeService
from src.orchestrator import AgentOrchestrator

logger = logging.getLogger(__name__)

settings = load_config()
event_bus = EventBus()
ws_clients: list[WebSocket] = []

DomainRegistry.discover(settings.domains.search_paths)

llm_provider = settings.llm.provider
if llm_provider == "ollama":
    llm = OllamaLLMService(
        model=settings.llm.model,
        base_url=settings.llm.base_url,
        temperature=settings.llm.temperature,
        max_tokens=settings.llm.max_tokens,
    )
else:
    from src.services.llm_service import StubLLMService
    llm = StubLLMService()

rag = VHDLRAGService(
    vector_store_path=settings.rag.vector_store_path,
    embedding_model=settings.rag.embedding_model,
)
artifact_gen = VHDLArtifactGenerator()
fs = LocalFileSystemService(
    base_dir=settings.workspace.base_dir,
    cleanup_ttl_hours=settings.workspace.cleanup_ttl_hours,
    max_workspaces=settings.workspace.max_workspaces,
)
opencode = SubprocessOpenCodeService(
    binary=settings.opencode.binary,
    default_timeout=settings.opencode.default_timeout,
)

orchestrator = AgentOrchestrator(
    llm_service=llm,
    rag_service=rag,
    artifact_generator=artifact_gen,
    filesystem_service=fs,
    opencode_service=opencode,
    event_publisher=event_bus,
    max_repair_iterations=settings.opencode.max_repair_iterations,
)

active_tasks: dict[str, dict] = {}


def broadcast_sync(event: Event) -> None:
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(_async_broadcast(event))
    except RuntimeError:
        pass


async def _async_broadcast(event: Event) -> None:
    message = json.dumps(event.to_dict(), ensure_ascii=False)
    dead_clients: list[WebSocket] = []
    for ws in ws_clients:
        try:
            await ws.send_text(message)
        except Exception:
            dead_clients.append(ws)
    for ws in dead_clients:
        ws_clients.remove(ws)


class TaskRequest(BaseModel):
    user_request: str
    domain: str = "vhdl"


@asynccontextmanager
async def lifespan(app: FastAPI):
    event_bus.on_event(broadcast_sync)
    yield
    event_bus.remove_listener(broadcast_sync)


dashboard_dir = Path(__file__).parent / "dashboard"

app = FastAPI(
    title="AI Engineer Platform API",
    version="2.0.0",
    lifespan=lifespan,
)

if dashboard_dir.exists():
    app.mount("/static", StaticFiles(directory=str(dashboard_dir)), name="dashboard")

app.include_router(rag_router)


@app.get("/")
async def get_dashboard():
    index_path = dashboard_dir / "index.html"
    if index_path.exists():
        return HTMLResponse(index_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Dashboard not found</h1>")


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
                if msg.get("action") == "run_task":
                    request = msg.get("request", "")
                    domain = msg.get("domain", settings.domains.default)
                    result = orchestrator.execute(request, domain)
                    await ws.send_text(json.dumps({
                        "event_type": "TASK_COMPLETED",
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.api_server:app",
        host=settings.dashboard.host,
        port=settings.dashboard.port,
        reload=True,
    )
