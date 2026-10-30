"""The read model (design §2.4): discovery, the fast executions table, the full row check on open, the detail loader,
and the sorted-file lookup. No Qt."""

from __future__ import annotations

import io
import json
import random
from pathlib import Path

import pytest
from agentprov.corpus.reader import CorpusReader, CorpusReadError
from agentprov.ingest.limits import IngestLimits

from _corpus_support import tree_state
from agentprov_gui.readmodel.corpus import discover, summarise
from agentprov_gui.readmodel.detail import DetailCache, load_detail, lookup_sorted_lines
from agentprov_gui.readmodel.executions import IndexChangedError, TableFilter, load_table, read_row


def test_discover_and_summarise(mini_corpus: Path) -> None:
    found = discover([mini_corpus.parent])
    assert [c.name for c in found] == ["mini"]
    s = found[0]
    assert s.state == "working" and not s.writing and s.executions == 3 and s.error is None
    assert summarise(mini_corpus.with_name("mini.partial")).path == mini_corpus


def test_unreadable_corpus_reports_a_code(tmp_path: Path) -> None:
    bad = tmp_path / "x.partial"
    bad.mkdir()
    (bad / "corpus.json").write_bytes(b"{not json")
    s = summarise(bad)
    assert s.state in ("working", "unreadable")
    found = discover([tmp_path])
    assert len(found) == 1


def test_lock_is_observed_not_taken(corpus_copy: Path) -> None:
    partial = corpus_copy.with_name("mini.partial")
    (partial / ".agentprov.lock").write_text("{}")
    assert summarise(corpus_copy).writing


def test_table_matches_core_index_and_full_row_check(mini_corpus: Path) -> None:
    reader = CorpusReader.open(mini_corpus)
    table = load_table(reader)
    core_rows = list(reader.iter_index())
    assert [table.ex(i) for i in range(len(table))] == [r.ex for r in core_rows]
    for i, core in enumerate(core_rows):
        assert read_row(reader, table, i) == core
        assert table.value(i, "status") == core.status


def test_select_sort_filter(mini_corpus: Path) -> None:
    table = load_table(CorpusReader.open(mini_corpus))
    assert table.select(TableFilter()) == list(range(len(table)))
    assert table.select(TableFilter(), descending=True) == list(reversed(range(len(table))))
    ex1 = table.ex(1)
    assert table.select(TableFilter(ex_contains=ex1[-6:])) == [1]
    status = table.value(0, "status")
    picked = table.select(TableFilter(pickers=(("status", frozenset({status})),)))
    assert 0 in picked
    assert table.select(TableFilter(pickers=(("status", frozenset({"nope"})),))) == []


def test_unsorted_index_refused(corpus_copy: Path) -> None:
    path = corpus_copy.with_name("mini.partial") / "executions.jsonl"
    lines = path.read_bytes().splitlines(keepends=True)
    path.write_bytes(b"".join(reversed(lines)))
    with pytest.raises(CorpusReadError):
        load_table(CorpusReader.open(corpus_copy))


def test_non_canonical_row_refused_on_open(corpus_copy: Path) -> None:
    path = corpus_copy.with_name("mini.partial") / "executions.jsonl"
    lines = path.read_bytes().splitlines(keepends=True)
    row = json.loads(lines[0])
    lines[0] = json.dumps(row, indent=None, separators=(", ", ": ")).encode() + b"\n"  # valid JSON, not JCS
    path.write_bytes(b"".join(lines))
    reader = CorpusReader.open(corpus_copy)
    table = load_table(reader)  # the light table read accepts it
    with pytest.raises(CorpusReadError):
        read_row(reader, table, 0)  # the full check on open refuses it


def test_index_replaced_after_load(corpus_copy: Path) -> None:
    reader = CorpusReader.open(corpus_copy)
    table = load_table(reader)
    path = corpus_copy.with_name("mini.partial") / "executions.jsonl"
    data = path.read_bytes()
    path.unlink()
    path.write_bytes(data)
    with pytest.raises(IndexChangedError):
        read_row(reader, table, 0)


def test_detail_is_read_only_and_complete(mini_corpus: Path) -> None:
    before = tree_state(mini_corpus.parent)  # the corpora root: the tree and anything beside it
    reader = CorpusReader.open(mini_corpus)
    table = load_table(reader)
    for i in range(len(table)):
        d = load_detail(reader, read_row(reader, table, i))
        assert d.aer is not None and d.prov and d.errors == {}
        assert d.validation is not None and d.validation["ex"] == d.ex
        core_register = [e for e in reader.register() if e.subject.get("ex") == d.ex]
        assert d.register == core_register
    assert tree_state(mini_corpus.parent) == before


def test_tampered_prov_is_reported_not_shown(corpus_copy: Path) -> None:
    reader = CorpusReader.open(corpus_copy)
    table = load_table(reader)
    row = read_row(reader, table, 0)
    prov = corpus_copy.with_name("mini.partial") / next(iter(row.prov_paths.values()))
    prov.write_bytes(prov.read_bytes().replace(b"{", b"{ ", 1))
    d = load_detail(reader, row)
    assert d.prov == {} and d.errors.get("prov:agentprov-prov/0.1") == "corpus.read.digest"
    assert d.aer is not None  # the other parts still load


def test_lookup_sorted_lines_matches_a_scan() -> None:
    rnd = random.Random(7)
    keys = sorted({f"k{rnd.randrange(400):04d}" for _ in range(300)})
    lines: list[bytes] = []
    for k in keys:
        for c in range(rnd.randrange(1, 4)):
            lines.append(json.dumps({"key": k, "c": c, "pad": "x" * rnd.randrange(0, 50)}, sort_keys=True).encode()
                         + b"\n")
    data = b"".join(lines)
    limits = IngestLimits()
    for target in [*keys[:5], *keys[-5:], "k0000", "a", "z", *rnd.sample(keys, 20)]:
        want = [line for line in lines if json.loads(line)["key"] == target]
        got = lookup_sorted_lines(io.BytesIO(data), len(data), target, lambda v: v.get("key"), limits)
        assert got == want, target
    assert lookup_sorted_lines(io.BytesIO(b""), 0, "x", lambda v: v.get("key"), limits) == []


def test_detail_cache_bounds() -> None:
    from agentprov_gui.readmodel.detail import ExecutionDetail

    cache = DetailCache(max_entries=2, max_bytes=100)
    for i in range(3):
        d = ExecutionDetail(f"ex_{i}", None)  # type: ignore[arg-type]
        d.size_bytes = 10
        cache.put("r", d)
    assert cache.get("r", "ex_0") is None and cache.get("r", "ex_2") is not None
    big = ExecutionDetail("ex_big", None)  # type: ignore[arg-type]
    big.size_bytes = 1000
    cache.put("r", big)
    assert cache.get("r", "ex_big") is None
