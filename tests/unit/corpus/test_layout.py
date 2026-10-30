"""Corpus layout, sharding, ``.partial`` and the write guards (HL H.1.2, H.1.3, H.1.5)."""

from __future__ import annotations

import hashlib
import json

import pytest

from agentprov.aer.ids import shard as aer_shard
from agentprov.corpus.layout import (
    CorpusLayout,
    GitWorkTreeRefusedError,
    SealedCorpusError,
    assert_outside_git_work_tree,
    assert_writable,
    dirname,
    find_git_work_tree,
    partial_dir,
    shard,
)

EX = "ex_7uz2oys57hugtsueixylme4fl5"  # the C.4.1 known-answer id
LIVE = "ex_018f3a4e-7b2c-7d3a-8c1e-0123456789ab"


def test_shard_is_the_first_hex_digits_of_sha256_of_the_id():
    digest = hashlib.sha256(EX.encode("ascii")).hexdigest()
    assert shard(EX) == digest[:2] == aer_shard(EX)
    assert shard(EX, 2) == f"{digest[:2]}/{digest[2:4]}"
    assert shard(LIVE) == hashlib.sha256(LIVE.encode()).hexdigest()[:2]  # hashed, so time-ordered ids spread
    for bad in ("", "ex_", "../x", "ex_7uz2oys57hugtsueixylme4fl", EX + "x"):
        with pytest.raises(ValueError):
            shard(bad)
    with pytest.raises(ValueError):
        shard(EX, 3)


def test_paths_follow_h12(tmp_path):
    layout = CorpusLayout(tmp_path / "c.partial")
    root = tmp_path / "c.partial"
    assert layout.manifest == root / "corpus.json" and layout.executions == root / "executions.jsonl"
    assert layout.register == root / "register.jsonl"
    assert layout.objects == root / "raw" / "objects" and layout.origins == root / "raw" / "origins.jsonl"
    assert layout.members == root / "raw" / "members.jsonl"
    rel = layout.aer_relpath(EX)
    assert rel == f"aer/{shard(EX)}/{EX}.aer.jsonl" and layout.aer_path(EX) == root / "aer" / shard(EX) / f"{EX}.aer.jsonl"
    deep = CorpusLayout(root, shard_depth=2).aer_relpath(EX)
    assert deep == f"aer/{shard(EX, 2)}/{EX}.aer.jsonl" and deep.count("/") == 3
    assert rel.isascii() and len(rel) <= 200 and "\\" not in rel
    with pytest.raises(ValueError):
        CorpusLayout(root, shard_depth=0)


def test_version_identifiers_map_to_directory_names():
    assert dirname("agentprov-prov/0.1") == "agentprov-prov-0.1"
    assert dirname("agentdojo.suites@1") == "agentdojo.suites-1"
    assert dirname("adprov-v2.3-compat") == "adprov-v2.3-compat"


def test_partial_directory_name(tmp_path):
    assert partial_dir(tmp_path / "agentdojo-upstream-0.1.0").name == "agentdojo-upstream-0.1.0.partial"


def write_manifest(directory, **fields):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "corpus.json").write_text(json.dumps(fields), encoding="utf-8")


def test_assert_writable_refuses_a_sealed_corpus_at_any_depth(tmp_path):
    write_manifest(tmp_path / "sealed", sealed=True)
    for target in (tmp_path / "sealed", tmp_path / "sealed" / "raw", tmp_path / "sealed" / "raw" / "not" / "yet" / "there"):
        with pytest.raises(SealedCorpusError) as exc:
            assert_writable(target)
        assert exc.value.exit_code == 4 and exc.value.code == "corpus.sealed"


def test_assert_writable_allows_unsealed_and_unrelated_paths(tmp_path):
    write_manifest(tmp_path / "work", sealed=False)
    assert_writable(tmp_path / "work" / "x")
    assert_writable(tmp_path / "plain" / "dir")
    write_manifest(tmp_path / "other", name="no sealed key")
    assert_writable(tmp_path / "other")


@pytest.mark.parametrize("content", [b"{not json", b"\xff\xfe", b"[]x"])
def test_an_unreadable_manifest_fails_closed(tmp_path, content):
    (tmp_path / "w").mkdir()
    (tmp_path / "w" / "corpus.json").write_bytes(content)
    with pytest.raises(SealedCorpusError) as exc:
        assert_writable(tmp_path / "w" / "x")
    assert exc.value.code == "corpus.sealed.unverifiable"


def test_a_symlink_into_a_sealed_corpus_is_resolved(tmp_path):
    write_manifest(tmp_path / "sealed", sealed=True)
    link = tmp_path / "alias"
    try:
        link.symlink_to(tmp_path / "sealed", target_is_directory=True)
    except OSError:
        pytest.skip("symlinks unavailable")
    with pytest.raises(SealedCorpusError):
        assert_writable(link / "raw")


def test_git_work_tree_guard(tmp_path):
    inside = tmp_path / "repo" / "out" / "corpus.partial"
    inside.mkdir(parents=True)
    assert find_git_work_tree(inside) is None
    assert_outside_git_work_tree(inside)  # no work tree: fine
    (tmp_path / "repo" / ".git").mkdir()
    assert find_git_work_tree(inside) == (tmp_path / "repo").resolve()
    with pytest.raises(GitWorkTreeRefusedError) as exc:
        assert_outside_git_work_tree(inside)  # no decision from the caller: refused (fail closed)
    assert exc.value.exit_code == 4
    with pytest.raises(GitWorkTreeRefusedError):
        assert_outside_git_work_tree(inside, is_ignored=lambda tree, path: False)
    seen = []
    assert_outside_git_work_tree(inside, is_ignored=lambda tree, path: seen.append((tree, path)) or True)
    assert seen == [((tmp_path / "repo").resolve(), inside.resolve())]


def test_a_linked_worktree_marker_file_counts_as_a_work_tree(tmp_path):
    (tmp_path / "wt").mkdir()
    (tmp_path / "wt" / ".git").write_text("gitdir: /elsewhere\n")
    assert find_git_work_tree(tmp_path / "wt" / "x") == (tmp_path / "wt").resolve()


# ---------------------------------------------------------------------------------------------- phase 11: H.1.2 paths
def test_every_h12_path_has_a_property(tmp_path):
    from agentprov.corpus.layout import classify_relpath

    root = tmp_path / "c"
    layout = CorpusLayout(root)
    expected = {
        layout.checksums: "checksums.sha256", layout.datasheet: "DATASHEET.md", layout.changelog: "CHANGELOG.md",
        layout.withheld: "WITHHELD.json", layout.references: "raw/REFERENCES.json", layout.tombstones: "raw/tombstones.jsonl",
        layout.licence_derived: "LICENSES/DERIVED.txt", layout.licence_file("agentdojo"): "LICENSES/agentdojo/LICENSE",
        layout.licence_file("agentdojo", "NOTICE.md"): "LICENSES/agentdojo/NOTICE.md",
        layout.schema("corpus-0.1.schema.json"): "schemas/corpus-0.1.schema.json", layout.rules_spec: "rules/corpus-spec.toml",
        layout.rules_card: "rules/CARD.md", layout.rules_changes: "rules/CHANGES.toml",
        layout.rules_profile("agentdojo-upstream"): "rules/agentdojo-upstream.profile.toml",
        layout.rules_catalogue("aer"): "rules/aer.rules.toml",
        layout.rules_prov("agentprov-prov/0.1"): "rules/prov/agentprov-prov-0.1.toml",
        layout.validation_results: "validation/results.jsonl", layout.validation_summary: "validation/summary.json",
        layout.view_path("transcript-v1", EX): f"views/transcript-v1/{shard(EX)}/{EX}.transcript.json",
    }  # fmt: skip
    for path, label in expected.items():
        assert path == root.joinpath(*label.split("/")) and classify_relpath(label) is not None, label
    assert layout.raw_tmp == root / "raw" / "tmp" and classify_relpath("raw/tmp/x") is None
    for bad in (lambda: layout.schema("evil.schema.json"), lambda: layout.licence_file("../x"),
                lambda: layout.rules_catalogue("A b"), lambda: layout.view_relpath("stats", EX)):
        with pytest.raises(ValueError):
            bad()


@pytest.mark.parametrize(
    ("label", "role"),
    [
        ("corpus.json", "manifest"), ("executions.jsonl", "index"), ("checksums.sha256", "checksums"),
        (f"aer/{shard(EX)}/{EX}.aer.jsonl", "aer"), (f"aer/{shard(EX, 2)}/{EX}.aer.jsonl", "aer"),
        (f"aer/00/{EX}.aer.jsonl", None),  # the wrong shard
        (f"sem/agentdojo.suites-1/{shard(EX)}/{EX}.sem.jsonl", "sem"), (f"sem/suites/{shard(EX)}/{EX}.sem.jsonl", None),
        (f"prov/adprov-v2.3-compat/{shard(EX)}/{EX}.prov.json", "prov"),
        (f"prov/agentprov-prov-0.1/{shard(EX)}/{EX}.prov-core.json", None),  # not in a v0.1 corpus (AD-10 row 4)
        (f"prov/agentprov-prov-0.1/{shard(EX)}/{EX}.prov.trig", None),  # TriG is never stored (AD-10 row 3)
        ("raw/objects/ab/" + "ab" * 32 + ".zip", "raw_object"), ("raw/objects/ab/" + "ab" * 32 + ".exe", None),
        ("raw/objects/ac/" + "ab" * 32 + ".zip", None), ("raw/objects/ab/" + "AB" * 32 + ".zip", None),
        (".DS_Store", None), ("raw/.DS_Store", None), ("LICENSES/foo/.hidden", None), (".agentprov.lock", None),
        ("a/../corpus.json", None), ("/corpus.json", None), ("aer//x", None), ("corpus.json\n", None),
        ("runs/gpt-4o/banking/user_task_0.json", None),  # a source-derived name (H.1.3(1))
        ("schemas/aer-0.1.schema.json", "schema"), ("schemas/aer-0.2.schema.json", "schema"), ("schemas/aer-0.3.schema.json", None), ("x" * 201, None),
    ],
)
def test_classify_relpath_is_the_closed_grammar(label, role):
    from agentprov.corpus.layout import classify_relpath

    assert classify_relpath(label) == role


def test_iter_tree_reports_everything_outside_the_closed_world(tmp_path):
    import os

    from agentprov.corpus.layout import iter_tree

    root = tmp_path / "c.partial"
    layout = CorpusLayout(root)
    (root / "raw" / "objects" / "ab").mkdir(parents=True)
    (root / "raw" / "tmp").mkdir()
    obj = root / "raw" / "objects" / "ab" / ("ab" * 32 + ".json")
    obj.write_bytes(b"{}")
    os.link(obj, tmp_path / "hardlink")  # a hard link changes no byte (recompute --link-raw, D-32): admitted
    (root / "corpus.json").write_bytes(b"{}")
    (root / ".agentprov.lock").write_bytes(b"{}")
    (root / ".DS_Store").write_bytes(b"\0")
    (root / "notes.txt").write_bytes(b"")
    (root / "views").mkdir()
    os.symlink(obj, root / "executions.jsonl")
    layout.aer_path(EX).parent.mkdir(parents=True)
    os.symlink(tmp_path, layout.aer_path(EX).parent / "linked_dir")
    scan = iter_tree(root)
    assert scan.files == (("corpus.json", "manifest", 2), ("raw/objects/ab/" + "ab" * 32 + ".json", "raw_object", 2))
    assert [(f.code, f.label) for f in scan.findings] == [
        ("corpus.tree.stray", ".DS_Store"), ("corpus.tree.lock", ".agentprov.lock"),  # bytewise label order
        ("corpus.tree.link", f"aer/{shard(EX)}/linked_dir"), ("corpus.tree.link", "executions.jsonl"),
        ("corpus.tree.stray", "notes.txt"), ("corpus.tree.raw_tmp", "raw/tmp"), ("corpus.tree.empty_dir", "views"),
    ]  # fmt: skip
    assert {f.code for f in scan.blocking(working=True)} == {"corpus.tree.stray", "corpus.tree.link", "corpus.tree.empty_dir"}
    assert len(scan.blocking(working=False)) == len(scan.findings) and not scan.closed
    assert not (tmp_path / "linked_dir").exists()  # nothing was followed or created


def test_iter_tree_escapes_untrusted_names(tmp_path):
    from agentprov.corpus.layout import iter_tree

    root = tmp_path / "c"
    root.mkdir()
    (root / "a\u202eb.txt").write_bytes(b"")  # a bidi control in a downloaded tree's file name
    (finding,) = iter_tree(root).findings
    assert finding.code == "corpus.tree.stray" and "\u202e" not in finding.label and "<U+202E>" in finding.label


def test_a_lock_break_token_is_a_working_tree_lock_entry(tmp_path):
    """Pre-round review D #6: ``io.atomic.LockFile`` breaks a stale lock under a ``.agentprov.lock.break`` token; one
    left by a breaker that died is a working-tree lock entry like the lock itself, not a stray file."""
    from agentprov.corpus.layout import iter_tree

    root = tmp_path / "c.partial"
    root.mkdir()
    (root / "corpus.json").write_bytes(b"{}")
    (root / ".agentprov.lock.break").write_bytes(b"1 host\n")
    scan = iter_tree(root)
    assert [(f.code, f.label) for f in scan.findings] == [("corpus.tree.lock", ".agentprov.lock.break")]
    assert not scan.blocking(working=True)
