"""Retrieval / RAG package.

A lightweight, dependency-free retrieval stack grounds the assistant on the
synthetic county knowledge base. The interfaces are intentionally clean so the
local retriever can be swapped for Azure AI Search in production without touching
the agent layer.
"""

from app.rag.embeddings import EmbeddingClient, get_embedding_client
from app.rag.models import Document, RetrievedChunk
from app.rag.retriever import (
    AzureAISearchRetriever,
    LocalRetriever,
    Retriever,
    get_retriever,
)

__all__ = [
    "AzureAISearchRetriever",
    "Document",
    "EmbeddingClient",
    "LocalRetriever",
    "RetrievedChunk",
    "Retriever",
    "get_embedding_client",
    "get_retriever",
]
