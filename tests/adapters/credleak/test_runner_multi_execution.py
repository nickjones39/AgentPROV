"""Runner support for multi-execution whole-file artefacts, R-10k-1 (D-320; D.2.9, D.19.14; HL H.7.1, H.7.2).

A credleak cell is one JSON file holding many runs, and each run is one execution with source key
``sha256:<cell>#{"p":"/runs/<i>"}`` (HL H.7.1). The reader declares ``multi_execution``, so the ``total`` map job maps
every run as its own unit (``per_item`` framing), and the importer resumes and collapses (D-202) each execution by its
source key. A cell that fails the strict loader is still one degenerate AER; a cell with no run is registered, not
mapped. The cells are generated at test time and carry no planted value.
"""

from __future__ import annotations

import dataclasses
import hashlib
import importlib.util
import io
import json
import sys
import zipfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

_TESTS = Path(__file__).resolve().parents[2]
for _path in (_TESTS / "security", _TESTS / "corpus", _TESTS / "unit" / "release", _TESTS / "adapters",
              _TESTS.parent / "tools"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import corpus_harness as harness  # noqa: E402
import credleak_support as support  # noqa: E402
import verify_support as vs  # noqa: E402
from corpus_harness import verify  # noqa: E402


def _load_e2e() -> Any:
    """credleak's ``test_withhold_e2e``, loaded by path under its own name: geminicli has a module of the same name,
    and a bare import took whichever directory came first on ``sys.path`` in the worker (bug pass BF-36)."""
    name = "agentprov_tests_credleak_withhold_e2e"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name("test_withhold_e2e.py"))
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


e2e = _load_e2e()

from agentprov.progress import ProgressEvent  # noqa: E402

cli = harness.cli

LABEL = "p15b-run-data/01-injection-map/T1-file-document/test-model/run__T1__test-model__T1.9__2026-06-11T08-00-00-000Z.json"
OTHER = "p15b-run-data/01-injection-map/T1-file-document/test-model/run__T1__test-model__T1.8__2026-06-11T08-00-00-000Z.json"


def _deposit(base: Path, members: Mapping[str, bytes], *, record: int = 1, name: str = "deposit.zip") -> tuple[Path, dict[str, Any]]:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for label, data in members.items():
            zf.writestr(label, data)
    path = base / name
    path.write_bytes(buf.getvalue())
    data = path.read_bytes()
    pin = {"role": "head", "kind": "zenodo", "doi": f"10.5281/zenodo.{record}", "record": record, "version": f"v{record}",
           "file": path.name, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    return path, pin


def _run(path: Path, pin: Mapping[str, Any], corpus: Path, **kwargs: Any) -> Any:
    from agentprov.adapters.runner.importer import ArchiveTree, import_source
    from agentprov.corpus.writer import CorpusWriter

    tree = ArchiveTree(path, pin=pin, sha256=pin["sha256"], size=pin["bytes"])
    kwargs.setdefault("snapshot_id", "head")
    kwargs.setdefault("mode", "release")
    with CorpusWriter(corpus) as writer:
        return import_source("credleak-p15b", tree, corpus=writer, profile_id="credleak-p15b", part="head", pin=pin,
                             workers=1, **kwargs)


def _import(base: Path, runs: int, *, label: str = LABEL) -> Any:
    path, pin = _deposit(base, {label: support.synthetic_cell(runs=runs, scenario="T1.9", technique="T1")})
    return _run(path, pin, base / "c")


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line]


def _tree(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def _two_runs(base: Path) -> tuple[Path, dict[str, Any]]:
    return _deposit(base, {LABEL: support.synthetic_cell(runs=2, scenario="T1.9", technique="T1")})


def test_a_single_run_cell_imports_today(tmp_path):
    """The control: one run per cell (the end-to-end withholding test relies on it)."""
    report = _import(tmp_path, 1)
    assert report.exit_code == 0 and report.counters["mapped"] == 1 and report.counters["degenerate"] == 0
    (row,) = _jsonl(tmp_path / "c.partial" / "executions.jsonl")
    assert row["source_key"].endswith('#{"p":"/runs/0"}')


def test_a_two_run_cell_imports_as_two_executions(tmp_path):
    report = _import(tmp_path, 2)
    assert report.exit_code == 0, report.counters
    assert report.counters["mapped"] == 2 and report.counters["degenerate"] == 0
    assert report.counters["sealed_clean"] + report.counters["sealed_with_issues"] == 2
    rows = _jsonl(tmp_path / "c.partial" / "executions.jsonl")
    keys = sorted(r["source_key"] for r in rows)
    digest = keys[0][len("sha256:") : len("sha256:") + 64]
    assert keys == [f'sha256:{digest}#{{"p":"/runs/0"}}', f'sha256:{digest}#{{"p":"/runs/1"}}']
    assert len({r["ex"] for r in rows}) == 2 and all(r["n_origins"] == 1 for r in rows)
    for row in rows:  # each AER names its own run as its source key
        header = json.loads((tmp_path / "c.partial" / row["paths"]["aer"]).read_bytes().split(b"\n", 1)[0])
        assert header["source_key"] == {"sha256": digest, "loc": json.loads(row["source_key"].split("#", 1)[1])}


def test_resume_after_a_crash_between_two_runs_maps_only_the_second(tmp_path):
    path, pin = _two_runs(tmp_path)

    class Stop:
        def emit(self, event: ProgressEvent) -> None:
            if event.kind == "unit_done":
                raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        _run(path, pin, tmp_path / "c", progress=Stop())
    (first,) = _jsonl(tmp_path / "c.partial" / "executions.jsonl")
    assert first["source_key"].endswith('#{"p":"/runs/0"}')
    resumed = _run(path, pin, tmp_path / "c")
    assert resumed.exit_code == 0, resumed.counters
    assert (resumed.counters["mapped"], resumed.counters["skipped_resume"], resumed.counters["duplicates"]) == (1, 1, 0)
    _run(path, pin, tmp_path / "w")
    a, b = _tree(tmp_path / "c.partial"), _tree(tmp_path / "w.partial")
    a.pop("corpus.json"), b.pop("corpus.json")
    assert a == b


def test_a_limit_stops_inside_a_cell_and_resume_continues(tmp_path):
    path, pin = _two_runs(tmp_path)
    first = _run(path, pin, tmp_path / "c", limit=1)
    assert first.counters["mapped"] == 1 and first.partial
    second = _run(path, pin, tmp_path / "c")
    assert (second.counters["mapped"], second.counters["skipped_resume"]) == (1, 1)
    third = _run(path, pin, tmp_path / "c")
    assert (third.counters["mapped"], third.counters["skipped_resume"]) == (0, 2)
    assert len(_jsonl(tmp_path / "c.partial" / "executions.jsonl")) == 2


def test_a_byte_identical_cell_in_a_second_snapshot_collapses_both_runs(tmp_path):
    cell = support.synthetic_cell(runs=2, scenario="T1.9", technique="T1")
    one, pin_one = _deposit(tmp_path, {LABEL: cell}, record=1, name="v1.zip")
    other = support.synthetic_cell(runs=1, scenario="T1.8", technique="T1")
    two, pin_two = _deposit(tmp_path, {LABEL: cell, OTHER: other}, record=2, name="v2.zip")
    assert _run(one, pin_one, tmp_path / "c", snapshot_id="v1").exit_code == 0
    report = _run(two, pin_two, tmp_path / "c", snapshot_id="v2")
    assert report.exit_code == 0, report.counters
    assert (report.counters["mapped"], report.counters["duplicates"], report.counters["skipped_resume"]) == (1, 2, 0)
    partial = tmp_path / "c.partial"
    rows = _jsonl(partial / "executions.jsonl")
    shared = sorted(r["source_key"] for r in rows if r["snapshot_ids"] == ["v1", "v2"])
    assert len(shared) == 2 and [r["snapshot_ids"] for r in rows if r["source_key"] not in shared] == [["v2"]]
    assert all(r["n_origins"] == 2 for r in rows if r["source_key"] in shared)
    collapsed = [e for e in _jsonl(partial / "register.jsonl") if e["code"] == "dedup.collapsed"]
    assert sorted(e["subject"]["source_key"] for e in collapsed) == shared
    again = _run(two, pin_two, tmp_path / "c", snapshot_id="v2")  # a resumed second snapshot is skipped, not collapsed
    assert (again.counters["mapped"], again.counters["skipped_resume"], again.counters["duplicates"]) == (0, 3, 0)


def test_a_crashed_cell_resumes_as_its_one_degenerate_execution_not_as_its_runs(tmp_path, monkeypatch):
    """A crashed per-item job seals the whole cell as one degenerate AER (document-root key). The resume, whose job now
    succeeds, keeps that one execution (``skipped_resume``) and never adds the cell's runs beside it (the same evidence
    twice); the indexed degenerate row is not rewritten. In process (dev mode) so the crash can be injected."""
    import agentprov.adapters.runner as runner

    path, pin = _two_runs(tmp_path)

    def crash(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("injected worker crash")

    with monkeypatch.context() as patched:
        patched.setattr(runner, "map_artefact_units", crash)
        first = _run(path, pin, tmp_path / "c", mode="dev", in_process=True)
    assert (first.counters["mapped"], first.counters["degenerate"]) == (1, 1)
    (row,) = _jsonl(tmp_path / "c.partial" / "executions.jsonl")
    assert row["source_key"].endswith('#{"p":""}')
    before = (tmp_path / "c.partial" / "executions.jsonl").read_bytes()
    resumed = _run(path, pin, tmp_path / "c", mode="dev", in_process=True)
    assert (resumed.counters["mapped"], resumed.counters["skipped_resume"]) == (0, 1)
    assert (tmp_path / "c.partial" / "executions.jsonl").read_bytes() == before


def test_a_cell_with_no_run_is_registered_not_mapped(tmp_path):
    report = _import(tmp_path, 0)
    assert report.exit_code == 0, report.counters
    assert (report.counters["mapped"], report.counters["registered"], report.counters["degenerate"]) == (0, 1, 0)
    (entry,) = [e for e in _jsonl(tmp_path / "c.partial" / "register.jsonl") if e["code"] == "select.not_execution_artefact"]
    assert entry["disposition"] == "not_imported" and "0 located items" in entry["detail"]
    assert _jsonl(tmp_path / "c.partial" / "executions.jsonl") == []


def test_a_cell_failing_the_strict_loader_is_one_degenerate_aer(tmp_path):
    path, pin = _deposit(tmp_path, {LABEL: b'{"runs": [1, 2], "runs": []}'})  # a duplicate key: the strict loader refuses
    report = _run(path, pin, tmp_path / "c")
    assert (report.counters["mapped"], report.counters["degenerate"]) == (1, 1)
    (row,) = _jsonl(tmp_path / "c.partial" / "executions.jsonl")
    assert row["source_key"].endswith('#{"p":""}')
    again = _run(path, pin, tmp_path / "c")
    assert (again.counters["mapped"], again.counters["skipped_resume"]) == (0, 1)


def test_map_artefact_total_keeps_the_single_item_rule():
    """The single-item entry point is unchanged for every reader: a two-run cell through it is one degenerate outcome."""
    from agentprov.adapters.runner import map_artefact_total, map_artefact_units

    cell = support.synthetic_cell(runs=2, scenario="T1.9", technique="T1")
    origin = support.member_origin(LABEL, cell)
    outcome, _unit = map_artefact_total(cell, origin, profile_id="credleak-p15b", part="head")
    assert outcome.degenerate
    pairs = map_artefact_units(cell, origin, profile_id="credleak-p15b", part="head")
    assert [u.primary.locator.key() for _o, u in pairs] == [{"p": "/runs/0"}, {"p": "/runs/1"}]
    assert not any(o.degenerate for o, _u in pairs) and len({o.ex for o, _u in pairs}) == 2


# ------------------------------------------------------------------------------------------------ sealed (release)
_SNAPSHOT = """
[[sources.snapshots]]
snapshot_id = "{sid}"
origin = {{ kind = "zenodo", doi = "10.5281/zenodo.{record}", file = "{file}" }}
alt_origins = []
raw_policy = "include"
"""


def _cell(runs: int, scenario: str, *, planted_in: int | None = None) -> bytes:
    """A synthetic cell; with ``planted_in`` only that run's tool output holds a test-made sentinel (never printed)."""
    cell = json.loads(support.synthetic_cell(runs=runs, scenario=scenario, technique="T1"))
    if planted_in is not None:
        cell["runs"][planted_in]["turns"][0]["toolCalls"][0]["output"] = f"API_TOKEN={support.sentinel('tag')}\n"
    return json.dumps(cell, indent=2).encode()


def test_a_sealed_two_snapshot_corpus_of_multi_run_cells_verifies_and_withholds_the_planted_run(cli, tmp_path):
    """Sealing in release mode: the source-key ``dedup.collapsed`` subjects, the shared rows' ``n_origins`` and the
    ``duplicates`` summary pass ``verify --level chain --release``. The profile's object-scope ``[withhold]`` rules
    (D-265) withhold the planted cell's object and, by derived-hit escalation (D-235), only the run that holds the
    sentinel: its sibling run is released with its raw object withheld, as D-265 expects for the full import."""
    from agentprov.corpus.package import ReleaseArgs, seal
    from agentprov.corpus.withheld import decode_withheld

    clean = _cell(2, "T1.9")
    planted_label = LABEL.replace("T1.9", "T1.7")
    one, pin_one = _deposit(tmp_path, {LABEL: clean, planted_label: _cell(2, "T1.7", planted_in=1)}, record=1, name="v1.zip")
    two, pin_two = _deposit(tmp_path, {LABEL: clean, OTHER: _cell(1, "T1.8")}, record=2, name="v2.zip")
    assert _run(one, pin_one, tmp_path / "c", snapshot_id="v1").exit_code == 0
    assert _run(two, pin_two, tmp_path / "c", snapshot_id="v2").exit_code == 0
    head, _sep, tail = e2e.SPEC.partition("[[sources.snapshots]]")
    spec = head.rstrip() + "\n" + "".join(
        _SNAPSHOT.format(sid=sid, record=pin["record"], file=pin["file"]) for sid, pin in (("v1", pin_one), ("v2", pin_two))
    ) + "\n" + tail.partition("\n[derive]")[1] + tail.partition("\n[derive]")[2]
    report = seal(tmp_path / "c", corpus_version="0.1.0", inputs=dataclasses.replace(e2e._inputs(), spec=spec.encode()),
                  release=ReleaseArgs(release_date="2026-10-13"))
    assert report.counters["withheld_executions"] == 1
    root = tmp_path / "c"
    document = decode_withheld((root / "WITHHELD.json").read_bytes())
    assert len(document.executions) == 1
    planted = hashlib.sha256(_cell(2, "T1.7", planted_in=1)).hexdigest()
    assert planted in {e.sha256 for e in document.entries}
    rows = _jsonl(root / "executions.jsonl")
    assert sorted(r["snapshot_ids"] for r in rows) == [["v1"], ["v1", "v2"], ["v1", "v2"], ["v2"]]
    (sibling,) = [r for r in rows if r["source_key"].startswith(f"sha256:{planted}#")]
    assert sibling["source_key"].endswith('#{"p":"/runs/0"}')
    manifest = json.loads((root / "corpus.json").read_text("utf-8"))
    assert manifest["duplicates"]["collapsed"] == 2 and manifest["duplicates"]["multi_origin_executions"] == 2
    run = verify(cli, root, "--level", "chain", "--release", "--root-digest", vs.root_digest(root))
    assert run.code == 0 and run.codes() == {}, run.codes()
