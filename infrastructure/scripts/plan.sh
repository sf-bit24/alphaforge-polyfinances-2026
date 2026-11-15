#!/bin/sh
set -e

if [ -z "${WORKSPACE_ID:-}" ] || [ -z "${CONFIG_VERSION_ID:-}" ]; then
  echo "ERROR: WORKSPACE_ID ou CONFIG_VERSION_ID absent."
  exit 1
fi

SHORT_SHA=$(printf '%.8s' "${GITHUB_SHA:-local}")

# Cree un run plan-only sur la configuration uploadee
RUN_PAYLOAD=$(cat <<PAYLOAD
{
  "data": {
    "type": "runs",
    "attributes": {
      "is-destroy": false,
      "message": "GitHub Actions plan - ${UPSTREAM_COMMIT_SHA:-${SHORT_SHA}} (${DEPLOY_ENV})",
      "plan-only": true
    },
    "relationships": {
      "workspace":             { "data": { "type": "workspaces",             "id": "$WORKSPACE_ID" } },
      "configuration-version": { "data": { "type": "configuration-versions", "id": "$CONFIG_VERSION_ID" } }
    }
  }
}
PAYLOAD
)

RUN_RESPONSE=$(curl -s --fail \
  --header "Authorization: Bearer $TF_API_TOKEN" \
  --header "Content-Type: application/vnd.api+json" \
  --request POST \
  --data "$RUN_PAYLOAD" \
  "https://${TF_CLOUD_HOSTNAME}/api/v2/runs")

RUN_ID=$(echo "$RUN_RESPONSE" | jq -r '.data.id')

if [ -z "$RUN_ID" ] || [ "$RUN_ID" = "null" ]; then
  echo "ERROR: impossible de creer le run"
  echo "$RUN_RESPONSE"
  exit 1
fi
echo "Run cree : $RUN_ID"

# Affiche le resume du plan et chaque ressource touchee (action + adresse), pour
# qu'une destruction ou un remplacement se voie dans la PR avant le merge.
print_plan_changes() {
  PLAN_ID=$(echo "$1" | jq -r '.data.relationships.plan.data.id')
  [ -n "$PLAN_ID" ] && [ "$PLAN_ID" != "null" ] || return 0
  PLAN_DATA=$(curl -s \
    --header "Authorization: Bearer $TF_API_TOKEN" \
    "https://${TF_CLOUD_HOSTNAME}/api/v2/plans/${PLAN_ID}")
  echo "$PLAN_DATA" | jq -r '.data.attributes
    | "Plan : \(."resource-additions") a ajouter, \(."resource-changes") a modifier, \(."resource-destructions") a detruire, \(."resource-imports" // 0) a importer"'
  LOG_URL=$(echo "$PLAN_DATA" | jq -r '.data.attributes."log-read-url"')
  [ -n "$LOG_URL" ] && [ "$LOG_URL" != "null" ] || return 0
  curl -s -L "$LOG_URL" | grep '^{' \
    | jq -r 'select(.type == "planned_change") | "  \(.change.action)\t\(.change.resource.addr)"' || true
}

# Polling jusqu'a 10 min
for i in $(seq 1 60); do
  STATUS_DATA=$(curl -s --fail \
    --header "Authorization: Bearer $TF_API_TOKEN" \
    "https://${TF_CLOUD_HOSTNAME}/api/v2/runs/${RUN_ID}")

  STATUS=$(echo "$STATUS_DATA" | jq -r '.data.attributes.status')
  echo "  $i/60 - $STATUS"

  case "$STATUS" in
    planned|cost_estimated|policy_checked|planned_and_finished)
      echo "Plan OK"
      print_plan_changes "$STATUS_DATA"
      break
      ;;
    errored|canceled)
      echo "ERROR: plan en echec ($STATUS)"
      PLAN_ID=$(echo "$STATUS_DATA" | jq -r '.data.relationships.plan.data.id')
      if [ -n "$PLAN_ID" ] && [ "$PLAN_ID" != "null" ]; then
        LOG_URL=$(curl -s \
          --header "Authorization: Bearer $TF_API_TOKEN" \
          "https://${TF_CLOUD_HOSTNAME}/api/v2/plans/${PLAN_ID}" \
          | jq -r '.data.attributes."log-read-url"')
        if [ -n "$LOG_URL" ] && [ "$LOG_URL" != "null" ]; then
          echo "--- log ---"
          curl -s -L "$LOG_URL" | head -n 200
        fi
      fi
      exit 1
      ;;
  esac

  sleep 10
done

echo "RUN_ID=$RUN_ID" > run.env
if [ -n "${GITHUB_OUTPUT:-}" ]; then
  cat run.env >> "$GITHUB_OUTPUT"
fi
