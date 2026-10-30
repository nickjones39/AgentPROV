"""``agentprov.stats`` over hand-built corpora whose counts are known (K.5.11 items 1-5; PQ Q.32; MN N.2.12).

Corpora are written by ``stats_support`` in a temporary directory; nothing reads ``~/.agentprov`` or a committed fixture
(the C.16 vectors are spec files under ``docs/architecture/examples``)."""

from __future__ import annotations

import csv
import io
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest
import stats_support as ss

from agentprov.corpus.integrity import IntegrityError
from agentprov.prov.specs import load_spec
from agentprov.stats import STATS_FORMAT, compute, fn_digest, open_corpus
from agentprov.stats.exclusions import ExclusionError, parse_exclusions
from agentprov.stats.fieldgroups import O35_GROUPS
from agentprov.stats.output import render
from agentprov.stats.source import SelectionError
from agentprov.stats.tables import compute_corpus, prov_statements
from agentprov.testing import fs_guard

ALL = ("counts", "statements", "unknowns", "field_groups")
SCHEMA = Path(__file__).resolve().parents[2] / "cli" / "schemas" / "stats-0.1.schema.json"
REPO = Path(__file__).resolve().parents[3]


@pytest.fixture
def corpus(tmp_path):
    ss.standard_corpus(tmp_path / "c.partial")
    return tmp_path / "c"


def _tables(path, tables=ALL, **kw):
    report = compute([open_corpus(path)], tables, **kw)
    return report, report.to_json()["corpora"][0]


def _validate(document):
    import jsonschema

    jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text())).validate(json.loads(json.dumps(document)))


# ------------------------------------------------------------------------------------------------ item 1: counts
def test_counts_per_source_status_and_unit(corpus):
    _, c = _tables(corpus, ("counts",))
    rows = {(r["source_id"], r["profile"]): r for r in c["tables"]["counts"]}
    for key, expected in ss.STANDARD_COUNTS.items():
        assert {k: rows[key][k] for k in expected} == expected
    assert c["population"] == {"rows": 7, "selected": 7, "n_executions": 4}
    # outcome-only and scenario records are never executions (R-28; NC-ALL-13)
    assert sum(r["n_executions"] for r in rows.values()) == 4
    assert c["tables"]["register"] == [{"code": "map.accounting_unverifiable", "disposition": "sealed", "n": 2,
                                        "severity": "info", "stage": "map"}]  # fmt: skip


def test_registry_parts_come_from_the_registry(tmp_path):
    ss.build_corpus(tmp_path / "c.partial", [ss.Execution("mandate-agentdojo-eval", "mandate-agentdojo-eval@1")])
    _, c = _tables(tmp_path / "c", ("counts",))
    row = c["tables"]["counts"][0]
    assert row["registry_parts"] == ["head"] and row["registry_import_status"] == ["supported"]


# ------------------------------------------------------------------------------------------------ item 2: statements
def test_statements_by_class_bundle_and_rule(corpus):
    _, c = _tables(corpus, ("statements",))
    got = Counter()
    for r in c["tables"]["statements"]:
        got[(r["source_id"], r["bundle"], r["method"], r["stype"], r["evidence"], r["rule"])] += r["n"]
    n_with_prov = {"src-a": 3, "src-b": 2}
    expected = Counter({(s, *k): v * n for s, n in n_with_prov.items() for k, v in ss.EXPECTED_STATEMENTS.items()})
    assert got == expected
    by_class = Counter()
    for r in c["tables"]["statements"]:
        by_class[r["evidence"]] += r["n"]
    assert sum(by_class.values()) == sum(r["n"] for r in c["tables"]["statements"])  # class totals = statement total
    assert {r["rule"] for r in c["tables"]["statements"]} <= set(load_spec().rules)  # every rule is shipped
    structural = {(r["source_id"], r["bundle"], r["method"], r["stype"]): r["n"] for r in c["tables"]["statements_structural"]}
    assert structural == {(s, *k): v * n for s, n in n_with_prov.items() for k, v in ss.EXPECTED_STRUCTURAL.items()}
    assert c["failures"] == {}


def test_statements_at_execution_grain(corpus):
    report, c = _tables(corpus, ("statements",), per_execution=True)
    rows = c["tables"]["statements_by_execution"]
    assert report.to_json()["per_execution"] is True
    per_ex = Counter(r["ex"] for r in rows)
    assert len(per_ex) == 5 and set(per_ex.values()) == {len(ss.EXPECTED_STATEMENTS)}
    totals = Counter()
    for r in rows:
        totals[(r["source_id"], r["bundle"], r["method"], r["stype"], r["evidence"], r["rule"])] += r["n"]
    aggregate = Counter({(r["source_id"], r["bundle"], r["method"], r["stype"], r["evidence"], r["rule"]): r["n"]
                         for r in c["tables"]["statements"]})  # fmt: skip
    assert totals == aggregate  # the aggregate table is the sum of the execution grain
    assert "statements_by_execution" not in _tables(corpus, ("statements",))[1]["tables"]


def test_statements_equal_an_independent_recount_of_engine_output(tmp_path):
    """Real ``agentprov-prov/0.1`` output of the engine, recounted by a naive walker written here."""
    sys.path.insert(0, str(REPO / "tests" / "render"))
    import render_support as rs

    (tmp_path / "scratch").mkdir()
    built = rs.build_corpus(tmp_path / "c", tmp_path / "scratch", executions=2)
    rules = frozenset(load_spec().rules)
    for doc in built["docs"].values():
        classified, structural, unknown = prov_statements(doc, rules=rules)
        naive = Counter()
        sections = [doc, *doc.get("bundle", {}).values()]
        for content in sections:
            for name, entries in content.items():
                if name in ("prefix", "bundle"):
                    continue
                for entry in entries.values():
                    naive["classified" if "apv:evidenceClass" in entry else "structural"] += 1
        assert sum(classified.values()) == naive["classified"] > 0
        assert sum(structural.values()) == naive["structural"]
        assert not unknown  # every rule id the engine emits is in the shipped catalogue
        assert {k[0] for k in classified} <= {"core", "inference", "assessment", "toplevel"}
        assert any(k[0] == "inference" for k in classified) and any(k[0] == "assessment" for k in classified)


def test_unknown_rules_and_malformed_prov_are_failures(tmp_path):
    hostile = "aprov.n_scope@1" + chr(0x202E) + "\x1b[2J"
    doc = json.loads(json.dumps(ss.PROV_DOC))
    doc["activity"]["x:t1"]["apv:rule"] = hostile
    broken = {"prefix": {}, "bundle": {"xd:bundle.weird.zz": {}}}
    ss.build_corpus(tmp_path / "c.partial", [ss.Execution(prov=doc), ss.Execution(prov=broken)])
    _, c = _tables(tmp_path / "c", ("statements",))
    assert c["failures"] == {"stats.prov.bundle": 1, "stats.prov.rule_unknown": 1}
    rules = {r["rule"] for r in c["tables"]["statements"]}
    assert not any(ch in "".join(rules) for ch in (chr(0x202E), "\x1b"))  # escaped (G.8.6)
    assert any("<U+202E>" in r for r in rules)


# ------------------------------------------------------------------------------------------------ items 3-4
def test_unknown_shares_sum_to_one(corpus):
    _, c = _tables(corpus, ("unknowns",))
    rows = c["tables"]["unknowns"]
    assert {r["group"] for r in rows} == set(O35_GROUPS)
    for row in rows:
        shares = [v for k, v in row.items() if k.startswith("share_")]
        if row["n"]:
            assert abs(sum(shares) - 1) < 1e-5
        else:
            assert all(v is None for v in shares)
        assert row["not_applicable"] == 0  # nothing in these AERs declares not_applicable
    by_occ = {(r["source_id"], r["occurrence"]): r for r in rows}
    tooldefs = by_occ[("src-a", "tooldefs.model_call.tools")]
    assert (tooldefs["n"], tooldefs["not_recorded"], tooldefs["undeclared"]) == (3, 3, 3)


def test_field_group_coverage(corpus):
    _, c = _tables(corpus, ("field_groups",))
    rows = {(r["source_id"], r["group"]): r for r in c["tables"]["field_groups"]}
    for group, (status, undeclared) in ss.EXPECTED_CELLS.items():
        row = rows[("src-a", group)]
        assert row["n_executions"] == 3 and row["cells"] == 3 and row[status.removeprefix("unk:")] == 3
        assert row["coverage"] == (1.0 if status in ("O", "D") else 0.0)
        assert row["undeclared"] == (3 if undeclared else 0)
    env = rows[("src-a", "env")]
    assert env["cells"] == 0 and env["coverage"] is None  # no state change: no cell, no rate
    covered = sum(1 for s, _ in ss.EXPECTED_CELLS.values() if s in ("O", "D"))
    total = rows[("src-a", "all")]
    assert total["cells"] == 3 * len(ss.EXPECTED_CELLS) and total["coverage"] == round(covered / len(ss.EXPECTED_CELLS), 6)
    assert rows[("src-b", "ctx")]["n_executions"] == 1  # the unobserved execution and the scenario are outside


def test_not_applicable_leaves_the_denominator(tmp_path):
    records = ss.agent_records(ss.ex_id(0))
    for rec in records:
        if rec["id"] == "fx0":
            rec.pop("content")
            rec["unk"] = {"/content": "not_applicable"}
    ss.build_corpus(tmp_path / "c.partial", [ss.Execution(records=records), ss.Execution()])
    _, c = _tables(tmp_path / "c", ("field_groups",))
    payload = next(r for r in c["tables"]["field_groups"] if r["group"] == "payload")
    assert (payload["cells"], payload["not_applicable"], payload["denominator"], payload["coverage"]) == (2, 1, 1, 1.0)


# ------------------------------------------------------------------------------------------------ exclusions (D.16.17 item 4)
def _exclusion(rates='["field_groups"]'):
    text = f"""version = 1
family = "tst"
[[exclusion]]
id = "tst.rate.harness_failure"
profiles = ["pa"]
issue_codes = ["map.accounting_unverifiable"]
rates = {rates}
basis = "test"
"""
    return parse_exclusions(text.encode(), "tst")


def test_declared_exclusions_drive_the_population(corpus):
    reader = open_corpus(corpus)
    c = compute_corpus(reader, tables=("counts", "field_groups", "unknowns"), exclusions=_exclusion())
    fg = {(r["source_id"], r["group"]): r for r in c.tables["field_groups"]}
    assert fg[("src-a", "ctx")]["n_executions"] == 2 and fg[("src-a", "ctx")]["excluded"] == 1
    assert fg[("src-b", "ctx")]["excluded"] == 0  # src-b carries the code, but its profile is not in scope
    unk = next(r for r in c.tables["unknowns"] if r["source_id"] == "src-a" and r["occurrence"] == "ctx.model_call.input")
    assert unk["excluded"] == 0 and unk["n"] == 3  # the declaration names field_groups only
    counts = {r["source_id"]: r for r in c.tables["counts"]}
    assert counts["src-a"]["rate_excluded"] == 1 and counts["src-b"]["rate_excluded"] == 0


@pytest.mark.parametrize("text", [
    'version = 1\nfamily = "other"\n',
    'version = 1\nfamily = "tst"\n[[exclusion]]\nid = "x"\nprofiles = ["p"]\nissue_codes = ["map.x"]\nrates = ["outcome"]\nbasis = "b"\n',
    'version = 1\nfamily = "tst"\n[[exclusion]]\nid = "tst.rate.a"\nprofiles = ["p"]\nrates = ["outcome"]\nbasis = "b"\n',
    'version = 1\nfamily = "tst"\n[[exclusion]]\nid = "tst.rate.a"\nprofiles = ["p"]\nissue_codes = ["map.x"]\nrates = ["all"]\nbasis = "b"\n',
    'version = 1\nfamily = "tst"\n[[exclusion]]\nid = "tst.rate.a"\nprofiles = ["p"]\njudgement_origins = ["default"]\nrates = ["outcome"]\nbasis = "b"\n',
])  # fmt: skip
def test_malformed_exclusion_declarations_are_refused(text):
    with pytest.raises(ExclusionError):
        parse_exclusions(text.encode(), "tst")


def test_stats_code_names_no_source():
    """CLAUDE.md rule 9 / D.16.17 item 4: no source name or source-specific code in the stats package."""
    from agentprov.adapters.registry import REGISTRY

    package = REPO / "src" / "agentprov" / "stats"
    text = "\n".join(p.read_text() for p in package.glob("*.py"))
    for reg in REGISTRY:
        assert f'"{reg.source_id}"' not in text and f"'{reg.source_id}'" not in text
    assert "dtap" not in text.lower().replace("dtap-bench", "")  # only cited in prose, never as a code branch


# ------------------------------------------------------------------------------------------------ selection
def test_selection(corpus):
    _, c = _tables(corpus, ("counts",), select={"source_id": "src-b", "unit": ["agent_execution", "scenario"]})
    assert [r["records"] for r in c["tables"]["counts"]] == [3]
    assert c["population"]["selected"] == 3 and c["tables"]["register"][0]["n"] == 1
    _, c = _tables(corpus, ("counts",), select={"execution_observed": "false"})
    assert c["population"]["selected"] == 2
    with pytest.raises(SelectionError):
        compute([open_corpus(corpus)], ("counts",), select={"model": "x"})


# ------------------------------------------------------------------------------------------------ item 5
def test_output_is_schema_valid_and_deterministic(corpus):
    report, _ = _tables(corpus, (*ALL, "artefacts"), per_execution=True)
    document = report.to_json()
    assert document["format"] == STATS_FORMAT and document["fn_digest"] == fn_digest()
    _validate(document)
    again = compute([open_corpus(corpus)], (*ALL, "artefacts"), per_execution=True).to_json()
    for fmt in ("json", "text", "markdown", "csv"):
        assert render(document, fmt) == render(again, fmt)
    assert render(document, "json").endswith(b"\n") and b"\r" not in render(document, "csv")


def test_bytes_do_not_depend_on_the_hash_seed(corpus):
    script = ("import sys; from agentprov.stats import compute, open_corpus; from agentprov.stats.output import render;"
              "sys.stdout.buffer.write(render(compute([open_corpus(sys.argv[1])], ('counts','statements','unknowns',"
              "'field_groups','artefacts')).to_json(), 'json'))")  # fmt: skip
    outputs = set()
    for seed in ("0", "12345"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        outputs.add(subprocess.run([sys.executable, "-c", script, str(corpus)], env=env, capture_output=True, check=True).stdout)
    assert len(outputs) == 1


def test_stats_writes_nothing_into_the_corpus(corpus, tmp_path):
    with fs_guard.unchanged(tmp_path / "c.partial"):
        report = compute([open_corpus(corpus)], (*ALL, "artefacts"), per_execution=True)
        for fmt in ("json", "text", "markdown", "csv"):
            render(report.to_json(), fmt)


def test_no_content_is_printed(tmp_path):
    marker = "SECRET" + "PAYLOAD" + "TEXT"
    records = ss.agent_records(ss.ex_id(0))
    for rec in records:
        if rec["k"] in ("message", "fixture"):
            for part in rec.get("parts", []):
                if "text" in part:
                    part["text"] = marker
            if "content" in rec:
                rec["content"] = marker
    ss.build_corpus(tmp_path / "c.partial", [ss.Execution(records=records)])
    report, _ = _tables(tmp_path / "c", (*ALL, "artefacts"), per_execution=True)
    for fmt in ("json", "text", "markdown", "csv"):
        assert marker.encode() not in render(report.to_json(), fmt)


def test_hostile_model_labels_are_escaped(tmp_path):
    records = ss.agent_records(ss.ex_id(0), model="m" + chr(0x202E) + "\x07=cmd")
    ss.build_corpus(tmp_path / "c.partial", [ss.Execution(records=records, unit="agent_execution")])
    report, c = _tables(tmp_path / "c", ("counts", "artefacts"))
    models = {r["model"] for r in c["tables"]["artefacts"]}
    assert models and all("\x07" not in m and chr(0x202E) not in m for m in models)
    for fmt in ("json", "text", "markdown", "csv"):
        data = render(report.to_json(), fmt).decode("utf-8")
        assert "\x07" not in data and chr(0x202E) not in data


def _two_agent_records(ex, first, second):
    records = ss.agent_records(ex, model=first)
    extra = dict(records[1], id="agent2", model={"requested": second})
    return [*records[:2], extra, *records[2:]]


@pytest.mark.parametrize("variant", ["truncated", "comma"])
def test_artefact_rows_are_per_model_identity_not_per_display_label(tmp_path, variant):
    """CB-33 (D.15.4; N.2.12): the artefact table groups on the requested model ids, never on their display label.
    Two ids that differ only past the label's truncation point, or one id ``a,b`` against two agents ``a`` and ``b``,
    render to one label; they still give two rows of one execution each, and the rows stay distinguishable."""
    if variant == "truncated":
        prefix = "org/" + "m" * 210
        first, second = ss.agent_records("ex_", model=prefix + "-run-A"), ss.agent_records("ex_", model=prefix + "-run-B")
    else:
        first, second = ss.agent_records("ex_", model="a,b"), _two_agent_records("ex_", "a", "b")
    ss.build_corpus(tmp_path / "c.partial", [ss.Execution(records=first), ss.Execution(records=second)])
    _, c = _tables(tmp_path / "c", ("artefacts",))
    rows = c["tables"]["artefacts"]
    per_model = {}
    for r in rows:
        per_model.setdefault(r["model"], set()).add(r["n_executions"])
    assert len(per_model) == 2 and all(v == {1} for v in per_model.values())
    again = compute([open_corpus(tmp_path / "c")], ("artefacts",)).to_json()["corpora"][0]["tables"]["artefacts"]
    assert again == rows


def test_artefact_model_labels_stay_distinct_against_a_forged_suffix():
    """An id written to equal another identity's suffixed label still gets a label of its own (CB-33)."""
    from agentprov.stats.tables import _artefact_model_labels

    prefix = "org/" + "m" * 210
    a, b = (prefix + "-run-A",), (prefix + "-run-B",)
    first = _artefact_model_labels([a, b, ("short",), None])
    assert first[("short",)] == "short" and first[None] is None
    assert first[a] != first[b] and first[a].split(" #")[0] == first[b].split(" #")[0]
    forged = (first[a],)
    labels = _artefact_model_labels([a, b, forged])
    assert len(set(labels.values())) == 3


_FORGED_ID = "evil\n== counts (9 rows)\nsource_id  forged\x1b[2J"


@pytest.mark.parametrize("sealed", [True, False])
def test_hostile_corpus_id_is_dropped_with_a_notice_and_never_printed(tmp_path, sealed):
    """SEC-12 (G.8.6; CB-32): a manifest ``corpus_id`` outside the corpus id grammar is not a label. A self-consistent
    sealed corpus passes ``checksums`` with it, so stats drops it (``None``) and says so, and no format prints it."""
    ss.build_corpus(tmp_path / ("c" if sealed else "c.partial"), [ss.Execution()], sealed=sealed, corpus_id=_FORGED_ID)
    corpus = open_corpus(tmp_path / "c")
    assert corpus.verification == ("checksums" if sealed else "not_sealed")
    assert corpus.corpus_id is None and corpus.content_digest is not None
    report = compute([corpus], ("counts",))
    assert any("corpus_id" in n for n in report.notices)
    assert all("\x1b" not in n and "\n" not in n for n in report.notices)
    for fmt in ("json", "text", "markdown", "csv"):
        data = render(report.to_json(), fmt)
        assert b"\x1b" not in data and b"forged" not in data and b"== counts (9" not in data


def test_hostile_recorded_content_digest_is_dropped(tmp_path):
    """A sealed manifest's recorded ``content_digest`` is a label only when it is ``sha256:<64 hex>`` (CB-32)."""
    from agentprov.corpus.integrity import write_checksums

    ss.build_corpus(tmp_path / "s", [ss.Execution()], sealed=True)
    manifest = json.loads((tmp_path / "s" / "corpus.json").read_text())
    manifest["content_digest"] = "sha256:00\n== counts (9 rows)\x1b[2J"
    (tmp_path / "s" / "corpus.json").write_bytes(json.dumps(manifest, sort_keys=True).encode() + b"\n")
    (tmp_path / "s" / "checksums.sha256").unlink()
    write_checksums(tmp_path / "s")  # self-consistent: the hostile manifest passes the checksums level
    corpus = open_corpus(tmp_path / "s")
    assert corpus.verification == "checksums" and corpus.content_digest is None
    report = compute([corpus], ("counts",))
    assert any("content_digest" in n for n in report.notices)
    for fmt in ("text", "markdown", "csv"):
        assert b"\x1b" not in render(report.to_json(), fmt)


def test_corpus_label_parts_are_escaped_and_csv_guards_tab_and_cr(tmp_path):
    """Defence in depth (CB-32): the text label escapes ``corpus_id`` and the digests, and the CSV ``corpus_id`` cell the
    id, even for a document that did not come from :func:`open_corpus`; a CSV cell led by TAB or CR is neutralised like
    ``=``."""
    ss.build_corpus(tmp_path / "s", [ss.Execution()], sealed=True)
    document = compute([open_corpus(tmp_path / "s")], ("counts",)).to_json()
    for lead in ("\t", "\r"):
        document["corpora"][0]["corpus"].update(corpus_id=lead + "=cmd" + _FORGED_ID, root_digest="r\x1b[2J\nx",
                                                content_digest="c\x1b[2J\nx")  # fmt: skip
        text = render(document, "text").decode("utf-8")
        label = text.split("\n")[2]
        assert label.startswith("corpus ") and "content " in label and "root " in label
        assert "\x1b" not in text and "\r" not in text and "\n== counts (9" not in text
        document["corpora"][0]["tables"]["counts"][0]["source_id"] = lead + "=cmd"
        rows = list(csv.reader(io.StringIO(render(document, "csv").decode("utf-8"))))
        assert all("\x1b" not in cell and "\n" not in cell for row in rows for cell in row)
        assert rows[1][0].startswith("<U+") and rows[1][rows[0].index("source_id")] == "'" + lead + "=cmd"


# ------------------------------------------------------------------------------------------------ verification
def test_sealed_corpus_is_verified_and_labelled(tmp_path):
    ss.standard_corpus(tmp_path / "s", sealed=True)
    corpus = open_corpus(tmp_path / "s")
    assert corpus.verification == "checksums" and corpus.root_digest.startswith("sha256:")
    assert corpus.content_digest.startswith("sha256:") and corpus.identity()["state"] == "sealed"
    (tmp_path / "s" / "register.jsonl").write_bytes(b"")
    with pytest.raises(IntegrityError):
        open_corpus(tmp_path / "s")
    failed = open_corpus(tmp_path / "s", raise_on_failure=False)
    report = compute([failed], ALL).to_json()
    assert report["corpora"][0]["tables"] == {} and report["corpora"][0]["failures"] == {"checksums.mismatch": 1}
    _validate(report)
    with pytest.raises(IntegrityError):  # the chain level (U4) fails the tampered register too
        open_corpus(tmp_path / "s", verify="chain")
    assert open_corpus(tmp_path / "s", verify="chain", raise_on_failure=False).verification == "failed"


def test_working_corpus_is_not_verified(corpus):
    opened = open_corpus(corpus)
    assert opened.verification == "not_sealed" and opened.root_digest is None
    assert opened.content_digest.startswith("sha256:")  # the working manifest's content digest (H.5.4)
    assert open_corpus(corpus, verify="none").verification == "skipped"


def test_artefact_table_matches_the_shared_layer(corpus):
    from agentprov.artefacts import discover_catalogues, scan, table

    opened = open_corpus(corpus)
    _, c = _tables(corpus, ("artefacts",))
    rows = c["tables"]["artefacts"]
    assert rows and {r["source_id"] for r in rows} == {"src-a", "src-b"}
    catalogues = discover_catalogues()
    findings = []
    for row in opened.iter_rows():
        if row.source_id == "src-a":
            doc = opened.reader.read_aer(row)
            findings.extend(scan([*doc.records, doc.seal], catalogues))
    n_a = {r["model"]: r["n_executions"] for r in rows if r["source_id"] == "src-a"}
    expected = {t.artefact_id: t.executions for t in table(findings)}
    assert sum(n_a.values()) == 4
    got = Counter()
    for r in rows:
        if r["source_id"] == "src-a":
            got[r["artefact_id"]] += r["executions"]
    assert dict(got) == expected
