"""Gemini embeddings. Public API (embed_documents / embed_query) is model-agnostic."""
import time
from functools import lru_cache

import numpy as np
from google import genai
from google.genai import types
from google.genai.errors import APIError

from app.config import settings

BATCH_SIZE = 20             # smaller batches = fewer tokens per call
MAX_RETRIES = 8
PAUSE_BETWEEN_BATCHES = 3   # seconds; raise if you still see 429s


@lru_cache(maxsize=1)
def _client() -> genai.Client:
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    return genai.Client(api_key=settings.gemini_api_key)


def _normalize(vectors: list[list[float]]) -> list[list[float]]:
    # Truncated Gemini embeddings (e.g. 768-dim) are not pre-normalized.
    arr = np.array(vectors, dtype=np.float32)
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    return (arr / np.clip(norms, 1e-12, None)).tolist()


def _embed(texts: list[str], task_type: str) -> list[list[float]]:
    for attempt in range(MAX_RETRIES):
        try:
            res = _client().models.embed_content(
                model=settings.embedding_model,
                contents=texts,
                config=types.EmbedContentConfig(
                    task_type=task_type,
                    output_dimensionality=settings.embedding_dim,
                ),
            )
            return [e.values for e in res.embeddings]
        except APIError as e:
            # 429 = rate limit, 5xx = transient. Back off long enough to outlast
            # a one-minute quota window: 5s, 10s, 20s, 40s, then 65s.
            if e.code in (429, 500, 503) and attempt < MAX_RETRIES - 1:
                time.sleep(min(5 * 2 ** attempt, 65))
                continue
            raise


def embed_documents(texts: list[str], batch_size: int = BATCH_SIZE) -> list[list[float]]:
    out: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        if i > 0:
            time.sleep(PAUSE_BETWEEN_BATCHES)
        out.extend(_embed(texts[i:i + batch_size], "RETRIEVAL_DOCUMENT"))
    return _normalize(out)


def embed_query(text: str) -> list[float]:
    return _normalize(_embed([text], "RETRIEVAL_QUERY"))[0]
