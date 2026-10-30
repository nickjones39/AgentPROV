"""``ext.agentdojo.committed_no_later_than`` (D) and ``benchmark_era`` (I) from the git origin's ``introduced_in_commit`` (D.6.16).

No test needs the history cache: the history table is package data (``tables/agentdojo-history.table.toml``) and the
introducing commit arrives on the artefact's origin. The tests that need the real history store are in
``tests/full_corpus/test_history_table.py``.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tomllib
from pathlib import Path
from typing import Any

import pytest
from agentdojo_support import C274885, REPO_URL, base_log, git_blob, log_bytes, map_bytes, path_of
from test_v1_import import v1_log

from agentprov.adapters.agentdojo.history_table import FORMAT, load_history_table, parse_history_table
from agentprov.adapters.agentdojo.profile import family_table
from agentprov.adapters.profiles import load_profile
from agentprov.adapters.types import Origin
from agentprov.errors import ProfileError

TABLE_PATH = Path(__file__).resolve().parents[3] / "src/agentprov/adapters/agentdojo/tables/agentdojo-history.table.toml"
DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")


def _table():
    return family_table(load_profile("agentdojo-upstream")).history


def _commit(prefix: str) -> str:
    (found,) = [c for c in _table().commits if c.startswith(prefix)]
    return found


def _map(doc: dict[str, Any], introduced: str | None, *, repo: str = REPO_URL):
    raw = log_bytes(doc)
    origin = Origin.git(repo, C274885, path_of(doc, None), git_blob(raw), introduced_in_commit=introduced)
    return map_bytes(raw, path_of(doc, None), origin=origin)


def _ok(m: Any) -> None:
    report = m.validate()
    assert report.ok and report.passed, [(f.code, f.pointer) for f in report.errors]


def _ext(m: Any) -> dict[str, Any]:
    return m.header["ext"]["agentdojo"]


# ------------------------------------------------------------------------------------------------ the date (D)
def test_the_date_of_the_introducing_commit_is_written_as_an_ext_field():
    commit = _commit("52df3bc1d9")
    m = _map(base_log(), commit)
    _ok(m)
    h = m.header
    assert _ext(m)["committed_no_later_than"] == "2024-07-16T12:30:29Z" == _table().date(commit)
    # D-27 c6: the rule cites no code (its evidence is git's semantics, documented), so its I twin is cited
    assert h["evf"]["/ext/agentdojo/committed_no_later_than"] == "I"
    assert "agentdojo.committed_no_later_than_unverified@1#/ext/agentdojo/committed_no_later_than" in h["rule"]
    assert {"a": "a0", "o": "/introduced_in_commit"} in h["src"]
    assert h["artifacts"][0]["origin"]["introduced_in_commit"] == commit
    # a bound in ext only: no record of the file carries a time, and the header has no time member
    assert "t" not in h
    assert not any("2024-07-16T12:30:29Z" in json.dumps(r) for r in m.records[1:])


def test_without_the_introducing_commit_neither_field_is_written_and_nothing_else_changes():
    doc = base_log()
    plain, with_commit = _map(doc, None), _map(doc, _commit("c274885610"))
    assert "committed_no_later_than" not in _ext(plain) and "benchmark_era" not in _ext(plain)
    assert not plain.issues("agentdojo.history_commit_unlisted")
    assert plain.of_kind("actor")[0]["unk"].get("/version") == "not_recorded"  # the existing unk path stays
    # every record but the header and the seal is identical
    body = lambda m: [r for r in m.records[1:] if r.get("k") != "seal"]  # noqa: E731
    assert body(plain) == body(with_commit)
    assert {k: v for k, v in plain.header.items() if k not in ("ext", "evf", "rule", "src", "artifacts")} == {
        k: v for k, v in with_commit.header.items() if k not in ("ext", "evf", "rule", "src", "artifacts")
    }


def test_a_commit_the_table_does_not_list_is_reported_not_guessed():
    m = _map(base_log(), "f" * 40)
    assert "committed_no_later_than" not in _ext(m) and "benchmark_era" not in _ext(m)
    (issue,) = m.issues("agentdojo.history_commit_unlisted")
    assert issue.get("severity", "warning") == "warning" and issue["rule"] == "agentdojo.committed_no_later_than@1"
    _ok(m)


def test_an_origin_of_another_repository_gets_nothing():
    m = _map(base_log(), _commit("c274885610"), repo="https://github.com/someone/else")
    assert "committed_no_later_than" not in _ext(m) and not m.issues("agentdojo.history_commit_unlisted")


# ------------------------------------------------------------------------------------------------ the era (I)
@pytest.mark.parametrize(
    ("prefix", "candidate", "basis", "next_version", "next_cut"),
    [
        ("c274885610", "v1", "pre_versioning", "v1.1", "2024-07-16T13:13:51Z"),  # the last commit of the 2024-06 pin
        ("9d7d13912c", "v1", "registered", "v1.1", "2024-07-16T13:13:51Z"),
        ("52df3bc1d9", "v1", "registered", "v1.1", "2024-07-16T13:13:51Z"),  # committed 43 minutes before the v1.1 cut
        ("04ffc17845", "v1", "registered", "v1.1", "2024-07-16T13:13:51Z"),  # on a branch that did not hold the cut yet
        ("26c5a22b7d", "v1.1", "registered", "v1.1.1", "2024-11-07T10:06:26Z"),
        ("650bc7ead0", "v1.1.1", "registered", "v1.1.2", "2025-01-15T10:34:09Z"),
        ("6bbd9ca443", "v1.2", "registered", "v1.2.1", "2025-04-30T05:41:49Z"),
        ("9272bf1e0c", "v1.2.1", "registered", "v1.2.2", "2025-10-27T18:01:06Z"),
    ],
)
def test_the_era_is_the_version_in_force_at_the_introducing_commit(prefix, candidate, basis, next_version, next_cut):
    commit = _commit(prefix)
    m = _map(base_log(), commit)
    _ok(m)
    era = _ext(m)["benchmark_era"]
    assert era == {"candidate": candidate, "basis": basis, "next": {"version": next_version, "cut_date": next_cut}}
    h = m.header
    assert h["evf"]["/ext/agentdojo/benchmark_era"] == "I"
    assert "agentdojo.benchmark_era_from_commit@1#/ext/agentdojo/benchmark_era" in h["rule"]
    assert m.of_kind("actor")[0]["unk"]["/version"] == "not_recorded" and "version" not in m.of_kind("actor")[0]


def test_the_last_registered_version_has_no_next():
    doc = tomllib.loads(TABLE_PATH.read_text(encoding="utf-8"))
    row = {"id": "a" * 40, "date": "2026-01-01T00:00:00Z", "version": "v1.2.2", "registered": True, "under": doc["pins"][1]}
    table = parse_history_table(_doc(commit=[*doc["commit"], row]))
    era = table.era("a" * 40)
    assert (era.candidate, era.registered, era.next_version, era.next_cut_date) == ("v1.2.2", True, None, None)
    assert table.era("b" * 40) is None and table.date("b" * 40) is None


def test_the_era_is_per_file_not_per_pipeline_directory():
    """Two files of one pipeline directory, introduced by different commits, get different candidates (verify §5.3)."""
    a = _map(base_log(), _commit("9d7d13912c"))
    b = _map(base_log(), _commit("26c5a22b7d"))
    assert a.header["task"] == b.header["task"]
    assert _ext(a)["benchmark_era"]["candidate"] == "v1" and _ext(b)["benchmark_era"]["candidate"] == "v1.1"


def test_a_recorded_benchmark_version_gets_no_era():
    m = _map(v1_log(), _commit("9272bf1e0c"))
    _ok(m)
    assert "benchmark_era" not in _ext(m) and _ext(m)["committed_no_later_than"] == "2025-07-25T17:05:15Z"
    assert m.get("bench")["version"] == "v1.2.1"
    assert "/ext/agentdojo/benchmark_era" not in m.header["evf"]


def test_a_sentinel_version_label_is_not_a_recorded_version():
    m = _map(v1_log(benchmark_version="unknown"), _commit("9272bf1e0c"))
    assert _ext(m)["benchmark_era"]["candidate"] == "v1.2.1" and m.get("bench")["unk"]["/version"] == "not_recorded"


def test_the_ext_fields_conform_to_the_closed_ext_schema():
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((TABLE_PATH.parents[1] / "ext.schema.json").read_bytes())
    for prefix in ("52df3bc1d9", "c274885610", "9272bf1e0c"):
        m = _map(base_log(), _commit(prefix))
        jsonschema.validate({"execution": _ext(m)}, schema)
    jsonschema.validate({"execution": {"pipeline_name": 1, "error": None, "benchmark_era": {"candidate": "v1.2", "basis": "registered"}}}, schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"execution": {"pipeline_name": 1, "error": None, "benchmark_era": {"candidate": "v1", "basis": "guess"}}}, schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"execution": {"pipeline_name": 1, "error": None, "committed_no_later_than": "2024-06-02"}}, schema)


# ------------------------------------------------------------------------------------------------ the table
def test_the_shipped_table_matches_the_profile_pin_and_its_pins():
    profile = load_profile("agentdojo-upstream")
    declared = profile.family_table()["benchmark"]["history"]
    data = TABLE_PATH.read_bytes()
    assert hashlib.sha256(data).hexdigest() == declared["table"]["sha256"]
    table = load_history_table(declared["table"]["path"], declared["table"]["sha256"])
    assert table.repo == declared["repo"] == profile.data["source"]["canonical_repo"]
    assert set(table.pins) == {p["commit"] for p in profile.data["source"]["pins"] if p.get("part") in ("head", "2024-06")}
    assert [v.label for v in table.versions] == ["v1", "v1.1", "v1.1.1", "v1.1.2", "v1.2", "v1.2.1", "v1.2.2"]


def test_a_table_whose_bytes_changed_is_refused():
    with pytest.raises(ProfileError):
        load_history_table("tables/agentdojo-history.table.toml", "0" * 64)


def test_table_rows_are_internally_consistent():
    table = _table()
    cuts = {v.label: v for v in table.versions}
    assert all(DATE.fullmatch(v.cut_date) and len(v.cut) == 40 for v in table.versions)
    for row in table.commits.values():
        assert DATE.fullmatch(row.date) and row.version in cuts
        if row.registered:
            assert row.date >= cuts[row.version].cut_date, row.id  # a version is in force only after its cut
        else:
            assert row.version == "v1" and row.date < cuts["v1"].cut_date, row.id
    assert any(not r.registered for r in table.commits.values())  # the whole 2024-06 pin predates the label


def _doc(**changes: Any) -> bytes:
    doc = tomllib.loads(TABLE_PATH.read_text(encoding="utf-8"))
    doc.update(changes)
    lines = [f'format = "{doc["format"]}"', f'repo = "{doc["repo"]}"', "pins = " + json.dumps(doc["pins"])]
    for kind in ("version", "commit"):
        for row in doc[kind]:
            lines.append(f"[[{kind}]]")
            lines += [f"{k} = {json.dumps(v)}" for k, v in row.items()]
    return "\n".join(lines).encode()


def test_the_table_parser_is_closed_and_strict():
    assert parse_history_table(_doc()).repo == "https://github.com/ethz-spylab/agentdojo"
    bad: list[bytes] = [
        _doc(format="other/1"),
        _doc(commit=[{"id": "a" * 40, "date": "2024-06-02T12:26:48Z", "version": "v9", "registered": True, "under": C274885}]),  # unknown version
        _doc(commit=[{"id": "a" * 40, "date": "yesterday", "version": "v1", "registered": True, "under": C274885}]),
        _doc(commit=[{"id": "short", "date": "2024-06-02T12:26:48Z", "version": "v1", "registered": True, "under": C274885}]),
        _doc(commit=[{"id": "a" * 40, "date": "2024-06-02T12:26:48Z", "version": "v1", "registered": True, "under": C274885, "x": 1}]),
        _doc(commit=[{"id": "a" * 40, "date": "2024-06-02T12:26:48Z", "version": "v1", "registered": True, "under": C274885}] * 2),  # twice
        _doc(commit=[{"id": "a" * 40, "date": "2024-06-02T12:26:48Z", "version": "v1", "registered": True}]),  # no under
        _doc(commit=[{"id": "a" * 40, "date": "2024-06-02T12:26:48Z", "version": "v1", "registered": True,
                      "under": "b" * 40}]),  # under a commit that is not a pin
        _doc(version=[]),
        b"not = [toml",
    ]
    for data in bad:
        with pytest.raises(ProfileError):
            parse_history_table(data)
    assert FORMAT.endswith("/2")


def test_introduced_under_is_the_oldest_pin_holding_the_introducing_commit():
    """D-84: the facet that decides whether a v0.k11 log is June-2024 code. The table lists each introducing commit
    under the oldest pin whose history contains it; an origin at the oldest pin needs no introducing commit; an unlisted
    or unknown one gives None (fail closed)."""
    table = _table()
    assert table.pins[0] == C274885 and set(r.under for r in table.commits.values()) <= set(table.pins)
    june = [c for c, r in table.commits.items() if r.under == C274885]
    later = [c for c, r in table.commits.items() if r.under != C274885]
    assert june and later and all(table.commits[c].date <= "2024-06-05T23:59:59Z" for c in june)
    assert table.introduced_under(C274885, None) == C274885  # the 2024-06 corpus: blobs in the pin's own tree
    assert table.introduced_under(table.pins[1], june[0]) == C274885
    assert table.introduced_under(table.pins[1], later[0]) == table.pins[1]
    assert table.introduced_under(table.pins[1], None) is None
    assert table.introduced_under(table.pins[1], "f" * 40) is None


# ------------------------------------------------------------------------------------------------ a real artefact
HISTORY_DIGESTS = Path(__file__).resolve().parent / "history_aer_digests.json"
C161_COMMIT = "a73028fb7bae3c6cf05294d6a1756b34cd90d63c"  # introduced the C.16.1 blob (real history: 2024-06-04, "Add gpt-4o defense results")


def test_the_c161_artefact_with_its_real_introducing_commit():
    """The June-2024 worked example as an import with the history index would write it: both fields, pinned bytes. The
    committed vector (C.16.1) has no introducing commit on its origin and stays as it is."""
    from agentdojo_support import C161_BLOB, C161_PATH, c161_bytes

    raw = c161_bytes()
    origin = Origin.git(REPO_URL, C274885, C161_PATH, C161_BLOB, introduced_in_commit=C161_COMMIT)
    m = map_bytes(raw, C161_PATH, origin=origin)
    _ok(m)
    assert _ext(m)["committed_no_later_than"] == "2024-06-04T15:17:19Z"
    assert _ext(m)["benchmark_era"] == {"candidate": "v1", "basis": "pre_versioning",
                                        "next": {"version": "v1.1", "cut_date": "2024-07-16T13:13:51Z"}}
    # The AER's digest is a pin regenerated with the other agentdojo AER pins (AGENTPROV_REGEN_AGENTDOJO_AER=1;
    # tools/regen_pins.py, family agentdojo-aer), never edited by hand.
    produced = {"C.16.1+introduced_in_commit": hashlib.sha256(m.data).hexdigest()}
    if os.environ.get("AGENTPROV_REGEN_AGENTDOJO_AER"):
        HISTORY_DIGESTS.write_text(json.dumps(produced, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    assert json.loads(HISTORY_DIGESTS.read_text(encoding="utf-8")) == produced
