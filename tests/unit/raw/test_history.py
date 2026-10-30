"""``agentprov.raw.history`` and the Fetcher's history store: the introducing commit of every blob (D.6.16).

The pure parts run on hand-made git output (including paths that look like log headers); the rest uses a synthetic local
upstream (``history_support``) fetched through ``file://`` with the Fetcher's test seam. No test touches the network.
"""

from __future__ import annotations

import json
import os
import subprocess

import pytest
from fetch_support import REPO_URL, needs_git
from history_support import History, make_history

from agentprov.raw.fetch import HISTORY_MODE, Fetcher, NetworkRefusedError, Recipe
from agentprov.raw.history import (
    INDEX_FORMAT,
    HistoryError,
    HistoryIndex,
    LogCommit,
    build_index,
    introducing_commits,
    parse_history_log,
    parse_plain_ls_tree,
    rfc3339_utc,
)

C1, C2, C3 = "1" * 40, "2" * 40, "3" * 40
B1, B2 = "a" * 40, "b" * 40


# ------------------------------------------------------------------------------------------------ pure parsing
def _header(commit: str, parents: list[str], epoch: int) -> bytes:
    return b"\x01" + " ".join([commit, *parents, str(epoch)]).encode() + b"\0"


def _raw(status: str, oid: str, path: bytes, nmode: str = "100644") -> bytes:
    return f":000000 {nmode} {'0' * 40} {oid} {status}".encode() + b"\0" + path + b"\0"


def test_the_log_parser_reads_headers_and_additions_and_ignores_deletions():
    data = _header(C2, [C1], 200) + _raw("A", B1, b"runs/a.json") + _raw("D", B2, b"runs/gone.json") + _raw("M", B2, b"x") \
        + _header(C1, [], 100) + _raw("A", B1, b"runs/a.json")  # fmt: skip
    blocks = list(parse_history_log(data))
    assert blocks == [
        LogCommit(C2, 1, 200, (("runs/a.json", B1), ("x", B2))),
        LogCommit(C1, 0, 100, (("runs/a.json", B1),)),
    ]


def test_a_path_that_looks_like_a_header_or_a_raw_record_is_still_a_path():
    data = _header(C1, [], 5) + _raw("A", B1, b"\x01evil") + _raw("A", B2, b":000000 100644 x") + _raw("A", B1, b"")
    (block,) = list(parse_history_log(data))
    assert block.added == (("\x01evil", B1), (":000000 100644 x", B2), ("", B1))


def test_a_gitlink_and_an_undecodable_path_are_not_additions():
    data = _header(C1, [], 5) + _raw("A", B1, b"sub", nmode="160000") + _raw("A", B2, b"\xff\xfe") + _raw("A", B1, b"ok")
    (block,) = list(parse_history_log(data))
    assert block.added == (("ok", B1),)


@pytest.mark.parametrize(
    "data",
    [b"garbage\0", b"\x01nothex 1\0", b"\x01" + C1.encode() + b" zz 5\0", b":000000 100644 a b A\0p\0",
     _header(C1, [], 1) + b":1 2 3\0p\0"],
)  # fmt: skip
def test_malformed_log_output_is_refused(data):
    with pytest.raises(HistoryError):
        list(parse_history_log(data))


def test_ls_tree_without_sizes_keeps_blobs_and_symlinks_and_drops_gitlinks():
    data = f"100644 blob {B1}\truns/a.json\x00120000 blob {B2}\truns/link\x00160000 commit {C1}\truns/sub\x00".encode()
    tree, skipped = parse_plain_ls_tree(data)
    assert tree == {"runs/a.json": B1, "runs/link": B2} and skipped == 0
    tree, skipped = parse_plain_ls_tree(f"100644 blob {B1}\t".encode() + b"\xff\0")
    assert tree == {} and skipped == 1
    with pytest.raises(HistoryError):
        parse_plain_ls_tree(b"100644 blob nothex\tp\0")


def test_the_earliest_introducing_commit_wins_whatever_the_stream_order():
    tree = {"p": B1}
    blocks = [LogCommit(C3, 1, 300, (("p", B1),)), LogCommit(C1, 0, 100, (("p", B1),)), LogCommit(C2, 1, 200, (("p", B1),))]
    assert introducing_commits(blocks, tree) == {("p", B1): (100, C1)}
    assert introducing_commits(blocks[:1] + blocks[2:], tree) == {("p", B1): (200, C2)}


def test_ties_on_the_date_break_on_the_commit_id():
    tree = {"p": B1}
    blocks = [LogCommit(C3, 1, 100, (("p", B1),)), LogCommit(C2, 1, 100, (("p", B1),))]
    assert introducing_commits(blocks, tree)[("p", B1)] == (100, C2)


def test_a_merge_introduces_a_blob_only_when_no_parent_holds_it():
    tree = {"p": B1, "q": B2}
    # two-parent merge: p is listed against both parents (neither holds it), q against one parent only
    merge = [LogCommit(C3, 2, 300, (("p", B1), ("q", B2))), LogCommit(C3, 2, 300, (("p", B1),))]
    assert introducing_commits(merge, tree) == {("p", B1): (300, C3)}


def test_blobs_off_the_pinned_tree_are_ignored():
    blocks = [LogCommit(C1, 0, 1, (("p", B1), ("p", B2), ("other", B1)))]
    assert introducing_commits(blocks, {"p": B1}) == {("p", B1): (1, C1)}


def test_an_index_with_an_unreached_blob_is_refused_not_completed():
    with pytest.raises(HistoryError) as err:
        build_index("https://x/y/z", C1, C2, {"p": B1, "q": B2}, {("p", B1): (1, C1)})
    assert err.value.code == "raw.history.incomplete"


def test_dates_are_utc_seconds_and_range_checked():
    assert rfc3339_utc(0) == "1970-01-01T00:00:00Z" and rfc3339_utc(1714816800) == "2024-05-04T10:00:00Z"
    assert rfc3339_utc(253402300799) == "9999-12-31T23:59:59Z"
    # 253402300800 is year 10000: git accepts it, datetime does not (CB-23: was an untyped ValueError).
    for bad in (-1, 253402300800, (1 << 40) - 1, 1 << 41):
        with pytest.raises(HistoryError) as err:
            rfc3339_utc(bad)
        assert err.value.code == "raw.history.date"


def _index() -> HistoryIndex:
    best = {("b/p", B1): (1714816800, C1), ("a/p", B2): (1714816800, C1), ("a/q", B2): (1714900000, C2)}
    return build_index("https://github.com/o/r", C3, "4" * 40, {k[0]: k[1] for k in best}, best, history_commits=7)


def test_the_index_file_is_deterministic_sorted_and_round_trips():
    index = _index()
    data = index.to_bytes()
    assert data == _index().to_bytes()
    lines = data.splitlines()
    header = json.loads(lines[0])
    assert header["format"] == INDEX_FORMAT and header["entries"] == 3 and header["introducing_commits"] == 2
    assert [json.loads(line)["p"] for line in lines[1:]] == ["a/p", "a/q", "b/p"]
    assert b"retrieved" not in data
    back = HistoryIndex.from_bytes(data, expect_repo="https://github.com/o/r", expect_commit=C3)
    assert back.rows == index.rows and back.commits == index.commits and back.history_commits == 7
    assert back.lookup("a/q", B2) == C2 and back.lookup("a/q", B1) is None and back.date_of(C1) == "2024-05-04T10:00:00Z"


@pytest.mark.parametrize("damage", ["row", "digest", "repo", "commit", "format", "date", "unlisted", "count", "nonjson"])
def test_a_damaged_index_file_is_refused(damage):
    data = _index().to_bytes()
    head, _, body = data.partition(b"\n")
    header = json.loads(head)
    expect = {"expect_repo": "https://github.com/o/r", "expect_commit": C3}
    if damage == "row":
        body = body.replace(b'"a/q"', b'"a/Q"')
    elif damage == "digest":
        header["rows_sha256"] = "0" * 64
    elif damage == "repo":
        expect["expect_repo"] = "https://github.com/o/other"
    elif damage == "commit":
        expect["expect_commit"] = C1
    elif damage == "format":
        header["format"] = "agentprov-history-index/9"
    elif damage == "date":
        header["commits"][C1] = "yesterday"
    elif damage == "unlisted":
        header["commits"].pop(C2)
    elif damage == "count":
        header["entries"] = 99
    elif damage == "nonjson":
        head = b"{not json"
    if damage not in ("nonjson",):
        head = json.dumps(header, separators=(",", ":")).encode()
    if damage == "row":  # keep the digest honest for the other damages; this one must trip the digest itself
        pass
    with pytest.raises(HistoryError):
        HistoryIndex.from_bytes(head + b"\n" + body, **expect)


# ------------------------------------------------------------------------------------------------ git history store
def _fetcher(history: History, cache, **kwargs) -> Fetcher:
    kwargs.setdefault("remote_urls", {REPO_URL: history.url})
    kwargs.setdefault("file_protocol", True)
    return Fetcher(cache, **kwargs)


def _recipe(history: History, **changes) -> Recipe:
    base = {"kind": "git", "repo": REPO_URL, "commit": history.head, "paths": ("runs/",)}
    base.update(changes)
    return Recipe(**base)


@pytest.fixture(scope="module")
def history(tmp_path_factory) -> History:
    return make_history(tmp_path_factory.mktemp("hist"))


@needs_git
def test_every_blob_gets_its_earliest_introducing_commit(history, tmp_path):
    fetcher = _fetcher(history, tmp_path / "cache", allow_network=True, consent="test consent")
    result = fetcher.fetch_history(_recipe(history))
    index = result.index
    assert result.network_used and result.index_created
    got = {path: index.lookup(path, blob) for (path, blob) in index.rows}
    assert got == {p: history.commits[name] for p, name in history.expect.items()}
    for path, name in history.expect.items():
        commit = got[path]
        assert commit == history.commits[name], path
        assert index.date_of(commit) == history.dates[name]
    # the merges c7, c10 (clean), c13 introduce nothing except the conflict resolution c10
    assert {history.commits[n] for n in ("c7", "c13", "c5", "c6", "c12", "c15", "c16")}.isdisjoint(set(index.commits))
    assert index.history_commits == 16 and index.tree and len(index.rows) == len(history.expect)


@needs_git
def test_a_rename_is_introduced_at_the_new_path_and_a_re_add_keeps_the_first_commit(history, tmp_path):
    index = _fetcher(history, tmp_path / "cache", allow_network=True).fetch_history(_recipe(history)).index
    blob_of = {p: b for (p, b) in index.rows}
    assert index.rows[("runs/b2.json", blob_of["runs/b2.json"])] == history.commits["c4"]  # b.json existed from c1
    assert index.rows[("runs/d.json", blob_of["runs/d.json"])] == history.commits["c4"]  # re-added at c6
    assert index.rows[("runs/g.json", blob_of["runs/g.json"])] == history.commits["c14"]  # reverted to G1 at c16


@needs_git
def test_the_history_store_is_a_separate_blobless_full_history_and_logs_one_row(history, tmp_path):
    cache = tmp_path / "cache"
    result = _fetcher(history, cache, allow_network=True, consent="user approved (test)").fetch_history(_recipe(history))
    assert result.store == cache / "git-history" / "example.invalid" / "acme" / "runs.git"
    assert not (cache / "git" / "example.invalid").exists()  # the depth-1 store is not touched
    assert not (result.store / "shallow").exists() and not (result.store / "index").exists()  # bare: no working tree
    exe = ["git", "-C", str(result.store)]
    env = {**os.environ, "GIT_NO_LAZY_FETCH": "1", "GIT_CONFIG_GLOBAL": os.devnull}
    count = subprocess.run([*exe, "rev-list", "--count", history.head], capture_output=True, text=True, env=env, check=True)
    assert count.stdout.strip() == "16"
    missing = subprocess.run([*exe, "rev-list", "--objects", "--missing=print", history.head], capture_output=True, text=True, env=env, check=True)
    assert any(line.startswith("?") for line in missing.stdout.splitlines())  # blobs are not there
    (row,) = _fetcher(history, cache).log.rows()
    assert row["mode"] == HISTORY_MODE and row["filter"] == "blob:none" and row["consent"] == "user approved (test)"
    assert row["repo"] == REPO_URL and row["commit"] == history.head and row["commits"] == 16 and row["entries"] == len(history.expect)
    assert row["index_sha256"] == result.index_sha256 and row["bytes"] > 0 and "retrieved_at" in row
    assert not any(k in row for k in ("token", "password"))


@needs_git
def test_the_index_is_cached_keyed_by_the_commit_and_not_recomputed(history, tmp_path):
    cache = tmp_path / "cache"
    first = _fetcher(history, cache, allow_network=True).fetch_history(_recipe(history))
    assert first.index_path == cache / "git-history" / "example.invalid" / "acme" / "runs.index" / f"{history.head}.jsonl"
    # a fresh Fetcher with no network finds the index and answers from the file alone
    offline = _fetcher(history, cache)
    again = offline.fetch_history(_recipe(history))
    assert not again.network_used and not again.index_created and again.index_sha256 == first.index_sha256
    assert offline.history_index(_recipe(history)).rows == first.index.rows
    assert len(offline.log.rows()) == 1  # no second acquisition
    # the index file is byte-identical when recomputed from a fresh store
    other = _fetcher(history, tmp_path / "cache2", allow_network=True).fetch_history(_recipe(history))
    assert other.index_path.read_bytes() == first.index_path.read_bytes()


@needs_git
def test_without_the_index_there_is_nothing_and_no_network_is_used(history, tmp_path):
    fetcher = _fetcher(history, tmp_path / "cache")
    recipe = _recipe(history)
    assert fetcher.history_index(recipe) is None
    plan = fetcher.plan_history(recipe)
    assert not plan.cached and plan.needs_network and not (tmp_path / "cache").exists()
    with pytest.raises(NetworkRefusedError):
        fetcher.fetch_history(recipe)
    assert not (tmp_path / "cache").exists()


@needs_git
def test_an_earlier_commit_gets_its_own_index_from_the_same_store_without_the_network(history, tmp_path):
    cache = tmp_path / "cache"
    _fetcher(history, cache, allow_network=True).fetch_history(_recipe(history))
    earlier = _recipe(history, commit=history.commits["c7"])
    offline = _fetcher(history, cache)  # no allow_network: the store already holds c7
    assert offline.plan_history(earlier).needs_network is False
    index = offline.fetch_history(earlier).index
    assert not any(c == history.commits["c16"] for c in index.commits)
    names = {history.commits[n]: n for n in history.commits}
    assert {p: names[c] for (p, _b), c in index.rows.items()}["runs/a.json"] == "c3"
    assert len(offline.log.rows()) == 1


@needs_git
def test_a_corrupt_cached_index_is_loud(history, tmp_path):
    cache = tmp_path / "cache"
    result = _fetcher(history, cache, allow_network=True).fetch_history(_recipe(history))
    result.index_path.write_bytes(result.index_path.read_bytes().replace(b'"p":"README.md"', b'"p":"README.mx"'))
    with pytest.raises(HistoryError):
        _fetcher(history, cache).history_index(_recipe(history))


@needs_git
def test_store_git_records_the_introducing_commit_only_when_the_index_is_cached(history, tmp_path):
    from agentprov.raw.origins import OriginLog
    from agentprov.raw.store import RawObjectStore

    cache = tmp_path / "cache"
    plain = _fetcher(history, cache, allow_network=True)
    recipe = _recipe(history, commit=history.head)
    plain.fetch(recipe)  # the depth-1 store only
    store, origins = RawObjectStore(tmp_path / "raw1"), OriginLog()
    before = plain.store_git(recipe, store, origins)
    assert all(b.origin.data.get("introduced_in_commit") is None for b in before)
    plain.fetch_history(recipe)
    store2, origins2 = RawObjectStore(tmp_path / "raw2"), OriginLog()
    after = plain.store_git(recipe, store2, origins2)
    by_path = {b.path: b.origin.data["introduced_in_commit"] for b in after}
    assert by_path["runs/a.json"] == history.commits["c3"] and by_path["runs/e.json"] == history.commits["c10"]
    assert all(b.origin.data["blob_sha1"] == b.blob_sha1 for b in after)


@needs_git
def test_a_shallow_history_store_is_refused_not_used(history, tmp_path):
    cache = tmp_path / "cache"
    fetcher = _fetcher(history, cache, allow_network=True)
    recipe = _recipe(history)
    store = fetcher.history_store(recipe)
    store.parent.mkdir(parents=True)
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull}
    subprocess.run(["git", "init", "-q", "--bare", str(store)], check=True, env=env)
    (store / "shallow").write_text(history.head + "\n")
    assert fetcher._has_history_commit(store, history.head) is False


@needs_git
def test_a_failed_index_computation_after_a_network_fetch_still_logs_the_acquisition(history, tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    fetcher = _fetcher(history, cache, allow_network=True, consent="c")

    def broken(recipe, bare):
        raise HistoryError("boom", code="raw.history.incomplete")

    monkeypatch.setattr(fetcher, "_compute_history_index", broken)
    with pytest.raises(HistoryError):
        fetcher.fetch_history(_recipe(history))
    (row,) = fetcher.log.rows()
    assert row["mode"] == HISTORY_MODE and row["index"] is None and row["bytes"] > 0
    assert not fetcher.history_index_path(_recipe(history)).exists()
    monkeypatch.undo()
    again = _fetcher(history, cache).fetch_history(_recipe(history))  # the store is there: no network needed now
    assert not again.network_used and again.index_created
