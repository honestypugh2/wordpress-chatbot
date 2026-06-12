# Grounding with Bing Custom Search — limitations for .gov / public-sector sites

> **TL;DR** — Grounding with Bing Custom Search only returns results for domains
> and pages that are **public and already indexed by Bing**. For the typical government /
> county-government scenario (a brand-new or staging site, or a site you want to
> evaluate *before* go-live), that precondition usually isn't met, so the tool
> returns **no results** even though it is configured correctly. For owned content,
> **Azure AI Search RAG (Pattern 2 / Pattern 3)** is the reliable path. This doc
> explains why, what we observed, and how to move forward.

---

## 1. What we provisioned (and verified works)

The Bing infrastructure itself is **fully provisioned and not gated**:

| Item | Value | Status |
|------|-------|--------|
| Bing Custom Search resource | `county-bing-cs` (`Bing.GroundingCustomSearch`, **SKU `G2`**) | ✅ Created |
| Foundry project connection | `county-bing-custom` (`GroundingWithCustomSearch`, ApiKey) | ✅ Created |
| SDK | `azure-ai-projects` 2.2.0 exposes `BingCustomSearchPreviewTool` | ✅ Present |

> **SKU gotcha (not a limitation, just a footgun):** the Custom Search resource
> requires SKU **`G2`**. The standard *Grounding with Bing Search* resource uses
> `G1`. Creating `Bing.GroundingCustomSearch` with `G1` fails with a generic
> `InternalServerError`, which is easy to misread as "the feature is gated." It is
> **not** gated — it just needs `G2`.

So the blocker below is **not** about provisioning or permissions. It is about how
Bing Custom Search sources its results.

---

## 2. The core limitation

Grounding with Bing Custom Search does **not** crawl or read the sites you list. It
filters **Bing's existing public web index** down to the domains in your
configuration. Microsoft's documentation states this directly:

> *"Grounding with Bing Custom Search only returns results for domains and webpages
> that are public and indexed by Bing."*

That single sentence drives every limitation that follows.

### 2.1 Why this hits .gov / public-sector scenarios hard

| Factor | Why it's common in public sector | Effect on Bing Custom Search |
|--------|----------------------------------|------------------------------|
| **Staging / pre-prod sites** | Customers evaluate a chatbot *before* launch, on a staging host | Staging subdomains are usually `noindex` / `robots.txt`-disallowed / auth-gated → **not in Bing's index → zero results** |
| **Newly created or migrated sites** | Site rebuilds, CMS migrations, new county portals | Crawl + index lag is **days to weeks** → freshly published pages are not yet groundable |
| **Shallow index coverage** | Smaller municipal/county sites get crawled less deeply than large commercial sites | Many pages (esp. PDFs, JS-rendered, dynamic service pages) are **missing from the index** |
| **No on-demand indexing** | You can't force Bing to index a page now | You depend entirely on Bing's crawler schedule; Bing Webmaster Tools helps but still has lag and requires domain ownership verification |
| **Data residency / sovereignty** | Government workloads frequently require data to stay in-region / in-boundary | Bing grounding sends queries **outside the Azure compliance boundary**; the Data Protection Addendum (DPA) does **not** apply, and GCC commitments are waived (see §4) |
| **Preview status** | Production launches need supportability | `BingCustomSearchPreviewTool` is **preview** — no production SLA |

### 2.2 What we observed in this prototype

- **County of Westvale** (our created WordPress site) runs locally in Docker and is
  synthetic. Bing has never crawled it → Custom Search returns **nothing** for it.
- **Customer staging site** — a staging subdomain is the textbook case of a host
  Bing typically has **not** indexed (and often is explicitly told not to). Even
  with a perfect configuration + connection, results would be empty or unreliable.

In both demo targets, the precondition ("public and indexed by Bing") is not
satisfied, so a live Pattern 1 demo would show an empty/weak answer — which
misrepresents the architecture rather than showcasing it.

---

## 3. How to move forward (what actually works)

### Option A — Use Azure AI Search RAG for owned content (recommended)

For any site whose content **you own** — which includes both the created site and
the customer's own staging/production WordPress — **Pattern 2 (Azure AI Search via
the Foundry AI Search tool)** or **Pattern 3 (Hybrid)** is the correct primary
pattern:

- **No indexing dependency.** Content is ingested from the **WordPress REST API**
  (structured, no scraping) into an Azure AI Search index. Works on **staging /
  pre-prod / brand-new** sites immediately.
- **Stays in the Azure compliance boundary.** Nothing is sent to Bing; data
  residency is preserved (region-bound Search service).
- **Precise, chunk-level citations** instead of page-level web links.
- **Deterministic + governable** — you control exactly what is searchable.

This is already implemented and is the default for Pattern 2. The `county-kb` index
is populated (keyword + semantic + vector) and ready to demo today.

### Option B — Standard Grounding with Bing Search (whole web)

If the goal is specifically *live public-web* grounding (not domain-restricted), the
standard **Grounding with Bing Search** tool (resource kind `Bing.Grounding`, SKU
`G1`) searches the whole public web and can be biased toward a site via agent
instructions. Trade-offs: **no enforced domain scoping**, and the same compliance /
data-boundary caveats as §4. Only meaningful once the target domain is publicly
indexed.

### Option C — Make Bing Custom Search viable (when a real public domain exists)

Bing Custom Search becomes a good fit when the target is a **public, production,
Bing-indexed** site (e.g., a live county `.gov` / `.org` portal). Prerequisites:

1. **Use the production public domain**, not a staging subdomain.
2. **Verify it's indexed**: run a `site:yourdomain.gov` query on
   [bing.com](https://www.bing.com) and confirm pages appear.
3. If coverage is thin/missing, submit the site + sitemap via
   [Bing Webmaster Tools](https://www.bing.com/webmasters) and allow time for crawl.
4. Create the **configuration instance** in the Foundry portal (resource →
   *Configurations*) with the allowed domains — there is **no ARM / data-plane API**
   for this step; it is portal-only.
5. Accept the **preview** status and the **compliance / data-boundary** trade-offs.

> Because the resource and Foundry connection are already provisioned, switching to
> Custom Search later requires **no code change** — only environment variables
> (`BING_CONNECTION_NAME`, `BING_CUSTOM_SEARCH_INSTANCE_NAME`,
> `BING_GROUNDING_AGENT_NAME`) once a real indexed domain + config instance exist.

---

## 4. Compliance note (independent of indexing)

Even when Bing Custom Search *works*, it is a **First-Party Consumption Service**
governed by the Grounding with Bing terms — **not** the Azure Data Protection
Addendum. Queries flow **outside the Azure compliance and Geo boundary**, and use of
the service **waives** elevated Government Community Cloud (GCC) security and
compliance commitments, including data sovereignty. For many public-sector
workloads this alone makes **Azure AI Search RAG the preferred grounding path**,
regardless of indexing.

---

## 5. Recommendation summary

| Demo target | Owns content? | Public + Bing-indexed? | Recommended pattern |
|-------------|---------------|------------------------|---------------------|
| Created County of Westvale site | Yes | No (local/synthetic) | **Pattern 2 / 3 (Azure AI Search RAG)** |
| Customer staging site | Yes | Usually no (staging `noindex`) | **Pattern 2 / 3 (Azure AI Search RAG)** |
| Customer live production `.gov`/`.org` | Yes | Often yes | Pattern 2/3 for governed answers; **Pattern 1 (Bing Custom Search)** only if web freshness is required and compliance trade-offs are acceptable |

**Bottom line:** keep the Bing Custom Search path in the codebase (it's wired and
ready), but lead the demo and any production rollout with **Azure AI Search RAG**,
which works on owned content immediately, stays inside the Azure compliance
boundary, and produces precise citations.

See also: [docs/retrieval-patterns.md](retrieval-patterns.md),
[docs/security-governance.md](security-governance.md).
