"""Run by ``test_pi_detector_real.py`` in a fresh interpreter whose environment already holds HF_HUB_OFFLINE=1,
TRANSFORMERS_OFFLINE=1 and HF_HUB_CACHE (read when huggingface_hub is first imported). Argument: the offline hub cache.
Prints one JSON object: the instrumented run's decisions and pass messages, and the stock run's messages."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agentprov_backend import defences  # noqa: E402
from agentprov_backend.testing import netguard  # noqa: E402

HF = Path(sys.argv[1])
defences.hf_cache_dir = lambda prefix=None: HF  # the test's provisioned cache instead of <venv>/agentprov_defences/hf
netguard.install()  # loading the classifier must not touch the network

import tempfile  # noqa: E402

from support import pass_message_lists, run_cell  # noqa: E402
from test_defences import BANKING_READ, FINAL, _defended_cell, _stock_run  # noqa: E402

from agentprov_backend.session import serialise_messages  # noqa: E402
from agentprov_backend.testing.scenarios import _agent  # noqa: E402

steps = [{"reply": "tool_calls", "calls": [BANKING_READ]}, FINAL]
out: dict = {}
with tempfile.TemporaryDirectory() as tmp:
    for label, kw in (("attacked", {"attack": "important_instructions", "injection": "injection_task_0"}), ("benign", {})):
        run = run_cell(Path(tmp) / label, _defended_cell("transformers_pi_detector", **kw), _agent(), steps)
        stock = _stock_run("transformers_pi_detector", steps) if label == "benign" else None
        out[label] = {
            "status": run.result.status,
            "errors": [e["data"]["exception"] for e in run.of("error")],
            "decisions": [{k: e["data"].get(k) for k in ("verdict", "reason", "subject")} for e in run.of("decision")],
            "items": run.instrumentation_ids(),
            "weights_item": next((i for i in run.of("instrumentation")[0]["data"]["items"]
                                  if i["id"] == "agentdojo.defence_weights_offline@1"), None),
            "messages": pass_message_lists(run)[-1],
            "stock_messages": json.loads(serialise_messages(stock[0])[0]) if stock is not None else None,
        }
sys.stdout.write(json.dumps(out) + "\n")
