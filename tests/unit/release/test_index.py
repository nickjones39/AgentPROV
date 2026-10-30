"""``agentprov.release.index`` and the uploader's index kind (HL H.10.7; D-941 L-5, D-947).

Part deposits are built by the real builder from the sealed test corpora (``release_support``) and drafted on the fake
Zenodo of ``zenodo_fake`` (127.0.0.1; nothing contacts zenodo.org or the sandbox), so their receipts are the uploader's
own. The index is then built from those receipts and the sealed corpora, checked, drafted on the same fake server as the
umbrella, and cross-linked with the parts. The corpus deposits themselves must stay byte-identical.
"""

from __future__ import annotations

import hashlib
import io
import json
import shutil
from pathlib import Path
from typing import Any

import agentprov_zenodo.draft as zd
import pytest
import release_support as rs
from zenodo_fake import FakeZenodo

from agentprov.release.builder import DEPOSIT_MANIFEST, DEPOSIT_MANIFEST_FORMAT, DepositRefusedError
from agentprov.release.index import (
    COLLECTION_INDEX,
    COLLECTION_INDEX_FORMAT,
    INDEX_KIND,
    INDEX_MANIFEST_FORMAT,
    RECEIPT_FORMAT,
    RECEIPT_TARGETS,
    build_index,
    check_index_deposit,
)
from agentprov.release.verify import verify_deposit

CANARY = "ZENODO-CANARY-TOKEN-5d2e8a7c19f04b36e1aa"
PHRASE = "create unpublished draft on sandbox.zenodo.org"
INDEX_METADATA = rs.METADATA.__class__(title="AgentPROV test collection", creators=rs.METADATA.creators,
                                       keywords=("test",), description_preamble="An index built by the test suite.")


class Run:
    def __init__(self, code: int, out: str, err: str) -> None:
        self.code, self.out, self.err = code, out, err


def go(args: list[str], server: FakeZenodo | None, *, phrase: str = PHRASE) -> Run:
    out, err = io.StringIO(), io.StringIO()
    code = zd.run(args, environ={"ZENODO_SANDBOX_TOKEN": CANARY}, stdout=out, stderr=err,
                  input_fn=lambda prompt: phrase, interactive=lambda: True,
                  test_base_url=None if server is None else server.base, release_verify=False)
    return Run(code, out.getvalue(), err.getvalue())


def receipt(directory: Path, target: str = "sandbox") -> Path:
    return directory.parent / f"{directory.name}.zenodo-{target}-draft-receipt.json"


def tree(directory: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(directory.iterdir())}


@pytest.fixture
def server():
    fake = FakeZenodo(CANARY).start()
    yield fake
    fake.stop()
    assert fake.violations == [], fake.violations  # nothing outside the allowlist, never a publish


@pytest.fixture(scope="module")
def templates(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """Two sealed corpora and one part deposit for each (not drafted yet)."""
    base = tmp_path_factory.mktemp("index-template")
    (base / "parts").mkdir()
    out: dict[str, Path] = {}
    for corpus_id, record in (("mini-mit", "r1-mit"), ("mini-mit-b", "r2-mit-b")):
        sealed = rs.sealed(tmp_path_factory, base / "corpora", corpus_id)
        rs.build([sealed], base / "parts" / record)
        out[corpus_id], out[record] = sealed, base / "parts" / record
    return out


@pytest.fixture
def collection(templates: dict[str, Path], tmp_path: Path, server: FakeZenodo) -> dict[str, Any]:
    """Fresh copies of the corpora and parts, each part drafted (receipt ``complete``)."""
    corpora = {cid: tmp_path / "corpora" / cid for cid in ("mini-mit", "mini-mit-b")}
    for cid, dest in corpora.items():
        shutil.copytree(templates[cid], dest)
    parts = {}
    (tmp_path / "parts").mkdir()
    for record in ("r1-mit", "r2-mit-b"):
        dest = tmp_path / "parts" / record
        shutil.copytree(templates[record], dest)
        run = go([str(dest), "--target", "sandbox", "--create-draft", "--community", "agentprov"], server)
        assert run.code == 0, run.err
        parts[record] = dest
    return {"corpora": corpora, "parts": parts, "receipts": [receipt(d) for d in parts.values()], "tmp": tmp_path}


def build(c: dict[str, Any], out: Path | None = None, **kwargs: Any) -> Path:
    out = out or c["tmp"] / "index"
    kwargs.setdefault("release_date", rs.RELEASE_DATE)
    kwargs.setdefault("producer", rs.PRODUCER)
    build_index(kwargs.pop("parts", c["receipts"]), kwargs.pop("corpora", list(c["corpora"].values())),
                kwargs.pop("metadata", INDEX_METADATA), out, **kwargs)
    return out


def _json(path: Path) -> Any:
    return json.loads(path.read_text("utf-8"))


# ================================================================================================ the index
def test_the_index_lists_each_part_and_corpus_with_the_digests_and_holds_no_archive(collection):
    from agentprov.corpus.integrity import root_digest

    out = build(collection)
    names = sorted(p.name for p in out.iterdir())
    assert names == sorted(["COLLECTION-INDEX.json", "DATASHEET-mini-mit-b.md", "DATASHEET-mini-mit.md",
                            "DEPOSIT-MANIFEST.json", "README.md", "deposit-metadata.json"])
    assert not [n for n in names if n.endswith(".zip")]
    index = _json(out / COLLECTION_INDEX)
    assert index["format"] == COLLECTION_INDEX_FORMAT and index["status"] == "draft-unpublished"
    assert index["target"] == {"host": "sandbox.zenodo.org", "name": "sandbox"}
    assert index["licence"] == {"restrictions": [], "spdx": "CC-BY-4.0"}
    assert [p["record"] for p in index["parts"]] == ["r1-mit", "r2-mit-b"]
    for part, cid in zip(index["parts"], ("mini-mit", "mini-mit-b"), strict=True):
        data = _json(receipt(collection["parts"][part["record"]]))
        assert part["reserved_doi"] == data["reserved_doi"] and part["record_id"] == data["reserved_recid"]
        assert part["deposition_id"] == data["deposition_id"] and part["communities"] == ["agentprov"]
        assert part["licence_class"] == {"restrictions": [], "spdx": "MIT"}
        (corpus,) = part["corpora"]
        sealed = collection["corpora"][cid]
        assert corpus["corpus_id"] == cid and corpus["corpus_version"] == "0.1.0"
        assert corpus["root_digest"] == root_digest(sealed)
        assert corpus["content_digest"] == rs.manifest(sealed)["content_digest"]
        assert corpus["licence_class"] == {"restrictions": [], "spdx": "MIT"}
        assert (out / corpus["datasheet"]["name"]).read_bytes() == (sealed / "DATASHEET.md").read_bytes()
        part_manifest = _json(collection["parts"][part["record"]] / DEPOSIT_MANIFEST)
        assert corpus["archives"] == part_manifest["corpora"][0]["archives"]
    manifest = _json(out / DEPOSIT_MANIFEST)
    assert manifest["format"] == INDEX_MANIFEST_FORMAT and manifest["kind"] == INDEX_KIND
    assert manifest["licence_class"] == {"restrictions": [], "spdx": "CC-BY-4.0"}
    assert manifest["counts"] == {"corpora": 2, "parts": 2} and "archives" not in manifest
    assert sorted(d["name"] for d in manifest["documents"]) == sorted(set(names) - {DEPOSIT_MANIFEST})
    meta = _json(out / "deposit-metadata.json")
    assert meta["licences"] == [{"archives": [], "corpora": [], "documents": sorted(set(names) - {DEPOSIT_MANIFEST}),
                                 "restrictions": [], "spdx": "CC-BY-4.0"}]
    assert meta["version_doi"] is None and meta["status"] == "draft-unpublished"
    has_part = [r["identifier"] for r in meta["related_identifiers"] if r["relation"] == "HasPart"]
    assert has_part == sorted(p["reserved_doi"] for p in index["parts"])
    readme = (out / "README.md").read_text("utf-8")
    assert "no corpus data" in readme and "Nothing has been uploaded or published." in readme
    assert check_index_deposit(out).problems == []


def test_two_builds_are_byte_identical_and_the_argument_order_does_not_matter(collection):
    first = build(collection)
    second = build(collection, collection["tmp"] / "index2", parts=collection["receipts"][::-1],
                   corpora=list(collection["corpora"].values())[::-1])
    assert tree(first) == tree(second)


def test_the_corpus_deposits_are_byte_identical_after_d947(templates, collection, tmp_path):
    """D-947 is class 0 for deposits: building an index reads a part and changes nothing in it, and a corpus deposit is
    still the builder's unchanged output (format 0.1, no ``kind``), which the uploader still checks as before."""
    before = {r: tree(d) for r, d in collection["parts"].items()}
    build(collection)
    assert {r: tree(d) for r, d in collection["parts"].items()} == before
    again = tmp_path / "rebuilt" / "r1-mit"
    again.parent.mkdir()
    rs.build([collection["corpora"]["mini-mit"]], again)
    assert tree(again) == tree(templates["r1-mit"]) == before["r1-mit"]
    manifest = _json(again / DEPOSIT_MANIFEST)
    assert manifest["format"] == DEPOSIT_MANIFEST_FORMAT and "kind" not in manifest
    check = go([str(again), "--target", "sandbox", "--check"], None)
    assert check.code == 0, check.err
    assert "Kind: collection index" not in check.out


def test_a_dry_run_checks_everything_and_writes_nothing(collection):
    out = collection["tmp"] / "index"
    report = build_index(collection["receipts"], list(collection["corpora"].values()), INDEX_METADATA, out,
                         release_date=rs.RELEASE_DATE, producer=rs.PRODUCER, dry_run=True)
    assert report.dry_run and not out.exists() and not out.with_name("index.partial").exists()
    assert report.counters["parts"] == 2 and report.counters["corpora"] == 2


def test_the_generated_texts_pass_the_claims_lint(collection):
    from agentprov.cli.deposit import _lint

    build(collection, lint=_lint)


def test_the_constants_match_the_uploaders():
    assert RECEIPT_FORMAT == zd.RECEIPT_FORMAT
    assert dict(RECEIPT_TARGETS) == {name: t.host for name, t in zd.TARGETS.items()}


# ================================================================================================ refusals
def _edit(path: Path, **changes: Any) -> None:
    data = _json(path)
    data.update(changes)
    path.write_text(json.dumps(data), "utf-8")


@pytest.mark.parametrize(("change", "code"), [
    ({"status": "uploading"}, "release.refused.index_incomplete"),
    ({"reserved_doi": None}, "release.refused.index_receipt"),
    ({"format": "agentprov-zenodo-draft-receipt/0.1"}, "release.refused.index_receipt"),
    ({"draft_dir": "elsewhere"}, "release.refused.index_receipt"),
    ({"host": "zenodo.org"}, "release.refused.index_receipt"),
])
def test_a_receipt_that_is_not_a_complete_draft_with_a_doi_is_refused(collection, change, code):
    _edit(collection["receipts"][1], **change)
    with pytest.raises(DepositRefusedError) as exc:
        build(collection)
    assert exc.value.code == code and not (collection["tmp"] / "index").exists()


def test_a_part_changed_since_its_upload_is_refused(collection):
    manifest = collection["parts"]["r2-mit-b"] / DEPOSIT_MANIFEST
    manifest.write_bytes(manifest.read_bytes().replace(b'"draft-unpublished"', b'"draft-unpublishe "'))
    with pytest.raises(DepositRefusedError) as exc:
        build(collection)
    assert exc.value.code == "release.refused.index_part_changed"


def test_a_part_directory_that_is_not_beside_its_receipt_is_refused(collection):
    shutil.rmtree(collection["parts"]["r1-mit"])
    with pytest.raises(DepositRefusedError) as exc:
        build(collection)
    assert exc.value.code == "release.refused.index_part_missing"


def test_every_corpus_has_exactly_one_part(collection, templates, server):
    corpora = list(collection["corpora"].values())
    with pytest.raises(DepositRefusedError) as exc:
        build(collection, corpora=corpora[:1])
    assert exc.value.code == "release.refused.index_corpus_missing"
    with pytest.raises(DepositRefusedError) as exc:
        build(collection, parts=collection["receipts"][:1])
    assert exc.value.code == "release.refused.index_corpus_extra"
    twice = collection["tmp"] / "parts" / "r3-mit-again"
    shutil.copytree(templates["r1-mit"], twice)
    assert go([str(twice), "--target", "sandbox", "--create-draft"], server).code == 0
    with pytest.raises(DepositRefusedError) as exc:
        build(collection, parts=[*collection["receipts"], receipt(twice)])
    assert exc.value.code == "release.refused.index_duplicate"


def test_a_receipt_given_twice_or_two_targets_are_refused(collection):
    with pytest.raises(DepositRefusedError) as exc:
        build(collection, parts=[collection["receipts"][0], collection["receipts"][0]])
    assert exc.value.code == "release.usage"
    part = collection["parts"]["r2-mit-b"]
    production = receipt(part, "production")
    receipt(part).rename(production)
    _edit(production, target="production", host="zenodo.org")
    with pytest.raises(DepositRefusedError) as exc:
        build(collection, parts=[collection["receipts"][0], production])
    assert exc.value.code == "release.refused.index_targets"


def test_a_corpus_that_is_not_the_one_the_part_holds_is_refused(collection):
    root = collection["corpora"]["mini-mit-b"]
    rs.restamp(root, lambda m: m.update(title=m["title"] + " (changed)"))
    with pytest.raises(DepositRefusedError) as exc:
        build(collection)
    assert exc.value.code == "release.refused.index_corpus_mismatch"


def test_an_existing_output_is_refused(collection):
    (collection["tmp"] / "index").mkdir()
    with pytest.raises(DepositRefusedError) as exc:
        build(collection)
    assert exc.value.code == "release.refused.index_exists"


# ================================================================================================ the uploader
def test_the_uploader_drafts_the_index_and_cross_links_it_as_the_umbrella(collection, server):
    out = build(collection)
    before = tree(out)
    check = go([str(out), "--target", "sandbox", "--check"], None)
    assert check.code == 0, check.err
    assert "Kind: collection index (no corpus data; COLLECTION-INDEX.json lists 2 part record(s)" in check.out
    assert "This creates an unpublished draft; nothing is published." in check.out
    assert "Licence: cc-by-4.0" in check.out
    run = go([str(out), "--target", "sandbox", "--create-draft", "--community", "agentprov"], server)
    assert run.code == 0, run.err
    assert tree(out) == before
    umbrella = _json(receipt(out))
    assert umbrella["status"] == "complete" and umbrella["reserved_doi"]
    stored = server.depositions[umbrella["deposition_id"]]
    assert set(stored["files"]) == set(before)
    phrase = "link 3 unpublished drafts on sandbox.zenodo.org"
    link = go(["--target", "sandbox", "--cross-link", "--umbrella", str(receipt(out)),
               *(a for r in collection["receipts"] for a in ("--member", str(r)))], server, phrase=phrase)
    assert link.code == 0, link.err
    members = [_json(r) for r in collection["receipts"]]
    related = server.depositions[umbrella["deposition_id"]]["metadata"]["related_identifiers"]
    assert sorted(r["identifier"] for r in related if r["relation"] == "hasPart") == sorted(
        m["reserved_doi"] for m in members)  # sent with the draft already; cross-linking added nothing twice
    assert len(related) == len({(r["identifier"], r["relation"]) for r in related})
    for member in members:
        assert {"identifier": umbrella["reserved_doi"], "relation": "isPartOf"} in (
            server.depositions[member["deposition_id"]]["metadata"]["related_identifiers"])


def test_the_uploader_refuses_a_root_digest_a_tampered_index_and_another_target(collection, server):
    out = build(collection)
    run = go([str(out), "--target", "sandbox", "--check", "--root-digest", "sha256:" + "a" * 64], None)
    assert run.code == 2 and "--root-digest belongs to corpus deposits" in run.err
    other = go([str(out), "--target", "production", "--check"], None)
    assert other.code == 4 and "built from sandbox receipts" in other.err
    sheet = out / "DATASHEET-mini-mit.md"
    sheet.write_bytes(sheet.read_bytes() + b"\n")
    seen = len(server.requests)
    tampered = go([str(out), "--target", "sandbox", "--create-draft"], server)
    assert tampered.code == 4 and "differ from DEPOSIT-MANIFEST.json" in tampered.err
    assert len(server.requests) == seen and not receipt(out).exists()


def test_the_index_check_finds_an_inconsistent_index(collection):
    out = build(collection)
    index = _json(out / COLLECTION_INDEX)
    index["parts"][1]["reserved_doi"] = index["parts"][0]["reserved_doi"]
    data = (json.dumps(index, sort_keys=True, indent=2) + "\n").encode()
    (out / COLLECTION_INDEX).write_bytes(data)
    manifest = _json(out / DEPOSIT_MANIFEST)
    for entry in manifest["documents"]:  # a consistent forgery of the manifest too: the index's shape still fails
        if entry["name"] == COLLECTION_INDEX:
            entry.update(bytes=len(data), sha256="sha256:" + hashlib.sha256(data).hexdigest(),
                         md5=hashlib.md5(data).hexdigest())
    (out / DEPOSIT_MANIFEST).write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", "utf-8")
    problems = check_index_deposit(out).problems
    assert problems == [f"{COLLECTION_INDEX}: two part records share a reserved DOI"]
    (out / "stray.txt").write_text("x")
    assert any("1 unlisted" in p for p in check_index_deposit(out).problems)


def test_archive_mode_verify_says_an_index_holds_no_archive(collection):
    out = build(collection)
    result = verify_deposit(out, level="chain")
    assert not result.passed()
    assert any("index deposit" in f.detail for f in result.findings)


# ================================================================================================ D-949
def test_a_copyleft_corpus_s_datasheet_is_linked_not_copied(collection, server, tmp_path_factory):
    """The CC-BY-4.0 index holds no datasheet of a GPL corpus: its row names the part record's copy (D-949)."""
    gpl = rs.sealed(tmp_path_factory, collection["tmp"] / "corpora", "mini-gpl", derived="GPL-3.0-only")
    part = collection["tmp"] / "parts" / "r3-gpl"
    rs.build([gpl], part)
    run = go([str(part), "--target", "sandbox", "--create-draft"], server)
    assert run.code == 0, run.err
    out = build(collection, parts=[*collection["receipts"], receipt(part)],
                corpora=[*collection["corpora"].values(), gpl])
    assert not (out / "DATASHEET-mini-gpl.md").exists() and (out / "DATASHEET-mini-mit.md").is_file()
    index = _json(out / COLLECTION_INDEX)
    rows = {c["corpus_id"]: c for p in index["parts"] for c in p["corpora"]}
    sheet = rows["mini-gpl"]["datasheet"]
    assert sheet["location"] == "part" and sheet["name"] == "DATASHEET-mini-gpl.md"
    assert sheet["sha256"] == "sha256:" + hashlib.sha256((gpl / "DATASHEET.md").read_bytes()).hexdigest()
    assert rows["mini-mit"]["datasheet"]["location"] == "index"
    readme = (out / "README.md").read_text("utf-8")
    assert "not copied: copyleft licence class" in readme
    assert check_index_deposit(out).problems == []
    assert check_index_deposit(out).corpora == 3


def test_the_index_check_refuses_a_copied_copyleft_datasheet_location(collection, server, tmp_path_factory):
    gpl = rs.sealed(tmp_path_factory, collection["tmp"] / "corpora", "mini-gpl", derived="GPL-3.0-only")
    part = collection["tmp"] / "parts" / "r3-gpl"
    rs.build([gpl], part)
    assert go([str(part), "--target", "sandbox", "--create-draft"], server).code == 0
    out = build(collection, parts=[*collection["receipts"], receipt(part)],
                corpora=[*collection["corpora"].values(), gpl])
    index = _json(out / COLLECTION_INDEX)
    for p in index["parts"]:
        for c in p["corpora"]:
            if c["corpus_id"] == "mini-gpl":
                c["datasheet"]["location"] = "index"
    (out / COLLECTION_INDEX).write_text(json.dumps(index, sort_keys=True, indent=2) + "\n", "utf-8")
    problems = check_index_deposit(out).problems
    assert any("copyleft corpus's datasheet is linked" in p for p in problems)


def test_cross_link_refuses_members_that_are_not_the_index_s_parts(collection, server):
    out = build(collection)
    assert go([str(out), "--target", "sandbox", "--create-draft"], server).code == 0
    seen = len(server.requests)
    missing = go(["--target", "sandbox", "--cross-link", "--umbrella", str(receipt(out)),
                  "--member", str(collection["receipts"][0])], server, phrase="link 2 unpublished drafts on sandbox.zenodo.org")
    assert missing.code == 4 and "1 listed but not given, 0 given but not listed" in missing.err
    assert len(server.requests) == seen  # refused before any request
    (out / COLLECTION_INDEX).write_bytes((out / COLLECTION_INDEX).read_bytes() + b"\n")
    changed = go(["--target", "sandbox", "--cross-link", "--umbrella", str(receipt(out)),
                  *(a for r in collection["receipts"] for a in ("--member", str(r)))], server,
                 phrase="link 3 unpublished drafts on sandbox.zenodo.org")
    assert changed.code == 4 and "is not the file that was uploaded" in changed.err
    assert len(server.requests) == seen
