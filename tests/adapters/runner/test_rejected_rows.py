"""Rejected rows of multi-execution files (D-321; follow-up (ii) of R-10k-1; HL H.6.1 R1/R5, H.6.2).

A ``multi_execution`` reader may define ``rejected``: the rows its ``parse`` does not yield, each with a register code and
detail. The T1 map job emits them as ``{"register": …}`` frames; the parent validates every row before registering any
(allowed code, a key locator naming an element and no execution's, a detail the register accepts) and registers them in
canonical locator order with the subject ``{source_key}`` and disposition ``not_imported``. Each counts as a candidate
(the user's R5 ruling, option A), so a corpus with several snapshots cannot attribute it and fails loudly
(``corpus.manifest.unattributed``). The reader and mapper of ``test_multi_execution_lines.py`` are reused, with lines
that are not cells classified by a test ``rejected``; the registry's factory resolution is patched in process (dev mode).
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import test_multi_execution_lines as lines_support  # noqa: E402

from agentprov.adapters.types import ArtefactRef, Rejected  # noqa: E402
from agentprov.ingest.limits import IngestLimits  # noqa: E402

LABEL = lines_support.LABEL


class RowReader(lines_support.LineReader):
    """Lines that are cells are executions; ``{"probe": …}`` lines are not executions, ``{"partial": …}`` lines are out of
    scope. ``bad`` makes ``rejected`` misbehave in one way (the parent must refuse it)."""

    bad: str | None = None
    reverse = False

    def sniff(self, data: bytes, *, label: str, limits: IngestLimits) -> Any:
        from agentprov.adapters.types import SniffResult

        values = self._lines(data, limits)
        if any(isinstance(v, dict) and "runs" in v for v in values):
            return SniffResult(True, "credleak.cell", "v1", frozenset(), ("test.cells",))
        return SniffResult(False, reasons=("credleak.not_a_cell",))

    def parse(self, data: bytes, artefact: ArtefactRef, *, limits: IngestLimits) -> Iterator[Any]:
        from agentprov.adapters.types import LocatedItem, Locator

        for n, value in enumerate(self._lines(data, limits)):
            if isinstance(value, dict) and "runs" in value:
                yield LocatedItem(artefact=artefact, locator=Locator(a=artefact.id, line=n), dialect="credleak.cell",
                                  variant="v1", flags=frozenset(), value=value)

    def rejected(self, data: bytes, artefact: ArtefactRef, *, limits: IngestLimits) -> Iterator[Rejected]:
        from agentprov.adapters.types import Locator

        out = []
        for n, value in enumerate(self._lines(data, limits)):
            if isinstance(value, dict) and "probe" in value:
                out.append(Rejected(Locator(line=n), "select.not_execution_artefact", "test.probe_no_agent"))
            elif isinstance(value, dict) and "partial" in value:
                out.append(Rejected(Locator(line=n), "select.out_of_scope", "test.partial_trajectory"))
        if self.bad == "code":
            out[0] = Rejected(out[0].locator, "select.owned_elsewhere", "test.wrong_code")
        elif self.bad == "detail":
            out[0] = Rejected(out[0].locator, out[0].code, "test.\u0007bell")
        elif self.bad == "long":
            out[0] = Rejected(out[0].locator, out[0].code, "x" * 201)
        elif self.bad == "root":
            out[0] = Rejected(Locator(p=""), out[0].code, out[0].detail)
        elif self.bad == "taken":
            out[0] = Rejected(Locator(line=0), out[0].code, out[0].detail)  # line 0 is an execution
        elif self.bad == "twice":
            out.append(out[0])
        yield from (reversed(out) if self.reverse else out)


@pytest.fixture
def rows(monkeypatch: pytest.MonkeyPatch) -> type[RowReader]:
    import agentprov.adapters.runner as runner
    import agentprov.adapters.runner.importer as importer
    from agentprov.adapters.credleak.dialect import DIALECT_ID
    from agentprov.adapters.credleak.mapper import CredleakMapper
    from agentprov.adapters.registry import MAPPERS, READERS

    original = runner.resolve_factory
    reader = type("Reader", (RowReader,), {})  # a fresh class per test: ``bad``/``reverse`` are set on it
    fakes = {READERS[DIALECT_ID]: reader, MAPPERS[CredleakMapper.mapper_id]: lines_support.LineMapper}
    monkeypatch.setattr(runner, "resolve_factory", lambda path: fakes.get(path) or original(path))
    monkeypatch.setattr(importer, "resolve_factory", lambda path: fakes.get(path) or original(path))
    return reader


def _cell(n: int) -> dict[str, Any]:
    return json.loads(lines_support.support.synthetic_cell(scenario=f"T1.9.{n}", technique="T1"))


def _file(*kinds: str) -> bytes:
    """One JSONL line per kind: ``run`` (a one-run cell), ``probe`` or ``partial``."""
    values = [_cell(n) if kind == "run" else {kind: n} for n, kind in enumerate(kinds)]
    return b"".join(json.dumps(v, separators=(",", ":")).encode() + b"\n" for v in values)


def _register(corpus: Path) -> list[dict[str, Any]]:
    path = corpus.with_name(corpus.name + ".partial") / "register.jsonl"
    return [json.loads(x) for x in path.read_text().splitlines()]


def _rejected(corpus: Path) -> list[tuple[str, str]]:
    return [(e["subject"]["source_key"].split("#", 1)[1], e["code"]) for e in _register(corpus)
            if set(e["subject"]) == {"source_key"} and e["disposition"] == "not_imported"]


def _counts(corpus: Path, snapshot_id: str = "head") -> dict[str, Any]:
    """The H.2.3 snapshot counts as sealing and ``verify --level chain`` recompute them (H.6.1 R5): the working
    ``corpus.json`` keeps the importer's file count as ``candidates``."""
    from agentprov.corpus.manifest import snapshot_counts
    from agentprov.corpus.reader import CorpusReader

    reader = CorpusReader(corpus.with_name(corpus.name + ".partial"), state="working")
    snapshots = [str(s["snapshot_id"]) for s in (reader.manifest() or {})["sources"][0]["snapshots"]]
    return snapshot_counts(reader.index(), reader.register(), snapshot_id, [], all_snapshots=snapshots)


def test_rejected_rows_are_registered_by_source_key_and_count_as_candidates(rows, tmp_path):
    path, pin = lines_support._deposit(tmp_path, {LABEL: _file("run", "probe", "run", "partial")})
    report = lines_support._run(path, pin, tmp_path / "c")
    assert report.exit_code == 0, report.counters
    assert (report.counters["mapped"], report.counters["registered"]) == (2, 2)
    assert _rejected(tmp_path / "c") == [('{"line":1}', "select.not_execution_artefact"),
                                         ('{"line":3}', "select.out_of_scope")]
    entry = next(e for e in _register(tmp_path / "c") if e["code"] == "select.out_of_scope")
    assert (entry["stage"], entry["severity"], entry["detail"]) == ("select", "info", "test.partial_trajectory")
    counts = _counts(tmp_path / "c")
    assert (counts["candidates"], counts["executions"], counts["not_imported"]) == (4, 2, 2)


def test_a_file_without_an_execution_is_accounted_for_by_its_rows(rows, tmp_path):
    path, pin = lines_support._deposit(tmp_path, {LABEL: _file("probe", "probe", "partial")})
    report = lines_support._run(path, pin, tmp_path / "c")
    assert report.exit_code == 0 and report.counters["mapped"] == 0
    assert [loc for loc, _code in _rejected(tmp_path / "c")] == ['{"line":0}', '{"line":1}', '{"line":2}']
    assert not [e for e in _register(tmp_path / "c") if "path" in e["subject"]]  # no file-level entry beside the rows
    assert _counts(tmp_path / "c")["candidates"] == 3


def test_rows_are_registered_in_canonical_locator_order(rows, tmp_path):
    rows.reverse = True
    path, pin = lines_support._deposit(tmp_path, {LABEL: _file("probe", "run", "probe", "partial")})
    report = lines_support._run(path, pin, tmp_path / "c")
    assert [e["subject"]["source_key"].split("#", 1)[1] for e in report.register
            if set(e["subject"]) == {"source_key"}] == ['{"line":0}', '{"line":2}', '{"line":3}']


def test_a_resume_registers_no_row_twice(rows, tmp_path):
    path, pin = lines_support._deposit(tmp_path, {LABEL: _file("run", "probe", "partial")})
    lines_support._run(path, pin, tmp_path / "c")
    before = (tmp_path / "c.partial" / "register.jsonl").read_bytes()
    again = lines_support._run(path, pin, tmp_path / "c")
    assert (again.counters["mapped"], again.counters["registered"], again.counters["skipped_resume"]) == (0, 0, 3)
    assert (tmp_path / "c.partial" / "register.jsonl").read_bytes() == before


@pytest.mark.parametrize("bad", ["code", "detail", "long", "root", "taken", "twice"])
def test_an_invalid_row_makes_the_file_one_degenerate_aer_with_no_row(rows, tmp_path, bad):
    rows.bad = bad
    path, pin = lines_support._deposit(tmp_path, {LABEL: _file("run", "probe", "partial")})
    report = lines_support._run(path, pin, tmp_path / "c")
    assert (report.counters["mapped"], report.counters["degenerate"], report.counters["registered"]) == (1, 1, 0)
    assert lines_support._locs(tmp_path / "c") == ['{"p":""}']
    assert _rejected(tmp_path / "c") == []
    codes = {e["code"] for e in _register(tmp_path / "c")}
    assert "map.adapter_defect" in codes


def test_a_second_snapshot_with_rejected_rows_fails_loudly(rows, tmp_path):
    """R5 option A: a {source_key} not_imported entry belongs to no single snapshot of a multi-snapshot corpus, so the
    counts sealing and ``verify`` recompute refuse it (``corpus.manifest.unattributed``); one snapshot reconciles."""
    from agentprov.corpus.manifest import ManifestError

    data = _file("run", "probe")
    one, pin_one = lines_support._deposit(tmp_path, {LABEL: data}, record=1)
    two, pin_two = lines_support._deposit(tmp_path, {LABEL: data, lines_support.OTHER: _file("run")}, record=2)
    lines_support._run(one, pin_one, tmp_path / "c", snapshot_id="v1")
    assert _counts(tmp_path / "c", "v1")["candidates"] == 2
    lines_support._run(two, pin_two, tmp_path / "c", snapshot_id="v2")
    with pytest.raises(ManifestError) as raised:
        _counts(tmp_path / "c", "v2")
    assert raised.value.code == "corpus.manifest.unattributed"


@pytest.mark.parametrize("stages", ["aer", "prov"])
def test_recompute_reproduces_the_rows(rows, tmp_path, capsys, monkeypatch, stages):
    """A re-map (``aer``) re-derives the rows from the stored file; a re-derive (``prov``) carries them as they are. Either
    way ``register.jsonl`` and the snapshot counts are identical."""
    from agentprov.cli.main import main

    monkeypatch.setenv("AGENTPROV_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("AGENTPROV_PROGRESS", raising=False)
    path, pin = lines_support._deposit(tmp_path, {LABEL: _file("run", "probe", "run", "partial")})
    lines_support._run(path, pin, tmp_path / "c", until="prov")
    capsys.readouterr()
    code = main(["recompute", "--corpus", str(tmp_path / "c.partial"), "--out", str(tmp_path / "n"), "--in-process",
                 "--no-reuse", "--stages", stages, "--json"])
    summary = json.loads(capsys.readouterr().out)
    assert code == 0, summary.get("failures")
    assert summary["counters"]["unexplained_change"] == 0 and summary["counters"]["failed"] == 0
    assert (tmp_path / "n.partial" / "register.jsonl").read_bytes() == (tmp_path / "c.partial" / "register.jsonl").read_bytes()
    assert _counts(tmp_path / "n") == _counts(tmp_path / "c")



class CarvingMapper(lines_support.LineMapper):
    """The test mapper, also carving the run's scenario string (D-218) and citing it from the header's
    ``ext.credleak.run_fields`` (open JSON), so a stored ``carved`` object shows. Since the D-218 check-and-hold
    follow-up a carved blob is stored only when a written AER cites it."""

    def map(self, unit: Any, ctx: Any) -> Iterator[dict[str, Any]]:
        ref = ctx.carve({"line": unit.primary.locator.line, "p": "/scenario"}, "utf8")
        header, *rest = list(super().map(unit, ctx))
        header["ext"] = {"credleak": {**(header.get("ext") or {}).get("credleak", {}), "run_fields": {"scenario": ref}}}
        yield header
        yield from rest


@pytest.mark.parametrize("bad", [None, "code"])
def test_a_refused_file_stores_nothing_it_carved(rows, tmp_path, monkeypatch, bad):
    """D-321 with D-218: invalid rejected rows seal the file whole, and its carved blobs are not stored (the valid case
    is the control: its carved object is stored with a ``carved`` origin)."""
    import agentprov.adapters.runner as runner
    import agentprov.adapters.runner.importer as importer
    from agentprov.adapters.credleak.mapper import CredleakMapper
    from agentprov.adapters.registry import MAPPERS

    fakes_path = MAPPERS[CredleakMapper.mapper_id]
    resolve = runner.resolve_factory
    patched = lambda path: CarvingMapper if path == fakes_path else resolve(path)  # noqa: E731
    monkeypatch.setattr(runner, "resolve_factory", patched)
    monkeypatch.setattr(importer, "resolve_factory", patched)
    rows.bad = bad
    path, pin = lines_support._deposit(tmp_path, {LABEL: _file("run", "probe")})
    lines_support._run(path, pin, tmp_path / "c")
    origins = [json.loads(x) for x in (tmp_path / "c.partial" / "raw" / "origins.jsonl").read_text().splitlines()]
    carved = [o for o in origins if o["origin"]["kind"] == "carved"]
    assert len(carved) == (0 if bad else 1)
