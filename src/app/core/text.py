"""Small text utilities shared across agents.

Kept free of web-framework imports so it is safe to import from both the
FastAPI app and the Azure Functions host.
"""

from __future__ import annotations

import re

# Foundry Responses API embeds inline citation markers in the answer text, e.g.
# ``【4:0†source】`` (fullwidth brackets) or ``[4:0†source]``. We surface citations
# separately (as clickable sources), so these raw markers are stripped from the
# answer shown to the user.
_CITATION_MARKER_RE = re.compile(r"[【\[]\s*\d+:\d+\s*†[^】\]]*[】\]]")
_CITATION_MARKER_FALLBACK_RE = re.compile(r"【[^】]*†[^】]*】")
_SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([.,;:!?])")
_MULTISPACE_RE = re.compile(r"[ \t]{2,}")


def strip_citation_markers(text: str) -> str:
    """Remove inline Responses-API citation markers from answer text.

    Examples removed: ``【4:0†source】``, ``[4:0†source]``. Leaves the prose intact
    and tidies up spacing left behind by the removed markers.
    """
    if not text:
        return text
    cleaned = _CITATION_MARKER_RE.sub("", text)
    cleaned = _CITATION_MARKER_FALLBACK_RE.sub("", cleaned)
    cleaned = _MULTISPACE_RE.sub(" ", cleaned)
    cleaned = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", cleaned)
    return cleaned.strip()
