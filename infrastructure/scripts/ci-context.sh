#!/bin/sh
set -eu

# =============================================================================
# Decide ce que le run GitHub Actions fait (equivalent des `rules:` GitLab).
# Appele par le job `context` de .github/workflows/pipeline.yml, cwd = racine
# du repo. Ecrit ses outputs dans $GITHUB_OUTPUT (et sur stdout).
#
# Entrees (env) :
#   GITHUB_EVENT_NAME, GITHUB_REF_NAME, GITHUB_BASE_REF, GITHUB_SHA,
#   GITHUB_REPOSITORY      : predefinies par GitHub
#   DEFAULT_BRANCH         : github.event.repository.default_branch
#   EPHEMERAL_ENVS_ENABLED : "true" pour deployer les push feature/*
#   DESTROY_ENV            : "true" -> tests seulement
#   DEPLOY_ENV, TF_CLOUD_HOSTNAME, TF_CLOUD_ORGANIZATION : republies tels quels
#   ECR_REGISTRY_IMAGE     : depot ECR de l'image de l'interface (sinon GHCR)
#   AWS_ECR_PUSH_ROLE_ARN, AWS_REGION : role et region du push, republies
#
# Sorties :
#   build   : construire et pousser les images
#   deploy  : images_tfvars + validate -> upload -> plan
#   apply   : apply apres le plan
#   image_tag, registry_image, aws_push_role_arn, aws_region, deploy_env,
#   ephemeral_envs_enabled, tf_cloud_hostname, tf_cloud_organization
#
# | evenement                                   | build | deploy | apply |
# |---------------------------------------------|-------|--------|-------|
# | push branche par defaut                     | true  | true   | true  |
# | push feature/* + EPHEMERAL_ENVS_ENABLED     | true  | true   | true  |
# | pull_request touchant infrastructure/**     | false | true   | false |
# | autre (PR sans infra, dispatch, destroy...) | false | false  | false |
# =============================================================================

EVENT="${GITHUB_EVENT_NAME:-}"
BRANCH="${GITHUB_REF_NAME:-}"
DEFAULT_BRANCH="${DEFAULT_BRANCH:-main}"
EPHEMERAL="${EPHEMERAL_ENVS_ENABLED:-false}"

BUILD=false
DEPLOY=false
APPLY=false

infra_changed() {
  BASE_REF="${GITHUB_BASE_REF:-}"
  [ -n "$BASE_REF" ] || return 1
  # Necessite actions/checkout avec fetch-depth: 0.
  git diff --name-only "origin/${BASE_REF}...HEAD" -- infrastructure/ | grep -q .
}

if [ "${DESTROY_ENV:-false}" != "true" ]; then
  case "$EVENT" in
    push)
      if [ "$BRANCH" = "$DEFAULT_BRANCH" ]; then
        BUILD=true
      else
        case "$EPHEMERAL:$BRANCH" in
          true:feature/?*) BUILD=true ;;
        esac
      fi
      DEPLOY=$BUILD
      APPLY=$BUILD
      ;;
    pull_request)
      if infra_changed; then
        DEPLOY=true
      fi
      ;;
  esac
fi

# Image de l'interface : le depot ECR du bootstrap s'il est donne, sinon le
# prefixe GHCR du repo (GHCR exige un chemin en minuscules).
REGISTRY_IMAGE="${ECR_REGISTRY_IMAGE:-ghcr.io/$(printf '%s' "${GITHUB_REPOSITORY:-local/repo}" | tr '[:upper:]' '[:lower:]')}"
# 8 caracteres, comme CI_COMMIT_SHORT_SHA cote GitLab.
IMAGE_TAG=$(printf '%.8s' "${GITHUB_SHA:-local}")

OUT="${GITHUB_OUTPUT:-/dev/null}"
{
  echo "build=$BUILD"
  echo "deploy=$DEPLOY"
  echo "apply=$APPLY"
  echo "image_tag=$IMAGE_TAG"
  echo "registry_image=$REGISTRY_IMAGE"
  echo "aws_push_role_arn=${AWS_ECR_PUSH_ROLE_ARN:-}"
  echo "aws_region=${AWS_REGION:-us-east-1}"
  echo "deploy_env=${DEPLOY_ENV:-}"
  echo "ephemeral_envs_enabled=$EPHEMERAL"
  echo "tf_cloud_hostname=${TF_CLOUD_HOSTNAME:-app.terraform.io}"
  echo "tf_cloud_organization=${TF_CLOUD_ORGANIZATION:-}"
} | tee -a "$OUT"
