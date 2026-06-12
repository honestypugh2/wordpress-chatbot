"""Demo site profiles \u2014 the single source of truth for per-site presentation
and grounding behaviour, switchable via ``DEMO_SITE_PROFILE``.

Two profiles are demonstrated:

* ``westvale`` — our synthetic *County of Westvale* WordPress site. Can be demoed
  with Azure AI Search (RAG / hybrid) over ingested WordPress content, or with
  Bing Custom Search over its public domain. All content is fictional.
* ``staging``  — a generic *customer staging* WordPress site. To avoid scraping
  or ingesting a site we don't own, this profile grounds answers exclusively via
  **Grounding with Bing Custom Search**. The real staging domain is supplied at
  runtime (``BING_ALLOWED_DOMAINS`` / the Bing Custom Search instance config) and
  is never hard-coded here.

Both sites can demo the Bing Custom Search pattern; the placeholder domains below
are only informational — actual scoping lives in the Bing Custom Search instance.

Keeping this in one module lets the backend (system prompts, greeting), the
front-end widget config, and the site-switch tooling stay consistent.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import DemoSite, RetrievalPattern, Settings, get_settings


@dataclass(frozen=True)
class SiteProfile:
    """Presentation + grounding configuration for one demo site."""

    key: DemoSite
    county_name: str
    short_name: str
    greeting: str
    title: str
    # The grounding pattern this site is designed to demo. The runtime may still
    # override via RETRIEVAL_PATTERN; this is the recommended default.
    recommended_pattern: RetrievalPattern
    # Public domains the Bing Custom Search instance should be scoped to. These
    # are informational placeholders; the real scoping lives in the Bing Custom
    # Search instance and can be overridden at runtime via BING_ALLOWED_DOMAINS.
    allowed_domains: tuple[str, ...]
    system_prompt: str


_WESTVALE = SiteProfile(
    key=DemoSite.westvale,
    county_name="County of Westvale",
    short_name="Westvale",
    greeting=(
        "Hi! I can help with Westvale County services \u2014 permits, taxes, voting, "
        "health, and more. What do you need?"
    ),
    title="County Assistant",
    recommended_pattern=RetrievalPattern.hybrid,
    allowed_domains=("county-portal.example.gov",),
    system_prompt=(
        "You are the County of Westvale Assistant, a helpful, plain-language guide "
        "to county government services. Westvale is a FICTIONAL county and all data "
        "is synthetic. Answer ONLY using the provided context. If the context does "
        "not contain the answer, say you don't have that information and point the "
        "resident to the relevant department. Never provide legal, medical, "
        "financial, or emergency advice; for emergencies tell them to call 911. Be "
        "concise, neutral, and accessible. Cite the source titles you used."
    ),
)

_STAGING = SiteProfile(
    key=DemoSite.staging,
    county_name="County of Lakeside",
    short_name="Lakeside",
    greeting=(
        "Hi! I can help you find information about county services. "
        "Ask me about permits, property taxes, elections, public health, and more."
    ),
    title="County Assistant",
    recommended_pattern=RetrievalPattern.bing,
    allowed_domains=("staging.example.gov", "www.example.gov"),
    system_prompt=(
        "You are a county government virtual assistant. Answer residents' "
        "questions about county services using ONLY grounded web citations "
        "returned by the Bing Custom Search tool (the county's official public "
        "pages). If the tool returns no relevant result, say you couldn't find it "
        "on the county website and suggest contacting the relevant department. "
        "Never provide legal, medical, financial, or emergency advice; for "
        "emergencies tell them to call 911. Be concise, neutral, and accessible. "
        "Always include the source links you used."
    ),
)

_PROFILES: dict[DemoSite, SiteProfile] = {
    DemoSite.westvale: _WESTVALE,
    DemoSite.staging: _STAGING,
}


def get_site_profile(settings: Settings | None = None) -> SiteProfile:
    """Return the active site profile (from ``DEMO_SITE_PROFILE``)."""
    settings = settings or get_settings()
    return _PROFILES[settings.demo_site_profile]


def effective_allowed_domains(
    profile: SiteProfile, settings: Settings | None = None
) -> tuple[str, ...]:
    """Allowed domains for a profile, with a runtime override.

    ``BING_ALLOWED_DOMAINS`` (comma-separated) wins when set, so the real
    customer/staging domain is supplied at deploy time and never hard-coded.
    """
    settings = settings or get_settings()
    override = [d.strip() for d in settings.bing_allowed_domains.split(",") if d.strip()]
    return tuple(override) if override else profile.allowed_domains


def all_profiles() -> dict[DemoSite, SiteProfile]:
    """Return every known site profile (used by site-switch tooling)."""
    return dict(_PROFILES)
