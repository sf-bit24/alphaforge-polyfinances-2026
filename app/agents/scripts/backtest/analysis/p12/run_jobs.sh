#!/usr/bin/env bash
# Runs every engine job of persona 12 (4 in parallel). Usage: bash analysis/p12/run_jobs.sh  (from app/agents/scripts/backtest)
cd "$(dirname "$0")/../.."
i=0
while read -r line; do
  i=$((i+1)); echo "$i $line"
done < analysis/p12/jobs.txt | xargs -P 8 -L 1 bash -c 'n=$0; uv run --group finance python -I -m alphaforge.finance.backtest.run --profile "$@" > results/p12_logs/job_$n.log 2>&1; echo "done $n $@"'
