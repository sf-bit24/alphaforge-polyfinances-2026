#!/bin/sh
set -e

# =============================================================================
# Destroy d'un environnement ephemere.
#
# Usage : init.sh doit avoir ete sourcee avant (TF_WORKSPACE positionne).
#   . scripts/init.sh "$DEPLOY_ENV"
#   sh scripts/destroy.sh
#
# Comportement :
#   1. Si workspace inexistant -> rien a faire, succes.
#   2. Trigger un run is-destroy=true auto-apply=true via TFC API.
#   3. Poll le run jusqu'a status=applied (timeout 20 min).
#   4. DELETE le workspace via TFC API.
#
# Securite : ce script REFUSE de tourner sur sandbox/nprod/prod (envs
# canoniques) — uniquement sur feat-*. Le cleanup des envs persistants
# se fait manuellement via la UI TFC.
# =============================================================================

if [ -z "$DEPLOY_ENV" ] || [ -z "$TF_WORKSPACE" ]; then
  echo "ERROR: DEPLOY_ENV ou TF_WORKSPACE absent. As-tu source init.sh ?"
  exit 1
fi

case "$DEPLOY_ENV" in
  sandbox|nprod|prod)
    echo "ERROR: destroy bloque sur env persistant '$DEPLOY_ENV'. Cleanup manuel via TFC UI."
    exit 1
    ;;
  feat-*) ;;
  *)
    echo "ERROR: env '$DEPLOY_ENV' n'est ni persistant ni un slug feat-*. Refuse."
    exit 1
    ;;
esac

: "${TF_CLOUD_HOSTNAME:=app.terraform.io}"
: "${TF_CLOUD_ORGANIZATION:=larpathon_2026}"

if [ -z "$TF_API_TOKEN" ]; then
  echo "ERROR: TF_API_TOKEN absent."
  exit 1
fi

# Lookup workspace ID. Si 404, c'est que le workspace a deja ete supprime
# par un cleanup precedent -> succes idempotent.
WS_HTTP_CODE=$(curl -s -o /tmp/destroy_ws.json -w "%{http_code}" \
  --header "Authorization: Bearer $TF_API_TOKEN" \
  "https://${TF_CLOUD_HOSTNAME}/api/v2/organizations/${TF_CLOUD_ORGANIZATION}/workspaces/${TF_WORKSPACE}")

if [ "$WS_HTTP_CODE" = "404" ]; then
  echo "[destroy] workspace $TF_WORKSPACE deja inexistant — rien a faire."
  exit 0
fi
if [ "$WS_HTTP_CODE" != "200" ]; then
  echo "ERROR: lookup workspace HTTP $WS_HTTP_CODE"
  cat /tmp/destroy_ws.json
  exit 1
fi

WS_ID=$(jq -r '.data.id' < /tmp/destroy_ws.json)
echo "[destroy] workspace $TF_WORKSPACE (id=$WS_ID)"

# Trigger un run destroy + auto-apply.
RUN_PAYLOAD=$(cat <<EOF
{"data":{
  "type":"runs",
  "attributes":{
    "is-destroy": true,
    "auto-apply": true,
    "message": "Branche feature supprimee/mergee — cleanup ephemere"
  },
  "relationships":{
    "workspace":{"data":{"type":"workspaces","id":"${WS_ID}"}}
  }
}}
EOF
)

RUN_RESPONSE=$(curl -s --fail \
  --header "Authorization: Bearer $TF_API_TOKEN" \
  --header "Content-Type: application/vnd.api+json" \
  --request POST \
  --data "$RUN_PAYLOAD" \
  "https://${TF_CLOUD_HOSTNAME}/api/v2/runs")

RUN_ID=$(echo "$RUN_RESPONSE" | jq -r '.data.id')
if [ -z "$RUN_ID" ] || [ "$RUN_ID" = "null" ]; then
  echo "ERROR: impossible de creer le run destroy"
  echo "$RUN_RESPONSE"
  exit 1
fi
echo "[destroy] run destroy cree : $RUN_ID"

# Poll jusqu'a applied (ou erreur).
for i in $(seq 1 120); do
  STATUS_DATA=$(curl -s --fail \
    --header "Authorization: Bearer $TF_API_TOKEN" \
    "https://${TF_CLOUD_HOSTNAME}/api/v2/runs/${RUN_ID}")
  STATUS=$(echo "$STATUS_DATA" | jq -r '.data.attributes.status')
  echo "  $i/120 - $STATUS"

  case "$STATUS" in
    applied)
      echo "[destroy] destroy OK"
      break
      ;;
    errored|canceled|discarded|policy_soft_failed)
      echo "ERROR: destroy en echec ($STATUS)"
      RUN_DETAIL=$(curl -s \
        --header "Authorization: Bearer $TF_API_TOKEN" \
        --header "Content-Type: application/vnd.api+json" \
        "https://${TF_CLOUD_HOSTNAME}/api/v2/runs/${RUN_ID}?include=plan,apply")
      PLAN_LOG_URL=$(echo "$RUN_DETAIL" | jq -r '[.included[]? | select(.type == "plans")][0].attributes."log-read-url" // empty')
      APPLY_LOG_URL=$(echo "$RUN_DETAIL" | jq -r '[.included[]? | select(.type == "applies")][0].attributes."log-read-url" // empty')
      [ -n "$PLAN_LOG_URL" ]  && { echo "--- plan log ---";  curl -s "$PLAN_LOG_URL"  || true; }
      [ -n "$APPLY_LOG_URL" ] && { echo "--- apply log ---"; curl -s "$APPLY_LOG_URL" || true; }
      exit 1
      ;;
    planned_and_finished)
      echo "[destroy] aucune ressource a detruire — workspace deja vide"
      break
      ;;
  esac

  if [ "$i" = "120" ]; then
    echo "ERROR: destroy timeout (20 min)"
    exit 1
  fi
  sleep 10
done

# Supprime le workspace lui-meme.
echo "[destroy] suppression du workspace $TF_WORKSPACE..."
DELETE_HTTP=$(curl -s -o /dev/null -w "%{http_code}" \
  --header "Authorization: Bearer $TF_API_TOKEN" \
  --request DELETE \
  "https://${TF_CLOUD_HOSTNAME}/api/v2/organizations/${TF_CLOUD_ORGANIZATION}/workspaces/${TF_WORKSPACE}")

case "$DELETE_HTTP" in
  200|204) echo "[destroy] workspace supprime" ;;
  404)     echo "[destroy] workspace deja supprime (idempotent)" ;;
  *)
    echo "ERROR: suppression workspace HTTP $DELETE_HTTP"
    exit 1
    ;;
esac

# Nettoie le tfvars ephemere genere (si present) — pas critique mais propre.
if [ -f "deploy/envs/${DEPLOY_ENV}.tfvars" ]; then
  case "$DEPLOY_ENV" in
    feat-*) rm -f "deploy/envs/${DEPLOY_ENV}.tfvars" ;;
  esac
fi

echo "[destroy] cleanup complet pour $DEPLOY_ENV"
