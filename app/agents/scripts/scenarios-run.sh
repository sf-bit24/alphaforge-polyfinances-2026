#!/bin/sh
# Point d'entrée du job SageMaker Processing des scénarios (image scikit-learn d'AWS, Python 3.12, linux/amd64).
#
# Copié par package.sh dans infra/build/scenarios/run.sh, puis envoyé par Terraform sous
# scenarios/code/<release_id>/ ; SageMaker le place dans /opt/ml/processing/input/code/ et le lance par
#   /bin/sh /opt/ml/processing/input/code/run.sh --request <request.json> --output <dossier>
# (arguments posés par la machine Step Functions, infrastructure/infra/scenarios.tf).
#
# 1. Extrait scenarios.zip dans /opt/ml/processing/app : alphaforge/ (scenarios et jeu de départ),
#    research/backtest/ s'il a été empaqueté, et les dépendances figées de requirements-job.txt.
# 2. Place ce dossier EN TÊTE de sys.path par un fichier .pth du site-packages de l'image. Un .pth reste lu sous
#    « python -I » (qui ignore PYTHONPATH), mode imposé à build_data.py ; les dépendances figées passent donc
#    avant celles de l'image, dans tous les processus Python du job.
# 3. Si research/backtest/ est présent : « python3 -I research/backtest/data/build_data.py » reconstruit les
#    données mensuelles depuis les sources publiques (accès Internet), dans le volume du job seulement.
#    Sinon, les données sont attendues dans /opt/ml/processing/input/data (aucune entrée de ce nom n'est posée
#    par la machine aujourd'hui : le job échouera en le disant).
# 4. Traduit params de request.json en options du job (config, seed, fitted_through, workers ; toute autre clé
#    est refusée), copie request.json dans les sorties, puis exécute « python3 -m alphaforge.scenarios.job ».
set -eu

request=""
output=/opt/ml/processing/output
while [ "$#" -gt 0 ]; do
    case "$1" in
        --request) request="$2"; shift 2 ;;
        --output) output="$2"; shift 2 ;;
        *) echo "error: unknown argument: $1" >&2; exit 2 ;;
    esac
done

code_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
app_dir=${SCENARIOS_APP_DIR:-/opt/ml/processing/app}  # surcharge pour un essai local seulement

if [ ! -f "$code_dir/scenarios.zip" ]; then
    echo "error: $code_dir/scenarios.zip is missing" >&2
    exit 1
fi

mkdir -p -- "$app_dir" "$output"
python3 -m zipfile -e "$code_dir/scenarios.zip" "$app_dir"

site_dir=$(python3 -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')
printf 'import sys; sys.path.insert(0, "%s")\n' "$app_dir" >"$site_dir/00-alphaforge-scenarios.pth"

# Jeu de départ lu par build_data.py (variable prévue par research/backtest).
export ALPHAFORGE_STARTER_DIR="$app_dir/alphaforge/data/starter"

echo "alphaforge scenarios: release=${ALPHAFORGE_RELEASE:-?} run_id=${ALPHAFORGE_RUN_ID:-?}" \
    "python=$(python3 -c 'import sys; print(sys.version.split()[0])')" \
    "image=${ALPHAFORGE_IMAGE:-?}"

cd -- "$app_dir"

# Options du job tirées de request.json (params), déjà citées pour le shell ; vérifiées avant la construction
# des données, qui est longue.
job_args=""
if [ -n "$request" ]; then
    if [ ! -f "$request" ]; then
        echo "error: request file not found: $request" >&2
        exit 1
    fi
    cp -- "$request" "$output/request.json"
    job_args=$(python3 -I - "$request" <<'PY'
import json, shlex, sys

params = json.load(open(sys.argv[1], encoding="utf-8")).get("params") or {}
options = {"config": "--config", "seed": "--seed", "fitted_through": "--fitted-through", "workers": "--workers"}
unknown = sorted(set(params) - set(options))
if unknown:
    sys.exit(f"error: unknown request params: {unknown} (allowed: {sorted(options)})")
print(" ".join(f"{options[k]} {shlex.quote(str(v))}" for k, v in sorted(params.items()) if v is not None))
PY
)
fi

input=/opt/ml/processing/input/data
if [ -f research/backtest/data/build_data.py ]; then
    echo "building long monthly data (research/backtest/data/build_data.py)..."
    python3 -I research/backtest/data/build_data.py
    input="$app_dir/research/backtest/data/processed"
fi

eval "set -- $job_args"
exec python3 -m alphaforge.scenarios.job --input "$input" --output "$output" "$@"
