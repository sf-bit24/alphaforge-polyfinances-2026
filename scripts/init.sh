#!/usr/bin/env bash
# Prépare le poste : dépendances Python (uv) et Node, puis .env depuis .env.example.
#   ./scripts/init.sh          dépendances et .env
#   ./scripts/init.sh --data   reconstruit aussi les données longues du moteur (page /portfolio en mode local)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WITH_DATA=false

case "${1:-}" in
  "") ;;
  --data) WITH_DATA=true ;;
  *) echo "usage : $0 [--data]" >&2; exit 2 ;;
esac

need() {
  command -v "$1" >/dev/null 2>&1 || { echo "Introuvable : $1 ($2)" >&2; exit 1; }
}
need uv "https://docs.astral.sh/uv/"
need node "Node.js 20.9 ou plus, 24 recommandé"
need npm "fourni avec Node.js"

echo "==> app/agents : uv sync (avec le groupe finance)"
(cd "$ROOT/app/agents" && uv sync --frozen --group finance)

echo "==> app/web : npm ci"
(cd "$ROOT/app/web" && npm ci)

if [ -f "$ROOT/.env" ]; then
  echo "==> .env existe déjà : inchangé (comparer avec .env.example au besoin)"
else
  cp "$ROOT/.env.example" "$ROOT/.env"
  echo "==> .env créé depuis .env.example"
fi

if [ "$WITH_DATA" = true ]; then
  echo "==> Données longues du moteur (sources publiques, quelques minutes)"
  (cd "$ROOT/app/agents" && uv run --frozen --group finance --group backtest-data \
    python -I -m alphaforge.finance.backtest.build_data)
fi

echo
echo "Prêt. Lancer : ./scripts/run.sh [mock|local|aws]"
