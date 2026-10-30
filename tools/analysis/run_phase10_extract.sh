#!/bin/sh
# Run the phase-10 feature extraction over the five completed phase-10 corpora (read-only), 4 workers each,
# sequentially. Usage: tools/analysis/run_phase10_extract.sh OUTDIR
set -eu
out="${1:?usage: run_phase10_extract.sh OUTDIR}"
here="$(cd "$(dirname "$0")/../.." && pwd)"
py="$here/.venv/bin/python"
corpora="${AGENTPROV_HOME:-$HOME/.agentprov}/corpora"
mkdir -p "$out"
for c in mandate-agentdojo-eval-p10 ast-survey-agentdojo-p10 rope-p10 agentdojo-upstream-head-p10 agentdyn-a-p10; do
  "$py" "$here/tools/analysis/phase10_extract.py" --corpus "$corpora/$c.partial" --out "$out/$c.jsonl" --jobs 4
done
echo "all done"
