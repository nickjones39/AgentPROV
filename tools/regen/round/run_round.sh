#!/bin/zsh
# The regeneration round (user yes 2026-10-22; D-350..D-357): scope A, pinned commit 5b1f6fdf, worktree branch regen-round.
# One queued job at a time. A failed check stops the round (D-356): the new tree stays, the old corpus is not renamed.
# Usage: run_round.sh [name ...]   (default: the plan order). Resumable by name markers in $L/<name>.done.
set -u
REPO=$HOME/Desktop/PhD/Labs/AgentPROV-framework/.claude/worktrees/agentprov-regen-plan-89e815
R=$HOME/.agentprov/migration-work/regen-plan/round
L=$HOME/.agentprov/migration-work/regen-plan/logs/round
C=$HOME/.agentprov/corpora
PY=$REPO/.venv/bin/python
ACQ=$HOME/.agentprov/cache/acquisitions.jsonl
CPU=${ROUND_CPU:-8}
export GIT_NO_LAZY_FETCH=1
HERE=${0:A:h}  # this driver's folder (inside a function $0 is the function name)

# the pinned code: refuse to run anywhere else
[ "$(git -C $REPO rev-parse HEAD)" = "$(git -C $REPO rev-parse 5b1f6fdf)" ] || { echo "REPO is not at 5b1f6fdf"; exit 2; }
[ -z "$(git -C $REPO status --porcelain)" ] || { echo "REPO tree is not clean"; exit 2; }

typeset -A ID N ARGS
ID[mandate]=mandate-agentdojo-eval;   N[mandate]=396;    ARGS[mandate]="mandate-agentdojo-eval --snapshot head --fetch"
ID[agentharm]=ast-survey-agentharm;   N[agentharm]=1056; ARGS[agentharm]="agent-security-tools-survey --snapshot agentharm --fetch"
ID[survey]=ast-survey-agentdojo;      N[survey]=3243;    ARGS[survey]="agent-security-tools-survey --snapshot agentdojo-runs --fetch"
ID[adprov]=adprov-v1-release;         N[adprov]=17664;   ARGS[adprov]="adprov-v1 --snapshot release --input $HOME/.agentprov/migration-work/deferrals/baseline-pristine/corpus/corpus-prov --verify-against-pin"
ID[d2024]=agentdojo-upstream-2024-06; N[d2024]=18241;    ARGS[d2024]="agentdojo --snapshot 2024-06 --fetch"
ID[rope]=rope;                        N[rope]=10791;     ARGS[rope]="rope --snapshot head --fetch"
ID[head]=agentdojo-upstream-head;     N[head]=36679;     ARGS[head]="agentdojo --snapshot head --fetch"
ID[agentdyn]=agentdyn-a;              N[agentdyn]=38281; ARGS[agentdyn]="agentdyn --snapshot a --fetch"

say() { echo "$(date -u +%FT%TZ) $*" >> $L/round.log; }
q() {  # q CLASS CPU LABEL CMD...
  local cls=$1 cpu=$2 label=$3; shift 3
  $PY -I $REPO/tools/suite_queue.py --class $cls --label "regen-round $label" --cpu $cpu --mem-gib $(( cpu * 3 )) \
    --run-timeout 0 -- $PY -I $REPO/tools/regen/measure.py --label $label --record $L/runs.jsonl -- "$@"
  local rc=$?; say "$label rc=$rc"; return $rc
}

corpus() {
  local n=$1 id=${ID[$1]} new=$C/${ID[$1]}-rg1 old=$C/${ID[$1]}-p10.partial
  local before=$(shasum -a 256 $ACQ | cut -d' ' -f1)
  q import $CPU $n-import $PY -m agentprov import ${=ARGS[$n]} --release --jobs $CPU --progress off --corpus $new \
    --summary-json $L/$n-import.json
  if [ "$(shasum -a 256 $ACQ | cut -d' ' -f1)" != "$before" ]; then say "STOP $n: acquisitions.jsonl changed"; exit 3; fi
  [ -f $L/$n-import.json ] || { say "STOP $n: no import summary"; exit 1; }
  local tiers=aer,sem,prov,linkage  # D-354 addendum 2026-10-22: no regression tier in validate --corpus; gates A/B cover it
  q rehearsal 3 $n-dryrun $PY -m agentprov recompute --corpus $new.partial --dry-run --jobs 3 --progress off \
    --summary-json $L/$n-dryrun.json
  q rehearsal $CPU $n-validate $PY -m agentprov validate --corpus $new.partial --strict --tiers $tiers --jobs $CPU \
    --progress off --summary-json $L/$n-validate.json
  q rehearsal 1 $n-verify $PY -m agentprov verify --corpus $new.partial --level chain --progress off \
    --summary-json $L/$n-verify.json
  q rehearsal 4 $n-compare $PY -I $REPO/tools/regen/compare.py --old $old --new $new.partial \
    --report $L/$n-compare.json --expect $R/expect/$n.json --jobs 4
  if $PY -I $R/evaluate.py $L $n ${N[$n]} >> $L/round.log; then
    say "PASS $n"
    local renamed=$C/${ID[$n]}-p10.pre-regen.partial
    if [ -e $renamed ]; then say "STOP $n: $renamed exists"; exit 1; fi
    mv $old $renamed && say "renamed $(basename $old) -> $(basename $renamed)"
    # adprov-v1's corpus-spec.toml names two prov specs; import writes only agentprov-prov/0.1, so the
    # adprov-v2.3-compat regression oracle (R-55) is derived into -rg2 before the corpus counts as done (2026-10-23)
    if [ $n = adprov ]; then
      zsh $HERE/run_adprov_compat.sh || { say "FAIL $n: adprov-v2.3-compat derive (rg1 kept)"; exit 1; }
    fi
    touch $L/$n.done
  else
    say "FAIL $n (D-356: new tree kept, old corpus not renamed)"; exit 1
  fi
}

gates() {  # AD-07 chain G0 -> A -> B -> D -> E at full scope, release mode (D-354 addendum 2026-10-22)
  export AGENTPROV_BASELINE_CORPUS=$HOME/.agentprov/migration-work/deferrals/baseline-pristine
  export AGENTPROV_BASELINE_WHEEL=$HOME/.agentprov/baseline/venv-579a908/wheel/agentdojo_prov-1.0.0-py3-none-any.whl  # J.1.6 wheel; G0 checks its hash against the lock
  local g
  for g in G0 A B; do
    q rehearsal $CPU gate-$g $PY -m agentprov migrate gate $g --scope full --release --reports-dir $L/gates \
      --progress off || { say "FAIL gate-$g"; exit 1; }
  done
  q rehearsal $CPU gate-D $PY -m agentprov migrate gate-d --scope full --release --workers $CPU \
    --corpus $C/agentdojo-upstream-2024-06-rg1.partial --corpus $C/adprov-v1-release-rg1.partial \
    --reports-dir $L/gates --progress off || { say "FAIL gate-D"; exit 1; }
  q rehearsal $CPU gate-E $PY -m agentprov migrate gate-e --scope full --release --workers $CPU \
    --reports-dir $L/gates --progress off || { say "FAIL gate-E"; exit 1; }
  say "PASS gates G0 A B D E"
  touch $L/gates.done
}

names=("$@")
[ ${#names} -eq 0 ] && names=(mandate agentharm survey adprov d2024 gates rope head agentdyn)
say "start: ${names[*]} at $(git -C $REPO rev-parse --short HEAD), cpu $CPU"
for n in $names; do
  [ -f $L/$n.done ] && { say "skip $n (done)"; continue; }
  if [ $n = gates ]; then gates; else corpus $n; fi
done
say "ALL DONE"
