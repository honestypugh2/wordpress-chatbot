"""Tests for the RAG retrieval layer over the synthetic county KB."""

from __future__ import annotations

from app.rag import get_retriever


def test_index_has_chunks() -> None:
    retriever = get_retriever()
    assert retriever.chunk_count > 0


def test_permit_query_retrieves_permit_doc() -> None:
    retriever = get_retriever()
    results = retriever.search("how do I apply for a building permit and the fee")
    assert results, "expected at least one hit"
    top_categories = {r.chunk.category for r in results}
    assert "permits" in top_categories


def test_tax_query_retrieves_tax_doc() -> None:
    retriever = get_retriever()
    results = retriever.search("when is property tax due")
    assert results
    assert any(r.chunk.category == "taxes" for r in results)
