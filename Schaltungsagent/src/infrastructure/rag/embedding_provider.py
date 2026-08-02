import logging
from typing import Any

logger = logging.getLogger(__name__)

_embeddings = None


class EmbeddingProvider:
    def __init__(self, model_name: str = "jina-embeddings-v5-text-small"):
        self._model_name = model_name
        self._embeddings = None

    def get_embeddings(self):
        global _embeddings
        if _embeddings is not None:
            return _embeddings
        try:
            from langchain_huggingface import HuggingFaceEmbeddings
        except ImportError:
            logger.warning("langchain-huggingface not installed")
            return None
        candidates = [self._model_name, "sentence-transformers/all-MiniLM-L6-v2"]
        for model in candidates:
            try:
                _embeddings = HuggingFaceEmbeddings(
                    model_name=model,
                    encode_kwargs={"normalize_embeddings": True},
                )
                self._embeddings = _embeddings
                logger.info("Embeddings loaded: %s", model)
                break
            except Exception as e:
                logger.debug("Embeddings model %s failed: %s", model, e)
                continue
        return _embeddings
