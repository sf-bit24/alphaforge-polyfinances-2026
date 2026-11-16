#!/bin/sh
set -eu

# =============================================================================
# Knowledge Bases des clients : les liste (par defaut), ou les supprime.
#
# Le runtime profile cree une Knowledge Base et un index S3 Vectors par
# investisseur (app/agents/src/alphaforge/profile/client_kb.py, infra/client_kb.tf).
# Ils ne sont pas dans l'etat Terraform : un destroy ne supprime pas les
# Knowledge Bases (le bucket de vecteurs, en force_destroy, emporte les index).
#
# Le script retrouve les bases par leurs etiquettes alphaforge:scope=client et
# alphaforge:prefix=<PREFIX>, puis, avec --apply :
#   1. supprime chaque base (ses sources CUSTOM, en RETAIN, partent avec elle
#      sans toucher aux vecteurs) ;
#   2. supprime les index client-* du bucket <PREFIX>-client-vectors.
# L'ordre par rapport au destroy n'importe pas. Les clients/<id>/kb.json restent
# dans le bucket des bases OKF : une base supprimee y passe a failed a la
# prochaine ingestion (les runtimes n'ont aucun droit de suppression et ne la
# recreent pas).
#
# Usage, avec les identifiants AWS de l'equipe (role du Workshop) :
#   sh scripts/clean-client-kbs.sh               # --dry-run : liste seulement
#   sh scripts/clean-client-kbs.sh --apply       # supprime
#   PREFIX=alphaforge-sandbox AWS_REGION=us-east-1 sh scripts/clean-client-kbs.sh
# =============================================================================

MODE="dry-run"
for arg in "$@"; do
  case "$arg" in
    --dry-run) MODE="dry-run" ;;
    --apply) MODE="apply" ;;
    -h | --help)
      sed -n '4,25p' "$0"
      exit 0
      ;;
    *)
      echo "ERROR: argument inconnu : $arg (--dry-run ou --apply)"
      exit 1
      ;;
  esac
done

: "${AWS_REGION:=us-east-1}"
: "${PREFIX:=alphaforge-sandbox}"
: "${VECTOR_BUCKET:=${PREFIX}-client-vectors}"
export AWS_REGION

ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
echo "[clean-client-kbs] compte $ACCOUNT, region $AWS_REGION, prefixe $PREFIX, mode $MODE"

# --- 1. Knowledge Bases etiquetees client --------------------------------------
kbs=0
for kb_id in $(aws bedrock-agent list-knowledge-bases --query 'knowledgeBaseSummaries[].knowledgeBaseId' --output text); do
  arn="arn:aws:bedrock:${AWS_REGION}:${ACCOUNT}:knowledge-base/${kb_id}"
  tags=$(aws bedrock-agent list-tags-for-resource --resource-arn "$arn" \
    --query '[tags."alphaforge:scope", tags."alphaforge:prefix", tags."alphaforge:client_id"]' --output text)
  scope=$(echo "$tags" | cut -f1)
  owner=$(echo "$tags" | cut -f2)
  client=$(echo "$tags" | cut -f3)
  if [ "$scope" != "client" ] || [ "$owner" != "$PREFIX" ]; then
    continue
  fi
  kbs=$((kbs + 1))
  echo "  Knowledge Base $kb_id (client $client)"
  if [ "$MODE" = "apply" ]; then
    aws bedrock-agent delete-knowledge-base --knowledge-base-id "$kb_id" --query status --output text
  fi
done

# --- 2. Index client-* du bucket de vecteurs des clients -----------------------
indexes=0
if aws s3vectors get-vector-bucket --vector-bucket-name "$VECTOR_BUCKET" >/dev/null 2>&1; then
  for name in $(aws s3vectors list-indexes --vector-bucket-name "$VECTOR_BUCKET" --prefix client- \
    --query 'indexes[].indexName' --output text); do
    indexes=$((indexes + 1))
    echo "  index $VECTOR_BUCKET/$name"
    if [ "$MODE" = "apply" ]; then
      aws s3vectors delete-index --vector-bucket-name "$VECTOR_BUCKET" --index-name "$name"
    fi
  done
else
  echo "  bucket de vecteurs $VECTOR_BUCKET absent : aucun index a supprimer"
fi

if [ "$MODE" = "apply" ]; then
  echo "[clean-client-kbs] supprime : $kbs Knowledge Base(s), $indexes index"
else
  echo "[clean-client-kbs] trouve : $kbs Knowledge Base(s), $indexes index (--apply pour supprimer)"
fi
