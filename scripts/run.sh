#!/usr/bin/env bash
# Lance l'application sur le poste, avec les variables de .env (racine du dépôt).
#   ./scripts/run.sh mock    interface seule, simulateur du contrat, aucun appel AWS
#   ./scripts/run.sh local   runtimes profile (:8080) et portfolio (:8081) sur le poste, puis l'interface
#   ./scripts/run.sh aws     interface branchée sur les runtimes déployés (identifiants AWS du poste)
# Sans argument : AGENT_MODE de .env, sinon mock. Interface sur http://localhost:3000. Ctrl-C arrête tout.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [ -f "$ROOT/.env" ]; then
  set -a
  # shellcheck source=/dev/null
  . "$ROOT/.env"
  set +a
fi

MODE="${1:-${AGENT_MODE:-mock}}"
case "$MODE" in
  mock|local|aws) ;;
  *) echo "usage : $0 [mock|local|aws]" >&2; exit 2 ;;
esac
export AGENT_MODE="$MODE"

[ -d "$ROOT/app/web/node_modules" ] || { echo "Dépendances absentes : lancer ./scripts/init.sh" >&2; exit 1; }

# À la sortie (Ctrl-C, kill, arrêt de l'interface, runtime muet) : arrêter chaque serveur et ses processus enfants.
# Tous tournent en arrière-plan : bash ne traite un signal qu'entre deux commandes, et `wait` s'interrompt.
PIDS=""
kill_tree() {
  local child
  for child in $(pgrep -P "$1" 2>/dev/null); do kill_tree "$child"; done
  kill "$1" 2>/dev/null || true
}
stop_all() {
  local pid
  for pid in $PIDS; do kill_tree "$pid"; done
}
trap stop_all EXIT
trap 'exit 130' INT TERM

# Lance un runtime Python en arrière-plan, journaux préfixés par son rôle.
start_runtime() {
  local role="$1" port="$2"
  shift 2
  echo "==> runtime $role sur http://127.0.0.1:$port"
  (
    cd "$ROOT/app/agents"
    AGENT_ROLE="$role" PORT="$port" ALPHAFORGE_STORE=local PYTHONUNBUFFERED=1 \
      uv run --frozen "$@" python main.py 2>&1 | awk -v p="[$role] " '{ print p $0; fflush() }'
  ) &
  PIDS="$PIDS $!"
}

# Attend le /ping d'un runtime (60 s au plus).
wait_ping() {
  local role="$1" port="$2" _
  for _ in $(seq 60); do
    curl -fsS "http://127.0.0.1:$port/ping" >/dev/null 2>&1 && return 0
    sleep 1
  done
  echo "Le runtime $role ne répond pas sur le port $port" >&2
  exit 1
}

if [ "$MODE" = local ]; then
  if ! (cd "$ROOT/app/agents" && uv run --frozen --group finance python -c \
    "import sys; from alphaforge.finance.backtest.paths import long_data_available; sys.exit(not long_data_available())"); then
    echo "Attention : données longues absentes, /portfolio échouera. Les reconstruire : ./scripts/init.sh --data" >&2
  fi
  export LOCAL_AGENT_URL="${LOCAL_AGENT_URL:-http://127.0.0.1:8080/invocations}"
  export LOCAL_PORTFOLIO_URL="${LOCAL_PORTFOLIO_URL:-http://127.0.0.1:8081/invocations}"
  start_runtime profile 8080
  start_runtime portfolio 8081 --group finance
  wait_ping profile 8080
  wait_ping portfolio 8081
fi

echo "==> interface (AGENT_MODE=$MODE) sur http://localhost:3000"
(cd "$ROOT/app/web" && npm run dev) &
WEB_PID=$!
PIDS="$PIDS $WEB_PID"
wait "$WEB_PID"
