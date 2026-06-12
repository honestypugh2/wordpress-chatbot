# Architecture Overview

> High-level positioning and decisions. This document makes **no compliance claims**.

## 1. The core idea

> **This architecture separates the experience layer from the intelligence layer.**
>
> **WordPress on AWS remains the front door, while Azure AI Foundry becomes the brain.**

- **Experience layer** — the existing WordPress site on AWS. It owns branding, content,
  navigation, accessibility, and the chat *widget* the resident interacts with.
- **Intelligence layer** — Azure AI Foundry. It owns the model(s), the agent, retrieval
  over the county knowledge base, and tool execution.
- **Gateway in between** — Azure API Management (APIM) as the **AI Gateway**: the single,
  governed entry point from the public web to the intelligence layer.

## 2. Target pattern

```
Users ──▶ AWS WordPress ──▶ Azure API Management (AI Gateway) ──▶ Azure AI Foundry
                                                                      │
                                                  Models • Retrieval/Data • Tools
```

See [reference-architecture.md](reference-architecture.md) for slide-quality Mermaid diagrams
(baseline, advanced, and county-tailored).

## 3. How to apply an Azure AI Foundry chatbot to AWS-hosted WordPress

At a high level:

1. **Build the brain in Foundry.** Create an Azure AI Foundry project, deploy a model, and
   define a **prompt agent** (Azure AI Projects SDK) with county-specific instructions and tools.
2. **Ground it.** Connect retrieval (RAG) over a **synthetic county knowledge base** so answers
   are scoped to county services rather than open-ended.
3. **Expose it safely.** Put **APIM** in front as the AI Gateway (auth, rate limiting, token
   metering, content safety, logging). The public never calls Foundry directly. APIM also
   fronts the **Azure OpenAI model** on a `/openai` API, so the backend's model calls pass
   through `azure-openai-token-limit` + `azure-openai-emit-token-metric` and APIM authenticates
   to the model with its **managed identity** (no model key on the wire). See
   [apim/policies/README.md](apim/policies/README.md).
4. **Add a thin backend.** A small orchestrator service (this repo) mediates between the widget
   and Foundry — managing threads/sessions, shaping requests, and enforcing app-level rules.
   The **same orchestrator code** runs on either host: **Azure Functions (Flex Consumption,
   the default — serverless/scale-to-zero)** or **Azure Container Apps (always-on FastAPI)**.
   *(In a minimal variant APIM can call Foundry directly; the backend is used here for
   session state, tool brokering, and testability.)*
5. **Embed on WordPress.** Drop in a **chat widget** (custom JS or a lightweight plugin) that
   calls the APIM endpoint. WordPress stays the front door.
6. **Govern and observe.** Centralize keys/identity, quotas, and telemetry at the gateway.

See [wordpress-integration.md](wordpress-integration.md) and
[security-and-government-overlays.md](security-and-government-overlays.md) for detail.

## 4. Recommended implementation pattern: **Hybrid**

Three options were considered:

| Option | What it means | Trade-off |
| --- | --- | --- |
| **Foundry SDK first** | Use `azure-ai-projects` (~= 2.2.0) prompt agents as the primary surface. | Strong managed governance, server-side tools, and connections; less local orchestration flexibility. |
| **Agent Framework first** | Use `agent-framework` (~= 1.8.0) to orchestrate everything client-side. | Maximum orchestration/eval flexibility; you re-own hosting, identity, and governance Foundry would otherwise provide. |
| **Hybrid** ✅ | Foundry is the system of record (project, model deployment, prompt agent, connections, content safety); Agent Framework is used client-side for multi-step orchestration, tool calling, and local evaluation where it adds value. | Slightly more moving parts, but best fit for a governed government prototype that must scale to production. |

**Recommendation: Hybrid.** Rationale:

- **Governance belongs server-side.** A government scenario benefits from Foundry's managed
  identity, connections, content safety, and centralized model/agent management — which APIM
  then fronts. This keeps secrets and policy out of the public edge.
- **Orchestration benefits client-side.** Agent Framework gives clean, testable multi-step
  flows (retrieve → reason → call tool → answer) and **local evaluation**, valuable for
  demonstrating quality and iterating quickly.
- **Portability.** Staying hybrid avoids lock-in to a single SDK surface and lets the team
  shift the orchestration boundary as requirements firm up.

## 5. Why APIM sits between WordPress and Foundry

APIM as the **AI Gateway** provides, in one governed hop:

- **Single public entry point** with a stable contract for the widget.
- **AuthN/Z** — subscription keys / OAuth / managed identity to the backend; the public never
  holds Foundry credentials.
- **Rate limiting & token quotas** — protect cost and capacity (per-IP, per-key, token-based).
- **Content safety & prompt-shield hooks** — apply guardrails consistently.
- **Cross-cloud seam** — clean AWS↔Azure boundary (CORS, TLS, allow-listing, regional routing).
- **Observability** — centralized request/latency/token logging for ops and FinOps.

See [apim/policies/](../apim/policies/) for the applied policies and full references.

## 6. Current build vs production hardening

| Concern | This build | Production hardening |
| --- | --- | --- |
| Compute | Azure Functions (Flex Consumption, default); local FastAPI for dev | Functions or Container Apps, autoscaled, zone-redundant |
| Identity | Managed identity / `DefaultAzureCredential` | Managed identity end-to-end; no keys in app |
| Secrets | `.env` (local, never committed); app settings | Azure Key Vault references |
| Retrieval | Local file-based fallback + Azure AI Search index | Azure AI Search index, scheduled refresh |
| Gateway | APIM Developer tier, applied AI policies | APIM with full AI policies, WAF/Front Door, private networking |
| WordPress link | Plugin proxy (server-side key) + JS widget | Hardened widget/plugin, signed/session-scoped calls |
| Observability | App Insights + structured logging | App Insights / OpenTelemetry, dashboards, alerts |
| Data | Synthetic KB | Governed content pipeline with review/approval |

## 7. Government / county security overlays (summary)

Detailed in [security-and-government-overlays.md](security-and-government-overlays.md). Highlights:

- Data residency & region selection; consider sovereign/government cloud options.
- PII minimization, retention limits, and transparency to residents.
- Human-in-the-loop / escalation for sensitive intents (legal, emergency, benefits).
- Accessibility (e.g., WCAG / Section 508 alignment) for public-facing UI.
- Least-privilege identity, audit logging, and content-safety guardrails.

> This is **guidance, not a compliance attestation.** Engage the jurisdiction's security,
> privacy, and legal stakeholders before production.

## 8. Decisions left to the jurisdiction

- Hosting target for production scale-out (Functions vs Container Apps).
- Whether the backend or APIM holds the Foundry session — this build keeps it in the backend for testability.
- Government vs commercial cloud and data-residency region.
- Content review/approval pipeline for non-synthetic knowledge-base data.
