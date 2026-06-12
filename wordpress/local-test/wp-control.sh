#!/usr/bin/env bash
#
# wp-control.sh — one-stop control panel for the County Assistant WordPress demo.
#
# WHAT IT DOES
#   demo     ONE STEP: switch the retrieval pattern (and optionally the demo site)
#            AND start the WordPress app, then print the URL. Use this if you just
#            want to try the chatbot.
#   start    Bring up the local WordPress stack (Docker) and point the plugin at
#            the live Azure APIM endpoint (subscription key auto-fetched from Azure).
#   stop     Stop the WordPress stack (data is preserved).
#   destroy  Stop the stack AND delete its volumes (fresh DB next start).
#   pattern  Switch RETRIEVAL_PATTERN (and optionally DEMO_SITE_PROFILE) on the
#            Azure Function, restart it, and poll until the live routing is stable
#            (handles Flex Consumption lag).
#            NOTE: this ONLY changes Azure routing. It does NOT start the app.
#   status   Log every active Azure service used by the demo and its key config.
#   open     Print the site URL (and try to open it in a browser).
#   logs     Tail the WordPress container logs.
#   menu     Interactive menu (default when run with no arguments).
#
# REQUIREMENTS
#   - az CLI logged in to the subscription that holds the demo resources
#   - docker + docker compose
#   - run from anywhere; the script locates its own directory
#
# QUICK START (the easy way)
#   cd wordpress/local-test
#   ./wp-control.sh demo bing          # switch pattern AND start the app
#   ./wp-control.sh demo bing staging  # switch pattern + demo site, then start
#   # ...then open http://localhost:8083 and use the launcher bottom-right.
#
# QUICK START (individual steps)
#   ./wp-control.sh start                  # boots WP + wires APIM, prints the URL
#   ./wp-control.sh pattern hybrid         # switch pattern only (does NOT start app)
#   ./wp-control.sh pattern bing staging   # switch pattern + demo site
#   ./wp-control.sh status                 # log all active Azure services + configs
#   open http://localhost:8083
#
set -euo pipefail

# ----------------------------------------------------------------------------
# Configuration (override any of these via environment variables).
# ----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

SUBSCRIPTION_ID="${SUBSCRIPTION_ID:-b44206b5-80c5-499e-9da8-21f8fa79fb27}"
RESOURCE_GROUP="${RESOURCE_GROUP:-rg-county-sc}"
FUNCTION_APP="${FUNCTION_APP:-wpcounty-dev-func-mro5df}"
APIM_NAME="${APIM_NAME:-wpcounty-dev-apim-mro5df}"
APIM_SUBSCRIPTION="${APIM_SUBSCRIPTION:-county-assistant-wp}"
APIM_API_ID="${APIM_API_ID:-county-assistant}"
APIM_CHAT_URL="${APIM_CHAT_URL:-https://wpcounty-dev-apim-mro5df.azure-api.net/assistant/chat}"
FUNCTION_HOST="${FUNCTION_HOST:-wpcounty-dev-func-mro5df.azurewebsites.net}"
SITE_URL="${SITE_URL:-http://localhost:8083}"

# AOAI AI gateway: APIM fronts the Azure OpenAI model (token-limit, token-metrics,
# managed-identity backend auth). The Function routes chat + embeddings through
# this API by default. AOAI_API_ID is the imported Azure OpenAI inference API;
# AOAI_BACKEND_ID is its backend pointing at the Foundry .openai.azure.com endpoint.
AOAI_API_ID="${AOAI_API_ID:-aoai}"
AOAI_BACKEND_ID="${AOAI_BACKEND_ID:-aoai-backend}"

# Foundry / Search / Bing identifiers (used only for the status report).
FOUNDRY_NAME="${FOUNDRY_NAME:-wpcounty-dev-aifoundry-mro5df}"
SEARCH_NAME="${SEARCH_NAME:-wpcounty-dev-search-mro5df}"

VALID_PATTERNS="local azure_search bing hybrid"
VALID_SITES="westvale staging"

# ----------------------------------------------------------------------------
# Pretty output helpers.
# ----------------------------------------------------------------------------
if [[ -t 1 ]]; then
  BOLD=$'\033[1m'; DIM=$'\033[2m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'
  BLUE=$'\033[34m'; RED=$'\033[31m'; RESET=$'\033[0m'
else
  BOLD=""; DIM=""; GREEN=""; YELLOW=""; BLUE=""; RED=""; RESET=""
fi
say()  { printf '%s==>%s %s\n' "$BLUE$BOLD" "$RESET" "$*"; }
ok()   { printf '%s  ok%s %s\n' "$GREEN" "$RESET" "$*"; }
warn() { printf '%s  !!%s %s\n' "$YELLOW" "$RESET" "$*"; }
err()  { printf '%s ERR%s %s\n' "$RED" "$RESET" "$*" >&2; }
hr()   { printf '%s\n' "${DIM}----------------------------------------------------------------------${RESET}"; }

require() { command -v "$1" >/dev/null 2>&1 || { err "missing required command: $1"; exit 1; }; }

az_q() { az "$@" 2>/dev/null; }

dc() { ( cd "$SCRIPT_DIR" && docker compose "$@" ); }

# Fetch the APIM subscription key from Azure (never hard-coded / never echoed).
fetch_apim_key() {
  az rest --method post \
    --url "https://management.azure.com/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${RESOURCE_GROUP}/providers/Microsoft.ApiManagement/service/${APIM_NAME}/subscriptions/${APIM_SUBSCRIPTION}/listSecrets?api-version=2024-05-01" \
    --query "primaryKey" -o tsv 2>/dev/null
}

# ----------------------------------------------------------------------------
# Commands.
# ----------------------------------------------------------------------------
cmd_start() {
  require docker; require az
  say "Starting WordPress stack (docker compose up -d) ..."
  dc up -d
  ok "containers up"

  say "Fetching APIM subscription key from Azure ..."
  local key
  key="$(fetch_apim_key)"
  if [[ -z "$key" ]]; then
    err "could not fetch APIM key (is 'az' logged in to the right subscription?)"
    warn "stack is up but the plugin is NOT configured yet"
    return 1
  fi
  ok "key retrieved (length ${#key})"

  say "Configuring WordPress plugin -> ${APIM_CHAT_URL}"
  ( cd "$SCRIPT_DIR" && ./setup.sh "$APIM_CHAT_URL" "$key" >/dev/null )
  ok "plugin configured and pointed at APIM"

  hr
  ok "Demo ready: ${BOLD}${SITE_URL}${RESET}"
  printf '   admin: admin / admin-password\n'
  printf '   The County Assistant launcher appears bottom-right.\n'
  hr
}

cmd_stop() {
  require docker
  say "Stopping WordPress stack (data preserved) ..."
  dc down
  ok "stopped"
}

cmd_destroy() {
  require docker
  say "Stopping stack and deleting volumes (fresh DB next start) ..."
  dc down -v
  ok "destroyed"
}

cmd_open() {
  ok "Site URL: ${BOLD}${SITE_URL}${RESET}"
  if command -v xdg-open >/dev/null 2>&1; then xdg-open "$SITE_URL" >/dev/null 2>&1 || true
  elif command -v open >/dev/null 2>&1; then open "$SITE_URL" >/dev/null 2>&1 || true
  fi
}

cmd_logs() {
  require docker
  dc logs -f wordpress
}

# Switch RETRIEVAL_PATTERN (and optionally DEMO_SITE_PROFILE) on the Function,
# restart, and poll until stable.
cmd_pattern() {
  require az
  local pattern="${1:-}"
  local site="${2:-}"
  if [[ -z "$pattern" ]]; then
    err "usage: $0 pattern <${VALID_PATTERNS// /|}> [${VALID_SITES// /|}]"
    return 2
  fi
  if [[ " $VALID_PATTERNS " != *" $pattern "* ]]; then
    err "invalid pattern '$pattern' (valid: ${VALID_PATTERNS})"
    return 2
  fi
  if [[ -n "$site" && " $VALID_SITES " != *" $site "* ]]; then
    err "invalid site profile '$site' (valid: ${VALID_SITES})"
    return 2
  fi

  if [[ -n "$site" ]]; then
    say "Setting RETRIEVAL_PATTERN=${pattern} and DEMO_SITE_PROFILE=${site} on ${FUNCTION_APP} ..."
    az functionapp config appsettings set -g "$RESOURCE_GROUP" -n "$FUNCTION_APP" \
      --settings "RETRIEVAL_PATTERN=${pattern}" "DEMO_SITE_PROFILE=${site}" -o none
  else
    say "Setting RETRIEVAL_PATTERN=${pattern} on ${FUNCTION_APP} ..."
    az functionapp config appsettings set -g "$RESOURCE_GROUP" -n "$FUNCTION_APP" \
      --settings "RETRIEVAL_PATTERN=${pattern}" -o none
  fi
  ok "app setting(s) updated"

  say "Restarting the Function ..."
  az functionapp restart -g "$RESOURCE_GROUP" -n "$FUNCTION_APP"

  say "Waiting for health endpoint ..."
  local i code
  for i in $(seq 1 15); do
    code="$(curl -s -m 15 -o /dev/null -w "%{http_code}" "https://${FUNCTION_HOST}/api/health" || true)"
    if [[ "$code" == "200" ]]; then ok "health=200"; break; fi
    sleep 4
  done

  # Flex Consumption runs multiple instances that pick up the new setting at
  # different times, so the first several calls can show mixed modes. Poll the
  # live APIM endpoint until the observed mode is stable.
  local key
  key="$(fetch_apim_key)"
  if [[ -z "$key" ]]; then
    warn "could not fetch APIM key to verify routing; setting was applied though"
    return 0
  fi

  say "Polling live routing until stable (this can take a few calls) ..."
  local q='{"message":"When are my property taxes due?","session_id":"wpctl-pattern"}'
  local last="" stable=0 mode
  for i in $(seq 1 10); do
    mode="$(curl -s -m 90 -X POST "$APIM_CHAT_URL" \
      -H "Content-Type: application/json" \
      -H "Ocp-Apim-Subscription-Key: $key" \
      -d "$q" 2>/dev/null | python3 -c "import sys,json;print(json.load(sys.stdin).get('mode',''))" 2>/dev/null || true)"
    printf '   call %-2s -> %s\n' "$i" "${mode:-<no response>}"
    if [[ -n "$mode" && "$mode" == "$last" ]]; then
      stable=$((stable+1))
    else
      stable=0
    fi
    last="$mode"
    [[ $stable -ge 2 ]] && break
    sleep 2
  done
  hr
  ok "RETRIEVAL_PATTERN=${pattern}${site:+; DEMO_SITE_PROFILE=${site}}; stable live mode: ${BOLD}${last:-unknown}${RESET}"
  printf '   %slocal%s=offline KB | %sazure_search%s=ai-search-grounding | %sbing%s=bing-grounding | %shybrid%s=foundry RAG + bing fallback\n' \
    "$DIM" "$RESET" "$DIM" "$RESET" "$DIM" "$RESET" "$DIM" "$RESET"
}

# ONE STEP: switch the retrieval pattern (and optionally the demo site) AND start
# the WordPress app. This is the command most users want: it changes Azure routing
# and then brings the local WordPress demo up so you can actually use the chatbot.
cmd_demo() {
  require docker; require az
  local pattern="${1:-}"
  local site="${2:-}"
  if [[ -z "$pattern" ]]; then
    err "usage: $0 demo <${VALID_PATTERNS// /|}> [${VALID_SITES// /|}]"
    return 2
  fi
  if [[ " $VALID_PATTERNS " != *" $pattern "* ]]; then
    err "invalid pattern '$pattern' (valid: ${VALID_PATTERNS})"
    return 2
  fi
  if [[ -n "$site" && " $VALID_SITES " != *" $site "* ]]; then
    err "invalid site profile '$site' (valid: ${VALID_SITES})"
    return 2
  fi

  hr
  if [[ -n "$site" ]]; then
    say "STEP 1/2 — switch Azure routing to RETRIEVAL_PATTERN=${pattern}, DEMO_SITE_PROFILE=${site}"
  else
    say "STEP 1/2 — switch Azure routing to RETRIEVAL_PATTERN=${pattern}"
  fi
  hr
  cmd_pattern "$pattern" "$site"

  echo
  hr
  say "STEP 2/2 — start the WordPress app and wire it to APIM"
  hr
  cmd_start

  echo
  ok "All set. Open ${BOLD}${SITE_URL}${RESET} and use the launcher (bottom-right) to chat."
}

# Log every active Azure service used by the demo and its key configuration.
cmd_status() {
  require az
  hr
  printf '%sActive Azure services for the County Assistant demo%s\n' "$BOLD" "$RESET"
  printf '%ssubscription=%s  resource-group=%s%s\n' "$DIM" "$SUBSCRIPTION_ID" "$RESOURCE_GROUP" "$RESET"
  hr

  say "Local WordPress stack (docker)"
  if command -v docker >/dev/null 2>&1; then
    dc ps 2>/dev/null || warn "docker compose not running in $SCRIPT_DIR"
    local site_code
    site_code="$(curl -s -m 10 -o /dev/null -w "%{http_code}" "$SITE_URL" || true)"
    printf '   site %s -> HTTP %s\n' "$SITE_URL" "${site_code:-down}"
  else
    warn "docker not installed"
  fi
  echo

  say "Azure Function: ${FUNCTION_APP}"
  az_q functionapp show -g "$RESOURCE_GROUP" -n "$FUNCTION_APP" \
    --query "{name:name, state:properties.state, kind:kind, host:properties.defaultHostName, location:location}" -o jsonc || warn "lookup failed"
  printf '   health -> HTTP %s\n' \
    "$(curl -s -m 15 -o /dev/null -w "%{http_code}" "https://${FUNCTION_HOST}/api/health" || echo down)"
  printf '   %sretrieval / grounding settings:%s\n' "$DIM" "$RESET"
  az_q functionapp config appsettings list -g "$RESOURCE_GROUP" -n "$FUNCTION_APP" \
    --query "[?name=='RETRIEVAL_PATTERN' || name=='AZURE_SEARCH_USE_CUSTOM_RETRIEVER' || name=='RAG_VECTOR_ENABLED' || name=='HYBRID_MIN_SCORE' || name=='HYBRID_MIN_RESULTS' || name=='AZURE_SEARCH_AGENT_NAME' || name=='AZURE_SEARCH_CONNECTION_NAME' || name=='AZURE_SEARCH_QUERY_TYPE' || name=='BING_GROUNDING_ENABLED' || name=='BING_CONNECTION_NAME' || name=='BING_GROUNDING_AGENT_NAME' || name=='FOUNDRY_ENABLED' || name=='AZURE_AI_MODEL_DEPLOYMENT'].{name:name,value:value}" \
    -o table || warn "settings lookup failed"
  echo

  say "API Management: ${APIM_NAME}"
  az_q apim show -g "$RESOURCE_GROUP" -n "$APIM_NAME" \
    --query "{sku:sku.name, state:provisioningState, gateway:properties.gatewayUrl}" -o jsonc || warn "lookup failed"
  printf '   %sAPI:%s\n' "$DIM" "$RESET"
  az_q apim api show -g "$RESOURCE_GROUP" --service-name "$APIM_NAME" --api-id "$APIM_API_ID" \
    --query "{name:name, path:path, subscriptionRequired:subscriptionRequired, serviceUrl:serviceUrl}" -o jsonc || true
  printf '   %sbackend(s):%s\n' "$DIM" "$RESET"
  az_q rest --method get \
    --url "https://management.azure.com/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${RESOURCE_GROUP}/providers/Microsoft.ApiManagement/service/${APIM_NAME}/backends?api-version=2024-05-01" \
    --query "value[].{name:name,url:properties.url}" -o jsonc || true
  printf '   %sactive policy elements on POST /chat:%s\n' "$DIM" "$RESET"
  az_q rest --method get \
    --url "https://management.azure.com/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${RESOURCE_GROUP}/providers/Microsoft.ApiManagement/service/${APIM_NAME}/apis/${APIM_API_ID}/operations/chat/policies/policy?api-version=2024-05-01&format=rawxml" \
    -o tsv \
    | grep -oiE "<(cors|rate-limit-by-key|set-backend-service|rewrite-uri|forward-request|set-header)\b" \
    | sed 's/[<>]//g' | sort | uniq -c | awk '{printf "     %s x%s\n",$2,$1}' \
    || warn "no operation policy found"
  echo

  say "AOAI AI gateway (APIM fronts the Azure OpenAI model)"
  printf '   %sgoverned model API:%s\n' "$DIM" "$RESET"
  az_q apim api show -g "$RESOURCE_GROUP" --service-name "$APIM_NAME" --api-id "$AOAI_API_ID" \
    --query "{name:name, path:path, subscriptionRequired:subscriptionRequired}" -o jsonc \
    || warn "AOAI API '${AOAI_API_ID}' not found (gateway not provisioned)"
  printf '   %smodel backend:%s\n' "$DIM" "$RESET"
  az_q rest --method get \
    --url "https://management.azure.com/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${RESOURCE_GROUP}/providers/Microsoft.ApiManagement/service/${APIM_NAME}/backends/${AOAI_BACKEND_ID}?api-version=2024-05-01" \
    --query "{name:name,url:properties.url}" -o jsonc \
    || warn "backend '${AOAI_BACKEND_ID}' not found"
  printf '   %sgovernance policy elements on the AOAI API:%s\n' "$DIM" "$RESET"
  az_q rest --method get \
    --url "https://management.azure.com/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${RESOURCE_GROUP}/providers/Microsoft.ApiManagement/service/${APIM_NAME}/apis/${AOAI_API_ID}/policies/policy?api-version=2024-05-01&format=rawxml" \
    -o tsv \
    | grep -oiE "<(authentication-managed-identity|azure-openai-token-limit|azure-openai-emit-token-metric|azure-openai-semantic-cache-lookup|azure-openai-semantic-cache-store|set-backend-service)\b" \
    | sed 's/[<>]//g' | sort | uniq -c | awk '{printf "     %s x%s\n",$2,$1}' \
    || warn "no AOAI policy found"
  printf '   %sFunction routing (AZURE_OPENAI_GATEWAY_*):%s\n' "$DIM" "$RESET"
  local gw_ep gw_key_set
  gw_ep="$(az_q functionapp config appsettings list -g "$RESOURCE_GROUP" -n "$FUNCTION_APP" --query "[?name=='AZURE_OPENAI_GATEWAY_ENDPOINT'].value | [0]" -o tsv)"
  gw_key_set="$(az_q functionapp config appsettings list -g "$RESOURCE_GROUP" -n "$FUNCTION_APP" --query "[?name=='AZURE_OPENAI_GATEWAY_KEY'].value | [0]" -o tsv)"
  if [[ -n "$gw_ep" && -n "$gw_key_set" ]]; then
    ok "model calls route through APIM AOAI gateway -> ${gw_ep}/openai"
  else
    warn "gateway settings not fully set; Function would call Foundry directly"
  fi
  echo

  say "AI Foundry: ${FOUNDRY_NAME}  /  Azure AI Search: ${SEARCH_NAME}"
  az_q search service show -g "$RESOURCE_GROUP" -n "$SEARCH_NAME" \
    --query "{sku:sku.name, status:status, replicas:replicaCount, partitions:partitionCount}" -o jsonc || warn "search lookup failed"
  printf '   %sFoundry project endpoint:%s %s\n' "$DIM" "$RESET" \
    "$(az_q functionapp config appsettings list -g "$RESOURCE_GROUP" -n "$FUNCTION_APP" --query "[?name=='AZURE_AI_PROJECT_ENDPOINT'].value | [0]" -o tsv)"
  printf '   %sSearch endpoint / index:%s %s / %s\n' "$DIM" "$RESET" \
    "$(az_q functionapp config appsettings list -g "$RESOURCE_GROUP" -n "$FUNCTION_APP" --query "[?name=='AZURE_SEARCH_ENDPOINT'].value | [0]" -o tsv)" \
    "$(az_q functionapp config appsettings list -g "$RESOURCE_GROUP" -n "$FUNCTION_APP" --query "[?name=='AZURE_SEARCH_INDEX'].value | [0]" -o tsv)"
  hr
  ok "status report complete"
}

cmd_menu() {
  while true; do
    echo
    printf '%sCounty Assistant — WordPress demo control%s\n' "$BOLD" "$RESET"
    printf '  1) demo         switch pattern (+ optional site) AND start the app\n'
    printf '  2) start        bring up WordPress + wire APIM\n'
    printf '  3) pattern      switch RETRIEVAL_PATTERN (+ optional site); no app start\n'
    printf '  4) status       log active Azure services + configs\n'
    printf '  5) open         print/open the site URL\n'
    printf '  6) logs         tail WordPress logs\n'
    printf '  7) stop         stop the stack (keep data)\n'
    printf '  8) destroy      stop + delete volumes\n'
    printf '  q) quit\n'
    read -r -p "select> " choice
    case "$choice" in
      1)
        read -r -p "pattern (${VALID_PATTERNS// /|}) > " p
        read -r -p "site profile (${VALID_SITES// /|}) [optional, Enter to skip] > " s
        cmd_demo "$p" "$s" ;;
      2) cmd_start ;;
      3)
        read -r -p "pattern (${VALID_PATTERNS// /|}) > " p
        read -r -p "site profile (${VALID_SITES// /|}) [optional, Enter to skip] > " s
        cmd_pattern "$p" "$s" ;;
      4) cmd_status ;;
      5) cmd_open ;;
      6) cmd_logs ;;
      7) cmd_stop ;;
      8) cmd_destroy ;;
      q|Q) break ;;
      *) warn "unknown choice: $choice" ;;
    esac
  done
}

usage() {
  sed -n '2,40p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

main() {
  local cmd="${1:-menu}"
  shift || true
  case "$cmd" in
    demo)    cmd_demo "$@" ;;
    start)   cmd_start "$@" ;;
    stop)    cmd_stop "$@" ;;
    destroy) cmd_destroy "$@" ;;
    pattern) cmd_pattern "$@" ;;
    status)  cmd_status "$@" ;;
    open)    cmd_open "$@" ;;
    logs)    cmd_logs "$@" ;;
    menu)    cmd_menu ;;
    -h|--help|help) usage ;;
    *) err "unknown command: $cmd"; usage; exit 2 ;;
  esac
}

main "$@"
