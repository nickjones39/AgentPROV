"""``CorpusReader``: N.1.5 resolution and strict, read-only, chain-checked reads of working and sealed trees."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from agentprov.aer.reader import load_aer
from agentprov.corpus.dedup import source_key
from agentprov.corpus.facets import facet_members
from agentprov.corpus.index import IndexRow, RawRef, StageOutput, encode_index
from agentprov.corpus.layout import CorpusLayout
from agentprov.corpus.reader import CorpusNotFoundError, CorpusReader, CorpusReadError, resolve_corpus
from agentprov.formats import UnsupportedFormatError
from agentprov.sem.reader import load_sem
from agentprov.testing import fs_guard

VECTORS = Path(__file__).resolve().parents[3] / "docs" / "architecture" / "examples" / "C"
AER_FILE = VECTORS / "adprov_v1_llama_injecagent.aer.jsonl"
SEM_FILE = VECTORS / "adprov_v1_llama_injecagent.sem.jsonl"
PROFILE = "agentdojo.suites@1"
SPEC = "agentprov-prov/0.1"
PROV = b'{"bundle": {}}\n'


def build(root: Path, *, sealed: bool = False, depth: int = 1, full: bool = False, manifest_format: str = "agentprov-corpus/0.1") -> IndexRow:
    """A one-execution corpus from the C.16.2 AER and its C.14.5 SEM document; returns its index row."""
    layout = CorpusLayout(root, shard_depth=depth)
    aer, sem = load_aer(AER_FILE), load_sem(SEM_FILE)
    ex = aer.ex
    primary = next(a for a in aer.header["artifacts"] if a["role"] == "primary")
    row = IndexRow(
        ex=ex, mode="import", unit=aer.header["unit"], source_id="adprov", snapshot_ids=("v1",),
        source_key=source_key(aer.header["source_key"]["sha256"], aer.header["source_key"]["loc"]),
        raw=(RawRef(primary["sha256"], "primary", True),), n_origins=1, adapter="adprov.transcript_v1@0.1.0",
        profile="adprov-v1@1", aer_digest=aer.execution_digest, aer_path=layout.aer_relpath(ex),
        stages={"raw": "ok", "aer": "ok"}, status="ok", completeness="verified_complete", execution_observed=True,
        issues=(), attempt=None, prov={SPEC: StageOutput("ok", hashlib.sha256(PROV).hexdigest())},
        prov_paths={SPEC: layout.prov_relpath(SPEC, ex)}, validation=StageOutput("ok", "33" * 32),
        sem={PROFILE: StageOutput("ok", sem.digest)}, sem_paths={PROFILE: layout.sem_relpath(PROFILE, ex)},
    )  # fmt: skip
    if full:
        row = row.with_facets(facet_members(aer, {PROFILE: sem}, prov_specs=[SPEC]))
    files = {
        "corpus.json": json.dumps({"format": manifest_format, "corpus_id": "t", "sealed": sealed, "state": "working"}).encode(),
        "derivation.json": json.dumps({"format": "agentprov-derivation/0.1", "stages": {}}).encode(),
        "executions.jsonl": encode_index([row]),
        "register.jsonl": b"", "raw/origins.jsonl": b"", "raw/members.jsonl": b"",
        "validation/results.jsonl": json.dumps({"ex": ex, "verdict": "pass"}, separators=(",", ":")).encode() + b"\n",
        "validation/summary.json": json.dumps({"format": "agentprov-validation-summary/0.1", "executions": 1}).encode(),
        row.aer_path: AER_FILE.read_bytes(), layout.sem_relpath(PROFILE, ex): SEM_FILE.read_bytes(),
        layout.prov_relpath(SPEC, ex): PROV,
    }  # fmt: skip
    for label, data in files.items():
        path = root.joinpath(*label.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    (root / "raw" / "objects").mkdir(parents=True, exist_ok=True)
    return row


# ------------------------------------------------------------------------------------------------ N.1.5 resolution
def test_resolution_follows_n15(tmp_path):
    build(tmp_path / "c.partial")
    for given in (tmp_path / "c", tmp_path / "c.partial"):  # an explicit .partial is normalised to DIR first
        location = resolve_corpus(given)
        assert (location.root, location.state, location.used_partial) == (tmp_path / "c.partial", "working", True)
    build(tmp_path / "c", sealed=True)
    location = resolve_corpus(tmp_path / "c.partial")
    assert (location.root, location.state) == (tmp_path / "c", "sealed")  # the sealed DIR wins
    with pytest.raises(CorpusNotFoundError) as exc:
        resolve_corpus(tmp_path / "absent")
    assert exc.value.exit_code == 2
    build(tmp_path / "unsealed")  # a working tree not named .partial
    with pytest.raises(CorpusNotFoundError) as exc:
        resolve_corpus(tmp_path / "unsealed")
    assert exc.value.code == "corpus.not_sealed" and exc.value.exit_code == 2
    (tmp_path / "broken").mkdir()
    (tmp_path / "broken" / "corpus.json").write_bytes(b'{"sealed": true,')
    with pytest.raises(CorpusReadError):
        resolve_corpus(tmp_path / "broken")  # whether it is sealed cannot be established: fail closed


# ------------------------------------------------------------------------------------------------ reads
@pytest.mark.parametrize("full", [False, True])
def test_reads_every_file_and_checks_the_chain_without_writing(tmp_path, full):
    row = build(tmp_path / "c.partial", full=full)
    with fs_guard.unchanged(tmp_path):
        reader = CorpusReader.open(tmp_path / "c")
        assert reader.state == "working" and not reader.sealed and reader.shard_depth == 1
        assert reader.index() == [row] and reader.row(row.ex) == row and reader.row("ex_" + "a" * 26) is None
        assert reader.manifest()["corpus_id"] == "t" and reader.derivation()["stages"] == {}
        assert reader.register() == [] and reader.origins() == [] and reader.members() == []
        assert [r["ex"] for r in reader.validation_results()] == [row.ex] and reader.validation_summary()["executions"] == 1
        assert reader.read_aer(row).ex == row.ex and reader.read_sem(row, PROFILE).digest == row.sem[PROFILE].digest
        assert reader.read_prov(row, SPEC) == {"bundle": {}} and set(reader.read_sem_all(row)) == {PROFILE}
        assert reader.checksums_bytes() is None and not reader.raw_store().has("ab" * 32)
        assert reader.index()[0].is_full is full


#: ultra raw-withhold #10: a members.jsonl row whose closed-vocabulary field is an array or an object
_BAD_MEMBER_ROWS = [
    {"disposition": []},
    {"disposition": "rejected", "code": {"x": 1}, "label": None, "size": None},
]


def _bad_members_line(change: dict) -> bytes:
    row = {"container": "sha256:" + "a" * 64, "crc32": "00000000", "disposition": "not_selected",
           "fn_digest": "sha256:" + "b" * 64, "label": "m.json", "method": 0, "sha256": None, "size": 1, **change}
    return json.dumps(row).encode() + b"\n"


@pytest.mark.parametrize("change", _BAD_MEMBER_ROWS)
def test_a_members_row_of_the_wrong_type_is_a_coded_read_error(tmp_path, change):
    """Ultra raw-withhold #10: ``reader.members()`` fails closed with ``corpus.read.members``, never a ``TypeError``."""
    build(tmp_path / "c.partial")
    (tmp_path / "c.partial" / "raw" / "members.jsonl").write_bytes(_bad_members_line(change))
    with pytest.raises(CorpusReadError) as err:
        CorpusReader.open(tmp_path / "c").members()
    assert err.value.code == "corpus.read.members"


def test_shard_depth_two_is_detected(tmp_path):
    row = build(tmp_path / "c.partial", depth=2)
    reader = CorpusReader.open(tmp_path / "c")
    assert reader.shard_depth == 2 and reader.read_aer(row).ex == row.ex


def test_an_unknown_manifest_format_fails_closed(tmp_path):
    build(tmp_path / "c.partial", manifest_format="agentprov-corpus/0.3")
    with pytest.raises(UnsupportedFormatError):
        CorpusReader.open(tmp_path / "c").manifest()


def test_the_chain_is_checked(tmp_path):
    row = build(tmp_path / "c.partial")
    root = tmp_path / "c.partial"
    reader = CorpusReader.open(tmp_path / "c")
    (root / row.prov_paths[SPEC]).write_bytes(b"{}\n")
    with pytest.raises(CorpusReadError) as exc:
        reader.read_prov(row, SPEC)
    assert exc.value.code == "corpus.read.digest"
    aer_path = root / row.aer_path
    data = aer_path.read_bytes()
    aer_path.write_bytes(data.replace(b'"utility"', b'"utilitx"', 1))
    with pytest.raises(CorpusReadError):
        reader.read_aer(row)  # the seal no longer verifies
    aer_path.write_bytes(data)
    other = IndexRow.from_json({**row.to_json(), "digests": {**row.to_json()["digests"], "aer": "sha256:" + "0" * 64}})
    with pytest.raises(CorpusReadError) as exc:
        reader.read_aer(other)
    assert exc.value.code == "corpus.read.digest"


def test_a_symlinked_file_is_refused(tmp_path):
    row = build(tmp_path / "c.partial")
    root = tmp_path / "c.partial"
    copy = tmp_path / "elsewhere.aer.jsonl"
    copy.write_bytes((root / row.aer_path).read_bytes())
    (root / row.aer_path).unlink()
    os.symlink(copy, root / row.aer_path)
    with pytest.raises(CorpusReadError) as exc:
        CorpusReader.open(tmp_path / "c").read_aer(row)
    assert exc.value.code == "corpus.read.unreadable"


@pytest.mark.parametrize(
    "damage",
    [
        lambda b: b.replace(b'{"adapter"', b'{ "adapter"', 1),  # not canonical
        lambda b: b + b,  # a duplicate row
        lambda b: b[:-1],  # no final LF
        lambda b: b.replace(b'"aer":"aer/', b'"aer":"aer/0', 1),  # a recorded path the layout does not give
    ],
)
def test_a_malformed_index_is_refused(tmp_path, damage):
    build(tmp_path / "c.partial")
    index = tmp_path / "c.partial" / "executions.jsonl"
    index.write_bytes(damage(index.read_bytes()))
    with pytest.raises(CorpusReadError) as exc:
        CorpusReader.open(tmp_path / "c").index()
    assert exc.value.code == "corpus.read.index"


def test_labels_outside_the_grammar_are_never_opened(tmp_path):
    build(tmp_path / "c.partial")
    reader = CorpusReader.open(tmp_path / "c")
    for label in ("../c.partial/corpus.json", ".DS_Store", "raw/tmp/x", "/etc/passwd"):
        with pytest.raises(CorpusReadError) as exc:
            reader.read_bytes(label)
        assert exc.value.code == "corpus.read.path"


@pytest.mark.parametrize(
    "damage",
    [
        lambda b: b.replace(b'"source_id":"adprov"', b'"source_id":5', 1),
        lambda b: b.replace(b'"adapter":"adprov.transcript_v1@0.1.0"', b'"adapter":null', 1),
        lambda b: b.replace(b'"snapshot_ids":["v1"]', b'"snapshot_ids":[["v1"]]', 1),
        lambda b: b.replace(b'"issues":[]', b'"issues":[{}]', 1),
    ],
)
def test_an_index_member_of_the_wrong_type_is_a_read_error_not_a_type_error(tmp_path, damage):
    """CB-2: a type-confused member of an untrusted index was a builtins.TypeError (``verify``: exit 70)."""
    build(tmp_path / "c.partial")
    index = tmp_path / "c.partial" / "executions.jsonl"
    damaged = damage(index.read_bytes())
    assert damaged != index.read_bytes()
    index.write_bytes(damaged)
    with pytest.raises(CorpusReadError) as exc:
        CorpusReader.open(tmp_path / "c").index()  # the shard depth is detected from line 1 first
    assert exc.value.code == "corpus.read.index"
    with pytest.raises(CorpusReadError) as exc:
        list(CorpusReader(tmp_path / "c.partial", state="working", shard_depth=1).iter_index())
    assert exc.value.code == "corpus.read.index"


def test_a_register_member_of_the_wrong_type_is_a_read_error_not_a_type_error(tmp_path):
    """CB-2: ``previous.rid`` of the wrong type was a builtins.TypeError (``verify``: exit 70)."""
    build(tmp_path / "c.partial")
    entry = {"code": "dedup.collapsed", "detail": "", "disposition": "not_imported", "ids": [], "owner": None,
             "previous": {"corpus_version": "1", "rid": 5}, "rid": "r_" + "a" * 20, "rule": None, "severity": "info",
             "stage": "select", "subject": {"ex": "ex_" + "a" * 26}, "subject_key": "ex_" + "a" * 26}  # fmt: skip
    (tmp_path / "c.partial" / "register.jsonl").write_bytes(json.dumps(entry, separators=(",", ":"), sort_keys=True).encode() + b"\n")
    with pytest.raises(CorpusReadError) as exc:
        CorpusReader.open(tmp_path / "c").register()
    assert exc.value.code == "corpus.read.register"


def test_verify_reports_a_type_confused_index_row_as_index_invalid(tmp_path, monkeypatch, capsys):
    """CB-2 end to end: ``verify`` reports ``index.invalid`` and exits 1 (it ended with an internal error, exit 70)."""
    from agentprov.cli.main import main

    monkeypatch.setenv("AGENTPROV_HOME", str(tmp_path / "home"))
    build(tmp_path / "c.partial")
    index = tmp_path / "c.partial" / "executions.jsonl"
    index.write_bytes(index.read_bytes().replace(b'"source_id":"adprov"', b'"source_id":5', 1))
    code = main(["verify", "--corpus", str(tmp_path / "c"), "--level", "chain"])
    out, err = capsys.readouterr()
    assert code == 1, out + err
    assert "index.invalid" in out + err and "internal error" not in out + err


# ------------------------------------------------------------------------------------------------ GR-35 JSON size cap
@pytest.mark.parametrize("label", ["corpus.json", "derivation.json"])
def test_a_json_document_over_max_json_bytes_is_refused_at_open(tmp_path, monkeypatch, label):
    """GR-35: ``corpus.json`` (``_sealed_flag``) and every ``read_document`` are opened under ``max_json_bytes``, so an
    oversized document is refused by size before it is read, not read under the 2 GiB artefact cap first."""
    from agentprov.corpus import reader as reader_module
    from agentprov.ingest.limits import IngestLimits

    build(tmp_path / "c.partial")
    path = tmp_path / "c.partial" / label
    path.write_bytes(path.read_bytes() + b" " * 4096)
    limits = IngestLimits().replace(max_json_bytes=2048)
    caps: list[int] = []
    real = reader_module.open_evidence

    def spy(root, rel, lim, **kw):  # type: ignore[no-untyped-def]
        if rel == label:
            caps.append(lim.max_artefact_bytes)
        return real(root, rel, lim, **kw)

    monkeypatch.setattr(reader_module, "open_evidence", spy)
    with pytest.raises(CorpusReadError):
        reader = CorpusReader.open(tmp_path / "c", limits=limits)
        reader.read_document(label)
    assert caps and all(cap == 2048 for cap in caps)


def test_json_document_limits_never_raise_a_cap() -> None:
    from agentprov.corpus.reader import json_document_limits
    from agentprov.ingest.limits import IngestLimits

    default = IngestLimits()
    assert json_document_limits(default).max_artefact_bytes == default.max_json_bytes
    tight = default.replace(max_artefact_bytes=1000)
    assert json_document_limits(tight) is tight
