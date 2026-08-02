import logging
from pathlib import Path
from typing import Any

from src.domain.ports import RAGService
from src.domain.models import KnowledgeBundle, CodingRule, ReferenceDesign, DocumentRef
from src.domain_plugins.vhdl import VHDLRAGData
from src.services.rag_pipeline import (
    RAGChatPipeline,
    load_api_key,
    retrieve_context,
    get_vector_store,
    index_documents,
    load_documents_from_directory,
    create_chat_session,
)

logger = logging.getLogger(__name__)

SUPPORTED_RAG_SUFFIXES = {".txt", ".md", ".vhd", ".vhdl", ".json", ".yaml", ".yml", ".csv"}


class VHDLRAGService(RAGService):
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
    ):
        self._rag_data = VHDLRAGData()
        self._pipeline = RAGChatPipeline(
            model=model,
            base_url=base_url,
            embedding_model=embedding_model,
            qdrant_path=qdrant_path,
            data_dir=data_dir,
            memory_dir=memory_dir,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            top_k=top_k,
            api_key=load_api_key(),
        )

    def retrieve_knowledge(self, request: str, domain: str = "vhdl") -> KnowledgeBundle:
        logger.info("RAGChat retrieving knowledge: %s (domain=%s)", request, domain)
        request_lower = request.lower()

        matched = self._keyword_match(request_lower)
        knowledge = self._rag_data.get_knowledge(request)

        if matched:
            logger.info("Matched template: %s", matched)
            knowledge.raw_context.append(f"matched_template: {matched}")

        vector_context = self._pipeline.retrieve_knowledge(request)
        if vector_context:
            logger.info("Vector search returned %d results", len(vector_context))
            knowledge.raw_context.extend(vector_context)

        knowledge.documentation = [
            DocumentRef(title=f"RAG Result {i+1}", source="vector_db", content=c[:500])
            for i, c in enumerate(vector_context)
        ]

        logger.info(
            "RAGChat: %d rules, %d designs, %d vector results",
            len(knowledge.coding_rules),
            len(knowledge.reference_designs),
            len(vector_context),
        )
        return knowledge

    def _keyword_match(self, request_lower: str) -> str | None:
        for template_name, keywords in self._rag_data.TEMPLATE_MAP.items():
            if any(kw in request_lower for kw in keywords):
                return template_name
        return None

    def chat_query(
        self,
        query: str,
        chat_id: str | None = None,
        memory_dir: str | Path | None = None,
        data_dir: str | Path | None = None,
    ) -> str:
        return self._pipeline.query(
            query=query,
            chat_id=chat_id,
            memory_dir=memory_dir,
            data_dir=data_dir,
        )

    def chat_query_with_tools(
        self,
        query: str,
        tools: list | None = None,
        chat_id: str | None = None,
        memory_dir: str | Path | None = None,
        data_dir: str | Path | None = None,
    ) -> str:
        return self._pipeline.query_with_tools(
            query=query,
            tools=tools,
            chat_id=chat_id,
            memory_dir=memory_dir,
            data_dir=data_dir,
        )

    def index_data(self, data_dir: str | Path | None = None) -> int:
        return self._pipeline.index_data(data_dir)

    def create_session(self, chat_id: str | None = None) -> dict:
        return create_chat_session(
            chat_id=chat_id,
            memory_dir=self._pipeline._memory_dir,
        )

    @property
    def pipeline(self) -> RAGChatPipeline:
        return self._pipeline
