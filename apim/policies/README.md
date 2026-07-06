# APIM AI Gateway — Policy Samples

Azure API Management policy fragments that turn APIM into the **AI Gateway** between
the WordPress experience layer and the Azure AI Foundry intelligence layer.

> All policies are illustrative. Validate against your APIM tier and the current
> policy schema. **No secrets in policy files** — use Named Values backed by Key
> Vault and prefer managed identity. Some AI-gateway policies (token-limit,
> semantic-cache, emit-token-metric) require an APIM tier with AI-gateway support
> and an embeddings/cache backend.

## Files

| File | Purpose |
| --- | --- |
| [aoai-api.applied.xml](aoai-api.applied.xml) | **APPLIED** — the live policy on the AOAI model API (path `/openai`). Fronts the Azure OpenAI model with managed-identity backend auth, `azure-openai-token-limit`, and `azure-openai-emit-token-metric`. This is what makes APIM a *true* GenAI gateway in front of the model. |
| [aoai-api.policy.xml](aoai-api.policy.xml) | **FULL reference** for the AOAI model API — everything in the applied policy plus `azure-openai-semantic-cache-lookup`/`-store` (needs an external Redis cache with RediSearch). |
| [chat-operation.applied.xml](chat-operation.applied.xml) | **APPLIED** — the live policy on the WordPress-facing chat operation (`POST /assistant/chat`): CORS, correlation id, `rate-limit-by-key`, backend routing to the Function, header hygiene. |
| [chat-operation.policy.xml](chat-operation.policy.xml) | **Full** chat-operation reference: CORS, auth mediation, rate limit, token throttle, semantic cache, content-safety hook, correlation, backend routing. |
| [rate-limit.fragment.xml](rate-limit.fragment.xml) | Per-IP burst limiting + per-subscription daily quota. |
| [token-throttle.fragment.xml](token-throttle.fragment.xml) | Token-based throttling + token metrics for FinOps. |
| [semantic-cache.fragment.xml](semantic-cache.fragment.xml) | Semantic cache lookup/store for repeated questions. |
| [content-safety.fragment.xml](content-safety.fragment.xml) | Optional Azure AI Content Safety pre-check (defense in depth). |
| [backend-routing.fragment.xml](backend-routing.fragment.xml) | Backend routing + correlation header propagation + retries. |

## Two gateway layers

The prototype runs APIM as **two** governed surfaces:

1. **WordPress-facing chat API** (`POST /assistant/chat`) → routes to the Azure
   Function backend. Governed by [chat-operation.applied.xml](chat-operation.applied.xml).
2. **AOAI model API** (`/openai`) → routes to the Foundry Azure OpenAI endpoint with
   APIM's **managed identity** (no model key on the wire). Governed by
   [aoai-api.applied.xml](aoai-api.applied.xml). The Function calls chat-completions
   and embeddings **through this API** (see `AZURE_OPENAI_GATEWAY_ENDPOINT` /
   `AZURE_OPENAI_GATEWAY_KEY` in [src/app/config/settings.py](src/app/config/settings.py)),
   so token limits and token metrics apply to every model call.


## How the controls map to requirements

- **Auth mediation** — public widget presents a tightly-scoped product key; APIM
  validates it and swaps in the backend credential so Foundry/backend secrets never
  reach the browser.
- **Token-based throttling** — `azure-openai-token-limit` meters prompt+completion
  tokens per subscription/IP to bound model cost. **Applied** on the AOAI model API
  ([aoai-api.applied.xml](aoai-api.applied.xml), 20k tokens/min) — APIM can read the
  token counts because it fronts the Azure OpenAI response directly.
- **Token metrics** — `azure-openai-emit-token-metric` emits prompt/completion/total
  token metrics to Application Insights (logger `appinsights`). **Applied** on the
  AOAI model API.
- **Managed-identity backend auth** — `authentication-managed-identity` lets APIM call
  the Foundry model endpoint with its **system-assigned identity** (granted *Cognitive
  Services OpenAI User* on the Foundry account), so no model key is stored or sent.
- **Rate limiting** — `rate-limit-by-key` + `quota-by-key` for burst and daily caps.
- **Semantic caching** — `azure-openai-semantic-cache-lookup/store` returns cached
  answers for semantically similar prompts. Present in the **full** AOAI reference
  ([aoai-api.policy.xml](aoai-api.policy.xml)); **not applied** in the prototype
  because it requires an external Redis cache with the RediSearch module.
- **Backend routing** — `set-backend-service` (named backend) with retries.
- **Correlation headers** — `X-Correlation-Id` reused or minted and echoed back.
- **Content safety** — insertion point that calls Azure AI Content Safety and blocks
  high-severity content before the model.

## Named Values to configure (Key Vault-backed)

- `backend-api-token` — credential APIM presents to the backend.
- `content-safety-endpoint`, `content-safety-key` — Content Safety resource.
- Backend `county-backend` and `embeddings-backend` registrations.
- `entra-openid-config`, `entra-audience` — Entra ID OIDC config URL and API
  audience for the per-user JWT attribution path (see below). `entra-audience`
  requires an Entra app registration.

## Per-user cost attribution (capture user identity here)

Per-user identity capture belongs in **these production policies** — not just the
`/ai_demo/apim` illustration copy — so it is governed, versioned, and applied
consistently. The applied AOAI policy
([aoai-api.applied.xml](aoai-api.applied.xml)) already implements this:

1. **Identity resolution.** Resolves a `userId` with precedence **Entra `oid` ›
   `x-user-id` header › subscription id** (previously everything keyed on
   `context.Subscription?.Id`, which is per-team, not per-user).
2. **Per-user metering & metrics.** `azure-openai-token-limit` keys its
   `counter-key` on the resolved `userId`, and `azure-openai-emit-token-metric`
   emits `UserId` / `TeamId` dimensions for chargeback/showback dashboards.
3. **Entra `oid` preferred; `x-user-id` is trusted-proxy only.** The JWT path is
   non-breaking — it runs only when an `Authorization` bearer is present, so
   api-key callers are unaffected. `x-user-id` must never be accepted directly
   from a browser; the WordPress server-side proxy is the correct place to stamp a
   trusted identity.
4. **Reuse via a fragment (recommended next step).** Promote the identity
   resolution into `user-identity.fragment.xml` and `<include-fragment>` it from
   both the AOAI API and the chat operation, mirroring the existing
   `rate-limit.fragment.xml` / `token-throttle.fragment.xml` pattern.

5. **FinOps dashboards (per-user).** The `genai` `azure-openai-emit-token-metric`
   also emits a `ModelName` dimension (the pricing key). Per-user cost views built
   on it live in [../dashboards](../dashboards):
   - [per-user-cost.kql](../dashboards/per-user-cost.kql) — paste-in Azure Monitor
     Workbook queries (spend by user, over time, budget vs actual, team roll-up,
     `oid`→name enrichment); `AppMetrics` + `customMetrics` schema variants.
   - [per-user-finops-dashboard.bicep](../dashboards/per-user-finops-dashboard.bicep)
     — deployable Portal dashboard whose tiles mirror the upstream AI-Gateway FinOps
     dashboard but group by `UserId` (Entra `oid`) instead of `ApimSubscriptionId`.
   Requires `PRICING_CL` seeded with a row per `ModelName` (incl. `model-router`)
   and, for budgets, a `USER_QUOTA_CL` table (`UserId`, `CostQuota`).

> **NOTE — Entra JWT path not yet applied to live.** Applying the JWT path needs
> the `entra-openid-config` and `entra-audience` Named Values, and `entra-audience`
> requires an Entra **app registration**. The current subscription may not grant
> app-registration privileges —
> complete that step in a subscription/tenant where you have admin rights, create
> the Named Values, then re-apply the policy. Until then the live policy runs
> header + subscription attribution only.
