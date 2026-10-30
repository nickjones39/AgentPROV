"""``agentprov.corpus.rawtree.StoredRawTree``: a source corpus's raw store as the input tree of a re-map (D-30)."""

from __future__ import annotations

import hashlib
import json
import os

import derive_support as ds
import pytest

from agentprov.corpus.reader import CorpusReader
from agentprov.corpus.rawtree import StoredRawTree, StoredTreeError
from agentprov.corpus.register import RegisterEntry
from agentprov.testing import fs_guard


@pytest.fixture(scope="module")
def source(tmp_path_factory):
    return ds.agentdojo_corpus(tmp_path_factory.mktemp("rawtree"), count=2, until="aer")


def test_candidates_are_the_stored_objects_at_their_pinned_labels(source):
    with fs_guard.unchanged(ds.partial(source)):
        reader = CorpusReader.open(source)
        tree = StoredRawTree(reader)
        candidates = list(tree.walk())
        origins = [json.loads(line) for line in (ds.partial(source) / "raw" / "origins.jsonl").read_text().splitlines()]
        assert [c.label for c in candidates] == sorted(o["origin"]["path"] for o in origins)
        assert all(c.origin.kind == "git" for c in candidates)
        for candidate, data in tree.read(candidates):
            assert hashlib.sha256(data).hexdigest() == tree.sha256_of(candidate.label)
            assert candidate.size == len(data)
        assert tree.snapshot_origin() == json.loads((ds.partial(source) / "corpus.json").read_text())["sources"][0][
            "snapshots"][0]["origin"]


def test_a_tampered_object_is_never_returned(source, tmp_path):
    import shutil

    copy = tmp_path / "copy"
    shutil.copytree(ds.partial(source), ds.partial(copy))
    reader = CorpusReader.open(copy)
    tree = StoredRawTree(reader)
    label = tree.labels[0]
    path = next((ds.partial(copy) / "raw" / "objects").rglob(tree.sha256_of(label) + ".*"))
    os.chmod(path, 0o644)
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(StoredTreeError) as caught:
        tree.open(label)
    assert caught.value.code == "raw.digest.mismatch"


def test_corpus_origins_drop_the_pin_tree_leaf_and_unreproducible_rows_are_found(source):
    from agentprov.raw.origins import Origin

    reader = CorpusReader.open(source)
    tree = StoredRawTree(reader)
    tree._leaf = "corpus-prov"
    assert tree.label_for(Origin.corpus("AgentDojo-PROV", "2.3", "corpus-prov/m/x.transcript.json")) == "m/x.transcript.json"
    assert tree.label_for(Origin.local("/x/y")) is None
    stored = tree.labels[0]
    kept = RegisterEntry(subject={"snapshot_id": tree.snapshot_id, "path": stored}, code="dedup.collapsed", severity="info",
                         stage="select", disposition="sealed")
    member = RegisterEntry(subject={"snapshot_id": tree.snapshot_id, "path": stored + "!/m.json"},
                           code="select.not_execution_artefact", severity="info", stage="select", disposition="not_imported")
    excluded = RegisterEntry(subject={"snapshot_id": tree.snapshot_id, "path": "docs/README.md"},
                             code="select.not_execution_artefact", severity="info", stage="select", disposition="not_imported")
    assert tree.unreproducible([kept, member, excluded]) == [excluded]


# ---------------------------------------------------------------------------------------- sealed manifests (D-221)
class _FakeStore:
    objects_dir = "/nonexistent-agentprov-store"

    def __init__(self, blobs):
        self.blobs = blobs

    def size(self, sha):
        return len(self.blobs[sha])

    def open(self, sha):
        import io

        return io.BytesIO(self.blobs[sha])


class _FakeReader:
    """The reader calls ``StoredRawTree`` makes, over an in-memory manifest, origins and store (and rules files)."""

    def __init__(self, manifest, rows, blobs, files=None):
        self._manifest, self._rows, self._store, self._files = manifest, rows, _FakeStore(blobs), dict(files or {})

    def manifest(self):
        return self._manifest

    def derivation(self):
        return None

    def raw_store(self):
        return self._store

    def origins(self):
        return list(self._rows)

    def read_bytes(self, label, *, stored=False):
        return self._files[label]


def _blob(text):
    data = text.encode()
    return hashlib.sha256(data).hexdigest(), data


def _manifest(snapshots, *, sealed=True, profile=None, parts=("release",)):
    source = {"source_id": "s", "parts": list(parts), "snapshots": snapshots}
    if profile is not None:
        source["profile"] = profile
    manifest = {"sources": [source]}
    if sealed:
        manifest["sealed"] = True
    return manifest


C1, C2 = "1" * 40, "2" * 40
REPO = "https://github.com/example/runs"


def test_a_sealed_multi_snapshot_corpus_gives_each_snapshot_its_own_candidates():
    """Ultra raw-withhold #2: a sealed snapshot records no ``pin`` (D-221), so the D-202 filter matches its sealed origin."""
    from agentprov.raw.origins import Origin, OriginRow

    (sha_a, a), (sha_b, b) = _blob("a"), _blob("b")
    rows = [OriginRow(sha_a, Origin.git(REPO, C1, "runs/a.json", "a" * 40)),
            OriginRow(sha_b, Origin.git(REPO, C2, "runs/b.json", "b" * 40))]
    snapshots = [{"snapshot_id": "one", "origin": {"kind": "git", "repo": REPO, "commit": C1, "subtree": ""}},
                 {"snapshot_id": "two", "origin": {"kind": "git", "repo": REPO, "commit": C2, "subtree": ""}}]
    reader = _FakeReader(_manifest(snapshots), rows, {sha_a: a, sha_b: b})
    assert StoredRawTree(reader, snapshot_id="one").labels == ("runs/a.json",)
    assert StoredRawTree(reader, snapshot_id="two").labels == ("runs/b.json",)
    # the working form (pins, no seal) gives the same trees
    working = [{**s, "pin": {"kind": "git", "repo": REPO, "commit": s["origin"]["commit"]}} for s in snapshots]
    reader = _FakeReader(_manifest(working, sealed=False), rows, {sha_a: a, sha_b: b})
    assert StoredRawTree(reader, snapshot_id="one").labels == ("runs/a.json",)
    assert StoredRawTree(reader, snapshot_id="two").labels == ("runs/b.json",)


def test_a_sealed_multi_snapshot_archive_input_finds_its_container():
    """Ultra raw-withhold #2: before the fix the archive-input constructor refused (no candidate was kept)."""
    from agentprov.raw.origins import Origin, OriginRow

    (sha_z, z), (sha_u, u), (sha_b, b) = _blob("zip bytes"), _blob("url zip bytes"), _blob("b")
    url = "https://example.org/runs.zip"
    rows = [OriginRow(sha_z, Origin.zenodo("10.5281/zenodo.1", "runs.zip")),
            OriginRow(sha_u, Origin.url(url, "2026-10-01")),
            OriginRow(sha_b, Origin.git(REPO, C2, "runs/b.json", "b" * 40))]
    snapshots = [{"snapshot_id": "one", "origin": {"kind": "zenodo", "doi": "10.5281/zenodo.1", "file": "runs.zip"},
                  "input": {"kind": "archive", "label": "runs.zip", "sha256": "sha256:" + sha_z, "bytes": len(z)}},
                 {"snapshot_id": "two", "origin": {"kind": "git", "repo": REPO, "commit": C2, "subtree": ""}},
                 {"snapshot_id": "three", "origin": {"kind": "url", "url": url, "retrieved_at": "2026-10-01T00:00:00Z"},
                  "input": {"kind": "archive", "label": "web.zip", "sha256": "sha256:" + sha_u, "bytes": len(u)}}]
    reader = _FakeReader(_manifest(snapshots), rows, {sha_z: z, sha_u: u, sha_b: b})
    tree = StoredRawTree(reader, snapshot_id="one")
    assert tree.archive_input and tree.labels == ("runs.zip",) and tree.sha256_of("runs.zip") == sha_z
    assert StoredRawTree(reader, snapshot_id="two").labels == ("runs/b.json",)
    tree = StoredRawTree(reader, snapshot_id="three")
    assert tree.archive_input and tree.labels == ("web.zip",) and tree.sha256_of("web.zip") == sha_u


ADPROV_COMMIT = "579a908354b93361efe0905ffb7623256aa96a06"
ADPROV_PROFILE = "rules/adprov-v1.profile.toml"


def _adprov_profile_bytes():
    from importlib.resources import files

    return (files("agentprov.adapters.adprov") / "profiles" / "adprov-v1.profile.toml").read_bytes()


def _adprov(*, sealed, snapshot_id="release", profile_bytes=None, parts=("release",)):
    """An adprov-style corpus: ``corpus`` listing origins ``<leaf>/<label>`` (TranscriptV1Reader.listing_origin)."""
    from agentprov.raw.origins import Origin, OriginRow

    data = _adprov_profile_bytes() if profile_bytes is None else profile_bytes
    (sha_a, a), (sha_b, b) = _blob("x"), _blob("y")
    rows = [OriginRow(sha_a, Origin.corpus("AgentDojo-PROV", "2.3", "corpus-prov/m/prov/i/x.transcript.json",
                                           producer_commit=ADPROV_COMMIT)),
            OriginRow(sha_b, Origin.corpus("AgentDojo-PROV", "2.3", "corpus-prov/m/prov/i/y.transcript.json",
                                           producer_commit=ADPROV_COMMIT))]
    snapshot = {"snapshot_id": snapshot_id,
                "origin": {"kind": "corpus", "corpus": "AgentDojo-PROV", "version": "2.3", "producer_commit": ADPROV_COMMIT}}
    if not sealed:
        snapshot["pin"] = {"kind": "git", "commit": ADPROV_COMMIT, "tree": "corpus/corpus-prov", "part": "release"}
    profile = {"id": "adprov-v1", "version": 2, "path": ADPROV_PROFILE,
               "sha256": "sha256:" + hashlib.sha256(_adprov_profile_bytes()).hexdigest()}
    return _FakeReader(_manifest([snapshot], sealed=sealed, profile=profile, parts=parts), rows, {sha_a: a, sha_b: b},
                       files={ADPROV_PROFILE: data})


def test_a_sealed_corpus_with_corpus_listing_origins_drops_the_tree_leaf_as_the_working_copy_does():
    """Ultra raw-withhold #3: the sealed snapshot records no pin (D-221) and its ``corpus`` origin no tree, so the leaf
    comes from the pin of the recorded source profile (``rules/<profile>.profile.toml``, digest-checked) that vouched for
    the snapshot (its commit, part and role)."""
    working = StoredRawTree(_adprov(sealed=False))
    assert working.labels == ("m/prov/i/x.transcript.json", "m/prov/i/y.transcript.json")
    assert StoredRawTree(_adprov(sealed=True)).labels == working.labels


def test_a_sealed_corpus_listing_leaf_is_refused_when_the_profile_cannot_tell_it():
    tampered = _adprov_profile_bytes() + b"\n# changed\n"
    with pytest.raises(StoredTreeError):
        StoredRawTree(_adprov(sealed=True, profile_bytes=tampered))
    # both adprov pins share the commit, and neither the snapshot id nor the corpus's one part picks one of them
    with pytest.raises(StoredTreeError):
        StoredRawTree(_adprov(sealed=True, snapshot_id="other", parts=("release", "converted-legacy")))
    # a snapshot id that is not a part: the corpus's one recorded part picks the pin
    assert StoredRawTree(_adprov(sealed=True, snapshot_id="other")).labels[0] == "m/prov/i/x.transcript.json"


def test_a_sealed_copy_of_an_imported_adprov_corpus_keeps_the_working_labels(tmp_path):
    """The same through the product import and a real reader: the working snapshot put in the sealed form (no pin, the
    sealed ``corpus`` origin, the profile under ``rules/``)."""
    import shutil

    from agentprov.corpus.reader import WORKING

    source = ds.adprov_corpus(tmp_path, count=2, until="aer")
    working = StoredRawTree(CorpusReader(ds.partial(source), state=WORKING, used_partial=True))
    assert working.labels and not any(label.startswith("corpus-prov/") for label in working.labels)
    copy = tmp_path / "sealed.partial"
    shutil.copytree(ds.partial(source), copy)
    manifest = json.loads((copy / "corpus.json").read_text("utf-8"))
    snapshot = manifest["sources"][0]["snapshots"][0]
    pin = snapshot.pop("pin")
    snapshot.pop("verification", None)
    snapshot["origin"] = {"kind": "corpus", "corpus": "AgentDojo-PROV", "version": "2.3", "producer_commit": pin["commit"]}
    data = _adprov_profile_bytes()
    (copy / "rules").mkdir(exist_ok=True)
    (copy / ADPROV_PROFILE).write_bytes(data)
    manifest["sources"][0]["profile"] = {"id": "adprov-v1", "version": 2, "path": ADPROV_PROFILE,
                                         "sha256": "sha256:" + hashlib.sha256(data).hexdigest()}
    manifest["sources"][0]["parts"] = ["release"]
    manifest["sealed"] = True
    (copy / "corpus.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", "utf-8")
    sealed = StoredRawTree(CorpusReader(copy, state=WORKING, used_partial=True))
    assert sealed.labels == working.labels
    assert [sealed.sha256_of(label) for label in sealed.labels] == [working.sha256_of(label) for label in working.labels]
