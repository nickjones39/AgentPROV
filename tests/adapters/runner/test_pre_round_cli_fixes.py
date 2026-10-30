"""Pre-round integration review (docs/reports/pre-round-review/report.md, cdd26e34), the runner findings in the D-525,
D-529 and D-610 area: PR-6 (a re-map never drains), PR-9 (a sampled-out multi-execution file sealed whole elsewhere is
never collapsed into the sampled snapshot), PR-11 #3 (pass 1 lists a file whose rows are refused as one unit, as pass 2
seals it) and PR-11 #6 (a write-gate rejection after the last counted item breaks the D-610 clean tail)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import import_support as support
import pytest

from agentprov import drain
from agentprov.adapters.runner.importer import ImportSample, LocalTree, import_source
from agentprov.corpus.writer import CorpusWriter
from agentprov.progress import ProgressEvent

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_sample as ts  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_drain() -> Any:
    drain.reset()
    yield
    drain.reset()


class _OnUnit:
    def __init__(self, at: int, action: Any) -> None:
        self.at, self.action, self.done = at, action, 0

    def emit(self, event: ProgressEvent) -> None:
        if event.kind == "unit_done":
            self.done += 1
            if self.done == self.at:
                self.action()


def _rows(partial: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in (partial / "executions.jsonl").read_text().splitlines()]


# ------------------------------------------------------------------------------------------------ PR-6
def _agentdojo(tmp: Path, **kwargs: Any) -> Any:
    with CorpusWriter(tmp / "c") as corpus:
        return import_source("agentdojo", LocalTree(tmp / "in"), corpus=corpus, part="2024-06", in_process=True,
                             batch_size=1, pin_check=support.vouch(tmp / "in"), **kwargs)


def test_only_an_import_that_opts_in_honours_a_drain(tmp_path):
    support.agentdojo_tree(tmp_path / "in", count=4)
    report = _agentdojo(tmp_path, progress=_OnUnit(1, drain.request))  # a re-map caller: no opt-in
    assert not drain.is_supported() and len(_rows(tmp_path / "c.partial")) == 4
    assert not any("drained" in n for n in report.notices)
    snapshot = json.loads((tmp_path / "c.partial" / "corpus.json").read_text())["sources"][0]["snapshots"][0]
    assert "incomplete" not in snapshot


def test_a_drain_sent_to_recompute_does_not_truncate_its_re_map(tmp_path, monkeypatch, capsys):
    """The review's probe: a control-file drain accepted mid-recompute gave a truncated NEW, marked incomplete and
    reported as failures (exit 1). The re-map now never opts in, so the drain degrades to a stop (N.1.10(5))."""
    from agentprov.cli.main import main

    support.agentdojo_tree(tmp_path / "in", count=4)
    _agentdojo(tmp_path)
    monkeypatch.setattr(drain, "draining", lambda: True)  # as if the watcher accepted a drain at once
    monkeypatch.setenv("AGENTPROV_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("AGENTPROV_PROGRESS", raising=False)
    capsys.readouterr()
    code = main(["recompute", "--corpus", str(tmp_path / "c"), "--out", str(tmp_path / "r"), "--in-process",
                 "--progress", "off", "--json", "--stages", "aer"])
    assert code == 0, capsys.readouterr().err
    assert sorted(r["source_key"] for r in _rows(tmp_path / "r.partial")) == sorted(
        r["source_key"] for r in _rows(tmp_path / "c.partial"))


# ------------------------------------------------------------------------------------------------ PR-9
BAD = "p15b-run-data/03-egress-axis/zzz/model-z/bad.json"


def _two_snapshots(tmp: Path, n: int) -> tuple[Any, list[dict[str, Any]], list[dict[str, Any]]]:
    path, pin = ts._deposit(tmp, {**ts.CELLS, BAD: b'{"not": json'})  # bad.json is sealed whole (degenerate)
    _credleak(path, pin, tmp / "c")  # snapshot head, whole
    report = _credleak(path, pin, tmp / "c", snapshot_id="s2", sample=ImportSample(n, "first"))
    register = [json.loads(x) for x in (tmp / "c.partial" / "register.jsonl").read_text().splitlines()]
    return report, _rows(tmp / "c.partial"), register


def _whole(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return next(r for r in rows if r["status"] == "failed")  # the one execution of bad.json


def test_a_sampled_out_file_sealed_whole_elsewhere_is_not_collapsed_into_the_sample(tmp_path):
    _report, rows, register = _two_snapshots(tmp_path, 2)  # the first two keys are the first file's items
    whole = _whole(rows)
    assert whole["snapshot_ids"] == ["head"]  # before: ["head", "s2"] with a dedup.collapsed row
    assert not any(e["code"] == "dedup.collapsed" and e["subject"].get("source_key") == whole["source_key"]
                   for e in register)


def test_a_drawn_file_sealed_whole_elsewhere_is_still_collapsed(tmp_path):
    report, rows, register = _two_snapshots(tmp_path, 7)  # every key: bad.json# is drawn
    whole = _whole(rows)
    assert whole["snapshot_ids"] == ["head", "s2"] and report.counters["duplicates"] == 7
    assert any(e["code"] == "dedup.collapsed" and e["subject"].get("source_key") == whole["source_key"]
               for e in register)


def _credleak(path: Path, pin: dict[str, Any], corpus: Path, **kwargs: Any) -> Any:
    from agentprov.adapters.runner.importer import ArchiveTree

    tree = ArchiveTree(path, pin=pin, sha256=pin["sha256"], size=pin["bytes"])
    kwargs.setdefault("snapshot_id", "head")
    with CorpusWriter(corpus) as writer:
        return import_source("credleak-p15b", tree, corpus=writer, profile_id="credleak-p15b", part="head", pin=pin,
                             workers=1, until="aer", **kwargs)


def _mcphunt_snapshots(tmp: Path, n: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """PR-9 x PR-8 (MCPHunt-shaped, after 10i's PR-8 test): an LFS pointer whose pinned object is sealed whole in
    snapshot ``head`` (bytes no reader parses), and an ordinary document whose traces sort before the object's key."""
    import hashlib

    import test_mcphunt_lfs_overlay_d530 as lfs

    from agentprov.adapters.runner.importer import PinnedObject
    from agentprov.adapters.types import Origin

    root = tmp / "in"
    (root / "main").mkdir(parents=True)
    broken = b'{"not": json'
    sha = hashlib.sha256(broken).hexdigest()
    (root / lfs.LABEL).write_bytes(lfs.POINTER % (sha.encode(), len(broken)))
    (root / "main" / "A_plain.json").write_bytes((lfs.support.FIXTURES / "docs" / lfs.LABEL).read_bytes())
    (tmp / "object.json").write_bytes(broken)
    obj = PinnedObject(lfs.LABEL, Origin.hf(lfs.DATASET, lfs.support.REVISION, lfs.LABEL), str(tmp / "object.json"), sha,
                       len(broken))
    for snapshot, kwargs in (("head", {}), ("s2", {"sample": ImportSample(n, "first")})):
        with CorpusWriter(tmp / "c", limits=lfs.support.limits()) as writer:
            import_source("mcphunt", LocalTree(root), corpus=writer, profile_id="mcphunt", part="head",
                          snapshot_id=snapshot, pinned_objects=[obj], in_process=True, until="aer",
                          pin_check=support.vouch(root, repo=lfs.REPO_URL, commit=lfs.support.REVISION),
                          limits=lfs.support.limits(), **kwargs)
    register = [json.loads(x) for x in (tmp / "c.partial" / "register.jsonl").read_text().splitlines()]
    return _rows(tmp / "c.partial"), register


@pytest.mark.parametrize("drawn", [False, True], ids=["sampled-out", "drawn"])
def test_a_pinned_object_sealed_whole_elsewhere_is_collapsed_only_when_drawn(tmp_path, drawn):
    rows, register = _mcphunt_snapshots(tmp_path, 100 if drawn else 1)
    whole = [r for r in rows if r["status"] == "failed"]  # the pinned object's one execution
    assert len(whole) == 1
    assert whole[0]["snapshot_ids"] == (["head", "s2"] if drawn else ["head"])
    collapsed = [e for e in register if e["code"] == "dedup.collapsed"
                 and e["subject"].get("source_key") == whole[0]["source_key"]]
    assert len(collapsed) == (1 if drawn else 0)
    assert sum(1 for e in register if e["code"] == "select.not_execution_artefact") >= 1  # the pointer, always


# ------------------------------------------------------------------------------------------------ PR-11 #3
@pytest.mark.parametrize("seed", ["s0", "s1", "s2", "s3", "s4", "s5"])
def test_a_resumed_random_sample_draws_the_same_set_when_a_file_s_rows_are_refused(tmp_path, monkeypatch, seed):
    """D-321: a file whose rejected rows fail validation is sealed whole. Pass 1 listed its items (``label#<key>``), the
    resume its ``label#`` key (NF-34), so a random draw over the two key sets differed. It is now one unit in both."""
    import agentprov.adapters.runner as runner

    real = runner.rejected_rows

    def refused(data: bytes, origin: Any, **kwargs: Any) -> Any:
        rows = real(data, origin, **kwargs)
        return [*rows, {"code": "bogus.code", "detail": "x", "loc": {"p": "/runs/0"}}] if b"T1.1" in data else rows

    monkeypatch.setattr(runner, "rejected_rows", refused)
    path, pin = ts._deposit(tmp_path, ts.CELLS)
    sample = ImportSample(2, "random", seed)
    ts._credleak(path, pin, tmp_path / "a", sample=sample, in_process=True)
    first = (ts._keys(tmp_path / "a.partial"),
             json.loads((tmp_path / "a.partial" / "corpus.json").read_text())["selection"]["sample"])
    again = ts._credleak(path, pin, tmp_path / "a", sample=sample, in_process=True)
    assert again.counters["mapped"] == 0
    assert (ts._keys(tmp_path / "a.partial"),
            json.loads((tmp_path / "a.partial" / "corpus.json").read_text())["selection"]["sample"]) == first


# ------------------------------------------------------------------------------------------------ PR-11 #6
def test_a_write_gate_rejection_after_the_last_counted_item_breaks_the_clean_tail(tmp_path, monkeypatch):
    """The review's probe: the last mapped file ends in an item the AER write gate rejects (registered failed, no unit)
    after a counted one. The clean tail looked at sealed units only, so the drained ``--limit`` run went unmarked and a
    re-map under its cap stopped before the rejected item."""
    import test_multi_execution_lines as ml

    import agentprov.adapters.runner as runner
    import agentprov.adapters.runner.importer as importer
    from agentprov.adapters.credleak.mapper import CredleakMapper
    from agentprov.adapters.registry import MAPPERS, READERS
    from agentprov.aer.writer import AerWriteError

    original = runner.resolve_factory
    fakes = {READERS[ml.DIALECT_ID]: ml.LineReader, MAPPERS[CredleakMapper.mapper_id]: ml.LineMapper}
    monkeypatch.setattr(runner, "resolve_factory", lambda p: fakes.get(p) or original(p))
    monkeypatch.setattr(importer, "resolve_factory", lambda p: fakes.get(p) or original(p))
    real_seal = importer.seal_outcome

    def seal(outcome: Any, *args: Any, **kwargs: Any) -> Any:
        if "SEALFAIL" in repr(outcome):
            raise AerWriteError("the write gate rejects this record")
        return real_seal(outcome, *args, **kwargs)

    monkeypatch.setattr(importer, "seal_outcome", seal)
    folder = "p15b-run-data/01-injection-map/T1-file-document/test-model/"
    members = {folder + "a1.json": ml._jsonl(1, "X"), folder + "a2.json": ml._jsonl(1) + ml._jsonl(1, scenario="SEALFAIL"),
               folder + "a3.json": ml._jsonl(1, "Y"), folder + "a4.json": ml._jsonl(1, "Z")}
    path, pin = ml._deposit(tmp_path, members)
    ml._run(path, pin, tmp_path / "c", limit=10, batch_size=1, drain=True, progress=_OnUnit(1, drain.request))
    snapshot = json.loads((tmp_path / "c.partial" / "corpus.json").read_text())["sources"][0]["snapshots"][0]
    assert snapshot["incomplete"] == {"reason": "drained"} and snapshot["selection"]["limit"] == 2
