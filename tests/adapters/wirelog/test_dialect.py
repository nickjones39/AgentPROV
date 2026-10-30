"""The ``wirelog.request_response`` reader (docs/architecture D.20.1, D.20.2): sniff, layout and the per-unit plan."""

from __future__ import annotations

import json

import wirelog_support as support

from agentprov.adapters.runner.importer import _AuxListing
from agentprov.adapters.wirelog.dialect import ROOT_FILES, SIBLINGS, WireLogReader, parse_label
from agentprov.adapters.wirelog.wire import detect_variant
from agentprov.ingest.limits import IngestLimits


def test_sniff_detects_both_variants_and_refuses_other_json():
    reader = WireLogReader()
    for crit, variant in (("anthropic_messages", "anthropic-messages"), ("tool_description_hijack", "bedrock-converse")):
        result = reader.sniff(support.member_bytes(support.label_of(crit)), label="", limits=IngestLimits())
        assert result.match and result.variant == variant, crit
    for other in (b"{}", b"[]", json.dumps([{"messages": []}]).encode(), b"not json",
                  support.member_bytes(support.label_of("zero_calls", "request.json"))):
        assert not reader.sniff(other, label="", limits=IngestLimits()).match
    assert detect_variant([{"model": "m", "messages": [], "max_tokens": 1, "inferenceConfig": {}}]) is None


def test_label_grammar_and_plan():
    label = support.label_of("three_result_message")
    facets = parse_label(label)
    assert facets is not None and facets.runs_dir == "runs_named" and facets.arm == "mcptox_p2_toolresult"
    assert parse_label("runs_named/x/meta.json") is None and parse_label("response_raw.json") is None
    assert parse_label("/home/u/dep/" + label) is not None  # a local prefix is tolerated
    labels = [e["label"] for e in support.source_entries()]
    plan = WireLogReader().auxiliary_for(label, _AuxListing(labels, {}))
    assert set(plan) <= set(SIBLINGS) | set(ROOT_FILES)
    assert {"request", "meta", "dispatch", "outcome", "results", "attacks"} <= set(plan)
    assert plan["results"] == "results.csv" and plan["request"].endswith("/request.json")


def test_iter_artefacts_yields_response_logs_only():
    from agentprov.adapters.profiles import load_profile
    from agentprov.adapters.types import CandidateArtefact, Origin

    class Tree:
        def walk(self):
            for e in support.source_entries():
                yield CandidateArtefact(e["label"], e["size"], Origin.member(support.ZIP_SHA256, e["label"], 8, 0, e["size"]))

        def open(self, label, *, max_bytes):  # pragma: no cover - not used
            raise AssertionError

    chosen = [c.label for c in WireLogReader().iter_artefacts(Tree(), load_profile(support.PROFILE))]
    assert chosen == sorted(support.label_of(c) for c in support.F)
