#!/bin/zsh
# D-358 at the building commit (regeneration plan §3.7; D-430): repeat each old corpus's original import at afe7038 on
# the same pinned input (scratch checkouts of the verified fetch cache, or the pristine baseline clone), then
# byte-compare the whole tree with a clone of the stored corpus. One import at a time through the machine queue
# (tools/suite_queue.py --class import). Scratch only: nothing under ~/.agentprov/corpora/ is written.
# Usage: tools/regen/d358_building_commit.sh [name ...]   (default: the seven not yet checked)
# After the round (2026-10-23): the stored corpora are read as <id>-p10.pre-regen.partial (the round's rename), the CPU
# comes from D358_CPU (default 4) and the memory reservation is 2 GiB per CPU (peak RSS 2.7 GiB at 8 workers, AgentDyn).
set -u
REPO=${0:A:h:h:h}
W=$HOME/.agentprov/migration-work/regen-plan
B=$W/build-afe7038
I=$W/inputs
L=$W/logs
C=$HOME/.agentprov/corpora
PY=$REPO/.venv/bin/python
export GIT_NO_LAZY_FETCH=1
ACQ=$HOME/.agentprov/cache/acquisitions.jsonl
CPU=${D358_CPU:-4}
MEM=$(( CPU * 2 ))

typeset -A SRC ARGS
SRC[agentharm]=ast-survey-agentharm-p10;        ARGS[agentharm]="agent-security-tools-survey --snapshot agentharm --input $I/survey --verify-against-pin"
SRC[survey]=ast-survey-agentdojo-p10;           ARGS[survey]="agent-security-tools-survey --snapshot agentdojo-runs --input $I/survey --verify-against-pin"
SRC[adprov]=adprov-v1-release-p10;              ARGS[adprov]="adprov-v1 --input $W/../deferrals/baseline-pristine/corpus/corpus-prov --verify-against-pin"
SRC[d2024]=agentdojo-upstream-2024-06-p10;      ARGS[d2024]="agentdojo --snapshot 2024-06 --fetch --allow-network"  # the original command; network use approved by the user 2026-10-14 (the pin is cached)
SRC[rope]=rope-p10;                             ARGS[rope]="rope --snapshot head --input $I/rope --verify-against-pin"
SRC[head]=agentdojo-upstream-head-p10;          ARGS[head]="agentdojo --snapshot head --input $I/agentdojo-089ed468 --verify-against-pin"
SRC[agentdyn]=agentdyn-a-p10;                   ARGS[agentdyn]="agentdyn --snapshot a --input $I/agentdyn --verify-against-pin"

names=("$@")
[ ${#names} -eq 0 ] && names=(agentharm survey adprov d2024 rope head agentdyn)
for n in $names; do
  out=$W/out/d358-$n
  if [ -f $L/d358-$n.done ]; then echo "skip $n (done)"; continue; fi
  echo "$(date -u +%FT%TZ) queue $n" >> $L/d358.log
  cd $REPO
  # a fresh start never resumes an interrupted tree: it is renamed aside (kept, never deleted)
  for t in $out.partial $out; do
    [ -e $t ] || continue
    aside=$out.interrupted-$(date -u +%Y%m%dT%H%M%SZ); [[ $t == *.partial ]] && aside=$aside.partial
    mv -n $t $aside && [ ! -e $t ] || { echo "cannot rename $t aside"; exit 2; }
    echo "$(date -u +%FT%TZ) $n: existing tree ${t:t} renamed aside to ${aside:t}" >> $L/d358.log
  done
  acq_before=$(shasum -a 256 $ACQ | cut -d' ' -f1)
  $PY -I tools/suite_queue.py --class import --label "regen-plan d358 $n" --cpu $CPU --mem-gib $MEM --run-timeout 0 -- \
    $PY -I tools/regen/measure.py --label d358-$n-import-afe7038 --record $L/runs.jsonl -- \
    $B/.venv/bin/python -m agentprov import ${=ARGS[$n]} --release --jobs $CPU --progress off --corpus $out \
    --summary-json $L/d358-$n-import.json
  rc=$?
  echo "$(date -u +%FT%TZ) import $n rc=$rc" >> $L/d358.log
  [ $rc -ne 0 ] && { echo "import $n failed rc=$rc"; exit $rc; }
  # no download may happen (every pin is cached): the acquisitions log must be unchanged
  if [ "$(shasum -a 256 $ACQ | cut -d' ' -f1)" != "$acq_before" ]; then
    echo "$(date -u +%FT%TZ) STOP $n: acquisitions.jsonl changed" >> $L/d358.log; echo "acquisitions.jsonl changed"; exit 3
  fi
  # the stored corpus is read in place (read-only); the comparison writes only its report. An --input rebuild may differ
  # from the stored corpus in the snapshot origin (the input directory); a --fetch rebuild must match corpus.json too.
  allow=(--allow-pointer '/sources/0/snapshots/0/origin/*' --allow-pointer '/sources/0/snapshots/0/origin')
  [[ ${ARGS[$n]} == *--fetch* ]] && allow=()
  $PY -I tools/regen/tree_compare.py $C/${SRC[$n]}.pre-regen.partial $out.partial --report $L/d358-$n-tree.json $allow
  rc=$?
  echo "$(date -u +%FT%TZ) compare $n rc=$rc" >> $L/d358.log
  if [ $n = rope ]; then
    # pipeline-perf's aer.blob.digest (AER-V35) finding: every re-imported ROPE AER through the afe7038 validator
    : > $L/d358-rope-validate-afe7038.jsonl
    find $out.partial/aer -name '*.aer.jsonl' -print0 | sort -z | xargs -0 -n 500 \
      $B/.venv/bin/python -m agentprov validate --release --store $out.partial/raw --json -q >> $L/d358-rope-validate-afe7038.jsonl
    echo "$(date -u +%FT%TZ) rope afe7038 validator: $(grep -c . $L/d358-rope-validate-afe7038.jsonl) batches" >> $L/d358.log
  fi
  touch $L/d358-$n.done
done
echo "$(date -u +%FT%TZ) ALL DONE" >> $L/d358.log
