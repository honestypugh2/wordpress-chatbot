# Security & Government Overlays

> **Guidance, not a compliance attestation.** This document outlines security and
> state/local-government considerations. It does **not** claim conformance with any
> framework. Engage the jurisdiction's security, privacy, and legal stakeholders before any
> production use. Some items below are decisions for the jurisdiction rather than defaults.

## 1. Threat-model snapshot (cross-cloud)

The system spans AWS (WordPress) and Azure (APIM + Foundry). Key trust boundaries:

- **Public → WordPress (AWS):** untrusted input; standard web hardening + WAF.
- **WordPress → APIM (AWS→Azure):** cross-cloud seam; TLS, CORS allow-list, scoped keys.
- **APIM → Backend/Foundry (Azure):** private/managed-identity hop; no public credentials.
- **Foundry → Models/Data/Tools:** least-privilege connections; content safety.

Primary risks to design against: prompt injection, data exfiltration via tools/RAG, key
leakage in public JS, cost/abuse (token flooding), and oversharing of PII.

## 2. Identity & secrets

- **Managed identity** end-to-end in shared environments; avoid static keys in app code.
- **Key Vault** for any secrets; reference at runtime, never commit. `.env` is local-only.
- **Least privilege** RBAC for the backend's identity to Foundry, Search, and Key Vault.
- Public widget must **not** carry privileged keys — use a **session-token broker** (see
  [wordpress-integration.md](wordpress-integration.md#4-key-handling--cors-important)).

## 3. Gateway-enforced controls (APIM AI Gateway)

- **AuthN/Z**, **rate limiting**, and **token quotas** (per-key / per-IP / token-based).
- **Content safety / prompt-shield** hooks on inbound and outbound.
- **Audit logging** of requests (correlation id, route, latency, token usage) — PII-scrubbed.
- **CORS** restricted to WordPress origin(s); strict methods/headers.
- See [apim/policies/](../apim/policies/) for the applied policies and full references.

## 4. Data protection & privacy (privacy-sensitive)

- **PII minimization:** don't collect more than needed; redact before logging; avoid storing
  raw transcripts unless there's a defined, lawful purpose and retention limit.
- **Retention & deletion:** define retention windows and deletion paths up front — a
  **jurisdiction decision**.
- **Transparency:** clear "AI-generated" disclosure and links to authoritative county pages.
- **Grounding scope:** RAG limited to the **synthetic county KB**; the agent should decline or
  escalate out-of-scope/sensitive requests rather than improvise.
- **Data residency / sovereignty:** select region(s) deliberately; evaluate
  **government/sovereign cloud** options if the jurisdiction requires it. This build uses a
  standard commercial region with synthetic data only.

## 5. Human-in-the-loop & escalation

Route **sensitive intents** to a human or authoritative resource rather than answering directly:

- Legal advice, benefits eligibility determinations, emergencies (911/active hazards),
  individualized financial/tax advice, and anything implying enforcement action.
- Provide a visible, fast path to the relevant department contact / page.

## 6. Accessibility (public-sector requirement)

- Target **WCAG 2.1 AA / Section 508** alignment for the widget and transcript surface.
  *(Guidance, not an attestation.)*

## 7. Content-safety & abuse guardrails

- Apply content safety at the gateway **and** in the agent (defense in depth).
- Prompt-injection defenses: treat retrieved content as untrusted; constrain tool permissions;
  validate tool inputs/outputs.
- Abuse/cost controls: token quotas, request size limits, and anomaly alerts.

## 8. Observability & incident readiness

- Centralized, **PII-scrubbed** logging/metrics (App Insights / OpenTelemetry).
- Correlation ids across WordPress → APIM → backend → Foundry for traceability.
- Define alerting and an incident runbook before production — a **jurisdiction decision**.

## 9. Current build vs production hardening (security)

| Control | This build | Production hardening |
| --- | --- | --- |
| Identity | Managed identity / `DefaultAzureCredential` | Managed identity everywhere |
| Secrets | local `.env` + app settings | Key Vault references |
| Public key | server-side key (plugin) or scoped product key | session-token broker, no static key |
| Networking | public APIM Developer tier | private endpoints / VNet, WAF / Front Door |
| Logging | App Insights + structured logging | App Insights/OTEL, retention policy, alerts |
| Data | synthetic only | governed pipeline + retention/deletion policy |

## 10. Explicit non-claims

- No statement of conformance to FedRAMP, StateRAMP, CJIS, HIPAA, SOC 2, NIST 800-53, or any
  other framework is made or implied.
- Region/sovereign-cloud suitability, retention policy, and escalation workflows are
  **decisions for the jurisdiction**, not defaults of this build.

## 11. Decisions left to the jurisdiction

- Government vs commercial cloud and data-residency region.
- Retention / deletion windows for transcripts and logs.
- Token-broker design for public widget embeds and the specific APIM policy set.
