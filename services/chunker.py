"""
services/chunker.py
────────────────────
Split text into overlapping token-counted chunks.

Why token-based?
  Character counts are inaccurate — a 300-char chunk can be 60 or 400 tokens
  depending on language. tiktoken counts exactly what OpenAI will charge.

Algorithm: sliding window
  1. Encode full text → token IDs
  2. Slice [start : start+chunk_size]
  3. Advance start by (chunk_size - overlap)
  4. Decode each slice back to string
"""

import logging
from dataclasses import dataclass

import tiktoken

import os

CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "512"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "64"))

logger = logging.getLogger(__name__)

# cl100k_base is shared by gpt-4o, gpt-4o-mini, text-embedding-3-*
_enc = tiktoken.get_encoding("cl100k_base")


@dataclass
class TextChunk:
    index: int
    text: str
    token_count: int


def chunk_text(
    text: str,
    chunk_size: int | None = None,
    overlap: int | None = None,
) -> list[TextChunk]:
    """
    Returns a list of TextChunk objects.
    Empty or whitespace-only text returns [].
    """
    text = text.strip()
    if not text:
        return []

    size = chunk_size or CHUNK_SIZE
    lap = overlap or CHUNK_OVERLAP

    if lap >= size:
        raise ValueError(f"overlap ({lap}) must be less than chunk_size ({size})")

    token_ids = _enc.encode(text)
    total = len(token_ids)

    if total == 0:
        return []

    chunks: list[TextChunk] = []
    start = 0
    idx = 0

    while start < total:
        end = min(start + size, total)
        slice_ids = token_ids[start:end]
        chunk_text_str = _enc.decode(slice_ids)

        chunks.append(
            TextChunk(
                index=idx,
                text=chunk_text_str,
                token_count=len(slice_ids),
            )
        )

        if end == total:
            break

        start += size - lap
        idx += 1

    logger.debug("Chunked %d tokens → %d chunks (size=%d, overlap=%d)", total, len(chunks), size, lap)
    return chunks


def count_tokens(text: str) -> int:
    """Quick token count without chunking."""
    return len(_enc.encode(text))
