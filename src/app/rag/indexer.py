"""In-memory index over knowledge-base chunks.

Implements a transparent TF-IDF-style keyword ranker with no third-party
dependencies. It is intentionally simple and explainable — appropriate for a
prototype — and sits behind the same `Retriever` interface that an Azure AI Search
implementation would satisfy.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict

from app.rag.models import Chunk, RetrievedChunk

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "is", "are",
    "do", "i", "how", "what", "when", "where", "can", "my", "you", "your", "with",
    "at", "be", "this", "that", "it", "as", "by", "from", "if",
}


def _tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS]


class InMemoryIndex:
    """A small inverted index with TF-IDF cosine scoring."""

    def __init__(self) -> None:
        self._chunks: list[Chunk] = []
        self._tf: list[Counter[str]] = []
        self._df: Counter[str] = Counter()
        self._idf: dict[str, float] = {}

    @property
    def size(self) -> int:
        return len(self._chunks)

    def add(self, chunks: list[Chunk]) -> None:
        for chunk in chunks:
            tokens = _tokenize(chunk.text)
            if not tokens:
                continue
            tf = Counter(tokens)
            self._chunks.append(chunk)
            self._tf.append(tf)
            for term in tf:
                self._df[term] += 1

    def finalize(self) -> None:
        """Compute IDF weights after all chunks are added."""
        n = max(1, len(self._chunks))
        self._idf = {
            term: math.log((1 + n) / (1 + df)) + 1.0 for term, df in self._df.items()
        }

    def _vector(self, tf: Counter[str]) -> dict[str, float]:
        return {term: freq * self._idf.get(term, 0.0) for term, freq in tf.items()}

    def search(self, query: str, top_k: int) -> list[RetrievedChunk]:
        if not self._chunks:
            return []
        q_tokens = _tokenize(query)
        if not q_tokens:
            return []
        q_vec = self._vector(Counter(q_tokens))
        q_norm = math.sqrt(sum(v * v for v in q_vec.values())) or 1.0

        # Gather candidate docs that share at least one query term.
        postings: dict[int, float] = defaultdict(float)
        for i, tf in enumerate(self._tf):
            d_vec = self._vector(tf)
            dot = sum(q_vec[t] * d_vec.get(t, 0.0) for t in q_vec)
            if dot <= 0:
                continue
            d_norm = math.sqrt(sum(v * v for v in d_vec.values())) or 1.0
            postings[i] = dot / (q_norm * d_norm)

        ranked = sorted(postings.items(), key=lambda kv: kv[1], reverse=True)[:top_k]
        return [
            RetrievedChunk(chunk=self._chunks[i], score=round(score, 4))
            for i, score in ranked
        ]
