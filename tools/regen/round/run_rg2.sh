#!/bin/zsh
# D-771 re-import (user go 2026-10-23, relayed): ast-survey-agentdojo as -rg2 at d93aa261 (survey-runs@3), same checks as
# the round (D-354 and its addendum), closed-world expectations (D-359). NO rename: -rg1 stays as the evidence copy.
set -u
REPO=$HOME/.agentprov/migration-work/regen-plan/rg2-wt
PIN=d93aa261
R=$HOME/.agentprov/migration-work/regen-plan/round
L=$HOME/.agentprov/migration-work/regen-plan/logs/round
C=$HOME/.agentprov/corpora
PY=$REPO/.venv/bin/python
ACQ=$HOME/.agentprov/cache/acquisitions.jsonl
CPU=${ROUND_CPU:-6}
N=survey-rg2
export GIT_NO_LAZY_FETCH=1

[ "$(git -C $REPO rev-parse HEAD)" = "$(git -C $REPO rev-parse $PIN)" ] || { echo "REPO is not at $PIN"; exit 2; }
[ -z "$(git -C $REPO status --porcelain)" ] || { echo "REPO tree is not clean"; exit 2; }

say() { echo "$(date -u +%FT%TZ) $*" >> $L/round.log; }
q() {  # q CLASS CPU LABEL CMD...
  local cls=$1 cpu=$2 label=$3; shift 3
  # memory reservation capped at MEM_GIB (default 6; orchestrator OK 2026-10-23): the round measured a 1.3 GiB peak for
  # this corpus, and 3 GiB per CPU (18) waited on the 24 GiB budget; the run itself is unchanged
  local mem=$(( cpu * 3 )); [ $mem -gt ${MEM_GIB:-6} ] && mem=${MEM_GIB:-6}
  $PY -I $REPO/tools/suite_queue.py --class $cls --label "regen-rg2 $label" --cpu $cpu --mem-gib $mem \
    --run-timeout 0 -- $PY -I $REPO/tools/regen/measure.py --label $label --record $L/runs.jsonl -- "$@"
  local rc=$?; say "$label rc=$rc"; return $rc
}

new=$C/ast-survey-agentdojo-rg2 old=$C/ast-survey-agentdojo-rg1.partial
[ -e $new ] || [ -e $new.partial ] && { say "STOP $N: $new exists"; exit 1; }
[ -f $L/$N.done ] && { say "skip $N (done)"; exit 0; }
say "start: $N at $(git -C $REPO rev-parse --short HEAD), cpu $CPU"
before=$(shasum -a 256 $ACQ | cut -d' ' -f1)
q import $CPU $N-import $PY -m agentprov import agent-security-tools-survey --snapshot agentdojo-runs --fetch --release \
  --jobs $CPU --progress off --corpus $new --summary-json $L/$N-import.json
if [ "$(shasum -a 256 $ACQ | cut -d' ' -f1)" != "$before" ]; then say "STOP $N: acquisitions.jsonl changed"; exit 3; fi
[ -f $L/$N-import.json ] || { say "STOP $N: no import summary"; exit 1; }
q rehearsal 3 $N-dryrun $PY -m agentprov recompute --corpus $new.partial --dry-run --jobs 3 --progress off \
  --summary-json $L/$N-dryrun.json
q rehearsal $CPU $N-validate $PY -m agentprov validate --corpus $new.partial --strict --tiers aer,sem,prov,linkage \
  --jobs $CPU --progress off --summary-json $L/$N-validate.json
q rehearsal 1 $N-verify $PY -m agentprov verify --corpus $new.partial --level chain --progress off \
  --summary-json $L/$N-verify.json
q rehearsal 4 $N-compare $PY -I $REPO/tools/regen/compare.py --old $old --new $new.partial \
  --report $L/$N-compare.json --expect $R/expect/survey-rg2.json --jobs 4
if $PY -I $R/evaluate.py $L $N 3243 >> $L/round.log; then
  say "PASS $N (no rename: rg1 kept as the evidence copy)"
  touch $L/$N.done
else
  say "FAIL $N (D-356: new tree kept)"; exit 1
fi
