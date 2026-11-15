#!/bin/sh
# Construit le paquet de déploiement direct d'AgentCore Runtime (linux/arm64, Python 3.13).
#
#   app/agents/scripts/package.sh <out_dir>
#
# Produit :
#   <out_dir>/agents.zip   main.py et le paquet alphaforge (données de départ et YAML compris, sans les parquets
#                          ni raw/ de alphaforge/data/long) à la racine,
#                          à côté des dépendances verrouillées (uv.lock), installées en roues aarch64-manylinux2014.
#   <out_dir>/agents-portfolio.zip   sauf si ALPHAFORGE_PACKAGE_PORTFOLIO=0 (construit par défaut : le sandbox
#                          active portfolio_enabled; sans lui, Terraform ignore ce zip) : le même code que agents.zip, avec en
#                          plus le groupe uv finance, en roues aarch64-manylinux_2_28 (section 4 bis). Terraform
#                          l'envoie sous runtime/agents-portfolio-<release>.zip pour le seul runtime portfolio.
#   <out_dir>/knowledge/   les fichiers **/*.md de app/knowledge/general/ et leurs éventuels fichiers compagnons
#                          **/*.md.metadata.json de la Knowledge Base (10 Ko au plus, à côté de leur document;
#                          app/CONTRACTS.md section 5.1). Terraform les envoie sous general/.
#   <out_dir>/scenarios/   seulement si ALPHAFORGE_PACKAGE_SCENARIOS=1, ou, si elle est absente, si le tfvars déployé
#                          (infrastructure/deploy/envs/<DEPLOY_ENV>.tfvars, sandbox par défaut) pose
#                          scenarios_enabled = true (donc jamais par défaut quand scenarios_enabled = false) :
#                          bundle du job SageMaker Processing des
#                          scénarios (image scikit-learn d'AWS, Python 3.12, linux/amd64), que Terraform envoie
#                          sous scenarios/code/<release_id>/ (infrastructure/infra/scenarios.tf) :
#                            run.sh          point d'entrée du conteneur (scripts/scenarios-run.sh)
#                            scenarios.zip   alphaforge/__init__.py, alphaforge/scenarios/, le jeu de départ
#                                            (alphaforge/data/starter/), le constructeur des données longues
#                                            (alphaforge/finance/__init__.py et finance/backtest/{__init__,
#                                            build_data,bonds,paths}.py), le catalogue versionné de
#                                            alphaforge/data/long/ (jamais les parquet ni raw/, sous licence),
#                                            et les dépendances figées de scenarios/requirements-job.txt, en
#                                            roues x86_64-manylinux_2_28 pour Python 3.12
#                          Demandé (=1), il échoue bruyamment au moindre manque (job, constructeur, roue, taille).
#
# Le script échoue si une dépendance n'a pas de roue pour la plateforme visée (la plateforme n'est jamais
# changée en silence), ou si le zip dépasse 250 Mo ou son contenu 750 Mo (limites d'AgentCore).
set -eu

PLATFORM=aarch64-manylinux2014
# Zip du runtime portfolio seulement (section 4 bis) : cvxpy n'a pas de roue manylinux2014 pour linux/arm64.
PORTFOLIO_PLATFORM=aarch64-manylinux_2_28
PY_VERSION=3.13
MAX_ZIP_BYTES=250000000
MAX_UNZIPPED_BYTES=750000000

if [ "$#" -ne 1 ] || [ -z "$1" ]; then
    echo "usage: $0 <out_dir>" >&2
    exit 2
fi

# Bundle du job des scénarios (section 6) : 0 ou 1, vérifié avant tout travail. ALPHAFORGE_PACKAGE_SCENARIOS non vide
# l'emporte; absente ou vide, la valeur suit scenarios_enabled du tfvars déployé, seule source de vérité
# (infrastructure/deploy/envs/<DEPLOY_ENV>.tfvars, sandbox par défaut, celui que upload-config.sh envoie à Terraform) :
# true -> 1; false ou clé absente (défaut Terraform false) -> 0; toute autre forme est une erreur.
scenarios_from_tfvars() {
    # Lignes « scenarios_enabled = <v> » hors commentaires (#, //, /* */), espaces et guillemets ignorés.
    # Affiche true, false, none (clé absente), multiple, ou invalid:<v>.
    awk '
        in_block { if (index($0, "*/")) { in_block = 0; sub(/^.*\*\//, "") } else next }
        {
            line = $0
            gsub(/\/\*([^*]|\*+[^*\/])*\*+\//, "", line)
            if (index(line, "/*")) { in_block = 1; sub(/\/\*.*$/, "", line) }
            if (line !~ /^[[:space:]]*scenarios_enabled[[:space:]]*=/) next
            sub(/^[[:space:]]*scenarios_enabled[[:space:]]*=[[:space:]]*/, "", line)
            sub(/[[:space:]]*(#|\/\/).*$/, "", line)
            sub(/[[:space:]]+$/, "", line)
            if (line ~ /^"[^"]*"$/) line = substr(line, 2, length(line) - 2)
            n++
            v = line
        }
        END {
            if (n == 0) print "none"
            else if (n > 1) print "multiple"
            else if (v == "true" || v == "false") print v
            else print "invalid:" v
        }
    ' "$1"
}
if [ -n "${ALPHAFORGE_PACKAGE_SCENARIOS:-}" ]; then
    package_scenarios=$ALPHAFORGE_PACKAGE_SCENARIOS
    scenarios_source="ALPHAFORGE_PACKAGE_SCENARIOS"
else
    scenarios_env=${DEPLOY_ENV:-sandbox}
    case "$scenarios_env" in
        *[!A-Za-z0-9_-]*)
            echo "error: invalid DEPLOY_ENV '$scenarios_env'" >&2
            exit 1
            ;;
    esac
    scenarios_tfvars="$(CDPATH='' cd -- "$(dirname -- "$0")/../../.." && pwd)/infrastructure/deploy/envs/$scenarios_env.tfvars"
    if [ ! -f "$scenarios_tfvars" ]; then
        echo "error: ALPHAFORGE_PACKAGE_SCENARIOS is unset or empty and $scenarios_tfvars was not found (set it to 0 or 1)" >&2
        exit 1
    fi
    case "$(scenarios_from_tfvars "$scenarios_tfvars")" in
        true) package_scenarios=1 ;;
        false | none) package_scenarios=0 ;;
        *)
            echo "error: cannot read scenarios_enabled from $scenarios_tfvars (expected a single" \
                "'scenarios_enabled = true|false'); fix it or set ALPHAFORGE_PACKAGE_SCENARIOS to 0 or 1" >&2
            exit 1
            ;;
    esac
    scenarios_source="scenarios_enabled of infrastructure/deploy/envs/$scenarios_env.tfvars"
fi
case "$package_scenarios" in
    0 | 1) ;;
    *)
        echo "error: ALPHAFORGE_PACKAGE_SCENARIOS must be 0 or 1 (got '$package_scenarios')" >&2
        exit 1
        ;;
esac

# Zip du runtime portfolio (section 4 bis) : 1 (défaut, portfolio_enabled = true en sandbox) ou 0, vérifié avant tout travail.
package_portfolio=${ALPHAFORGE_PACKAGE_PORTFOLIO:-1}
case "$package_portfolio" in
    0 | 1) ;;
    *)
        echo "error: ALPHAFORGE_PACKAGE_PORTFOLIO must be 0 or 1 (got '$package_portfolio')" >&2
        exit 1
        ;;
esac

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

# Sections 1 à 4 pour un zip de runtime : build_runtime_zip <nom> <plateforme> <requirements> <zip>. Pose
# zip_bytes, unzipped_bytes et file_count. Sert à agents.zip et, sur demande, à agents-portfolio.zip.
build_runtime_zip() {
    name=$1
    platform=$2
    requirements_file=$3
    zip_path=$4
    stage="$work/stage-$name"
    mkdir -- "$stage"

    # 1. Dépendances d'exécution, aux versions du verrou.
    echo "Installing locked dependencies of $name for $platform / Python $PY_VERSION (wheels only)..."
    if ! (cd -- "$agents_dir" && uv pip install --quiet \
        --python-platform "$platform" \
        --python-version "$PY_VERSION" \
        --target "$stage" \
        --only-binary=:all: \
        --no-compile-bytecode \
        --no-installer-metadata \
        -r "$requirements_file") >"$work/install-$name.log" 2>&1; then
        cat -- "$work/install-$name.log" >&2
        echo "error: the locked dependencies of $name could not all be installed as wheels for $platform / Python $PY_VERSION." >&2
        echo "       A dependency probably has no wheel for this platform; see the uv output above." >&2
        echo "       The target platform is not changed automatically." >&2
        exit 1
    fi

    # Les scripts de console des dépendances ne servent pas (le point d'entrée est main.py) et leur ligne #!
    # contient un chemin de la machine de construction. Le fichier .lock est celui de uv pour --target. Les tests
    # de pyarrow (zip portfolio seulement) contiennent des fichiers parquet d'exemple, inutiles au runtime.
    rm -rf -- "${stage:?}/bin" "${stage:?}/pyarrow/tests"
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
    for required in alphaforge/profile/questionnaire.yaml alphaforge/profile/skills/client-brain-init/SKILL.md \
        alphaforge/profile/skills/client-brain-update/SKILL.md alphaforge/data/starter/assets_universe.csv \
        alphaforge/data/starter/prices_daily.csv alphaforge/data/starter/fx_usdcad_daily.csv \
        alphaforge/data/market/universe.yaml; do
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
        echo "error: unzipped $name package is $unzipped_bytes bytes, above the $MAX_UNZIPPED_BYTES byte limit (750 MB)" >&2
        exit 1
    fi

    # 4. Archive.
    rm -f -- "$zip_path"
    (cd -- "$stage" && zip -q -r -X "$zip_path" .)
    zip_bytes=$(wc -c <"$zip_path" | tr -d ' ')
    if [ "$zip_bytes" -gt "$MAX_ZIP_BYTES" ]; then
        rm -f -- "$zip_path"
        echo "error: $(basename -- "$zip_path") is $zip_bytes bytes, above the $MAX_ZIP_BYTES byte limit (250 MB); archive removed" >&2
        exit 1
    fi
    file_count=$(find "$stage" -type f | wc -l | tr -d ' ')
}

# 1 à 4. Zip commun des runtimes : dépendances de base seulement (ni dev, ni finance, ni scénarios).
requirements="$work/requirements.txt"
(cd -- "$agents_dir" && uv export --frozen --no-dev --no-hashes --no-emit-project --quiet -o "$requirements")
build_runtime_zip agents "$PLATFORM" "$requirements" "$out_dir/agents.zip"
agents_zip="$zip_path"
agents_zip_bytes=$zip_bytes
agents_unzipped_bytes=$unzipped_bytes
agents_file_count=$file_count

# 4 bis. Zip du runtime portfolio (par défaut; ALPHAFORGE_PACKAGE_PORTFOLIO=0 pour s'en passer) : le même code, plus
#    le groupe uv finance (numpy, pandas, scipy, pyarrow, cvxpy, clarabel, OpenTelemetry). Construit par défaut car
#    app.yml ne pose pas la variable et le sandbox active portfolio_enabled; un zip précédent est toujours retiré.
#    Plateforme : aarch64-manylinux_2_28, et non manylinux2014 comme agents.zip, car cvxpy 1.9.3 (uv.lock) n'a de
#    roue linux/arm64 qu'en manylinux_2_24/2_28 (PyPI, lu le 2026-11-14). Cela suppose un glibc >= 2.28 dans
#    AgentCore Runtime (Amazon Linux 2023 : 2.34; les .so du zip demandent au plus GLIBC_2.28), à vérifier par un
#    health du runtime avant de s'y fier. Mesuré le 2026-11-14 (uv.lock du jour, pyarrow compris, sans ses tests) :
#    167 Mo zippé et 515 Mo décompressé, 10 596 fichiers, sous les limites d'AgentCore (250 Mo et 750 Mo).
portfolio_zip_path="$out_dir/agents-portfolio.zip"
rm -f -- "$portfolio_zip_path"
portfolio_summary="agents-portfolio.zip: skipped (ALPHAFORGE_PACKAGE_PORTFOLIO=$package_portfolio)"
if [ "$package_portfolio" = 1 ]; then
    portfolio_requirements="$work/requirements-portfolio.txt"
    (cd -- "$agents_dir" && uv export --frozen --no-dev --group finance --no-hashes --no-emit-project --quiet \
        -o "$portfolio_requirements")
    build_runtime_zip agents-portfolio "$PORTFOLIO_PLATFORM" "$portfolio_requirements" "$portfolio_zip_path"
    portfolio_summary=$(awk -v z="$zip_bytes" -v u="$unzipped_bytes" -v n="$file_count" -v p="$portfolio_zip_path" \
        -v f="$PORTFOLIO_PLATFORM" 'BEGIN {
        printf "agents-portfolio.zip: %s (%s)\n  %.1f MB zipped (limit 250 MB), %.1f MB unzipped (limit 750 MB), %d files", p, f, z / 1e6, u / 1e6, n
    }')
fi

# 5. Base générale : les documents Markdown et leurs fichiers compagnons de la Knowledge Base, arborescence
#    conservée. Un compagnon sans son document, ou de plus de 10 Ko (limite de Bedrock), est une erreur.
MAX_KB_METADATA_BYTES=10240
rm -rf -- "$out_dir/knowledge"
mkdir -p -- "$out_dir/knowledge"
knowledge_count=0
metadata_count=0
set -f
for rel in $(cd -- "$knowledge_src" && find . -type f \( -name '*.md' -o -name '*.md.metadata.json' \) |
    sed 's|^\./||' | LC_ALL=C sort); do
    case "$rel" in
        *[!A-Za-z0-9._/-]*)
            echo "error: unexpected character in knowledge path: $rel" >&2
            exit 1
            ;;
    esac
    case "$rel" in
        *.md.metadata.json)
            if [ ! -f "$knowledge_src/${rel%.metadata.json}" ]; then
                echo "error: knowledge metadata without its document: $rel" >&2
                exit 1
            fi
            if [ "$(wc -c <"$knowledge_src/$rel" | tr -d ' ')" -gt "$MAX_KB_METADATA_BYTES" ]; then
                echo "error: knowledge metadata above $MAX_KB_METADATA_BYTES bytes: $rel" >&2
                exit 1
            fi
            metadata_count=$((metadata_count + 1))
            ;;
        *) knowledge_count=$((knowledge_count + 1)) ;;
    esac
    mkdir -p -- "$out_dir/knowledge/$(dirname -- "$rel")"
    cp -- "$knowledge_src/$rel" "$out_dir/knowledge/$rel"
    chmod 644 "$out_dir/knowledge/$rel"
done
set +f
find "$out_dir/knowledge" -type d -exec chmod 755 {} +

# 6. Job des scénarios (facultatif : ALPHAFORGE_PACKAGE_SCENARIOS=1, ou scenarios_enabled = true dans le tfvars si la
#    variable est absente). Il ne tourne pas dans AgentCore : autre plateforme (linux/amd64, Python de l'image AWS),
#    et seulement les dépendances du job, jamais celles des runtimes. Sans scénarios (0), le déploiement ne dépend
#    ni de PyPI pour ces roues, ni de la taille du bundle. Demandé, tout manque est une erreur (pas de bundle
#    incomplet) : le job package_agents échoue, et avec lui le déploiement (app.yml, release_tfvars).
SCEN_PLATFORM=x86_64-manylinux_2_28
SCEN_PY_VERSION=3.12
SCEN_MAX_ZIP_BYTES=200000000
scen_src="$agents_dir/src/alphaforge/scenarios"
bt_src="$agents_dir/src/alphaforge/finance/backtest"
scen_out="$out_dir/scenarios"
rm -rf -- "$scen_out"
scen_summary="scenarios: skipped (0 from $scenarios_source)"
if [ "$package_scenarios" = 1 ]; then
    scen_reqs="$scen_src/requirements-job.txt"
    for required in "$scen_src/job.py" "$scen_reqs" "$script_dir/scenarios-run.sh" \
        "$agents_dir/src/alphaforge/finance/__init__.py" "$bt_src/__init__.py" "$bt_src/build_data.py" \
        "$bt_src/bonds.py" "$bt_src/paths.py"; do
        if [ ! -f "$required" ]; then
            echo "error: scenarios packaging requested but $required is missing" >&2
            exit 1
        fi
    done
    if ! command -v git >/dev/null 2>&1 || ! git -C "$agents_dir" rev-parse --git-dir >/dev/null 2>&1; then
        echo "error: scenarios packaging copies alphaforge/data/long from a git checkout (versioned files only)" >&2
        exit 1
    fi
    # Chaque dépendance est figée par == : le job doit être reproductible.
    unpinned=$(sed -e 's/#.*//' -e 's/[[:space:]]//g' -- "$scen_reqs" | awk 'NF && !/==/' || true)
    if [ -n "$unpinned" ]; then
        echo "error: unpinned requirement(s) in $scen_reqs (use ==):" >&2
        echo "$unpinned" >&2
        exit 1
    fi

    scen_stage="$work/scenarios"
    mkdir -p -- "$scen_stage" "$scen_out"
    echo "Scenarios bundle requested (1 from $scenarios_source)."
    echo "Installing scenarios job dependencies for $SCEN_PLATFORM / Python $SCEN_PY_VERSION (wheels only)..."
    if ! (cd -- "$agents_dir" && uv pip install --quiet \
        --python-platform "$SCEN_PLATFORM" \
        --python-version "$SCEN_PY_VERSION" \
        --target "$scen_stage" \
        --only-binary=:all: \
        --no-compile-bytecode \
        --no-installer-metadata \
        -r "$scen_reqs") >"$work/scenarios-install.log" 2>&1; then
        cat -- "$work/scenarios-install.log" >&2
        echo "error: the scenarios job dependencies could not all be installed as wheels for $SCEN_PLATFORM / Python $SCEN_PY_VERSION." >&2
        exit 1
    fi
    rm -rf -- "${scen_stage:?}/bin"
    rm -f -- "$scen_stage/.lock"
    # Suites de tests des dépendances lourdes (celles de pyarrow contiennent des parquet d'exemple) et en-têtes C++ de
    # pyarrow : jamais importés par le job, environ 11 Mo du zip (143 -> 132 Mo, mesuré le 2026-11-15). Aucun .so
    # n'est retiré (chargement dynamique non vérifié dans l'image).
    for pkg in numpy pandas scipy pyarrow; do
        if [ -d "$scen_stage/$pkg" ]; then
            find "$scen_stage/$pkg" -type d -name tests -prune -exec rm -rf {} +
        fi
    done
    rm -rf -- "${scen_stage:?}/pyarrow/include" "${scen_stage:?}/pyarrow/src"
    if [ -e "$scen_stage/alphaforge" ]; then
        echo "error: a dependency already provides alphaforge/ in the scenarios bundle" >&2
        exit 1
    fi
    # Seulement le paquet du job, le jeu de départ et le constructeur des données longues : le job ne peut pas
    # importer les modules des runtimes (Strands, AgentCore) ni le reste du volet finance.
    mkdir -p -- "$scen_stage/alphaforge/finance/backtest" "$scen_stage/alphaforge/data"
    cp -- "$agents_dir/src/alphaforge/__init__.py" "$scen_stage/alphaforge/__init__.py"
    cp -R -- "$scen_src" "$scen_stage/alphaforge/scenarios"
    cp -R -- "$agents_dir/src/alphaforge/data/starter" "$scen_stage/alphaforge/data/starter"
    cp -- "$agents_dir/src/alphaforge/finance/__init__.py" "$scen_stage/alphaforge/finance/__init__.py"
    for mod in __init__ build_data bonds paths; do
        cp -- "$bt_src/$mod.py" "$scen_stage/alphaforge/finance/backtest/$mod.py"
    done
    # Catalogue des données longues (SOURCES.md, assets.csv, ...) : fichiers versionnés seulement, donc jamais
    # les parquet reconstruits ni raw/ (licences Yahoo, Moody's, OCDE), même présents dans un checkout local.
    long_count=0
    set -f
    for rel in $(git -C "$agents_dir" ls-files -- src/alphaforge/data/long); do
        case "$rel" in
            *[!A-Za-z0-9._/-]*)
                echo "error: unexpected character in data/long path: $rel" >&2
                exit 1
                ;;
            *.parquet | src/alphaforge/data/long/raw/*) continue ;;
        esac
        dest="$scen_stage/${rel#src/}"
        mkdir -p -- "$(dirname -- "$dest")"
        cp -- "$agents_dir/$rel" "$dest"
        long_count=$((long_count + 1))
    done
    set +f
    find "$scen_stage" -type d -name __pycache__ -prune -exec rm -rf {} +
    find "$scen_stage" -type f \( -name '*.pyc' -o -name '*.pyo' -o -name '.DS_Store' \) -exec rm -f {} +
    find "$scen_stage" -type d -exec chmod 755 {} +
    find "$scen_stage" -type f -perm -100 -exec chmod 755 {} +
    find "$scen_stage" -type f ! -perm -100 -exec chmod 644 {} +
    # Garde-fou : aucun parquet nulle part dans le bundle, aucun dossier raw/ des données longues.
    leaked=$(find "$scen_stage" \( -name '*.parquet' -o -path '*/data/long/raw' \) -print | head -n 5)
    if [ -n "$leaked" ]; then
        echo "error: licensed data found in the scenarios bundle:" >&2
        echo "$leaked" >&2
        exit 1
    fi

    scen_zip="$scen_out/scenarios.zip"
    (cd -- "$scen_stage" && zip -q -r -X "$scen_zip" .)
    scen_zip_bytes=$(wc -c <"$scen_zip" | tr -d ' ')
    if [ "$scen_zip_bytes" -gt "$SCEN_MAX_ZIP_BYTES" ]; then
        rm -rf -- "$scen_out"
        echo "error: scenarios.zip is $scen_zip_bytes bytes, above $SCEN_MAX_ZIP_BYTES; bundle removed" >&2
        exit 1
    fi
    cp -- "$script_dir/scenarios-run.sh" "$scen_out/run.sh"
    chmod 644 "$scen_out/run.sh"

    scen_summary=$(awk -v z="$scen_zip_bytes" -v n="$long_count" -v p="$scen_out" 'BEGIN {
        printf "scenarios: %s (run.sh, scenarios.zip %.1f MB, %d data/long catalog files)", p, z / 1e6, n
    }')
fi

awk -v z="$agents_zip_bytes" -v u="$agents_unzipped_bytes" -v n="$agents_file_count" -v k="$knowledge_count" \
    -v p="$agents_zip" -v d="$out_dir/knowledge" -v m="$metadata_count" 'BEGIN {
        printf "agents.zip: %s\n  %.1f MB zipped (limit 250 MB), %.1f MB unzipped (limit 750 MB), %d files\n", p, z / 1e6, u / 1e6, n
        printf "knowledge: %s (%d Markdown files, %d metadata files)\n", d, k, m
    }'
echo "$scen_summary"
echo "$portfolio_summary"
