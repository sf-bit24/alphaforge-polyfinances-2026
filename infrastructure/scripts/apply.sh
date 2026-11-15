#!/bin/sh
set -e

if [ -z "${RUN_ID:-}" ]; then
  echo "ERROR: RUN_ID absent."
  exit 1
fi

# Statut courant
STATUS_DATA=$(curl -s --fail \
  --header "Authorization: Bearer $TF_API_TOKEN" \
  "https://${TF_CLOUD_HOSTNAME}/api/v2/runs/${RUN_ID}")
STATUS=$(echo "$STATUS_DATA" | jq -r '.data.attributes.status')
echo "Statut courant : $STATUS"

if [ "$STATUS" = "applied" ]; then
  echo "Deja applique."
  exit 0
fi

# Si plan-only, on declenche un nouveau run en auto-apply
if [ "$STATUS" = "planned_and_finished" ]; then
  echo "Run plan-only detecte : creation d'un run apply auto-apply..."
  CONFIG_VERSION_ID=$(echo "$STATUS_DATA" | jq -r '.data.relationships."configuration-version".data.id')
  WORKSPACE_ID=$(echo "$STATUS_DATA" | jq -r '.data.relationships.workspace.data.id')

  RUN_PAYLOAD=$(cat <<'PAYLOAD'
{
  "data": {
    "type": "runs",
    "attributes": {
      "is-destroy": false,
      "message": "GitHub Actions apply",
      "auto-apply": true
    },
    "relationships": {
      "workspace":             { "data": { "type": "workspaces",             "id": "WORKSPACE_ID_PLACEHOLDER" } },
      "configuration-version": { "data": { "type": "configuration-versions", "id": "CONFIG_VERSION_ID_PLACEHOLDER" } }
    }
  }
}
PAYLOAD
)
  RUN_PAYLOAD=$(echo "$RUN_PAYLOAD" | sed "s/WORKSPACE_ID_PLACEHOLDER/$WORKSPACE_ID/g" | sed "s/CONFIG_VERSION_ID_PLACEHOLDER/$CONFIG_VERSION_ID/g")

  RUN_RESPONSE=$(curl -s --fail \
    --header "Authorization: Bearer $TF_API_TOKEN" \
    --header "Content-Type: application/vnd.api+json" \
    --request POST \
    --data "$RUN_PAYLOAD" \
    "https://${TF_CLOUD_HOSTNAME}/api/v2/runs")
  RUN_ID=$(echo "$RUN_RESPONSE" | jq -r '.data.id')
  echo "Nouveau run : $RUN_ID"
else
  curl -s --fail \
    --header "Authorization: Bearer $TF_API_TOKEN" \
    --header "Content-Type: application/vnd.api+json" \
    --request POST \
    --data '{"comment":"Applied via GitHub Actions"}' \
    "https://${TF_CLOUD_HOSTNAME}/api/v2/runs/${RUN_ID}/actions/apply"
fi

# Polling apply jusqu'a 20 min
for i in $(seq 1 120); do
  STATUS_DATA=$(curl -s --fail \
    --header "Authorization: Bearer $TF_API_TOKEN" \
    "https://${TF_CLOUD_HOSTNAME}/api/v2/runs/${RUN_ID}")
  STATUS=$(echo "$STATUS_DATA" | jq -r '.data.attributes.status')
  echo "  $i/120 - $STATUS"

  case "$STATUS" in
    applied)
      echo "Apply OK"
      exit 0
      ;;
    errored|canceled)
      echo "ERROR: apply en echec ($STATUS)"
      RUN_DETAIL=$(curl -s \
        --header "Authorization: Bearer $TF_API_TOKEN" \
        --header "Content-Type: application/vnd.api+json" \
        "https://${TF_CLOUD_HOSTNAME}/api/v2/runs/${RUN_ID}?include=plan,apply")
      PLAN_LOG_URL=$(echo "$RUN_DETAIL" | jq -r '[.included[] | select(.type == "plans")][0].attributes."log-read-url" // empty')
      APPLY_LOG_URL=$(echo "$RUN_DETAIL" | jq -r '[.included[] | select(.type == "applies")][0].attributes."log-read-url" // empty')
      [ -n "$PLAN_LOG_URL" ]  && { echo "--- plan log ---";  curl -s "$PLAN_LOG_URL"  || true; }
      [ -n "$APPLY_LOG_URL" ] && { echo "--- apply log ---"; curl -s "$APPLY_LOG_URL" || true; }
      exit 1
      ;;
  esac
  sleep 10
done

echo "ERROR: apply timeout"
exit 1
