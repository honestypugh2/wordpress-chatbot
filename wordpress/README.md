# WordPress Integration Assets

Assets that connect the WordPress experience layer to the APIM AI Gateway. Two
integration options are provided — choose based on your rollout needs.

## A. WordPress plugin (`plugin/`) — recommended for production

A lightweight plugin that keeps the APIM key server-side and proxies requests.

| File | Purpose |
| --- | --- |
| [plugin/county-assistant.php](plugin/county-assistant.php) | Plugin bootstrap, activation defaults. |
| [plugin/includes/class-settings.php](plugin/includes/class-settings.php) | Admin settings page (APIM URL, key, greeting); sanitizes input, never echoes the key. |
| [plugin/includes/class-rest-proxy.php](plugin/includes/class-rest-proxy.php) | Same-origin REST proxy with **nonce validation** and input sanitization; injects the APIM key server-side. |
| [plugin/includes/class-widget.php](plugin/includes/class-widget.php) | Enqueues the widget, renders the container, registers a `[county_assistant]` shortcode. |
| [plugin/assets/widget.js](plugin/assets/widget.js) / [plugin/assets/widget.css](plugin/assets/widget.css) | The shared widget bundle (proxy mode). |

## B. Custom JavaScript widget (`widget/`) — fastest to embed

A standalone, dependency-free floating chat widget you can paste into a theme.

| File | Purpose |
| --- | --- |
| [widget/county-assistant-widget.js](widget/county-assistant-widget.js) | Floating launcher + panel, calls the backend, session persistence, citations. |
| [widget/county-assistant-widget.css](widget/county-assistant-widget.css) | Minimal, accessible, themeable styles. |
| [widget/embed-snippet.html](widget/embed-snippet.html) | Copy/paste embed for a WordPress HTML block or `footer.php`. |

## Choosing + security

- **Plugin (proxy mode):** browser calls a **same-origin** WordPress route; the APIM
  key stays server-side; a **nonce** guards the proxy. Best for production.
- **Widget (browser-direct mode):** browser calls APIM directly; requires a **public,
  tightly-scoped** APIM route (rate-limited + content-safe) and CORS to the WordPress
  origin. Fastest for a demo; never embed a privileged key in public HTML.

See [../docs/wordpress-integration.md](../docs/wordpress-integration.md) for the full
plugin-vs-widget, browser-direct-vs-proxy, and CORS/security tradeoffs.
