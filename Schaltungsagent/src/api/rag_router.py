import json as _json
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, UploadFile
from pydantic import BaseModel

from src.config import load_config
from src.services.rag_service import VHDLRAGService as RAGChatService
from src.services.task_planner_service import TaskPlannerService

logger = logging.getLogger(__name__)

settings = load_config()
PROJECT_ROOT = Path(__file__).resolve().parents[2]

rag_service = RAGChatService(
    model=settings.llm.model,
    base_url=settings.llm.base_url,
    embedding_model=settings.rag.embedding_model,
    qdrant_path=settings.rag.vector_store_path,
    chunk_size=settings.rag.chunk_size,
    chunk_overlap=settings.rag.chunk_overlap,
    top_k=settings.rag.max_results,
)

planner = TaskPlannerService(
    model_name=settings.llm.model,
    base_url=settings.llm.base_url,
)

router = APIRouter(prefix="/api/rag", tags=["RAG"])


class RagRequest(BaseModel):
    message: str
    chatId: Optional[str] = None
    memoryDir: Optional[str] = None
    dataDir: Optional[str] = None
    usePlanner: bool = False
    useTools: bool = False
    maxSteps: int = 3


class RagResponse(BaseModel):
    text: str
    chatId: Optional[str] = None


@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/query", response_model=RagResponse)
def rag_query(payload: RagRequest):
    if payload.usePlanner:
        result = planner.plan_and_execute(payload.message)
        answer = result.get("summary", _json.dumps(result, ensure_ascii=False))
    elif payload.useTools:
        answer = rag_service.chat_query_with_tools(
            query=payload.message,
            chat_id=payload.chatId,
            memory_dir=payload.memoryDir,
            data_dir=payload.dataDir,
        )
    else:
        answer = rag_service.chat_query(
            query=payload.message,
            chat_id=payload.chatId,
            memory_dir=payload.memoryDir,
            data_dir=payload.dataDir,
        )
    return RagResponse(text=answer, chatId=payload.chatId)


@router.post("/chat")
def create_chat():
    session = rag_service.create_session()
    return {
        "chatId": session["chat_id"],
        "memoryFile": session["memory_file"],
    }


@router.post("/index")
def index_documents(dataDir: Optional[str] = None):
    directory = dataDir or str(PROJECT_ROOT / "Dateien")
    count = rag_service.index_data(directory)
    return {"indexed_chunks": count, "data_dir": directory}


@router.post("/upload")
async def upload_files(
    files: list[UploadFile] = File(...),
    dataDir: Optional[str] = Form(None),
):
    target_dir = Path(dataDir) if dataDir else PROJECT_ROOT / "Dateien"
    target_dir.mkdir(parents=True, exist_ok=True)

    saved = []
    for f in files:
        dest = target_dir / f.filename
        with dest.open("wb") as handle:
            handle.write(await f.read())
        saved.append(f.filename)

    return {"savedFiles": saved, "dataDir": str(target_dir)}


@router.get("/models")
def get_models():
    return {"models": [settings.llm.model], "defaultModel": settings.llm.model}
