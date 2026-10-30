"""SEC-15: the corpus tamper matrix (G.10 SEC-15; K.12.5; HL H.5; T-13, T-14).

Every file kind of a sealed corpus (``sec15_support.KINDS``) is edited, removed, added and reordered, and three things
are asserted through ``agentprov verify --json``:

1. against the corpus's own ``checksums.sha256``, the ``checksums`` level fails with the one code that names the change
   (``checksums.mismatch``, ``.missing`` or ``.unlisted``);
2. after the attacker regenerates ``checksums.sha256``, the ``checksums`` level passes, and only the root digest
   published outside the corpus detects the change (``root_digest.mismatch``, D-39), also under ``--release``;
3. the ``chain`` level, over the regenerated checksums, fails with the code that names the broken link of H.5.1, or, for
   the files no digest chain covers (H.5.5: ``DATASHEET.md``, ``CHANGELOG.md``, ``LICENSES/**``), passes: those are
   detected by the root digest alone. That boundary is pinned here, so a change to it is visible (sec-coverage-12c.md,
   proposals P-1 and P-2). Since P-1 and P-2 were implemented (branch ``fix-12c-findings``), orphan execution files fail
   ``chain`` with ``index.orphan``, ``schemas/**`` with ``schemas.mismatch``, and an added ``WITHHELD.json`` or view
   with ``withheld.undeclared`` / ``views.undeclared``.

Further cases: a consistent forgery that hides a removed raw object behind a tombstone (reported ``tombstoned``, never
passed in release mode) or behind a reference (finding F-12C-01), and the ``chain`` level's CRC-32 check on a **sealed**
corpus with archive members (``slow``: it seals the Inspect AgentHarm test corpus). The phase-11 tests in
``tests/corpus/test_tamper.py`` cover the K.12.5 rows one by one; this file is the systematic matrix.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import corpus_harness as harness
import pytest
import sec15_support as t
import verify_support as vs  # on the path through corpus_harness
from corpus_harness import verify

cli = harness.cli  # the fixtures of corpus_harness, bound in this module so pytest finds them
sealed = harness.sealed

#: Files no H.5.1 digest chain covers: the root digest is their only anchor (H.5.3, H.5.5; D-39).
#: ``schemas/**`` left this set with P-2 (compared with the package's published schemas: ``schemas.mismatch``).
ROOT_ONLY = frozenset({"datasheet", "changelog", "licence_derived", "licence_source", "licence_notice"})

#: kind -> the primary code the ``chain`` level must report after an **edit** with regenerated checksums.
EDIT_CHAIN = {
    "manifest": "manifest.invalid",  # the first string leaf of corpus.json is part of its schema-checked body
    "index": "index.invalid",
    "register": "corpus.read.invalid",
    "derivation": "manifest.files",
    "origins": "corpus.read.invalid",
    "members": "corpus.read.invalid",
    "raw_object": "raw.digest.mismatch",
    "aer": "aer.seal.digest",
    "sem": "sem.seal.digest",
    "prov": "index.digest.prov",
    "validation_results": "index.digest.validation",
    "validation_summary": "manifest.validation",
    "rules_catalogue": "rules.mismatch",
    "rules_prov": "rules.mismatch",
    "rules_source_profile": "rules.mismatch",
    "rules_semantics": "rules.mismatch",
    "rules_spec": "manifest.files",
    "rules_card": "manifest.files",
    "rules_changes": "manifest.files",
    "schema": "schemas.mismatch",  # P-2: a byte copy of a package resource
}

#: kind -> the primary ``chain`` code after a **removal** with regenerated checksums.
REMOVE_CHAIN = {
    "index": "index.invalid",
    "register": "corpus.read.missing",
    "derivation": "manifest.files",
    "origins": "corpus.read.missing",
    "members": "corpus.read.missing",
    "raw_object": "raw.object.missing",
    "aer": "corpus.read.missing",
    "sem": "corpus.read.missing",
    "prov": "corpus.read.missing",
    "validation_results": "index.digest.validation",
    "validation_summary": "manifest.files",
    "rules_catalogue": "rules.mismatch",
    "rules_prov": "rules.mismatch",
    "rules_source_profile": "rules.mismatch",
    "rules_semantics": "rules.mismatch",
    "rules_spec": "manifest.files",
    "rules_card": "manifest.files",
    "rules_changes": "manifest.files",
    "schema": "schemas.mismatch",  # P-2: a schema sealing writes is absent
}

#: kind -> the primary ``chain`` code after a **reorder** (``None``: the reorder is not semantic, root digest only).
REORDER_CHAIN = {
    "manifest": None,  # key order: the content digest is over JCS (H.5.4), so only the root digest sees it
    "index": "index.invalid",
    "register": "corpus.read.invalid",
    "derivation": "manifest.files",
    "origins": "corpus.read.invalid",
    "aer": "aer.format",
    "sem": "sem.format",
    "prov": "index.digest.prov",
    "validation_results": "index.digest.validation",
    "validation_summary": "manifest.files",
    "schema": "schemas.mismatch",  # P-2: compared byte for byte with the package resource
}

#: kind -> the primary ``chain`` code after an **add** (``None``: root digest only).
ADD_CHAIN = {
    "raw_object": "manifest.digests",  # the raw set digest recomputes over the listed objects (H.2.11)
    "aer": "index.orphan",  # an orphan execution file: no index row names it (P-1, fixed: no longer root digest only)
    "sem": "index.orphan",
    "prov": "index.orphan",
    "licence_source": None,
    "rules_catalogue": None,  # an unlisted rules/ file: no manifest entry names it, nothing loads it (AD-14)
}


def _cases() -> list[Any]:
    out = []
    for kind in t.KINDS:
        out.append(pytest.param(kind, "edit", None if kind in ROOT_ONLY else EDIT_CHAIN[kind], id=f"{kind}-edit"))
        if kind != "manifest":
            out.append(pytest.param(kind, "remove", None if kind in ROOT_ONLY else REMOVE_CHAIN[kind],
                                    id=f"{kind}-remove"))
        if kind in ADD_CHAIN:
            out.append(pytest.param(kind, "add", ADD_CHAIN[kind], id=f"{kind}-add"))
        if kind in REORDER_CHAIN:
            out.append(pytest.param(kind, "reorder", REORDER_CHAIN[kind], id=f"{kind}-reorder"))
    return out


def _tamper(root: Path, kind: str, op: str) -> str:
    pick, fmt = t.KINDS[kind]
    label = pick(root)
    if op == "edit":
        t.edit(root, label, fmt)
    elif op == "remove":
        t.remove(root, label)
    elif op == "add":
        added = t.add(root, kind)
        assert added is not None
        return added
    else:
        assert t.reorder(root, label, fmt)
    return label


@pytest.mark.parametrize(("kind", "op", "chain_code"), _cases())
def test_sec15_every_sealed_file_kind_edited_removed_added_or_reordered_is_detected(cli, sealed, kind, op, chain_code):
    published = vs.root_digest(sealed)
    _tamper(sealed, kind, op)

    # 1. against the corpus's own checksums: the checksums level names the change
    expected = {"edit": "checksums.mismatch", "reorder": "checksums.mismatch", "remove": "checksums.missing",
                "add": "checksums.unlisted"}[op]
    run = verify(cli, sealed, "--level", "checksums")
    assert run.code == 1 and run.codes() == {expected: 1}, run.codes()

    # 2. the attacker regenerates checksums.sha256: only the published root digest detects it
    vs.regenerate_checksums(sealed)
    assert verify(cli, sealed, "--level", "checksums").code == 0
    run = verify(cli, sealed, "--level", "checksums", "--root-digest", published)
    assert run.code == 1 and run.codes() == {"root_digest.mismatch": 1}
    run = verify(cli, sealed, "--level", "checksums", "--release", "--root-digest", published)
    assert run.code == 1 and "root_digest.mismatch" in run.codes()

    # 3. the chain level, over the regenerated checksums
    run = verify(cli, sealed, "--level", "chain")
    if chain_code is None:
        assert run.code == 0 and run.codes() == {}, run.codes()  # the D-39 boundary: root digest only
    else:
        assert run.code == 1 and chain_code in run.codes(), run.codes()
        assert all(f["detail"].startswith("failed:") for f in run.json()["failures"]
                   if f["code"] == chain_code)


def test_sec15_a_reordered_checksums_file_is_malformed_and_every_line_is_named_by_number(cli, sealed):
    assert t.reorder(sealed, "checksums.sha256", "text")
    run = verify(cli, sealed, "--level", "checksums")
    found = run.codes()
    assert run.code == 1 and set(found) <= {"checksums.malformed", "checksums.unlisted"}
    assert found["checksums.malformed"] >= 1
    assert all(f["subject"]["path"].startswith("#") for f in run.json()["failures"] if f["code"] == "checksums.malformed")


def test_sec15_an_edited_or_removed_checksums_file(cli, sealed):
    published = vs.root_digest(sealed)
    path = sealed / "checksums.sha256"
    lines = path.read_bytes().splitlines(keepends=True)
    path.write_bytes(lines[0][:5] + (b"0" if lines[0][5:6] != b"0" else b"1") + lines[0][6:] + b"".join(lines[1:]))
    run = verify(cli, sealed, "--level", "checksums", "--root-digest", published)
    assert run.code == 1 and run.codes() == {"checksums.mismatch": 1, "root_digest.mismatch": 1}
    path.unlink()
    run = verify(cli, sealed, "--level", "checksums")
    assert run.code == 1 and run.codes() == {"checksums.absent": 1}
    run = verify(cli, sealed, "--level", "checksums", "--root-digest", published)
    assert run.code == 1 and "root_digest.unverifiable" in run.codes()


@pytest.mark.parametrize("level", ["checksums", "chain", "rederive"])
def test_sec15_a_removed_manifest_leaves_no_sealed_corpus_to_verify(cli, sealed, level):
    """Without ``corpus.json`` the directory is not a sealed corpus (N.1.5): every level refuses it (exit 2), never
    passes it."""
    (sealed / "corpus.json").unlink()
    run = verify(cli, sealed, "--level", level)
    assert run.code == 2


@pytest.mark.parametrize("what", ["withheld", "view"])
def test_sec15_an_added_optional_file_is_detected_by_chain_and_the_root_digest(cli, sealed, what):
    """``WITHHELD.json`` and ``views/**`` are grammar files (H.1.2) the corpus does not have. Added with regenerated
    checksums they passed ``chain`` before P-2; now ``chain`` reconciles them with the manifest and ``derivation.json``
    (``withheld.undeclared``, ``views.undeclared``), and the root digest still detects them."""
    from agentprov.corpus.layout import shard

    published = vs.root_digest(sealed)
    if what == "withheld":
        (sealed / "WITHHELD.json").write_bytes(b'{"withheld": []}\n')
    else:
        ex = vs.rows(sealed)[0]["ex"]
        target = sealed / "views" / "transcript-v1" / shard(ex, 1) / f"{ex}.transcript.json"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"{}")
    assert verify(cli, sealed, "--level", "checksums").codes() == {"checksums.unlisted": 1}
    vs.regenerate_checksums(sealed)
    run = verify(cli, sealed, "--level", "chain")
    if what == "withheld":  # since D-230 the file is also parsed and needs its schema copy
        assert run.code == 1 and run.codes() == {"withheld.undeclared": 1, "withheld.invalid": 1,
                                                 "schemas.mismatch": 1}, run.codes()
    else:
        assert run.code == 1 and run.codes() == {"views.undeclared": 1}, run.codes()
    if what == "view":  # P-2 positive control: with a views stage the same view of an indexed execution is declared
        from agentprov.corpus.derive import views_stage_definition

        derivation = json.loads((sealed / "derivation.json").read_text("utf-8"))
        derivation["stages"].append(views_stage_definition())
        (sealed / "derivation.json").write_bytes((json.dumps(derivation, sort_keys=True, indent=2) + "\n").encode())
        vs.reforge(sealed)
        assert "views.undeclared" not in verify(cli, sealed, "--level", "chain").codes()
    run = verify(cli, sealed, "--level", "checksums", "--root-digest", published)
    assert run.code == 1 and run.codes() == {"root_digest.mismatch": 1}


# ------------------------------------------------------------------------------------------------ consistent forgeries
def _first_origin(root: Path) -> tuple[dict[str, Any], str, str]:
    origin = json.loads((root / "raw" / "origins.jsonl").read_text("utf-8").splitlines()[0])
    sha = origin["sha256"][len("sha256:"):]
    return origin, sha, f"raw/objects/{sha[:2]}/{sha}.json"


def test_sec15_a_raw_object_hidden_behind_a_forged_tombstone_is_reported_and_fails_release_mode(cli, sealed):
    """The attacker deletes an included raw object, adds a ``raw/tombstones.jsonl`` row for it and regenerates the
    manifest and the checksums. The object is reported ``tombstoned`` (H.5.5: never silently missing): dev mode exits 0
    with the finding listed, release mode fails, and the published root digest detects the forgery."""
    from agentprov.corpus.purge import Tombstone, encode_tombstones

    published = vs.root_digest(sealed)
    _, sha, label = _first_origin(sealed)
    t.remove(sealed, label)
    (sealed / "raw" / "tombstones.jsonl").write_bytes(encode_tombstones([Tombstone(sha, "secret", "2026-10-12")]))
    vs.regenerate_checksums(sealed)
    run = verify(cli, sealed, "--level", "chain")
    assert run.code == 1 and {"manifest.digests", "raw.tombstoned"} <= set(run.codes())  # checksums only regenerated
    vs.reforge(sealed)
    run = verify(cli, sealed, "--level", "chain")
    assert run.code == 0 and run.codes() == {"raw.tombstoned": 1}
    assert run.json()["failures"][0]["detail"].startswith("tombstoned: purged 2026-10-12 (secret)")
    run = verify(cli, sealed, "--level", "chain", "--release", "--root-digest", vs.root_digest(sealed))
    assert run.code == 1 and run.codes() == {"raw.tombstoned": 1}
    run = verify(cli, sealed, "--level", "checksums", "--root-digest", published)
    assert run.code == 1 and run.codes() == {"root_digest.mismatch": 1}


def _hide_behind_reference(root: Path) -> None:
    origin, _, label = _first_origin(root)
    size = (root / label).stat().st_size
    t.remove(root, label)
    document = {"format": "agentprov-raw-references/0.1", "objects": [
        {"bytes": size, "origins": [origin["origin"]], "reason": "size", "sha256": origin["sha256"]}]}
    (root / "raw" / "REFERENCES.json").write_bytes(json.dumps(document).encode())


def test_sec15_a_raw_object_hidden_behind_a_forged_reference_with_only_the_checksums_regenerated_fails(cli, sealed):
    _hide_behind_reference(sealed)
    vs.regenerate_checksums(sealed)
    run = verify(cli, sealed, "--level", "chain")
    # raw.reference.not_permitted since the F-12C-01 fix (the snapshot's raw policy is include); references.undeclared
    # since D-237 (the manifest's files declare no references ledger)
    assert run.code == 1 and run.codes() == {"manifest.digests": 1, "raw.reference.not_permitted": 1,
                                             "references.undeclared": 1}


def test_sec15_a_raw_object_hidden_behind_a_forged_reference_is_never_passed_silently(cli, sealed):
    """F-12C-01, fixed. The attacker deletes an included raw object, writes a ``raw/REFERENCES.json`` entry that points
    at its real pinned origin (so ``raw.reference.unpinned_origin`` does not fire) and regenerates the manifest and
    checksums. The snapshot's ``raw_policy`` is ``include``, so the referenced object is a failure
    (``raw.reference.not_permitted``; H.4.1) in dev and release mode. Before the fix there was no finding at all and only
    the published root digest detected it."""
    published = vs.root_digest(sealed)
    _hide_behind_reference(sealed)
    vs.reforge(sealed)
    assert verify(cli, sealed, "--level", "checksums", "--root-digest", published).code == 1  # the anchor holds
    for mode in ((), ("--release", "--root-digest", vs.root_digest(sealed))):
        run = verify(cli, sealed, "--level", "chain", *mode)
        assert run.code == 1 and run.codes() == {"raw.reference.not_permitted": 1}


def test_sec15_a_referenced_object_of_a_reference_policy_snapshot_is_not_a_finding(cli, sealed):
    """The F-12C-01 check distinguishes the legitimate case by what the manifest declares (H.4.1): when the object's
    snapshot has raw policy ``reference``, a ``REFERENCES.json`` entry for it is expected and no finding is raised (this
    build seals no such corpus, so the manifest is rewritten consistently)."""
    def as_reference(m: dict[str, Any]) -> None:
        for source in m["sources"]:
            for snapshot in source["snapshots"]:
                snapshot["raw_policy"] = "reference"
        m["licences"]["policy"] = {"licence_policy": "reference", "raw_policy": "reference"}

    _hide_behind_reference(sealed)
    vs.reforge(sealed, change=as_reference)
    run = verify(cli, sealed, "--level", "chain", "--release", "--root-digest", vs.root_digest(sealed))
    assert run.code == 0 and run.codes() == {}, run.codes()
    assert run.json()["counters"]["raw_referenced"] == 1


# ------------------------------------------------------------------------------------------------ chain CRC, sealed
@pytest.fixture(scope="module")
def sealed_members_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The Inspect AgentHarm test corpus (one ``.eval`` archive, 177 selected members), imported in release mode and
    sealed with the in-repo spec ``corpora/ast-survey-agentharm`` (synthetic licence texts)."""
    from dataclasses import replace
    from importlib import resources

    import derive_support as ds
    import seal_support as ss

    from agentprov.corpus.package import LicenceFile, seal

    final = ds.inspect_corpus(tmp_path_factory.mktemp("sealed-members"), in_process=False, mode="release", workers=1)
    inspect = resources.files("agentprov").joinpath("adapters", "inspect")
    semantics = inspect.joinpath("semantics", "inspect.agentharm-2")
    inputs = replace(
        ss.inputs(),
        **ss.committed_spec("ast-survey-agentharm"),
        source_profile=inspect.joinpath("profiles", "survey-agentharm.profile.toml").read_bytes(),
        semantics_profiles={"inspect.agentharm@2": {c.name: c.read_bytes() for c in sorted(
            semantics.iterdir(), key=lambda c: c.name) if c.is_file()}},
        licence_files={"LICENSE": LicenceFile(b"test licence text\n", "supplied at sealing (test)"),
                       "AgentHarm-LICENSE": LicenceFile(b"test licence text 2\n", "supplied at sealing (test)")},
    )
    seal(final, corpus_version="0.1.0", inputs=inputs)
    return final


@pytest.fixture
def sealed_members(sealed_members_template: Path, tmp_path: Path) -> Path:
    import shutil

    dest = tmp_path / "corpora" / sealed_members_template.name
    shutil.copytree(sealed_members_template, dest, symlinks=True)
    return dest


def _selected(root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    items = [json.loads(line) for line in (root / "raw" / "members.jsonl").read_text("utf-8").splitlines()]
    return items, next(i for i in items if i["disposition"] == "selected")


@pytest.mark.slow
def test_sec15_chain_checks_member_crc32_and_size_on_a_sealed_corpus_even_after_a_consistent_forgery(cli, sealed_members):
    """AD-12; HL-T14: a ``raw/members.jsonl`` row whose CRC-32 (then size) disagrees with the stored member object fails
    ``chain``, with only the checksums regenerated and with the manifest regenerated too (a consistent forgery of the
    members file cannot hide it: the CRC-32 is recomputed from the object bytes)."""
    published = vs.root_digest(sealed_members)
    assert verify(cli, sealed_members, "--level", "chain").code == 0
    items, selected = _selected(sealed_members)
    selected["crc32"] = "%08x" % ((int(selected["crc32"], 16) + 1) % (1 << 32))
    vs.write_jsonl(sealed_members / "raw" / "members.jsonl", items)
    vs.regenerate_checksums(sealed_members)
    run = verify(cli, sealed_members, "--level", "chain")
    assert run.code == 1 and run.codes().get("raw.member.crc32") == 1
    assert {"manifest.files", "manifest.digests"} <= set(run.codes())
    vs.reforge(sealed_members)
    run = verify(cli, sealed_members, "--level", "chain")
    assert run.code == 1 and run.codes() == {"raw.member.crc32": 1}
    selected["size"] += 1
    vs.write_jsonl(sealed_members / "raw" / "members.jsonl", items)
    vs.reforge(sealed_members)
    run = verify(cli, sealed_members, "--level", "chain")
    assert run.code == 1 and run.codes() == {"raw.member.crc32": 1, "raw.member.size": 1}
    run = verify(cli, sealed_members, "--level", "checksums", "--root-digest", published)
    assert run.code == 1 and run.codes() == {"root_digest.mismatch": 1}


@pytest.mark.slow
def test_sec15_chain_detects_an_altered_member_object_on_a_sealed_corpus(cli, sealed_members):
    _, selected = _selected(sealed_members)
    sha = selected["sha256"][len("sha256:"):]
    label = next((sealed_members / "raw" / "objects" / sha[:2]).glob(sha + ".*")).relative_to(sealed_members).as_posix()
    t.edit(sealed_members, label, "bytes")
    run = verify(cli, sealed_members, "--level", "checksums")
    assert run.code == 1 and run.codes() == {"checksums.mismatch": 1}
    vs.regenerate_checksums(sealed_members)
    run = verify(cli, sealed_members, "--level", "chain")
    assert run.code == 1 and {"raw.digest.mismatch", "raw.member.crc32"} <= set(run.codes())


# ------------------------------------------------------------------------------------------------ WITHHELD.json, REFERENCES.json
# D-230..D-237: the rows of the matrix for the two optional ledgers. The withheld corpus is the purged and re-versioned
# test corpus of ``withheld_harness`` (one object and one execution withheld after a purge).
@pytest.fixture
def withheld(tmp_path_factory: pytest.TempPathFactory, tmp_path: Path) -> dict[str, Any]:
    import withheld_harness as wh

    return wh.purged_sealed(tmp_path_factory, tmp_path / "corpora")


def _withheld_doc(root: Path) -> dict[str, Any]:
    return json.loads((root / "WITHHELD.json").read_text("utf-8"))


def _write_withheld(root: Path, doc: dict[str, Any]) -> None:
    (root / "WITHHELD.json").write_bytes((json.dumps(doc, sort_keys=True, indent=2) + "\n").encode())


def test_sec15_withheld_control_the_sealed_withheld_corpus_passes_release_mode(cli, withheld):
    root = withheld["root"]
    run = verify(cli, root, "--level", "chain", "--release", "--root-digest", vs.root_digest(root))
    assert run.code == 0 and run.codes() == {}, run.codes()


@pytest.mark.parametrize(("op", "codes"), [
    ("edit", {"manifest.files"}),  # a changed note: the file no longer matches files.withheld
    ("reorder", {"manifest.files"}),  # same content, other bytes: the FileRef is over the bytes
    ("remove", {"manifest.files", "raw.tombstoned", "withheld.unlisted"}),
])  # fmt: skip
def test_sec15_withheld_json_edited_reordered_or_removed_with_checksums_regenerated(cli, withheld, op, codes):
    root = withheld["root"]
    published = vs.root_digest(root)
    if op == "edit":
        doc = _withheld_doc(root)
        doc["entries"][0]["public_note"] = "nothing to see here"
        _write_withheld(root, doc)
    elif op == "reorder":
        doc = _withheld_doc(root)
        (root / "WITHHELD.json").write_bytes(json.dumps(doc, indent=1).encode())
    else:
        (root / "WITHHELD.json").unlink()
    vs.regenerate_checksums(root)
    run = verify(cli, root, "--level", "chain")
    assert run.code == 1 and codes <= set(run.codes()), run.codes()
    run = verify(cli, root, "--level", "checksums", "--root-digest", published)
    assert run.code == 1 and run.codes() == {"root_digest.mismatch": 1}


def test_sec15_a_consistent_forgery_that_unlists_the_purged_object_fails_release_mode(cli, withheld):
    """The attacker drops the ledger (its only entry and execution) and regenerates the manifest and checksums: the
    tombstone is no longer accepted and the register still withholds the execution."""
    root = withheld["root"]
    (root / "WITHHELD.json").unlink()  # an empty ledger is not a valid document: the forger removes it
    vs.reforge(root, change=lambda m: m["files"].pop("withheld"))
    run = verify(cli, root, "--level", "chain", "--release", "--root-digest", vs.root_digest(root))
    assert run.code == 1 and {"raw.tombstoned", "withheld.unlisted"} <= set(run.codes()), run.codes()


def test_sec15_withheld_bytes_put_back_into_the_corpus_are_detected(cli, withheld):
    """The withheld execution's AER (from the private sidecar) and a withheld object put back with a consistent manifest
    and checksums: ``withheld.present`` (and the AER is an orphan, P-1)."""
    root, sidecar = withheld["root"], withheld["sidecar"]
    (aer,) = [p for p in sidecar.rglob("*.aer.jsonl")]
    target = root / aer.relative_to(sidecar)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(aer.read_bytes())
    sha = withheld["leak"]
    obj = root / "raw" / "objects" / sha[:2] / f"{sha}.json"
    obj.parent.mkdir(parents=True, exist_ok=True)
    obj.write_bytes(b'{"forged": true}')  # any bytes: the digest is the label, which is what WITHHELD.json lists
    vs.reforge(root)
    run = verify(cli, root, "--level", "chain")
    found = run.codes()
    assert run.code == 1 and found.get("withheld.present", 0) >= 2 and "index.orphan" in found, found


def test_sec15_a_withheld_execution_put_back_into_the_index_is_detected(cli, withheld):
    root, sidecar = withheld["root"], withheld["sidecar"]
    rows = vs.rows(root) + [json.loads(line) for line in (sidecar / "executions.jsonl").read_bytes().split(b"\n") if line]
    vs.write_jsonl(root / "executions.jsonl", sorted(rows, key=lambda r: r["ex"]))
    vs.reforge(root)
    run = verify(cli, root, "--level", "chain")
    assert run.code == 1 and "withheld.row" in run.codes(), run.codes()


def test_sec15_withheld_origins_that_differ_from_raw_origins_are_detected(cli, withheld):
    root = withheld["root"]
    doc = _withheld_doc(root)
    doc["entries"][0]["origins"][0]["path"] = "runs/elsewhere.json"
    _write_withheld(root, doc)
    vs.reforge(root)
    run = verify(cli, root, "--level", "chain")
    assert run.code == 1 and run.codes() == {"withheld.origins": 1}, run.codes()


def test_sec15_a_withheld_json_without_its_schema_copy_is_detected(cli, withheld):
    root = withheld["root"]
    (root / "schemas" / "withheld-0.1.schema.json").unlink()
    vs.regenerate_checksums(root)
    run = verify(cli, root, "--level", "chain")
    assert run.code == 1 and run.codes() == {"schemas.mismatch": 1}, run.codes()


def test_sec15_a_released_row_of_a_withhold_snapshot_is_detected(cli, sealed):
    def withhold(m: dict[str, Any]) -> None:
        for source in m["sources"]:
            for snapshot in source["snapshots"]:
                snapshot["raw_policy"] = "withhold"

    vs.reforge(sealed, change=withhold)
    run = verify(cli, sealed, "--level", "chain")
    assert run.code == 1 and set(run.codes()) == {"withheld.policy"} and run.codes()["withheld.policy"] == 3


def test_sec15_references_json_declared_and_edited_is_detected(cli, sealed):
    """D-237: a declared ``raw/REFERENCES.json`` is checked by ``manifest.files``; an undeclared one by
    ``references.undeclared`` (see the forged-reference rows above)."""
    def as_reference(m: dict[str, Any]) -> None:
        for source in m["sources"]:
            for snapshot in source["snapshots"]:
                snapshot["raw_policy"] = "reference"
        m["licences"]["policy"] = {"licence_policy": "reference", "raw_policy": "reference"}

    _hide_behind_reference(sealed)
    vs.reforge(sealed, change=as_reference)
    assert vs.manifest(sealed)["files"]["references"]["path"] == "raw/REFERENCES.json"
    assert verify(cli, sealed, "--level", "chain").codes() == {}
    path = sealed / "raw" / "REFERENCES.json"
    doc = json.loads(path.read_text("utf-8"))
    doc["objects"][0]["reason"] = "licence-unclear"
    path.write_bytes(json.dumps(doc).encode())
    vs.regenerate_checksums(sealed)
    run = verify(cli, sealed, "--level", "chain")
    assert run.code == 1 and run.codes() == {"manifest.files": 1}, run.codes()
