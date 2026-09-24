"""Local, CPU-first multilingual E5 embeddings for Vietnamese knowledge RAG.

Model weights are downloaded from Hugging Face on first use and cached locally.
Document text and queries are embedded in-process and are not sent to a provider.
"""

from __future__ import annotations

import math
from functools import lru_cache
from importlib.metadata import version
from pathlib import Path
from threading import Lock
from typing import Sequence

from .errors import ProviderConfigurationError, ProviderOutputError

LOCAL_E5_MODEL = "intfloat/multilingual-e5-small"
LOCAL_E5_REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
LOCAL_E5_DIMENSIONS = 384
LOCAL_E5_ONNX_FILE = "onnx/model_O4.onnx"
_REGISTRATION_LOCK = Lock()
_MODEL_REGISTERED = False


def _register_model() -> None:
    global _MODEL_REGISTERED
    if _MODEL_REGISTERED:
        return
    with _REGISTRATION_LOCK:
        if _MODEL_REGISTERED:
            return
        try:
            from fastembed import TextEmbedding
            from fastembed.common.model_description import ModelSource, PoolingType
        except ImportError as error:
            raise ProviderConfigurationError(
                "Install the project's fastembed dependency to use local semantic retrieval"
            ) from error
        TextEmbedding.add_custom_model(
            model=LOCAL_E5_MODEL,
            pooling=PoolingType.MEAN,
            normalization=True,
            sources=ModelSource(hf=LOCAL_E5_MODEL),
            dim=LOCAL_E5_DIMENSIONS,
            model_file=LOCAL_E5_ONNX_FILE,
            description="Local multilingual E5 small ONNX model for semantic passage retrieval",
            license="mit",
            size_in_gb=0.24,
        )
        _MODEL_REGISTERED = True


@lru_cache(maxsize=4)
def _load_model(cache_dir: str, threads: int, revision: str, local_files_only: bool):
    _register_model()
    from fastembed import TextEmbedding

    try:
        return TextEmbedding(
            model_name=LOCAL_E5_MODEL,
            cache_dir=cache_dir,
            threads=threads,
            revision=revision,
            local_files_only=local_files_only,
        )
    except Exception as error:
        mode = "local model cache" if local_files_only else "pinned model download/cache"
        raise ProviderConfigurationError(
            f"Could not load {LOCAL_E5_MODEL} from the {mode}"
        ) from error


class FastEmbedLocalEmbeddingProvider:
    """FastEmbed's ONNX Runtime adapter with the E5 query/passage prefixes."""

    provider_name = "fastembed-local"
    dimensions = LOCAL_E5_DIMENSIONS

    def __init__(
        self,
        *,
        cache_dir: Path,
        threads: int = 2,
        revision: str = LOCAL_E5_REVISION,
        local_files_only: bool = False,
    ) -> None:
        if threads < 1:
            raise ProviderConfigurationError("EMBEDDING_THREADS must be positive")
        if revision != LOCAL_E5_REVISION:
            raise ProviderConfigurationError(
                "EMBEDDING_MODEL_REVISION must match the reviewed multilingual E5 weights"
            )
        self.model_name = (
            f"{LOCAL_E5_MODEL}@{revision}:fastembed-{version('fastembed')}:query-passage-v1"
        )
        self._model = _load_model(str(cache_dir.expanduser().resolve()), threads, revision, local_files_only)

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed document passages using E5's required passage prefix."""

        return self._encode([f"passage: {text}" for text in texts])

    def embed_query(self, query: str) -> list[float]:
        """Embed one search query using E5's required query prefix."""

        vectors = self._encode([f"query: {query}"])
        return vectors[0]

    def _encode(self, texts: Sequence[str]) -> list[list[float]]:
        vectors = list(self._model.embed(list(texts), batch_size=32))
        if len(vectors) != len(texts):
            raise ProviderOutputError("Local embedding model returned a mismatched batch length")
        result = [[float(value) for value in vector] for vector in vectors]
        if any(
            len(vector) != self.dimensions
            or not all(math.isfinite(value) for value in vector)
            for vector in result
        ):
            raise ProviderOutputError("Local embedding model returned an invalid vector")
        return result
