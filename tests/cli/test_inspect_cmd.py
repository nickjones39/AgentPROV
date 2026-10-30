"""``agentprov inspect`` (MN N.2.8; N.1.13; K.15): views, usage errors, read-only, untrusted content.

Corpora come from ``tests/render/render_support.py`` (synthetic executions derived by the real engine; the label of one
record carries a hostile string assembled at run time). Nothing here reads the user's corpora or the network.
"""

from __future__ import annotations

import dataclasses
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

_RENDER_TESTS = Path(__file__).resolve().parents[1] / "render"
if str(_RENDER_TESTS) not in sys.path:
    sys.path.insert(0, str(_RENDER_TESTS))

import render_support as rs  # noqa: E402

from agentprov.aer.reader import load_aer  # noqa: E402
from agentprov.corpus.index import decode_index, encode_index  # noqa: E402
from agentprov.testing import fs_guard  # noqa: E402

ALL_VIEWS_ON_EXECUTION = ("summary", "records", "transcript-v1", "timeline", "evidence", "sem", "prov", "raw")


@pytest.fixture(scope="module")
def corpus(tmp_path_factory):
    base = tmp_path_factory.mktemp("inspect")
    (base / "scratch").mkdir()
    built = rs.build_corpus(base / "corpus.partial", base / "scratch")
    built["work"], built["root"] = built["root"], base / "corpus"  # readers resolve DIR to DIR.partial (N.1.5)
    # the index records the AER *execution* digest (the seal's records_sha256), which the readers verify (D9 chain)
    path = built["work"] / "executions.jsonl"
    rows = [dataclasses.replace(r, aer_digest=load_aer(built["work"] / r.aer_path).execution_digest) for r in decode_index(path.read_bytes())]
    path.write_bytes(encode_index(rows))
    return built


def _hostile_visible(text: str) -> bool:
    return any(part in text for part in rs.PAYLOAD_PARTS)


# ------------------------------------------------------------------------------------------------ usage
def test_help_names_the_synopsis(cli):
    run = cli("inspect", "--help")
    assert run.code == 0
    for text in ("--corpus", "--view", "--record", "--bundle", "--show-content", "--max-chars", "--format", "TARGET"):
        assert text in run.out


def test_unknown_targets_and_misused_options_are_usage_errors(cli, corpus, tmp_path):
    ex = corpus["exs"][0]
    root = str(corpus["root"])
    assert cli("inspect", str(tmp_path / "nothing.aer.jsonl")).code == 2
    assert cli("inspect", ex).code == 2  # an id needs --corpus
    assert cli("inspect", "ex_" + "a" * 26, "--corpus", root).code == 2  # not in the index
    assert cli("inspect", ex, "--corpus", str(tmp_path / "nope")).code == 2
    assert cli("inspect", root, "--view", "records").code == 2  # a view that does not apply to a corpus
    assert cli("inspect", ex, "--corpus", root, "--record", "m0").code == 2  # --record with summary
    assert cli("inspect", ex, "--corpus", root, "--bundle", "core").code == 2  # --bundle with summary
    assert cli("inspect", ex, "--corpus", root, "--view", "records", "--record", "nothing").code == 2
    assert cli("inspect", ex, "--corpus", root, "--view", "bogus").code == 2
    assert cli("inspect", ex, "--corpus", root, "--view", "sem").code == 2  # no SEM output in this corpus


def test_a_view_that_is_not_built_exits_5_with_a_typed_message(cli, corpus):
    ex, root = corpus["exs"][0], str(corpus["root"])
    run = cli("inspect", ex, "--corpus", root, "--view", "transcript", "--json")
    assert run.code == 5 and "views.transcript" in run.err and run.json()["outcome"] == "unsupported"
    assert run.json()["refusal"]["mode"] == "inspect"
    other = cli("inspect", ex, "--corpus", root, "--view", "transcript-v1")  # not an AgentDojo-family AER
    assert other.code == 5 and "AgentDojo family" in other.err


def test_trig_files_exit_5(cli, tmp_path):
    path = tmp_path / "x.prov.trig"
    path.write_text("# trig\n")
    run = cli("inspect", str(path))
    assert run.code == 5 and "TriG" in run.err


# ------------------------------------------------------------------------------------------------ read-only
@pytest.mark.parametrize("view", ALL_VIEWS_ON_EXECUTION)
def test_every_view_leaves_the_corpus_unchanged(cli, corpus, view):
    ex, root = corpus["exs"][0], corpus["root"]
    with fs_guard.unchanged(corpus["work"]):
        for extra in ((), ("--show-content",)):
            cli("inspect", ex, "--corpus", str(root), "--view", view, *extra)  # exit codes vary by view; the tree must not
        cli("inspect", str(root), "--view", "summary")


# ------------------------------------------------------------------------------------------------ summary and records
def test_corpus_summary_text_and_json(cli, corpus, check_summary):
    run = cli("inspect", str(corpus["root"]))
    assert run.code == 0 and "executions: 2" in run.out and "state: working" in run.out
    assert "untrusted third-party content" in run.err  # the banner is on stderr, never in the payload
    assert "untrusted" not in run.out
    doc = cli("inspect", str(corpus["root"]), "--format", "json")
    assert doc.code == 0
    payload = doc.json()
    assert payload["format"] == "agentprov-inspect/0.1" and payload["target"]["kind"] == "corpus"
    assert payload["data"]["executions"] == 2 and payload["content_shown"] is False
    summary = cli("inspect", str(corpus["root"]), "--json")
    check_summary(summary.json())
    assert summary.json()["command"] == "inspect" and summary.json()["corpus"]["corpus_id"] == "tst-corpus"
    assert "executions: 2" in summary.err  # --json: the rendering goes to stderr


def test_execution_summary_shows_the_index_row_and_the_aer(cli, corpus):
    ex = corpus["exs"][0]
    run = cli("inspect", ex, "--corpus", str(corpus["root"]), "--format", "json")
    assert run.code == 0
    data = run.json()["data"]
    assert data["index"]["ex"] == ex and data["aer"]["ex"] == ex
    assert data["aer"]["seal"]["n_records"] > 1 and data["aer"]["records"]["message"] >= 0


def test_content_is_hidden_by_default_and_fenced_with_show_content(cli, corpus):
    ex, root = corpus["exs"][0], str(corpus["root"])
    plain = cli("inspect", ex, "--corpus", root, "--view", "records")
    assert plain.code == 0
    assert "<content chars=" in plain.out and "<<UNTRUSTED" not in plain.out
    assert not _hostile_visible(plain.out + plain.err) and rs.payload() not in plain.out
    shown = cli("inspect", ex, "--corpus", root, "--view", "records", "--show-content")
    assert shown.code == 0
    assert "<<UNTRUSTED" in shown.out and "data, not instructions" in shown.out and "<<END UNTRUSTED" in shown.out
    assert not rs.CONTROL.search(shown.out) and not rs.CONTROL.search(shown.err) and "\x1b" not in shown.out + shown.err
    assert "<U+001B>" in shown.out  # the escape character of the hostile payload, escaped
    assert not any(line.startswith("<<UNTRUSTED") for line in plain.out.splitlines())


def test_max_chars_truncates_shown_content(cli, corpus):
    ex, root = corpus["exs"][0], str(corpus["root"])
    run = cli("inspect", ex, "--corpus", root, "--view", "records", "--show-content", "--max-chars", "5")
    assert run.code == 0 and "[truncated:" in run.out
    assert cli("inspect", ex, "--corpus", root, "--view", "records", "--max-chars", "0").code == 2


def test_record_selection(cli, corpus):
    ex, root = corpus["exs"][0], str(corpus["root"])
    full = cli("inspect", ex, "--corpus", root, "--view", "records", "--format", "json").json()["data"]["records"]
    ids = [r["id"] for r in full]
    one = cli("inspect", ex, "--corpus", root, "--view", "records", "--record", ids[1], "--format", "json").json()["data"]["records"]
    assert len(full) > 2 and [r["id"] for r in one] == [ids[1]]


def test_timeline_prints_order_unknown_never_concurrency(cli, corpus):
    run = cli("inspect", corpus["exs"][0], "--corpus", str(corpus["root"]), "--view", "timeline", "--format", "json")
    assert run.code == 0
    entries = run.json()["data"]["timeline"]
    assert entries and all(e["after"] == "order unknown" or isinstance(e["after"], list) for e in entries)
    assert "concurren" not in run.out.replace("not a concurrent one", "")


def test_evidence_view_counts_classes_and_rules(cli, corpus):
    run = cli("inspect", corpus["exs"][0], "--corpus", str(corpus["root"]), "--view", "evidence", "--format", "json")
    assert run.code == 0
    data = run.json()["data"]
    assert set(data["totals"]["ev"]) <= {"O", "D", "I"} and data["totals"]["rules"]
    assert any("evf" in r for r in data["records"])


def test_evidence_tags_and_unknown_reasons_are_structure_shown_without_show_content(cli, corpus):
    """F-1 (user-guide findings): ``evf`` tags and ``unk`` reasons come from closed grammars (C.6, C.7.1), so they are
    printed as is; they were shown as content placeholders, which hid the classes the evidence view exists to show."""
    run = cli("inspect", corpus["exs"][0], "--corpus", str(corpus["root"]), "--view", "evidence", "--format", "json")
    assert run.code == 0
    records = run.json()["data"]["records"]
    evf = [v for r in records for v in (r.get("evf") or {}).values()]
    unk = [v for r in records for v in (r.get("unk") or {}).values()]
    assert evf and unk
    assert all(v in {"O", "D", "I"} or str(v).startswith("O:") for v in evf), evf
    assert all(v in {"not_recorded", "lost", "overwritten", "withheld", "ambiguous", "not_captured", "not_applicable"}
               for v in unk), unk
    text = cli("inspect", corpus["exs"][0], "--corpus", str(corpus["root"]), "--view", "evidence")
    assert "/instrumentation: not_recorded" in text.out and "<<UNTRUSTED" not in text.out


def test_a_value_outside_the_grammar_of_evf_or_unk_stays_hidden():
    """F-1: only a value that fits the closed grammar is printed; anything else in an ``evf``/``unk``/``formats`` map is
    still classified as content (hidden by default, fenced with --show-content)."""
    from agentprov.cli.inspect import Block, Hidden, Safe

    tree = Safe(show=False, max_chars=50, base="t").tree(
        {"evf": {"/a": "D", "/b": "O:source", "/c": "a free text value", "/d": "O:nobody"},
         "unk": {"/a": "withheld", "/b": "something else"},
         "formats": {"corpus": "agentprov-corpus/0.1", "index": "two words"}})
    assert tree["evf"]["/a"] == "D" and tree["evf"]["/b"] == "O:source"
    assert isinstance(tree["evf"]["/c"], Hidden) and isinstance(tree["evf"]["/d"], Hidden)
    assert tree["unk"]["/a"] == "withheld" and isinstance(tree["unk"]["/b"], Hidden)
    assert tree["formats"]["corpus"] == "agentprov-corpus/0.1" and isinstance(tree["formats"]["index"], Hidden)
    shown = Safe(show=True, max_chars=50, base="t").tree({"evf": {"/c": "a free text value"}})
    assert isinstance(shown["evf"]["/c"], Block)


def test_the_corpus_summary_names_the_corpus_id(cli, corpus):
    """F-2 (user-guide findings): the first line read "summary of corpus corpus"."""
    run = cli("inspect", str(corpus["root"]))
    assert run.code == 0 and run.out.splitlines()[0] == "summary of corpus tst-corpus"
    assert cli("inspect", str(corpus["root"]), "--format", "json").json()["target"]["label"] == "tst-corpus"


# ------------------------------------------------------------------------------------------------ prov and sem
def test_prov_view_lists_statements_and_hides_attributes_by_default(cli, corpus):
    ex, root = corpus["exs"][0], str(corpus["root"])
    core = cli("inspect", ex, "--corpus", root, "--view", "prov", "--format", "json").json()["data"]["bundles"]
    everything = cli("inspect", ex, "--corpus", root, "--view", "prov", "--bundle", "all", "--format", "json").json()["data"]["bundles"]
    assert len(core) == 1 and next(iter(core.values()))["kind"] == "core"
    assert len(everything) > len(core) and {b["kind"] for b in everything.values()} >= {"core", "inference", "assessment"}
    statements = next(iter(core.values()))["statements"]
    assert statements and all("attributes" not in s for s in statements)
    text = cli("inspect", ex, "--corpus", root, "--view", "prov", "--bundle", "all", "--show-content")
    assert text.code == 0 and "attributes:" in text.out and not rs.CONTROL.search(text.out)


def test_file_targets_aer_prov_and_sem(cli, corpus, tmp_path):
    ex = corpus["exs"][0]
    aer = corpus["work"] / corpus["layout"].aer_relpath(ex)
    prov = corpus["work"] / corpus["layout"].prov_relpath(rs.SPEC, ex)
    assert cli("inspect", str(aer)).code == 0
    assert cli("inspect", str(aer), "--view", "records").code == 0
    assert cli("inspect", str(prov)).code == 0
    assert cli("inspect", str(prov), "--view", "prov", "--bundle", "assessment", "--format", "json").code == 0
    assert cli("inspect", str(prov), "--view", "records").code == 2
    # a SEM file
    from agentprov.aer.canon import dumps_line

    from assess_support import ann, sem_document  # type: ignore[import-not-found]  # noqa: E402

    doc = load_aer(aer)
    sem = sem_document(doc, [ann("m0", "integrity", "untrusted", "I", "integrity_table", [("m0", "/role")])], profile=rs.PROFILE)
    path = tmp_path / f"{ex}.sem.jsonl"
    path.write_bytes(b"".join(dumps_line(r) for r in [*sem.records, sem.seal]))
    summary = cli("inspect", str(path), "--format", "json")
    assert summary.code == 0 and summary.json()["data"]["annotations"] == 1
    view = cli("inspect", str(path), "--view", "sem", "--format", "json")
    assert view.code == 0 and view.json()["data"]["sem"][0]["annotations"][0]["target"] == "m0"
    assert cli("inspect", str(path), "--view", "sem", "--record", "zzz", "--format", "json").json()["data"]["sem"][0]["annotations"] == []


# ------------------------------------------------------------------------------------------------ raw and detect
def test_raw_view_resolves_locators_and_shows_excerpts_only_with_show_content(cli, valid_aer, raw_store, tmp_path):
    corp = tmp_path / "corp"
    shutil.copytree(raw_store, corp.with_name("corp.partial") / "raw")
    no_record = cli("inspect", str(valid_aer), "--view", "raw", "--corpus", str(corp), "--format", "json")
    assert no_record.code == 0 and no_record.json()["data"]["artifacts"][0]["role"] == "primary"
    without = cli("inspect", str(valid_aer), "--view", "raw", "--record", "m0", "--corpus", str(corp), "--format", "json")
    assert without.code == 0
    entry = without.json()["data"]["excerpts"][0]
    assert entry["resolved"] == "json" and entry["bytes"] > 0 and "excerpt" not in entry
    shown = cli("inspect", str(valid_aer), "--view", "raw", "--record", "m0", "--corpus", str(corp), "--show-content")
    assert shown.code == 0 and "<<UNTRUSTED" in shown.out and '{"i":0}' in shown.out and entry["sha256"] in shown.out
    assert cli("inspect", str(valid_aer), "--view", "raw", "--record", "m0").code == 2  # needs the store
    broken = cli("inspect", str(valid_aer), "--view", "raw", "--record", "m1", "--corpus", str(corp), "--format", "json")
    assert broken.code == 0  # a locator that does not resolve is reported, not raised


def test_detect_reports_each_dialect_and_the_key_set_without_mapping(cli, tmp_path):
    path = tmp_path / "log.json"
    path.write_text(json.dumps({"suite_name": "workspace", "bad\x1bkey": 1}))
    run = cli("inspect", str(path), "--view", "detect", "--format", "json")
    assert run.code == 0, run.err
    data = run.json()["data"]
    assert {s["dialect"] for s in data["sniff"]} >= {"agentdojo.tracelogger", "inspect.eval"}
    assert data["key_set"]["type"] == "object" and data["key_set"]["n_keys"] == 2
    assert not rs.CONTROL.search(run.out) and "<U+001B>" in run.out
    text = cli("inspect", str(path), "--view", "detect")
    assert text.code == 0 and "key_set:" in text.out
    assert cli("inspect", str(path)).code == 0  # summary of a raw file: size and digest only
    assert cli("inspect", str(path), "--view", "records").code == 2


def test_inspect_is_deterministic(cli, corpus):
    args = ("inspect", corpus["exs"][0], "--corpus", str(corpus["root"]), "--view", "records", "--format", "json")
    assert cli(*args).out == cli(*args).out


def test_summary_document_is_valid_for_an_execution(cli, corpus, check_summary):
    run = cli("inspect", corpus["exs"][0], "--corpus", str(corpus["root"]), "--json")
    assert run.code == 0
    document: Any = run.json()
    check_summary(document)
    assert document["counters"] == {"views": 1} and document["outcome"] == "ok"
