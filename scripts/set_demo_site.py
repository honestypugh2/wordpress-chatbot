"""Switch the active demo WordPress site (and recommended retrieval pattern).

Two demo sites are supported:

* ``westvale`` \u2014 our synthetic *County of Westvale* site (default). Recommended
  pattern: ``hybrid`` (Azure AI Search RAG over ingested WordPress content, with
  Bing Custom Search fallback). Can also demo the ``bing`` pattern.
* ``staging``  — a generic *customer staging* WordPress site. Recommended pattern:
  ``bing`` (Grounding with Bing Custom Search over its public domain — no
  scraping/ingestion). The real staging domain is supplied at runtime via
  ``BING_ALLOWED_DOMAINS`` / the Bing Custom Search instance, never hard-coded.

Both sites can demo the Bing Custom Search pattern (``--pattern bing``).

This prints the environment variables to apply. With ``--write <file>`` it also
upserts them into a dotenv-style file (e.g. ``.env`` or ``functionapp/.env``) so a
local run or the Azure Function picks them up.

Usage:
    uv run python scripts/set_demo_site.py staging
    uv run python scripts/set_demo_site.py westvale --pattern azure_search
    uv run python scripts/set_demo_site.py westvale --pattern bing
    uv run python scripts/set_demo_site.py staging --write .env
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.agents.site_profiles import all_profiles, get_site_profile
from app.config import DemoSite, RetrievalPattern, get_settings


def _upsert_dotenv(path: Path, values: dict[str, str]) -> None:
    """Insert or update ``KEY=value`` lines in a dotenv-style file."""
    existing: list[str] = []
    if path.exists():
        existing = path.read_text(encoding="utf-8").splitlines()
    keys = set(values)
    kept = [
        line
        for line in existing
        if "=" not in line or line.split("=", 1)[0].strip() not in keys
    ]
    kept.extend(f"{k}={v}" for k, v in values.items())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(kept) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Switch the active demo site.")
    parser.add_argument(
        "site",
        choices=[s.value for s in DemoSite],
        help="Demo site to activate.",
    )
    parser.add_argument(
        "--pattern",
        choices=[p.value for p in RetrievalPattern],
        default=None,
        help="Override the retrieval pattern (defaults to the site's recommended one).",
    )
    parser.add_argument(
        "--write",
        metavar="DOTENV",
        default=None,
        help="Upsert the variables into this dotenv file (e.g. .env).",
    )
    args = parser.parse_args(argv)

    site = DemoSite(args.site)
    profile = all_profiles()[site]
    pattern = RetrievalPattern(args.pattern) if args.pattern else profile.recommended_pattern

    values = {
        "DEMO_SITE_PROFILE": site.value,
        "RETRIEVAL_PATTERN": pattern.value,
    }
    if pattern in (RetrievalPattern.bing, RetrievalPattern.hybrid):
        values["BING_GROUNDING_ENABLED"] = "true"

    print(f"# Active demo site: {profile.county_name} ({site.value})")
    print(f"# Recommended pattern: {profile.recommended_pattern.value}; using: {pattern.value}")
    print(f"# Allowed domains: {', '.join(profile.allowed_domains)}")
    for key, value in values.items():
        print(f"export {key}={value}")

    if args.write:
        target = Path(args.write)
        _upsert_dotenv(target, values)
        print(f"\n# Wrote {len(values)} variable(s) to {target}")

    # Reflect what the backend would resolve given current settings.
    settings = get_settings()
    active = get_site_profile(settings)
    print(
        f"\n# Current process sees: site={active.key.value}, "
        f"effective_pattern={settings.effective_retrieval_pattern.value}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
