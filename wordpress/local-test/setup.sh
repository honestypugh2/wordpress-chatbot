#!/usr/bin/env bash
# Configure the local WordPress test site for the County Assistant plugin.
#
# Runs WordPress install (idempotent), activates the county-assistant plugin,
# and points it at the REAL Azure APIM endpoint + subscription key so the local
# site exercises the full browser -> WP proxy -> APIM -> Function -> Foundry path.
#
# Prereqs:
#   docker compose up -d        (db + wordpress + wpcli running)
#   APIM_URL and APIM_KEY exported (or passed as $1 and $2)
#
# Usage:
#   export APIM_URL="https://<apim>.azure-api.net/assistant/chat"
#   export APIM_KEY="<subscription-key>"
#   ./setup.sh
set -euo pipefail

SITE_URL="${SITE_URL:-http://localhost:8083}"
ADMIN_USER="${ADMIN_USER:-admin}"
ADMIN_PASS="${ADMIN_PASS:-admin-password}"
ADMIN_EMAIL="${ADMIN_EMAIL:-admin@example.test}"
APIM_URL="${1:-${APIM_URL:-}}"
APIM_KEY="${2:-${APIM_KEY:-}}"

wp() { docker compose exec -T wpcli wp --allow-root "$@"; }

echo "==> Waiting for WordPress to answer on ${SITE_URL} ..."
for _ in $(seq 1 30); do
  if curl -fsS -o /dev/null "${SITE_URL}/wp-login.php"; then break; fi
  sleep 2
done

echo "==> Installing WordPress (idempotent) ..."
if ! wp core is-installed 2>/dev/null; then
  wp core install \
    --url="${SITE_URL}" \
    --title="County of Westvale (Local Test)" \
    --admin_user="${ADMIN_USER}" \
    --admin_password="${ADMIN_PASS}" \
    --admin_email="${ADMIN_EMAIL}" \
    --skip-email
fi

echo "==> Activating county-westvale theme ..."
wp theme activate county-westvale

echo "==> Activating county-assistant plugin ..."
wp plugin activate county-assistant

if [[ -n "${APIM_URL}" ]]; then
  echo "==> Pointing plugin at APIM: ${APIM_URL}"
  # Store options as a PHP-serialized array via wp option update --format=json.
  wp option update county_assistant_options --format=json <<JSON
{
  "enabled": "1",
  "apim_url": "${APIM_URL}",
  "apim_subscription": "${APIM_KEY}",
  "greeting": "Hi! I can help with Westvale County services — permits, taxes, voting, health, and more."
}
JSON
else
  echo "!! APIM_URL not provided — plugin activated but not yet configured."
  echo "   Re-run: ./setup.sh \"<apim-url>\" \"<apim-key>\"  (or set the env vars)"
fi

echo ""
echo "==> Done. Open ${SITE_URL}  (admin: ${ADMIN_USER} / ${ADMIN_PASS})"
echo "    The County Assistant launcher appears bottom-right on the site."
