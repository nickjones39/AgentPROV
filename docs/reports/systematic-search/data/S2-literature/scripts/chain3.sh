set -e
python3 -I pool.py >/dev/null
python3 -I triage.py | tail -1
python3 -I rules.py
python3 -I stage1.py
python3 -I probe5.py | tail -1
bash chain2.sh
python3 - <<'PY'
import webtree3 as w, json
for r in ["SaFo-Lab/DRIFT","leolee99/AgentDyn","xhOwenMa/ROPE","xhOwenMa/AutoDojo","amazon-science/MultiTurnAgentAttack","compsec-snu/adi","agiresearch/ASB"]:
    o,n=r.split("/"); w.survey(o.lower(),n.lower())
json.dump(w.cache,open(w.C,"w")); print("own surveyed")
PY
echo CHAIN3-DONE
