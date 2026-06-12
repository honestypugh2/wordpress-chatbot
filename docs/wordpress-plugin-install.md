# WordPress Plugin — How It Is "Installed" in This Repo

> Quick reference for how the County Assistant WordPress plugin gets installed,
> activated, and configured. For the broader plugin-vs-widget and proxy-vs-direct
> design tradeoffs, see [wordpress-integration.md](wordpress-integration.md).

## Short answer

The plugin is **not** installed on the real customer site (e.g.
`staging.venturacounty.gov`) — that site is AWS-hosted and outside our control.
Instead, the plugin runs in a **local Dockerized WordPress test harness** that mounts
the plugin straight from the repo and points it at the **real Azure APIM endpoint**.
This exercises the full path end to end without needing AWS:

```
browser ──▶ WP REST proxy (nonce) ──▶ APIM ──▶ Azure Function ──▶ Foundry agent
```

## How it works

The mechanism lives in [../wordpress/local-test/docker-compose.yml](../wordpress/local-test/docker-compose.yml)
and [../wordpress/local-test/setup.sh](../wordpress/local-test/setup.sh).

1. **Containers** — `docker compose up -d` starts:
   - `db` — MariaDB 11
   - `wordpress` — `wordpress:6-php8.3-apache`, published on port `8083`
   - `wpcli` — a one-shot admin helper sharing the same WordPress volume
2. **"Install" = a read-only volume mount, not a zip upload.** The repo's
   [../wordpress/plugin](../wordpress/plugin) folder is bind-mounted into the container so
   WordPress sees it as an installed plugin and repo edits show up after a reactivation:
   ```yaml
   ../plugin:/var/www/html/wp-content/plugins/county-assistant:ro
   ../theme/county-westvale:/var/www/html/wp-content/themes/county-westvale:ro
   ```
3. **Activation + configuration** via [../wordpress/local-test/setup.sh](../wordpress/local-test/setup.sh),
   which uses `wp-cli`:
   - `wp core install` (idempotent)
   - `wp theme activate county-westvale`
   - `wp plugin activate county-assistant`
   - `wp option update county_assistant_options` — writes the APIM URL, the
     **server-side** subscription key, and the greeting into the plugin's settings.

## Run it

```bash
cd wordpress/local-test
docker compose up -d

export APIM_URL="https://wpcounty-dev-apim-mro5df.azure-api.net/assistant/chat"
export APIM_KEY="<subscription-key>"
./setup.sh                 # or: ./setup.sh "<apim-url>" "<apim-key>"

# open http://localhost:8083  (admin: admin / admin-password)
```

The County Assistant launcher appears bottom-right on the site. Day-to-day pattern/site
switching is driven by [../wordpress/local-test/wp-control.sh](../wordpress/local-test/wp-control.sh).

## Plugin internals (proxy pattern)

The plugin runs in **proxy mode** so the APIM key never reaches the browser. File-by-file
map is in [../wordpress/README.md](../wordpress/README.md):

| File | Purpose |
| --- | --- |
| [../wordpress/plugin/county-assistant.php](../wordpress/plugin/county-assistant.php) | Plugin bootstrap, activation defaults. |
| [../wordpress/plugin/includes/class-settings.php](../wordpress/plugin/includes/class-settings.php) | Admin settings page (APIM URL, key, greeting); never echoes the key. |
| [../wordpress/plugin/includes/class-rest-proxy.php](../wordpress/plugin/includes/class-rest-proxy.php) | Same-origin REST proxy with **nonce** validation + input sanitization; injects the APIM key server-side. |
| [../wordpress/plugin/includes/class-widget.php](../wordpress/plugin/includes/class-widget.php) | Enqueues the widget, renders the container, registers the `[county_assistant]` shortcode. |
| [../wordpress/plugin/assets/widget.js](../wordpress/plugin/assets/widget.js) / [../wordpress/plugin/assets/widget.css](../wordpress/plugin/assets/widget.css) | Shared widget bundle (proxy mode). |

## Production rollout (vs this local harness)

In this repo "install" means *bind-mount the plugin into a local WordPress container and
activate it with wp-cli* — a faithful stand-in for installing it on the customer's
WordPress, without touching their AWS site. For a real rollout you would:

1. Package [../wordpress/plugin](../wordpress/plugin) as a `.zip`.
2. Install it on the customer's WordPress (Plugins → Add New → Upload, or WP-CLI).
3. Configure the APIM endpoint + **server-side** key in the plugin settings page.
4. Ensure APIM CORS and rate-limit/content-safety policies are set for that origin.

See [wordpress-integration.md](wordpress-integration.md) §2b and §4–5 for the production
hardening checklist.
