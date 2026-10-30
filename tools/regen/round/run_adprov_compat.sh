#!/bin/zsh
# adprov-v1-release-rg2 (user decision 2026-10-23, option (a), relayed by the orchestrator): add the adprov-v2.3-compat
# regression oracle (R-55, D-37) that corpus-spec.toml names but the round's import does not write. derive at the round's
# own code (5b1f6fdf, the regen-round worktree), never in place: rg1 is read only and kept. No network.
# Checks: tools/regen/compat_derive_check.py (closed world: rg1 plus one compat graph per execution), strict validation
# with the round's four tiers, verify chain.
set -u
REPO=$HOME/Desktop/PhD/Labs/AgentPROV-framework/.claude/worktrees/agentprov-regen-plan-89e815
PIN=5b1f6fdf
T=${0:A:h:h}
L=$HOME/.agentprov/migration-work/regen-plan/logs/round
C=$HOME/.agentprov/corpora
PY=$REPO/.venv/bin/python
ACQ=$HOME/.agentprov/cache/acquisitions.jsonl
CPU=${COMPAT_CPU:-2}
N=adprov-rg2
export GIT_NO_LAZY_FETCH=1

[ "$(git -C $REPO rev-parse HEAD)" = "$(git -C $REPO rev-parse $PIN)" ] || { echo "REPO is not at $PIN"; exit 2; }
[ -z "$(git -C $REPO status --porcelain)" ] || { echo "REPO tree is not clean"; exit 2; }

say() { echo "$(date -u +%FT%TZ) $*" >> $L/round.log; }
q() {  # q CLASS CPU LABEL CMD...
  local cls=$1 cpu=$2 label=$3; shift 3
  $PY -I $REPO/tools/suite_queue.py --class $cls --label "regen-$label" --cpu $cpu --mem-gib $(( cpu * 3 )) \
    --run-timeout 0 -- $PY -I $REPO/tools/regen/measure.py --label $label --record $L/runs.jsonl -- "$@"
  local rc=$?; say "$label rc=$rc"; return $rc
}

old=$C/adprov-v1-release-rg1.partial new=$C/adprov-v1-release-rg2
[ -e $new ] || [ -e $new.partial ] && { say "STOP $N: $new exists"; exit 1; }
say "start: $N at $(git -C $REPO rev-parse --short HEAD), cpu $CPU"
before=$(shasum -a 256 $ACQ | cut -d' ' -f1)
q rehearsal $CPU $N-derive $PY -m agentprov derive --corpus $old --out $new --prov-spec adprov-v2.3-compat \
  --jobs $CPU --progress off --summary-json $L/$N-derive.json || { say "FAIL $N: derive"; exit 1; }
[ "$(shasum -a 256 $ACQ | cut -d' ' -f1)" = "$before" ] || { say "STOP $N: acquisitions.jsonl changed"; exit 3; }
ok=1
q rehearsal 1 $N-check $PY -I $T/compat_derive_check.py $old $new.partial --report $L/$N-check.json || ok=0
q rehearsal $CPU $N-validate $PY -m agentprov validate --corpus $new.partial --strict --tiers aer,sem,prov,linkage \
  --jobs $CPU --progress off --summary-json $L/$N-validate.json || ok=0
q rehearsal 1 $N-verify $PY -m agentprov verify --corpus $new.partial --level chain --progress off \
  --summary-json $L/$N-verify.json
if [ $ok = 1 ]; then say "PASS $N (rg1 kept)"; touch $L/$N.done; else say "FAIL $N (new tree kept)"; exit 1; fi
