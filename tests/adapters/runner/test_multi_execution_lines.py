"""Multi-execution whole files with JSONL line locators (R-10k-1, D-320; D.2.9 note item 11; HL H.7.1, H.7.2).

The runner keys every execution of a ``multi_execution`` file by its source key, whatever the locator shape. Credleak
exercises ``{"p": "/runs/<i>"}``; this pins ``{"line": n}`` (one execution per JSONL line, the shape phase 10n's AutoGen
``runs.jsonl`` needs, R-10n-3) before any family depends on it. No shipped family reads JSONL this way yet, so the
registry's factory resolution is patched in process (dev mode): a test reader yields one item per line, and a test mapper
writes the credleak header plus a run scope that cites the line. The deposit is an archive input (D-200) whose member is
the JSONL file. Lines are synthetic one-run cells built at test time.
"""

from __future__ import annotations

import hashlib
import io
import json
import sys
import zipfile
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

import pytest

_CREDLEAK = Path(__file__).resolve().parents[1] / "credleak"
if str(_CREDLEAK) not in sys.path:
    sys.path.insert(0, str(_CREDLEAK))

import credleak_support as support  # noqa: E402

from agentprov.adapters.credleak.dialect import DIALECT_ID, VARIANT, CredleakCellReader  # noqa: E402
from agentprov.adapters.credleak.mapper import CredleakMapper, _header_base, _task  # noqa: E402
from agentprov.adapters.types import ArtefactRef, LocatedItem, Locator, SniffResult  # noqa: E402
from agentprov.errors import IngestError, MalformedArtefact  # noqa: E402
from agentprov.ingest.limits import IngestLimits  # noqa: E402
from agentprov.ingest.loaders import strict_json_loads  # noqa: E402
from agentprov.progress import ProgressEvent  # noqa: E402

LABEL = "p15b-run-data/01-injection-map/T1-file-document/test-model/runs.json"
OTHER = "p15b-run-data/01-injection-map/T1-file-document/test-model/other.json"


class LineReader(CredleakCellReader):
    """One execution per JSONL line (``Locator(line=n)``); each line is a one-run cell."""

    multi_execution = True

    def _lines(self, data: bytes, limits: IngestLimits) -> list[Any]:
        return [strict_json_loads(line, limits) for line in data.split(b"\n") if line]

    def sniff(self, data: bytes, *, label: str, limits: IngestLimits) -> SniffResult:
        try:
            values = self._lines(data, limits)
        except IngestError as exc:
            return SniffResult(False, reasons=(exc.code,))
        if all(isinstance(v, dict) and "runs" in v for v in values):
            return SniffResult(True, DIALECT_ID, VARIANT, frozenset(), ("test.jsonl_lines",))
        return SniffResult(False, reasons=("credleak.not_a_cell",))

    def parse(self, data: bytes, artefact: ArtefactRef, *, limits: IngestLimits) -> Iterator[LocatedItem]:
        if not self.sniff(data, label="", limits=limits).match:
            raise MalformedArtefact("not a JSONL file of cells")
        for n, value in enumerate(self._lines(data, limits)):
            yield LocatedItem(artefact=artefact, locator=Locator(a=artefact.id, line=n), dialect=DIALECT_ID,
                              variant=VARIANT, flags=frozenset(), value=value)


class LineMapper(CredleakMapper):
    """The credleak header and one run scope citing the execution's line."""

    def map(self, unit: Any, ctx: Any) -> Iterator[dict[str, Any]]:
        item = unit.primary
        assert item.locator.line is not None and item.locator.p is None
        yield _header_base(unit, ctx, _task(item.value), [item.artefact.to_json()], cell_fields=False)
        yield {"k": "scope", "id": "run", "kind": "run", "ev": "O", "by": "source",
               "src": [{"a": item.artefact.id, **item.locator.key()}],
               "unk": {"/status": "not_recorded", "/t": "not_recorded"}}


@pytest.fixture
def lines(monkeypatch: pytest.MonkeyPatch) -> None:
    import agentprov.adapters.runner as runner
    import agentprov.adapters.runner.importer as importer
    from agentprov.adapters.registry import MAPPERS, READERS

    original = runner.resolve_factory
    fakes = {READERS[DIALECT_ID]: LineReader, MAPPERS[CredleakMapper.mapper_id]: LineMapper}

    def resolve(path: str) -> Any:
        return fakes.get(path) or original(path)

    monkeypatch.setattr(runner, "resolve_factory", resolve)
    monkeypatch.setattr(importer, "resolve_factory", resolve)


def _jsonl(rows: int, scenario: str = "T1.9") -> bytes:
    return b"".join(json.dumps(json.loads(support.synthetic_cell(scenario=f"{scenario}.{n}", technique="T1")),
                               separators=(",", ":")).encode() + b"\n" for n in range(rows))


def _deposit(base: Path, members: Mapping[str, bytes], *, record: int = 1) -> tuple[Path, dict[str, Any]]:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for label, data in members.items():
            zf.writestr(label, data)
    path = base / f"v{record}.zip"
    path.write_bytes(buf.getvalue())
    data = path.read_bytes()
    pin = {"role": "head", "kind": "zenodo", "doi": f"10.5281/zenodo.{record}", "record": record, "version": f"v{record}",
           "file": path.name, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    return path, pin


def _run(path: Path, pin: Mapping[str, Any], corpus: Path, **kwargs: Any) -> Any:
    from agentprov.adapters.runner.importer import ArchiveTree, import_source
    from agentprov.corpus.writer import CorpusWriter

    kwargs.setdefault("snapshot_id", "head")
    kwargs.setdefault("until", "aer")
    tree = ArchiveTree(path, pin=pin, sha256=pin["sha256"], size=pin["bytes"])
    with CorpusWriter(corpus) as writer:
        return import_source("credleak-p15b", tree, corpus=writer, profile_id="credleak-p15b", part="head", pin=pin,
                             mode="dev", in_process=True, **kwargs)


def _rows(corpus: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in (corpus.with_name(corpus.name + ".partial") / "executions.jsonl").read_text().splitlines()]


def _locs(corpus: Path) -> list[str]:
    return sorted(r["source_key"].split("#", 1)[1] for r in _rows(corpus))


def test_each_line_is_one_execution_keyed_by_its_line(lines, tmp_path):
    path, pin = _deposit(tmp_path, {LABEL: _jsonl(3)})
    report = _run(path, pin, tmp_path / "c")
    assert (report.counters["mapped"], report.counters["degenerate"]) == (3, 0), report.counters
    assert _locs(tmp_path / "c") == ['{"line":0}', '{"line":1}', '{"line":2}']
    assert len({r["ex"] for r in _rows(tmp_path / "c")}) == 3
    assert all(r["stages"]["aer"] == "ok" for r in _rows(tmp_path / "c"))  # the AER validator resolves the line locators


def test_an_interrupt_between_lines_resumes_by_key(lines, tmp_path):
    path, pin = _deposit(tmp_path, {LABEL: _jsonl(3)})

    class Stop:
        def emit(self, event: ProgressEvent) -> None:
            if event.kind == "unit_done":
                raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        _run(path, pin, tmp_path / "c", progress=Stop())
    assert _locs(tmp_path / "c") == ['{"line":0}']
    resumed = _run(path, pin, tmp_path / "c")
    assert (resumed.counters["mapped"], resumed.counters["skipped_resume"]) == (2, 1)
    assert _locs(tmp_path / "c") == ['{"line":0}', '{"line":1}', '{"line":2}']
    limited = _run(path, pin, tmp_path / "d", limit=2)  # --limit counts executions inside the file
    assert limited.counters["mapped"] == 2
    assert _run(path, pin, tmp_path / "d").counters["mapped"] == 1


def test_a_crashed_file_resumes_whole_not_as_its_lines(lines, tmp_path, monkeypatch):
    import agentprov.adapters.runner as runner

    path, pin = _deposit(tmp_path, {LABEL: _jsonl(3)})

    def crash(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("injected worker crash")

    with monkeypatch.context() as patched:
        patched.setattr(runner, "map_artefact_units", crash)
        first = _run(path, pin, tmp_path / "c")
    assert (first.counters["mapped"], first.counters["degenerate"]) == (1, 1)
    assert _locs(tmp_path / "c") == ['{"p":""}']
    resumed = _run(path, pin, tmp_path / "c")
    assert (resumed.counters["mapped"], resumed.counters["skipped_resume"]) == (0, 1)
    assert _locs(tmp_path / "c") == ['{"p":""}']


def test_a_byte_identical_file_in_a_second_snapshot_collapses_every_line(lines, tmp_path):
    data = _jsonl(2)
    one, pin_one = _deposit(tmp_path, {LABEL: data}, record=1)
    two, pin_two = _deposit(tmp_path, {LABEL: data, OTHER: _jsonl(1, "T1.8")}, record=2)
    _run(one, pin_one, tmp_path / "c", snapshot_id="v1")
    report = _run(two, pin_two, tmp_path / "c", snapshot_id="v2")
    assert (report.counters["mapped"], report.counters["duplicates"], report.counters["skipped_resume"]) == (1, 2, 0)
    rows = _rows(tmp_path / "c")
    shared = sorted(r["source_key"] for r in rows if r["snapshot_ids"] == ["v1", "v2"])
    assert [k.split("#", 1)[1] for k in shared] == ['{"line":0}', '{"line":1}']
    register = [json.loads(x) for x in (tmp_path / "c.partial" / "register.jsonl").read_text().splitlines()]
    assert sorted(e["subject"]["source_key"] for e in register if e["code"] == "dedup.collapsed") == shared


# ---- D-414: the parent's two passes over a per_item result (run in memory and spooled by the conftest) --------------


def _register(corpus: Path) -> list[dict[str, Any]]:
    path = corpus.with_name(corpus.name + ".partial") / "register.jsonl"
    return [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []


def test_a_limit_inside_a_file_seals_only_the_first_executions(lines, tmp_path):
    path, pin = _deposit(tmp_path, {LABEL: _jsonl(5)})
    _run(path, pin, tmp_path / "c", limit=2)
    assert len(_rows(tmp_path / "c")) == 2


def test_a_record_before_the_first_unit_frame_stops_before_anything_is_sealed(lines, tmp_path, monkeypatch):
    import agentprov.adapters.runner as runner

    real = runner.job_map

    def stray_record_first(ctx: Any) -> Any:
        ctx.emit({"record": {"k": "stray"}})
        return real(ctx)

    monkeypatch.setattr(runner, "job_map", stray_record_first)
    path, pin = _deposit(tmp_path, {LABEL: _jsonl(3)})
    from agentprov.errors import AgentProvError

    with pytest.raises(AgentProvError) as info:
        _run(path, pin, tmp_path / "c")
    assert info.value.code == "adapter.job_incomplete"
    aer = tmp_path / "c.partial" / "aer"
    assert not aer.exists() or not any(aer.rglob("*.aer.jsonl"))


def test_a_file_of_another_dialect_is_registered_not_imported(lines, tmp_path):
    path, pin = _deposit(tmp_path, {LABEL: _jsonl(2), OTHER: b'{"not": "a cell"}\n'})
    _run(path, pin, tmp_path / "c")
    assert len(_rows(tmp_path / "c")) == 2
    codes = [e["code"] for e in _register(tmp_path / "c")]
    assert "select.not_execution_artefact" in codes


def test_a_select_frame_on_a_per_item_result_registers_the_file(lines, tmp_path, monkeypatch):
    import agentprov.adapters.runner as runner

    real = runner.job_map

    def select_other(ctx: Any) -> Any:
        if ctx.params.get("per_item") and "other" in json.dumps(ctx.params.get("origin")):
            ctx.emit({"select": {"code": "select.dialect_planned", "detail": "a variant of another part"}})
            return {"records": 0, "degenerate": 0}
        return real(ctx)

    monkeypatch.setattr(runner, "job_map", select_other)
    path, pin = _deposit(tmp_path, {LABEL: _jsonl(2), OTHER: _jsonl(1, "T1.8")})
    _run(path, pin, tmp_path / "c")
    assert len(_rows(tmp_path / "c")) == 2
    assert "select.dialect_planned" in [e["code"] for e in _register(tmp_path / "c")]
