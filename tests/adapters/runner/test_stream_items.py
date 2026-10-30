"""Streamed multi-execution files (D-323, RB-1; D-320 framing; deferrals-session review conditions).

A ``multi_execution`` reader that defines ``sniff_stream`` and ``parse_stream`` is mapped by a ``per_item`` job that opens
the stored primary through ``JobContext.open_input`` (hashed whole before anything parses) and maps and frames each
streamed item at once. Pinned here with a test JSONL reader (registry factory resolution patched in process, dev mode):

* the differential: the streaming and the byte path give the same AER bytes, index, register, and the same order of
  units and register rows (frames compared job by job);
* store-first: a tampered stored object fails the job before ``sniff_stream`` or ``parse_stream`` sees it;
* abort: a failure after the first streamed item keeps one degenerate AER for the file and stores nothing it carved;
* bounded memory: the streaming job never reads the primary through the byte API (``read_input``, ``parse``).
"""

from __future__ import annotations

import io
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import IO, Any

import pytest

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import test_multi_execution_lines as lines_support  # noqa: E402
import test_rejected_rows as rows_support  # noqa: E402

from agentprov.adapters.types import ArtefactRef, LocatedItem, Locator, Rejected, SniffResult  # noqa: E402
from agentprov.errors import IngestError  # noqa: E402
from agentprov.ingest.limits import IngestLimits  # noqa: E402
from agentprov.ingest.loaders import strict_json_loads  # noqa: E402

LABEL = lines_support.LABEL
CALLS: list[str] = []


class ByteReader(rows_support.RowReader):
    """The byte path: cells are executions, probe and partial lines are rejected rows (``rejected``)."""


class StreamReader(ByteReader):
    """The streaming path over the same lines; ``fail_after`` makes ``parse_stream`` fail after that many items."""

    fail_after: int | None = None

    @staticmethod
    def _stream_lines(handle: IO[bytes], limits: IngestLimits) -> Iterator[tuple[int, Any]]:
        for n, line in enumerate(handle):
            yield n, strict_json_loads(line.rstrip(b"\n"), limits)

    def sniff_stream(self, handle: IO[bytes], *, limits: IngestLimits) -> SniffResult:
        CALLS.append("sniff_stream")
        values = [v for _n, v in self._stream_lines(handle, limits)]
        if any(isinstance(v, dict) and "runs" in v for v in values):
            return SniffResult(True, "credleak.cell", "v1", frozenset(), ("test.cells",))
        return SniffResult(False, reasons=("credleak.not_a_cell",))

    def parse_stream(self, handle: IO[bytes], artefact: ArtefactRef, *, limits: IngestLimits) -> Iterator[LocatedItem]:
        CALLS.append("parse_stream")
        done = 0
        for n, value in self._stream_lines(handle, limits):
            if isinstance(value, dict) and "runs" in value:
                if self.fail_after is not None and done >= self.fail_after:
                    raise IngestError("ingest.json.syntax", "injected failure while streaming")
                yield LocatedItem(artefact=artefact, locator=Locator(a=artefact.id, line=n), dialect="credleak.cell",
                                  variant="v1", flags=frozenset(), value=value)
                done += 1

    def rejected_stream(self, handle: IO[bytes], artefact: ArtefactRef, *, limits: IngestLimits) -> Iterator[Rejected]:
        yield from self.rejected(handle.read(), artefact, limits=limits)

    def parse(self, data: bytes, artefact: ArtefactRef, *, limits: IngestLimits) -> Iterator[LocatedItem]:
        CALLS.append("parse")
        yield from self.parse_stream(io.BytesIO(data), artefact, limits=limits)


def _patch(monkeypatch: pytest.MonkeyPatch, reader: type, mapper: type = lines_support.LineMapper) -> None:
    import agentprov.adapters.runner as runner
    import agentprov.adapters.runner.importer as importer
    from agentprov.adapters.credleak.dialect import DIALECT_ID
    from agentprov.adapters.credleak.mapper import CredleakMapper
    from agentprov.adapters.registry import MAPPERS, READERS

    original = runner.resolve_factory
    fakes = {READERS[DIALECT_ID]: reader, MAPPERS[CredleakMapper.mapper_id]: mapper}
    monkeypatch.setattr(runner, "resolve_factory", lambda path: fakes.get(path) or original(path))
    monkeypatch.setattr(importer, "resolve_factory", lambda path: fakes.get(path) or original(path))


def _tree(corpus: Path) -> dict[str, bytes]:
    root = corpus.with_name(corpus.name + ".partial")
    keep = ("aer/", "executions.jsonl", "register.jsonl", "raw/origins.jsonl")
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*"))
            if p.is_file() and str(p.relative_to(root)).startswith(keep)}


def test_streaming_and_byte_paths_give_the_same_corpus(monkeypatch, tmp_path):
    data = rows_support._file("run", "probe", "run", "partial", "run")
    path, pin = lines_support._deposit(tmp_path, {LABEL: data})
    with monkeypatch.context() as m:
        _patch(m, type("B", (ByteReader,), {}))
        bytes_report = lines_support._run(path, pin, tmp_path / "b")
    with monkeypatch.context() as m:
        _patch(m, type("S", (StreamReader,), {}))
        stream_report = lines_support._run(path, pin, tmp_path / "s")
    assert bytes_report.counters == stream_report.counters and stream_report.counters["mapped"] == 3
    assert _tree(tmp_path / "s") == _tree(tmp_path / "b")
    assert [e["subject"] for e in stream_report.register] == [e["subject"] for e in bytes_report.register]


def test_the_two_paths_emit_the_same_frames_in_the_same_order(monkeypatch):
    """Job by job: unit frames, records, seals and register rows, in order (the parent sorts rows again, D-321)."""
    from agentprov.adapters.runner import job_map
    from agentprov.ingest.limits import IngestLimits
    from agentprov.raw.origins import Origin

    data = rows_support._file("probe", "run", "partial", "run")
    origin = Origin.member("cd" * 32, LABEL, 8, 1, len(data))

    class Ctx:
        def __init__(self, stream: bool) -> None:
            import hashlib

            self.inputs = ({"sha256": hashlib.sha256(data).hexdigest(), "role": "primary"},)
            self.params = {"profile": "credleak-p15b", "origin": origin.to_json(), "mode": "total", "per_item": True,
                           "limits": IngestLimits().to_json(), **({"stream": True} if stream else {})}
            self.frames: list[Any] = []

        def read_input(self, index: int) -> bytes:
            return data

        def open_input(self, index: int) -> IO[bytes]:
            return io.BytesIO(data)

        def emit(self, frame: Any) -> None:
            self.frames.append(frame)

    with monkeypatch.context() as m:
        _patch(m, type("B", (ByteReader,), {}))
        by_bytes = Ctx(False)
        job_map(by_bytes)
    with monkeypatch.context() as m:
        _patch(m, type("S", (StreamReader,), {}))
        by_stream = Ctx(True)
        job_map(by_stream)
    units = lambda frames: [f["unit"]["loc"] for f in frames if "unit" in f]  # noqa: E731
    rows = lambda frames: [f["register"]["loc"] for f in frames if "register" in f]  # noqa: E731
    assert units(by_stream.frames) == units(by_bytes.frames) == [{"line": 1}, {"line": 3}]
    assert rows(by_stream.frames) == rows(by_bytes.frames) == [{"line": 0}, {"line": 2}]
    assert [f for f in by_stream.frames if "register" not in f] == [f for f in by_bytes.frames if "register" not in f]


def test_a_tampered_stored_object_fails_before_the_stream_is_read(monkeypatch, tmp_path):
    """Store-first (G.4.5): ``open_input`` hashes the object whole; a mismatch fails the job, and neither ``sniff_stream``
    nor the first read of ``parse_stream`` happens. The file is kept as one degenerate AER (job failure)."""
    import os

    from agentprov.corpus.writer import CorpusWriter

    original = CorpusWriter.add_object
    data = rows_support._file("run", "run")

    def add_then_tamper(self: Any, payload: Any, origin: Any, *, ext: str = "bin", **expected: Any) -> Any:
        put = original(self, payload, origin, ext=ext, **expected)
        if isinstance(payload, bytes) and payload == data:
            target = next(p for p in (self.store.objects_dir / put.sha256[:2]).iterdir() if p.name.startswith(put.sha256))
            os.chmod(target, 0o644)
            target.write_bytes(data.replace(b"T1", b"T2", 1))
            os.chmod(target, 0o444)
        return put

    CALLS.clear()
    _patch(monkeypatch, type("S", (StreamReader,), {}))
    monkeypatch.setattr(CorpusWriter, "add_object", add_then_tamper)
    path, pin = lines_support._deposit(tmp_path, {LABEL: data})
    report = lines_support._run(path, pin, tmp_path / "c")
    assert "sniff_stream" not in CALLS and "parse_stream" not in CALLS
    assert (report.counters["mapped"], report.counters["degenerate"]) == (1, 1)
    assert lines_support._locs(tmp_path / "c") == ['{"p":""}']


def test_an_abort_after_the_first_item_keeps_the_file_whole_and_stores_nothing_carved(monkeypatch, tmp_path):
    reader = type("S", (StreamReader,), {"fail_after": 1})
    _patch(monkeypatch, reader, rows_support.CarvingMapper)
    path, pin = lines_support._deposit(tmp_path, {LABEL: rows_support._file("run", "probe", "run")})
    report = lines_support._run(path, pin, tmp_path / "c")
    assert (report.counters["mapped"], report.counters["degenerate"], report.counters["registered"]) == (1, 1, 0)
    assert lines_support._locs(tmp_path / "c") == ['{"p":""}']
    origins = [json.loads(x) for x in (tmp_path / "c.partial" / "raw" / "origins.jsonl").read_text().splitlines()]
    assert [o for o in origins if o["origin"]["kind"] == "carved"] == []
    codes = {e["code"] for e in rows_support._register(tmp_path / "c")}
    assert "map.unparseable_artefact" in codes
    resumed = lines_support._run(path, pin, tmp_path / "c")  # the whole-file rule resumes it whole
    assert (resumed.counters["mapped"], resumed.counters["skipped_resume"]) == (0, 1)


def test_the_streaming_job_never_reads_the_primary_through_the_byte_api(monkeypatch, tmp_path):
    import agentprov.adapters.runner as runner
    from agentprov.io.workers import JobContext

    CALLS.clear()
    _patch(monkeypatch, type("S", (StreamReader,), {}))
    read = JobContext.read_input
    primaries: list[int] = []

    def spy_read(self: Any, index: int) -> bytes:
        if index == 0:
            primaries.append(index)
        return read(self, index)

    monkeypatch.setattr(JobContext, "read_input", spy_read)
    monkeypatch.setattr(runner, "map_artefact_units", lambda *a, **k: pytest.fail("the byte path was taken"))
    path, pin = lines_support._deposit(tmp_path, {LABEL: rows_support._file("run", "run", "probe")})
    report = lines_support._run(path, pin, tmp_path / "c")
    assert report.counters["mapped"] == 2 and primaries == [] and "parse" not in CALLS


def test_an_import_under_a_raising_profile_records_the_raised_limit(monkeypatch, tmp_path):
    """RB-2 end to end: the profile's ``[import] limits`` raise reaches the effective limits, which ``corpus.json`` records
    as an override (the value ``recompute`` replays and compares, D-323)."""
    from importlib import resources

    import agentprov.adapters.runner as runner
    import agentprov.adapters.runner.importer as importer
    from agentprov.adapters.profiles import parse_profile
    from agentprov.ingest.profile_limits import PROFILE_RAISABLE

    ceiling = PROFILE_RAISABLE["max_json_element_bytes"]
    text = resources.files("agentprov").joinpath("adapters", "credleak", "profiles",
                                                 "credleak-p15b.profile.toml").read_text("utf-8")
    raising = parse_profile(text.replace("\n[import]\n", f"\n[import]\nlimits = {{ max_json_element_bytes = {ceiling} }}\n",
                                         1).encode(), source="t")
    real = runner.load_profile
    monkeypatch.setattr(runner, "load_profile", lambda pid: raising if pid == "credleak-p15b" else real(pid))
    monkeypatch.setattr(importer, "load_profile", lambda pid: raising if pid == "credleak-p15b" else real(pid))
    _patch(monkeypatch, type("S", (StreamReader,), {}))
    path, pin = lines_support._deposit(tmp_path, {LABEL: rows_support._file("run")})
    report = lines_support._run(path, pin, tmp_path / "c")
    assert report.counters["mapped"] == 1 and report.limits["max_json_element_bytes"] == ceiling
    manifest = json.loads((tmp_path / "c.partial" / "corpus.json").read_text())
    assert manifest["limits"]["overrides"] == {"max_json_element_bytes": ceiling}
