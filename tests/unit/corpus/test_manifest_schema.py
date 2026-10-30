"""HL-T1: the in-code validator against the published schema ``corpus-0.2.schema.json`` (the current format) and its ``$defs`` (H.2.1).

* the committed schema file equals the one generated from the declarations (``agentprov.corpus.manifest``) and is a
  valid draft 2020-12 schema;
* a sealed manifest, its index rows, register entries, ``raw/members.jsonl`` rows and ``derivation.json`` pass both;
* differential (Hypothesis): random structural mutations of those documents (a member removed, an unknown member
  added, a value replaced by one of another JSON type) are accepted or refused **identically** by the in-code structural
  check and by :mod:`jsonschema`; the row validator (``validate_row``: the structural check, then the row class) refuses
  everything the schema refuses, and more (semantic issues).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest
import seal_support as ss
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from agentprov.corpus import manifest as m
from agentprov.corpus.package import seal

SCHEMA_FILE = ss.REPO / "src" / "agentprov" / "schemas" / m.schema_resource(m.FORMAT)  # the current format
_DOCS: dict[str, Any] = {}


@pytest.mark.parametrize("fmt", sorted(m.CORPUS_FORMATS))
def test_the_committed_schema_is_the_generated_one(fmt):
    path = SCHEMA_FILE.parent / m.schema_resource(fmt)
    assert path.read_bytes() == m.schema_bytes(fmt), "regenerate with agentprov.corpus.manifest.schema_bytes(fmt)"
    jsonschema.Draft202012Validator.check_schema(json.loads(path.read_bytes()))


def _validator(name: str | None) -> jsonschema.Draft202012Validator:
    schema = json.loads(SCHEMA_FILE.read_bytes())
    if name is not None:
        schema = {"$schema": schema["$schema"], "$defs": schema["$defs"], **schema["$defs"][name]}
    return jsonschema.Draft202012Validator(schema)


@pytest.fixture(scope="module")
def docs(tmp_path_factory) -> dict[str, Any]:
    if not _DOCS:
        root = ss.working_corpus(tmp_path_factory, tmp_path_factory.mktemp("schema") / "mini")
        seal(root, corpus_version="0.1.0", inputs=ss.inputs())
        read = lambda label: [json.loads(x) for x in (root / label).read_text().splitlines()]  # noqa: E731
        _DOCS.update(
            manifest=json.loads((root / "corpus.json").read_text()),
            index_row=read("executions.jsonl"),
            register_entry=read("register.jsonl"),
            derivation=json.loads((root / "derivation.json").read_text()),
        )
        _DOCS["members_row"] = [
            {"container": "sha256:" + "a" * 64, "crc32": "0a1b2c3d", "disposition": "selected", "fn_digest": "sha256:" + "b" * 64,
             "label": "samples/x.json", "method": 8, "sha256": "sha256:" + "c" * 64, "size": 10},
            {"container": "sha256:" + "a" * 64, "crc32": "0a1b2c3d", "disposition": "rejected", "fn_digest": "sha256:" + "b" * 64,
             "label": None, "method": 99, "sha256": None, "size": None, "code": "ingest.archive.method"},
        ]  # fmt: skip
    return _DOCS


def test_real_documents_pass_both(docs):
    assert m.validate_manifest(docs["manifest"]) == []
    assert not list(_validator(None).iter_errors(docs["manifest"]))
    for name in ("index_row", "register_entry", "members_row"):
        for doc in docs[name]:
            assert m.validate_def(name, doc) == [], name
            assert not list(_validator(name).iter_errors(doc)), name
    assert m.validate_def("derivation", docs["derivation"]) == []
    assert not list(_validator("derivation").iter_errors(docs["derivation"]))


# ------------------------------------------------------------------------------------------------ mutations
_OTHER_VALUES = (None, True, 0, 7, "x", "", [], ["x"], {}, {"zz": 1})


def _paths(doc: Any, prefix: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    out = [prefix]
    if isinstance(doc, dict):
        for k, v in doc.items():
            out += _paths(v, (*prefix, k))
    elif isinstance(doc, list):
        for i, v in enumerate(doc):
            out += _paths(v, (*prefix, i))
    return out


def _mutate(doc: Any, path: tuple[Any, ...], how: str, value: Any) -> Any:
    doc = copy.deepcopy(doc)
    if not path:
        return value if how == "replace" else doc
    parent = doc
    for key in path[:-1]:
        parent = parent[key]
    last = path[-1]
    if how == "remove" and isinstance(parent, dict):
        del parent[last]
    elif how == "add" and isinstance(parent[last], dict):
        parent[last]["zz_unknown"] = value
    else:
        parent[last] = value
    return doc


@st.composite
def _mutation(draw: Any, doc: Any) -> Any:
    paths = _paths(doc)
    path = draw(st.sampled_from(paths))
    how = draw(st.sampled_from(("remove", "add", "replace")))
    value = draw(st.sampled_from(_OTHER_VALUES))
    return _mutate(doc, path, how, value)


_SETTINGS = settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])


def _agree(name: str | None, doc: Any) -> None:
    structural = m.validate_def(name, doc) if name else m._structural(m.MANIFEST, doc)  # noqa: SLF001
    schema_errors = list(_validator(name).iter_errors(doc))
    assert bool(structural) == bool(schema_errors), (structural[:3], [e.message[:120] for e in schema_errors[:3]])


@pytest.mark.parametrize("name", ["manifest", "index_row", "register_entry", "members_row", "derivation"])
def test_differential_structural_check_equals_the_schema(docs, name):
    base = docs[name] if name in ("manifest", "derivation") else docs[name][0]
    schema_name = None if name == "manifest" else name

    @_SETTINGS
    @given(st.data())
    def run(data: Any) -> None:
        _agree(schema_name, data.draw(_mutation(base)))

    run()


@pytest.mark.parametrize("name", ["index_row", "register_entry", "members_row"])
def test_the_row_validator_is_the_schema_plus_the_row_class(docs, name):
    """``validate_row`` refuses whatever the schema refuses (it starts with the structural check) and, beyond it, what the
    row class refuses (semantic issues the schema cannot express)."""
    base = docs[name][0]

    @_SETTINGS
    @given(st.data())
    def run(data: Any) -> None:
        doc = data.draw(_mutation(base))
        if list(_validator(name).iter_errors(doc)):
            assert m.validate_row(name, doc)

    run()
    assert m.validate_row(name, base) == []


def test_row_semantics_beyond_the_schema(docs):
    row = copy.deepcopy(docs["index_row"][0])
    row["logical_key"] = "lk_" + "a" * 26  # well-formed, but not the key of the cell
    assert not list(_validator("index_row").iter_errors(row))
    assert [i.level for i in m.validate_row("index_row", row)] == ["semantic"]


def test_semantic_checks_are_reported_separately(docs):
    broken = copy.deepcopy(docs["manifest"])
    broken["sources"][0]["snapshots"][0]["counts"]["candidates"] += 1
    issues = m.validate_manifest(broken)
    assert any(i.level == "semantic" and i.code == "reconciliation" for i in issues)
    assert not list(_validator(None).iter_errors(broken))  # the schema cannot see it
    tampered = copy.deepcopy(docs["manifest"])
    tampered["title"] = "another title"
    assert any(i.code == "content_digest" for i in m.validate_manifest(tampered))
    floats = copy.deepcopy(docs["manifest"])
    floats["counts"]["executions"] = 3.0
    assert m.validate_manifest(floats)


@pytest.mark.parametrize("created", ["2026-02-30T00:00:00Z", "0000-01-01T00:00:00Z", "2026-13-45T00:00:00Z",
                                     "2026-01-01T25:00:00Z"])
def test_an_impossible_created_is_a_semantic_issue(docs, created):
    # CB-18b: release.created matches the RFC 3339 pattern but names no instant; the schema cannot see it.
    broken = copy.deepcopy(docs["manifest"])
    broken["release"]["created"] = created
    assert not list(_validator(None).iter_errors(broken))
    issues = m.validate_manifest(broken)
    assert any(i.level == "semantic" and i.pointer == "/release/created" for i in issues), issues


def test_paths_exist():
    assert Path(SCHEMA_FILE).is_file()


@pytest.mark.parametrize(("fmt", "accepted"), [("agentprov-corpus/0.2", True), ("agentprov-corpus/0.1", False)])
def test_a_validation_stage_that_skipped_tier_4_fits_the_0_2_derivation_v7(fmt, accepted):
    # pre-round verification V-7: validation_stage_definition lists a skipped tier 4 under `skipped` (G2c-5); corpus/0.2
    # takes it, corpus/0.1 stays as released (D-163)
    from agentprov.stage_definitions import validation_stage_definition

    doc = {"format": "agentprov-derivation/0.1", "lockfile_sha256": None,
           "python": {"implementation": "cpython", "version": "3.14.0"},
           "stages": [validation_stage_definition([], "dev", prov_conformance=False)]}
    assert doc["stages"][0]["skipped"]
    schema = json.loads((SCHEMA_FILE.parent / m.schema_resource(fmt)).read_bytes())
    validator = jsonschema.Draft202012Validator(
        {"$schema": schema["$schema"], "$defs": schema["$defs"], **schema["$defs"]["derivation"]})
    assert (not list(validator.iter_errors(doc))) is accepted
    assert (not m._structural(m.DEFS_BY_FORMAT[fmt]["derivation"], doc, m.DEFS_BY_FORMAT[fmt])) is accepted
