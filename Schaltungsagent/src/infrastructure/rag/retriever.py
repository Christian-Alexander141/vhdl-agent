from typing import Any

from .vector_store import VectorStoreService


class Retriever:
    def __init__(self, vector_store: VectorStoreService, top_k: int = 5):
        self._vector_store = vector_store
        self._top_k = top_k

    def retrieve(self, query: str) -> list[str]:
        return self._vector_store.similarity_search(query, top_k=self._top_k)

    def retrieve_with_scores(self, query: str) -> list[tuple[str, float]]:
        return []
