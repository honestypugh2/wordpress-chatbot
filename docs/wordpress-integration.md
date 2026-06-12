# WordPress Integration

> How the **experience layer** (WordPress on AWS) connects to the **intelligence layer**
> (Azure AI Foundry via APIM). Both the plugin (proxy) and the JS widget are implemented
> in [../wordpress](../wordpress).

## 1. Integration goal

WordPress stays the front door. We add a **chat widget** that calls the **APIM AI Gateway**
endpoint — never Foundry directly. The widget is intentionally thin: capture input, render
responses, manage a session id, and call one HTTPS endpoint.

```
WordPress page ──▶ Chat widget (JS) ──▶ APIM endpoint ──▶ backend ──▶ Foundry agent
```

## 2. Plugin vs custom JavaScript widget

| Dimension | Custom JS widget ✅ (demo default) | WordPress plugin |
| --- | --- | --- |
| Speed to demo | Fast — drop a script tag / block | Slower — plugin install, lifecycle |
| Control over UX | Full control of markup/CSS | Constrained by plugin conventions |
| Distribution | Per-site embed | Reusable, installable, settings UI |
| Maintenance | Manual updates | Versioned, update channel |
| Admin config | `.env` / build-time | WP admin settings page (key, endpoint) |
| Best for | Quick demo / single county site | Productized rollout to many sites |

**Recommendation: custom JavaScript widget for quick demos, the plugin (proxy mode) for
anything beyond a demo.** The widget minimizes WordPress-side moving parts and keeps the
AWS footprint unchanged; the plugin keeps the APIM key server-side and adds admin-managed
config and multi-site reuse.

### 2a. Custom JS widget

Embed via a child theme, a custom HTML block, or a snippet plugin:

```html
<div id="county-assistant"></div>
<script>
  window.CountyAssistant = {
    endpoint: "https://<your-apim>.azure-api.net/assistant/chat",
    // Subscription key handling: see §4 — do NOT hard-code a privileged key in public HTML.
  };
</script>
<script src="https://<your-cdn>/county-assistant-widget.js" defer></script>
```

### 2b. Plugin path (recommended beyond demos)

The included plugin ([../wordpress/plugin](../wordpress/plugin)):
- registers a shortcode (`[county_assistant]`) and a footer container,
- exposes an admin settings page (APIM endpoint, **server-side** key, greeting),
- enqueues the widget bundle,
- proxies chat through a **same-origin REST route** with **nonce** validation and input
  sanitization, so the APIM key never reaches the browser.

See [../wordpress/README.md](../wordpress/README.md) for the file-by-file map.

## 2c. Browser-direct vs WordPress-proxy API calls

| | **Browser-direct** (JS widget) | **WordPress-proxy** (plugin) |
| --- | --- | --- |
| Call path | Browser → APIM → backend → Foundry | Browser → WP REST route → APIM → backend → Foundry |
| Key exposure | Public, **tightly-scoped** APIM key in client config | Key stays **server-side**; never sent to browser |
| CORS | APIM must allow the WordPress origin | Same-origin call; **no third-party CORS** |
| Abuse protection | APIM rate-limit + content-safety (must be strict) | WP nonce + APIM controls (defense in depth) |
| Setup speed | Fastest (paste a snippet) | Plugin install + settings |
| Recommended for | Demos / low-risk public info | **Production** |

**Recommendation:** demo with the **browser-direct widget**; ship with the **plugin
(proxy mode)**. In browser-direct mode, the APIM route must be a public product key with
strict rate limits and content safety — never a privileged key.
## 3. Why APIM sits between WordPress and Foundry

(Full rationale in [architecture-overview.md](architecture-overview.md#5-why-apim-sits-between-wordpress-and-foundry).)
In short, APIM gives one governed hop for **auth, rate limiting, token quotas, content safety,
the AWS↔Azure boundary (CORS/TLS), and centralized observability** — so the public widget holds
no Foundry credentials and cost/safety are enforced consistently.

## 4. Key handling & CORS (important)

- **Do not** embed a privileged APIM subscription key in public HTML/JS. Options:
  - A **public, tightly-scoped** APIM product key with strict rate limits + content safety, **or**
  - A **session-token broker**: the widget first calls a backend endpoint that issues a short-lived,
    origin-bound token used for subsequent chat calls. *(Recommended for production.)*
- Configure **CORS** to allow only the WordPress origin(s). Backend CORS is set via
  `APP_CORS_ORIGINS`; APIM should mirror this at the gateway.
- Enforce **TLS** end to end and prefer **POST** with JSON bodies.

## 5. Current build vs production hardening

| | This build | Production hardening |
| --- | --- | --- |
| Embed | Plugin proxy or script tag / HTML block | Versioned plugin or managed embed |
| Key | Server-side key (plugin) or scoped public product key | Session-token broker, no static key |
| Hosting of widget JS | Any static host / repo | CDN with caching + integrity (SRI) |
| CORS | WordPress origin allow-list | Same, plus WAF / Front Door |
| Sessions | In-memory / stateless | Durable session store, expiry policy |

## 6. Accessibility & UX notes

- Public-sector UI should target **WCAG / Section 508** alignment (keyboard nav, ARIA labels,
  color contrast, screen-reader friendly transcript). *(Guidance, not an attestation.)*
- Always show a clear "AI-generated — verify important details" disclosure and an easy path to
  reach a human or the relevant department page.

## 7. Decisions left to the jurisdiction

- Final key strategy for public embeds (scoped public key vs token broker) — **token broker recommended**.
- Whether to ship the plugin or the JS widget for a given site.
- Widget hosting / CDN choice.
