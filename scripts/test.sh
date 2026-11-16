#!/usr/bin/env bash
# Les contrôles de la CI (.github/workflows/app.yml), sur le poste.
#   ./scripts/test.sh          agents et interface
#   ./scripts/test.sh agents   ruff et pytest seulement
#   ./scripts/test.sh web      lint, typecheck, tests et build de l'interface seulement
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="${1:-all}"

case "$TARGET" in
  all|agents|web) ;;
  *) echo "usage : $0 [agents|web]" >&2; exit 2 ;;
esac

if [ "$TARGET" != web ]; then
  echo "==> app/agents : ruff, pytest"
  cd "$ROOT/app/agents"
  uv run --frozen ruff check
  uv run --frozen pytest -q
fi

if [ "$TARGET" != agents ]; then
  echo "==> app/web : lint, typecheck, test, build"
  cd "$ROOT/app/web"
  # Types générés par un build ou un `next dev` d'une autre branche : la CI part d'un dépôt propre, sans eux.
  rm -rf .next/types .next/dev/types
  npm run lint
  npm run typecheck
  npm test
  npm run build
fi

echo "OK"
