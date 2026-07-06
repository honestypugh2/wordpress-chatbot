# Cost Model

> **Indicative** cost model to compare the three retrieval patterns and size a
> deployment. Figures are approximate **list** prices for relative comparison
> only — **always confirm in the
> [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/)**
> for your region, currency, and commitment. Prices change and vary by region.
> All County of Westvale content is synthetic.

Cost is dominated by a few components. The retrieval pattern mainly changes
**whether you pay for Azure AI Search**, **whether you pay per Bing grounding
call**, and the **prompt size** sent to the model.

---

## 1. Components and cost drivers

| Component | Billing shape | Driver | Notes |
|-----------|---------------|--------|-------|
| **Azure OpenAI — `gpt-4o-mini`** | Per 1M input/output tokens | Chats × tokens/answer | Low unit cost; RAG sends larger prompts (retrieved chunks) |
| **Azure OpenAI — `text-embedding-3-small`** | Per 1M tokens | Ingest size + (vector) per-query | Very low; mostly a one-off at ingest |
| **Azure AI Search (Basic)** | ~Fixed monthly per service | Tier + replicas/partitions | **Only Patterns 2 & 3.** Roughly fixed regardless of query volume |
| **Grounding with Bing Custom Search** | Per call (metered) | Bing-grounded answers | **Pattern 1** every answer; **Pattern 3** only on fallback. Confirm current rate |
| **API Management** | Per gateway (tier) | SKU | Developer for non-prod (no SLA); StandardV2/Premium for prod |
| **Azure Functions (Flex Consumption)** | Per execution + memory-GB-seconds | Requests + duration | Scale-to-zero; small at demo volumes |
| **Application Insights** | Per GB ingested | Telemetry volume | Sampling controls cost |
| **Key Vault / Storage** | Per operation / per GB | Secrets, deployment package | Negligible at this scale |

---

## 2. Per-pattern comparison

For a fixed chat volume, the **variable** (per-answer) and **fixed** (monthly)
costs differ as follows:

| Pattern | Fixed monthly | Per-answer variable | Best when |
|---------|---------------|---------------------|-----------|
| **1 · Bing Custom Search** | APIM + Function + telemetry (**no Search**) | LLM tokens **+ one Bing grounding call** | Lowest fixed cost; pay per use; site you can't ingest |
| **2 · Azure AI Search (RAG)** | APIM + Function + **Search (Basic)** + telemetry | LLM tokens (larger prompt) + (vector) query embedding | Owned content, precise citations, steady volume |
| **3 · Hybrid** | Same as Pattern 2 (**Search**) | LLM tokens + **Bing call only on fallback** | Best UX on owned site; highest TCO |

**Takeaways**

- **Pattern 1 has the lowest fixed cost** — no Search resource and no ingestion
  job — but adds a per-answer Bing grounding charge.
- **Patterns 2 & 3 add a roughly fixed monthly Azure AI Search cost**, which is
  efficient at higher volumes (the fixed cost amortizes across many queries).
- **Pattern 3** adds Bing charges only when the KB can't answer, so its variable
  cost sits between Patterns 1 and 2 depending on fallback rate.

---

## 3. Worked example (assumptions stated)

> Illustrative only. Replace with calculator output for a quote.

**Assumptions:** 10,000 chats/month; ~1.5k tokens in + 0.4k tokens out per answer
with `gpt-4o-mini`; KB of ~50k tokens embedded once with `text-embedding-3-small`;
APIM **Developer** (non-prod); Azure AI Search **Basic** (1 replica, 1 partition);
Functions Flex Consumption at demo scale; Pattern 3 fallback rate ~20%.

| Line item | Pattern 1 (Bing) | Pattern 2 (RAG) | Pattern 3 (Hybrid) |
|-----------|------------------|-----------------|--------------------|
| LLM tokens (`gpt-4o-mini`) | 10k answers | 10k answers (larger prompt) | 10k answers |
| Embeddings | — | one-off ingest (+ optional per-query) | one-off ingest (+ optional per-query) |
| Azure AI Search (Basic) | **—** | fixed monthly | fixed monthly |
| Bing grounding calls | 10,000 | — | ~2,000 (20% fallback) |
| APIM (Developer) | fixed | fixed | fixed |
| Functions | usage | usage | usage |
| Telemetry | small | small | small |
| **Cost shape** | **Lowest fixed + highest Bing usage** | **Fixed Search + low variable** | **Fixed Search + some Bing** |

Plug the token, Search-tier, Bing-call, APIM-SKU, and Functions numbers into the
calculator to turn this into currency.

---

## 4. Levers to reduce cost

- **Pick the right pattern per site.** The staging site (can't ingest) → Pattern 1;
  Westvale (owned, steady) → Pattern 2 or 3.
- **Right-size APIM.** Developer for demos/non-prod; move to StandardV2 only for
  production SLAs.
- **Right-size Search.** Basic is sufficient for a single county KB; scale replicas
  only for availability/throughput needs.
- **Trim prompts (RAG).** Lower `RAG_TOP_K` and chunk size to send fewer tokens to
  the model.
- **Tune hybrid fallback.** Raise `HYBRID_MIN_SCORE` / `HYBRID_MIN_RESULTS` to fall
  back to Bing less often (lower Bing spend, but more "not found"); lower them for
  the opposite trade-off.
- **Sample telemetry.** Reduce Application Insights ingestion with sampling.
- **Scale-to-zero compute.** Flex Consumption already idles to zero between bursts.

See trade-offs in [docs/retrieval-patterns.md](docs/retrieval-patterns.md) and the
SKU defaults in [infra/main.bicep](infra/main.bicep).

---

## 5. Alternative: secure-baseline cost model

The sections above model the **lean** topology (public APIM, no edge). This section
mirrors the **secure-baseline** option, which adds an **Application Gateway
WAF_v2 edge**, **private endpoints**, **DNS/networking**, and a **Defender/governance**
allowance, and assumes **API Management Basic**. It is the costed counterpart to the
[advanced-architecture-apim-landing-zone](diagrams/advanced-architecture-apim-landing-zone.drawio)
diagram. Use this option when secure ingress + private connectivity are required.

> **Indicative list prices** for planning comparison only — confirm in the
> [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/) for
> your region, currency, and commitment. All content is synthetic.

