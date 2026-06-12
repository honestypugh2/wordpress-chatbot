"""Document loading and chunking.

Loads Markdown documents with simple YAML-style front matter from the synthetic
county knowledge base and splits them into overlapping word-based chunks. This is
deliberately dependency-free so the prototype runs anywhere; production should use
a richer splitter and embeddings via Azure AI Search.
"""

from __future__ import annotations

from pathlib import Path

from app.rag.models import Chunk, Document


def _parse_front_matter(raw: str) -> tuple[dict[str, str], str]:
    """Parse a leading '---' front-matter block. Returns (meta, body)."""
    if not raw.startswith("---"):
        return {}, raw
    parts = raw.split("---", 2)
    if len(parts) < 3:
        return {}, raw
    meta: dict[str, str] = {}
    for line in parts[1].strip().splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()
    return meta, parts[2].strip()


def load_documents(kb_path: str | Path) -> list[Document]:
    """Load all Markdown documents under the knowledge-base directory."""
    base = Path(kb_path)
    docs: list[Document] = []
    if not base.exists():
        return docs

    for md in sorted(base.glob("*.md")):
        raw = md.read_text(encoding="utf-8")
        meta, body = _parse_front_matter(raw)
        docs.append(
            Document(
                doc_id=meta.get("doc_id", md.stem),
                title=meta.get("title", md.stem.replace("-", " ").title()),
                category=meta.get("category", "general"),
                department=meta.get("department"),
                url=meta.get("url"),
                text=body,
            )
        )
    return docs


def chunk_document(doc: Document, *, chunk_size: int, overlap: int) -> list[Chunk]:
    """Split a document into overlapping word-based chunks."""
    words = doc.text.split()
    if not words:
        return []

    size = max(50, chunk_size)
    step = max(1, size - max(0, overlap))
    chunks: list[Chunk] = []
    for index, start in enumerate(range(0, len(words), step)):
        window = words[start : start + size]
        if not window:
            break
        chunks.append(
            Chunk(
                chunk_id=f"{doc.doc_id}::{index}",
                doc_id=doc.doc_id,
                title=doc.title,
                category=doc.category,
                url=doc.url,
                text=" ".join(window),
            )
        )
        if start + size >= len(words):
            break
    return chunks
