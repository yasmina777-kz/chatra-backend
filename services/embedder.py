"""
services/embedder.py
─────────────────────
Generate embeddings via OpenAI text-embedding-3-small.

Cost: ~$0.00002 / 1K tokens (100× cheaper than ada-002).
Dimension: 1536.

Batching:
  OpenAI accepts up to 2048 inputs per request.
  We batch in groups of 512 to stay well under limits.
"""

import logging
from openai import AsyncOpenAI

import os

EMBED_MODEL = os.getenv("EMBED_MODEL", "text-embedding-3-small")

logger = logging.getLogger(__name__)

_BATCH_SIZE = 512


def _get_client() -> AsyncOpenAI:
    """Create OpenAI client with key read at call time (not at import)."""
    key = os.getenv("OPENAI_API_KEY", "")
    if not key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Please add it to your .env file: OPENAI_API_KEY=sk-..."
        )
    return AsyncOpenAI(api_key=key)


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    Embed a list of strings.
    Returns a list of float vectors in the same order as input.
    """
    if not texts:
        return []

    all_embeddings: list[list[float]] = []
    client = _get_client()

    for batch_start in range(0, len(texts), _BATCH_SIZE):
        batch = texts[batch_start : batch_start + _BATCH_SIZE]

        response = await client.embeddings.create(
            model=EMBED_MODEL,
            input=batch,
            encoding_format="float",
        )

        # API guarantees order matches input
        batch_embeddings = [item.embedding for item in response.data]
        all_embeddings.extend(batch_embeddings)

        logger.debug(
            "Embedded batch %d–%d (%d texts)",
            batch_start,
            batch_start + len(batch) - 1,
            len(batch),
        )

    return all_embeddings


async def embed_query(text: str) -> list[float]:
    """Embed a single query string. Kept separate for clarity."""
    client = _get_client()
    result = await client.embeddings.create(
        model=EMBED_MODEL,
        input=[text],
        encoding_format="float",
    )
    return result.data[0].embedding


# ── Synchronous variants (for use from sync FastAPI routes) ───────────────────

import httpx as _httpx


def embed_texts_sync(texts: list[str]) -> list[list[float]]:
    """Synchronous batch embed — used during file ingest from sync route."""
    if not texts:
        return []

    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Please add it to your .env file: OPENAI_API_KEY=sk-..."
        )

    all_embeddings: list[list[float]] = []

    for batch_start in range(0, len(texts), _BATCH_SIZE):
        batch = texts[batch_start: batch_start + _BATCH_SIZE]

        with _httpx.Client(timeout=60.0) as client:
            resp = client.post(
                "https://api.openai.com/v1/embeddings",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={"model": EMBED_MODEL, "input": batch, "encoding_format": "float"},
            )

        if not resp.is_success:
            raise RuntimeError(f"Embedding API error {resp.status_code}: {resp.text[:200]}")

        data = resp.json()["data"]
        data.sort(key=lambda x: x["index"])
        all_embeddings.extend([item["embedding"] for item in data])

    return all_embeddings


def embed_query_sync(text: str) -> list[float]:
    """Synchronous single-query embed — used in retriever."""
    return embed_texts_sync([text])[0]
