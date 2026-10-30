"""SECURITY, regeneration-batch item 132 (bug pass new-families NF-10, NF-11; routed R-NF-3): the agentdojo and Inspect
redaction modules fail closed. A zero-width pattern or a label that still holds the matched span is a profile defect,
never a pointer reported as redacted; and an observed string stored as ``{"$utf16": ...}`` (a lone surrogate, C.11.4) is
redacted inside its encoding. Made-up accounts only."""

from __future__ import annotations

import base64
import json
from typing import Any

import pytest
import test_rescont as T

from agentprov.adapters.agentdojo.redact import Redactor, parse_redact_rules, redact_value
from agentprov.adapters.inspect import redact as inspect_redact
from agentprov.errors import ProfileError

ACCT = "zzacct"


def _utf16_hits(value: Any, account: str) -> list[str]:
    hits: list[str] = []

    def walk(node: Any, ptr: str) -> None:
        if isinstance(node, dict):
            if set(node) == {"$utf16"}:
                if account in base64.b64decode(node["$utf16"]).decode("utf-16-be", "surrogatepass"):
                    hits.append(ptr)
            for k, v in node.items():
                walk(v, f"{ptr}/{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{ptr}/{i}")

    walk(value, "")
    return hits


@pytest.mark.parametrize("pattern", [r"(?=/scratch/)", r"(?<=/scratch/)(?=[^/]+/)", r"\b(?=scratch)"])
def test_a_zero_width_pattern_fails_closed(pattern):
    rules = parse_redact_rules([{"id": "r", "scope": "model_id", "pattern": pattern, "replacement": "scratch:{span12}"}], "t")
    with pytest.raises(ProfileError, match="zero-width"):
        redact_value(rules, "model_id", f"/scratch/{ACCT}/models/qwen", salt="p")


def test_the_leaf_fallback_never_returns_a_slashless_span():
    rules = parse_redact_rules([{"id": "h", "scope": "pipeline_name", "pattern": r"^_ceph_ssd_students_[^/]+_qwen3_5(?:-[0-9]+B)?$",
                                 "leaf": r"[A-Za-z0-9_.-]+", "replacement": "home:{span12}/{leaf}"}], "t")
    label, rid = redact_value(rules, "pipeline_name", f"_ceph_ssd_students_{ACCT}_qwen3_5-2B", salt="p")
    assert rid == "h" and ACCT not in label and label.endswith("/?")


def test_a_label_that_keeps_the_span_fails_closed():
    rules = parse_redact_rules([{"id": "k", "scope": "model_id", "pattern": r"/scratch/(?P<span>[^/]+)/(?P<leaf>[^/]+)",
                                 "replacement": "{leaf}"}], "t")
    with pytest.raises(ProfileError, match="still holds"):
        redact_value(rules, "model_id", f"/scratch/{ACCT}/{ACCT}", salt="p")


def test_the_r10j1_rule_is_unchanged():
    rules = parse_redact_rules([{"id": "p", "scope": "pipeline_name",
                                 "pattern": r"^_ceph_ssd_students_(?P<span>[^_/]+)_(?P<leaf>qwen3_5(?:-[0-9]+B)?)$",
                                 "replacement": "_ceph_ssd_students_{span12}_{leaf}"}], "t")
    label, rid = redact_value(rules, "pipeline_name", f"_ceph_ssd_students_{ACCT}_qwen3_5-2B", salt="p")
    assert rid == "p" and ACCT not in label and label.endswith("_qwen3_5-2B")


def test_a_lone_surrogate_model_string_is_redacted_inside_its_encoding():
    raw = json.dumps(T.container(model=T.CLUSTER_LLAMA + "\ud800"), indent=2, ensure_ascii=True).encode()
    m = T.map_all(raw)[0]
    records = [json.loads(line) for line in m.data.decode().splitlines() if line.strip()]
    assert _utf16_hits(records, T.ACCOUNT) == [] and T.ACCOUNT.encode() not in m.data
    assert "rescont.value_redacted" in m.codes


def test_the_agentdojo_redactor_rewrites_a_utf16_value():
    rules = parse_redact_rules([{"id": "p", "scope": "pipeline_name", "pattern": r"^_ceph_ssd_students_(?P<span>[^_/]+)_q$",
                                 "replacement": "_ceph_ssd_students_{span12}_q"}], "t")
    name = f"_ceph_ssd_students_{ACCT}_q"
    record = {"ext": {"x": {"$utf16": base64.b64encode(f"{name} \ud800".encode("utf-16-be", "surrogatepass")).decode()}}}
    done = Redactor("p", 1, rules, {"pipeline_name": [name]}).apply(record, lambda p: "rescont.value_redacted@1")
    assert done and _utf16_hits(record, ACCT) == []


# ------------------------------------------------------------------------------------------------ the Inspect module
def test_the_inspect_redactor_fails_closed_and_reads_utf16():
    rules = inspect_redact.parse_redact_rules([{"id": "z", "scope": "harness_text", "pattern": r"(?<=/Users/)(?=[^/]+/)",
                                                "replacement": "<account>"}], "t")
    redactor = inspect_redact.Redactor("p", 1, rules, [])
    with pytest.raises(ProfileError, match="zero-width"):
        redactor.apply({"k": "scope", "ext": {"inspect": {"error": f"/Users/{ACCT}/x.py"}}}, lambda p: "r")
    good = inspect_redact.parse_redact_rules([{"id": "h", "scope": "harness_text", "pattern": r'(?<=/Users/)[^/\s"]+(?=/)',
                                               "replacement": "<account>"}], "t")
    encoded = base64.b64encode(f"File /Users/{ACCT}/x.py \ud800".encode("utf-16-be", "surrogatepass")).decode()
    record = {"k": "scope", "ext": {"inspect": {"error": {"$utf16": encoded}}}}
    assert inspect_redact.Redactor("p", 1, good, []).apply(record, lambda p: "r")
    assert _utf16_hits(record, ACCT) == []
