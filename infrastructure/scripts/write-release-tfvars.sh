#!/bin/sh
set -eu

# =============================================================================
# Ecrit deploy/release.auto.tfvars : artefact de pipeline, jamais commit.
#
# Usage (job release_tfvars de .github/workflows/app.yml, cwd = racine du repo) :
#   sh infrastructure/scripts/write-release-tfvars.sh release_id=<sha court>
# ou, sous dash qui ignore les arguments d'un script source :
#   RELEASE_ID=<sha court> sh infrastructure/scripts/write-release-tfvars.sh
#
# release_id nomme le zip du code des runtimes AgentCore
# (runtime/agents-<release_id>.zip) : il doit etre immuable, donc un SHA de
# commit, jamais un tag mobile comme latest. Le script refuse tout autre cas.
# =============================================================================

OUT="$(dirname "$0")/../deploy/release.auto.tfvars"
RELEASE="${RELEASE_ID:-}"

for PAIR in "$@"; do
  case "$PAIR" in
    release_id=*) RELEASE="${PAIR#release_id=}" ;;
    *) echo "ERROR: argument inconnu '$PAIR' (attendu release_id=<sha court>)" >&2; exit 1 ;;
  esac
done

case "$RELEASE" in
  '') echo "ERROR: release_id absent (release_id=<sha court> ou RELEASE_ID)." >&2; exit 1 ;;
  *[!0123456789abcdef]*) echo "ERROR: release_id '$RELEASE' n'est pas un SHA hexadecimal en minuscules." >&2; exit 1 ;;
esac

LEN=$(printf '%s' "$RELEASE" | wc -c | tr -d ' ')
if [ "$LEN" -lt 7 ] || [ "$LEN" -gt 40 ]; then
  echo "ERROR: release_id '$RELEASE' doit compter de 7 a 40 caracteres." >&2
  exit 1
fi

{
  echo "# Genere par scripts/write-release-tfvars.sh : artefact de pipeline, jamais commit."
  printf 'release_id = "%s"\n' "$RELEASE"
} > "$OUT"

cat "$OUT"
