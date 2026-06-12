"""Provision the Azure AI Search index and upload the county knowledge base.

This script creates (or updates) a keyword + semantic search index and uploads
the synthetic county knowledge base as searchable chunks, matching the schema the
`AzureAISearchRetriever` expects.

When embeddings are configured (``RAG_VECTOR_ENABLED=true`` and an embedding
deployment reachable via the Foundry project), it also adds a vector field plus an
HNSW profile and embeds each chunk — enabling hybrid (keyword + vector) retrieval.

Authentication:
    Prefers managed identity / Azure CLI login via `DefaultAzureCredential`.
    Set ``AZURE_SEARCH_API_KEY`` only if you must use key-based auth.

Usage:
    # Requires the optional dependencies:  uv sync --extra rag
    export AZURE_SEARCH_ENDPOINT="https://<your-search>.search.windows.net"
    export AZURE_SEARCH_INDEX="county-kb"
    # Optional, for hybrid retrieval:
    export RAG_VECTOR_ENABLED="true"
    export AZURE_AI_PROJECT_ENDPOINT="https://<acct>.services.ai.azure.com/api/projects/<proj>"
    export AZURE_EMBEDDING_DEPLOYMENT="text-embedding-3-small"
    uv run python scripts/index_kb_to_search.py
"""

from __future__ import annotations

import sys

from app.config import Settings, get_settings
from app.rag.chunking import chunk_document, load_documents
from app.rag.embeddings import VECTOR_FIELD, get_embedding_client

SEMANTIC_CONFIG_NAME = "county-semantic"
VECTOR_PROFILE_NAME = "county-hnsw"
VECTOR_ALGORITHM_NAME = "county-hnsw-algo"
VECTOR_VECTORIZER_NAME = "county-aoai-vectorizer"


def _build_credential(api_key: str) -> object:
    if api_key:
        from azure.core.credentials import AzureKeyCredential

        return AzureKeyCredential(api_key)
    from azure.identity import DefaultAzureCredential

    return DefaultAzureCredential()


def _ensure_index(settings: Settings, credential: object, *, with_vectors: bool) -> None:
    """Create or update the index definition (idempotent)."""
    from azure.search.documents.indexes import SearchIndexClient
    from azure.search.documents.indexes.models import (
        AzureOpenAIVectorizer,
        AzureOpenAIVectorizerParameters,
        HnswAlgorithmConfiguration,
        SearchableField,
        SearchField,
        SearchFieldDataType,
        SearchIndex,
        SemanticConfiguration,
        SemanticField,
        SemanticPrioritizedFields,
        SemanticSearch,
        SimpleField,
        VectorSearch,
        VectorSearchProfile,
    )

    fields: list[object] = [
        SimpleField(name="chunk_id", type=SearchFieldDataType.String, key=True),
        SimpleField(name="doc_id", type=SearchFieldDataType.String, filterable=True),
        SearchableField(name="title", type=SearchFieldDataType.String),
        SearchField(
            name="category",
            type=SearchFieldDataType.String,
            filterable=True,
            facetable=True,
        ),
        SearchableField(name="content", type=SearchFieldDataType.String),
        SimpleField(name="url", type=SearchFieldDataType.String),
    ]

    vector_search = None
    if with_vectors:
        fields.append(
            SearchField(
                name=VECTOR_FIELD,
                type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                searchable=True,
                vector_search_dimensions=settings.azure_embedding_dimensions,
                vector_search_profile_name=VECTOR_PROFILE_NAME,
            )
        )
        # Attach a query-time AzureOpenAIVectorizer so the index can embed search
        # text itself. This is required by the Foundry AI Search tool's
        # ``vector_semantic_hybrid`` / ``vector`` query types (Pattern 2). The
        # Search service authenticates to Azure OpenAI with its managed identity
        # (needs the "Cognitive Services OpenAI User" role on the AI account).
        vectorizers = None
        if settings.openai_endpoint:
            vectorizers = [
                AzureOpenAIVectorizer(
                    vectorizer_name=VECTOR_VECTORIZER_NAME,
                    parameters=AzureOpenAIVectorizerParameters(
                        resource_url=settings.openai_endpoint,
                        deployment_name=settings.azure_embedding_deployment,
                        model_name=settings.azure_embedding_deployment,
                    ),
                )
            ]
        vector_search = VectorSearch(
            algorithms=[HnswAlgorithmConfiguration(name=VECTOR_ALGORITHM_NAME)],
            profiles=[
                VectorSearchProfile(
                    name=VECTOR_PROFILE_NAME,
                    algorithm_configuration_name=VECTOR_ALGORITHM_NAME,
                    vectorizer_name=(
                        VECTOR_VECTORIZER_NAME if vectorizers else None
                    ),
                )
            ],
            vectorizers=vectorizers,
        )

    semantic = SemanticSearch(
        configurations=[
            SemanticConfiguration(
                name=SEMANTIC_CONFIG_NAME,
                prioritized_fields=SemanticPrioritizedFields(
                    title_field=SemanticField(field_name="title"),
                    content_fields=[SemanticField(field_name="content")],
                    keywords_fields=[SemanticField(field_name="category")],
                ),
            )
        ]
    )

    index = SearchIndex(
        name=settings.azure_search_index,
        fields=fields,  # type: ignore[arg-type]
        semantic_search=semantic,
        vector_search=vector_search,
    )
    client = SearchIndexClient(
        endpoint=settings.azure_search_endpoint,
        credential=credential,  # type: ignore[arg-type]
    )
    client.create_or_update_index(index)
    mode = "keyword+semantic+vector" if with_vectors else "keyword+semantic"
    print(f"[ok] index ready: {settings.azure_search_index} ({mode})")


def _upload_documents(settings: Settings, credential: object, *, with_vectors: bool) -> int:
    """Chunk the KB and upload documents. Returns the number uploaded."""
    from azure.search.documents import SearchClient

    docs = load_documents(settings.rag_kb_path)
    payload: list[dict[str, object]] = []
    texts: list[str] = []
    for doc in docs:
        for chunk in chunk_document(
            doc,
            chunk_size=settings.rag_chunk_size,
            overlap=settings.rag_chunk_overlap,
        ):
            payload.append(
                {
                    "chunk_id": chunk.chunk_id.replace("::", "_"),
                    "doc_id": chunk.doc_id,
                    "title": chunk.title,
                    "category": chunk.category,
                    "content": chunk.text,
                    "url": chunk.url or "",
                }
            )
            texts.append(chunk.text)

    if not payload:
        print("[warn] no documents found to upload")
        return 0

    if with_vectors:
        embedder = get_embedding_client()
        vectors = embedder.embed(texts)
        if len(vectors) != len(payload):
            print("[warn] embedding count mismatch; uploading without vectors")
        else:
            for record, vector in zip(payload, vectors, strict=True):
                record[VECTOR_FIELD] = vector
            print(f"[ok] embedded {len(vectors)} chunks ({embedder.dimensions} dims)")

    client = SearchClient(
        endpoint=settings.azure_search_endpoint,
        index_name=settings.azure_search_index,
        credential=credential,  # type: ignore[arg-type]
    )
    client.upload_documents(documents=payload)
    print(f"[ok] uploaded {len(payload)} chunks from {len(docs)} documents")
    return len(payload)


def main() -> int:
    settings = get_settings()
    if not settings.azure_search_endpoint:
        print("error: AZURE_SEARCH_ENDPOINT is not set", file=sys.stderr)
        return 2

    with_vectors = settings.rag_vector_enabled
    if with_vectors and not settings.embeddings_ready:
        print(
            "warning: RAG_VECTOR_ENABLED is set but no embedding deployment is "
            "reachable (AZURE_AI_PROJECT_ENDPOINT/AZURE_EMBEDDING_DEPLOYMENT). "
            "Falling back to keyword+semantic only.",
            file=sys.stderr,
        )
        with_vectors = False

    try:
        credential = _build_credential(settings.azure_search_api_key)
        _ensure_index(settings, credential, with_vectors=with_vectors)
        _upload_documents(settings, credential, with_vectors=with_vectors)
    except ImportError:
        print(
            "error: Azure SDKs not installed. Run: uv sync --extra rag",
            file=sys.stderr,
        )
        return 3

    print(
        "[done] Set AZURE_SEARCH_SEMANTIC_CONFIG="
        f"{SEMANTIC_CONFIG_NAME} to enable semantic ranking at query time."
    )
    if with_vectors:
        print("[done] Hybrid retrieval enabled (set RAG_VECTOR_ENABLED=true on the backend).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
