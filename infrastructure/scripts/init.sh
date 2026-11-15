#!/bin/sh
# =============================================================================
# Charge l'environnement de deploiement.
#
# Usage (sourcer, pas executer) :
#   . scripts/init.sh <sandbox|nprod|prod|feat-XXX>
#   . scripts/init.sh "$DEPLOY_ENV"
#   . scripts/init.sh              # en CI : env deduit du run GitHub Actions
#
# Effets :
#   - normalise/tronque le slug (max 19 char total — contrainte ALB name)
#   - pour un slug feat-*, genere deploy/envs/feat-XXX.tfvars a partir de sandbox.tfvars
#   - cree le workspace TFC de l'env si absent
#     (tag alphaforge)
#   - tente d'attacher la Variable Set "Default provider instance" au nouveau
#     workspace (best-effort — si pas de permissions, on continue et on
#     compte sur TFC_AWS_PROVIDER_AUTH + workspace var TFC_AWS_RUN_ROLE_ARN
#     poussees par upload-config.sh)
#   - exporte DEPLOY_ENV et TF_WORKSPACE
#
# Pre-requis (variables d'env attendues) :
#   - TF_API_TOKEN          : token TFC avec droits create workspaces
#   - TF_CLOUD_HOSTNAME     : app.terraform.io
#   - TF_CLOUD_ORGANIZATION : larpathon_2026
# =============================================================================

# Slug de branche facon GitLab CI_COMMIT_REF_SLUG : minuscules, tout ce qui
# n'est pas [a-z0-9] devient '-', 63 caracteres max, pas de '-' aux bords.
# feature/Mon_Truc -> feature-mon-truc
_ref_slug() {
  printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g' | cut -c1-63 | sed 's/^-*//; s/-*$//'
}

# Variables GitHub Actions predefinies -> equivalents neutres.
#   GITHUB_EVENT_NAME : push | pull_request | workflow_dispatch ...
#   GITHUB_REF_NAME   : nom de branche sur un push (N/merge sur une PR)
#   GITHUB_REPOSITORY : <owner>/<repo>
CI_EVENT="${GITHUB_EVENT_NAME:-}"
CI_BRANCH="${GITHUB_REF_NAME:-}"
CI_BRANCH_SLUG=$(_ref_slug "$CI_BRANCH")

# Env explicite en argument, sinon deduit du run : push feature/* ->
# feat-<slug>, tout le reste (branche par defaut, PR, local) -> DEPLOY_ENV.
# Note : dash ne transmet pas les arguments de `. script arg` ; hors bash/ash,
# passer l'env par DEPLOY_ENV=<env>.
TARGET_ENV="${1:-}"
if [ -z "$TARGET_ENV" ]; then
  case "${CI_EVENT}:${CI_BRANCH}" in
    push:feature/*) TARGET_ENV="feat-${CI_BRANCH_SLUG#feature-}" ;;
    *) TARGET_ENV="${DEPLOY_ENV:-}" ;;
  esac
fi

if [ -z "$TARGET_ENV" ]; then
  echo "ERROR: env manquant. Usage: . scripts/init.sh <sandbox|nprod|prod|feat-XXX>"
  return 1 2>/dev/null || exit 1
fi

ephemeral_envs_enabled() {
  case "${EPHEMERAL_ENVS_ENABLED:-true}" in
    false|FALSE|False|0|no|NO|No|off|OFF|Off) return 1 ;;
    *) return 0 ;;
  esac
}

# Normalisation : tronquer a 19 char (contrainte ALB name = 32 chars,
# prefix alphaforge- (9) + env + -alb (4) = 13 + env <= 32 -> env <= 19).
TARGET_ENV_RAW="$TARGET_ENV"
TARGET_ENV=$(printf '%s' "$TARGET_ENV" | cut -c1-19 | sed 's/-*$//')
if [ "$TARGET_ENV" != "$TARGET_ENV_RAW" ]; then
  echo "[init] env tronque : '$TARGET_ENV_RAW' -> '$TARGET_ENV' (limite ALB 19 char)"
fi

# Validation : envs canoniques OU slug feat-<alnum-tirets>
case "$TARGET_ENV" in
  sandbox|nprod|prod)
    EPHEMERAL=false
    ;;
  feat-*)
    EPHEMERAL=true
    # Verifier que le suffixe apres feat- est valide (alnum + tirets)
    SUFFIX="${TARGET_ENV#feat-}"
    case "$SUFFIX" in
      ''|*[!a-z0-9-]*)
        echo "ERROR: slug ephemere invalide '$TARGET_ENV' — apres feat-, attendre lettres/chiffres/tirets minuscules uniquement."
        return 1 2>/dev/null || exit 1
        ;;
    esac
    ;;
  *)
    echo "ERROR: env invalide '$TARGET_ENV'. Valides : sandbox, nprod, prod, ou feat-<slug>."
    return 1 2>/dev/null || exit 1
    ;;
esac

if [ "$EPHEMERAL" = "true" ] && [ "$DESTROY_ENV" != "true" ] && ! ephemeral_envs_enabled; then
  echo "ERROR: environnements ephemeres desactives (EPHEMERAL_ENVS_ENABLED=${EPHEMERAL_ENVS_ENABLED:-true}); initialisation refusee pour '$TARGET_ENV'."
  return 1 2>/dev/null || exit 1
fi

TFVARS_DIR="deploy/envs"

# Pour un env ephemere, generer deploy/envs/<env>.tfvars a partir de sandbox.tfvars
# (memes VPC/subnets/cert, juste environment override).
TFVARS_FILE="${TFVARS_DIR}/${TARGET_ENV}.tfvars"
if [ ! -f "$TFVARS_FILE" ]; then
  if [ "$EPHEMERAL" = "true" ] && [ -f "${TFVARS_DIR}/sandbox.tfvars" ]; then
    echo "[init] generation tfvars ephemere : $TFVARS_FILE (base = ${TFVARS_DIR}/sandbox.tfvars)"
    # Remplace environment = "sandbox" par environment = "<slug>"
    # tr -d '\r' au cas ou le fichier source ait des CRLF Windows.
    tr -d '\r' < "${TFVARS_DIR}/sandbox.tfvars" \
      | sed "s/^\(environment[[:space:]]*=[[:space:]]*\).*/\1\"${TARGET_ENV}\"/" \
      > "$TFVARS_FILE"
  else
    echo "ERROR: fichier '$TFVARS_FILE' introuvable."
    return 1 2>/dev/null || exit 1
  fi
fi

echo "[init] env=$TARGET_ENV ephemeral=$EPHEMERAL tfvars=$TFVARS_FILE"

# Repo et branche qui nomment les workspaces feat-* : variables GitHub.
# Le nom de repo est slugifie (TFC n'accepte que lettres, chiffres, - et _).
if [ -n "${GITHUB_REPOSITORY:-}" ]; then
  : "${UPSTREAM_PROJECT_NAME:=$(_ref_slug "${GITHUB_REPOSITORY#*/}")}"
fi
: "${UPSTREAM_PROJECT_NAME:=}"
: "${UPSTREAM_BRANCH_SLUG:=${CI_BRANCH_SLUG}}"

# Nom du workspace TFC.
# - Workspace de la branche par defaut : le generateur remplace l'env principal
#   par le nom exact fourni, sans suffixe.
# - Workspaces feat-* : noms dynamiques pour les runs API-driven.
# - Branches feature (feat-*) : <upstream-project>-<branch-slug-sans-prefixe>
#   pour eviter les collisions causees par le truncate 19-char de TARGET_ENV
#   (necessaire pour var.environment / ALB name). Sans ce nommage long, deux
#   branches feature/<X> et feature/<Y> qui partagent les 13 premiers char
#   apres "feat-feature-" finiraient sur le meme workspace poc-feat-feature-X.
#   Les vars UPSTREAM_PROJECT_NAME / UPSTREAM_BRANCH_SLUG viennent de
#   GITHUB_REPOSITORY / GITHUB_REF_NAME ; hors CI, on retombe sur la legacy
#   poc-<TARGET_ENV>.
case "$TARGET_ENV" in
  sandbox)
    TF_WORKSPACE_NAME="larpathon"
    ;;
  nprod)
    TF_WORKSPACE_NAME="larpathon-nprod"
    ;;
  prod)
    TF_WORKSPACE_NAME="larpathon-prod"
    ;;
  feat-*)
    if [ -n "$UPSTREAM_PROJECT_NAME" ] && [ -n "$UPSTREAM_BRANCH_SLUG" ]; then
      # Strip un eventuel prefixe "feature-" en debut de slug (redondant avec
      # le "feature/" deja implicite). "main" / autres slugs non-feature sont
      # laisses intacts.
      _SLUG_TRIMMED="${UPSTREAM_BRANCH_SLUG#feature-}"
      TF_WORKSPACE_NAME="${UPSTREAM_PROJECT_NAME}-${_SLUG_TRIMMED}"
    else
      TF_WORKSPACE_NAME="larpathon-${TARGET_ENV}"
    fi
    ;;
  *)
    TF_WORKSPACE_NAME="larpathon-${TARGET_ENV}"
    ;;
esac
echo "[init] TF_WORKSPACE_NAME=$TF_WORKSPACE_NAME"

# Si le workspace est absent, le creer.
# En mode destroy, ne pas creer un workspace absent juste pour le detruire.
if [ "$DESTROY_ENV" != "true" ]; then
  : "${TF_CLOUD_HOSTNAME:=app.terraform.io}"
  : "${TF_CLOUD_ORGANIZATION:=larpathon_2026}"

  if [ -z "$TF_API_TOKEN" ]; then
    echo "ERROR: TF_API_TOKEN absent — impossible de creer/verifier le workspace TFC."
    return 1 2>/dev/null || exit 1
  fi

  WS_HTTP_CODE=$(curl -s -o /tmp/ws_check.json -w "%{http_code}" \
    --header "Authorization: Bearer $TF_API_TOKEN" \
    "https://${TF_CLOUD_HOSTNAME}/api/v2/organizations/${TF_CLOUD_ORGANIZATION}/workspaces/${TF_WORKSPACE_NAME}")

  if [ "$WS_HTTP_CODE" = "404" ]; then
    echo "[init] creation du workspace TFC : $TF_WORKSPACE_NAME"

    # Lookup du Project TFC. Priorite :
    # 1. TFC_PROJECT_ID passe comme variable/secret de repo GitHub (override explicite)
    # 2. Lookup depuis un workspace canonique existant (premier qui repond)
    # TFC exige un project lors de la creation si l'org en a ; sans lui -> 422.
    PROJECT_ID=""
    if [ -n "$TFC_PROJECT_ID" ]; then
      PROJECT_ID="$TFC_PROJECT_ID"
      echo "[init] project TFC (depuis TFC_PROJECT_ID) : $PROJECT_ID"
    else
      for _REF_WS in larpathon-nprod larpathon-prod larpathon; do
        _REF_DATA=$(curl -s --header "Authorization: Bearer $TF_API_TOKEN" \
          "https://${TF_CLOUD_HOSTNAME}/api/v2/organizations/${TF_CLOUD_ORGANIZATION}/workspaces/${_REF_WS}")
        PROJECT_ID=$(echo "$_REF_DATA" | jq -r '.data.relationships.project.data.id // empty')
        if [ -n "$PROJECT_ID" ]; then
          echo "[init] project TFC reference (depuis ${_REF_WS}) : $PROJECT_ID"
          break
        fi
      done
    fi
    if [ -n "$PROJECT_ID" ]; then
      PROJECT_RELATIONSHIP=", \"relationships\": {\"project\": {\"data\": {\"type\": \"projects\", \"id\": \"$PROJECT_ID\"}}}"
    else
      echo "ERROR: impossible de resoudre le project TFC (larpathon-nprod/larpathon-prod/larpathon introuvables, TFC_PROJECT_ID absent). Definir TFC_PROJECT_ID comme variable de repo GitHub."
      return 1 2>/dev/null || exit 1
    fi

    CREATE_PAYLOAD=$(cat <<EOF
{"data":{
  "type":"workspaces",
  "attributes":{
    "name": "${TF_WORKSPACE_NAME}",
    "tag-names": ["alphaforge"],
    "execution-mode": "remote",
    "working-directory": "infra",
    "auto-apply": true
  }
  ${PROJECT_RELATIONSHIP}
}}
EOF
)

    CREATE_RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" \
      --header "Authorization: Bearer $TF_API_TOKEN" \
      --header "Content-Type: application/vnd.api+json" \
      --request POST \
      --data "$CREATE_PAYLOAD" \
      "https://${TF_CLOUD_HOSTNAME}/api/v2/organizations/${TF_CLOUD_ORGANIZATION}/workspaces")
    CREATE_HTTP=$(echo "$CREATE_RESPONSE" | grep "HTTP_CODE:" | cut -d: -f2)
    CREATE_BODY=$(echo "$CREATE_RESPONSE" | grep -v "HTTP_CODE:")

    if [ "$CREATE_HTTP" != "201" ]; then
      echo "ERROR: creation workspace echouee (HTTP $CREATE_HTTP) : $CREATE_BODY"
      return 1 2>/dev/null || exit 1
    fi
    NEW_WS_ID=$(echo "$CREATE_BODY" | jq -r '.data.id')
    echo "[init] workspace cree : $NEW_WS_ID"

    # Tentative best-effort d'attacher la Variable Set "Default provider instance".
    # Si la VS est deja en scope-tag alphaforge, l'attache est deja faite ; ce
    # POST sera idempotent (renvoie 204 ou 422 deja attache). Si on n'a pas
    # les perms sur la VS, on log et on continue — upload-config.sh poussera
    # TFC_AWS_PROVIDER_AUTH au niveau workspace en defense-en-profondeur.
    VS_ID=$(curl -s --header "Authorization: Bearer $TF_API_TOKEN" \
      "https://${TF_CLOUD_HOSTNAME}/api/v2/organizations/${TF_CLOUD_ORGANIZATION}/varsets" \
      | jq -r '.data[]? | select(.attributes.name=="Default provider instance") | .id' \
      | head -1)

    if [ -n "$VS_ID" ] && [ "$VS_ID" != "null" ]; then
      echo "[init] attache de la Variable Set $VS_ID au nouveau workspace..."
      ATTACH_HTTP=$(curl -s -o /dev/null -w "%{http_code}" \
        --header "Authorization: Bearer $TF_API_TOKEN" \
        --header "Content-Type: application/vnd.api+json" \
        --request POST \
        --data "{\"data\":[{\"type\":\"workspaces\",\"id\":\"$NEW_WS_ID\"}]}" \
        "https://${TF_CLOUD_HOSTNAME}/api/v2/varsets/${VS_ID}/relationships/workspaces")

      VS_ATTACHED=false
      case "$ATTACH_HTTP" in
        200|201|204) echo "[init] Variable Set attache"; VS_ATTACHED=true ;;
        422) echo "[init] Variable Set deja attache (probablement via tag-scope)"; VS_ATTACHED=true ;;
        *)   echo "[init] WARN: attache Variable Set HTTP $ATTACH_HTTP — fallback : copie des vars de la VS vers le workspace" ;;
      esac

      # Fallback : si l'attache a echoue, copier les vars non-sensibles
      # de la VS directement sur le workspace. TFC_AWS_RUN_ROLE_ARN est
      # typiquement non-sensible et lisible. Les vars sensibles renvoient
      # value=null via l'API (workaround : a regler manuellement).
      if [ "$VS_ATTACHED" = "false" ]; then
        VS_VARS=$(curl -s --header "Authorization: Bearer $TF_API_TOKEN" \
          "https://${TF_CLOUD_HOSTNAME}/api/v2/varsets/${VS_ID}/relationships/vars")

        # Le retour est paginate (data.[].attributes). On iter sur chaque var.
        echo "$VS_VARS" | jq -c '.data[]? | {key:.attributes.key, value:.attributes.value, category:.attributes.category, hcl:.attributes.hcl, sensitive:.attributes.sensitive}' | while IFS= read -r VAR_JSON; do
          V_KEY=$(printf '%s' "$VAR_JSON" | jq -r '.key')
          V_VAL=$(printf '%s' "$VAR_JSON" | jq -r '.value // empty')
          V_CAT=$(printf '%s' "$VAR_JSON" | jq -r '.category')
          V_HCL=$(printf '%s' "$VAR_JSON" | jq -r '.hcl')
          V_SENS=$(printf '%s' "$VAR_JSON" | jq -r '.sensitive')

          if [ -z "$V_VAL" ]; then
            echo "[init] WARN: var VS '$V_KEY' (sensitive=$V_SENS) — valeur non lisible, skip. A definir manuellement sur le workspace si requise."
            continue
          fi

          V_VAL_ESCAPED=$(printf '%s' "$V_VAL" | jq -Rs '.')
          COPY_HTTP=$(curl -s -o /dev/null -w "%{http_code}" \
            --header "Authorization: Bearer $TF_API_TOKEN" \
            --header "Content-Type: application/vnd.api+json" \
            --request POST \
            --data "{\"data\":{\"type\":\"vars\",\"attributes\":{\"key\":\"${V_KEY}\",\"value\":${V_VAL_ESCAPED},\"category\":\"${V_CAT}\",\"hcl\":${V_HCL},\"sensitive\":${V_SENS}}}}" \
            "https://${TF_CLOUD_HOSTNAME}/api/v2/workspaces/${NEW_WS_ID}/vars")
          if [ "$COPY_HTTP" = "201" ]; then
            echo "[init] var VS '$V_KEY' (category=$V_CAT) copie sur le workspace"
          else
            echo "[init] WARN: copie var '$V_KEY' HTTP $COPY_HTTP"
          fi
        done
      fi
    else
      echo "[init] WARN: Variable Set 'Default provider instance' introuvable ou non accessible — fallback hardcoded role ARN."
    fi

    # Defense en profondeur : push direct des env vars d'auth dynamique AWS.
    # Run role ARN lu depuis deploy/envs/<env>.tfvars (cle tfc_aws_run_role_arn).
    # Les ARN ne sont pas des secrets, juste des identifiants de role IAM.
    # Les feat-* sont bases sur sandbox.tfvars (cf. generation lignes ~66-72)
    # donc heritent automatiquement de l'ARN sandbox.
    # tr -d '\r' au cas ou le tfvars a des CRLF Windows.
    AWS_RUN_ROLE_ARN=$(grep -E "^[[:space:]]*tfc_aws_run_role_arn[[:space:]]*=" "$TFVARS_FILE" | head -1 | sed -E "s/^[[:space:]]*tfc_aws_run_role_arn[[:space:]]*=[[:space:]]*//" | tr -d '\r')
    AWS_RUN_ROLE_ARN="${AWS_RUN_ROLE_ARN#\"}"
    AWS_RUN_ROLE_ARN="${AWS_RUN_ROLE_ARN%\"}"

    _push_env_var() {
      KEY="$1"
      VAL="$2"
      [ -z "$VAL" ] && { echo "[init] WARN: $KEY vide, skip"; return 0; }
      ESCAPED=$(printf '%s' "$VAL" | jq -Rs '.')
      HTTP=$(curl -s -o /dev/null -w "%{http_code}" \
        --header "Authorization: Bearer $TF_API_TOKEN" \
        --header "Content-Type: application/vnd.api+json" \
        --request POST \
        --data "{\"data\":{\"type\":\"vars\",\"attributes\":{\"key\":\"${KEY}\",\"value\":${ESCAPED},\"category\":\"env\",\"hcl\":false,\"sensitive\":false}}}" \
        "https://${TF_CLOUD_HOSTNAME}/api/v2/workspaces/${NEW_WS_ID}/vars")
      case "$HTTP" in
        201) echo "[init] env var $KEY definie sur le workspace" ;;
        422) echo "[init] env var $KEY existe deja (probablement copie via VS), skip" ;;
        *)   echo "[init] WARN: push env var $KEY HTTP $HTTP" ;;
      esac
    }
    _push_env_var "TFC_AWS_PROVIDER_AUTH" "true"
    _push_env_var "TFC_AWS_RUN_ROLE_ARN"  "$AWS_RUN_ROLE_ARN"

    # Laisse 2s a TFC pour propager le workspace + tag avant upload-config.sh.
    sleep 2
  elif [ "$WS_HTTP_CODE" = "200" ]; then
    echo "[init] workspace existant : $TF_WORKSPACE_NAME — re-push idempotent des env vars d'auth AWS"
    NEW_WS_ID=$(jq -r '.data.id' < /tmp/ws_check.json)

    # Re-push idempotent des env vars critiques pour AWS dynamic creds.
    # Important pour les workspaces crees par un init.sh anterieur qui
    # n'avait pas ces vars hardcodees. POST renvoie 422 si la var existe
    # deja avec la meme valeur — dans ce cas on PATCH pour s'assurer que
    # la valeur est correcte.
    # Run role ARN lu depuis deploy/envs/<env>.tfvars (idem creation, cf. ci-dessus).
    AWS_RUN_ROLE_ARN=$(grep -E "^[[:space:]]*tfc_aws_run_role_arn[[:space:]]*=" "$TFVARS_FILE" | head -1 | sed -E "s/^[[:space:]]*tfc_aws_run_role_arn[[:space:]]*=[[:space:]]*//" | tr -d '\r')
    AWS_RUN_ROLE_ARN="${AWS_RUN_ROLE_ARN#\"}"
    AWS_RUN_ROLE_ARN="${AWS_RUN_ROLE_ARN%\"}"

    _upsert_env_var() {
      KEY="$1"
      VAL="$2"
      [ -z "$VAL" ] && { echo "[init] WARN: $KEY vide, skip"; return 0; }
      ESCAPED=$(printf '%s' "$VAL" | jq -Rs '.')

      # Try POST first
      HTTP=$(curl -s -o /tmp/upsert.json -w "%{http_code}" \
        --header "Authorization: Bearer $TF_API_TOKEN" \
        --header "Content-Type: application/vnd.api+json" \
        --request POST \
        --data "{\"data\":{\"type\":\"vars\",\"attributes\":{\"key\":\"${KEY}\",\"value\":${ESCAPED},\"category\":\"env\",\"hcl\":false,\"sensitive\":false}}}" \
        "https://${TF_CLOUD_HOSTNAME}/api/v2/workspaces/${NEW_WS_ID}/vars")
      case "$HTTP" in
        201) echo "[init] env var $KEY creee" ; return 0 ;;
      esac

      # Lookup existing var id and PATCH
      VAR_ID=$(curl -s --header "Authorization: Bearer $TF_API_TOKEN" \
        "https://${TF_CLOUD_HOSTNAME}/api/v2/workspaces/${NEW_WS_ID}/vars" \
        | jq -r ".data[]? | select(.attributes.key == \"${KEY}\" and .attributes.category == \"env\") | .id" \
        | head -1)
      if [ -z "$VAR_ID" ] || [ "$VAR_ID" = "null" ]; then
        echo "[init] WARN: POST $KEY a renvoye $HTTP et aucune var existante trouvee."
        return 1
      fi
      PATCH_HTTP=$(curl -s -o /dev/null -w "%{http_code}" \
        --header "Authorization: Bearer $TF_API_TOKEN" \
        --header "Content-Type: application/vnd.api+json" \
        --request PATCH \
        --data "{\"data\":{\"type\":\"vars\",\"attributes\":{\"key\":\"${KEY}\",\"value\":${ESCAPED},\"category\":\"env\",\"hcl\":false,\"sensitive\":false}}}" \
        "https://${TF_CLOUD_HOSTNAME}/api/v2/workspaces/${NEW_WS_ID}/vars/${VAR_ID}")
      case "$PATCH_HTTP" in
        200) echo "[init] env var $KEY mise a jour (PATCH $VAR_ID)" ;;
        *)   echo "[init] WARN: PATCH var $KEY HTTP $PATCH_HTTP" ;;
      esac
    }

    _upsert_env_var "TFC_AWS_PROVIDER_AUTH" "true"
    _upsert_env_var "TFC_AWS_RUN_ROLE_ARN"  "$AWS_RUN_ROLE_ARN"

    # Laisse 1s a TFC pour propager la mise a jour.
    sleep 1
  else
    echo "ERROR: lookup workspace HTTP $WS_HTTP_CODE — verifier TF_API_TOKEN."
    cat /tmp/ws_check.json 2>/dev/null
    return 1 2>/dev/null || exit 1
  fi
fi

export DEPLOY_ENV="$TARGET_ENV"
export TF_WORKSPACE="$TF_WORKSPACE_NAME"

echo "[init] DEPLOY_ENV=$DEPLOY_ENV TF_WORKSPACE=$TF_WORKSPACE"
