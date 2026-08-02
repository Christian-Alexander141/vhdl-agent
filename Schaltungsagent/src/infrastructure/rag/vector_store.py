import logging
from pathlib import Path
from typing import Any

from .embedding_provider import EmbeddingProvider

logger = logging.getLogger(__name__)

_vector_store = None


class VectorStoreService:
    def __init__(
        self,
        qdrant_path: str | None = None,
        embedding_model: str = "jina-embeddings-v5-text-small",
        collection_name: str = "vhdl_knowledge",
    ):
        self._qdrant_path = qdrant_path
        self._embedding_model = embedding_model
        self._collection_name = collection_name
        self._store = None

    def get_store(self):
        global _vector_store
        if self._store is not None:
            return self._store
        if _vector_store is not None:
            self._store = _vector_store
            return self._store
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams
            from langchain_qdrant import QdrantVectorStore
        except ImportError:
            logger.warning("Qdrant dependencies not installed")
            return None

        provider = EmbeddingProvider(self._embedding_model)
        embeddings = provider.get_embeddings()
        if embeddings is None:
            return None

        from ...services.rag_pipeline import DEFAULT_QDRANT_PATH
        qdrant_dir = Path(self._qdrant_path) if self._qdrant_path else DEFAULT_QDRANT_PATH
        try:
            qdrant_dir.mkdir(parents=True, exist_ok=True)
            client = QdrantClient(path=str(qdrant_dir), check_compatibility=False)
            vector_size = len(embeddings.embed_query("sample text"))
            if not client.collection_exists(self._collection_name):
                client.create_collection(
                    collection_name=self._collection_name,
                    vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
                )
            self._store = QdrantVectorStore(
                client=client,
                collection_name=self._collection_name,
                embedding=embeddings,
            )
            _vector_store = self._store
            logger.info("Qdrant vector store initialized at %s", qdrant_dir)
        except Exception as e:
            logger.warning("Qdrant initialization failed: %s", e)
            self._store = None
        return self._store

    def similarity_search(self, query: str, top_k: int = 5) -> list[str]:
        store = self.get_store()
        if store is None:
            return []
        try:
            docs = store.similarity_search(query, k=top_k)
            return [doc.page_content for doc in docs if doc.page_content]
        except Exception as e:
            logger.warning("Vector search failed: %s", e)
            return []

    def add_documents(self, chunks: list) -> int:
        store = self.get_store()
        if store is None or not chunks:
            return 0
        try:
            store.add_documents(chunks)
            return len(chunks)
        except Exception as e:
            logger.error("Failed to add documents: %s", e)
            return 0

    def has_documents(self) -> bool:
        store = self.get_store()
        if store is None:
            return False
        try:
            docs = store.similarity_search("test", k=1)
            return len(docs) > 0
        except Exception:
            return False
