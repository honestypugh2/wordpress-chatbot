"""Tests for retrieval-pattern selection and demo-site switching."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.agents.base import AgentContext
from app.agents.orchestrator import Orchestrator
from app.agents.site_profiles import (
    all_profiles,
    effective_allowed_domains,
    get_site_profile,
)
from app.config import DemoSite, RetrievalPattern, Settings
from app.main import app
from app.rag.models import Chunk, RetrievedChunk

PROJECT_ENDPOINT = "https://acct.services.ai.azure.com/api/projects/county-assistant"
SEARCH_ENDPOINT = "https://county.search.windows.net"

client = TestClient(app)


def _chunk(score: float) -> RetrievedChunk:
    return RetrievedChunk(
        chunk=Chunk(
            chunk_id="c1",
            doc_id="d1",
            title="Permits",
            category="permits",
            text="Apply online for a building permit.",
            url=None,
        ),
        score=score,
    )


# --- effective_retrieval_pattern -------------------------------------------------


def test_default_pattern_is_local() -> None:
    assert Settings(_env_file=None).effective_retrieval_pattern is RetrievalPattern.local


def test_azure_search_degrades_to_local_without_endpoint() -> None:
    s = Settings(
        _env_file=None,
        retrieval_pattern=RetrievalPattern.azure_search,
        azure_search_endpoint="",
    )
    assert s.effective_retrieval_pattern is RetrievalPattern.local


def test_azure_search_active_with_endpoint() -> None:
    s = Settings(
        retrieval_pattern=RetrievalPattern.azure_search,
        azure_search_endpoint=SEARCH_ENDPOINT,
    )
    assert s.effective_retrieval_pattern is RetrievalPattern.azure_search


def test_azure_search_active_via_ai_search_tool_without_endpoint() -> None:
    # Default Pattern 2 path: Foundry AI Search tool needs a connection, not an endpoint.
    s = Settings(
        retrieval_pattern=RetrievalPattern.azure_search,
        azure_search_endpoint="",
        foundry_enabled=True,
        azure_ai_project_endpoint=PROJECT_ENDPOINT,
        azure_search_connection_name="my-search-connection",
    )
    assert s.ai_search_grounding_ready is True
    assert s.effective_retrieval_pattern is RetrievalPattern.azure_search


def test_azure_search_custom_retriever_requires_endpoint() -> None:
    # Opt-in custom retriever path needs a Search endpoint, not a connection.
    s = Settings(
        retrieval_pattern=RetrievalPattern.azure_search,
        azure_search_use_custom_retriever=True,
        azure_search_endpoint="",
        foundry_enabled=True,
        azure_ai_project_endpoint=PROJECT_ENDPOINT,
        azure_search_connection_name="my-search-connection",
    )
    assert s.effective_retrieval_pattern is RetrievalPattern.local
    s2 = Settings(
        retrieval_pattern=RetrievalPattern.azure_search,
        azure_search_use_custom_retriever=True,
        azure_search_endpoint=SEARCH_ENDPOINT,
    )
    assert s2.effective_retrieval_pattern is RetrievalPattern.azure_search


def test_hybrid_active_with_endpoint() -> None:
    s = Settings(
        retrieval_pattern=RetrievalPattern.hybrid,
        azure_search_endpoint=SEARCH_ENDPOINT,
    )
    assert s.effective_retrieval_pattern is RetrievalPattern.hybrid


def test_bing_degrades_to_local_when_not_configured() -> None:
    s = Settings(
        retrieval_pattern=RetrievalPattern.bing,
        bing_grounding_enabled=False,
    )
    assert s.effective_retrieval_pattern is RetrievalPattern.local


def test_bing_active_when_configured() -> None:
    s = Settings(
        retrieval_pattern=RetrievalPattern.bing,
        bing_grounding_enabled=True,
        foundry_enabled=True,
        azure_ai_project_endpoint=PROJECT_ENDPOINT,
        bing_grounding_agent_name="county-assistant-bing-grounding",
    )
    assert s.bing_grounding_ready is True
    assert s.effective_retrieval_pattern is RetrievalPattern.bing


# --- account_endpoint derivation -------------------------------------------------


def test_account_endpoint_derived_from_project_endpoint() -> None:
    s = Settings(
        azure_ai_project_endpoint=PROJECT_ENDPOINT,
        azure_ai_account_endpoint="",
    )
    assert s.account_endpoint == "https://acct.services.ai.azure.com"


def test_account_endpoint_explicit_override_wins() -> None:
    s = Settings(
        azure_ai_project_endpoint=PROJECT_ENDPOINT,
        azure_ai_account_endpoint="https://acct.cognitiveservices.azure.com/",
    )
    assert s.account_endpoint == "https://acct.cognitiveservices.azure.com"


# --- site profiles ---------------------------------------------------------------


def test_default_site_is_westvale() -> None:
    profile = get_site_profile(Settings(demo_site_profile=DemoSite.westvale))
    assert profile.key is DemoSite.westvale
    assert profile.recommended_pattern is RetrievalPattern.hybrid


def test_staging_profile_uses_bing_and_scopes_domains() -> None:
    profile = get_site_profile(Settings(demo_site_profile=DemoSite.staging))
    assert profile.key is DemoSite.staging
    assert profile.recommended_pattern is RetrievalPattern.bing
    assert profile.allowed_domains  # placeholder domains present (sanitized)
    assert not any("ventura" in d for d in profile.allowed_domains)


def test_allowed_domains_runtime_override() -> None:
    s = Settings(
        demo_site_profile=DemoSite.staging,
        bing_allowed_domains="staging.realsite.gov, www.realsite.gov",
    )
    profile = get_site_profile(s)
    assert effective_allowed_domains(profile, s) == (
        "staging.realsite.gov",
        "www.realsite.gov",
    )


def test_allowed_domains_default_to_profile() -> None:
    s = Settings(demo_site_profile=DemoSite.staging, bing_allowed_domains="")
    profile = get_site_profile(s)
    assert effective_allowed_domains(profile, s) == profile.allowed_domains


def test_all_profiles_cover_every_site() -> None:
    profiles = all_profiles()
    assert set(profiles) == set(DemoSite)


def test_site_endpoint_returns_active_profile() -> None:
    resp = client.get("/api/site")
    assert resp.status_code == 200
    body = resp.json()
    assert body["site"] in {s.value for s in DemoSite}
    assert body["title"]
    assert body["greeting"]


# --- hybrid fallback decision ----------------------------------------------------


def test_needs_fallback_when_no_results() -> None:
    ctx = AgentContext(message="x", session_id="s", correlation_id="c")
    assert Orchestrator._needs_fallback(ctx, Settings()) is True


def test_needs_fallback_when_top_score_below_threshold() -> None:
    ctx = AgentContext(message="x", session_id="s", correlation_id="c")
    ctx.retrieved = [_chunk(0.05)]
    s = Settings(hybrid_min_results=1, hybrid_min_score=0.15)
    assert Orchestrator._needs_fallback(ctx, s) is True


def test_no_fallback_when_results_strong() -> None:
    ctx = AgentContext(message="x", session_id="s", correlation_id="c")
    ctx.retrieved = [_chunk(0.9)]
    s = Settings(hybrid_min_results=1, hybrid_min_score=0.15)
    assert Orchestrator._needs_fallback(ctx, s) is False
