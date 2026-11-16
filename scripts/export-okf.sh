#!/usr/bin/env bash
# Copie les bases OKF du bucket AWS vers ./export/ (à faire avant la fermeture du compte Workshop, qui supprime
# toutes ses données). Utilise les identifiants AWS du poste.
#   ./scripts/export-okf.sh [dossier]   défaut : ./export
set -euo pipefail

command -v aws >/dev/null 2>&1 || { echo "Introuvable : aws (AWS CLI v2)" >&2; exit 1; }

DEST="${1:-export}"
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
BUCKET="alphaforge-sandbox-kb-$ACCOUNT"

for prefix in clients general; do
  echo "==> s3://$BUCKET/$prefix -> $DEST/$prefix"
  aws s3 sync "s3://$BUCKET/$prefix" "$DEST/$prefix"
done
