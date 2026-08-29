import os
import shutil
import subprocess
import uuid
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from langchain_core.documents import Document
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.domain.models import KnowledgeBundle

logger = logging.getLogger(__name__)

DEFAULT_MEMORY_DIR = Path("./memory")
DEFAULT_DATA_DIR = Path("./Dateien")
DEFAULT_QDRANT_PATH = DEFAULT_MEMORY_DIR / "qdrant"
SUPPORTED_TEXT_SUFFIXES = {".txt", ".md", ".mdx", ".json", ".csv", ".html", ".xml", ".yml", ".yaml", ".log", ".vhd", ".vhdl"}
SUPPORTED_PDF_SUFFIXES = {".pdf"}

_embeddings = None
_vector_store = None
_llm_model_ready = False


def load_api_key(key_file: str | None = None) -> str:
    if key_file:
        path = Path(key_file)
    else:
        path = Path(__file__).resolve().parents[2] / "RAG_Chatbot-main" / "zugangsdaten.txt"
        if not path.exists():
            path = Path(__file__).resolve().parents[2] / "zugangsdaten.txt"
    if not path.exists():
        return ""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("OLLAMA_API_KEY="):
            return line.split("=", 1)[1].strip()
    return ""


def build_ollama_kwargs(model: str, api_key: str = "", base_url: str = "") -> dict:
    kwargs = {"model": model, "temperature": 0.2}
    if api_key:
        kwargs["base_url"] = "https://ollama.com"
        try:
            import httpx
            kwargs["http_client"] = httpx.Client(
                headers={"Authorization": f"Bearer {api_key}"}
            )
        except ImportError:
            pass
    elif base_url:
        kwargs["base_url"] = base_url
    return kwargs


def get_embeddings(embedding_model: str = "jina-embeddings-v5-text-small"):
    global _embeddings
    if _embeddings is not None:
        return _embeddings
    try:
        from langchain_huggingface import HuggingFaceEmbeddings
    except ImportError:
        logger.warning("langchain-huggingface not installed")
        return None

    candidates = [embedding_model, "sentence-transformers/all-MiniLM-L6-v2"]
    for model in candidates:
        try:
            _embeddings = HuggingFaceEmbeddings(
                model_name=model,
                encode_kwargs={"normalize_embeddings": True},
            )
            logger.info("Embeddings loaded: %s", model)
            break
        except Exception as e:
            logger.debug("Embeddings model %s failed: %s", model, e)
            continue
    return _embeddings


def get_vector_store(
    qdrant_path: str | None = None,
    embedding_model: str = "jina-embeddings-v5-text-small",
    collection_name: str = "vhdl_knowledge",
):
    global _vector_store
    if _vector_store is not None:
        return _vector_store

    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams
        from langchain_qdrant import QdrantVectorStore
    except ImportError:
        logger.warning("Qdrant dependencies not installed")
        return None

    embeddings = get_embeddings(embedding_model)
    if embeddings is None:
        return None

    qdrant_dir = Path(qdrant_path) if qdrant_path else DEFAULT_QDRANT_PATH
    try:
        qdrant_dir.mkdir(parents=True, exist_ok=True)
        client = QdrantClient(path=str(qdrant_dir), check_compatibility=False)
        vector_size = len(embeddings.embed_query("sample text"))

        if not client.collection_exists(collection_name):
            client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )

        _vector_store = QdrantVectorStore(
            client=client,
            collection_name=collection_name,
            embedding=embeddings,
        )
        logger.info("Qdrant vector store initialized at %s", qdrant_dir)
    except Exception as e:
        logger.warning("Qdrant initialization failed: %s", e)
        _vector_store = None

    return _vector_store


def retrieve_context(
    query: str,
    top_k: int = 5,
    vector_store: Any = None,
) -> list[str]:
    store = vector_store or _vector_store or get_vector_store()
    if store is None:
        return []
    try:
        docs = store.similarity_search(query, k=top_k)
        return [doc.page_content for doc in docs if doc.page_content]
    except Exception as e:
        logger.warning("Vector search failed: %s", e)
        return []


def load_documents_from_directory(data_dir: str | Path) -> list[Document]:
    source_dir = Path(data_dir)
    if not source_dir.exists():
        return []

    documents = []
    for file_path in sorted(source_dir.rglob("*")):
        if not file_path.is_file():
            continue
        suffix = file_path.suffix.lower()
        if suffix in SUPPORTED_TEXT_SUFFIXES:
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
        elif suffix in SUPPORTED_PDF_SUFFIXES:
            try:
                content = _extract_pdf_text(file_path)
            except Exception:
                continue
        else:
            continue
        if content.strip():
            documents.append(
                Document(
                    page_content=content,
                    metadata={"source": str(file_path.relative_to(source_dir))},
                )
            )
    return documents


def _extract_pdf_text(file_path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        logger.warning("pypdf not installed, cannot read PDF: %s", file_path)
        return ""
    reader = PdfReader(str(file_path))
    parts = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n\n".join(parts)


def index_documents(
    data_dir: str | Path,
    vector_store: Any = None,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
    force_rebuild: bool = False,
) -> int:
    store = vector_store or _vector_store or get_vector_store()
    if store is None:
        return 0

    if not force_rebuild:
        try:
            docs = store.similarity_search("test", k=1)
            if docs:
                logger.info("Vector store already has documents")
                return 0
        except Exception:
            pass

    documents = load_documents_from_directory(data_dir)
    if not documents:
        logger.info("No documents found in %s", data_dir)
        return 0

    splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    chunks = splitter.split_documents(documents)
    if not chunks:
        return 0

    try:
        store.add_documents(chunks)
        logger.info("Indexed %d chunks from %d documents", len(chunks), len(documents))
        return len(chunks)
    except Exception as e:
        logger.error("Failed to index documents: %s", e)
        return 0


def resolve_memory_dir(memory_dir: str | Path | None = None) -> Path:
    path = Path(memory_dir) if memory_dir is not None else DEFAULT_MEMORY_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def create_chat_session(chat_id: str | None = None, memory_dir: str | Path | None = None) -> dict:
    base_dir = resolve_memory_dir(memory_dir)
    resolved_id = chat_id or f"chat-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    chat_dir = base_dir / resolved_id
    chat_dir.mkdir(parents=True, exist_ok=True)

    soul_path = chat_dir / "soul.md"
    if not soul_path.exists():
        soul_path.write_text(
            f"# Soul Memory\n\nChat-ID: {resolved_id}\n\n",
            encoding="utf-8",
        )
    return {
        "chat_id": resolved_id,
        "memory_dir": str(base_dir),
        "memory_file": str(soul_path),
    }


def append_exchange(
    chat_id: str,
    user_message: str,
    assistant_message: str,
    memory_dir: str | Path | None = None,
) -> Path:
    session = create_chat_session(chat_id=chat_id, memory_dir=memory_dir)
    soul_path = Path(session["memory_file"])
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    entry = f"\n## {timestamp}\n\n**Assistant:** {assistant_message.strip()}\n"
    with soul_path.open("a", encoding="utf-8") as handle:
        handle.write(entry)
    return soul_path


def read_memory(chat_id: str, memory_dir: str | Path | None = None) -> str:
    session = create_chat_session(chat_id=chat_id, memory_dir=memory_dir)
    memory_file = Path(session["memory_file"])
    if memory_file.exists():
        return memory_file.read_text(encoding="utf-8")
    return ""


def build_rag_prompt(query: str, memory_text: str, context_text: str) -> str:
    return (
        f"Du bist ein hilfreicher Assistent. Nutze das verfügbare Gedächtnis "
        f"und den relevanten Kontext, um die Frage zu beantworten.\n\n"
        f"Gedächtnis:\n{memory_text or 'Kein vorheriges Gedächtnis verfügbar.'}\n\n"
        f"Kontext:\n{context_text or 'Kein weiterer Kontext verfügbar.'}\n\n"
        f"Nutzerfrage: {query}\n\n"
        f"Antworte auf Deutsch, präzise und hilfreich."
    )


class RAGChatPipeline:
    def __init__(
        self,
        model: str = "gpt-oss:120b-cloud",
        base_url: str = "",
        embedding_model: str = "jina-embeddings-v5-text-small",
        qdrant_path: str | None = None,
        data_dir: str | Path | None = None,
        memory_dir: str | Path | None = None,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        top_k: int = 5,
        api_key: str = "",
    ):
        self._model = model
        self._base_url = base_url
        self._embedding_model = embedding_model
        self._qdrant_path = qdrant_path
        self._data_dir = Path(data_dir) if data_dir else DEFAULT_DATA_DIR
        self._memory_dir = memory_dir
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._top_k = top_k
        self._api_key = api_key or load_api_key()
        self._vector_store = None
        self._llm = None

    def _get_llm(self):
        if self._llm is not None:
            return self._llm
        try:
            from langchain_ollama import ChatOllama
        except ImportError:
            logger.warning("langchain-ollama not installed")
            return None

        kwargs = build_ollama_kwargs(self._model, self._api_key, self._base_url)
        try:
            self._llm = ChatOllama(**kwargs)
        except Exception as e:
            logger.warning("Failed to create ChatOllama: %s", e)
            self._llm = None
        return self._llm

    def _get_vector_store(self):
        if self._vector_store is not None:
            return self._vector_store
        self._vector_store = get_vector_store(
            qdrant_path=self._qdrant_path,
            embedding_model=self._embedding_model,
        )
        return self._vector_store

    def retrieve_knowledge(self, query: str) -> list[str]:
        store = self._get_vector_store()
        return retrieve_context(query, top_k=self._top_k, vector_store=store)

    def index_data(self, data_dir: str | Path | None = None) -> int:
        directory = Path(data_dir) if data_dir else self._data_dir
        store = self._get_vector_store()
        return index_documents(
            directory,
            vector_store=store,
            chunk_size=self._chunk_size,
            chunk_overlap=self._chunk_overlap,
        )

    def query(
        self,
        query: str,
        chat_id: str | None = None,
        memory_dir: str | Path | None = None,
        data_dir: str | Path | None = None,
    ) -> str:
        session = create_chat_session(chat_id=chat_id, memory_dir=memory_dir or self._memory_dir)
        resolved_data_dir = Path(data_dir) if data_dir else self._data_dir

        self.index_data(resolved_data_dir)

        memory_text = read_memory(session["chat_id"], memory_dir=memory_dir or self._memory_dir)
        context_chunks = self.retrieve_knowledge(query)
        context_text = "\n\n".join(context_chunks)
        prompt = build_rag_prompt(query, memory_text, context_text)

        llm = self._get_llm()
        if llm is None:
            answer = f"[RAG Fallback] Query: {query}\nContext: {context_text[:200]}..."
        else:
            try:
                response = llm.invoke(prompt)
                answer = response.content if hasattr(response, "content") else str(response)
            except Exception as e:
                logger.error("LLM query failed: %s", e)
                answer = f"[Error] {e}"

        append_exchange(session["chat_id"], query, answer, memory_dir=memory_dir or self._memory_dir)
        return answer

    def query_with_tools(
        self,
        query: str,
        tools: list | None = None,
        chat_id: str | None = None,
        memory_dir: str | Path | None = None,
        data_dir: str | Path | None = None,
    ) -> str:
        session = create_chat_session(chat_id=chat_id, memory_dir=memory_dir or self._memory_dir)
        resolved_data_dir = Path(data_dir) if data_dir else self._data_dir
        self.index_data(resolved_data_dir)

        memory_text = read_memory(session["chat_id"], memory_dir=memory_dir or self._memory_dir)
        context_chunks = self.retrieve_knowledge(query)
        context_text = "\n\n".join(context_chunks)

        from src.services.opencode_agent_tool import get_default_tools

        pipeline_tools = tools if tools is not None else get_default_tools()

        llm = self._get_llm()
        if llm is None:
            return f"[RAG Fallback] Query: {query}"

        if not hasattr(llm, "bind_tools"):
            return self.query(query, chat_id, memory_dir, data_dir)

        bound = llm.bind_tools(pipeline_tools)
        messages = [
            SystemMessage(
                content=(
                    "Du bist ein hilfreicher Assistent mit Zugriff auf Tools. "
                    "Nutze sie, um die Aufgabe zu erfüllen. Antworte auf Deutsch."
                )
            ),
            HumanMessage(content=build_rag_prompt(query, memory_text, context_text)),
        ]

        try:
            response = bound.invoke(messages)
        except Exception as e:
            logger.error("Tool invocation failed: %s", e)
            return self.query(query, chat_id, memory_dir, data_dir)

        if not getattr(response, "tool_calls", None):
            answer = response.content if hasattr(response, "content") else str(response)
            append_exchange(session["chat_id"], query, answer, memory_dir=memory_dir or self._memory_dir)
            return answer

        tool_messages = []
        tool_call_msgs = []
        from src.services.opencode_agent_tool import execute_tool_call

        for tc in response.tool_calls:
            result = execute_tool_call(tc, pipeline_tools)
            tc_id = getattr(tc, "id", None) or (tc.get("id") if isinstance(tc, dict) else None)
            tool_messages.append((
                "tool",
                result,
                {"tool_call_id": tc_id or "tool-call"},
            ))

        messages.extend(tool_messages)
        try:
            final = bound.invoke(messages)
            answer = final.content if hasattr(final, "content") else str(final)
        except Exception as e:
            answer = f"[Tool execution error] {e}"

        append_exchange(session["chat_id"], query, answer, memory_dir=memory_dir or self._memory_dir)
        return answer
