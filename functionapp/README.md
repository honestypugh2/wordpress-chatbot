# County Assistant — Azure Functions host (default backend)

Serverless (Flex Consumption) host for the backend orchestrator. This is the
**default / recommended** compute for the SLED scenario: it scales to zero
between bursts of resident traffic.

It shares the **same** orchestration code as the FastAPI host — both call
[`app.agents.Orchestrator`](../src/app/agents/orchestrator.py). Only the hosting
model differs, so the WordPress widget and APIM are unchanged when you switch.

## Contract

Same as the FastAPI `/api/chat`:

- `POST /api/chat` → body `{ "message", "session_id?", "page_url?" }` → `{ answer, citations, ... }`
- `GET  /api/health` → `{ "status": "ok", "host": "azure-functions" }`

(The Functions route prefix `api` is the default, so paths match the FastAPI host.)

## Run locally

```bash
# From the repo root, with the project venv active (provides app + deps):
cp functionapp/local.settings.json.example functionapp/local.settings.json
cd functionapp
func start
```

`function_app.py` adds the repo `../src` to `sys.path`, so locally it imports the
shared `app` package directly — no copy needed.

## Deploy

The deployment unit is the `functionapp/` folder, which does **not** include
`../src`. The publish step must **vendor** the shared package so the cloud host
can import it:

```bash
# Vendor the shared package, then publish.
rm -rf functionapp/app && cp -r src/app functionapp/app
cd functionapp
func azure functionapp publish <function-app-name>
rm -rf app   # keep the repo clean; src/app remains the source of truth
```

> `function_app.py` imports `app` from either `../src` (local dev) or a vendored
> `./app` (cloud) — whichever is present.

## Host selection

Provisioned via Bicep `backendHost = 'function'` (default). See
[../infra/README.md](../infra/README.md).
