"""RAG data models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Document(BaseModel):
    """A source document loaded from the knowledge base."""

    doc_id: str
    title: str
    category: str
    text: str
    department: str | None = None
    url: str | None = None


class Chunk(BaseModel):
    """A chunk of a document used for retrieval/indexing."""

    chunk_id: str
    doc_id: str
    title: str
    category: str
    text: str
    url: str | None = None


class RetrievedChunk(BaseModel):
    """A chunk returned from retrieval with a relevance score."""

    chunk: Chunk
    score: float = Field(ge=0.0)
