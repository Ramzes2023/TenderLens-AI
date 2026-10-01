"""Page-aware bounded chunking for RAG."""
from __future__ import annotations

import re
from collections.abc import Sequence

from .models import DocumentChunk

_SPACE = re.compile(r"[ \t\r\f\v]+")
_BLANKS = re.compile(r"\n{3,}")


def normalize_page(text: str) -> str:
    text = text.replace("\u00a0", " ")
    text = _SPACE.sub(" ", text)
    text = _BLANKS.sub("\n\n", text)
    return text.strip()


def _cut(text: str, start: int, target_end: int) -> int:
    if target_end >= len(text):
        return len(text)
    floor = max(start + 1, target_end - 180)
    segment = text[floor:target_end]
    best = max(segment.rfind(". "), segment.rfind("; "), segment.rfind("\n"), segment.rfind(" "))
    return floor + best + 1 if best >= 0 else target_end


def chunk_pages(page_texts: Sequence[str], chunk_size: int, overlap: int) -> list[DocumentChunk]:
    if chunk_size <= 0 or overlap < 0 or overlap >= chunk_size:
        raise ValueError("Некорректные параметры chunking.")
    chunks: list[DocumentChunk] = []
    index = 0
    for page_number, raw in enumerate(page_texts, start=1):
        text = normalize_page(raw)
        if not text:
            continue
        start = 0
        while start < len(text):
            end = _cut(text, start, min(len(text), start + chunk_size))
            piece = text[start:end].strip()
            if piece:
                chunks.append(DocumentChunk(index, page_number, piece))
                index += 1
            if end >= len(text):
                break
            next_start = max(0, end - overlap)
            if next_start <= start:
                next_start = end
            start = next_start
    return chunks
