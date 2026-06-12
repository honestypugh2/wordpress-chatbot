"""Active demo-site profile route.

Exposes the currently selected demo site (``DEMO_SITE_PROFILE``) so the embedded
widget can self-configure its title, greeting, and county name without rebuilding
the page. This is how the demo switches programmatically between the synthetic
*County of Westvale* site and a generic *customer staging* site.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.agents.site_profiles import effective_allowed_domains, get_site_profile
from app.config import get_settings

router = APIRouter(tags=["site"])


class SiteResponse(BaseModel):
    site: str
    county_name: str
    short_name: str
    title: str
    greeting: str
    retrieval_pattern: str
    allowed_domains: list[str]


@router.get("/site", response_model=SiteResponse, summary="Active demo site profile")
def site() -> SiteResponse:
    """Return the active site profile and effective retrieval pattern."""
    settings = get_settings()
    profile = get_site_profile(settings)
    return SiteResponse(
        site=str(profile.key),
        county_name=profile.county_name,
        short_name=profile.short_name,
        title=profile.title,
        greeting=profile.greeting,
        retrieval_pattern=str(settings.effective_retrieval_pattern),
        allowed_domains=list(effective_allowed_domains(profile, settings)),
    )
