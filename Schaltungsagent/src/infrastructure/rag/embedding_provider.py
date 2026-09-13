import logging
import os

logger = logging.getLogger(__name__)

_embeddings = None


def _load_local_snapshot(model_name: str, cache_dir: str) -> str | None:
    """Resolve a complete local HF snapshot without contacting the network."""
    try:
        from huggingface_hub import snapshot_download
        return snapshot_download(
            repo_id=model_name,
            cache_dir=cache_dir,
            local_files_only=True,
        )
    except Exception:
        return None


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

        # Persistent cache directory for embedding models
        cache_dir = os.path.expanduser("~/.cache/vhdl-agent/embeddings")
        os.makedirs(cache_dir, exist_ok=True)

        candidates = [self._model_name, "sentence-transformers/all-MiniLM-L6-v2"]
        for model in candidates:
            local_snapshot = _load_local_snapshot(model, cache_dir)
            if local_snapshot:
                try:
                    _embeddings = HuggingFaceEmbeddings(
                        model_name=local_snapshot,
                        cache_folder=cache_dir,
                        encode_kwargs={"normalize_embeddings": True},
                        model_kwargs={"local_files_only": True},
                    )
                    self._embeddings = _embeddings
                    logger.info("Embeddings reused from local cache: %s", model)
                    return _embeddings
                except Exception as e:
                    logger.debug("Cached embedding model %s could not be loaded; attempting download: %s", model, e)

            try:
                from huggingface_hub import snapshot_download
                local_snapshot = snapshot_download(
                    repo_id=model,
                    cache_dir=cache_dir,
                    local_files_only=False,
                )
                _embeddings = HuggingFaceEmbeddings(
                    model_name=local_snapshot,
                    cache_folder=cache_dir,
                    encode_kwargs={"normalize_embeddings": True},
                    model_kwargs={"local_files_only": True},
                )
                self._embeddings = _embeddings
                logger.info("Embeddings downloaded once and cached locally: %s (cache: %s)", model, cache_dir)
                return _embeddings
            except Exception as e:
                logger.debug("Embeddings model %s failed: %s", model, e)
                continue
        return _embeddings
