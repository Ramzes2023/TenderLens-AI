"""Data contracts for local RAG indexing and retrieval."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DocumentChunk:
    chunk_index: int
    page_number: int
    text: str


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_index: int
    page_number: int
    text: str
    score: float


@dataclass(frozen=True)
class RagAnswer:
    answer: str
    sources: tuple[RetrievedChunk, ...]
