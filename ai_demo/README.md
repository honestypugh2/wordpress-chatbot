# Per-User Cost Attribution — Identity + AI Gateway (APIM)

Goal: attribute **token usage and cost to individual users**, then build
chargeback/showback dashboards. The pattern is **identity + gateway**: every model
call flows through the APIM AI Gateway, which captures *who* made the call and
*how many tokens* it cost, and emits that record to Azure Monitor / Log Analytics.

```
 user identity ──▶ APIM AI Gateway ──▶ Foundry model
      │                  │                   │
 x-user-id /        resolves identity    returns token
 Entra JWT          + reads token usage  usage per request
                    │
                    ├─ azure-openai-emit-token-metric (UserId dim) ─▶ App Insights ─▶ Log Analytics
                    └─ trace (per-user record) ───────────────────▶ Log Analytics (ApiManagementGatewayLogs)
```

Why the gateway (not the app) owns this: APIM is the single hop that sees **both**
the caller identity and the model's token usage, and the caller cannot tamper with
what APIM emits. App-side logging is best-effort and spoofable; gateway-side logging
is authoritative.

## Files

| File | Purpose |
| --- | --- |
| [per_user_cost_attribution.py](per_user_cost_attribution.py) | Client demo: passes user identity, reads token usage per request, builds a per-user cost record, and (optionally) ships it to Log Analytics. |
| [apim/per-user-cost-attribution.policy.xml](apim/per-user-cost-attribution.policy.xml) | Gateway policy: resolves user identity (Entra `oid` › `x-user-id` › subscription), per-user token limit, emits per-user token metric + structured log. |

## How user identity is captured (three options)

| Method | How | When to use |
| --- | --- | --- |
| **Entra ID** | `validate-jwt` then read the `oid` claim from the bearer token | End users sign in with Entra (SSO). Strongest — tamper-proof. |
| **Custom header** | `x-user-id` header set by a trusted server-side proxy | App manages its own user ids; calls go through your backend (e.g. the WordPress proxy), not the browser. |
| **API key** | `context.Subscription.Id` (per-consumer fallback) | One key per user/app, or as a coarse fallback. |

The policy uses precedence **Entra `oid` › `x-user-id` › subscription id**, so you can
mix methods and migrate from header-based to Entra-based without changing dashboards.

> Security note: never trust `x-user-id` straight from a browser — end users can
> forge it. It is safe only when set by a trusted server-side component (your proxy
> validates the session, then stamps `x-user-id`). For zero-trust end-to-end
> attribution, use the Entra JWT path.

## Step-by-step

### 1. Run the client demo (works today)

```bash
source ../.venv/bin/activate
python per_user_cost_attribution.py
```

Each user prints a per-user cost record with `total_tokens` and `estimated_cost_usd`.
This proves the identity → gateway → token-usage loop end-to-end.

### 2. Gateway policy — already applied to the live `aoai` API

The per-user policy is **live** on the `aoai` API (path `/openai`) in
`wpcounty-dev-apim-mro5df`. The governed source of truth is
[apim/policies/aoai-api.applied.xml](../apim/policies/aoai-api.applied.xml) — it
includes managed-identity backend auth, a **per-user** token limit
(`counter-key` = resolved `userId`), and `azure-openai-emit-token-metric` with
`UserId` / `TeamId` dimensions. The demo copy
[apim/per-user-cost-attribution.policy.xml](apim/per-user-cost-attribution.policy.xml)
is illustrative only.

Verified live: a call with `x-user-id: alice@county.gov` returns `200`, echoes
`x-user-id: alice@county.gov`, and meters tokens in alice's own bucket; a
different `x-user-id` gets a separate bucket.

To re-apply after edits (requires `az login`):

```bash
SUB=$(az account show --query id -o tsv)
python3 -c "import json;xml=open('../apim/policies/aoai-api.applied.xml').read();json.dump({'properties':{'format':'rawxml','value':xml}},open('/tmp/body.json','w'))"
az rest --method put \
  --url "https://management.azure.com/subscriptions/$SUB/resourceGroups/rg-county-sc/providers/Microsoft.ApiManagement/service/wpcounty-dev-apim-mro5df/apis/aoai/policies/policy?api-version=2022-08-01" \
  --headers "Content-Type=application/json" --body @/tmp/body.json
```

### 3. Entra ID path — enabled in policy, **not yet applied to live** ⚠️

The Entra JWT path is **enabled in the policy file**
([apim/policies/aoai-api.applied.xml](../apim/policies/aoai-api.applied.xml)): a
`<choose>` validates the bearer token and attributes by the tamper-proof `oid`
**only when an `Authorization` header is present**, so existing api-key callers are
unaffected. Callers send `Authorization: Bearer <token>` to be attributed by `oid`.

> **⚠️ NOTE — app-registration prerequisite.**
> Applying the JWT path to the live API requires two APIM **Named Values**:
> `entra-openid-config` and `entra-audience`. APIM resolves Named-Value references
> at apply time, so the policy can only be pushed **after** they exist.
> `entra-audience` requires an Entra ID **app registration** for this API
> (Application ID URI / client id). The subscription here may **not** grant
> app-registration privileges. **Complete this step in an
> Azure subscription/tenant where you have admin rights for app registrations**,
> then create the Named Values and re-apply the policy (step 2):
>
> ```bash
> # In an admin-capable tenant:
> # 1. Register an app for this API, set an Application ID URI (the audience).
> # 2. Create the two Named Values in APIM:
> TENANT=$(az account show --query tenantId -o tsv)
> az apim nv create -g rg-county-sc --service-name wpcounty-dev-apim-mro5df \
>   --named-value-id entra-openid-config --display-name entra-openid-config \
>   --value "https://login.microsoftonline.com/$TENANT/v2.0/.well-known/openid-configuration"
> az apim nv create -g rg-county-sc --service-name wpcounty-dev-apim-mro5df \
>   --named-value-id entra-audience --display-name entra-audience \
>   --value "<application-id-uri-or-client-id>"
> # 3. Re-apply apim/policies/aoai-api.applied.xml (see step 2).
> ```
>
> Until then the live policy runs **header + subscription** attribution only.

### 4. Send gateway logs to Log Analytics

1. **APIM → Monitoring → Diagnostic settings → Add** → send `Logs` (Gateway logs)
   and `AllMetrics` to your **Log Analytics workspace**.
2. The `<trace severity="information">` records and `emit-token-metric` data become
   queryable in the workspace within a few minutes.

### 5. (Optional) App-side push to Log Analytics

If you also want the *client* to write records (no AI-gateway tier, or extra app
telemetry), set these env vars and the demo will use the **Logs Ingestion API**:

```bash
# Requires: uv add azure-monitor-ingestion azure-identity
# Identity needs 'Monitoring Metrics Publisher' on the Data Collection Rule.
LOGS_DCR_ENDPOINT="https://<dce>.<region>.ingest.monitor.azure.com"
LOGS_DCR_IMMUTABLE_ID="dcr-xxxxxxxxxxxxxxxx"
LOGS_DCR_STREAM="Custom-AIUsage_CL"
```

### 6. View per-user attribution & chargeback in the Azure portal

> **Where are `UserId` / `TeamId` in the portal?**
>
> | Portal location | Per-user visible? |
> | --- | --- |
> | **APIM resource → Metrics** blade (platform metrics) | ❌ No. Only APIM platform metrics (Requests, Capacity, Duration…). The token metric is a *custom* metric, not a platform metric. |
> | **Application Insights → Metrics** explorer (namespace `genai`, metric *Total Tokens*) | ⚠️ Shows totals, but you **cannot split by `UserId`/`TeamId`** unless custom-metric dimensions are enabled (see 6c). |
> | **Application Insights / Log Analytics → Logs** | ✅ **Yes** — but the table name differs by blade (see below). |
>
> Use the **Logs** path (6a) for attribution and chargeback. The per-user policy
> emits to Application Insights (`wpcounty-dev-appi`), which is workspace-based and
> writes into the `wpcounty-dev-law` Log Analytics workspace.
>
> **⚠️ Table name depends on which Logs blade you open** (this is the cause of the
> `Failed to resolve table or column expression named 'AppMetrics'` error):
>
> | Open Logs from… | Schema | Metric table | Dimensions field |
> | --- | --- | --- | --- |
> | **Application Insights** resource (`wpcounty-dev-appi`) | classic App Insights | `customMetrics` | `customDimensions` |
> | **Log Analytics workspace** (`wpcounty-dev-law`) | workspace | `AppMetrics` | `Properties` |
>
> Same data, two names. Pick the query below that matches the blade you're in.

#### 6a. View per-user token usage (Logs)

1. Azure portal → open the **Application Insights** resource `wpcounty-dev-appi`
   (or the **Log Analytics workspace** `wpcounty-dev-law` — same data).
   - Shortcut from APIM: **APIM → Application Insights** in the left menu opens the
     linked component.
2. Left menu → **Logs** (under *Monitoring*). Close the query-samples dialog.
3. Set the time range (top bar) to **Last 30 minutes** (or your window).
4. Paste the query that matches your blade and **Run**:

   **A) From the Application Insights resource** (`customMetrics` / `customDimensions`):

   ```kusto
   customMetrics
   | where name == "Total Tokens"
   | extend UserId = tostring(customDimensions["UserId"]),
            TeamId = tostring(customDimensions["TeamId"])
   | summarize total_tokens = sum(valueSum), requests = sum(valueCount)
             by UserId, TeamId, bin(timestamp, 1d)
   | order by total_tokens desc
   ```

   **B) From the Log Analytics workspace** (`AppMetrics` / `Properties`):

   ```kusto
   AppMetrics
   | where Name == "Total Tokens"
   | extend UserId = tostring(Properties["UserId"]),
            TeamId = tostring(Properties["TeamId"])
   | summarize total_tokens = sum(Sum), requests = sum(ItemCount)
             by UserId, TeamId, bin(TimeGenerated, 1d)
   | order by total_tokens desc
   ```

   You get one row per user (e.g. `alice@county.gov` / `permits`) with token totals.

#### 6b. View chargeback / showback cost (Logs)

Same **Logs** blade — convert tokens to cost (adjust the rate to your model pricing).

**A) From the Application Insights resource:**

```kusto
let price_per_1k = 0.002;  // USD per 1K tokens
customMetrics
| where name == "Total Tokens"
| extend UserId = tostring(customDimensions["UserId"]), TeamId = tostring(customDimensions["TeamId"])
| summarize tokens = sum(valueSum) by UserId, TeamId, bin(timestamp, 1d)
| extend cost_usd = round(tokens / 1000.0 * price_per_1k, 4)
| order by cost_usd desc
```

**B) From the Log Analytics workspace:**

```kusto
let price_per_1k = 0.002;  // USD per 1K tokens
AppMetrics
| where Name == "Total Tokens"
| extend UserId = tostring(Properties["UserId"]), TeamId = tostring(Properties["TeamId"])
| summarize tokens = sum(Sum) by UserId, TeamId, bin(TimeGenerated, 1d)
| extend cost_usd = round(tokens / 1000.0 * price_per_1k, 4)
| order by cost_usd desc
```

Roll up by `TeamId` (drop `UserId` from the `by` clause) for department-level chargeback.

**Pin it to a dashboard:** click **Pin to** (top-right of the Logs results) →
**Azure dashboard**, or **Save** → **Save as workbook** to build an
**Azure Monitor workbook**. For finance-grade reports, connect **Power BI** to the
workspace (Logs → **Export** → *Power BI (M query)*).

#### 6c. (Optional) See `UserId` in the Metrics explorer

To split the *Total Tokens* metric by `UserId`/`TeamId` directly in the
**Metrics** blade (not Logs):

1. App Insights `wpcounty-dev-appi` → **Usage and estimated costs** → **Custom metrics**
   → enable **"With dimensions"** (sends custom dimensions to the pre-aggregated
   metrics store). *This may increase custom-metric costs.*
2. After new traffic flows, go to **Metrics** → Metric Namespace **`genai`** →
   Metric **Total Tokens** → **Apply splitting** → **UserId** (or **TeamId**).

Until this is enabled, the Metrics blade shows token totals but the dimensions
collapse — use the **Logs** queries above for per-user breakdown.

