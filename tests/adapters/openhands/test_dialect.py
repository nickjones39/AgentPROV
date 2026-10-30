"""The ``openhands.events`` reader (docs/architecture D.17.1, D.17.2): sniff, variants, path grammars, auxiliary plans."""

from __future__ import annotations

import json

import openhands_support as support
import pytest

from agentprov.adapters.openhands.dialect import OAS, REDCODE, OpenHandsEventsReader, parse_path
from agentprov.adapters.runner.importer import _AuxListing
from agentprov.ingest.limits import IngestLimits

LIMITS = IngestLimits()


def _sniff(value: object):
    return OpenHandsEventsReader().sniff(json.dumps(value).encode(), label="x.json", limits=LIMITS)


def _event(eid: int, **kw: object) -> dict[str, object]:
    return {"id": eid, "timestamp": "2026-01-01T00:00:00.000001", "source": "agent", **kw}


def test_variants_come_from_the_event_vocabulary():
    oas = _sniff([_event(0, action="message", args={"content": "x"}), _event(1, observation="run", content="", cause=0)])
    assert (oas.match, oas.variant) == (True, "oas-0.28")
    oh = _sniff([_event(0, action="system", args={"content": "s", "openhands_version": "1.5.0"}), _event(1, action="finish", args={})])
    assert (oh.match, oh.variant) == (True, "oh-1.5")


@pytest.mark.parametrize(("value", "reason"), [
    ({"a": 1}, "openhands.sniff.not_array"),
    ([], "openhands.sniff.empty"),
    ([{"id": 0, "timestamp": "t"}], "openhands.sniff.event_shape"),
    ([_event(0, action="x", observation="y")], "openhands.sniff.event_shape"),
    ([_event(0, action="message", args={}), _event(1, action="system", args={"openhands_version": "1.5.0"})],
     "openhands.sniff.variant"),
    ([_event(0, action="system", args={"content": "s"})], "openhands.sniff.variant"),
])
def test_foreign_or_unknown_input_is_not_a_match(value, reason):
    result = _sniff(value)
    assert not result.match and reason in result.reasons


def test_bytes_that_fail_the_strict_loader_give_the_ingest_reason():
    result = OpenHandsEventsReader().sniff(b'[{"id": 0, "id": 1}]', label="x.json", limits=LIMITS)
    assert not result.match and result.reasons[0].startswith("ingest.")


def test_an_empty_list_is_registered_as_a_non_execution():
    assert OpenHandsEventsReader.register_detail(("openhands.sniff.empty",)) == "openhands.empty_event_list"
    assert OpenHandsEventsReader.register_detail(("openhands.sniff.not_array",)) is None


def test_path_grammars():
    oas = parse_path("prefix/evaluation/gpt-4o/traj_safety-x.json")
    assert oas is not None and (oas.source, oas.model, oas.task, oas.prefix) == (OAS, "gpt-4o", "safety-x", "prefix/")
    rc = parse_path("results/OH/qwen3-coder-30b-a3b/S1/bash/trajectory/oh_18_10_sh_S1-3b57f5.json")
    assert rc is not None and rc.source == REDCODE and (rc.target, rc.language, rc.case_key, rc.case_hash) == ("S1", "bash", "18_10", "3b57f5")
    assert parse_path("results/OH/m/S1/python/trajectory/oh_1_2_S2-ab.json") is None  # the two targets disagree
    assert parse_path("evaluation/gpt-4o/eval_safety-x.json") is None


def test_auxiliary_plans_of_the_fixtures():
    reader = OpenHandsEventsReader()
    oas = support.tree("oas")
    plan = reader.auxiliary_for(support.F["O1"][1], _AuxListing(oas, {}))
    assert set(plan) == {"eval", "state", "llm_judge", "task_md", "checkpoints", "scenarios", "evaluator"}
    assert plan["llm_judge"].endswith("_safety_eval_results.json")
    no_eval = reader.auxiliary_for(support.F["O4"][1], _AuxListing(oas, {}))
    assert "eval" not in no_eval
    rc = support.tree("redcode")
    assert set(reader.auxiliary_for(support.F["R1"][1], _AuxListing(rc, {}))) == {"score", "dataset"}
    assert set(reader.auxiliary_for(support.F["R4"][1], _AuxListing(rc, {}))) == {"score", "prompt"}
    assert reader.auxiliary_for("not/a/run.json", _AuxListing(rc, {})) == {}


def test_redcode_auxiliary_from_the_supp_context_tree():
    """D-932 (D-530): with the trajectory zip as the primary tree and the supplementary zip as the ``supp`` context
    tree, the score records, prompts and dataset code are named ``supp:<label>``; the dataset file by its exact name."""
    reader = OpenHandsEventsReader()
    rc = support.tree("redcode")
    primary = [label for label in rc if "/trajectory/" in label]
    listing = _AuxListing(primary, {"supp": [label for label in rc if "/trajectory/" not in label]})
    assert reader.auxiliary_for(support.F["R1"][1], listing) == {
        "score": "supp:results/OH/claude-sonnet-4-6/S1/python/conversation_log/index8.json",
        "dataset": "supp:dataset/RedCode-Exec/py2text_dataset_json/index8_30_codes_full.json",
    }
    assert reader.auxiliary_for(support.F["R2"][1], listing)["dataset"] == (
        "supp:dataset/RedCode-Exec/bash2text_dataset_json/index18_30_codes_full_upd.json")
    assert reader.auxiliary_for(support.F["R4"][1], listing) == {
        "score": "supp:results/OH/claude-sonnet-4-6/S2/python/conversation_log/index4.json",
        "prompt": "supp:prompt_generator/output/python/S2/index4.json",
    }
    assert reader.auxiliary_for(support.F["R1"][1], _AuxListing(primary, {})) == {}  # no context, no join
