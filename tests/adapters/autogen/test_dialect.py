"""The ``autogen.runs`` reader (docs/architecture D.19.1, D.19.2; DECISIONS D-300, D-302)."""

from __future__ import annotations

import hashlib
import json

import autogen_support as support
import pytest

from agentprov.adapters.autogen.dialect import AutoGenRunsReader, parse_label, row_reason, row_variant
from agentprov.adapters.types import ArtefactRef
from agentprov.errors import MalformedArtefact
from agentprov.ingest.limits import IngestLimits
from agentprov.raw.origins import Origin

LIMITS = IngestLimits()


def _artefact(data: bytes) -> ArtefactRef:
    return ArtefactRef(id="a0", sha256=hashlib.sha256(data).hexdigest(), bytes=len(data), media="application/jsonl",
                       origin=Origin.member("0" * 64, support.TOOL_ARM, 8, 0, len(data)), role="primary",
                       prov_primary="native")


def test_label_grammar():
    f = parse_label("autogen-guard-placement/results/phase6/tool/runs.jsonl")
    assert f is not None and (f.phase, f.arm, f.prefix) == (6, "tool", "autogen-guard-placement/")
    assert f.directory == "autogen-guard-placement/results/phase6/tool"
    g = parse_label("results/phase12/runs.jsonl")
    assert g is not None and (g.phase, g.arm, g.prefix) == (12, None, "")
    for bad in ("autogen-guard-placement/results/phase2/events.jsonl", "x/phase2/runs.jsonl",
                "autogen-guard-placement/results/p2/runs.jsonl", "results/phase2/a/b/runs.jsonl"):
        assert parse_label(bad) is None, bad


def test_variants_by_key_set():
    base = {"run_id": "r", "phase": 2, "entry": "tool", "error": None, "messages": [], "tool_calls": [], "wall_s": 1.0}
    assert row_variant({**base, "probe_id": "p", "modes": {}, "block_guard": "llm"}) == "team"
    assert row_variant({**base, "probe_id": "p", "modes": {}, "block_guard": "llm", "stop_reason": "x"}) == "team"
    assert row_variant({**base, "case_id": "c", "modes": {}, "block_guard": "llm", "block_at": "tool",
                        "stop_reason": "x"}) == "injecagent"
    assert row_variant({**base, "probe_id": "p", "modes": {}, "condition": "observe", "stop_reason": "x",
                        "termination": "text", "keyword": True, "carrier_id": "c"}) == "condition"
    assert row_variant({**base, "probe_id": "p", "defense": "sandwich", "stop_reason": "x"}) == "defense"
    assert row_variant({**base, "probe_id": "p"}) is None


def test_non_run_rows():
    rail = {"probe_id": "p", "response": "", "backend": None, "history_id": "h", "outcome": "o", "events": [], "wall_s": 1}
    framework = {"probe_id": "p", "framework": "crewai", "result": {}, "returncode": 0, "stderr_tail": "", "wall_s": 1}
    assert row_reason(rail) == "autogen.rail_probe_no_agent"
    assert row_reason(framework) == "autogen.partial_trajectory"
    assert row_reason({"x": 1}) == "autogen.sniff.keys" and row_reason([1]) == "autogen.sniff.not_object"
    reader = AutoGenRunsReader()
    data = (json.dumps(rail) + "\n" + json.dumps(rail) + "\n").encode()
    sniff = reader.sniff(data, label="results/phase7/runs.jsonl", limits=LIMITS)
    assert not sniff.match and sniff.reasons == ("autogen.rail_probe_no_agent",)
    assert reader.register_detail(sniff.reasons) == "autogen.rail_probe_no_agent"
    with pytest.raises(MalformedArtefact):
        list(reader.parse(data, _artefact(data), limits=LIMITS))


def test_one_located_item_per_run_row_with_a_line_locator():
    data, _method = support.fixture_members()[support.TOOL_ARM]
    reader = AutoGenRunsReader()
    sniff = reader.sniff(data, label=support.TOOL_ARM, limits=LIMITS)
    assert sniff.match and sniff.variant == "injecagent"
    items = list(reader.parse(data, _artefact(data), limits=LIMITS))
    assert len(items) == 20 and [i.locator.line for i in items] == list(range(20))
    assert all(i.locator.key() == {"line": i.locator.line} and i.variant == "injecagent" for i in items)


def test_blank_and_bad_lines_are_not_of_the_dialect():
    reader = AutoGenRunsReader()
    assert not reader.sniff(b"{}\n\n{}\n", label="x", limits=LIMITS).match
    assert not reader.sniff(b"not json\n", label="x", limits=LIMITS).match
    assert not reader.sniff(b"", label="x", limits=LIMITS).match


def test_auxiliary_inputs_resolve_against_the_phase_directory_and_the_root():
    class Listing:
        def __init__(self, labels):
            self.labels = set(labels)

        def siblings(self, label):
            return ()

        def exists(self, ref):
            return ref in self.labels

    plan = AutoGenRunsReader().auxiliary_for(support.TOOL_ARM, Listing(support.fixture_members()))
    assert plan == {"events": support.ROOT + "results/phase6/tool/events.jsonl",
                    "guard_raw": support.ROOT + "results/phase6/tool/guard_raw.jsonl",
                    "injecagent_cases": support.ROOT + "data/thirdparty/injecagent_dh.jsonl",
                    "config": support.ROOT + "config.json", "capture": support.ROOT + "results/phase0/capture.json"}


def test_the_staged_deposit_reconciles_with_the_census(staged):
    reader = AutoGenRunsReader()
    runs = rail = framework = 0
    for label, (data, _m) in staged.items():
        if not label.endswith("/runs.jsonl"):
            continue
        sniff = reader.sniff(data, label=label, limits=LIMITS)
        if sniff.match:
            runs += len(list(reader.parse(data, _artefact(data), limits=LIMITS)))
        else:
            rows = data.count(b"\n")
            rail += rows if sniff.reasons == ("autogen.rail_probe_no_agent",) else 0
            framework += rows if sniff.reasons == ("autogen.partial_trajectory",) else 0
    from agentprov.adapters.profiles import load_profile

    census = load_profile(support.PROFILE).family_table()["runs"]
    assert (runs, rail, framework) == (census["runs"], census["rail"], census["framework"]) == (1080, 150, 40)
    assert census["rows"] == runs + rail + framework
