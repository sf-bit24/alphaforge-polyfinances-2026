#!/bin/sh
# Construit le paquet de déploiement direct d'AgentCore Runtime (linux/arm64, Python 3.13).
#
#   app/agents/scripts/package.sh <out_dir>
#
# Produit :
#   <out_dir>/agents.zip   main.py et le paquet alphaforge (données de départ et YAML compris, sans les parquets
#                          ni raw/ de alphaforge/data/long) à la racine,
#                          à côté des dépendances verrouillées (uv.lock), installées en roues aarch64-manylinux2014.
#   <out_dir>/knowledge/   les fichiers **/*.md de app/knowledge/general/ (Terraform les envoie sous general/).
#
# Le script échoue si une dépendance n'a pas de roue pour la plateforme visée (la plateforme n'est jamais
# changée en silence), ou si le zip dépasse 250 Mo ou son contenu 750 Mo (limites d'AgentCore).
set -eu

PLATFORM=aarch64-manylinux2014
PY_VERSION=3.13
MAX_ZIP_BYTES=250000000
MAX_UNZIPPED_BYTES=750000000

if [ "$#" -ne 1 ] || [ -z "$1" ]; then
    echo "usage: $0 <out_dir>" >&2
    exit 2
fi

for tool in uv zip find awk; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        echo "error: '$tool' is required but was not found in PATH" >&2
        exit 1
    fi
done

script_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
agents_dir=$(dirname -- "$script_dir")
knowledge_src=$(dirname -- "$agents_dir")/knowledge/general

if [ ! -f "$agents_dir/uv.lock" ] || [ ! -f "$agents_dir/main.py" ] || [ ! -d "$agents_dir/src/alphaforge" ]; then
    echo "error: $agents_dir does not look like the agents project (uv.lock, main.py, src/alphaforge)" >&2
    exit 1
fi
if [ ! -d "$knowledge_src" ]; then
    echo "error: knowledge directory not found: $knowledge_src" >&2
    exit 1
fi

mkdir -p -- "$1"
out_dir=$(CDPATH='' cd -- "$1" && pwd)

work=$(mktemp -d "${TMPDIR:-/tmp}/alphaforge-package.XXXXXX")
trap 'rm -rf -- "$work"' EXIT
trap 'rm -rf -- "$work"; exit 1' HUP INT TERM
stage="$work/stage"
mkdir -- "$stage"

# 1. Dépendances d'exécution, aux versions du verrou.
requirements="$work/requirements.txt"
(cd -- "$agents_dir" && uv export --frozen --no-dev --no-hashes --no-emit-project --quiet -o "$requirements")

echo "Installing locked dependencies for $PLATFORM / Python $PY_VERSION (wheels only)..."
if ! (cd -- "$agents_dir" && uv pip install --quiet \
    --python-platform "$PLATFORM" \
    --python-version "$PY_VERSION" \
    --target "$stage" \
    --only-binary=:all: \
    --no-compile-bytecode \
    --no-installer-metadata \
    -r "$requirements") >"$work/install.log" 2>&1; then
    cat -- "$work/install.log" >&2
    echo "error: the locked dependencies could not all be installed as wheels for $PLATFORM / Python $PY_VERSION." >&2
    echo "       A dependency probably has no wheel for this platform; see the uv output above." >&2
    echo "       The target platform is not changed automatically." >&2
    exit 1
fi

# Les scripts de console des dépendances ne servent pas (le point d'entrée est main.py) et leur ligne #!
# contient un chemin de la machine de construction. Le fichier .lock est celui de uv pour --target.
rm -rf -- "${stage:?}/bin"
rm -f -- "$stage/.lock"

# 2. Code de l'application à la racine du zip.
if [ -e "$stage/main.py" ] || [ -e "$stage/alphaforge" ]; then
    echo "error: a dependency already provides main.py or alphaforge/ at the zip root" >&2
    exit 1
fi
cp -- "$agents_dir/main.py" "$stage/main.py"
cp -R -- "$agents_dir/src/alphaforge" "$stage/alphaforge"
# Données longues du moteur de backtest (alphaforge/data/long) : les parquets reconstruits (licences yfinance,
# Moody's, OCDE : pas de redistribution) et les téléchargements bruts raw/ ne partent jamais dans le zip, même
# s'ils existent dans un checkout local (ils ne sont pas versionnés, donc absents en CI). Seuls le catalogue
# (assets.csv, coverage.csv, qa_overlap.csv, data_version.json) et SOURCES.md restent.
if [ -d "$stage/alphaforge/data/long" ]; then
    rm -rf -- "$stage/alphaforge/data/long/raw"
    find "$stage/alphaforge/data/long" -type f -name '*.parquet' -exec rm -f {} +
fi
for required in alphaforge/profile/questionnaire.yaml alphaforge/data/starter/assets_universe.csv \
    alphaforge/data/starter/prices_daily.csv alphaforge/data/starter/fx_usdcad_daily.csv; do
    if [ ! -f "$stage/$required" ]; then
        echo "error: $required is missing from the package" >&2
        exit 1
    fi
done

# 3. Nettoyage et droits : aucun __pycache__ ni .pyc; 644 pour les fichiers, 755 pour les dossiers et exécutables.
find "$stage" -type d -name __pycache__ -prune -exec rm -rf {} +
find "$stage" -type f \( -name '*.pyc' -o -name '*.pyo' -o -name '.DS_Store' \) -exec rm -f {} +
find "$stage" -type d -exec chmod 755 {} +
find "$stage" -type f -perm -100 -exec chmod 755 {} +
find "$stage" -type f ! -perm -100 -exec chmod 644 {} +

unzipped_bytes=$(find "$stage" -type f -exec wc -c {} + | awk '$2 != "total" { s += $1 } END { printf "%d", s }')
if [ "$unzipped_bytes" -gt "$MAX_UNZIPPED_BYTES" ]; then
    echo "error: unzipped package is $unzipped_bytes bytes, above the $MAX_UNZIPPED_BYTES byte limit (750 MB)" >&2
    exit 1
fi

# 4. Archive.
zip_path="$out_dir/agents.zip"
rm -f -- "$zip_path"
(cd -- "$stage" && zip -q -r -X "$zip_path" .)
zip_bytes=$(wc -c <"$zip_path" | tr -d ' ')
if [ "$zip_bytes" -gt "$MAX_ZIP_BYTES" ]; then
    rm -f -- "$zip_path"
    echo "error: agents.zip is $zip_bytes bytes, above the $MAX_ZIP_BYTES byte limit (250 MB); archive removed" >&2
    exit 1
fi
file_count=$(find "$stage" -type f | wc -l | tr -d ' ')

# 5. Base générale : seuls les documents Markdown, arborescence conservée.
rm -rf -- "$out_dir/knowledge"
mkdir -p -- "$out_dir/knowledge"
knowledge_count=0
set -f
for rel in $(cd -- "$knowledge_src" && find . -type f -name '*.md' | sed 's|^\./||' | LC_ALL=C sort); do
    case "$rel" in
        *[!A-Za-z0-9._/-]*)
            echo "error: unexpected character in knowledge path: $rel" >&2
            exit 1
            ;;
    esac
    mkdir -p -- "$out_dir/knowledge/$(dirname -- "$rel")"
    cp -- "$knowledge_src/$rel" "$out_dir/knowledge/$rel"
    chmod 644 "$out_dir/knowledge/$rel"
    knowledge_count=$((knowledge_count + 1))
done
set +f
find "$out_dir/knowledge" -type d -exec chmod 755 {} +

awk -v z="$zip_bytes" -v u="$unzipped_bytes" -v n="$file_count" -v k="$knowledge_count" -v p="$zip_path" \
    -v d="$out_dir/knowledge" 'BEGIN {
        printf "agents.zip: %s\n  %.1f MB zipped (limit 250 MB), %.1f MB unzipped (limit 750 MB), %d files\n", p, z / 1e6, u / 1e6, n
        printf "knowledge: %s (%d Markdown files)\n", d, k
    }'
