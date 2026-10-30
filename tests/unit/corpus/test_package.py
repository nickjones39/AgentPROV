"""Sealing (``agentprov.corpus.package.seal``; HL H.1.5, H.2, H.5, H.9; MN N.2.11; HL-T3, HL-T4, HL-T7; Q.20, Q.30).

A small working corpus (three golden AgentDojo logs, imported in release mode through a T1 worker) is copied per test and
sealed. Checked: the sealed tree (layout, closed world, manifest validity, full index rows, untouched AER/SEM/PROV
bytes, recomputed counts and the snapshot origin built from the pin); determinism (two seals of two copies are
byte-identical; the release date changes the root digest but not the content digest); every precondition refuses with
exit 4 and writes nothing; a failure after writing rolls the working tree back; a dry run writes nothing; the sealed tree
refuses writers; a seal killed before the swap is resumed by the next seal, or refused when its tree does not check out.
"""

from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path

import pytest
import seal_support as ss

from agentprov.corpus.datasheet import DatasheetError
from agentprov.corpus.index import IndexRow
from agentprov.corpus.integrity import verify_checksums
from agentprov.corpus.layout import SealedCorpusError, assert_writable
from agentprov.corpus.manifest import ManifestError, validate_manifest
from agentprov.corpus.package import PackageRefusedError, ProducerFacts, ReleaseArgs, seal
from agentprov.errors import AgentProvError
from agentprov.testing import fs_guard


@pytest.fixture
def corpus(tmp_path_factory, tmp_path) -> Path:
    return ss.working_corpus(tmp_path_factory, tmp_path / "mini")


def _manifest(root: Path) -> dict:
    return json.loads((root / "corpus.json").read_text("utf-8"))


def _rewrite(partial: Path, change) -> None:
    path = partial / "corpus.json"
    manifest = json.loads(path.read_text("utf-8"))
    change(manifest)
    path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", "utf-8")


# ------------------------------------------------------------------------------------------------ the sealed tree
def test_seal_writes_a_valid_closed_world_corpus_and_swaps_it(corpus):
    partial = corpus.with_name("mini.partial")
    before = {k: v for k, v in ss.tree_bytes(partial).items() if k.startswith(("aer/", "sem/", "prov/", "raw/objects/"))}
    report = seal(corpus, corpus_version="0.1.0", inputs=ss.inputs())
    assert not partial.exists() and corpus.is_dir()
    assert report.root_digest is not None and report.counters["executions"] == 3
    manifest = _manifest(corpus)
    assert validate_manifest(manifest) == []
    assert manifest["sealed"] is True and manifest["release"]["status"] == "sealed" and manifest["release"]["created"] is None
    assert manifest["corpus_id"] == "mini-agentdojo"  # from the spec, never from the working manifest (D-35)
    assert verify_checksums(corpus).ok  # closed world, every file listed (HL-T2)
    for label in ("DATASHEET.md", "CHANGELOG.md", "LICENSES/DERIVED.txt", "LICENSES/agentdojo/LICENSE",
                  "LICENSES/agentdojo/NOTICE.md", "rules/corpus-spec.toml", "rules/CARD.md", "rules/CHANGES.toml",
                  "rules/agentdojo-upstream.profile.toml", "rules/agentdojo.rules.toml", "rules/aer.rules.toml",
                  "rules/corpus.rules.toml", "rules/prov/agentprov-prov-0.1.toml", "schemas/corpus-0.2.schema.json",
                  "schemas/aer-0.2.schema.json"):
        assert (corpus / label).is_file(), label
    assert not (corpus / "raw" / "tmp").exists()
    after = {k: v for k, v in ss.tree_bytes(corpus).items() if k.startswith(("aer/", "sem/", "prov/", "raw/objects/"))}
    assert after == before  # sealing changes no AER, SEM, PROV or raw byte
    rows = [IndexRow.from_json(json.loads(line)) for line in (corpus / "executions.jsonl").read_text().splitlines()]
    assert all(r.is_full for r in rows)


def test_counts_and_origin_are_recomputed_from_the_pin_d33(corpus):
    seal(corpus, corpus_version="0.1.0", inputs=ss.inputs())
    snapshot = _manifest(corpus)["sources"][0]["snapshots"][0]
    assert snapshot["origin"] == {"commit": ss.C274885, "kind": "git", "repo": ss.support.AGENTDOJO, "subtree": "runs",
                                  "subtree_sha1": ss.TREE_SHA1}
    counts = snapshot["counts"]
    assert counts == {"candidates": 3, "executions": 3, "not_imported": 0, "selection_excluded": {}}
    manifest = _manifest(corpus)
    assert manifest["counts"]["candidates"] == manifest["counts"]["executions"] + manifest["counts"]["not_imported"]
    assert manifest["validation"]["linkage_resolved_pct"] == {"$dec": "100.00"}
    assert {c["id"] for c in manifest["rule_catalogues"]} >= {"aer", "agentdojo", "aprov", "corpus"}
    corpus_cat = next(c for c in manifest["rule_catalogues"] if c["id"] == "corpus")
    assert len(corpus_cat["rules_used"]) == 6  # the facet rules facet_schema cites
    assert manifest["oracle_specs"] == []  # Q.30: no compat output in this corpus


def test_two_seals_of_two_copies_are_byte_identical_hl_t4(tmp_path_factory, tmp_path):
    first = ss.working_corpus(tmp_path_factory, tmp_path / "a" / "mini")
    second = ss.working_corpus(tmp_path_factory, tmp_path / "b" / "mini")
    r1 = seal(first, corpus_version="0.1.0", inputs=ss.inputs())
    r2 = seal(second, corpus_version="0.1.0", inputs=ss.inputs())
    assert ss.tree_bytes(first) == ss.tree_bytes(second)
    assert r1.root_digest == r2.root_digest and r1.content_digest == r2.content_digest


@pytest.mark.parametrize("release", [ReleaseArgs(release_date="2026-02-30"), ReleaseArgs(release_date="0000-00-00"),
                                     ReleaseArgs(release_date="2026/10/12"), ReleaseArgs(source_date_epoch=-1),
                                     ReleaseArgs(source_date_epoch=253402300800), ReleaseArgs(source_date_epoch=10**12)])
def test_an_impossible_release_date_is_a_typed_refusal(corpus, release):
    # CB-18b: ReleaseArgs never yields an impossible release.created, and refuses with a typed exit-2 error (not a bare
    # ValueError or OverflowError, exit 70) before seal writes anything.
    with pytest.raises(AgentProvError) as info:
        release.to_json()
    assert info.value.exit_code == 2 and info.value.code == "package.release_date"
    before = ss.tree_bytes(corpus.with_name("mini.partial"))
    with pytest.raises(AgentProvError) as info:
        seal(corpus, corpus_version="0.1.0", inputs=ss.inputs(), release=release)
    assert info.value.exit_code == 2
    assert ss.tree_bytes(corpus.with_name("mini.partial")) == before and not corpus.exists()


def test_the_release_date_bounds_are_inclusive():
    assert ReleaseArgs(source_date_epoch=0).to_json()["created"] == "1970-01-01T00:00:00Z"
    assert ReleaseArgs(source_date_epoch=253402300799).to_json()["created"] == "9999-12-31T23:59:59Z"
    assert ReleaseArgs(release_date="2028-02-29").to_json()["created"] == "2028-02-29T00:00:00Z"


def test_the_release_date_changes_the_root_digest_not_the_content_digest(tmp_path_factory, tmp_path):
    plain = ss.working_corpus(tmp_path_factory, tmp_path / "a" / "mini")
    dated = ss.working_corpus(tmp_path_factory, tmp_path / "b" / "mini")
    r1 = seal(plain, corpus_version="0.1.0", inputs=ss.inputs())
    r2 = seal(dated, corpus_version="0.1.0", inputs=ss.inputs(), release=ReleaseArgs(release_date="2026-10-12"))
    assert r1.content_digest == r2.content_digest and r1.root_digest != r2.root_digest
    assert _manifest(dated)["release"]["created"] == "2026-10-12T00:00:00Z"


def test_a_sealed_corpus_refuses_writers_hl_t7(corpus):
    seal(corpus, corpus_version="0.1.0", inputs=ss.inputs())
    with pytest.raises(SealedCorpusError):
        assert_writable(corpus / "aer")
    with pytest.raises(PackageRefusedError) as info:
        seal(corpus, corpus_version="0.1.0", inputs=ss.inputs())
    assert info.value.exit_code == 4


def test_a_dry_run_writes_nothing(corpus):
    partial = corpus.with_name("mini.partial")
    with fs_guard.unchanged(partial):
        report = seal(corpus, corpus_version="0.1.0", inputs=ss.inputs(), dry_run=True)
    assert report.dry_run and report.root_digest is None and not corpus.exists()


# ------------------------------------------------------------------------------------------------ preconditions (exit 4)
def _partial_import(m):
    m["partial"] = True


def _snapshot_selection(m):  # NF-36: a snapshot imported with a selection, under a top-level mark that says complete
    m["partial"] = False
    m["sources"][0]["snapshots"][0]["selection"] = {
        "filters": {"include_paths": [], "select": {}, "variants": None}, "limit": None,
        "sample": {"n": 2, "mode": "first", "seed": None, "candidates": 3, "selected": 2, "stratum": None}}


def _dev_validation(partial: Path) -> None:
    path = partial / "derivation.json"
    doc = json.loads(path.read_text())
    for stage in doc["stages"]:
        if stage["stage"] == "validation":
            stage["mode"] = "dev"
    path.write_text(json.dumps(doc, sort_keys=True, indent=2) + "\n")


def _advisory(m):
    m["producer"]["interpreter_advisory"] = {"floor": "3.14.8", "missing": ["CVE-0"], "python_version": "3.14.0"}


def _unverified(m):
    m["sources"][0]["snapshots"][0]["verification"]["unverified"] = 1


def _no_pin(m):
    m["sources"][0]["snapshots"][0]["pin"] = None


def _context_trees(m):  # D.16.14 R2, as a manifest written before D-530 records a second tree: no pin
    m["sources"][0]["snapshots"][0]["context"] = [{"role": "tasks", "origin": None, "verification": None, "stored": 3}]


TASKS_PIN = {"kind": "git", "role": "tasks", "repo": "https://github.com/example/tasks", "commit": "b" * 40}


def _context_unverified(m):  # D-221: a pinned context tree whose pin did not vouch for every file
    m["sources"][0]["snapshots"][0]["context"] = [{"role": "tasks", "origin": None, "pin": TASKS_PIN, "stored": 3,
                                                    "verification": {"kind": "blob", "verified": 2, "unverified": 1}}]


def _pinned_objects(m):  # D.16.14 R3, an object the corpus does not hold with the recorded origin
    m["sources"][0]["snapshots"][0]["pinned_objects"] = [
        {"label": "runs/x.json", "origin": {"kind": "url", "url": "https://example.org/x"}, "sha256": "0" * 64, "bytes": 1}]


def _as_corpus_0_1(partial):  # the records of an aer/0.1 import seal as agentprov-corpus/0.1
    path = partial / "derivation.json"
    derivation = json.loads(path.read_text("utf-8"))
    for stage in derivation["stages"]:
        if stage.get("stage") == "aer":
            stage["format"] = "aer/0.1"
    path.write_text(json.dumps(derivation, sort_keys=True, indent=2) + "\n", "utf-8")


def _archive_input(m):  # D-200, as the importer records a snapshot imported from a downloaded archive
    m["sources"][0]["snapshots"][0]["input"] = {"kind": "archive", "label": "deposit.zip", "sha256": "sha256:" + "0" * 64,
                                                "bytes": 1}


def _corpus_0_1_with_archive_input(partial):  # D-223: corpus/0.1 cannot record the archive a re-map re-expands
    _rewrite(partial, _archive_input)
    _as_corpus_0_1(partial)


def _corpus_0_1_with_context(partial):  # NF-24: records sealed as agentprov-corpus/0.1 cannot keep a context tree
    _rewrite(partial, _context_unverified)
    path = partial / "derivation.json"
    derivation = json.loads(path.read_text("utf-8"))
    for stage in derivation["stages"]:
        if stage.get("stage") == "aer":
            stage["format"] = "aer/0.1"
    path.write_text(json.dumps(derivation, sort_keys=True, indent=2) + "\n", "utf-8")


@pytest.mark.parametrize(
    ("name", "damage", "changes", "code"),
    [
        ("partial import", lambda p: _rewrite(p, _partial_import), {}, "package.refused.partial"),
        ("snapshot imported with a selection", lambda p: _rewrite(p, _snapshot_selection), {}, "package.refused.partial"),
        ("dev-mode validation", _dev_validation, {}, "package.refused.dev_validation"),
        ("interpreter advisory", lambda p: _rewrite(p, _advisory), {}, "ingest.interpreter.unpatched"),
        ("unverified input", lambda p: _rewrite(p, _unverified), {}, "package.refused.unverified"),
        ("no pin", lambda p: _rewrite(p, _no_pin), {}, "package.refused.unpinned"),
        ("context tree without a pin (D-221)", lambda p: _rewrite(p, _context_trees), {}, "package.refused.unpinned"),
        ("context tree not vouched for (D-221)", lambda p: _rewrite(p, _context_unverified), {}, "package.refused.unverified"),
        ("pinned object not stored (D-221)", lambda p: _rewrite(p, _pinned_objects), {}, "package.refused.pinned_object"),
        ("context in a corpus/0.1 seal (NF-24)", _corpus_0_1_with_context, {}, "package.refused.context"),
        ("archive input in a corpus/0.1 seal (D-223)", _corpus_0_1_with_archive_input, {}, "package.refused.archive_input"),
        ("missing changelog entry", None, {"changes": b'[[change]]\nversion = "0.0.9"\nbump = "initial"\nsummary = "x"\n'},
         "package.refused.changelog"),
        ("dirty producer tree", None, {"producer": ProducerFacts(ss.COMMIT, False, "sha256:" + "0" * 64, "1.2.12")},
         "package.refused.git"),
        ("unknown producer commit", None, {"producer": ProducerFacts(None, True, "sha256:" + "0" * 64, "1.2.12")},
         "package.refused.git"),
        ("missing licence file", None, {"licence_files": {}}, "package.refused.licence_file"),
        ("other source profile", None, {"source_profile": ss.source_profile() + b"\n"}, "package.refused.profile"),
        ("stray file", lambda p: (p / ".DS_Store").write_bytes(b"x"), {}, "package.refused.closed_world"),
        ("lock held", lambda p: (p / ".agentprov.lock").write_bytes(b"{}"), {}, "package.refused.locked"),
        ("origin differs from the pin", None, {"spec": ss.SPEC.replace('subtree = "runs"', 'subtree = "other"').encode()},
         "package.refused.origin"),
        ("card of another mode", None, {"card": ss.CARD.replace("mode: import", "mode: live").encode()},
         "corpus.datasheet.mode"),
        ("card with a literal number", None, {"card": (ss.CARD + "\nWe ran 648 cells.\n").encode()}, "corpus.datasheet.card"),
    ],
)
def test_every_precondition_refuses_with_exit_4_and_writes_nothing(corpus, name, damage, changes, code):
    partial = corpus.with_name("mini.partial")
    if damage is not None:
        damage(partial)
    snapshot = fs_guard.snapshot(partial)
    with pytest.raises(AgentProvError) as info:
        seal(corpus, corpus_version="0.1.0", inputs=ss.inputs(**changes))
    assert info.value.exit_code == 4, name
    assert info.value.code == code, name
    fs_guard.assert_unchanged(snapshot, fs_guard.snapshot(partial))
    assert not corpus.exists()


def test_a_vouched_context_tree_and_a_skipped_role_are_sealed_in_corpus_0_2_d221(corpus):
    def change(m):
        m["sources"][0]["snapshots"][0]["context"] = [{"role": "tasks", "origin": None, "pin": TASKS_PIN, "stored": 0,
                                                        "verification": {"kind": "blob", "verified": 0, "unverified": 0}}]
        m["sources"][0]["snapshots"][0]["context_skipped"] = ["notes"]

    _rewrite(corpus.with_name("mini.partial"), change)
    seal(corpus, corpus_version="0.1.0", inputs=ss.inputs())
    manifest = _manifest(corpus)
    assert manifest["format"] == "agentprov-corpus/0.2" and manifest["ontology"]["version"] == "0.2.0"
    snapshot = manifest["sources"][0]["snapshots"][0]
    assert snapshot["context"] == [{"role": "tasks", "stored": 0, "verification": {"kind": "blob", "verified": 0, "unverified": 0},
                                    "origin": {"kind": "git", "repo": "https://github.com/example/tasks", "commit": "b" * 40,
                                               "subtree": ""}}]
    assert snapshot["context_skipped"] == ["notes"] and "pinned_objects" not in snapshot
    assert not [i for i in validate_manifest(manifest) if i.level != "info"]


def test_a_context_tree_of_an_unknown_verification_kind_is_refused_rc15(corpus):
    # re-check RC-15: corpus/0.2 seals context[].verification.kind as download or blob only; the seal refuses any
    # other kind before writing, and the manifest validator flags one
    def change(m):
        m["sources"][0]["snapshots"][0]["context"] = [{"role": "tasks", "origin": None, "pin": TASKS_PIN, "stored": 0,
                                                        "verification": {"kind": "git", "verified": 0, "unverified": 0}}]

    partial = corpus.with_name("mini.partial")
    _rewrite(partial, change)
    snapshot = fs_guard.snapshot(partial)
    with pytest.raises(PackageRefusedError) as info:
        seal(corpus, corpus_version="0.1.0", inputs=ss.inputs())
    assert info.value.exit_code == 4 and info.value.code == "package.refused.unverified"
    fs_guard.assert_unchanged(snapshot, fs_guard.snapshot(partial))
    assert not corpus.exists()


def test_the_manifest_schema_takes_only_the_two_context_verification_kinds_rc15(corpus):
    def change(m):
        m["sources"][0]["snapshots"][0]["context"] = [{"role": "tasks", "origin": None, "pin": TASKS_PIN, "stored": 0,
                                                        "verification": {"kind": "blob", "verified": 0, "unverified": 0}}]

    _rewrite(corpus.with_name("mini.partial"), change)
    seal(corpus, corpus_version="0.1.0", inputs=ss.inputs())
    manifest = _manifest(corpus)
    assert not [i for i in validate_manifest(manifest) if i.level != "info"]
    manifest["sources"][0]["snapshots"][0]["context"][0]["verification"]["kind"] = "git"
    # the closed vocabulary itself, not only the content digest any edit breaks (pre-round verification V-6)
    pointer = "/sources/0/snapshots/0/context/0/verification/kind"
    assert [(i.code, i.pointer) for i in validate_manifest(manifest) if i.pointer == pointer] == [("enum", pointer)]


@pytest.mark.parametrize("names", [("LICENSE", "license"), ("LICENSE", "notice.md")])
def test_licence_labels_that_collide_case_insensitively_are_refused(corpus, monkeypatch, names):
    # Defence in depth behind parse_spec: two labels with one collision key (G.3.6) would overwrite each other on a
    # case-insensitive volume, so the seal refuses them before writing anything.
    import agentprov.corpus.package as package

    real = package.parse_spec
    monkeypatch.setattr(package, "parse_spec", lambda data: replace(real(data), licence_files=names))
    supplied = {name: ss.inputs().licence_files["LICENSE"] for name in names}
    partial = corpus.with_name("mini.partial")
    snapshot = fs_guard.snapshot(partial)
    with pytest.raises(PackageRefusedError) as info:
        seal(corpus, corpus_version="0.1.0", inputs=ss.inputs(licence_files=supplied))
    assert info.value.exit_code == 4 and info.value.code == "package.refused.label_collision"
    fs_guard.assert_unchanged(snapshot, fs_guard.snapshot(partial))
    assert not corpus.exists()


def test_the_version_must_be_the_specs(corpus):
    with pytest.raises(PackageRefusedError) as info:
        seal(corpus, corpus_version="0.2.0", inputs=ss.inputs())
    assert info.value.exit_code == 4 and info.value.code == "package.refused.version"


def test_a_local_object_origin_is_refused_d33(corpus):
    from agentprov.raw.origins import Origin, OriginRow, decode_origins, encode_origins

    partial = corpus.with_name("mini.partial")
    path = partial / "raw" / "origins.jsonl"
    rows = decode_origins(path.read_bytes())
    rows.append(OriginRow(rows[0].sha256, Origin.local("/somewhere/else")))
    path.write_bytes(encode_origins(rows))
    with pytest.raises(PackageRefusedError) as info:
        seal(corpus, corpus_version="0.1.0", inputs=ss.inputs())
    assert info.value.exit_code == 4 and info.value.code == "package.refused.local_origin"


# ------------------------------------------------------------------------------------------------ corpus-level failures
def test_a_claim_that_does_not_hold_fails_the_build_with_exit_1(corpus):
    card = ss.CARD.replace("{{claim:raw_included}}", "{{claim:restricted_use}}")
    partial = corpus.with_name("mini.partial")
    snapshot = fs_guard.snapshot(partial)
    with pytest.raises(DatasheetError) as info:
        seal(corpus, corpus_version="0.1.0", inputs=ss.inputs(card=card.encode()))
    assert info.value.exit_code == 1 and info.value.code == "corpus.datasheet.claim"
    fs_guard.assert_unchanged(snapshot, fs_guard.snapshot(partial))


def test_a_failure_after_writing_rolls_the_working_tree_back(corpus, monkeypatch):
    import agentprov.corpus.package as package

    partial = corpus.with_name("mini.partial")
    before = ss.tree_bytes(partial)

    def broken(root):
        raise ManifestError("injected failure")

    monkeypatch.setattr(package, "write_checksums", broken)
    with pytest.raises(ManifestError):
        seal(corpus, corpus_version="0.1.0", inputs=ss.inputs())
    assert ss.tree_bytes(partial) == before
    assert (partial / "raw" / "tmp").is_dir() and not (partial / "rules").exists()
    assert not corpus.exists()


def test_the_compat_spec_must_have_output(corpus):
    spec = ss.SPEC.replace('prov_specs = ["agentprov-prov/0.1"]', 'prov_specs = ["agentprov-prov/0.1", "adprov-v2.3-compat"]')
    with pytest.raises(PackageRefusedError) as info:
        seal(corpus, corpus_version="0.1.0", inputs=ss.inputs(spec=spec.encode()))
    assert info.value.code == "package.refused.stages"


def test_seal_report_names_the_sealed_tree(corpus):
    report = seal(corpus, corpus_version="0.1.0", inputs=ss.inputs())
    assert report.root == corpus and report.corpus_id == "mini-agentdojo" and report.corpus_version == "0.1.0"
    from agentprov.corpus.integrity import root_digest

    assert report.root_digest == root_digest(corpus)
    assert report.content_digest == _manifest(corpus)["content_digest"]
    assert os.path.isfile(corpus / "checksums.sha256")


def test_inputs_are_replaceable():
    base = ss.inputs()
    assert replace(base, registry_date="x").registry_date == "x"


# ------------------------------------------------------------------------------------------------ an interrupted seal (CB-9)
def _killed_seal(corpus: Path, step: str) -> None:
    """Run :func:`seal` in a forked child that dies with no Python exception (``os._exit(137)``, as SIGKILL, the OOM
    killer or a power loss would) at ``step``: after ``corpus.json`` says ``sealed: true`` and before the swap."""
    import agentprov.corpus.package as package

    pid = os.fork()
    if pid == 0:  # pragma: no cover - the child never returns into pytest
        try:
            setattr(package, step, lambda _root: os._exit(137))
            seal(corpus, corpus_version="0.1.0", inputs=ss.inputs())
        finally:
            os._exit(1)
    _, status = os.waitpid(pid, 0)
    assert os.waitstatus_to_exitcode(status) == 137
    partial = corpus.with_name("mini.partial")
    assert not corpus.exists() and _manifest(partial)["sealed"] is True


@pytest.mark.parametrize("step", ["write_checksums", "_verify_chain"])
def test_a_seal_killed_before_the_swap_is_resumed(tmp_path_factory, tmp_path, step):
    from agentprov.corpus.package import _verify_chain

    killed = ss.working_corpus(tmp_path_factory, tmp_path / "a" / "mini")
    clean = ss.working_corpus(tmp_path_factory, tmp_path / "b" / "mini")
    _killed_seal(killed, step)
    report = seal(killed, corpus_version="0.1.0", inputs=ss.inputs())
    assert killed.is_dir() and not killed.with_name("mini.partial").exists()
    assert _manifest(killed)["sealed"] is True and verify_checksums(killed).ok
    _verify_chain(killed)
    expected = seal(clean, corpus_version="0.1.0", inputs=ss.inputs())
    assert ss.tree_bytes(killed) == ss.tree_bytes(clean)  # the resumed seal is the seal that was interrupted
    assert (report.root_digest, report.content_digest, dict(report.counters)) == (
        expected.root_digest, expected.content_digest, dict(expected.counters))


def _tamper_aer(partial: Path) -> None:
    path = next(p for p in sorted((partial / "aer").rglob("*")) if p.is_file())
    path.write_bytes(path.read_bytes() + b"\n")


@pytest.mark.parametrize(
    ("damage", "changes", "release"),
    [
        (_tamper_aer, {}, None),
        (lambda p: (p / "stray.txt").write_bytes(b"x"), {}, None),
        (None, {"card": (ss.CARD + "\nMore text.\n").encode()}, None),
        (None, {}, ReleaseArgs(release_date="2026-10-12")),
    ],
    ids=["tampered file", "stray file", "other card", "other release date"],
)
def test_an_interrupted_seal_that_does_not_check_out_is_refused(corpus, damage, changes, release):
    _killed_seal(corpus, "_verify_chain")
    partial = corpus.with_name("mini.partial")
    if damage is not None:
        damage(partial)
    snapshot = fs_guard.snapshot(partial)
    with pytest.raises(PackageRefusedError) as info:
        seal(corpus, corpus_version="0.1.0", inputs=ss.inputs(**changes), release=release)
    assert info.value.code == "corpus.seal.interrupted" and info.value.exit_code == 4
    fs_guard.assert_unchanged(snapshot, fs_guard.snapshot(partial))
    assert not corpus.exists()


def test_a_sealed_tree_below_a_sealed_corpus_is_not_resumed(corpus):
    _killed_seal(corpus, "_verify_chain")
    partial = corpus.with_name("mini.partial")
    (partial.parent / "corpus.json").write_text('{"sealed": true}\n', "utf-8")
    with pytest.raises(SealedCorpusError):
        seal(corpus, corpus_version="0.1.0", inputs=ss.inputs())


# ------------------------------------------------------------------------------------------------ gating checks (CB-10)
def _gate(fails: int, rows: list[tuple[str, str]], register: list[tuple[str, str]], results: list[tuple[str, str]]):
    """Call :func:`_check_gating` with one gating check ``sem.x`` failed ``fails`` times. ``rows`` are (ex, status) index
    rows, ``register`` (ex, code) entries and ``results`` (ex, sem.x outcome) rows of ``validation/results.jsonl``."""
    from types import SimpleNamespace as NS

    from agentprov.corpus.package import _check_gating

    manifest = {"validation": {"checks": [{"id": "sem.x", "fail": fails, "skipped": 0, "pass": 0}]}}
    _check_gating(manifest, [NS(ex=ex, status=status) for ex, status in rows],
                  [NS(code=code, subject={"ex": ex}) for ex, code in register],
                  [{"checks": {"sem.x": outcome}, "ex": ex} for ex, outcome in results])


def test_a_failed_gating_check_of_a_failed_row_registered_as_a_stage_failure_is_accepted():
    """derive/import register ``prov.failed`` (not ``validate.failed``) when PROV failed but tier-3 checks still ran."""
    _gate(1, [("B", "failed")], [("B", "prov.failed")], [("B", "fail")])


def test_a_failed_gating_check_is_judged_per_execution_not_by_any_registered_row():
    with pytest.raises(ManifestError) as info:
        _gate(2, [("A", "failed"), ("B", "failed")], [("A", "validate.failed")], [("A", "fail"), ("B", "fail")])
    assert info.value.code == "corpus.manifest.validation"


def test_one_registered_row_does_not_cover_more_gating_failures_than_it_has():
    with pytest.raises(ManifestError) as info:
        _gate(5, [("A", "failed"), ("C", "ok")], [("A", "validate.failed")], [("A", "fail"), ("C", "pass")])
    assert info.value.code == "corpus.manifest.validation"


# ------------------------------------------------------------------------------------- redistribution class (CB-15b)
def _redistribution(derived: str, policy: str = "include") -> str:
    """The ``licences.redistribution`` :func:`_licences` records for a derived licence ``derived`` under ``policy``."""
    from types import SimpleNamespace as NS

    from agentprov.corpus.package import _licences

    spec = NS(corpus_id="mini-nc" if policy == "nc_partition" else "mini", licence_derived=derived,
              licence_decided_by="tester", licence_files=(), source=NS(source_id="src"))
    profile = {"licence": {"basis": "LICENSE", "policy": policy, "spdx": derived}, "profile": {"id": "p", "version": 1}}
    raw_policy = "include" if policy in ("include", "nc_partition") else policy
    return _licences(spec, profile, raw_policy, "2026-10-14")["redistribution"]  # type: ignore[arg-type]


@pytest.mark.parametrize(("derived", "expected"), [
    ("PolyForm-Noncommercial-1.0.0", "permitted-non-commercial"),
    ("CC-BY-NC-4.0", "permitted-non-commercial"),
    ("CC-BY-NC-SA-4.0", "permitted-non-commercial"),
    ("MIT", "permitted"),
    ("CC-BY-4.0", "permitted"),
])  # fmt: skip
def test_redistribution_uses_the_per_term_non_commercial_predicate(derived, expected):
    """Same predicate as the release licence class (H.10.6): ``…Noncommercial…`` is non-commercial, not only ``-NC``."""
    assert _redistribution(derived) == expected


def test_the_nc_partition_policy_stays_non_commercial():
    assert _redistribution("MIT", "nc_partition") == "permitted-non-commercial"


# ------------------------------------------------------------------------------------------------ D-960: archived aprov
def _prov_stage_rules(partial: Path, rules_sha256: str, version: int | None) -> None:
    path = partial / "derivation.json"
    derivation = json.loads(path.read_text("utf-8"))
    for stage in derivation["stages"]:
        if stage.get("stage") == "prov":
            stage["rules_sha256"] = rules_sha256
            if version is None:
                stage.pop("rules", None)
            else:
                stage["rules"] = {"aprov": version}
    path.write_text(json.dumps(derivation, sort_keys=True, indent=2) + "\n", "utf-8")


@pytest.mark.parametrize("record_version", [True, False])  # rules {aprov: n}, or the digest alone (prov_catalogue_version)
def test_a_corpus_built_under_an_archived_aprov_catalogue_is_sealed_with_that_catalogue_d960(corpus, record_version):
    """D-930 keeps a stored corpus at the aprov version it was built under; D-960 seals it with that version's byte-exact
    archive. The fixture is built at the current catalogue and relabelled as v(n-1): this test is about what package
    reads and records, not about the PROV documents."""
    from importlib import resources

    from agentprov.corpus.authority import check_sealed_rules, package_resources
    from agentprov.io.canonical import sha256_hex
    from agentprov.prov.specs import archived_catalogue_sha256, load_spec, parse_spec_catalogue

    older = load_spec().catalogue_version - 1
    digest = archived_catalogue_sha256(older)
    assert digest is not None
    archived = resources.files("agentprov.prov").joinpath("catalogue", "archive", f"agentprov-prov-0.1.v{older}.toml").read_bytes()
    _prov_stage_rules(corpus.with_name("mini.partial"), "sha256:" + digest, older if record_version else None)
    seal(corpus, corpus_version="0.1.0", inputs=ss.inputs())
    assert (corpus / "rules" / "prov" / "agentprov-prov-0.1.toml").read_bytes() == archived
    manifest = json.loads((corpus / "corpus.json").read_text("utf-8"))
    aprov = next(e for e in manifest["rule_catalogues"] if e["id"] == "aprov")
    assert (aprov["version"], aprov["sha256"]) == (older, "sha256:" + sha256_hex(archived))
    assert aprov["n_rules"] == len(parse_spec_catalogue(archived).rules)
    assert verify_checksums(corpus).ok
    assert check_sealed_rules(manifest, lambda label: (corpus / label).read_bytes() if (corpus / label).is_file() else None,
                              package_resources()) == []


def test_a_prov_catalogue_of_unknown_bytes_is_still_refused_d960(corpus):
    partial = corpus.with_name("mini.partial")
    _prov_stage_rules(partial, "sha256:" + "0" * 64, None)
    snapshot = fs_guard.snapshot(partial)
    with pytest.raises(AgentProvError) as info:
        seal(corpus, corpus_version="0.1.0", inputs=ss.inputs())
    assert (info.value.exit_code, info.value.code) == (4, "package.refused.catalogue")
    fs_guard.assert_unchanged(snapshot, fs_guard.snapshot(partial))
    assert not corpus.exists()
