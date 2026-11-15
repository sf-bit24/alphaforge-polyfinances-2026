#!/bin/sh
# Point d'entrée du job SageMaker Processing des scénarios (image scikit-learn d'AWS, Python 3.12, linux/amd64).
#
# Copié par package.sh dans infra/build/scenarios/run.sh, puis envoyé par Terraform sous
# scenarios/code/<release_id>/ ; SageMaker le place dans /opt/ml/processing/input/code/ et le lance par
#   /bin/sh /opt/ml/processing/input/code/run.sh --request <request.json> --output <dossier>
# (arguments posés par la machine Step Functions, infrastructure/infra/scenarios.tf).
#
# 1. Extrait scenarios.zip dans /opt/ml/processing/app : alphaforge/ (scenarios, jeu de départ, constructeur
#    des données longues alphaforge.finance.backtest.build_data et catalogue de data/long sans parquet) et les
#    dépendances figées de requirements-job.txt.
# 2. Place ce dossier EN TÊTE de sys.path par un fichier .pth du site-packages de l'image. Un .pth reste lu sous
#    « python -I » (qui ignore PYTHONPATH), mode imposé au constructeur ; les dépendances figées passent donc
#    avant celles de l'image, dans tous les processus Python du job.
# 3. « ALPHAFORGE_BT_DATA=<volume>/long python3 -I -m alphaforge.finance.backtest.build_data » reconstruit les
#    données mensuelles depuis les sources publiques (accès Internet), dans le volume du job seulement, hors de
#    app/ et des sorties. Constructeur absent du bundle : erreur (package.sh ne doit pas le permettre).
# 4. Traduit params de request.json en options du job (config, seed, fitted_through, workers ; toute autre clé
#    est refusée), copie request.json dans les sorties, puis exécute
#    « python3 -m alphaforge.scenarios.job --input $ALPHAFORGE_BT_DATA ».
#
# Essai local seulement : SCENARIOS_APP_DIR (dossier d'extraction), ALPHAFORGE_BT_DATA (dossier des données)
# et SCENARIOS_SKIP_BUILD=1 (réutilise les parquet déjà présents dans ALPHAFORGE_BT_DATA).
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

# Jeu de départ lu par le constructeur (alphaforge.finance.backtest.paths.starter_dir).
export ALPHAFORGE_STARTER_DIR="$app_dir/alphaforge/data/starter"
# Données longues reconstruites : volume du job, hors de app/ et de $output (jamais envoyées dans S3).
export ALPHAFORGE_BT_DATA="${ALPHAFORGE_BT_DATA:-/opt/ml/processing/work/long}"

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

doc = json.load(open(sys.argv[1], encoding="utf-8"))
if isinstance(doc, str):  # ancien marqueur encode deux fois par Step Functions
    doc = json.loads(doc)
if not isinstance(doc, dict):
    sys.exit("error: request.json is not a JSON object")
params = doc.get("params") or {}
options = {"config": "--config", "seed": "--seed", "fitted_through": "--fitted-through", "workers": "--workers"}
unknown = sorted(set(params) - set(options))
if unknown:
    sys.exit(f"error: unknown request params: {unknown} (allowed: {sorted(options)})")
print(" ".join(f"{options[k]} {shlex.quote(str(v))}" for k, v in sorted(params.items()) if v is not None))
PY
)
fi

if [ "${SCENARIOS_SKIP_BUILD:-0}" = 1 ]; then
    echo "SCENARIOS_SKIP_BUILD=1: reusing $ALPHAFORGE_BT_DATA (local trial only)"
else
    if [ ! -f "$app_dir/alphaforge/finance/backtest/build_data.py" ]; then
        echo "error: alphaforge/finance/backtest/build_data.py is missing from scenarios.zip" >&2
        exit 1
    fi
    mkdir -p -- "$ALPHAFORGE_BT_DATA"
    echo "building long monthly data (alphaforge.finance.backtest.build_data -> $ALPHAFORGE_BT_DATA)..."
    python3 -I -m alphaforge.finance.backtest.build_data
fi

eval "set -- $job_args"
exec python3 -m alphaforge.scenarios.job --input "$ALPHAFORGE_BT_DATA" --output "$output" "$@"
