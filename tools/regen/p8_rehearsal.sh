#!/bin/zsh
# P-8 (regeneration plan §3.5, go-no-go §3.1): route (a) rehearsed at the round's code, on scratch only.
# Each heavy step is one tools/suite_queue.py job (--class import for imports, --class rehearsal for checks), one at a time.
# Old corpora are the APFS clones under $W/src (never ~/.agentprov/corpora). Usage: tools/regen/p8_rehearsal.sh [step ...]
set -u
REPO=${0:A:h:h:h}
W=$HOME/.agentprov/migration-work/regen-plan
L=$W/logs/p8
O=$W/out/p8
EXP=$REPO/docs/reports/regeneration/p8
PY=$REPO/.venv/bin/python
ACQ=$HOME/.agentprov/cache/acquisitions.jsonl
CPU=${P8_CPU:-2}
export GIT_NO_LAZY_FETCH=1
mkdir -p $L $O

q() {  # q CLASS LABEL CMD... : one queued, measured job
  local cls=$1 label=$2; shift 2
  $PY -I $REPO/tools/suite_queue.py --class $cls --label "regen-plan p8 $label" --cpu $CPU --mem-gib $(( CPU * 4 )) \
    --run-timeout 0 -- $PY -I $REPO/tools/regen/measure.py --label p8-$label --record $L/runs.jsonl -- "$@"
  local rc=$?
  echo "$(date -u +%FT%TZ) $label rc=$rc" >> $L/p8.log
  return $rc
}

acq_check() {  # the fetch cache must make no acquisition
  if [ "$(shasum -a 256 $ACQ | cut -d' ' -f1)" != "$1" ]; then
    echo "$(date -u +%FT%TZ) STOP $2: acquisitions.jsonl changed" >> $L/p8.log; exit 3
  fi
}

checks() {  # checks NAME NEWCORPUS OLDCORPUS
  local n=$1 new=$2 old=$3
  q rehearsal $n-dryrun-j3 $PY -m agentprov recompute --corpus $new --dry-run --jobs 3 --progress off \
    --summary-json $L/$n-dryrun-j3.json
  q rehearsal $n-validate $PY -m agentprov validate --corpus $new --strict --tiers aer,sem,prov,linkage --jobs $CPU \
    --progress off --summary-json $L/$n-validate.json
  q rehearsal $n-verify $PY -m agentprov verify --corpus $new --level chain --progress off --summary-json $L/$n-verify.json
  q rehearsal $n-compare $PY -I $REPO/tools/regen/compare.py --old $old --new $new --report $L/$n-compare.json \
    --expect $EXP/$n.expect.json --jobs $CPU
}

imp() {  # imp NAME CORPUSDIR ARGS...
  local n=$1 dir=$2; shift 2
  local before=$(shasum -a 256 $ACQ | cut -d' ' -f1)
  q import $n-import $PY -m agentprov import "$@" --release --jobs $CPU --progress off --corpus $dir \
    --summary-json $L/$n-import.json || return 1
  acq_check $before $n
}

steps=("$@")
[ ${#steps} -eq 0 ] && steps=(mandate rope agentharm gated)
for s in $steps; do
  [ -f $L/$s.done ] && { echo "skip $s (done)"; continue; }
  echo "$(date -u +%FT%TZ) start $s" >> $L/p8.log
  case $s in
    mandate)
      imp mandate $O/mandate mandate-agentdojo-eval --snapshot head --fetch || exit 1
      checks mandate $O/mandate.partial $W/src/mandate-agentdojo-eval-p10.partial ;;
    rope)
      imp rope $O/rope rope --snapshot head --fetch || exit 1
      checks rope $O/rope.partial $W/src/rope-p10.partial ;;
    agentharm)
      imp agentharm $O/agentharm agent-security-tools-survey --snapshot agentharm --fetch || exit 1
      q rehearsal agentharm-compare $PY -I $REPO/tools/regen/compare.py --old $HOME/.agentprov/corpora/ast-survey-agentharm-p10.partial \
        --new $O/agentharm.partial --report $L/agentharm-compare.json --expect $EXP/agentharm.expect.json --jobs $CPU ;;
    gated)
      q rehearsal gate-d-golden $PY -m agentprov migrate gate-d --scope golden --progress off --summary-json $L/gate-d-golden.json ;;
  esac
  touch $L/$s.done
done
echo "$(date -u +%FT%TZ) ALL DONE" >> $L/p8.log
