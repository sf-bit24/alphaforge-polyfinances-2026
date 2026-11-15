#!/bin/sh
set -e

# =============================================================================
# Job upload_configuration (.github/workflows/infra.yml), cwd = infrastructure/.
#
# Chaque step GitHub Actions est un shell neuf : les exports de init.sh
# (DEPLOY_ENV, TF_WORKSPACE) seraient perdus entre deux steps. Ce wrapper
# source init.sh puis lance upload-config.sh dans le meme shell.
#
# init.sh est source sans argument : l'env est deduit du run
# (feat-<slug> pour un push feature/*, DEPLOY_ENV sinon).
# =============================================================================

. scripts/init.sh
sh scripts/upload-config.sh
