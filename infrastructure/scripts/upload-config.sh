#!/bin/sh
set -e

# =============================================================================
# Upload de la configuration Terraform vers TFC.
#
# Modele : deploy/envs/<DEPLOY_ENV>.tfvars contient les valeurs statiques (HCL natif).
# Ce script :
#   1. Copie deploy/envs/<DEPLOY_ENV>.tfvars -> infra/terraform.auto.tfvars
#      dans le bundle (auto-load par TF)
#   2. Empaquette infra/ en config.tar.gz pour un workspace TFC dont le
#      working directory reste "infra"
#   3. Upload le bundle vers TFC
#   4. Assure que les env vars TFC d'auth OIDC AWS sont configurees
#      (TFC_AWS_PROVIDER_AUTH=true) — necessaire pour que TFC ecrive le
#      token JWT consomme par assume_role_with_web_identity.
#   5. Pousse release_id (SHA du commit, nom du zip des runtimes AgentCore)
#      en variable Terraform du workspace.
#
# Le bundle contient infra/build/ : agents.zip (code des runtimes) et
# knowledge/ (base generale de depart), artefact agents-package du run.
# =============================================================================

if [ -z "$DEPLOY_ENV" ]; then
  echo "ERROR: DEPLOY_ENV non defini (attendu : sandbox|nprod|prod)"
  exit 1
fi

INFRA_DIR="infra"
DEPLOY_DIR="deploy"
TFVARS_SRC="${DEPLOY_DIR}/envs/${DEPLOY_ENV}.tfvars"
RELEASE_TFVARS="${DEPLOY_DIR}/release.auto.tfvars"
AGENTS_ZIP="${INFRA_DIR}/build/agents.zip"
if [ ! -f "$TFVARS_SRC" ]; then
  echo "ERROR: $TFVARS_SRC introuvable"
  exit 1
fi

if [ ! -d "$INFRA_DIR" ]; then
  echo "ERROR: dossier Terraform '$INFRA_DIR' introuvable"
  exit 1
fi

# Artefacts du run (.github/workflows/app.yml) : sans eux, le plan echoue plus
# loin et moins clairement.
if [ ! -f "$RELEASE_TFVARS" ]; then
  echo "ERROR: $RELEASE_TFVARS absent (artefact release-tfvars du job release_tfvars)."
  exit 1
fi
if [ ! -f "$AGENTS_ZIP" ]; then
  echo "ERROR: $AGENTS_ZIP absent (artefact agents-package du job package_agents)."
  exit 1
fi

if [ -z "$TF_API_TOKEN" ]; then
  echo "ERROR: TF_API_TOKEN absent."
  echo "       Verifier le secret de repo GitHub TF_API_TOKEN. Les PR ouvertes depuis un fork"
  echo "       ne recoivent aucun secret : le plan PR ne marche que pour les branches du repo."
  exit 1
fi

# Recupere l'ID du workspace Terraform Cloud (TF_WORKSPACE defini par init.sh)
WORKSPACE_RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" \
  --header "Authorization: Bearer $TF_API_TOKEN" \
  "https://${TF_CLOUD_HOSTNAME}/api/v2/organizations/${TF_CLOUD_ORGANIZATION}/workspaces/${TF_WORKSPACE}")
WORKSPACE_HTTP_CODE=$(echo "$WORKSPACE_RESPONSE" | grep "HTTP_CODE:" | cut -d: -f2)
WORKSPACE_DATA=$(echo "$WORKSPACE_RESPONSE" | grep -v "HTTP_CODE:")

if [ "$WORKSPACE_HTTP_CODE" != "200" ]; then
  echo "ERROR: lookup workspace TFC '$TF_WORKSPACE' HTTP $WORKSPACE_HTTP_CODE"
  case "$WORKSPACE_HTTP_CODE" in
    401|403)
      echo "       Token TFC absent, invalide, ou sans acces au workspace."
      echo "       En PR, verifier que TF_API_TOKEN n'est pas un secret d'environnement GitHub protege."
      ;;
    404)
      echo "       Workspace introuvable. Verifier le nom dans TFC : '$TF_WORKSPACE'."
      ;;
  esac
  echo "$WORKSPACE_DATA"
  exit 1
fi

WORKSPACE_ID=$(echo "$WORKSPACE_DATA" | jq -r '.data.id')

if [ -z "$WORKSPACE_ID" ] || [ "$WORKSPACE_ID" = "null" ]; then
  echo "ERROR: workspace introuvable : $TF_WORKSPACE"
  exit 1
fi
echo "Workspace ID : $WORKSPACE_ID"

if [ "${GITHUB_EVENT_NAME:-}" = "pull_request" ]; then
  echo "Workspace auto-apply non modifie en run PR."
else
  AUTO_APPLY_RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" \
    --header "Authorization: Bearer $TF_API_TOKEN" \
    --header "Content-Type: application/vnd.api+json" \
    --request PATCH \
    --data "{\"data\":{\"type\":\"workspaces\",\"id\":\"${WORKSPACE_ID}\",\"attributes\":{\"auto-apply\":true}}}" \
    "https://${TF_CLOUD_HOSTNAME}/api/v2/workspaces/${WORKSPACE_ID}")
  AUTO_APPLY_HTTP_CODE=$(echo "$AUTO_APPLY_RESPONSE" | grep "HTTP_CODE:" | cut -d: -f2)
  AUTO_APPLY_BODY=$(echo "$AUTO_APPLY_RESPONSE" | grep -v "HTTP_CODE:")

  case "$AUTO_APPLY_HTTP_CODE" in
    200)
      echo "Workspace auto-apply active : $TF_WORKSPACE"
      ;;
    *)
      echo "WARN: impossible d'activer auto-apply sur '$TF_WORKSPACE' HTTP $AUTO_APPLY_HTTP_CODE"
      echo "      Le pipeline continue; regler Auto Apply dans TFC ou utiliser un token avec droits admin workspace."
      echo "$AUTO_APPLY_BODY"
      ;;
  esac
fi

# Cree une nouvelle configuration version
CONFIG_VERSION_RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" \
  --header "Authorization: Bearer $TF_API_TOKEN" \
  --header "Content-Type: application/vnd.api+json" \
  --request POST \
  --data '{"data":{"type":"configuration-versions","attributes":{"auto-queue-runs":false}}}' \
  "https://${TF_CLOUD_HOSTNAME}/api/v2/workspaces/${WORKSPACE_ID}/configuration-versions")
CONFIG_VERSION_HTTP_CODE=$(echo "$CONFIG_VERSION_RESPONSE" | grep "HTTP_CODE:" | cut -d: -f2)
CONFIG_VERSION_BODY=$(echo "$CONFIG_VERSION_RESPONSE" | grep -v "HTTP_CODE:")

if [ "$CONFIG_VERSION_HTTP_CODE" != "201" ]; then
  echo "ERROR: creation configuration-version TFC HTTP $CONFIG_VERSION_HTTP_CODE"
  echo "$CONFIG_VERSION_BODY"
  exit 1
fi

UPLOAD_URL=$(echo "$CONFIG_VERSION_BODY" | jq -r '.data.attributes."upload-url"')
CONFIG_VERSION_ID=$(echo "$CONFIG_VERSION_BODY" | jq -r '.data.id')

if [ -z "$UPLOAD_URL" ] || [ "$UPLOAD_URL" = "null" ]; then
  echo "ERROR: impossible de creer la configuration version"
  exit 1
fi

# Empaquette et envoie la config Terraform.
# On n'inclut PAS deploy/envs/ (les autres tfvars n'ont pas leur place dans le
# bundle TFC). Le bundle garde le dossier infra/ parce que le workspace TFC a
# Working directory = infra.
BUNDLE_DIR=$(mktemp -d)
cleanup_bundle() {
  rm -rf "$BUNDLE_DIR" config.tar.gz
}
trap cleanup_bundle EXIT

mkdir -p "$BUNDLE_DIR/$INFRA_DIR"
tar --exclude=.terraform --exclude=.terraform.lock.hcl -cf - -C "$INFRA_DIR" . | tar -xf - -C "$BUNDLE_DIR/$INFRA_DIR"
cp "$TFVARS_SRC" "$BUNDLE_DIR/$INFRA_DIR/terraform.auto.tfvars"
cp "$RELEASE_TFVARS" "$BUNDLE_DIR/$INFRA_DIR/release.auto.tfvars"
tar -czf config.tar.gz -C "$BUNDLE_DIR" .

echo "Contenu du bundle config.tar.gz :"
tar -tzf config.tar.gz | sed 's/^/  /'

curl -s --fail --request PUT --data-binary @config.tar.gz "$UPLOAD_URL"
echo "Configuration uploadee : $CONFIG_VERSION_ID"

# --- helpers TFC vars -------------------------------------------------------
# Supporte category="terraform" (vars Terraform: var.foo) ou "env" (env vars
# du run, ex. TFC_AWS_PROVIDER_AUTH qui controle l'injection OIDC par TFC).
_set_tf_var_internal() {
  VAR_KEY="$1"
  VAR_VALUE="$2"
  IS_HCL="$3"
  CATEGORY="${4:-terraform}"

  if [ -z "$VAR_VALUE" ]; then
    echo "  -> $VAR_KEY [SKIP] empty value"
    return 0
  fi

  echo "  -> $VAR_KEY (category=$CATEGORY, hcl=$IS_HCL) value=$VAR_VALUE"
  ESCAPED_VALUE=$(printf '%s' "$VAR_VALUE" | jq -Rs '.')

  CREATE_RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" \
    --header "Authorization: Bearer $TF_API_TOKEN" \
    --header "Content-Type: application/vnd.api+json" \
    --request POST \
    --data "{\"data\":{\"type\":\"vars\",\"attributes\":{\"key\":\"${VAR_KEY}\",\"value\":${ESCAPED_VALUE},\"category\":\"${CATEGORY}\",\"hcl\":${IS_HCL},\"sensitive\":false}}}" \
    "https://${TF_CLOUD_HOSTNAME}/api/v2/workspaces/${WORKSPACE_ID}/vars")

  CREATE_HTTP_CODE=$(echo "$CREATE_RESPONSE" | grep "HTTP_CODE:" | cut -d: -f2)
  CREATE_BODY=$(echo "$CREATE_RESPONSE" | grep -v "HTTP_CODE:")

  if [ "$CREATE_HTTP_CODE" = "201" ]; then
    echo "     [created]"
    return 0
  fi

  # POST a echoue ou retourne autre chose que 201 (souvent 422 si la var
  # existe deja). On lookup l'ID existant et on PATCH.
  echo "     POST -> HTTP $CREATE_HTTP_CODE, looking up existing var..."
  VARS_RESPONSE=$(curl -s \
    --header "Authorization: Bearer $TF_API_TOKEN" \
    "https://${TF_CLOUD_HOSTNAME}/api/v2/workspaces/${WORKSPACE_ID}/vars")
  VAR_ID=$(echo "$VARS_RESPONSE" | jq -r ".data[] | select(.attributes.key == \"${VAR_KEY}\" and .attributes.category == \"${CATEGORY}\") | .id")

  if [ -z "$VAR_ID" ] || [ "$VAR_ID" = "null" ]; then
    echo "     [FAIL] POST returned $CREATE_HTTP_CODE and no existing var found for key=$VAR_KEY category=$CATEGORY"
    echo "     POST body: $CREATE_BODY"
    return 1
  fi

  echo "     -> PATCH $VAR_ID"
  PATCH_RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" \
    --header "Authorization: Bearer $TF_API_TOKEN" \
    --header "Content-Type: application/vnd.api+json" \
    --request PATCH \
    --data "{\"data\":{\"type\":\"vars\",\"attributes\":{\"key\":\"${VAR_KEY}\",\"value\":${ESCAPED_VALUE},\"category\":\"${CATEGORY}\",\"hcl\":${IS_HCL},\"sensitive\":false}}}" \
    "https://${TF_CLOUD_HOSTNAME}/api/v2/workspaces/${WORKSPACE_ID}/vars/${VAR_ID}")
  PATCH_HTTP_CODE=$(echo "$PATCH_RESPONSE" | grep "HTTP_CODE:" | cut -d: -f2)
  PATCH_BODY=$(echo "$PATCH_RESPONSE" | grep -v "HTTP_CODE:")

  if [ "$PATCH_HTTP_CODE" != "200" ]; then
    echo "     [FAIL] PATCH returned $PATCH_HTTP_CODE"
    echo "     PATCH body: $PATCH_BODY"
    return 1
  fi
  echo "     [updated]"
}

set_tf_var_hcl() { _set_tf_var_internal "$1" "$2" "true"  "terraform"; }
set_tf_env_var() { _set_tf_var_internal "$1" "$2" "false" "env"; }

# --- Env vars TFC pour auth dynamique AWS (OIDC) ----------------------------
# En principe, la Variable Set TFC "Default provider instance" (Dynamic
# Provider Credentials) attache au workspace fournit deja
# TFC_AWS_PROVIDER_AUTH=true et TFC_AWS_RUN_ROLE_ARN. On force quand meme
# les deux au niveau workspace en defense-en-profondeur, au cas ou la
# Variable Set serait detachee par erreur ou jamais attachee aux workspaces
# canoniques (sandbox/nprod/prod) — sinon le run TFC plante avec
# "TFC_AWS_RUN_ROLE_ARN must be set" avant meme le plan.
# Ref : https://developer.hashicorp.com/terraform/cloud-docs/workspaces/dynamic-provider-credentials/aws-configuration
echo "Configuration des env vars TFC (OIDC AWS)..."
set_tf_env_var "TFC_AWS_PROVIDER_AUTH" "true"

# Run role ARN lu depuis deploy/envs/<env>.tfvars (cle tfc_aws_run_role_arn,
# declaree dans variables.tf juste pour eviter le warning "value for
# undeclared variable" — non consomme par les ressources TF). Les ARN ne
# sont pas des secrets, juste des identifiants de role IAM.
# tr -d '\r' au cas ou le tfvars est commit avec CRLF Windows.
AWS_RUN_ROLE_ARN=$(grep -E "^[[:space:]]*tfc_aws_run_role_arn[[:space:]]*=" "$TFVARS_SRC" | head -1 | sed -E "s/^[[:space:]]*tfc_aws_run_role_arn[[:space:]]*=[[:space:]]*//" | tr -d '\r')
AWS_RUN_ROLE_ARN="${AWS_RUN_ROLE_ARN#\"}"
AWS_RUN_ROLE_ARN="${AWS_RUN_ROLE_ARN%\"}"
if [ -n "$AWS_RUN_ROLE_ARN" ]; then
  set_tf_env_var "TFC_AWS_RUN_ROLE_ARN" "$AWS_RUN_ROLE_ARN"
else
  echo "  -> TFC_AWS_RUN_ROLE_ARN [SKIP] tfc_aws_run_role_arn vide ou absent dans $TFVARS_SRC"
fi


# --- Push des inputs Terraform statiques depuis deploy/envs/<env>.tfvars ----------
# On constate empiriquement que TFC n'autoload pas systematiquement
# terraform.auto.tfvars du bundle pour des inputs qui n'ont pas deja une
# workspace var equivalente. Workaround : on lit chaque cle attendue dans
# le tfvars et on la pousse comme workspace var (terraform, HCL) via l'API.
# Seuls les champs single-line sont supportes — additional_tags reste a son
# default {} si elle est multi-ligne dans le tfvars.
echo "Push des inputs Terraform statiques depuis $TFVARS_SRC..."
for KEY in environment aws_region kms_admin_principal_arns; do
  # Recupere la valeur (RHS du premier "<KEY> = ..." trouve, single-line).
  # `tr -d '\r'` indispensable : les tfvars commit depuis Windows ont des
  # CRLF, et un CR trailing dans la valeur corrompt le JSON envoye a TFC.
  RAW=$(grep -E "^[[:space:]]*${KEY}[[:space:]]*=" "$TFVARS_SRC" | head -1 | sed -E "s/^[[:space:]]*${KEY}[[:space:]]*=[[:space:]]*//" | tr -d '\r')
  if [ -z "$RAW" ]; then
    echo "  -> $KEY absent de $TFVARS_SRC, skip"
    continue
  fi
  # 1) Push comme var terraform HCL (RAW est deja en HCL natif depuis tfvars).
  set_tf_var_hcl "$KEY" "$RAW"

  # 2) Defense en profondeur : aussi pousser comme TF_VAR_<KEY> env var.
  # Terraform plan lit TF_VAR_* env vars en input — redondance si le push
  # terraform-category echoue ou si le bundle auto.tfvars n'est pas autoloade.
  # TF_VAR env var format :
  #   - string : valeur RAW sans guillemets externes
  #   - liste/map : valeur RAW telle quelle (Terraform parse comme HCL)
  case "$RAW" in
    \"*\")
      ENV_VAL="${RAW#\"}"
      ENV_VAL="${ENV_VAL%\"}"
      ;;
    *)
      ENV_VAL="$RAW"
      ;;
  esac
  set_tf_env_var "TF_VAR_${KEY}" "$ENV_VAL"
done

# --- Release : fournie par deploy/release.auto.tfvars ----------------------
# Artefact du job release_tfvars (.github/workflows/app.yml), inclus dans le
# bundle ci-dessus. Pousse aussi en variable du workspace, en defense en
# profondeur comme les inputs statiques.
RELEASE_ID=$(grep -E "^[[:space:]]*release_id[[:space:]]*=" "$RELEASE_TFVARS" | head -1 | sed -E "s/^[[:space:]]*release_id[[:space:]]*=[[:space:]]*//" | tr -d '\r"')
if [ -z "$RELEASE_ID" ]; then
  echo "ERROR: release_id absent de $RELEASE_TFVARS"
  exit 1
fi
echo "Release : $RELEASE_ID"
set_tf_var_hcl "release_id" "\"$RELEASE_ID\""
set_tf_env_var "TF_VAR_release_id" "$RELEASE_ID"

# Persiste pour les jobs suivants : workspace.env en local, outputs du job
# upload_configuration en CI (lus par plan via needs.*.outputs).
echo "WORKSPACE_ID=$WORKSPACE_ID" > workspace.env
echo "CONFIG_VERSION_ID=$CONFIG_VERSION_ID" >> workspace.env
echo "DEPLOY_ENV=$DEPLOY_ENV" >> workspace.env
echo "TF_WORKSPACE=$TF_WORKSPACE" >> workspace.env
if [ -n "${GITHUB_OUTPUT:-}" ]; then
  cat workspace.env >> "$GITHUB_OUTPUT"
fi
