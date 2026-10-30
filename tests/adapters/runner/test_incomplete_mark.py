"""D-610 (regen item 150): an import run that stops before it ran to the end marks its snapshot ``incomplete`` and the
corpus ``partial``, unless the cumulative cap its snapshot records (NF-36) describes what it holds; a later run that runs
to the end with nothing left to map clears it; ``package``, ``derive`` and ``recompute`` refuse a marked corpus. Before,
a drained or interrupted fresh import recorded ``partial: false`` and ``package`` took it for a complete one."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any

import import_support as support
import pytest

from agentprov import drain
from agentprov.adapters.runner.importer import ImportFilters, LocalTree, import_source
from agentprov.corpus.derive import DeriveRefusedError, resolve_plan
from agentprov.corpus.package import PackageRefusedError, _check_working
from agentprov.corpus.reader import CorpusReader
from agentprov.corpus.writer import CorpusWriter
from agentprov.progress import ProgressEvent


class _OnUnit:
    """Calls ``action`` after the ``at``-th execution is done."""

    def __init__(self, at: int, action: Any) -> None:
        self.at, self.action, self.done = at, action, 0

    def emit(self, event: ProgressEvent) -> None:
        if event.kind == "unit_done":
            self.done += 1
            if self.done == self.at:
                self.action()


def _interrupt() -> None:
    raise KeyboardInterrupt


@pytest.fixture(autouse=True)
def _fresh_drain() -> Any:
    drain.reset()
    yield
    drain.reset()


def _run(tmp: Path, snapshot: str = "2024-06", **kwargs: Any) -> Any:
    with CorpusWriter(tmp / "c") as corpus:
        return import_source("agentdojo", LocalTree(tmp / "in"), corpus=corpus, part="2024-06", in_process=True,
                             batch_size=1, snapshot_id=snapshot, drain=True, pin_check=support.vouch(tmp / "in"), **kwargs)


def _drained(tmp: Path, **kwargs: Any) -> Any:
    report = _run(tmp, progress=_OnUnit(2, drain.request), **kwargs)
    drain.reset()
    return report


def _manifest(tmp: Path) -> dict[str, Any]:
    return json.loads((tmp / "c.partial" / "corpus.json").read_text())


def _rows(tmp: Path) -> int:
    return len((tmp / "c.partial" / "executions.jsonl").read_text().splitlines())


def _snapshots(tmp: Path) -> dict[str, dict[str, Any]]:
    return {s["snapshot_id"]: s for s in _manifest(tmp)["sources"][0]["snapshots"]}


def test_a_drained_import_is_recorded_incomplete(tmp_path):
    support.agentdojo_tree(tmp_path / "in", count=4)
    report = _drained(tmp_path)
    manifest = _manifest(tmp_path)
    assert _rows(tmp_path) < 4
    assert manifest["partial"] is True and manifest["selection"]["limit"] is None  # no --limit is invented
    snapshot = manifest["sources"][0]["snapshots"][0]
    assert snapshot["incomplete"] == {"reason": "drained"} and "selection" not in snapshot
    assert report.partial is True and report.incomplete == {"2024-06": "drained"}
    assert any("recorded incomplete (drained" in n for n in report.notices)


def test_an_interrupted_import_is_recorded_incomplete(tmp_path):
    support.agentdojo_tree(tmp_path / "in", count=4)
    with pytest.raises(KeyboardInterrupt):
        _run(tmp_path, progress=_OnUnit(2, _interrupt))
    manifest = _manifest(tmp_path)  # flushed on the way out (N.1.10(2))
    assert _rows(tmp_path) < 4 and manifest["partial"] is True
    assert manifest["sources"][0]["snapshots"][0]["incomplete"] == {"reason": "interrupted"}


def test_a_run_to_the_end_clears_the_mark_and_an_ordinary_import_carries_none(tmp_path):
    support.agentdojo_tree(tmp_path / "in", count=4)
    _drained(tmp_path)
    report = _run(tmp_path)  # the same command again
    manifest = _manifest(tmp_path)
    assert _rows(tmp_path) == 4 and manifest["partial"] is False
    assert "incomplete" not in manifest["sources"][0]["snapshots"][0] and report.incomplete == {}
    assert any("cleared the incomplete mark" in n for n in report.notices)
    _run(tmp_path)  # a resume of a whole snapshot keeps it whole
    assert "incomplete" not in _snapshots(tmp_path)["2024-06"]


def test_only_a_run_that_leaves_nothing_to_map_clears_it(tmp_path):
    support.agentdojo_tree(tmp_path / "in", count=4)
    _drained(tmp_path)
    _run(tmp_path, limit=1)  # stopped at its cap with units left: the mark stays
    assert _snapshots(tmp_path)["2024-06"]["incomplete"] == {"reason": "drained"}
    _run(tmp_path, until="raw")  # maps nothing
    assert _snapshots(tmp_path)["2024-06"]["incomplete"] == {"reason": "drained"}
    _run(tmp_path, limit=50)  # found fewer units than its limit: nothing left
    assert "incomplete" not in _snapshots(tmp_path)["2024-06"] and _rows(tmp_path) == 4


def test_another_snapshot_never_clears_a_mark(tmp_path):
    support.agentdojo_tree(tmp_path / "in", count=4)
    report = _run(tmp_path, snapshot="s1", progress=_OnUnit(2, drain.request))
    drain.reset()
    assert report.incomplete == {"s1": "drained"}
    report = _run(tmp_path, snapshot="s2")
    snapshots = _snapshots(tmp_path)
    assert snapshots["s1"]["incomplete"] == {"reason": "drained"} and "incomplete" not in snapshots["s2"]
    assert _manifest(tmp_path)["partial"] is True and report.incomplete == {"s1": "drained"}


def test_a_stopped_limit_run_is_described_by_its_cap_not_marked(tmp_path):
    """NF-36's cumulative cap records what a stopped --limit run holds (a re-map maps the same units): no mark."""
    support.agentdojo_tree(tmp_path / "in", count=6)
    _drained(tmp_path, limit=4)
    snapshot = _snapshots(tmp_path)["2024-06"]
    assert "incomplete" not in snapshot and snapshot["selection"]["limit"] == _rows(tmp_path) < 4
    assert _manifest(tmp_path)["partial"] is True  # partial through its selection; package refuses it as before
    resolve_plan(CorpusReader(tmp_path / "c.partial", state="working"), "recompute")  # re-mappable


def _limited_tree(root: Path, second: bytes | None = None, *, degenerate: bool = False) -> None:
    """The NF pass's D-610 probes: four logs; the second in path order broken (``second``) or made degenerate."""
    paths = sorted(support.agentdojo_tree(root, count=4))
    if second is not None:
        (root / paths[1]).write_bytes(second)
    if degenerate:
        log = json.loads((root / paths[1]).read_bytes())
        (root / paths[1]).write_text(json.dumps({**log, "messages": "x"}))


def _limited(tmp: Path, action: Any) -> Any:
    with CorpusWriter(tmp / "c") as corpus:
        return import_source("agentdojo", LocalTree(tmp / "in"), corpus=corpus, part="2024-06", in_process=True,
                             batch_size=1, limit=10, drain=True, pin_check=support.vouch(tmp / "in"),
                             progress=_OnUnit(1, action))


def _recompute(tmp: Path, monkeypatch: Any, capsys: Any) -> int:
    from agentprov.cli.main import main

    monkeypatch.setenv("AGENTPROV_HOME", str(tmp / "home"))
    monkeypatch.delenv("AGENTPROV_PROGRESS", raising=False)
    capsys.readouterr()
    return main(["recompute", "--corpus", str(tmp / "c"), "--out", str(tmp / "r"), "--in-process", "--progress", "off",
                 "--json"])


def test_a_clean_drain_under_a_limit_recomputes_to_the_same_executions(tmp_path, monkeypatch, capsys):
    _limited_tree(tmp_path / "in")
    _limited(tmp_path, drain.request)
    drain.reset()
    snapshot = _snapshots(tmp_path)["2024-06"]
    assert "incomplete" not in snapshot and snapshot["selection"]["limit"] == _rows(tmp_path) == 2
    assert _recompute(tmp_path, monkeypatch, capsys) == 0, capsys.readouterr().err
    held = sorted(json.loads(x)["source_key"] for x in (tmp_path / "c.partial" / "executions.jsonl").read_text().splitlines())
    again = sorted(json.loads(x)["source_key"] for x in (tmp_path / "r.partial" / "executions.jsonl").read_text().splitlines())
    assert again == held


@pytest.mark.parametrize("case", ["degenerate", "rejected", "interrupted"])
def test_a_stop_after_the_last_counted_unit_is_marked(tmp_path, monkeypatch, capsys, case):
    """The NF pass's counter-cases to the first narrowing: the cap counts non-degenerate indexed units, so a re-map under
    it stops right after the last counted one and never reproduces a degenerate unit, a rejected candidate (register and
    origin rows, no unit) or an interrupted run's mapped, stored, never-indexed batch after it."""
    _limited_tree(tmp_path / "in", b"{ not json" if case == "rejected" else None, degenerate=case == "degenerate")
    if case == "interrupted":
        with pytest.raises(KeyboardInterrupt):
            _limited(tmp_path, _interrupt)
    else:
        _limited(tmp_path, drain.request)
        drain.reset()
    reason = "interrupted" if case == "interrupted" else "drained"
    assert _snapshots(tmp_path)["2024-06"]["incomplete"] == {"reason": reason}
    assert _recompute(tmp_path, monkeypatch, capsys) == 4  # refused (before: exit 1, unexplained origins or rows)
    assert "corpus.derive.incomplete" in capsys.readouterr().err


def test_a_stop_no_cap_describes_is_marked(tmp_path):
    support.agentdojo_tree(tmp_path / "in", count=4)
    _drained(tmp_path, filters=ImportFilters(include_paths=("**",)))  # a selection with no cap: a re-map maps it all
    snapshot = _snapshots(tmp_path)["2024-06"]
    assert snapshot["incomplete"] == {"reason": "drained"} and snapshot["selection"]["limit"] is None
    _run(tmp_path, filters=ImportFilters(include_paths=("**",)))  # the same selection run to the end clears it
    assert "incomplete" not in _snapshots(tmp_path)["2024-06"] and _rows(tmp_path) == 4


def test_a_cap_never_hides_an_earlier_mark(tmp_path):
    support.agentdojo_tree(tmp_path / "in", count=6)
    _drained(tmp_path)  # uncapped: marked
    report = _drained(tmp_path, limit=3)  # a stopped --limit run cannot cap what the first run held
    assert any("drained" in n for n in report.notices)
    assert _snapshots(tmp_path)["2024-06"]["incomplete"] == {"reason": "drained"}


def test_package_derive_and_recompute_refuse_an_incomplete_corpus(tmp_path):
    support.agentdojo_tree(tmp_path / "in", count=4)
    _drained(tmp_path)
    manifest = _manifest(tmp_path)
    with pytest.raises(PackageRefusedError) as refused:
        _check_working(manifest, None, "0.1.0")  # type: ignore[arg-type]  # refused before the spec is read
    assert refused.value.code == "package.refused.incomplete"
    manifest["partial"] = False  # the snapshot's mark refuses it whatever the corpus-level flag says
    with pytest.raises(PackageRefusedError, match="incomplete"):
        _check_working(manifest, None, "0.1.0")  # type: ignore[arg-type]
    reader = CorpusReader(tmp_path / "c.partial", state="working")
    for command in ("derive", "recompute"):
        with pytest.raises(DeriveRefusedError) as derive_refused:
            resolve_plan(reader, command)
        assert derive_refused.value.code == "corpus.derive.incomplete" and derive_refused.value.exit_code == 4


def test_a_killed_import_writes_no_manifest(tmp_path):
    """SIGKILL (and the second signal's ``os._exit``) runs no ``finally``: nothing is recorded, so nothing can be sealed."""
    support.agentdojo_tree(tmp_path / "in", count=4)
    code = textwrap.dedent(f"""
        import os, signal, sys
        sys.path.insert(0, {str(Path(__file__).resolve().parents[1])!r})
        from pathlib import Path
        import import_support as support
        from agentprov.adapters.runner.importer import ImportFilters, LocalTree, import_source
        from agentprov.corpus.writer import CorpusWriter

        class Kill:
            done = 0
            def emit(self, event):
                if event.kind == "unit_done":
                    Kill.done += 1
                    if Kill.done == 2:
                        os.kill(os.getpid(), signal.SIGKILL)

        tmp = Path({str(tmp_path)!r})
        with CorpusWriter(tmp / "c") as corpus:
            import_source("agentdojo", LocalTree(tmp / "in"), corpus=corpus, part="2024-06", in_process=True,
                          batch_size=1, pin_check=support.vouch(tmp / "in"), progress=Kill())
    """)
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, check=False, env={**os.environ})
    assert done.returncode == -signal.SIGKILL
    assert not (tmp_path / "c.partial" / "corpus.json").exists()
    with pytest.raises(PackageRefusedError) as refused:
        _check_working(None, None, "0.1.0")  # type: ignore[arg-type]
    assert refused.value.code == "package.refused.manifest"


def test_a_drain_after_a_degenerate_item_inside_a_multi_execution_file_is_marked(tmp_path, monkeypatch):
    """Second review (NF pass, probe 5): the cap counts units and a re-map cuts per unit inside a multi-execution file,
    so a drain whose last file ends in a degenerate item after a counted one held what no cap describes (an unstopped
    ``--limit 2`` recorded the same cap and held one unit fewer). Before, any counted unit in the last file passed."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import test_multi_execution_lines as ml

    import agentprov.adapters.runner as runner
    import agentprov.adapters.runner.importer as importer
    from agentprov.adapters.credleak.mapper import CredleakMapper
    from agentprov.adapters.registry import MAPPERS, READERS
    from agentprov.errors import MalformedArtefact

    class BadLineMapper(ml.LineMapper):
        def map(self, unit: Any, ctx: Any) -> Any:
            if "BAD" in json.dumps(unit.primary.value):
                raise MalformedArtefact("a bad line")
            yield from super().map(unit, ctx)

    original = runner.resolve_factory
    fakes = {READERS[ml.DIALECT_ID]: ml.LineReader, MAPPERS[CredleakMapper.mapper_id]: BadLineMapper}
    monkeypatch.setattr(runner, "resolve_factory", lambda p: fakes.get(p) or original(p))
    monkeypatch.setattr(importer, "resolve_factory", lambda p: fakes.get(p) or original(p))
    folder = "p15b-run-data/01-injection-map/T1-file-document/test-model/"
    members = {folder + "a1.json": ml._jsonl(1, "X"), folder + "a2.json": ml._jsonl(1) + ml._jsonl(1, scenario="BAD"),
               folder + "a3.json": ml._jsonl(1, "Y"), folder + "a4.json": ml._jsonl(1, "Z")}
    path, pin = ml._deposit(tmp_path, members)
    ml._run(path, pin, tmp_path / "c", limit=10, batch_size=1, drain=True, progress=_OnUnit(1, drain.request))
    drain.reset()
    snapshot = _snapshots(tmp_path)["head"]
    assert snapshot["incomplete"] == {"reason": "drained"} and snapshot["selection"]["limit"] == 2
    reader = CorpusReader(tmp_path / "c.partial", state="working")
    with pytest.raises(DeriveRefusedError, match="incomplete"):
        resolve_plan(reader, "recompute")
    ml._run(path, pin, tmp_path / "u", limit=2, batch_size=1)  # an unstopped --limit 2 ends in a counted item: no mark
    unstopped = json.loads((tmp_path / "u.partial" / "corpus.json").read_text())["sources"][0]["snapshots"][0]
    assert "incomplete" not in unstopped and unstopped["selection"]["limit"] == 2


@pytest.mark.parametrize(("candidate", "unit", "degenerate", "clean"), [
    ("logs/a.json", "logs/a.json", False, True),  # a whole or multi-execution file
    ("logs/a.json", "logs/a.json", True, False),  # its last unit is degenerate
    ("logs/a.json", "logs/b.json", False, False),  # the last candidate sealed nothing (an earlier one did)
    ("d.zip!/runs.tar", "d.zip!/runs.tar!/m1.json", False, True),  # a container inside an archive input
    ("outer.zip!/inner.zip", "outer.zip!/inner.zip!/logs/m2.json", False, True),  # a D-380 chain label
    ("outer.zip!/inner.zip", "outer.zip!/inner.zip!/logs/m2.json", True, False),
    ("d.zip!/runs.tar", "d.zip!/other.tar!/m1.json", False, False),  # another container's member
    ("d.zip!/runs.tar", "d.zip!/runs.tar2!/m1.json", False, False),  # a label prefix, not a member
])
def test_the_clean_tail_compares_a_nested_archive_label_by_prefix(candidate, unit, degenerate, clean):
    """Third review (NF pass): ``split("!/", 1)[0]`` cut a container's own label when it sits inside an archive input
    (``d.zip!/runs.tar!/m1.json`` gave ``d.zip``), so its clean tail was never seen; the member is matched by prefix."""
    from types import SimpleNamespace

    from agentprov.adapters.runner.importer import _Pipeline

    units = [SimpleNamespace(label="logs/0.json", degenerate=False), SimpleNamespace(label=unit, degenerate=degenerate)]
    batch = [SimpleNamespace(label="logs/0.json"), SimpleNamespace(label=candidate)]
    pipeline = SimpleNamespace(_rejected_since_unit=False)
    assert _Pipeline._ends_counted(pipeline, batch, units) is clean  # type: ignore[arg-type]
    assert _Pipeline._ends_counted(pipeline, batch, []) is False  # type: ignore[arg-type]
