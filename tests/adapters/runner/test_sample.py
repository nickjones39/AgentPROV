"""``import --sample N --sample-mode first|spread|random --seed S`` (D-529; user-approved 2026-10-14, landing alone
2026-10-15). The sample is chosen once, from every execution of the import, before anything is mapped: it does not depend
on ``--batch-size`` (cf. CD-7) and a resume chooses the same set. Whole files are listed by label and only the chosen
ones are stored; container members and multi-execution items are listed in a first pass (the user's choice for those
sources) and only the chosen ones are mapped (members) or sealed (items)."""

from __future__ import annotations

import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path
from typing import Any

import import_support as support
import pytest

from agentprov.adapters.runner.importer import (
    ImportSample,
    LocalTree,
    SampleRefusedError,
    import_source,
    select_sample,
)
from agentprov.corpus.writer import CorpusWriter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "credleak"))
import credleak_support as credleak  # noqa: E402


def _rows(partial: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in (partial / "executions.jsonl").read_text().splitlines()]


def _keys(partial: Path) -> list[str]:
    return sorted(r["source_key"] for r in _rows(partial))


# ------------------------------------------------------------------------------------------------ the selection rules
KEYS = [(f"k{i:02d}", "a" if i < 6 else "b") for i in range(10)]


def test_first_takes_the_first_keys_in_order():
    assert select_sample(KEYS, ImportSample(3)) == {"k00", "k01", "k02"}


def test_random_is_a_pure_function_of_the_seed_and_the_keys():
    one = select_sample(KEYS, ImportSample(4, "random", "s1"))
    assert one == select_sample(list(reversed(KEYS)), ImportSample(4, "random", "s1"))  # order-free
    assert len(one) == 4 and one != select_sample(KEYS, ImportSample(4, "random", "s2"))
    expected = sorted(k for k, _ in KEYS)
    expected.sort(key=lambda k: hashlib.sha256(b"s1\x00" + k.encode()).digest())
    assert one == set(expected[:4])  # the documented rule, recomputed


def test_spread_takes_the_strata_round_robin():
    assert select_sample(KEYS, ImportSample(4, "spread")) == {"k00", "k06", "k01", "k07"}
    assert select_sample(KEYS, ImportSample(50, "spread")) == {k for k, _ in KEYS}  # N above the total: everything


def test_a_bad_sample_is_refused():
    for bad in (dict(n=0), dict(n=2, mode="weird"), dict(n=2, mode="random"), dict(n=2, mode="first", seed="s")):
        with pytest.raises(ValueError):
            ImportSample(**bad)


# ------------------------------------------------------------------------------------------------ whole files
def _agentdojo(tmp: Path, out: str, **kwargs: Any) -> Any:
    kwargs.setdefault("in_process", True)
    kwargs.setdefault("until", "aer")
    with CorpusWriter(tmp / out) as corpus:
        return import_source("agentdojo", LocalTree(tmp / "in"), corpus=corpus, part="2024-06",
                             pin_check=support.vouch(tmp / "in"), **kwargs)


def test_a_whole_file_sample_stores_and_maps_only_the_chosen_files_whatever_the_batch_size(tmp_path):
    support.agentdojo_tree(tmp_path / "in", count=5)
    one = _agentdojo(tmp_path, "a", sample=ImportSample(2, "random", "seed"), batch_size=1)
    three = _agentdojo(tmp_path, "b", sample=ImportSample(2, "random", "seed"), batch_size=3)
    assert one.counters["mapped"] == three.counters["mapped"] == 2 and one.counters["sampled_out"] == 3
    a, b = tmp_path / "a.partial", tmp_path / "b.partial"
    assert _keys(a) == _keys(b)  # CD-7: membership never depends on batching
    assert len(list((a / "raw" / "objects").rglob("*.json"))) == 2  # the sampled-out files were never stored
    manifest = json.loads((a / "corpus.json").read_text())
    assert manifest["partial"] is True and manifest["selection"]["sample"] == {
        "n": 2, "mode": "random", "seed": "seed", "candidates": 5, "selected": 2, "stratum": None}
    resumed = _agentdojo(tmp_path, "a", sample=ImportSample(2, "random", "seed"))
    assert resumed.counters["skipped_resume"] == 2 and resumed.counters["mapped"] == 0  # the same set again


def test_spread_is_refused_for_a_reader_that_names_no_stratum(tmp_path):
    support.agentdojo_tree(tmp_path / "in", count=2)
    with pytest.raises(SampleRefusedError) as caught:
        _agentdojo(tmp_path, "c", sample=ImportSample(1, "spread"))
    assert caught.value.exit_code == 5


def _tree_digests(root: Path) -> dict[str, str]:
    return {str(f.relative_to(root)): hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(root.rglob("*"))
            if f.is_file() and f.name != "lock"}


def test_a_refused_spread_writes_nothing(tmp_path):
    """NF-35 (regen item 129): the refusal comes before any write. A fresh corpus gets no manifest, and an existing one
    keeps its corpus.json (and its recorded selection.sample) and every other file byte for byte."""
    support.agentdojo_tree(tmp_path / "in", count=3)
    with pytest.raises(SampleRefusedError):
        _agentdojo(tmp_path, "fresh", sample=ImportSample(1, "spread"))
    assert not (tmp_path / "fresh.partial" / "corpus.json").exists()
    assert not (tmp_path / "fresh.partial" / "derivation.json").exists()
    _agentdojo(tmp_path, "c", sample=ImportSample(2, "random", "s"))
    before = _tree_digests(tmp_path / "c.partial")
    with pytest.raises(SampleRefusedError):
        _agentdojo(tmp_path, "c", sample=ImportSample(1, "spread"))
    assert _tree_digests(tmp_path / "c.partial") == before


def test_an_ordinary_import_records_no_sample_and_no_sampled_out_counter(tmp_path):
    support.agentdojo_tree(tmp_path / "in", count=1)
    report = _agentdojo(tmp_path, "c")
    assert "sampled_out" not in report.counters
    manifest = json.loads((tmp_path / "c.partial" / "corpus.json").read_text())
    assert "sample" not in manifest["selection"] and manifest["partial"] is False
    assert "selection" not in manifest["sources"][0]["snapshots"][0]  # NF-36: only a partial snapshot records one


# ------------------------------------------------------------------------------------------------ selections per snapshot
def _manifest(partial: Path) -> dict[str, Any]:
    return json.loads((partial / "corpus.json").read_text())


def _snapshots(partial: Path) -> dict[str, dict[str, Any]]:
    return {s["snapshot_id"]: s for s in _manifest(partial)["sources"][0]["snapshots"]}


def test_a_listed_snapshot_refuses_another_selection_and_writes_nothing(tmp_path):
    """NF-36 (regen item 130, option (a)): a snapshot the corpus lists is resumed with the selection it recorded, or
    with none (the completion path); any other selection is refused before anything is written (G4, exit 4)."""
    from agentprov.adapters.runner.importer import IdentityRefusedError, ImportFilters

    support.agentdojo_tree(tmp_path / "in", count=4)
    _agentdojo(tmp_path, "c", snapshot_id="s1", sample=ImportSample(2, "first"))
    before = _tree_digests(tmp_path / "c.partial")
    for other in ({"sample": ImportSample(3, "random", "x")}, {"sample": ImportSample(3, "first")}, {"limit": 1},
                  {"filters": ImportFilters(include_paths=("**",))}):
        with pytest.raises(IdentityRefusedError) as caught:
            _agentdojo(tmp_path, "c", snapshot_id="s1", **other)
        assert caught.value.exit_code == 4
        assert _tree_digests(tmp_path / "c.partial") == before
    again = _agentdojo(tmp_path, "c", snapshot_id="s1", sample=ImportSample(2, "first"))  # the same selection resumes
    assert again.counters["skipped_resume"] == 2 and again.counters["mapped"] == 0
    _agentdojo(tmp_path, "full", snapshot_id="s1")  # a complete snapshot refuses a filter or sample too
    for other in ({"sample": ImportSample(1, "first")}, {"filters": ImportFilters(include_paths=("**",)), "limit": 1}):
        with pytest.raises(IdentityRefusedError):
            _agentdojo(tmp_path, "full", snapshot_id="s1", **other)


def test_partial_stays_with_the_sampled_snapshot_when_another_is_imported_whole(tmp_path):
    """NF-36: each snapshot records its own selection, and the corpus stays partial while any snapshot is; package's
    working check refuses it (before, s2's full import cleared partial and dropped s1's selection.sample)."""
    from agentprov.corpus.package import PackageRefusedError, _check_working

    support.agentdojo_tree(tmp_path / "in", count=4)
    _agentdojo(tmp_path, "c", snapshot_id="s1", sample=ImportSample(2, "first"))
    whole = _agentdojo(tmp_path, "c", snapshot_id="s2")
    manifest, snapshots = _manifest(tmp_path / "c.partial"), _snapshots(tmp_path / "c.partial")
    assert manifest["partial"] is True and whole.partial is True  # the report says what the corpus is
    assert snapshots["s1"]["selection"]["sample"]["mode"] == "first" and snapshots["s1"]["selection"]["sample"]["n"] == 2
    assert "selection" not in snapshots["s2"]
    with pytest.raises(PackageRefusedError) as caught:
        _check_working(manifest, None, "0.1.0")  # type: ignore[arg-type]
    assert caught.value.code == "package.refused.partial"


def test_a_selection_free_resume_completes_a_sampled_snapshot(tmp_path):
    """N.1.7's documented completion path: re-running the same import without a selection resumes the snapshot and
    completes it; the snapshot's selection and the corpus's partial mark go (a later snapshot cannot clear them)."""
    support.agentdojo_tree(tmp_path / "in", count=4)
    _agentdojo(tmp_path, "c", snapshot_id="s1", sample=ImportSample(2, "first"))
    done = _agentdojo(tmp_path, "c", snapshot_id="s1")
    assert done.counters["skipped_resume"] == 2 and done.counters["mapped"] == 2
    manifest = _manifest(tmp_path / "c.partial")
    assert manifest["partial"] is False and "selection" not in _snapshots(tmp_path / "c.partial")["s1"]
    assert "sample" not in manifest["selection"]


def test_an_interrupted_completion_keeps_the_snapshot_partial(tmp_path, monkeypatch):
    """A selection-free resume that does not finish leaves the snapshot's recorded selection (partial is sticky)."""
    from agentprov.adapters.runner import importer

    support.agentdojo_tree(tmp_path / "in", count=4)
    _agentdojo(tmp_path, "c", snapshot_id="s1", sample=ImportSample(2, "first"))

    def interrupted(self: Any) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(importer._Pipeline, "run", interrupted)
    with pytest.raises(KeyboardInterrupt):
        _agentdojo(tmp_path, "c", snapshot_id="s1")
    assert _manifest(tmp_path / "c.partial")["partial"] is True
    assert _snapshots(tmp_path / "c.partial")["s1"]["selection"]["sample"]["n"] == 2


def test_a_remap_replays_each_snapshot_with_its_own_selection(tmp_path):
    """NF-36: a re-map (recompute, verify --level rederive) imports each snapshot with the selection that snapshot
    recorded, not with the last run's top-level one (which would complete s1 or refuse s2 on the re-map). A manifest
    written before the per-snapshot record keeps its top-level selection for every snapshot."""
    from types import SimpleNamespace

    from agentprov.corpus.derive import Derivation

    support.agentdojo_tree(tmp_path / "in", count=4)
    _agentdojo(tmp_path, "s", snapshot_id="s1", sample=ImportSample(2, "first"))
    _agentdojo(tmp_path, "s", snapshot_id="s2", limit=1)
    derivation = object.__new__(Derivation)  # only the recorded-argument helpers are exercised
    derivation.manifest = _manifest(tmp_path / "s.partial")
    derivation.plan = SimpleNamespace(until="aer", semantics=(), mode="dev", prov_conformance=True)
    one, two = derivation.import_arguments("s1"), derivation.import_arguments("s2")
    assert (one["limit"], one["sample"]["mode"], one["sample"]["n"]) == (None, "first", 2)
    assert two["limit"] == 1 and "sample" not in two
    assert derivation.recorded_selection("s1") == derivation.recorded_selection("s2") == {
        "include_paths": [], "select": {}, "variants": None}
    legacy = json.loads(json.dumps(derivation.manifest))
    for snapshot in legacy["sources"][0]["snapshots"]:
        del snapshot["selection"]
    derivation.manifest = legacy
    assert derivation.import_arguments("s1")["limit"] == derivation.import_arguments("s2")["limit"] == 1


def _recompute(tmp: Path, source: str, out: str, monkeypatch: Any, capsys: Any) -> None:
    from agentprov.cli.main import main

    monkeypatch.setenv("AGENTPROV_HOME", str(tmp / "home"))
    monkeypatch.delenv("AGENTPROV_PROGRESS", raising=False)
    capsys.readouterr()
    code = main(["recompute", "--corpus", str(tmp / source), "--out", str(tmp / out), "--in-process", "--progress", "off",
                 "--json"])
    assert code in (0, 1), capsys.readouterr().err


def test_limit_stays_resumable_and_a_complete_run_records_no_selection(tmp_path):
    """NF-36 as narrowed (N.1.7: --limit is an incremental cap): a limited snapshot records its selection, and the
    selection-free run that completes it drops it (ported from e435967e, CLI robustness)."""
    support.agentdojo_tree(tmp_path / "in", count=3)
    _agentdojo(tmp_path, "c", limit=1)
    assert _manifest(tmp_path / "c.partial")["sources"][0]["snapshots"][0]["selection"]["limit"] == 1
    full = _agentdojo(tmp_path, "c")  # completes the limited snapshot, as before
    assert full.counters["skipped_resume"] == 1 and full.counters["mapped"] == 2
    manifest = _manifest(tmp_path / "c.partial")
    assert manifest["partial"] is False and "selection" not in manifest["sources"][0]["snapshots"][0]


def test_a_later_limit_extends_the_snapshot_and_a_remap_replays_it(tmp_path, monkeypatch, capsys):
    """--limit counts the units newly mapped by this run (N.1.7), so --limit 1 then --limit 2 extends one snapshot by
    design (before: refused, the limit was part of the snapshot's identity). The snapshot records the cumulative cap,
    3, so a re-map (which starts from no executions) maps the same three, not two (and not the last run's one)."""
    support.agentdojo_tree(tmp_path / "in", count=5)
    _agentdojo(tmp_path, "s", limit=1)
    more = _agentdojo(tmp_path, "s", limit=2)
    assert more.counters["skipped_resume"] == 1 and more.counters["mapped"] == 2
    manifest = _manifest(tmp_path / "s.partial")
    assert manifest["partial"] is True and manifest["sources"][0]["snapshots"][0]["selection"]["limit"] == 3
    assert len(_keys(tmp_path / "s.partial")) == 3
    _recompute(tmp_path, "s", "r", monkeypatch, capsys)
    assert _keys(tmp_path / "r.partial") == _keys(tmp_path / "s.partial")
    assert _manifest(tmp_path / "r.partial")["sources"][0]["snapshots"][0]["selection"]["limit"] == 3


def test_a_limit_run_that_exhausts_the_snapshot_completes_it(tmp_path):
    """A limited run that runs to the end and maps fewer than its limit found nothing left: the limit is dropped and a
    snapshot with no filter or sample is complete (partial false), so package does not refuse it as partial."""
    from agentprov.corpus.package import _check_working

    support.agentdojo_tree(tmp_path / "in", count=3)
    _agentdojo(tmp_path, "c", limit=2)
    last = _agentdojo(tmp_path, "c", limit=5)
    assert last.counters["mapped"] == 1 and last.partial is False
    manifest = _manifest(tmp_path / "c.partial")
    assert manifest["partial"] is False and "selection" not in manifest["sources"][0]["snapshots"][0]
    try:
        _check_working(manifest, None, "0.1.0")  # type: ignore[arg-type]
    except Exception as exc:  # a later precondition may refuse this test corpus; never as a partial import
        assert getattr(exc, "code", "") != "package.refused.partial", exc
    _agentdojo(tmp_path, "c", limit=1)  # a later limited run on the complete snapshot maps nothing and keeps it whole
    assert _manifest(tmp_path / "c.partial")["partial"] is False


def test_a_filtered_snapshot_extends_by_limit_but_refuses_another_filter(tmp_path):
    """The snapshot's selection (filters, sample) must match; --limit is not part of it. A different filter is refused
    before anything is written; the same filter with another limit extends the snapshot and keeps the filter."""
    from agentprov.adapters.runner.importer import IdentityRefusedError, ImportFilters

    support.agentdojo_tree(tmp_path / "in", count=4)
    every = ImportFilters(include_paths=("**",))
    _agentdojo(tmp_path, "c", filters=every, limit=1)
    before = _tree_digests(tmp_path / "c.partial")
    for other in ({"filters": ImportFilters(include_paths=("**/*.json",)), "limit": 1}, {"limit": 1}):
        with pytest.raises(IdentityRefusedError) as caught:
            _agentdojo(tmp_path, "c", **other)
        assert caught.value.exit_code == 4
        assert _tree_digests(tmp_path / "c.partial") == before
    more = _agentdojo(tmp_path, "c", filters=every, limit=2)
    assert more.counters["mapped"] == 2
    selection = _manifest(tmp_path / "c.partial")["sources"][0]["snapshots"][0]["selection"]
    assert selection["limit"] == 3 and selection["filters"]["include_paths"] == ["**"]
    _agentdojo(tmp_path, "c", filters=every)  # the filter alone runs to the end: the cap goes, the filter stays
    manifest = _manifest(tmp_path / "c.partial")
    assert manifest["partial"] is True and manifest["sources"][0]["snapshots"][0]["selection"]["limit"] is None


def _interrupt_after_finishing(monkeypatch: Any, batches: int) -> None:
    """Interrupt the import once ``batches`` batches were finished (indexed); later batches were mapped, not indexed."""
    from agentprov.adapters.runner import importer

    finish, calls = importer._Pipeline.finish, {"n": 0}

    def interrupted(self: Any, *args: Any, **kwargs: Any) -> None:
        finish(self, *args, **kwargs)
        calls["n"] += 1
        if calls["n"] >= batches:
            raise KeyboardInterrupt

    monkeypatch.setattr(importer._Pipeline, "finish", interrupted)


@pytest.mark.parametrize("limit", [4, None], ids=["limit", "completion"])
def test_an_interrupted_run_records_the_cap_of_the_units_the_snapshot_holds(tmp_path, monkeypatch, capsys, limit):
    """NF-36 review: an interrupted run adds to the cap only the units it indexed. Its mapping runs a batch ahead of the
    index (the next batch is mapped before the previous one is finished), and a unit mapped but never indexed is mapped
    again by the resume, so counting it (before: ``written``) over-counted the cap for good and a re-map mapped more
    units than the snapshot holds. An interrupted completion of a snapshot that records only a cap (no filter or
    sample) extends the cap the same way (before: the recorded cap stayed, and a re-map dropped what it had mapped).

    D-610 review: an interrupt can leave a mapped, stored, never-indexed batch that no cap describes, so the snapshot is
    also marked incomplete and ``recompute`` refuses it until a run to the end (the cap stays what the snapshot holds)."""
    from agentprov.corpus.derive import DeriveRefusedError, resolve_plan
    from agentprov.corpus.reader import CorpusReader

    support.agentdojo_tree(tmp_path / "in", count=6)
    _agentdojo(tmp_path, "c", limit=1, batch_size=1)
    _interrupt_after_finishing(monkeypatch, 3)  # the resumed unit makes an empty first batch
    with pytest.raises(KeyboardInterrupt):
        _agentdojo(tmp_path, "c", limit=limit, batch_size=1)
    monkeypatch.undo()
    held = _keys(tmp_path / "c.partial")
    snapshot = _manifest(tmp_path / "c.partial")["sources"][0]["snapshots"][0]
    assert len(held) == 3 and _manifest(tmp_path / "c.partial")["partial"] is True
    assert snapshot["selection"]["limit"] == 3 and snapshot["incomplete"] == {"reason": "interrupted"}
    with pytest.raises(DeriveRefusedError, match="incomplete"):
        resolve_plan(CorpusReader(tmp_path / "c.partial", state="working"), "recompute")


def test_a_limit_given_to_a_raw_only_run_is_not_counted_as_held_units(tmp_path, monkeypatch, capsys):
    """NF-36 review: ``--until raw --limit 3`` maps nothing and records 3 (what a ``derive`` of that corpus maps). A
    later mapping resume with ``--limit 1`` holds one unit, and the cap must say 1 (before: 3 + 1 = 4, and a re-map
    mapped four)."""
    support.agentdojo_tree(tmp_path / "in", count=6)
    _agentdojo(tmp_path, "c", limit=3, until="raw")
    assert _manifest(tmp_path / "c.partial")["sources"][0]["snapshots"][0]["selection"]["limit"] == 3
    _agentdojo(tmp_path, "c", limit=1)
    held = _keys(tmp_path / "c.partial")
    assert len(held) == 1
    assert _manifest(tmp_path / "c.partial")["sources"][0]["snapshots"][0]["selection"]["limit"] == 1
    _recompute(tmp_path, "c", "r", monkeypatch, capsys)
    assert _keys(tmp_path / "r.partial") == held


def test_a_sealed_snapshot_selection_is_not_an_import_selection(tmp_path):
    """NF-36 review: a sealed manifest's snapshot ``selection`` is the spec's ``{include, exclude}`` (H.2), and a
    ``derive`` from a sealed corpus copies it into the working manifest. It is not a selection the snapshot was imported
    with: the snapshot is complete, so adding another snapshot whole leaves the corpus not partial and package's
    working check does not refuse it as a partial import."""
    from agentprov.corpus.package import _check_working
    from agentprov.corpus.selection import snapshot_selections

    support.agentdojo_tree(tmp_path / "in", count=2)
    _agentdojo(tmp_path, "c", snapshot_id="s1")
    path = tmp_path / "c.partial" / "corpus.json"
    manifest = json.loads(path.read_text())
    manifest["sources"][0]["snapshots"][0]["selection"] = {  # as a derive from the sealed corpus leaves it
        "include": ["runs/**/*.json"], "exclude": [{"glob": "**/.DS_Store", "code": "select.not_execution_artefact",
                                                     "owner": None}]}
    path.write_text(json.dumps(manifest))
    assert snapshot_selections(manifest) == {}
    _agentdojo(tmp_path, "c", snapshot_id="s2")
    assert _manifest(tmp_path / "c.partial")["partial"] is False
    try:
        _check_working(_manifest(tmp_path / "c.partial"), None, "0.1.0")  # type: ignore[arg-type]
    except Exception as exc:  # a later precondition may refuse this hand-built corpus; never as a partial import
        assert getattr(exc, "code", "") != "package.refused.partial", exc


# ------------------------------------------------------------------------------------------------ containers
def _survey(tmp: Path, out: str, **kwargs: Any) -> Any:
    with CorpusWriter(tmp / out) as corpus:
        return import_source("agent-security-tools-survey", LocalTree(tmp / "in"), corpus=corpus, part="agentharm",
                             until="aer", in_process=True,
                             pin_check=support.vouch(tmp / "in", repo=support.SURVEY, commit=support.SURVEY_COMMIT),
                             **kwargs)


def test_a_container_sample_maps_only_the_chosen_members_whatever_the_batch_size(tmp_path):
    support.inspect_tree(tmp_path / "in")
    full = _survey(tmp_path, "f")
    one = _survey(tmp_path, "a", sample=ImportSample(2, "random", "x"), batch_size=1)
    four = _survey(tmp_path, "b", sample=ImportSample(2, "random", "x"), batch_size=4)
    assert one.counters["mapped"] == four.counters["mapped"] == 2
    assert one.counters["sampled_out"] == full.counters["mapped"] - 2
    assert _keys(tmp_path / "a.partial") == _keys(tmp_path / "b.partial")
    assert set(_keys(tmp_path / "a.partial")) <= set(_keys(tmp_path / "f.partial"))  # the same AERs as a full import
    record = json.loads((tmp_path / "a.partial" / "corpus.json").read_text())["selection"]["sample"]
    assert record["candidates"] == full.counters["mapped"] and record["selected"] == 2


# ------------------------------------------------------------------------------------------------ multi-execution
def _deposit(base: Path, members: dict[str, bytes]) -> tuple[Path, dict[str, Any]]:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for label, data in members.items():
            zf.writestr(label, data)
    path = base / "deposit.zip"
    path.write_bytes(buf.getvalue())
    data = path.read_bytes()
    pin = {"role": "head", "kind": "zenodo", "doi": "10.5281/zenodo.1", "record": 1, "version": "v1",
           "file": path.name, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    return path, pin


def _credleak(path: Path, pin: dict[str, Any], corpus: Path, **kwargs: Any) -> Any:
    from agentprov.adapters.runner.importer import ArchiveTree

    tree = ArchiveTree(path, pin=pin, sha256=pin["sha256"], size=pin["bytes"])
    with CorpusWriter(corpus) as writer:
        return import_source("credleak-p15b", tree, corpus=writer, profile_id="credleak-p15b", part="head", pin=pin,
                             workers=1, snapshot_id="head", until="aer", **kwargs)


CELLS = {
    "p15b-run-data/01-injection-map/chan-a/model-x/run-1.json": credleak.synthetic_cell(runs=3, scenario="T1.1", technique="T1"),
    "p15b-run-data/03-egress-axis/chan-b/model-y/run-2.json": credleak.synthetic_cell(runs=3, scenario="T1.2", technique="T1"),
}


def test_a_multi_execution_sample_seals_only_the_chosen_items_whatever_the_batch_size(tmp_path):
    path, pin = _deposit(tmp_path, CELLS)
    full = _credleak(path, pin, tmp_path / "f")
    assert full.counters["mapped"] == 6
    one = _credleak(path, pin, tmp_path / "a", sample=ImportSample(3, "random", "r"), batch_size=1)
    two = _credleak(path, pin, tmp_path / "b", sample=ImportSample(3, "random", "r"), batch_size=2)
    assert one.counters["mapped"] == two.counters["mapped"] == 3 and one.counters["sampled_out"] == 3
    assert _keys(tmp_path / "a.partial") == _keys(tmp_path / "b.partial")
    assert set(_keys(tmp_path / "a.partial")) <= set(_keys(tmp_path / "f.partial"))


def test_a_remap_of_a_sampled_corpus_replays_its_sample(tmp_path, monkeypatch, capsys):
    """A recompute that re-maps (expand, aer) re-imports with the recorded selection.sample, so NEW holds the same
    executions instead of the whole source."""
    from agentprov.cli.main import main

    monkeypatch.setenv("AGENTPROV_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("AGENTPROV_PROGRESS", raising=False)
    support.agentdojo_tree(tmp_path / "in", count=4)
    _agentdojo(tmp_path, "s", sample=ImportSample(2, "random", "z"))
    capsys.readouterr()
    code = main(["recompute", "--corpus", str(tmp_path / "s"), "--out", str(tmp_path / "r"), "--in-process",
                 "--progress", "off", "--json"])
    out, err = capsys.readouterr()
    assert code in (0, 1), err
    assert _keys(tmp_path / "r.partial") == _keys(tmp_path / "s.partial")
    assert json.loads((tmp_path / "r.partial" / "corpus.json").read_text())["selection"]["sample"]["seed"] == "z"


def test_a_resumed_multi_execution_sample_keeps_a_file_sealed_whole_among_its_candidates(tmp_path):
    """NF-34 (regen item 128): a file sealed whole (one degenerate AER, the ``label#`` key) is skipped by the resume
    before pass 1 maps it; it stays a candidate under that key, so the resume draws the same set and adds nothing."""
    cells = {**CELLS, "p15b-run-data/01-injection-map/aaa/model-z/bad.json": b'{"not": json'}
    path, pin = _deposit(tmp_path, cells)
    first = _credleak(path, pin, tmp_path / "a", sample=ImportSample(2, "first"))
    keys = _keys(tmp_path / "a.partial")
    record = json.loads((tmp_path / "a.partial" / "corpus.json").read_text())["selection"]["sample"]
    assert first.counters["degenerate"] == 1 and len(keys) == 2 and record["candidates"] == 7
    again = _credleak(path, pin, tmp_path / "a", sample=ImportSample(2, "first"))
    assert again.counters["mapped"] == 0 and again.counters["skipped_resume"] == 2
    assert _keys(tmp_path / "a.partial") == keys  # not the union of two samples
    assert json.loads((tmp_path / "a.partial" / "corpus.json").read_text())["selection"]["sample"] == record


def test_a_later_limit_on_a_multi_execution_archive_is_replayed_by_a_remap(tmp_path, monkeypatch, capsys):
    """NF-36 as narrowed: --limit counts items here (N.1.7), and two --limit 2 runs of one archive snapshot hold four;
    the snapshot records the cumulative cap, so the re-map of the stored archive maps the same four items."""
    path, pin = _deposit(tmp_path, CELLS)
    _credleak(path, pin, tmp_path / "s", limit=2)
    _credleak(path, pin, tmp_path / "s", limit=2)
    assert len(_keys(tmp_path / "s.partial")) == 4
    assert _manifest(tmp_path / "s.partial")["sources"][0]["snapshots"][0]["selection"]["limit"] == 4
    _recompute(tmp_path, "s", "r", monkeypatch, capsys)
    assert _keys(tmp_path / "r.partial") == _keys(tmp_path / "s.partial")
