# County Assistant — Azure AI Foundry chatbot for AWS-hosted WordPress

> A working prototype that applies a **Microsoft Foundry** chatbot/agent to a
> **WordPress site hosted on AWS** for a **county-government** scenario. All content
> is synthetic. See [Status](#status) for what is implemented.

## The core idea

> **This architecture separates the experience layer from the intelligence layer.**
>
> **WordPress on AWS remains the front door, while Azure AI Foundry becomes the brain.**

```
Users ──▶ AWS WordPress ──▶ Azure API Management (AI Gateway) ──▶ Azure AI Foundry
                                                                      │
                                              ┌───────────────────────┼───────────────────────┐
                                              ▼                       ▼                       ▼
                                           Models               Retrieval / Data            Tools
```

The WordPress site (the *experience layer*) embeds a chat widget. All AI calls flow through
**Azure API Management**, which acts as the **AI Gateway** (auth, rate limiting, token metering,
content safety, observability). APIM forwards to **Azure AI Foundry** (the *intelligence layer*),
which orchestrates models, retrieval/RAG over a synthetic county knowledge base, and tools.

APIM governs **two** surfaces: the public **chat API** (`/assistant/chat` → the Azure Function
backend) and the **Azure OpenAI model API** (`/openai` → the Foundry model). The Function routes
its chat-completions and embeddings calls back **through** the model API, so `azure-openai-token-limit`
(token budgets + 429), `azure-openai-emit-token-metric` (token metrics to App Insights), and
**managed-identity** backend auth (no model key on the wire) apply to every model call. See
[apim/policies/README.md](apim/policies/README.md).

## Scenario

A fictional county-government public website. Information architecture is *inspired by* the
public structure of a county portal (departments, services, FAQs, online services, permits,
taxes, health, emergency, voting, reporting concerns) but **all content is synthetic and
fictionalized**. No real site content is copied. See [data/](data/).

## Tech stack

- **Python** (`src/` layout), shared orchestrator with two interchangeable hosts:
  **Azure Functions** (Flex Consumption, default) and **FastAPI** (Container Apps, alternative)
- **UV** package manager (`~= 0.11.19`)
- **azure-ai-projects** (`~= 2.2.0`) — Azure AI Foundry SDK patterns
- **agent-framework** (`~= 1.8.0`) — Microsoft Agent Framework where useful
- **pytest**, **ruff**, **mypy**
- `.env`-based configuration

## Repository layout

```
.
├── pyproject.toml          # Project metadata, dependencies, ruff/mypy/pytest config
├── README.md               # This file
├── Dockerfile              # Container image for the FastAPI host (Container Apps)
├── .env.example            # Sample environment configuration
├── .gitignore
│
├── src/app/                # Shared application code: orchestrator + agents + RAG
│   ├── main.py             #   FastAPI app factory: middleware, lifespan, router wiring
│   ├── __init__.py         #   Package version + exports
│   ├── api/                #   HTTP layer (FastAPI)
│   │   └── routes/
│   │       ├── health.py   #     GET /api/health — liveness/readiness + config summary
│   │       ├── chat.py     #     POST /api/chat — the endpoint the WP widget calls via APIM
│   │       └── site.py     #     GET /api/site — active demo-site profile (greeting/title)
│   ├── agents/             #   Agent layer (Foundry / Agent Framework orchestration)
│   │   ├── orchestrator.py #     Routes a turn: safety → workflow → grounding → assistant
│   │   ├── base.py         #     Shared agent abstractions (BaseAgent, AgentContext/Result)
│   │   ├── safety_agent.py #     Guardrail stub (TODO(prod): Azure AI Content Safety)
│   │   ├── workflow_agent.py #   Intent/action router stub (keyword-based for now)
│   │   ├── retrieval_agent.py #  Grounds the turn on the local synthetic KB (safety net)
│   │   ├── citizen_assistant.py # Composes the final grounded answer + disclaimer
│   │   ├── ai_search_grounding.py # Pattern 2: Foundry AI Search tool (prompt agent)
│   │   ├── bing_grounding.py #   Pattern 3: Grounding with Bing Custom Search (prompt agent)
│   │   ├── foundry_client.py #   Azure AI Foundry client wrapper (azure-ai-projects v2)
│   │   └── site_profiles.py #    Per-site presentation (westvale / staging) source of truth
│   ├── rag/                #   Retrieval / RAG over the synthetic county KB
│   │   ├── retriever.py     #     Retrieval service: local + Azure AI Search retrievers
│   │   ├── indexer.py       #     In-memory index over KB chunks (offline default)
│   │   ├── chunking.py      #     Document loading + chunking
│   │   ├── embeddings.py    #     Embedding client for vector / hybrid retrieval
│   │   └── models.py        #     RAG data models (chunks, results)
│   ├── config/             #   Configuration
│   │   └── settings.py      #     Pydantic settings loaded from environment / .env
│   ├── core/               #   Cross-cutting utilities (no web-framework coupling)
│   │   ├── correlation.py   #     Correlation-ID context + middleware
│   │   ├── logging.py       #     Structured logging configuration
│   │   ├── telemetry.py     #     Optional OpenTelemetry / App Insights hooks
│   │   ├── errors.py        #     Application errors + FastAPI exception handlers
│   │   └── text.py          #     Shared text utilities (e.g. citation-marker stripping)
│   └── schemas/            #   Pydantic request/response models
│       └── chat.py          #     ChatRequest / ChatResponse / Citation
│
├── functionapp/            # Azure Functions host (default backend) — reuses src/app
│   ├── function_app.py     #   Functions entrypoint that mounts the shared orchestrator
│   ├── host.json           #   Functions host configuration
│   ├── requirements.txt    #   Functions runtime dependencies
│   └── local.settings.json.example # Local Functions settings sample
│
├── apim/policies/          # APIM AI Gateway policy samples (two governed surfaces)
│   ├── chat-operation.*.xml #   Chat API policy (/assistant/chat → Function)
│   ├── aoai-api.*.xml       #   AOAI model API policy (/openai → Foundry model)
│   ├── site-operation.*.xml #   Site profile operation policy
│   ├── *.fragment.xml       #   Reusable policy fragments (rate-limit, content-safety,
│   │                        #   token-throttle, semantic-cache, backend-routing)
│   └── README.md            #   How the policies compose + apply
│
├── wordpress/              # WordPress integration assets
│   ├── plugin/             #   County Assistant WP plugin (server-side proxy to APIM)
│   │   ├── county-assistant.php # Plugin bootstrap
│   │   ├── includes/        #   REST proxy, settings page, widget shortcode classes
│   │   └── assets/          #   Plugin front-end assets
│   ├── widget/             #   Standalone JS chat widget (no plugin required)
│   │   ├── county-assistant-widget.js / .css
│   │   └── embed-snippet.html # Copy-paste embed example
│   ├── theme/county-westvale/ # Demo theme for the synthetic county site
│   ├── demo-site/          #   Static demo landing page
│   ├── local-test/         #   Local WordPress (Docker) wired to live Azure
│   │   ├── wp-control.sh    #     One-script control: start/stop, switch pattern, status
│   │   ├── docker-compose.yml
│   │   └── setup.sh
│   └── README.md
│
├── docs/                   # Architecture, integration, security, cost, demo docs
│   └── diagrams/           #   draw.io sources (.drawio) + committed SVG renders
│
├── infra/                  # Infrastructure as Code (Bicep)
│   ├── main.bicep          #   Top-level deployment
│   ├── main.bicepparam     #   Parameters
│   ├── main.json           #   Compiled ARM template
│   └── modules/            #   Per-service modules: identity, keyvault, monitoring,
│                           #   apim, foundry, search, functionapp, containerapp
│
├── data/                   # Synthetic county knowledge base
│   ├── county_kb/          #   Source markdown (permits, taxes, health, voting, …)
│   ├── county_kb.seed.json #   Seed payload for indexing
│   └── demo_questions.md   #   Sample questions for demos
│
├── scripts/                # Dev helper scripts
│   ├── index_kb_to_search.py # Index the synthetic KB into Azure AI Search
│   └── set_demo_site.py    #   Switch the demo-site profile in local .env
│
├── examples/               # Sample API requests / seed payloads
└── tests/                  # pytest suite (health, chat, RAG, retrieval patterns)
```


## Quickstart

```bash
# 1. Install UV (~= 0.11.19) — https://docs.astral.sh/uv/
# 2. Sync dependencies (creates .venv)
uv sync

# 3. Configure environment
cp .env.example .env   # then edit values

# 4. Run the API
uv run uvicorn app.main:app --reload --app-dir src

# 5. Verify
curl http://localhost:8000/api/health
```

Quality gates:

```bash
uv run ruff check .
uv run mypy
uv run pytest
```

## Documentation

- [Architecture overview](docs/architecture-overview.md)
- [Reference architecture](docs/reference-architecture.md) — Mermaid diagrams (baseline / advanced / county-tailored)
- [Retrieval patterns](docs/retrieval-patterns.md) — Bing Custom Search vs Azure AI Search (RAG) vs Hybrid: pros/cons, cost, ingestion, switching
- [Deployment guide](docs/deployment-guide.md) — end-to-end deploy, pattern + demo-site switching
- [Cost model](docs/cost-model.md) — indicative per-pattern cost comparison
- [Security & governance](docs/security-governance.md) — identity, RBAC, content safety, hardening
- [WordPress integration](docs/wordpress-integration.md) — plugin vs JS widget, embedding
- [Security & SLG overlays](docs/security-and-slg-overlays.md)
- [Demo script](docs/demo-script.md) — ~10-minute executive walkthrough
- [Assumptions & alternatives](docs/assumptions-and-alternatives.md) — AWS hosting options + production hardening

## Try the chat endpoint

The assistant runs **fully offline** in local-fallback mode (grounded on the synthetic
KB). It uses Azure AI Foundry automatically when configured (`FOUNDRY_ENABLED=true` +
`AZURE_AI_PROJECT_ENDPOINT`).

```bash
uv run uvicorn app.main:app --reload --app-dir src

curl -s -X POST http://localhost:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"How do I apply for a building permit and how much does it cost?"}'
```

Each response includes a grounded `answer`, `citations`, the `route` that handled the
turn, the `mode` (`local-fallback`, `foundry`, `ai-search-grounding`, or `bing-grounding`),
and a standing disclaimer. Every response carries an `X-Correlation-Id` header that flows
WordPress → APIM → backend → Foundry.

## Test the chatbot on WordPress (step by step)

A single control script drives a local WordPress site (Docker) wired to the live Azure
resources ([wordpress/local-test/wp-control.sh](wordpress/local-test/wp-control.sh)).
Run everything from `wordpress/local-test`:

```bash
cd wordpress/local-test
```

1. **Start the WordPress demo.** Boots WordPress in Docker, auto-fetches the APIM
   subscription key, and wires the plugin (endpoint + key) automatically:

   ```bash
   ./wp-control.sh start
   ```

2. **Open the site** and try the chat widget in the bottom corner:

   ```bash
   ./wp-control.sh open          # or browse to http://localhost:8083
   ```

   Ask e.g. *"How do I apply for a building permit and how much does it cost?"* — the reply
   includes citations and the route/mode that handled it.

3. **Check the live services** (Function, APIM chat API + AOAI model gateway, Foundry, Search):

   ```bash
   ./wp-control.sh status
   ```

4. **Stop or tear down** when finished:

   ```bash
   ./wp-control.sh stop          # stop containers (keep state)
   ./wp-control.sh destroy       # remove containers + volumes
   ```

### Change the retrieval pattern

Switch how the assistant grounds answers — no code change. The WordPress demo talks to
the **live Azure Function**, so switching means updating the live Function's app
settings (not your local `.env`).

> ⚠️ **Switching a pattern does NOT start the WordPress app.** `pattern` only changes
> Azure routing. To actually use the chatbot you still need the app running (step 1
> above). Use the one-step `demo` command below to do both at once.

**Easiest — switch the pattern AND start the app in one step:**

```bash
cd wordpress/local-test
./wp-control.sh demo local          # offline: synthetic KB only
./wp-control.sh demo azure_search   # RAG over the Azure AI Search index
./wp-control.sh demo bing           # Grounding with Bing Custom Search
./wp-control.sh demo hybrid         # RAG with Bing fallback
```

You can also switch the **demo site profile** in the same command by passing an
optional second argument (`westvale` or `staging`). This sets `DEMO_SITE_PROFILE`
too, so the greeting/title follow the site automatically:

```bash
./wp-control.sh demo bing staging   # bing routing + County of Lakeside profile
./wp-control.sh demo hybrid westvale # hybrid routing + County of Westvale profile
```

`demo` runs **STEP 1** (switch `RETRIEVAL_PATTERN` — and `DEMO_SITE_PROFILE` if you
passed a site — on the live Function and wait until routing is stable) and then
**STEP 2** (bring up the WordPress stack and wire it to APIM), and prints the URL.
Open <http://localhost:8083> and chat.

**Or switch the pattern only** (Azure routing change; app must already be running via
`./wp-control.sh start`):

```bash
./wp-control.sh pattern local          # offline: synthetic KB only
./wp-control.sh pattern azure_search   # RAG over the Azure AI Search index
./wp-control.sh pattern bing           # Grounding with Bing Custom Search
./wp-control.sh pattern hybrid         # RAG with Bing fallback
```

To change the **pattern and the demo site together** on the live Function (e.g. to test
Bing grounding against the staging-site profile), set both app settings, restart, then
wait for the health check. Paste this as a **single line** (avoids broken `\`
continuations):

```bash
az functionapp config appsettings set -g rg-county-sc -n wpcounty-dev-func-mro5df --settings RETRIEVAL_PATTERN=bing DEMO_SITE_PROFILE=staging -o none && az functionapp restart -g rg-county-sc -n wpcounty-dev-func-mro5df && echo "Waiting for the Function to come back..." && for i in $(seq 1 15); do code=$(curl -s -m 15 -o /dev/null -w "%{http_code}" https://wpcounty-dev-func-mro5df.azurewebsites.net/api/health); if [ "$code" = "200" ]; then echo "health=200 OK"; break; fi; echo "  attempt $i: health=$code, retrying..."; sleep 4; done
```

The `&&` chain runs each step only if the prior one succeeds: **set** the two app
settings → **restart** (Flex Consumption runs multiple instances, so a restart makes
them all pick up the change) → **poll** `GET /api/health` until it returns `200`. The
first few attempts printing `health=000` is normal — that's curl while the Function is
still restarting. Swap the `--settings` values for any other pattern/site.

> ⚠️ This `az` command **only updates Azure** — it does **not** start the WordPress app.
> After it finishes, start the demo with `cd wordpress/local-test && ./wp-control.sh start`
> (or just use `./wp-control.sh demo <pattern>` above, which does both).

> `scripts/set_demo_site.py` only edits your local `.env` for running the backend
> yourself — it does **not** change the deployed Function. Full explanation of the two
> config layers: [Deployment guide §6](docs/deployment-guide.md#6-switching-retrieval-patterns).

Re-ask a question in the widget after switching; the response `mode` reflects the active
pattern. Full pattern comparison and the demo-site switch (`westvale` ⇄ `staging`) are in
the [Deployment guide](docs/deployment-guide.md#6-switching-retrieval-patterns) and
[Retrieval patterns](docs/retrieval-patterns.md).

## Status

Working against live Azure resources (synthetic data; not a production deployment):

- ✅ Backend: health + chat, correlation id, structured logging, error contract, OTEL hooks
- ✅ Agent layer: orchestrator + safety, retrieval, citizen-assistant, workflow agents
- ✅ RAG: synthetic county KB + chunking + retriever, with an Azure AI Search retriever
- ✅ Foundry integration (azure-ai-projects v2) with graceful local fallback
- ✅ WordPress plugin (proxy) + standalone JS widget
- ✅ APIM AI gateway: chat API (`/assistant/chat`) and AOAI model API (`/openai`) with token-limit + token-metrics + managed-identity backend auth; the Function routes model calls through the gateway by default
- ✅ IaC: Bicep modules under [infra](infra) (identity, Key Vault, storage, monitoring, APIM, Foundry, Search, Functions, Container Apps)
- ✅ Local control script ([wordpress/local-test/wp-control.sh](wordpress/local-test/wp-control.sh)): start/stop the WordPress demo, switch retrieval patterns, and report all live Azure services

Semantic caching (`azure-openai-semantic-cache-*`) is **not enabled** in this build — the
full policy is provided in [apim/policies/aoai-api.policy.xml](apim/policies/aoai-api.policy.xml)
and requires an external Redis cache to turn on.

This project makes **no compliance claims** and uses only synthetic data.

## License

MIT.
