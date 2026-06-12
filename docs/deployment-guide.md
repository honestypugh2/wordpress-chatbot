# Deployment Guide

> End-to-end deployment of the County Assistant for an AWS-hosted WordPress site
> backed by Azure AI Foundry. Covers infra, backend, retrieval index, the AI
> gateway, the WordPress plugin, and switching between the two demo sites and the
> three retrieval patterns. All County of Westvale content is synthetic.

Architecture (summary): **WordPress (AWS) → APIM (AI gateway) → Azure Function
(backend) → Azure AI Foundry**, with Azure AI Search and/or Grounding with Bing
Custom Search as the retrieval layer. Diagrams: [docs/reference-architecture.md](docs/reference-architecture.md).
Plugin/proxy detail: [docs/wordpress-integration.md](docs/wordpress-integration.md).

---

## 1. Prerequisites

- Azure subscription with quota for **Azure OpenAI** (`gpt-4o-mini`,
  `text-embedding-3-small`), **Azure AI Search**, **API Management**, and
  **Azure Functions (Flex Consumption)**.
- Tools: [Azure CLI](https://learn.microsoft.com/cli/azure/), `func` (Azure
  Functions Core Tools), [uv](https://docs.astral.sh/uv/), and `python` 3.12.
- A WordPress site (the customer's AWS instance, or the local Docker harness in
  [wordpress/local-test](wordpress/local-test)).
- Sign in: `az login` and `az account set --subscription <SUBSCRIPTION_ID>`.

> **Region note:** some regions are capacity-constrained for Azure AI Search.
> This prototype was deployed to **Sweden Central**. If Search reports
> `InsufficientResourcesAvailable`, pick another region with both model and Search
> capacity.

---

## 2. Provision infrastructure (Bicep)

Infrastructure is modular under [infra](infra) ([infra/main.bicep](infra/main.bicep)
+ [infra/modules](infra/modules)). Defaults: APIM **Developer** (non-prod), Search
**basic**, Functions **Flex Consumption**, models on **GlobalStandard**.

```bash
az group create -n rg-county-sc -l swedencentral

az deployment group create \
  -g rg-county-sc -n county-full \
  -f infra/main.bicep -p infra/main.bicepparam
```

> APIM provisioning takes ~30–45 minutes. The deployment also creates a
> user-assigned **managed identity**, **Key Vault**, **Storage**, and
> **Application Insights**, and assigns RBAC (see [docs/security-governance.md](docs/security-governance.md)).

Capture the outputs:

```bash
az deployment group show -g rg-county-sc -n county-full \
  --query properties.outputs -o jsonc
```

You will use: `apimGatewayUrl`, `backendFqdn`, `foundryProjectEndpoint`,
`foundryAccountEndpoint`, `searchEndpoint`, `searchIndexName`,
`modelDeploymentName`, `embeddingDeploymentName`, `managedIdentityClientId`,
`keyVaultUri`.

---

## 3. Deploy the backend (Azure Function)

The backend is host-agnostic (shared orchestrator); the Function is a thin wrapper.
Vendor the app, publish, then clean up:

```bash
cp -r src/app functionapp/app
cd functionapp && func azure functionapp publish <functionAppName>
cd .. && rm -rf functionapp/app
```

Smoke test:

```bash
curl https://<backendFqdn>/api/health        # → 200 {"status":"ok",...}
```

> Anything imported transitively by `functionapp/function_app.py` must be in
> [functionapp/requirements.txt](functionapp/requirements.txt), or the host indexes
> 0 functions. The shared `app.core` is deliberately web-framework-free for this
> reason.

### Backend configuration (app settings)

Set these on the Function (or in your local `.env`) to choose the retrieval pattern
and site. See the full matrix in [§6](#6-switching-retrieval-patterns) and
[§7](#7-switching-the-demo-site).

| Setting | Example | Purpose |
|---------|---------|---------|
| `FOUNDRY_ENABLED` | `true` | Use Foundry for answer composition |
| `AZURE_AI_PROJECT_ENDPOINT` | `https://<acct>.services.ai.azure.com/api/projects/<proj>` | Foundry project |
| `AZURE_AI_MODEL_DEPLOYMENT` | `gpt-4o-mini` | Chat model |
| `AZURE_EMBEDDING_DEPLOYMENT` | `text-embedding-3-small` | Embeddings |
| `RETRIEVAL_PATTERN` | `hybrid` | `local` \| `azure_search` \| `bing` \| `hybrid` |
| `DEMO_SITE_PROFILE` | `westvale` | `westvale` \| `staging` |
| `AZURE_SEARCH_CONNECTION_NAME` | `<project-search-connection>` | Pattern 2 default (Foundry AI Search tool) |
| `AZURE_SEARCH_AGENT_NAME` | `county-assistant-ai-search` | Existing AI Search prompt agent (optional) |
| `AZURE_SEARCH_QUERY_TYPE` | `vector_semantic_hybrid` | AI Search tool query type |
| `AZURE_SEARCH_USE_CUSTOM_RETRIEVER` | `false` | Opt in to the in-repo retriever instead of the tool |
| `AZURE_SEARCH_ENDPOINT` | `https://<search>.search.windows.net` | Custom retriever / hybrid |
| `AZURE_SEARCH_INDEX` | `county-kb` | Index name |
| `BING_GROUNDING_ENABLED` | `true` | Enable Bing grounding (bing / hybrid) |
| `BING_ALLOWED_DOMAINS` | `staging.example.gov,www.example.gov` | Runtime override of allowed public domains |
| `BING_GROUNDING_AGENT_NAME` | `county-assistant-bing-grounding` | Existing Foundry prompt agent (or set `BING_CONNECTION_NAME` + `BING_CUSTOM_SEARCH_INSTANCE_NAME` to create one) |

---

## 4. Build the retrieval index (Patterns 2 & 3)

Skip this for **Pattern 1 (Bing)** and the **staging** site — they need no index.
Pattern 2 by default grounds via the Foundry AI Search tool (a prompt agent), which
queries an existing index through a project connection; you still build the index
here. The opt-in custom retriever (`AZURE_SEARCH_USE_CUSTOM_RETRIEVER=true`) also
uses it.

```bash
export AZURE_SEARCH_ENDPOINT="<searchEndpoint>"
export AZURE_SEARCH_INDEX=county-kb
export RAG_VECTOR_ENABLED=true
export AZURE_AI_PROJECT_ENDPOINT="<foundryProjectEndpoint>"
export AZURE_EMBEDDING_DEPLOYMENT=text-embedding-3-small
uv run --extra rag python scripts/index_kb_to_search.py
```

This creates the `county-kb` index (keyword + semantic + vector) and uploads the
chunked, embedded knowledge base. Re-running is idempotent. Pipeline details:
[docs/retrieval-patterns.md §5](docs/retrieval-patterns.md). Auth uses
`DefaultAzureCredential` (Azure CLI / managed identity); the identity needs
**Search Index Data Contributor** to write.

---

## 5. Configure the AI gateway (APIM) and the WordPress plugin

1. **APIM** — apply the chat policy [apim/policies/chat-operation.policy.xml](apim/policies/chat-operation.policy.xml)
   to the chat operation, and create a **subscription key** for the assistant
   product/API. The chat URL looks like
   `https://<apim>.azure-api.net/assistant/chat`.
2. **WordPress plugin** — install [wordpress/plugin](wordpress/plugin) and set the
   gateway URL + subscription key. The plugin exposes a server-side REST **proxy**
   (`/wp-json/county-assistant/v1/chat`) that validates a nonce and injects the
   APIM key, so the key is **never** exposed to the browser. Details:
   [docs/wordpress-integration.md](docs/wordpress-integration.md).

For the local harness, use the control script (it boots Docker, auto-fetches the
APIM key, and wires the plugin):

```bash
cd wordpress/local-test
./wp-control.sh start            # boot WordPress + wire APIM (key auto-fetched)
./wp-control.sh status           # report all live Azure services incl. the AOAI gateway
# open http://localhost:8083
```

Or wire it manually:

```bash
cd wordpress/local-test
docker compose up -d
./setup.sh "https://<apim>.azure-api.net/assistant/chat" "<subscription-key>"
# open http://localhost:8083
```

---

## 5a. Front the Azure OpenAI model in APIM (true AI-gateway governance)

APIM also fronts the **Azure OpenAI model** so token budgets and token metrics apply
to every model call and no model key is stored in the backend. The Function then calls
chat-completions and embeddings **through** APIM instead of directly against Foundry.

1. **Grant APIM access to the model.** Give the APIM **system-assigned managed identity**
   the **Cognitive Services OpenAI User** role on the Foundry account.
2. **Backend** — register an APIM backend (`aoai-backend`) pointing at the Foundry
   Azure OpenAI endpoint: `https://<foundry>.openai.azure.com/openai`.
3. **Model API** — import the Azure OpenAI inference OpenAPI spec as an API (path
   `/openai`, `api-key` header for the subscription key) and create an API-scoped
   subscription for the backend caller.
4. **Policy** — apply [apim/policies/aoai-api.applied.xml](apim/policies/aoai-api.applied.xml):
   `authentication-managed-identity` (backend auth), `azure-openai-token-limit`
   (per-caller tokens/min + 429), and `azure-openai-emit-token-metric` (token metrics
   to Application Insights). The full reference
   [apim/policies/aoai-api.policy.xml](apim/policies/aoai-api.policy.xml) adds semantic
   caching (`azure-openai-semantic-cache-*`), which needs an external Redis cache.
5. **Route the Function through the gateway** — set on the Function (and in `.env`):

   ```bash
   AZURE_OPENAI_GATEWAY_ENDPOINT="https://<apim>.azure-api.net"   # client appends /openai/...
   AZURE_OPENAI_GATEWAY_KEY="<aoai-api subscription key>"          # sent as the api-key header
   ```

   When both are set, [FoundryClient](src/app/agents/foundry_client.py) and the
   [embeddings client](src/app/rag/embeddings.py) route through APIM. When unset, they
   call Foundry directly with managed identity — so local/offline runs are unaffected.

`./wp-control.sh status` reports the AOAI API, the `aoai-backend`, the applied
governance policy elements, and whether the Function is routing through the gateway.

---

## 6. Switching retrieval patterns

### Where settings live (read this first)

There are **two separate places** configuration can live, and they do **not** sync
automatically:

| Layer | What reads it | How to change it |
|-------|---------------|------------------|
| **Live Function app settings** (in Azure) | The **deployed** backend that the WordPress demo, APIM, and any real client call | `az functionapp config appsettings set ...` (below) or `./wp-control.sh pattern <p>` |
| **Local `.env`** (in this repo) | Only a backend you run yourself with `uv run uvicorn ...` | edit `.env` directly, or `scripts/set_demo_site.py` |

> The WordPress demo at `localhost:8083` talks to the **live Function**, not your
> local `.env`. So to change what the demo does, you must change the **live Function
> app settings**. `scripts/set_demo_site.py` only edits `.env` ([§7](#7-switching-the-demo-site))
> and has **no effect on the deployed Function**.

### Easiest: switch the pattern AND start the app in one step

Switching a pattern is an **Azure routing change only** — it does **not** start the
WordPress app. To both switch the pattern and bring the demo up so you can actually use
the chatbot, run the one-step `demo` command:

```bash
cd wordpress/local-test
./wp-control.sh demo bing       # STEP 1 switch RETRIEVAL_PATTERN + wait; STEP 2 start app
./wp-control.sh demo bing staging  # also set DEMO_SITE_PROFILE (westvale|staging)
```

Valid patterns: `local`, `azure_search`, `bing`, `hybrid`. An optional second argument
sets the demo site profile (`westvale` or `staging`), so the greeting/title follow the
site automatically. When it finishes, open <http://localhost:8083> and use the launcher
(bottom-right). If the app is already running, `./wp-control.sh pattern <p> [site]`
switches the pattern (and site) without restarting the WordPress containers.

### Change the live pattern (and demo site) in one command

`RETRIEVAL_PATTERN` selects the grounding path; the backend resolves
[Settings.effective_retrieval_pattern](src/app/config/settings.py) and **degrades
gracefully** to `local` if a path is not configured. `DEMO_SITE_PROFILE` selects the
site's prompt/greeting and recommended grounding (`westvale` synthetic ⇄ `staging`
external). To set both on the live Function, restart it, and confirm it came back
healthy, paste this as a **single line** (a single-line command avoids broken `\`
line-continuations, the usual reason a copy-pasted multi-line version "doesn't work"):

```bash
az functionapp config appsettings set -g rg-county-sc -n wpcounty-dev-func-mro5df --settings RETRIEVAL_PATTERN=bing DEMO_SITE_PROFILE=staging -o none && az functionapp restart -g rg-county-sc -n wpcounty-dev-func-mro5df && echo "Waiting for the Function to come back..." && for i in $(seq 1 15); do code=$(curl -s -m 15 -o /dev/null -w "%{http_code}" https://wpcounty-dev-func-mro5df.azurewebsites.net/api/health); if [ "$code" = "200" ]; then echo "health=200 OK"; break; fi; echo "  attempt $i: health=$code, retrying..."; sleep 4; done
```

What each part does:

- **`appsettings set`** writes `RETRIEVAL_PATTERN` and `DEMO_SITE_PROFILE` into the live
  Function's configuration. `&&` means each step only runs if the previous one
  succeeded.
- **`restart`** is required because Flex Consumption runs multiple instances; a restart
  makes them all reload the new settings (otherwise the first calls can show a mix of
  old and new behaviour).
- **The health poll** retries `GET /api/health` up to 15 times (4s apart) until it
  returns `200`, so you know the Function is ready before you test in the widget. Seeing
  `health=000` on the first few attempts is normal — that's curl while the Function is
  still restarting. Swap the `--settings` values to switch to any other pattern/site.

> **Prefer a readable multi-line version?** Save it as a script instead of pasting it,
> so line-continuations can't be corrupted by a stray trailing space:
>
> ```bash
> cat > /tmp/switch.sh <<'EOF'
> az functionapp config appsettings set -g rg-county-sc -n wpcounty-dev-func-mro5df \
>   --settings RETRIEVAL_PATTERN=bing DEMO_SITE_PROFILE=staging -o none
> az functionapp restart -g rg-county-sc -n wpcounty-dev-func-mro5df
> echo "Waiting for the Function to come back..."
> for i in $(seq 1 15); do
>   code=$(curl -s -m 15 -o /dev/null -w "%{http_code}" https://wpcounty-dev-func-mro5df.azurewebsites.net/api/health)
>   [ "$code" = "200" ] && { echo "health=200 OK"; break; }
>   echo "  attempt $i: health=$code, retrying..."; sleep 4
> done
> EOF
> bash /tmp/switch.sh
> ```

> **Pattern only?** `./wp-control.sh pattern <local|azure_search|bing|hybrid>` does the
> equivalent for `RETRIEVAL_PATTERN` (set + restart + poll live routing until stable),
> but it does **not** change `DEMO_SITE_PROFILE` — use the command above to change both.

> ⚠️ **This `az` command only updates Azure — it does NOT start the WordPress app.**
> After it returns `health=200`, start the demo with
> `cd wordpress/local-test && ./wp-control.sh start`, or skip the `az` command entirely
> and use `./wp-control.sh demo <pattern>` (above), which switches the pattern **and**
> starts the app.

Each pattern's prerequisites:

```bash
# RAG
RETRIEVAL_PATTERN=azure_search  AZURE_SEARCH_ENDPOINT=...  AZURE_SEARCH_INDEX=county-kb
# Hybrid (RAG → Bing fallback)
RETRIEVAL_PATTERN=hybrid  AZURE_SEARCH_ENDPOINT=...  BING_GROUNDING_ENABLED=true
# Bing Custom Search grounding
RETRIEVAL_PATTERN=bing  BING_GROUNDING_ENABLED=true  BING_GROUNDING_AGENT_NAME=county-assistant-bing-grounding
# Offline default
RETRIEVAL_PATTERN=local
```

Comparison and trade-offs: [docs/retrieval-patterns.md](docs/retrieval-patterns.md).

---

## 7. Switching the demo site

`DEMO_SITE_PROFILE` selects the site profile (prompt, greeting, recommended pattern).
On the **live Function**, set it with the chained `az` command in
[§6](#6-switching-retrieval-patterns) (it sets the pattern and the site together).

For a backend you run **locally** (`uv run uvicorn ...`), the helper updates your
`.env` instead:

```bash
uv run python scripts/set_demo_site.py westvale          # synthetic site → hybrid
uv run python scripts/set_demo_site.py staging           # staging site   → bing
uv run python scripts/set_demo_site.py staging --write .env
```

> This edits **`.env` only** — it does **not** touch the deployed Function. Use it when
> running the backend yourself; use the `az` command in §6 for the live demo.

The widget fetches `GET /api/site` and self-configures its title/greeting, so the same
page reflects the active site. Profiles: [src/app/agents/site_profiles.py](src/app/agents/site_profiles.py).

- **Westvale** (synthetic): grounded via Azure AI Search RAG / hybrid;
  can also demo the Bing Custom Search pattern.
- **Staging** (generic customer staging site): grounded via Bing Custom Search
  scoped to the domains in `BING_ALLOWED_DOMAINS` — **no scraping or ingestion**.
  The real staging domain is supplied at deploy time, never hard-coded here.

---

## 8. Run locally (offline)

The whole stack runs offline with the local retriever and local answer composer:

```bash
FOUNDRY_ENABLED=false AZURE_SEARCH_ENDPOINT="" RETRIEVAL_PATTERN=local \
  uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --app-dir src

# Static demo site (County of Westvale portal):
python3 -m http.server 8080 -d wordpress    # → http://localhost:8080/demo-site/
```

---

## 9. Validate

```bash
uv run ruff check src tests scripts
uv run mypy src
uv run pytest -q
curl -s -X POST https://<backendFqdn>/api/chat \
  -H 'content-type: application/json' \
  -d '{"message":"How do I apply for a building permit?"}'
```

Foundry prompt agents are created on demand from the SDK by the orchestrator (see
[src/app/agents](src/app/agents)); provisioning settings and test queries for both
sites are in [retrieval-patterns.md](retrieval-patterns.md). Cost:
[cost-model.md](cost-model.md). Security & RBAC: [security-governance.md](security-governance.md).
