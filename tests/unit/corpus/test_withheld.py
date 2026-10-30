"""``WITHHELD.json`` (``agentprov-withheld/0.1``; HL H.4.5, G.9.5; D-230): the format, its published schema and the
strict reader.

Checked: the committed schema is the generated one and a valid draft 2020-12 schema; a built document round-trips byte
for byte; the in-code reader and :mod:`jsonschema` agree on the structural verdict of valid and mutated documents; the
semantic rules the schema cannot express (sorted unique arrays, cross-references between entries and executions, object
origins, a finding exactly for a profile rule, one-line notes) are refused; floats and over-long notes are refused; the
datasheet summary counts objects and executions by reason and basis.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from agentprov.corpus import withheld as w

REPO = Path(__file__).resolve().parents[3]
SCHEMA_FILE = REPO / "src" / "agentprov" / "schemas" / "withheld-0.1.schema.json"
SHA_A, SHA_B = "a" * 64, "b" * 64
EX_1, EX_2 = "ex_" + "a" * 26, "ex_" + "b" * 26
GIT = {"blob_sha1": "c" * 40, "commit": "d" * 40, "kind": "git", "path": "runs/x.json", "repo": "https://github.com/o/r"}


def _document() -> w.WithheldDocument:
    return w.WithheldDocument(
        entries=(
            w.WithheldObject(SHA_A, (GIT,), "secret", "purge", "purged from the private raw store", (EX_1,), 12,
                             "application/json", None, "2026-10-12"),
            w.WithheldObject(SHA_B, (GIT,), "licence", "profile_rule", "canary credential", (EX_1, EX_2),
                             finding=w.WithheldFinding("agentprov-withhold/1", "tst-profile@1:canary",
                                                       "raw/objects/bb/" + SHA_B + ".json:canary")),
        ),
        executions=(w.WithheldExecution(EX_1, ("s1",), {"aer": "sha256:" + "e" * 64}),
                    w.WithheldExecution(EX_2, ("s1", "s2"), {"aer": "sha256:" + "f" * 64, "validation": None})),
        policies=(w.WithheldPolicy("tst-profile", 1, "sha256:" + "0" * 64, (("canary", "pattern", "executions"),),
                                   ("generic-api-key",)),),
    )


def test_the_committed_schema_is_the_generated_one():
    assert SCHEMA_FILE.read_bytes() == w.schema_bytes(), "regenerate with agentprov.corpus.withheld.schema_bytes()"
    assert w.load_published_schema() == w.schema_bytes()
    jsonschema.Draft202012Validator.check_schema(json.loads(SCHEMA_FILE.read_bytes()))


def test_a_document_round_trips_byte_for_byte_and_names_its_format():
    data = w.encode_withheld(_document())
    assert data.endswith(b"\n") and json.loads(data)["format"] == "agentprov-withheld/0.1"
    again = w.decode_withheld(data)
    assert w.encode_withheld(again) == data
    assert set(again.objects) == {SHA_A, SHA_B} and set(again.execution_map) == {EX_1, EX_2}
    assert again.counts() == {"executions": 2, "objects": 2}
    assert again.execution_map[EX_2].sem_profiles() == [] and again.execution_map[EX_2].prov_specs() == []


def _valid() -> dict[str, Any]:
    return json.loads(w.encode_withheld(_document()))


def _mutations() -> list[tuple[str, Any]]:
    def drop(key: str) -> Any:
        return lambda d: d["entries"][0].pop(key)

    return [
        ("format", lambda d: d.update(format="agentprov-withheld/0.2")),
        ("no entries", lambda d: d.update(entries=[])),
        ("unknown member", lambda d: d["entries"][0].update(value="x")),
        ("missing sha256", drop("sha256")),
        ("missing origins", drop("origins")),
        ("bad reason", lambda d: d["entries"][0].update(reason="dangerous")),
        ("bad basis", lambda d: d["entries"][0].update(basis="manual")),
        ("float bytes", lambda d: d["entries"][0].update(bytes=1.5)),
        ("negative bytes", lambda d: d["entries"][0].update(bytes=-1)),
        ("empty origins", lambda d: d["entries"][0].update(origins=[])),
        ("bad ex", lambda d: d["entries"][0].update(affected_executions=["ex_NOT"])),
        ("note with LF", lambda d: d["entries"][0].update(public_note="a\nb")),
        ("note too long", lambda d: d["entries"][0].update(public_note="x" * 201)),
        ("bad date", lambda d: d["entries"][0].update(decided_on="12/10/2026")),
        ("float digest", lambda d: d["executions"][0]["digests"].update(aer=1.0)),
        ("no snapshot", lambda d: d["executions"][0].update(snapshot_ids=[])),
        ("policy without rules", lambda d: d["policies"][0].update(rules=[])),
    ]


@pytest.mark.parametrize(("name", "mutate"), _mutations(), ids=[n for n, _ in _mutations()])
def test_the_reader_and_jsonschema_refuse_every_structural_mutation(name, mutate):
    schema = jsonschema.Draft202012Validator(json.loads(SCHEMA_FILE.read_bytes()))
    doc = _valid()
    assert w.validate_withheld(doc) == [] and not list(schema.iter_errors(doc))
    mutated = copy.deepcopy(doc)
    mutate(mutated)
    assert w.validate_withheld(mutated), name
    assert list(schema.iter_errors(mutated)), name
    with pytest.raises(w.WithheldError):
        w.decode_withheld(json.dumps(mutated).encode())


@pytest.mark.parametrize(("name", "mutate"), [
    ("unsorted entries", lambda d: d["entries"].reverse()),
    ("affected not listed", lambda d: d["executions"].pop()),
    ("execution named by no entry", lambda d: d["entries"][0].update(affected_executions=[]) or
     d["entries"][1].update(affected_executions=[EX_1])),
    ("unsorted affected", lambda d: d["entries"][1]["affected_executions"].reverse()),
    ("an origin that is not one", lambda d: d["entries"][0].update(origins=[{"kind": "git", "repo": "x"}])),
    ("duplicate origins", lambda d: d["entries"][0].update(origins=[GIT, GIT])),
    ("finding without a profile rule", lambda d: d["entries"][1].update(basis="purge")),
    ("profile rule without a finding", lambda d: d["entries"][1].update(finding=None)),
    ("impossible date", lambda d: d["entries"][0].update(decided_on="2026-02-30")),
    ("padded note", lambda d: d["entries"][0].update(public_note=" padded")),
    ("unsorted snapshots", lambda d: d["executions"][1].update(snapshot_ids=["s2", "s1"])),
    ("unsorted scan rules", lambda d: d["policies"][0].update(scan_rules=["b", "a"])),
])  # fmt: skip
def test_the_reader_refuses_what_the_schema_cannot_express(name, mutate):
    doc = _valid()
    mutate(doc)
    issues = w.validate_withheld(doc)
    assert issues and all(i.level == "semantic" for i in issues), (name, issues)
    with pytest.raises(w.WithheldError) as refused:
        w.decode_withheld(json.dumps(doc).encode())
    assert refused.value.code == "corpus.withheld.invalid" and refused.value.exit_code == 1


def test_the_reader_refuses_non_strict_json():
    for data in (b'{"format": "agentprov-withheld/0.1", "format": "x"}', b"[1, 2", b'{"entries": NaN}'):
        with pytest.raises(w.WithheldError):
            w.decode_withheld(data)


def test_the_writer_refuses_an_inconsistent_document():
    bad = w.WithheldDocument(entries=(w.WithheldObject(SHA_A, (GIT,), "secret", "purge", "note", (EX_1,)),))
    with pytest.raises(w.WithheldError):
        w.encode_withheld(bad)  # EX_1 is affected but not listed under executions


def test_the_summary_groups_by_reason_and_basis_in_priority_order():
    rows = w.withheld_summary(_document())
    assert [(r["reason"], r["basis"], r["objects"], r["executions"]) for r in rows] == [
        ("secret", "purge", 1, 1), ("licence", "profile_rule", 1, 2)]
    assert rows[1]["notes"] == ["canary credential"]


def test_one_line_note_removes_controls_and_bounds_the_length():
    assert w.one_line_note("a\r\nb\u2028c\x1b[31m") == "a b c [31m"
    assert len(w.one_line_note("x" * 500)) == w.NOTE_MAX
    assert w.one_line_note("\n") == "withheld (H.4.5)"


# ================================================================================================ 0.2 (D-311)
SCHEMA_FILE_02 = REPO / "src" / "agentprov" / "schemas" / "withheld-0.2.schema.json"


def _issue_document() -> w.WithheldDocument:
    from dataclasses import replace

    document = _document()
    policy = replace(document.policies[0], rules=(("canary", "pattern", "executions"),
                                                  ("flagged", "issue", "executions")))
    return w.WithheldDocument(document.entries, document.executions, (policy,))


def test_the_committed_0_2_schema_is_the_generated_one_and_0_1_is_unchanged():
    assert SCHEMA_FILE_02.read_bytes() == w.schema_bytes(w.FORMAT_02), "regenerate with schema_bytes(FORMAT_02)"
    assert w.load_published_schema(w.SCHEMA_RESOURCE_02) == w.schema_bytes(w.FORMAT_02)
    assert SCHEMA_FILE.read_bytes() == w.schema_bytes(w.FORMAT)  # frozen with its version (D-163)
    jsonschema.Draft202012Validator.check_schema(json.loads(SCHEMA_FILE_02.read_bytes()))
    old, new = json.loads(SCHEMA_FILE.read_bytes()), json.loads(SCHEMA_FILE_02.read_bytes())
    kinds = new["properties"]["policies"]["items"]["properties"]["rules"]["items"]["properties"]["kind"]["enum"]
    assert kinds == ["marker", "pattern", "issue"]
    for doc in (old, new):  # the only differences: id, title, format constant and the kind enum
        doc.pop("$id"), doc.pop("title"), doc["properties"].pop("format")
        doc["properties"]["policies"]["items"]["properties"]["rules"]["items"]["properties"].pop("kind")
    assert old == new


def test_the_format_is_0_2_exactly_when_a_policy_has_an_issue_rule():
    assert _document().format == w.FORMAT and _document().schema_resource == w.SCHEMA_RESOURCE
    document = _issue_document()
    assert document.format == w.FORMAT_02 and document.schema_resource == w.SCHEMA_RESOURCE_02
    data = w.encode_withheld(document)
    assert json.loads(data)["format"] == "agentprov-withheld/0.2"
    assert w.encode_withheld(w.decode_withheld(data)) == data
    jsonschema.validate(json.loads(data), json.loads(SCHEMA_FILE_02.read_bytes()))
    with pytest.raises(jsonschema.ValidationError):  # the 0.1 schema refuses an issue rule
        jsonschema.validate({**json.loads(data), "format": w.FORMAT}, json.loads(SCHEMA_FILE.read_bytes()))


@pytest.mark.parametrize("which", ["0.1 with an issue rule", "0.2 without one"])
def test_a_format_that_disagrees_with_the_policies_is_refused(which):
    if which == "0.1 with an issue rule":
        obj = {**_issue_document().to_json(), "format": w.FORMAT}
    else:
        obj = {**_document().to_json(), "format": w.FORMAT_02}
    assert w.validate_withheld(obj)
    with pytest.raises(w.WithheldError):
        w.decode_withheld(json.dumps(obj).encode())


# ================================================================================================ 0.3 (D-454)
SCHEMA_FILE_03 = REPO / "src" / "agentprov" / "schemas" / "withheld-0.3.schema.json"


def _unscanned_document(*, issue: bool = False) -> w.WithheldDocument:
    from dataclasses import replace

    document = _issue_document() if issue else _document()
    entry = replace(document.entries[0], basis="unscanned", finding=None, affected_executions=())
    return w.WithheldDocument((entry, *document.entries[1:]), document.executions, document.policies)


def test_the_committed_0_3_schema_is_the_generated_one_and_0_1_0_2_are_unchanged():
    assert SCHEMA_FILE_03.read_bytes() == w.schema_bytes(w.FORMAT_03), "regenerate with schema_bytes(FORMAT_03)"
    assert w.load_published_schema(w.SCHEMA_RESOURCE_03) == w.schema_bytes(w.FORMAT_03)
    assert SCHEMA_FILE.read_bytes() == w.schema_bytes(w.FORMAT)  # frozen with their versions (D-163)
    assert SCHEMA_FILE_02.read_bytes() == w.schema_bytes(w.FORMAT_02)
    jsonschema.Draft202012Validator.check_schema(json.loads(SCHEMA_FILE_03.read_bytes()))
    old, new = json.loads(SCHEMA_FILE_02.read_bytes()), json.loads(SCHEMA_FILE_03.read_bytes())
    bases = new["properties"]["entries"]["items"]["properties"]["basis"]["enum"]
    assert bases == ["purge", "profile_rule", "raw_policy", "container", "unscanned"]
    for doc in (old, new):  # the only differences: id, title, format constant and the basis enum
        doc.pop("$id"), doc.pop("title"), doc["properties"].pop("format")
        doc["properties"]["entries"]["items"]["properties"].pop("basis")
    assert old == new


@pytest.mark.parametrize("issue", [False, True])
def test_the_format_is_0_3_exactly_when_an_entry_is_unscanned(issue):
    document = _unscanned_document(issue=issue)
    assert document.format == w.FORMAT_03 and document.schema_resource == w.SCHEMA_RESOURCE_03
    data = w.encode_withheld(document)
    assert w.encode_withheld(w.decode_withheld(data)) == data
    jsonschema.validate(json.loads(data), json.loads(SCHEMA_FILE_03.read_bytes()))
    with pytest.raises(jsonschema.ValidationError):  # the 0.2 schema refuses the basis
        jsonschema.validate({**json.loads(data), "format": w.FORMAT_02}, json.loads(SCHEMA_FILE_02.read_bytes()))
    assert w.withheld_summary(document)[-1]["basis"] in ("unscanned", "profile_rule", "container")


@pytest.mark.parametrize("which", ["0.2 with an unscanned entry", "0.3 without one"])
def test_a_0_3_format_that_disagrees_with_the_entries_is_refused(which):
    if which == "0.2 with an unscanned entry":
        obj = {**_unscanned_document(issue=True).to_json(), "format": w.FORMAT_02}
    else:
        obj = {**_issue_document().to_json(), "format": w.FORMAT_03}
    assert w.validate_withheld(obj)
    with pytest.raises(w.WithheldError):
        w.decode_withheld(json.dumps(obj).encode())
