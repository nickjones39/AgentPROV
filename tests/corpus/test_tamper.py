"""Tampering detected by ``agentprov verify`` at the level that detects it (K.12.5, K.12.15; SEC-15; Q.19; HL-T2, T14, T15).

Every case runs the CLI with ``--json`` and checks the exit code and the finding code in the summary. The K.12.5 rows and
where they are covered:

=====================================================================  ============================================
row                                                                     test (level)
=====================================================================  ============================================
one byte changed in a raw artefact                                      ``test_raw_byte`` (checksums, chain, rederive)
``corpus.json`` / ``executions.jsonl`` edited                           ``test_manifest_or_index_edited`` (checksums;
                                                                        chain after a regenerated checksums file)
``checksums.sha256`` regenerated over tampered files                    ``test_regenerated_checksums_*`` (root digest;
                                                                        chain through the AER -> SEM -> PROV chain)
forged AER seal (right count, wrong hash)                               ``test_forged_aer_seal`` (chain)
forged raw origin (blob id does not match the bytes)                    ``test_forged_raw_origin`` (chain
                                                                        ``--against-pins``)
forged derived file, checksums and manifest regenerated                 ``test_forged_derived_file`` (rederive)
archive member object altered                                           ``test_member_*`` (chain: CRC-32/size; rederive:
                                                                        inputs re-hashed, ``expand`` re-run)
``REFERENCES.json`` origin that no in-package profile pins              ``test_unpinned_reference`` (chain)
AER lines reordered (references valid / a reference made forward)       ``test_reordered_aer_lines`` (chain;
                                                                        ``validate --corpus`` names the order code)
swapped ``rules/`` copy; unshipped catalogue version (K.12.15)          ``test_swapped_rules_copy``,
                                                                        ``test_unshipped_catalogue_version`` (chain)
sealed corpus targeted by a writer                                      ``test_writers_refuse_a_sealed_corpus``
a stray file (closed world; HL-T2)                                      ``test_stray_file`` (checksums)
=====================================================================  ============================================

Not ``verify`` cases (covered where they are detected): capture/0.1 event reordering (SEC-16, capture verifier), embedded
PROV claims and claimed times (SEC-17, SEC-18, import), one source key claimed twice (SEC-19, ``test_dedup``). Deposit
archives: ``test_deposit_verify.py``.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import pytest
import verify_support as vs

from agentprov.testing import fs_guard


def codes(run: Any) -> dict[str, int]:
    return dict(run.json()["issues_by_code"])


def verify(cli: Any, root: Path, *flags: str) -> Any:
    return cli("verify", "--corpus", str(root), "--json", *flags)


def flip_byte(path: Path, offset: int = 10) -> None:
    path.chmod(0o644)  # stored raw objects are read-only
    data = bytearray(path.read_bytes())
    data[offset] ^= 0x01
    path.write_bytes(bytes(data))


# ------------------------------------------------------------------------------------------------ baseline
@pytest.mark.parametrize("level", ["checksums", "chain", "rederive"])
def test_an_untampered_sealed_corpus_passes_every_level_read_only(cli, sealed, check_summary, level):
    digest = vs.root_digest(sealed)
    with fs_guard.unchanged(sealed):
        run = verify(cli, sealed, "--level", level, "--root-digest", digest)
    assert run.code == 0, run.err
    document = run.json()
    check_summary(document)
    assert document["failures"] == [] and document["issues_by_code"] == {}
    assert document["counters"]["files_matched"] == document["counters"]["files_listed"] > 0
    assert document["corpus"]["state"] == "sealed" and document["corpus"]["corpus_id"] == "mini-mit"
    if level != "checksums":
        assert document["counters"]["executions_checked"] == 3 and document["counters"]["raw_objects"] == 3
    if level == "rederive":
        assert document["counters"]["rederive_identical"] == 3
    assert f"root digest {digest}" in run.err


# ------------------------------------------------------------------------------------------------ K.12.5 rows
def test_raw_byte(cli, sealed):
    target = vs.first_file(sealed, "raw/objects")
    flip_byte(target)
    run = verify(cli, sealed, "--level", "checksums")
    assert run.code == 1 and codes(run) == {"checksums.mismatch": 1}
    run = verify(cli, sealed, "--level", "chain")
    assert run.code == 1 and "raw.digest.mismatch" in codes(run)
    vs.regenerate_checksums(sealed)  # even with the checksums regenerated, the object no longer hashes to its address
    run = verify(cli, sealed, "--level", "chain")
    assert run.code == 1 and codes(run).get("raw.digest.mismatch") == 1
    run = verify(cli, sealed, "--level", "rederive")
    assert run.code == 1 and "raw.digest.mismatch" in codes(run)  # inputs re-hashed before anything is derived


@pytest.mark.parametrize("name", ["corpus.json", "executions.jsonl"])
def test_manifest_or_index_edited(cli, sealed, name):
    digest = vs.root_digest(sealed)
    path = sealed / name
    if name == "corpus.json":
        m = vs.manifest(sealed)
        m["title"] = m["title"] + " (edited)"
        path.write_bytes((json.dumps(m, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode())
    else:
        items = vs.rows(sealed)
        items[0]["completeness"] = "known_incomplete" if items[0]["completeness"] != "known_incomplete" else "unverifiable"
        vs.write_jsonl(path, items)
    run = verify(cli, sealed, "--level", "checksums")
    assert run.code == 1 and codes(run) == {"checksums.mismatch": 1}
    vs.regenerate_checksums(sealed)
    run = verify(cli, sealed, "--level", "checksums", "--root-digest", digest)
    assert run.code == 1 and codes(run) == {"root_digest.mismatch": 1}
    run = verify(cli, sealed, "--level", "chain")
    expected = "manifest.content_digest" if name == "corpus.json" else "index.completeness"
    assert run.code == 1 and expected in codes(run)


def test_regenerated_checksums_over_a_tampered_prov_file_fail_the_chain(cli, sealed):
    digest = vs.root_digest(sealed)
    prov = vs.first_file(sealed, "prov")
    document = json.loads(prov.read_bytes())
    document["agent"]["sw:agentprov"]["apv:softwareName"] = "forged"
    prov.write_bytes(json.dumps(document).encode())
    vs.regenerate_checksums(sealed)
    assert verify(cli, sealed, "--level", "checksums").code == 0  # the regenerated checksums cover the forgery
    run = verify(cli, sealed, "--level", "checksums", "--root-digest", digest)
    assert run.code == 1 and codes(run) == {"root_digest.mismatch": 1}
    run = verify(cli, sealed, "--level", "chain")
    assert run.code == 1 and codes(run) == {"index.digest.prov": 1}  # the AER seal -> SEM -> PROV digest chain


def test_regenerated_checksums_over_a_datasheet_edit_are_detected_only_by_the_root_digest(cli, sealed):
    """A file no digest chain covers (DATASHEET.md) with ``checksums.sha256`` regenerated: every level passes; only
    the root digest published outside the corpus detects it (D-39)."""
    digest = vs.root_digest(sealed)
    datasheet = sealed / "DATASHEET.md"
    datasheet.write_bytes(datasheet.read_bytes() + b"\nAn added sentence.\n")
    vs.regenerate_checksums(sealed)
    for level in ("checksums", "chain", "rederive"):
        assert verify(cli, sealed, "--level", level).code == 0, level
    run = verify(cli, sealed, "--level", "checksums", "--root-digest", digest)
    assert run.code == 1 and codes(run) == {"root_digest.mismatch": 1}
    run = verify(cli, sealed, "--release", "--root-digest", digest)
    assert run.code == 1 and "root_digest.mismatch" in codes(run)
    assert verify(cli, sealed, "--release", "--root-digest", vs.root_digest(sealed)).code == 0


def test_forged_aer_seal(cli, sealed):
    aer = vs.first_file(sealed, "aer")
    lines = aer.read_bytes().splitlines(keepends=True)
    seal = json.loads(lines[-1])
    seal["records_sha256"] = hashlib.sha256(b"forged").hexdigest()  # the count stays right, the hash is wrong
    from agentprov.aer.canon import dumps_line

    aer.write_bytes(b"".join(lines[:-1]) + dumps_line(seal))
    vs.regenerate_checksums(sealed)
    run = verify(cli, sealed, "--level", "chain")
    assert run.code == 1 and codes(run) == {"aer.seal.digest": 1}


def test_forged_raw_origin(cli, sealed):
    origins = sealed / "raw" / "origins.jsonl"
    items = [json.loads(line) for line in origins.read_text("utf-8").splitlines()]
    items[0]["origin"]["blob_sha1"] = "0" * 40
    vs.write_jsonl(origins, items)
    vs.reforge(sealed)  # files.origins, content digest and checksums made consistent
    assert verify(cli, sealed, "--level", "chain").code == 0
    run = verify(cli, sealed, "--level", "chain", "--against-pins")
    assert run.code == 1 and codes(run).get("raw.origin.blob_mismatch") == 1
    assert codes(run).get("raw.origin.listing_unavailable") == 1  # no cached tree listing: unverified, never passed


def test_forged_derived_file(cli, sealed):
    """A forged PROV file whose index digest, manifest digests and checksums were all regenerated passes ``chain``;
    ``rederive`` re-derives from raw with package catalogues and detects it (SEC-15)."""
    prov = vs.first_file(sealed, "prov")
    ex = prov.name.split(".", 1)[0]
    document = json.loads(prov.read_bytes())
    document["agent"]["sw:agentprov"]["apv:softwareName"] = "forged"
    data = json.dumps(document).encode()
    prov.write_bytes(data)

    def index(row: dict[str, Any]) -> None:
        if row["ex"] == ex:
            row["digests"]["prov"]["agentprov-prov/0.1"]["json"] = "sha256:" + hashlib.sha256(data).hexdigest()

    vs.reforge(sealed, index=index)
    assert verify(cli, sealed, "--level", "chain").code == 0
    run = verify(cli, sealed, "--level", "rederive")
    assert run.code == 1 and codes(run) == {"rederive.unexplained_change": 1}
    failure = run.json()["failures"][0]
    assert failure["subject"] == {"ex": ex} and "prov:agentprov-prov/0.1" in failure["detail"]


def test_reordered_aer_lines(cli, sealed):
    from agentprov.aer.canon import dumps_line

    aer = vs.first_file(sealed, "aer")
    lines = aer.read_bytes().splitlines(keepends=True)
    records = [json.loads(line) for line in lines]
    # references still valid: swap two actor records
    actors = [i for i, r in enumerate(records) if r.get("k") == "actor"][:2]
    swapped = list(lines)
    swapped[actors[0]], swapped[actors[1]] = lines[actors[1]], lines[actors[0]]
    aer.write_bytes(b"".join(swapped))
    vs.regenerate_checksums(sealed)
    run = verify(cli, sealed, "--level", "chain")
    assert run.code == 1 and codes(run) == {"aer.seal.digest": 1}
    # a reference made forward, and the seal recomputed by the attacker: the index digest no longer matches
    child = next(i for i, r in enumerate(records) if "parent" in r)
    parent = next(i for i, r in enumerate(records) if r.get("id") == records[child]["parent"])
    moved = list(lines)
    moved.insert(parent, moved.pop(child))
    seal = json.loads(moved[-1])
    seal["records_sha256"] = hashlib.sha256(b"".join(moved[:-1])).hexdigest()
    moved[-1] = dumps_line(seal)
    aer.write_bytes(b"".join(moved))
    vs.regenerate_checksums(sealed)
    run = verify(cli, sealed, "--level", "chain")
    assert run.code == 1 and codes(run) == {"index.digest.aer": 1}


def test_swapped_rules_copy(cli, sealed):
    """K.12.15: a corpus whose ``rules/`` copy was swapped gives ``rules.mismatch``; rederive still derives from the
    package catalogues (HL-T15)."""
    copy = sealed / "rules" / "agentdojo.rules.toml"
    copy.write_bytes(copy.read_bytes() + b"\n# swapped\n")
    vs.regenerate_checksums(sealed)
    run = verify(cli, sealed, "--level", "chain")
    assert run.code == 1 and codes(run) == {"rules.mismatch": 1}
    run = verify(cli, sealed, "--level", "rederive")
    assert codes(run) == {"rules.mismatch": 1} and run.json()["counters"]["rederive_identical"] == 3


def test_unshipped_catalogue_version(cli, sealed):
    def change(m: dict[str, Any]) -> None:
        for entry in m["rule_catalogues"]:
            if entry["id"] == "agentdojo":
                entry["version"] = 99

    vs.reforge(sealed, change=change)
    run = verify(cli, sealed, "--level", "chain")
    assert run.code == 0 and codes(run) == {"rules.unavailable": 1}  # unverified: reported, not passed
    assert run.json()["failures"][0]["detail"].startswith("unverified:")
    run = verify(cli, sealed, "--level", "chain", "--release", "--root-digest", vs.root_digest(sealed))
    assert run.code == 1 and codes(run) == {"rules.unavailable": 1}  # release mode: unverified fails


def test_stray_file(cli, sealed):
    (sealed / ".DS_Store").write_bytes(b"x")
    run = verify(cli, sealed, "--level", "checksums")
    assert run.code == 1 and codes(run) == {"corpus.tree.stray": 1}


# ------------------------------------------------------------------------------------------------ members (AD-12)
@pytest.fixture(scope="module")
def inspect_working_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The 177-sample Inspect working corpus, imported once per module (each test tampers with its own copy)."""
    import derive_support as ds

    template = ds.partial(ds.inspect_corpus(tmp_path_factory.mktemp("inspect-template")))
    assert not any(p.is_symlink() for p in template.rglob("*"))  # a copy can never write through into the template
    return template


@pytest.fixture
def inspect_working(inspect_working_template: Path, tmp_path: Path) -> Path:
    """A fresh copy of the template, byte for byte and mode for mode (raw objects stay read-only)."""
    copy = tmp_path / inspect_working_template.name
    shutil.copytree(inspect_working_template, copy, symlinks=True)
    return copy


def test_member_crc32_disagreeing_with_members_jsonl(cli, inspect_working):
    path = inspect_working / "raw" / "members.jsonl"
    items = [json.loads(line) for line in path.read_text("utf-8").splitlines()]
    selected = next(i for i in items if i["disposition"] == "selected")
    selected["crc32"] = "%08x" % ((int(selected["crc32"], 16) + 1) % (1 << 32))
    vs.write_jsonl(path, items)
    run = verify(cli, inspect_working, "--level", "chain")
    assert run.code == 1 and codes(run).get("raw.member.crc32") == 1
    selected["size"] += 1
    vs.write_jsonl(path, items)
    assert codes(verify(cli, inspect_working, "--level", "chain")).get("raw.member.size") == 1


def test_member_object_altered(cli, inspect_working):
    path = inspect_working / "raw" / "members.jsonl"
    member = next(json.loads(line) for line in path.read_text("utf-8").splitlines() if '"selected"' in line)
    sha = member["sha256"][7:]
    target = next((inspect_working / "raw" / "objects" / sha[:2]).glob(sha + "*"))
    flip_byte(target)
    run = verify(cli, inspect_working, "--level", "chain")
    assert run.code == 1 and "raw.digest.mismatch" in codes(run) and "raw.member.crc32" in codes(run)
    run = verify(cli, inspect_working, "--level", "rederive")
    assert run.code == 1 and "raw.digest.mismatch" in codes(run)


# ------------------------------------------------------------------------------------------------ references (R-43)
def test_unpinned_reference(cli, tmp_path):
    import derive_support as ds

    working = ds.partial(ds.agentdojo_corpus(tmp_path))
    document = {"format": "agentprov-raw-references/0.1", "objects": [{
        "bytes": 10, "origins": [{"blob_sha1": "1" * 40, "commit": "2" * 40, "kind": "git", "path": "runs/x.json",
                                  "repo": "https://github.com/example/unpinned"}],
        "reason": "size", "sha256": "sha256:" + "3" * 64}]}
    (working / "raw" / "REFERENCES.json").write_bytes(json.dumps(document).encode())
    run = verify(cli, working, "--level", "chain")
    assert run.code == 1 and codes(run).get("raw.reference.unpinned_origin") == 1


# ------------------------------------------------------------------------------------------------ writers
def test_writers_refuse_a_sealed_corpus(cli, sealed, tmp_path):
    import seal_support as ss

    spec = tmp_path / "specs" / "corpora" / "mini-mit" / "corpus-spec.toml"
    spec.parent.mkdir(parents=True)
    spec.write_bytes(ss.SPEC.encode())
    shutil.copy(ss.REPO / "corpora" / "datasheet-statements.toml", spec.parent.parent / "datasheet-statements.toml")
    shutil.copy(sealed / "rules" / "CARD.md", spec.parent / "CARD.md")
    shutil.copy(sealed / "rules" / "CHANGES.toml", spec.parent / "CHANGES.toml")
    with fs_guard.unchanged(sealed):
        assert cli("package", "--corpus", str(sealed), "--corpus-version", "0.1.0", "--spec", str(spec)).code == 4
        assert cli("recompute", "--corpus", str(tmp_path / "x"), "--out", str(sealed)).code in (2, 4)
        assert cli("recompute", "--corpus", str(sealed), "--out", str(sealed)).code == 4


def _forge_status(root: Path, before: str, after: str) -> str:
    """A consistent forgery (CB-11): one row's status changed, ``counts.by_status`` adjusted, every digest recomputed."""
    rows = vs.rows(root)
    target = next(r["ex"] for r in rows if r["status"] == before)

    def index(row: dict[str, Any]) -> None:
        if row["ex"] == target:
            row["status"] = after

    def change(manifest: dict[str, Any]) -> None:
        by_status = manifest["counts"]["by_status"]
        by_status[before] -= 1
        by_status[after] = by_status.get(after, 0) + 1

    vs.reforge(root, index=index, change=change)
    return target


@pytest.mark.parametrize(("before", "after"), [("ok", "failed"), ("ok", "ok_with_issues")])
def test_cb11_a_consistently_forged_row_status_fails_chain_and_rederive(cli, sealed, before, after):
    """CB-11 (H.3.2(1)): chain recomputes each row's status from its stages and its issues' register severities, and
    rederive reports index rows that differ outside their outputs. Only the published root digest caught this before."""
    statuses = {r["status"] for r in vs.rows(sealed)}
    if before not in statuses:
        pytest.skip(f"the sealed fixture has no {before} row")
    assert verify(cli, sealed, "--level", "chain").code == 0
    ex = _forge_status(sealed, before, after)
    run = verify(cli, sealed, "--level", "chain")
    assert run.code == 1 and codes(run) == {"index.status": 1}, codes(run)
    assert ex in run.out
    run = verify(cli, sealed, "--level", "rederive")
    assert run.code == 1 and codes(run).get("rederive.index_refreshed") == 1, codes(run)
