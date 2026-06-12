# Assumptions & Alternatives

> Customer-ready summary of design assumptions, the architecture options we
> considered, and the path from prototype to hardened production. This document
> **does not make compliance claims**; suitability decisions belong to the
> jurisdiction's security, privacy, and legal stakeholders.

## 1. Key assumptions (explicit)

| # | Assumption | Why / impact |
| --- | --- | --- |
| A1 | **Hybrid** SDK pattern: Azure AI Foundry (azure-ai-projects ~= 2.2.0) is the system of record for the model; orchestration is implemented locally (Agent-Framework-inspired). | Runs offline for demos; lifts cleanly into Foundry prompt agents/tools. |
| A2 | Prototype runs in **local fallback** when Foundry isn't configured. | Zero cloud dependency to evaluate the experience. |
| A3 | Retrieval is a transparent **local TF-IDF** index over synthetic Markdown. | No external services; swappable for Azure AI Search via the same `Retriever` interface. |
| A4 | **APIM** is the single public entry point (AI gateway). | Centralizes auth, throttling, caching, safety, observability. |
| A5 | WordPress stays on **AWS**, unchanged. | Separation of experience and intelligence layers. |
| A6 | All county content is **synthetic/fictional** (County of Westvale). | No reuse of real county content; safe for public demos. |
| A7 | Commercial Azure region for the prototype. | Government/sovereign cloud is a production decision (see §4). |
| A8 | Version baselines: azure-ai-projects ~= 2.2.0, agent-framework ~= 1.8.0, uv ~= 0.11.19. | Verify latest stable at implementation time. |

## 2. SDK pattern alternatives

| Option | Pros | Cons | Verdict |
| --- | --- | --- | --- |
| **Foundry SDK first** | Managed identity, server-side tools, connections, content safety. | Less local orchestration flexibility. | Used for inference. |
| **Agent Framework first** | Rich client-side orchestration + local eval. | Re-owns hosting/identity/governance. | Concepts adopted. |
| **Hybrid** ✅ | Governance server-side + orchestration/eval flexibility; portable. | Slightly more moving parts. | **Chosen.** |

## 3. WordPress hosting on AWS — architecture alternatives

All keep WordPress as the front door; they differ in scalability and hardening.

### 3a. EC2 + ALB + CloudFront + WAF
- **Shape:** WordPress on EC2 (or an Auto Scaling Group) behind an Application Load
  Balancer, fronted by CloudFront with AWS WAF; RDS (MySQL) for the database.
- **Pros:** familiar, full OS control, straightforward lift of existing sites.
- **Cons:** you patch/scale the instances; less elastic than containers.
- **Best for:** existing EC2-hosted county sites wanting CDN + WAF hardening.

### 3b. ECS/Fargate + ALB + CloudFront + WAF
- **Shape:** containerized WordPress on ECS/Fargate behind an ALB, CloudFront + WAF
  at the edge; RDS + EFS (for `wp-content`/uploads).
- **Pros:** serverless containers, easy horizontal scale, immutable images.
- **Cons:** container packaging + shared storage considerations for WordPress.
- **Best for:** teams standardizing on containers and CI/CD image pipelines.

### 3c. Simpler prototype path
- Single EC2 or a managed WordPress host; CloudFront optional; the **JS widget**
  embedded via a Custom HTML block; APIM dev tier; backend run locally or in a
  single container. Fastest to demo.

### 3d. Hardened production path
- Multi-AZ ECS/Fargate (or ASG) behind ALB; CloudFront + WAF; RDS Multi-AZ; the
  **WordPress plugin** (proxy mode) so no key reaches the browser; APIM with full AI
  policies + private networking; backend on Azure Container Apps (zone-redundant,
  autoscaled) with managed identity + Key Vault + App Insights.

> The **Azure side** is unchanged across all AWS options — APIM → backend → Foundry —
> which is the point of separating the experience and intelligence layers.

## 4. Production hardening checklist (next steps)

- **Identity/secrets:** managed identity end to end; Key Vault references; remove
  any static keys; token-broker or proxy so the browser holds no privileged key.
- **Retrieval:** Azure AI Search index with embeddings + scheduled refresh; replace
  the local TF-IDF retriever behind the same interface.
- **Foundry:** adopt persisted Foundry agents with server-side tools/threads if the
  use case needs tool execution and conversation state.
- **APIM:** enable token-limit, semantic cache, and content-safety policies; private
  endpoints/VNet; WAF/Front Door; per-product keys with quotas.
- **Observability:** OpenTelemetry → App Insights; dashboards + alerts; PII-scrubbed
  logs; correlation across WordPress → APIM → backend → Foundry.
- **Governance:** data residency/sovereign-cloud decision; retention/deletion policy;
  human-in-the-loop for sensitive intents; accessibility (WCAG/508) review.
- **Content:** replace synthetic KB with a governed content pipeline (review/approval).

See [security-and-government-overlays.md](security-and-government-overlays.md) and
[architecture-overview.md](architecture-overview.md) for detail.
