#!/bin/zsh
# The round's gate chain (D-354 addendum 2026-10-22; user OK for the gate D fix): G0 -> A -> B -> D -> E, full scope,
# release mode, run from the gate-fix worktree at f0410684 (stage digests equal 5b1f6fdf, the round's commit), on the
# regenerated 2024-06 (native) and adprov-v1 (release) corpora. The converted tree has no stored AERs (D-49).
set -u
G=$HOME/.agentprov/migration-work/regen-plan/gatefix-wt
L=$HOME/.agentprov/migration-work/regen-plan/logs/round
C=$HOME/.agentprov/corpora
PY=$G/.venv/bin/python
CPU=${ROUND_CPU:-8}
RD=$L/gates-f0410684
export GIT_NO_LAZY_FETCH=1
export AGENTPROV_BASELINE_CORPUS=$HOME/.agentprov/migration-work/deferrals/baseline-pristine
export AGENTPROV_BASELINE_WHEEL=$HOME/.agentprov/baseline/venv-579a908/wheel/agentdojo_prov-1.0.0-py3-none-any.whl
[ "$(git -C $G rev-parse HEAD)" = "$(git -C $G rev-parse f0410684)" ] || { echo "gate worktree is not at f0410684"; exit 2; }
[ -z "$(git -C $G status --porcelain)" ] || { echo "gate worktree is not clean"; exit 2; }
say() { echo "$(date -u +%FT%TZ) $*" >> $L/round.log; }
q() {
  local label=$1; shift
  $PY -I $G/tools/suite_queue.py --class rehearsal --label "regen-round $label" --cpu $CPU --mem-gib $(( CPU * 3 )) \
    --run-timeout 0 -- $PY -I $G/tools/regen/measure.py --label $label --record $L/runs.jsonl -- "$@"
  local rc=$?; say "$label rc=$rc"; return $rc
}
say "gates at $(git -C $G rev-parse --short HEAD): G0 A B D E"
for g in G0 A B; do
  q gate-$g-f04 $PY -m agentprov migrate gate $g --scope full --release --reports-dir $RD --progress off || { say "FAIL gate-$g (f0410684)"; exit 1; }
done
q gate-D-f04 $PY -m agentprov migrate gate-d --scope full --release --workers $CPU \
  --corpus $C/agentdojo-upstream-2024-06-rg1.partial --corpus $C/adprov-v1-release-rg1.partial --accept-gap converted \
  --reports-dir $RD --progress off || { say "FAIL gate-D (f0410684)"; exit 1; }
q gate-E-f04 $PY -m agentprov migrate gate-e --scope full --release --workers $CPU --reports-dir $RD --progress off \
  || { say "FAIL gate-E (f0410684)"; exit 1; }
say "PASS gates G0 A B D E at f0410684"
touch $L/gates.done
