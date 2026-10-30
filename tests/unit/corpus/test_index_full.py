"""Full H.3.1 index rows (phase 11) beside the working rows the importer writes (HL H.3.1, H.7.4; HL-T19)."""

from __future__ import annotations

import base64
import dataclasses
import hashlib
import json

import pytest
from facet_support import aer, outcome_sem

from agentprov.corpus.dedup import source_key
from agentprov.corpus.facets import facet_members
from agentprov.corpus.index import (
    FacetMembers,
    IndexError_,
    IndexRow,
    RawRef,
    StageOutput,
    check_corpus_json,
    decode_index,
    encode_index,
    logical_key,
)
from agentprov.corpus.layout import CorpusLayout
from agentprov.io.canonical import jcs_bytes

EX = "ex_7uz2oys57hugtsueixylme4fl5"
H = "ab" * 32
LAYOUT = CorpusLayout("/x")
SPEC = "agentprov-prov/0.1"
COMPAT = "adprov-v2.3-compat"
PROFILE = "foo.sem@1"

#: A phase-10 working row as the importer writes it (synthetic values; the member layout of the p10 corpora).
P10_ROW = (
    '{"adapter":"agentdojo.tracelogger@0.1.0","attempt":null,"completeness":"unverifiable","digests":{"aer":"sha256:'
    + "f6" * 32 + '","prov":{"agentprov-prov/0.1":{"json":"sha256:' + "df" * 32 + '"}},"sem":{"agentdojo.suites@1":"sha256:'
    + "93" * 32 + '"},"validation":"sha256:' + "a0" * 32 + '"},"ex":"' + EX + '","execution_observed":true,"issues":'
    '["map.accounting_unverifiable","map.earlier_attempts_unobservable"],"mode":"import","n_origins":1,"paths":{"aer":"'
    + LAYOUT.aer_relpath(EX) + '","prov":{"agentprov-prov/0.1":{"json":"' + LAYOUT.prov_relpath(SPEC, EX) + '"}},"sem":'
    '{"agentdojo.suites@1":"' + LAYOUT.sem_relpath("agentdojo.suites@1", EX) + '"}},"profile":"mandate-agentdojo-eval@1",'
    '"raw":[{"included":true,"role":"primary","sha256":"sha256:' + H + '"}],"snapshot_ids":["head"],"source_id":'
    '"mandate-agentdojo-eval","source_key":"sha256:' + H + '#{\\"p\\":\\"\\"}","stages":{"aer":"ok","prov":'
    '{"agentprov-prov/0.1":"ok"},"raw":"ok","sem":{"agentdojo.suites@1":"ok"},"validation":"ok"},"status":"ok",'
    '"unit":"agent_execution"}\n'
).encode()


def working_row(*, compat: bool = False) -> IndexRow:
    prov = {SPEC: StageOutput("ok", "11" * 32)}
    paths = {SPEC: LAYOUT.prov_relpath(SPEC, EX)}
    if compat:
        prov[COMPAT] = StageOutput("ok", "22" * 32)
        paths[COMPAT] = LAYOUT.prov_relpath(COMPAT, EX)
    return IndexRow(
        ex=EX, mode="import", unit="agent_execution", source_id="foo", snapshot_ids=("s",), source_key=source_key(H, {"p": ""}),
        raw=(RawRef(H, "primary", True),), n_origins=1, adapter="foo.reader@0.1.0", profile="foo@1", aer_digest="cd" * 32,
        aer_path=LAYOUT.aer_relpath(EX), stages={"raw": "ok", "aer": "ok"}, status="ok", completeness="unverifiable",
        execution_observed=True, issues=(), attempt=None, prov=prov, prov_paths=paths,
        validation=StageOutput("ok", "33" * 32), sem={PROFILE: StageOutput("ok", "44" * 32)},
        sem_paths={PROFILE: LAYOUT.sem_relpath(PROFILE, EX)},
    )  # fmt: skip


def members(*, compat: bool = False) -> FacetMembers:
    specs = [SPEC, COMPAT] if compat else [SPEC]
    return facet_members(aer(), {PROFILE: outcome_sem()}, prov_specs=specs)


def test_phase10_working_rows_still_decode_byte_for_byte():
    (row,) = decode_index(P10_ROW, LAYOUT)
    assert not row.is_full and row.line() == P10_ROW


def test_full_row_has_every_h31_member_and_round_trips():
    row = working_row().with_facets(members())
    j = row.to_json()
    assert sorted(j) == sorted([
        "adapter", "attempt", "cell", "completeness", "digests", "ev", "ex", "execution_observed", "facets", "issues",
        "logical_key", "mode", "n_origins", "oracles", "paths", "profile", "raw", "snapshot_ids", "source_id",
        "source_key", "stages", "status", "unit"])  # fmt: skip
    assert j["oracles"] == {} and j["logical_key"].startswith("lk_") and j["unit"] == "agent_execution"
    assert j["completeness"] == "unverifiable" and j["execution_observed"] is True  # HL-T19 flags on every row
    data = encode_index([row])
    (back,) = decode_index(data, LAYOUT)
    assert back == row and back.is_full and back.line() == data
    assert j["facets"]["outcome"][0]["value"] == {"$dec": "0.25"}
    check_corpus_json(j)  # no float anywhere in the row (H.1.4(3))


def test_hl_t19_compat_output_is_flagged_as_regression_oracle():
    row = working_row(compat=True).with_facets(members(compat=True))
    assert row.to_json()["oracles"] == {COMPAT: {"gate_report": None, "status": "apv:RegressionOracle"}}
    with pytest.raises(IndexError_):
        working_row(compat=True).with_facets(members())  # compat output without the flag
    with pytest.raises(IndexError_):
        working_row().with_facets(members(compat=True))  # a flag without compat output


def test_a_full_row_records_every_stage():
    from dataclasses import replace

    with pytest.raises(IndexError_):
        replace(working_row(), sem=None, sem_paths=None).with_facets(members())
    with pytest.raises(IndexError_):
        replace(working_row(), validation=None).with_facets(members())


def test_a_row_is_one_kind_or_the_other():
    j = working_row().with_facets(members()).to_json()
    del j["oracles"]
    with pytest.raises(IndexError_):
        IndexRow.from_json(j)
    k = working_row().to_json()
    k["facets"] = {}
    with pytest.raises(IndexError_):
        IndexRow.from_json(k)


def test_logical_key_kat_and_consistency():
    cell = {"benchmark": "agentdojo", "model": "gpt-4o-2024-05-13", "repeat": None, "suite": "banking", "task_id": "user_task_7"}
    digest = hashlib.sha256(b"aer-lk/1\n" + jcs_bytes(cell)).digest()
    assert logical_key(cell) == "lk_" + base64.b32encode(digest).decode().lower()[:26]
    assert logical_key(dict(reversed(list(cell.items())))) == logical_key(cell)  # JCS: member order is irrelevant
    for bad in ({}, {"model": {"$unk": "lost"}}, {"x": 0.5}):
        with pytest.raises(ValueError):
            logical_key(bad)
    good = members()
    with pytest.raises(IndexError_):
        FacetMembers("lk_" + "a" * 26, good.cell, good.facets, good.ev, good.oracles)  # not the cell's key
    with pytest.raises(IndexError_):
        FacetMembers(None, good.cell, good.facets, good.ev, good.oracles)  # null with every member known
    unknown = {**good.cell, "model": {"$unk": "not_recorded"}}
    assert FacetMembers(None, unknown, good.facets, {k: v for k, v in good.ev.items() if k != "cell.model"}, {}).logical_key is None
    with pytest.raises(IndexError_):
        FacetMembers(None, {**good.cell, "model": {"$unk": "forgotten"}}, good.facets, good.ev, {})  # not a C.7.1 reason


@pytest.mark.parametrize(
    "mutate",
    [
        lambda m: m["facets"].update({"n.messages": 1.0}),  # a float (H.1.4(3))
        lambda m: m["facets"].pop("outcome"),  # a core facet missing
        lambda m: m["facets"].update({"pipeline": "x"}),  # an adapter facet without x.<ns>.
        lambda m: m["facets"].update({"model.requested": ["b", "a"]}),  # not sorted
        lambda m: m["facets"].update({"framework": "agentdojo 0.1.35"}),  # a version string is not an identity
        lambda m: m["facets"].update({"generic_types": ["no_namespace"]}),
        lambda m: m["ev"].update({"task": "X"}),
        lambda m: m["ev"].update({"cell.nothing": "O"}),
        lambda m: m["facets"]["outcome"][0].pop("ev"),
        lambda m: m["facets"].update({"model.requested": [""]}),  # the published schema requires non-empty strings
        lambda m: m["facets"].update({"model.served": ["", "gpt-4o"]}),
        lambda m: m["facets"]["outcome"][0].update({"name": 7}),  # a non-string outcome name
        lambda m: m["paths"].update({"aer": None}),  # no null path (corpus-0.1 schema: a relative path)
        lambda m: m["oracles"].update({SPEC: {"gate_report": None, "status": "apv:RegressionOracle"}}),
    ],
)
def test_malformed_full_members_are_refused(mutate):
    j = json.loads(jcs_bytes(working_row().with_facets(members()).to_json()))
    mutate(j)
    with pytest.raises(IndexError_):
        IndexRow.from_json(j, LAYOUT)


def test_adapter_facets_are_accepted_when_namespaced():
    good = members()
    extended = FacetMembers(good.logical_key, good.cell, {**good.facets, "x.agentdojo.pipeline_dir": "gpt-4o"}, good.ev, {})
    assert working_row().with_facets(extended).to_json()["facets"]["x.agentdojo.pipeline_dir"] == "gpt-4o"


def test_the_row_class_follows_the_published_schema_on_null_and_empty_members():
    """HL-T1 findings of phase 11: the classes were looser than ``corpus-0.1.schema.json``; a working row is checked too."""
    working = json.loads(P10_ROW)
    working["paths"]["aer"] = None
    with pytest.raises(IndexError_):
        IndexRow.from_json(working, LAYOUT)
    good = json.loads(jcs_bytes(working_row().with_facets(members()).to_json()))
    good["facets"]["outcome"][0]["name"] = None  # the schema allows a null name (and then no evidence class for it)
    good["facets"]["outcome"][0]["ev"].pop("name", None)
    assert IndexRow.from_json(good, LAYOUT).is_full
    with pytest.raises(IndexError_):
        dataclasses.replace(working_row(), aer_path=None)  # type: ignore[arg-type]


#: CB-2: members of untrusted JSON with the wrong type; each was a builtins.TypeError (exit 70 in ``verify``).
WRONG_TYPES = {
    "ex": 1,
    "source_id": 5,
    "snapshot_ids": [["x"]],
    "source_key": 3,
    "adapter": None,
    "profile": 7,
    "issues": [{}],
    "mode": [],
    "unit": {},
    "status": [],
    "completeness": [],
    "n_origins": "1",
}


@pytest.mark.parametrize(("member", "value"), WRONG_TYPES.items(), ids=list(WRONG_TYPES))
def test_a_member_of_the_wrong_type_is_an_index_error_not_a_type_error(member, value):
    for row in (working_row(), working_row().with_facets(members())):
        j = json.loads(jcs_bytes(row.to_json()))
        j[member] = value
        with pytest.raises(IndexError_):
            IndexRow.from_json(j, LAYOUT)
        with pytest.raises(IndexError_):
            decode_index(jcs_bytes(j) + b"\n", LAYOUT)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda m: m["stages"].update({"aer": []}),
        lambda m: m["raw"][0].update({"role": {}}),
        lambda m: m["stages"]["prov"].update({SPEC: []}),
        lambda m: m["stages"]["sem"].update({PROFILE: {}}),
        lambda m: m.update({"logical_key": 5}),
        lambda m: m["oracles"].update({SPEC: {"gate_report": 5, "status": []}}),
        lambda m: m["facets"].update({"outcome": 5}),
        lambda m: m["ev"].update({"outcome": []}),
    ],
)
def test_a_nested_member_of_the_wrong_type_is_an_index_error_not_a_type_error(mutate):
    j = json.loads(jcs_bytes(working_row().with_facets(members()).to_json()))
    mutate(j)
    with pytest.raises(IndexError_):
        IndexRow.from_json(j, LAYOUT)
