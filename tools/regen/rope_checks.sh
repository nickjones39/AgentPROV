#!/bin/sh
# Rehearsal checks on a re-mapped corpus, one heavy job at a time (regeneration plan §3.3).
# Usage: tools/regen/rope_checks.sh NEW_CORPUS LABEL_PREFIX LOG_DIR
set -u
N="$1"; L="$2"; W="$3"
P="$(pwd)/.venv/bin/python"
M="$P -I $(pwd)/tools/regen/measure.py"
for j in 8 3; do
  $M --label "$L-3-dryrun-new-j$j" --record "$W/runs.jsonl" -- \
    $P -m agentprov recompute --corpus "$N" --dry-run --jobs $j --progress off --summary-json "$W/$L-3-dryrun-new-j$j.json"
done
$M --label "$L-4-validate-strict-sample" --record "$W/runs.jsonl" -- \
  $P -m agentprov validate --corpus "$N" --strict --tiers aer,sem,prov,linkage --sample 2000 --seed 0 --progress off \
  --summary-json "$W/$L-4-validate-strict-sample.json"
$M --label "$L-5-verify-chain" --record "$W/runs.jsonl" -- \
  $P -m agentprov verify --corpus "$N" --level chain --progress off --summary-json "$W/$L-5-verify-chain.json"
echo ALL DONE
