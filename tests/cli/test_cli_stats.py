"""``agentprov stats`` (MN N.2.12; K.5.11; K.15; G.8.6): options, streams, output guard, exit codes, determinism.

Corpora are hand-built in a temporary directory by ``tests/unit/stats/stats_support.py``; nothing reads the user's
corpora, a committed fixture or the network."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_STATS_TESTS = Path(__file__).resolve().parents[1] / "unit" / "stats"
if str(_STATS_TESTS) not in sys.path:
    sys.path.insert(0, str(_STATS_TESTS))

import stats_support as ss  # noqa: E402

from agentprov.testing import fs_guard  # noqa: E402

SCHEMA = Path(__file__).resolve().parent / "schemas" / "stats-0.1.schema.json"


@pytest.fixture
def corpus(tmp_path):
    ss.standard_corpus(tmp_path / "c.partial")
    return tmp_path / "c"


def _validate(document):
    import jsonschema

    jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text())).validate(document)


def test_stats_is_registered(cli):
    from agentprov.cli.main import COMMANDS

    assert "stats" in COMMANDS
    run = cli("stats", "--help")
    assert run.code == 0 and "--tables" in run.out and "--artefacts" in run.out and "--per-execution" in run.out


def test_json_payload_on_stdout(cli, corpus, tmp_path):
    with fs_guard.unchanged(tmp_path / "c.partial"):
        run = cli("stats", "--corpus", str(corpus), "--format", "json", "--artefacts", "--per-execution")
    assert run.code == 0, run.err
    document = run.json()
    _validate(document)
    assert [c["corpus"]["corpus_id"] for c in document["corpora"]] == ["tst-stats"]
    assert set(document["corpora"][0]["tables"]) == {"counts", "register", "statements", "statements_by_execution",
                                                     "statements_structural", "unknowns", "field_groups", "artefacts"}  # fmt: skip
    assert "working corpus, not sealed or verified" in run.err
    again = cli("stats", "--corpus", str(corpus), "--format", "json", "--artefacts", "--per-execution")
    assert again.out == run.out  # byte-stable


def test_tables_option_selects(cli, corpus):
    run = cli("stats", "--corpus", str(corpus), "--tables", "field_groups", "--format", "json")
    assert run.code == 0 and set(run.json()["corpora"][0]["tables"]) == {"field_groups"}
    assert run.json()["tables"] == ["field_groups"]


@pytest.mark.parametrize("fmt, marker", [("text", "== counts"), ("markdown", "### counts"), ("csv", "corpus_id,table,source_id")])
def test_formats(cli, corpus, fmt, marker):
    run = cli("stats", "--corpus", str(corpus), "--format", fmt)
    assert run.code == 0 and marker in run.out
    assert cli("stats", "--corpus", str(corpus), "--format", fmt).out == run.out


def test_json_summary_takes_stdout(cli, corpus, check_summary):
    run = cli("stats", "--corpus", str(corpus), "--format", "json", "--json")
    assert run.code == 0
    summary = run.json()
    check_summary(summary)
    assert summary["command"] == "stats" and summary["counters"]["rows"] == 7
    assert '"format":"agentprov-stats/0.1"' in run.err  # the payload went to stderr


def test_out_file_and_guard(cli, corpus, tmp_path):
    out = tmp_path / "elsewhere" / "stats.csv"
    out.parent.mkdir()
    run = cli("stats", "--corpus", str(corpus), "--format", "csv", "--out", str(out))
    assert run.code == 0 and run.out == "" and out.read_text().startswith("corpus_id,table,")
    inside = cli("stats", "--corpus", str(corpus), "--out", str(tmp_path / "c.partial" / "stats.txt"))
    assert inside.code == 4 and not (tmp_path / "c.partial" / "stats.txt").exists()
    nested = cli("stats", "--corpus", str(corpus), "--out", str(tmp_path / "c.partial" / "aer" / "x.txt"))
    assert nested.code == 4


@pytest.mark.parametrize("argv", [
    ("--tables", "counts,bogus"),
    ("--select", "nonsense"),
    ("--select", "model=x"),
    ("--tables", "counts", "--per-execution"),
    ("--format", "xml"),
])  # fmt: skip
def test_usage_errors(cli, corpus, argv):
    assert cli("stats", "--corpus", str(corpus), *argv).code == 2


def test_missing_corpus_is_usage(cli, tmp_path):
    assert cli("stats", "--corpus", str(tmp_path / "absent")).code == 2


def test_select(cli, corpus):
    run = cli("stats", "--corpus", str(corpus), "--select", "source_id=src-a", "--tables", "counts", "--format", "json")
    document = run.json()
    assert document["select"] == {"source_id": ["src-a"]}
    assert [r["source_id"] for r in document["corpora"][0]["tables"]["counts"]] == ["src-a"]


def test_several_corpora_are_never_pooled(cli, tmp_path):
    ss.standard_corpus(tmp_path / "a.partial", corpus_id="corpus-a")
    ss.build_corpus(tmp_path / "b.partial", [ss.Execution("src-a", "pa@1")], corpus_id="corpus-b")
    run = cli("stats", "--corpus", str(tmp_path / "a"), "--corpus", str(tmp_path / "b"), "--tables", "counts", "--format", "json")
    corpora = run.json()["corpora"]
    assert [c["corpus"]["corpus_id"] for c in corpora] == ["corpus-a", "corpus-b"]
    assert [c["tables"]["counts"][0]["records"] for c in corpora] == [4, 1]
    assert cli("stats", "--corpus", str(tmp_path / "a"), "--corpus", str(tmp_path / "a.partial")).code == 2  # same corpus twice


def test_sealed_corpus_checksum_failure_exits_1(cli, tmp_path):
    ss.standard_corpus(tmp_path / "s", sealed=True)
    ok = cli("stats", "--corpus", str(tmp_path / "s"), "--format", "json")
    assert ok.code == 0 and ok.json()["corpora"][0]["corpus"]["verification"] == "checksums"
    assert "not sealed" not in ok.err
    (tmp_path / "s" / "register.jsonl").write_bytes(b"")
    bad = cli("stats", "--corpus", str(tmp_path / "s"), "--format", "json")
    assert bad.code == 1 and bad.json()["corpora"][0]["tables"] == {} and "fails the checksums check" in bad.err


def test_unreadable_file_is_a_failure(cli, corpus, tmp_path):
    prov = sorted((tmp_path / "c.partial" / "prov").rglob("*.prov.json"))[0]
    prov.write_bytes(b"{}")
    run = cli("stats", "--corpus", str(corpus), "--tables", "statements", "--format", "json", "--json")
    summary = run.json()
    assert run.code == 1 and summary["issues_by_code"] == {"corpus.read.digest": 1}
    assert summary["failures"][0]["stage"] == "prov"
