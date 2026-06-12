# Reference Architecture

> **Slide-quality diagrams** for the County Assistant prototype. Three views:
> **baseline**, **advanced**, and **county-government tailored**. All content is
> synthetic; no real county content is depicted.
>
> Editable [draw.io](diagrams/) sources and SVG renders for these diagrams live in
> [docs/diagrams/](diagrams/). The Mermaid versions below render inline on GitHub.

Positioning, repeated for slides:

> **This architecture separates the experience layer from the intelligence layer.**
> **WordPress on AWS remains the front door, while Azure AI Foundry becomes the brain.**

---

## 1. Baseline architecture

The minimal end-to-end path: a WordPress widget calls APIM, which fronts a thin backend that
talks to a Foundry agent grounded on a small knowledge base.

![Baseline architecture](diagrams/baseline-architecture.svg)

> Editable source: [baseline-architecture.drawio](diagrams/baseline-architecture.drawio)

```mermaid
flowchart LR
    user([Resident / Public User])

    subgraph AWS["AWS — Experience Layer"]
        wp["WordPress Site<br/>+ Chat Widget"]
    end

    subgraph AZURE["Azure — Intelligence Layer"]
        apim["API Management<br/>(AI Gateway)"]
        api["Azure Function<br/>(default backend)"]
        subgraph FOUNDRY["Azure AI Foundry"]
            agent["County Agent"]
            model["Model Deployment"]
            kb["Retrieval<br/>(Synthetic County KB)"]
        end
    end

    user --> wp --> apim --> api --> agent
    agent --> model
    agent --> kb

    classDef aws fill:#FF9900,stroke:#7a4900,color:#1b1b1b;
    classDef azure fill:#0078D4,stroke:#004578,color:#ffffff;
    classDef foundry fill:#50E6FF,stroke:#004578,color:#1b1b1b;
    class wp aws;
    class apim,api azure;
    class agent,model,kb foundry;
```

---

## 2. Advanced architecture

Adds production-grade edges: CDN/WAF in front of WordPress, managed identity, Key Vault,
Azure AI Search as the retrieval store, tools, content safety, and observability.

![Advanced architecture](diagrams/advanced-architecture.svg)

> Editable source: [advanced-architecture.drawio](diagrams/advanced-architecture.drawio)

```mermaid
flowchart LR
    user([Resident / Public User])

    subgraph AWS["AWS — Experience Layer"]
        cf["CloudFront / WAF"]
        wp["WordPress<br/>+ Chat Widget"]
        cf --> wp
    end

    subgraph EDGE["Azure Edge"]
        fd["Front Door / WAF"]
        apim["API Management<br/>(AI Gateway)<br/>auth • quotas • token metering<br/>content safety • logging"]
        fd --> apim
    end

    subgraph APP["Azure — Application"]
        api["Azure Function (Flex)<br/>default · or Container Apps"]
        mi["Managed Identity"]
        kv["Key Vault"]
        api -.-> mi
        api -.-> kv
    end

    subgraph FOUNDRY["Azure AI Foundry — Intelligence Layer"]
        agent["County Agent<br/>(hosted)"]
        model["Model Deployment(s)"]
        tools["Tools / Functions"]
        safety["Content Safety"]
    end

    subgraph DATA["Grounding & Data"]
        search["Azure AI Search<br/>(county-kb index)"]
        store["Synthetic KB Source<br/>(data/)"]
        store --> search
    end

    subgraph OBS["Observability"]
        appi["App Insights / OTEL"]
    end

    user --> cf
    wp --> fd
    apim --> api --> agent
    agent --> model
    agent --> tools
    agent --> safety
    agent --> search
    api -.-> appi
    apim -.-> appi

    classDef aws fill:#FF9900,stroke:#7a4900,color:#1b1b1b;
    classDef azure fill:#0078D4,stroke:#004578,color:#ffffff;
    classDef foundry fill:#50E6FF,stroke:#004578,color:#1b1b1b;
    classDef data fill:#7FBA00,stroke:#3a5400,color:#1b1b1b;
    class cf,wp aws;
    class fd,apim,api,mi,kv azure;
    class agent,model,tools,safety foundry;
    class search,store,appi data;
```

---

## 3. County-government tailored architecture

Maps the same pattern to county portal categories (synthetic) and adds SLG overlays:
escalation/human-in-the-loop, audit logging, and PII minimization.

```mermaid
flowchart TB
    user([Resident])

    subgraph AWS["AWS — county-portal.example.gov (Experience Layer)"]
        wp["WordPress Portal<br/>Departments • Services • FAQs<br/>Permits • Taxes • Health<br/>Emergency • Voting • Report a Concern"]
        widget["County Assistant Widget"]
        wp --- widget
    end

    subgraph GATEWAY["Azure API Management — AI Gateway"]
        apim["AuthN/Z • Rate limit • Token quota<br/>Content safety • Audit logging"]
    end

    subgraph BRAIN["Azure AI Foundry — Intelligence Layer"]
        agent["County Assistant Agent<br/>(synthetic county persona)"]
        model["Model Deployment"]
        subgraph TOOLS["Tools"]
            t1["Service / Department lookup"]
            t2["Permit & tax FAQ"]
            t3["Emergency & alerts info"]
            t4["Report-a-concern intake"]
        end
    end

    subgraph GROUND["Grounding"]
        kb["Synthetic County KB<br/>(departments, services, FAQs)"]
    end

    subgraph OVERLAY["SLG Overlays"]
        esc["Human-in-the-loop / Escalation<br/>(legal • benefits • emergency)"]
        audit["Audit Log & Retention"]
        pii["PII Minimization"]
    end

    user --> widget --> apim --> agent
    agent --> model
    agent --> TOOLS
    agent --> kb
    agent -. sensitive intent .-> esc
    apim -.-> audit
    agent -.-> pii

    classDef aws fill:#FF9900,stroke:#7a4900,color:#1b1b1b;
    classDef azure fill:#0078D4,stroke:#004578,color:#ffffff;
    classDef foundry fill:#50E6FF,stroke:#004578,color:#1b1b1b;
    classDef overlay fill:#E3008C,stroke:#6e0044,color:#ffffff;
    class wp,widget aws;
    class apim azure;
    class agent,model,t1,t2,t3,t4 foundry;
    class kb foundry;
    class esc,audit,pii overlay;
```

---

## Request lifecycle (sequence)

![Chat request sequence](diagrams/chat-sequence.svg)

> Editable source: [chat-sequence.drawio](diagrams/chat-sequence.drawio)

```mermaid
sequenceDiagram
    actor U as Resident
    participant W as WordPress Widget (AWS)
    participant G as APIM (AI Gateway)
    participant B as Azure Function (backend)
    participant F as Foundry Agent
    participant R as Retrieval (County KB)

    U->>W: Ask a question
    W->>G: POST /county-assistant/chat (+ subscription key)
    G->>G: Auth, rate limit, content safety
    G->>B: Forward request
    B->>F: Run agent (thread/session)
    F->>R: Retrieve grounding (RAG)
    R-->>F: Relevant synthetic KB passages
    F-->>B: Grounded answer (+ citations)
    B-->>G: Response
    G-->>W: Response (logged, metered)
    W-->>U: Render answer in widget
```

> All diagrams are **illustrative**. Colors and Azure/AWS service choices are
> suggestions; final services and network topology are decided per deployment.

---

## Decision record — Gateway: APIM + WordPress plugin proxy

**Decision:** For the SLED (State / Local / Education / Government) scenario, the
production front door is the **WordPress plugin proxy (AWS-side) → Azure API
Management AI Gateway (Azure-side) → Azure AI Foundry**. These are complementary
layers, not alternatives. **AWS API Gateway is explicitly not used.**

```
Browser → WordPress plugin proxy (AWS, hides key) → APIM AI Gateway (Azure, governs) → Foundry
```

**Why APIM (not "no gateway" or AWS API Gateway):**

- **Auditability & accountability** — Public-records and oversight expectations
  require central logging of every citizen interaction across all front-ends.
- **Cost control / FinOps** — APIM AI-gateway token-based throttling and quotas
  bound model spend against a fixed agency budget. The plugin proxy and AWS API
  Gateway cannot meter tokens or model cost.
- **Responsible AI** — Content-safety / prompt-shield controls sit in front of the
  model in APIM, supporting SLED procurement requirements.
- **Governance next to the model** — Model and data live in Azure; keeping the AI
  gateway, managed identity, and logging in Azure avoids stretching trust across
  AWS → Azure.
- **Defense in depth** — The plugin proxy keeps the APIM subscription key
  server-side on AWS so it never reaches the browser.

**When APIM can be skipped:** throwaway internal demos or pilots with no public
traffic and no budget/audit requirements. For any resident-facing deployment,
APIM stays in.

**Independence:** This gateway decision holds regardless of whether the
intelligence layer is a FastAPI orchestrator or a Foundry prompt agent — APIM
sits in front of either.
