"""``transformers_pi_detector`` with the real classifier (D-672; opt-in: the pinned weights must be in the fetch cache).

The pinned files are linked from the fetch cache (``url/<sha256>``) into a temporary offline hub cache, and a fresh
interpreter runs the defended cell with HF_HUB_OFFLINE=1, TRANSFORMERS_OFFLINE=1 and the network guard: the
important_instructions payload is redacted with a ``redact`` decision that keeps the classifier's score, the benign
output gets the decision its observed label gives, with the score (D-673), and the instrumented benign run equals the
stock one.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from agentprov_backend.defences import resolve

CACHE = Path(os.environ.get("AGENTPROV_UPSTREAM_CACHE") or Path(os.environ.get("AGENTPROV_HOME") or Path.home()
                                                                 / ".agentprov") / "cache")


def _hub(tmp_path: Path) -> Path:
    entry = resolve("transformers_pi_detector", "agentdojo")
    (weights,) = entry.weights
    org, name = weights["repo"].split("/", 1)
    model = tmp_path / "hf" / f"models--{org}--{name}"
    snap = model / "snapshots" / weights["revision"]
    snap.mkdir(parents=True)
    for f in weights["files"]:
        cached = CACHE / "url" / f["sha256"]
        if not cached.is_file():
            pytest.skip(f"the pinned weights file {f['path']} is not in the fetch cache ({cached})")
        (snap / f["path"]).symlink_to(cached)
    (model / "refs").mkdir()
    (model / "refs" / "main").write_text(weights["revision"])
    return tmp_path / "hf"


def test_the_real_classifier_redacts_the_payload_and_allows_benign_output(tmp_path):
    pytest.importorskip("torch")
    pytest.importorskip("transformers")
    hub = _hub(tmp_path)
    env = {**os.environ, "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "HF_HUB_CACHE": str(hub),
           "HF_HUB_DISABLE_TELEMETRY": "1", "TOKENIZERS_PARALLELISM": "false"}
    inner = Path(__file__).with_name("pi_real_inner.py")
    proc = subprocess.run([sys.executable, str(inner), str(hub)], capture_output=True, text=True, env=env, timeout=900,
                          check=False, cwd=inner.parent)
    assert proc.returncode == 0, proc.stderr[-4000:]
    out = json.loads(proc.stdout.strip().splitlines()[-1])
    attacked, benign = out["attacked"], out["benign"]
    assert attacked["status"] == "complete" and not attacked["errors"], attacked["errors"]
    (d,) = attacked["decisions"]
    assert d["verdict"] == "redact" and d["reason"].startswith("is_injection=True score=")
    assert attacked["messages"][3]["content"][0]["content"] == "<Data omitted because a prompt injection was detected>"
    # the benign output: whatever the classifier decides, the verdict follows its observed label (on banking
    # user_task_1 at revision 90c9989b it flags the benign transaction list too: a false positive the record shows)
    (b,) = benign["decisions"]
    assert (b["verdict"], b["reason"].split(" ")[0]) in (("allow", "is_injection=False"), ("redact", "is_injection=True"))
    assert benign["messages"] == benign["stock_messages"]  # instrumented == stock with the real classifier
    item = attacked["weights_item"]
    assert item is not None and item["params"]["revision"] == resolve("transformers_pi_detector", "agentdojo").weights[0]["revision"]
    assert item["params"]["device"] == "cpu"
