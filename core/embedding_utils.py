import ollama
import math
import logging
from functools import lru_cache

from config.settings import get_settings

_settings = get_settings()


logger = logging.getLogger(__name__)


def _uncached_embedding(text):
    """Cache embeddings for repeated identical strings within and across runs."""
    response = ollama.embeddings(
        model=_settings.embedding_model,
        prompt=text
    )
    return response["embedding"]


# Wrap with LRU cache whose size is sourced from settings (set at import time).
_get_embedding_cached = lru_cache(maxsize=_settings.embedding_cache_size)(_uncached_embedding)


def get_embedding(text):
    normalized_text = " ".join((text or "").split())

    if not normalized_text:
        logger.debug("Received empty text for embedding; returning empty vector.")
        return []

    return _get_embedding_cached(normalized_text)


def cosine_similarity(vec1, vec2):
    dot = sum(a*b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a*a for a in vec1))
    norm2 = math.sqrt(sum(b*b for b in vec2))
    
    if norm1 == 0 or norm2 == 0:
        return 0

    return dot / (norm1 * norm2)