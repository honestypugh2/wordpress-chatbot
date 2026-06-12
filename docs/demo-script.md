# Demo Script — County Assistant (20-minute customer walkthrough)

A **20-minute, story-driven** walkthrough for a county-government customer. The goal is
not just to show a chatbot — it is to **win the customer and open new opportunities** by
proving one idea end to end:

> **Keep WordPress on AWS as your front door. Add Microsoft Foundry as the brain.
> Govern everything through one Azure AI Gateway (APIM).**

The **County of Westvale** content is **synthetic and fictional**. The **staging**
profile (display name *County of Lakeside*) is a demo persona, but it grounds via
**Grounding with Bing Custom Search** scoped to a **real, public county website**, so
those answers surface that site's real content with real citations. **No real county
content is ever ingested, scraped, or stored** — Bing runs the query server-side and
returns citations only; Azure AI Search indexes the synthetic Westvale KB exclusively.
The prototype runs fully offline (the `local` pattern) and lights up Azure AI Foundry
when configured.

**Timing at a glance**

| Section | Time | What the customer takes away |
|---|---|---|
| 1. Why we're here (the hook) | 2 min | We protect your existing investment and add AI safely |
| 2. High-level architecture + components | 4 min | Each Azure piece has a clear, governed job |
| 3. The three grounding patterns | 2 min | You choose the trade-off; you're never locked in |
| 4. The staging-site grounding story | 2 min | We can ground on *your* live site without touching it |
| 5. Live demo (Hybrid → contrast) | 8 min | It actually works — with citations, safety, and control |
| 6. Close + call to action | 2 min | A concrete next step toward production |

---

## 0. Pre-flight (before the customer joins — not part of the 20 min)

Bring the demo up against the **live Azure** backend so the customer sees the real path
(WordPress → APIM → Azure Functions → Foundry), not a localhost mock:

```bash
cd wordpress/local-test
./wp-control.sh demo hybrid westvale   # switch routing + site, then start the app
```

Open <http://localhost:8083> and confirm the launcher (bottom-right) opens and greets you
as the **County of Westvale** assistant. Keep a second terminal ready for the
"under-the-hood" reveals. Optional offline fallback if the network is unavailable:
`uv run uvicorn app.main:app --reload --app-dir src` (API at `http://localhost:8000`).

---

## 1. Why we're here — purpose, goal, value prop (2 min)

**Tell the story, don't list features.** Open with the customer's world:

> "Your residents already come to your WordPress site for permits, taxes, voting, and
> health info. You've invested in that experience, it lives on AWS, and it works. The
> ask isn't to rip that out — it's to make it *answer questions* like a knowledgeable
> staff member, 24/7, without the resident ever leaving your site."

- **Purpose** — show how to add a grounded, governed AI assistant to an **existing
  AWS-hosted WordPress** site with **no migration** of the front door.
- **Goal of this session** — prove the architecture works end to end, on synthetic data,
  and that it scales cleanly from this prototype to a hardened production deployment.
- **Value proposition (say it plainly):**
  - **Protect the existing investment** — WordPress/AWS stays the experience layer.
  - **Grounded answers, not hallucinations** — every answer is built from *sources* with
    **citations**, so residents (and auditors) can trust it.
  - **Governed by design** — one Azure AI Gateway enforces auth, rate limits, token
    budgets, content safety, and logging *before* anything reaches the model.
  - **No lock-in** — three switchable grounding patterns; you pick the trade-off and can
    change it at runtime with no code change.

> Transition: *"Let me show you how the pieces fit — and then we'll watch it work."*

---

## 2. High-level architecture + component roles (4 min)

Open [reference-architecture.md](reference-architecture.md) and walk the **baseline →
advanced → county-tailored** diagrams. The one sentence to repeat:

> **This architecture separates the experience layer from the intelligence layer.**

```
Resident ─▶ WordPress (AWS, front door) ─▶ APIM (AI Gateway) ─▶ Azure Functions
                                                                   (orchestrator)
                                                                        │
                                                                        ▼
                                                              Microsoft Foundry (brain)
                                                       models • prompt agents • tools • safety
                                                                        │
                                              ┌─────────────────────────┴───────────────┐
                                         Azure AI Search                            Blob Storage
                                        (county-kb index)                       (source content)
```

**Walk each component and its job** (this is the part the customer remembers):

| Component | Role in this solution | Why it matters to the customer |
|---|---|---|
| **WordPress on AWS** (or **Azure App Service**) | The **experience layer / front door** — branding, content, accessibility, and the chat widget the resident sees. Hosted on AWS today; the *same* pattern works if WordPress is later hosted on **Azure App Service** (managed WordPress) — no architecture change. | Zero disruption. Keep your CMS, your team's skills, and your hosting choice. |
| **Azure API Management (APIM)** | The **AI Gateway** — the single, public, governed entry point. Handles auth (subscription key swap), rate limiting, **token budgets**, content-safety hooks, caching, correlation IDs, and logging. Also fronts the model on a `/openai` API so even model calls are metered and key-free (managed identity). | The public **never** touches the model directly. Cost, safety, and audit live in one place. |
| **Azure Functions** (Flex Consumption) | The **thin orchestrator backend** — manages session/thread state, selects the retrieval pattern, routes intents (info vs. action vs. safety), and calls Foundry. **Serverless, scale-to-zero** → you pay only when residents ask. | Low idle cost, elastic scale for spikes (e.g., tax deadline, election day). The same code can run on **App Service / Container Apps** if you want always-on. |
| **Microsoft Foundry** | The **brain** — model deployments, the **prompt agent** with county-specific instructions, server-side **tools** (AI Search tool, Grounding with Bing Custom Search tool), connections, and content safety. | Governance and tooling are managed for you; the model is never exposed to the open internet. |
| **Azure AI Search** | The **retrieval store** — the `county-kb` index (keyword + semantic + vector) that grounds answers in *your* curated content. | Accurate, current, **governed** answers that stay inside the Azure compliance boundary. |
| **Azure Blob Storage** | The **source-of-truth content store** — holds the synthetic county documents that are ingested into the AI Search index (and backs the Functions deployment/runtime). | A clean content pipeline: publish to storage → index → ground. No scraping. |

> Key message: *"Every box has one job, and the gateway makes the whole thing
> governable. That's what turns a demo into something a county can actually run."*

---

## 3. The three grounding patterns (2 min)

Open [retrieval-patterns.md](retrieval-patterns.md). The chatbot **answers from sources,
not from memory** — and you choose where those sources come from. All three are
switchable at runtime via `RETRIEVAL_PATTERN`, **no code change, no redeploy**.

| # | Pattern | Grounding source | Best for |
|---|---------|------------------|----------|
| **1** | **Bing Custom Search** (`bing`) | Your **live, public** county website (scoped domains) via *Grounding with Bing Custom Search* | A site that's already live and indexed; always-current content |
| **2** | **Azure AI Search / RAG** (`azure_search`) | **Your curated content** ingested into an Azure AI Search index | Owned content, accuracy, governance, staying in the Azure boundary |
| **3** | **Hybrid** (`hybrid`) ✅ | **AI Search first**, with **Bing fallback** when the index has no good answer | The recommended default — accuracy *and* coverage |

> There's also a `local` offline mode (in-memory KB) that makes the whole thing run with
> zero cloud config — handy for air-gapped demos.

> Transition: *"Pattern 1 raises a great question for public sector — what if the site
> isn't indexed yet, or it's still in staging? Let me show you how we handle that."*

---

## 4. The staging-site grounding story — the "how" and "why" (2 min)

This is a **differentiator** — slow down and make it land.

**The why.** Counties almost always want to evaluate the assistant **before go-live**, on
a **staging** site. But *Grounding with Bing Custom Search only returns results for pages
that are public and already indexed by Bing* — and staging subdomains are typically
`noindex` / auth-gated / brand-new. So a naive Bing demo on a staging site returns
**nothing** — which would misrepresent the architecture. (Full detail:
[bing-custom-search-limitations.md](bing-custom-search-limitations.md).)

**The how (the clever part).** We **decouple where the chatbot lives from where it gets
its answers**:

- The chatbot **widget is embedded on OUR demo WordPress** (the synthetic site at
  `localhost:8083`) — so we fully control the experience and nothing touches the
  customer's environment.
- The **Foundry prompt agent** is configured with the **Grounding with Bing Custom
  Search** tool, scoped (via `BING_ALLOWED_DOMAINS`) to the **customer's actual public
  site**. The grounding happens **server-side in Foundry** against the real domain.

So the customer sees their **own site's content** answering questions inside our safe
demo shell — **without us scraping, ingesting, or modifying their site at all**. It's a
faithful preview of "what your live site would feel like with the assistant" while
staying entirely read-only and hands-off.

> **Why we don't embed the widget on the real `staging.venturacounty.gov` site.** That
> site is a **third-party, AWS-hosted WordPress we don't own or control** — adding the
> assistant there would require installing **this** WordPress plugin / widget JS on
> *their* WordPress, which we can't do. So we host the widget on our own demo WordPress
> and point the Foundry Bing tool at their **public** domain instead. In a real
> engagement the customer would install the same plugin on their own site; the grounding
> and gateway stay identical.

> Honest framing (builds trust): *"For a site that isn't public yet, the right production
> pattern is AI Search RAG over content you own — same gateway, same agent, no indexing
> dependency. We'll use that for owned content; Bing is for the live, public site."*

---

## 5. Live demo — start with Hybrid, then contrast (8 min)

We lead with **Pattern 3 (Hybrid)** on purpose: **it exercises both Pattern 2 (AI Search)
and Pattern 1 (Bing) in a single flow**, so the customer sees the whole capability before
we break it down.

### 5a. Hybrid on the County of Westvale (≈3 min)

The app is already running in Hybrid + Westvale (from pre-flight). In the browser at
<http://localhost:8083>, open the launcher and ask a question that lives **in the curated
KB**:

> **"How do I apply for a building permit and how much does it cost?"**

Point out, live in the widget:
- a **grounded answer** in plain language,
- **citations** to the source — transparency residents and auditors can trust,
- speed and tone appropriate for a public audience.

Now ask something **outside** the curated KB to trigger the **Bing fallback**:

> **"What are the hours for the closest county park this weekend?"**

> Narrate: *"Hybrid checked the knowledge base first; when it didn't find a strong match,
> it automatically fell back to web grounding — so residents still get an answer, and you
> still keep curated content authoritative when it exists."*

**Under the hood (second terminal)** — show it's the real governed path, not a mock:

```bash
# Subscription key is auto-fetched from Azure by wp-control.sh; this is the same
# APIM endpoint the WordPress widget calls.
curl -s -X POST "$APIM_CHAT_URL" \
  -H 'Content-Type: application/json' \
  -H "Ocp-Apim-Subscription-Key: $KEY" \
  -d '{"message":"How do I apply for a building permit and how much does it cost?","session_id":"demo"}' | jq '{answer, mode, citations}'
```

Call out `mode` — `ai-search-grounding` for KB hits, `bing-grounding` on fallback — and
the `X-Correlation-Id` header that flows WordPress → APIM → Functions → Foundry.

### 5b. Show the same shell becomes the customer's site (≈2 min)

Switch to the **staging** profile (the customer's live, public site) — **one command**:

```bash
cd wordpress/local-test
./wp-control.sh demo bing staging   # Bing grounding + County of Lakeside profile
```

Reload <http://localhost:8083>. The widget **re-themes itself** (title/greeting follow the
profile via `GET /api/site`), and answers are now grounded on the **customer's real public
domain** via Bing Custom Search — all inside our demo shell, nothing installed on their
site. Tie it back to Section 4: *"This is exactly the 'preview your live site' story."*

> **Optional flourish — overlay the widget on the customer's *real* live site (visual
> only).** You can open a second browser window/profile, navigate to the customer's
> actual public site (e.g. `staging.venturacounty.gov`), and inject the widget JS via a
> **bookmarklet or a browser extension/userscript** that loads
> [../wordpress/widget/county-assistant-widget.js](../wordpress/widget/county-assistant-widget.js)
> in **browser-direct** mode. This makes the assistant *appear* to float on their real
> page for a striking "this is what it looks like on your site" moment. Important caveats
> to state honestly:
> - It is **purely client-side in your browser** — we are **not** modifying, deploying
>   to, or installing anything on the customer's AWS-hosted WordPress (we don't control
>   it). A real rollout means installing **this** plugin on *their* WordPress.
> - **We cannot just `<iframe>` the live site** — government sites typically send
>   `X-Frame-Options` / CSP `frame-ancestors` that block being framed. The bookmarklet/
>   extension approach side-steps that by running on the page's own origin.
> - The widget calls **APIM directly** from the `venturacounty.gov` origin, so **APIM
>   CORS must allow that origin** or the chat requests will be blocked. The grounding is
>   identical to the `bing staging` profile above.
>
> If the overlay isn't pre-set up, **don't improvise it live** — the safe, repeatable
> version of this story is the re-themed demo shell shown above.

### 5c. Governance, workflow, and safety — why this is enterprise-ready (≈3 min)

Open [../apim/policies/chat-operation.policy.xml](../apim/policies/chat-operation.policy.xml)
and name the guardrails the gateway enforces on **every** request: auth/key mediation,
rate limiting, **token budgets**, content-safety hook, caching, correlation propagation,
and backend routing.

Then show the orchestrator's **intent routing** — that this is an *assistant*, not just a
search box:

```bash
# Action/workflow intent — short-circuits to an actionable next step (311 intake)
curl -s -X POST "$APIM_CHAT_URL" -H 'Content-Type: application/json' \
  -H "Ocp-Apim-Subscription-Key: $KEY" \
  -d '{"message":"I want to report a pothole on Elm Street","session_id":"demo"}' | jq '.answer, .route'

# Safety intent — never answered by the model; redirected to 911
curl -s -X POST "$APIM_CHAT_URL" -H 'Content-Type: application/json' \
  -H "Ocp-Apim-Subscription-Key: $KEY" \
  -d '{"message":"this is an emergency, someone is hurt","session_id":"demo"}' | jq '.answer, .route'
```

> Message: *"Sensitive intents — emergencies, legal, benefits — are intercepted and
> escalated, never improvised by the model. For a government audience, that safety floor
> is non-negotiable, and it's built in."*

---

## 6. Close — why Pattern 3 wins, and the call to action (2 min)

**Recommend Hybrid (Pattern 3)** and contrast it head-to-head:

| Aspect | 1 · Bing Custom Search | 2 · Azure AI Search (RAG) | 3 · **Hybrid** ✅ |
|---|---|---|---|
| **Freshness** | ✅ Always current (live web) | ⚠️ As fresh as last ingest | ✅ Current via fallback |
| **Accuracy / control** | ⚠️ Whatever is published | ✅ Curated & governed | ✅ Curated first, web as backup |
| **Coverage** | ⚠️ Only indexed pages | ⚠️ Only ingested content | ✅ Best of both |
| **Works pre-launch / staging** | ❌ Needs public + indexed | ✅ No indexing dependency | ✅ Yes (KB path) |
| **Stays in Azure boundary** | ❌ Leaves boundary | ✅ Yes | ✅ For KB answers |

> *"Pattern 3 gives you the **accuracy and governance** of your curated content **and** the
> **coverage** of the live web — without forcing a choice. That's why it's our recommended
> default."*

**Recap the value prop in one breath:** existing WordPress/AWS front door untouched;
Foundry adds the intelligence; APIM governs cost, safety, and audit centrally; grounded,
cited answers; and a clean path from this prototype to production.

**Call to action (open the opportunity):**
1. A short **content-readiness review** of the customer's WordPress to scope the AI Search
   ingest (Pattern 2/3).
2. A **scoped pilot** on one department (e.g., permits or taxes) on their staging site.
3. A **production hardening plan** — Key Vault, private networking, Front Door/WAF, region
   selection, and SLG overlays — see
   [assumptions-and-alternatives.md](assumptions-and-alternatives.md) and
   [security-and-slg-overlays.md](security-and-slg-overlays.md).

---

## Appendix — switching during Q&A

```bash
cd wordpress/local-test
./wp-control.sh demo hybrid westvale     # recommended default (RAG + Bing fallback)
./wp-control.sh demo azure_search westvale  # pure RAG over curated KB
./wp-control.sh demo bing staging        # Bing grounding on the live/public site
./wp-control.sh demo local westvale      # fully offline (no cloud)
```

More prompts: [../data/demo_questions.md](../data/demo_questions.md). Architecture detail:
[architecture-overview.md](architecture-overview.md) and
[reference-architecture.md](reference-architecture.md).
