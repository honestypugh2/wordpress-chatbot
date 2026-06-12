# Infrastructure as Code (Bicep)

Deployable Bicep for the **Azure intelligence layer**. The WordPress experience
layer remains on AWS; this provisions only the Azure services the assistant uses.

## Modules

| File | Provisions |
| --- | --- |
| [main.bicep](main.bicep) | Top-level composition + outputs (resource-group scope). |
| [main.bicepparam](main.bicepparam) | Default parameters — edit before deploying. |
| [modules/identity.bicep](modules/identity.bicep) | User-assigned managed identity (secretless access). |
| [modules/monitoring.bicep](modules/monitoring.bicep) | Log Analytics workspace + Application Insights. |
| [modules/keyvault.bicep](modules/keyvault.bicep) | RBAC Key Vault + Secrets User role for the identity. |
| [modules/search.bicep](modules/search.bicep) | Azure AI Search (semantic) + Index Data Reader role. |
| [modules/foundry.bicep](modules/foundry.bicep) | AI Foundry account + project + model + OpenAI User role. |
| [modules/apim.bicep](modules/apim.bicep) | API Management gateway + API + chat operation. |
| [modules/functionapp.bicep](modules/functionapp.bicep) | **Default** backend host: Azure Functions (Flex Consumption), serverless/scale-to-zero. |
| [modules/containerapp.bicep](modules/containerapp.bicep) | Alternative backend host: Azure Container Apps (always-on FastAPI). |

## Backend host — Function (default) or Container App

The backend orchestrator runs the **same shared code** ([`app.agents.Orchestrator`](../src/app/agents/orchestrator.py)) regardless of host. Pick the compute with the `backendHost` parameter; APIM automatically routes to whichever is deployed:

| `backendHost` | Compute | When to use |
| --- | --- | --- |
| `function` *(default)* | Azure Functions, Flex Consumption | Recommended for government workloads — serverless, scale-to-zero, matches bursty resident traffic. |
| `containerapp` | Azure Container Apps (FastAPI) | Portable / always-on demonstration. Build & push `backendImage` first. |
| `none` | — | No backend; APIM falls back to the raw Foundry endpoint (widget contract will not match). |

The Function host ([function_app.py](../functionapp/function_app.py)) and the FastAPI host ([main.py](../src/app/main.py)) are thin wrappers over the identical orchestrator, so the WordPress widget and APIM are unchanged when you switch.

## Identity & RBAC (no secrets in the app)

The backend authenticates with the user-assigned managed identity via
`DefaultAzureCredential` (`AZURE_CLIENT_ID` selects it). Role assignments granted:

- **Cognitive Services OpenAI User** on the Foundry account (model inference).
- **Search Index Data Reader** on the search service (query-time retrieval).
- **Key Vault Secrets User** on the vault (read the APIM subscription key, etc.).
- **Storage Blob Data Owner** on the Function's storage account (Flex Consumption
  uses identity-based host + deployment storage — no connection-string secrets).

## Deploy

```bash
az group create -n rg-county-assistant -l eastus2

# Validate first (no changes made)
az deployment group what-if \
  -g rg-county-assistant \
  -f infra/main.bicep \
  -p infra/main.bicepparam

# Deploy
az deployment group create \
  -g rg-county-assistant \
  -f infra/main.bicep \
  -p infra/main.bicepparam
```

## After deployment

1. Capture outputs (`foundryProjectEndpoint`, `searchEndpoint`, `apimGatewayUrl`,
   `managedIdentityClientId`, `backendHost`, `backendFqdn`) into your runtime config / `.env`.
2. Publish the backend code to the selected host:
   - **Function (default):** `cd functionapp && func azure functionapp publish <backendFqdn host>` — the publish step vendors the shared `src/app` package (see [../functionapp/README.md](../functionapp/README.md)).
   - **Container App:** build & push the image from the repo [Dockerfile](../Dockerfile), then redeploy with `backendHost = 'containerapp'` and `backendImage` set.
3. Populate the search index from the synthetic KB:
   ```bash
   export AZURE_SEARCH_ENDPOINT="<searchEndpoint output>"
   uv run python scripts/index_kb_to_search.py
   ```
4. Apply the full AI-gateway policy from
   [../apim/policies/chat-operation.policy.xml](../apim/policies/chat-operation.policy.xml)
   to the `chat` operation and configure the Named Values listed in
   [../apim/policies/README.md](../apim/policies/README.md).

## Not included (deliberate scope)

Private endpoints / VNet integration, customer-managed keys, WAF, semantic-cache
Redis for APIM, and sovereign-cloud variants are environment decisions — see
[../docs/security-and-government-overlays.md](../docs/security-and-government-overlays.md) and
[../docs/assumptions-and-alternatives.md](../docs/assumptions-and-alternatives.md).

> Verify region availability for the chosen model and Foundry API versions before
> deploying to production.
