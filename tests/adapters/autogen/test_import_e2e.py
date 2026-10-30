"""End-to-end import of AutoGen run rows through the product path (D-301; R-10k-1, D-320; D-200 archive inputs).

The committed fixture members are packed into a zip at their deposit labels (a test deposit with its own pin, never the
real one), and ``import_source`` imports it into a temporary corpus: one execution per run row, source key
``sha256:<file>#{"line": n}``, the per-unit inputs found in the same archive. Nothing prints fixture content.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path
from typing import Any

import autogen_support as support


def _deposit(base: Path, extra_rows: bytes = b"", extra_files: dict[str, bytes] | None = None) -> tuple[Path, dict[str, Any]]:
    """One deterministic test deposit per directory (fixed member times), reused by every import of a test;
    ``extra_rows`` are appended to the run file and ``extra_files`` added as members (synthetic rows, built in memory,
    never committed)."""
    path = base / "deposit.zip"
    if not path.is_file():
        buf = io.BytesIO()
        members = {label: data for label, (data, _method) in support.fixture_members().items()}
        members[support.TOOL_ARM] += extra_rows
        members.update(extra_files or {})
        with zipfile.ZipFile(buf, "w") as zf:
            for label, data in sorted(members.items()):
                info = zipfile.ZipInfo(label, (2026, 9, 29, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                zf.writestr(info, data)
        path.write_bytes(buf.getvalue())
    data = path.read_bytes()
    pin = {"role": "deposit", "kind": "zenodo", "doi": "10.5281/zenodo.1", "record": 1, "version": "v1",
           "file": path.name, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    return path, pin


def _import(base: Path, corpus: Path, extra_rows: bytes = b"", extra_files: dict[str, bytes] | None = None,
            **kwargs: Any) -> Any:
    from agentprov.adapters.runner.importer import ArchiveTree, import_source
    from agentprov.corpus.writer import CorpusWriter

    path, pin = _deposit(base, extra_rows, extra_files)
    tree = ArchiveTree(path, pin=pin, sha256=pin["sha256"], size=pin["bytes"])
    with CorpusWriter(corpus) as writer:
        return import_source(support.PROFILE, tree, corpus=writer, profile_id=support.PROFILE, part="v1.0", pin=pin,
                             snapshot_id="v1.0", mode="release", workers=1, **kwargs)


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line]


def test_the_tool_arm_imports_as_one_execution_per_run_row(tmp_path):
    report = _import(tmp_path, tmp_path / "c")
    assert report.exit_code == 0, (report.counters, report.failures[:3])
    assert report.counters["mapped"] == 20 and report.counters["degenerate"] == 0, report.counters
    rows = _jsonl(tmp_path / "c.partial" / "executions.jsonl")
    keys = sorted(r["source_key"] for r in rows)
    digest = keys[0][len("sha256:"):len("sha256:") + 64]
    assert keys == sorted(f'sha256:{digest}#{{"line":{n}}}' for n in range(20))
    for row in rows:
        header = json.loads((tmp_path / "c.partial" / row["paths"]["aer"]).read_bytes().split(b"\n", 1)[0])
        roles = {a["origin"].get("label", "").rsplit("/", 1)[-1] for a in header["artifacts"][1:]}
        assert {"events.jsonl", "guard_raw.jsonl", "injecagent_dh.jsonl", "config.json", "capture.json"} <= roles


def test_the_import_is_deterministic_and_resumes(tmp_path):
    first = _import(tmp_path, tmp_path / "a", limit=7)
    assert first.counters["mapped"] == 7 and first.partial
    second = _import(tmp_path, tmp_path / "a")
    assert (second.counters["mapped"], second.counters["skipped_resume"]) == (13, 7)
    _import(tmp_path, tmp_path / "b")

    def tree(root: Path) -> dict[str, bytes]:
        return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}

    a, b = tree(tmp_path / "a.partial"), tree(tmp_path / "b.partial")
    a.pop("corpus.json"), b.pop("corpus.json")
    assert a == b


_RAIL = {"probe_id": "p", "response": "", "backend": None, "history_id": "h", "outcome": "o", "events": [], "wall_s": 1}
_FRAMEWORK = {"probe_id": "p", "framework": "crewai", "result": {}, "returncode": 0, "stderr_tail": "", "wall_s": 1}


def _lines(*rows: dict[str, Any]) -> bytes:
    return "".join(json.dumps(r) + "\n" for r in rows).encode()


def _selected(corpus: Path) -> dict[tuple[str, int], dict[str, Any]]:
    """The ``select`` register rows with a line subject, by ``(file sha256, line)``."""
    out = {}
    for row in _jsonl(corpus / "register.jsonl"):
        key = row.get("subject", {}).get("source_key", "")
        if str(row.get("code", "")).startswith("select.") and "#" in key:
            out[(key.split("#", 1)[0], json.loads(key.split("#", 1)[1])["line"])] = row
    return out


def test_rows_that_are_not_runs_are_registered_one_by_one(tmp_path):
    """D-300 with D-321: a guardrail-rail row and a framework row inside a run file are register rows with their line as
    subject, never dropped; the runs beside them import as before."""
    report = _import(tmp_path, tmp_path / "c", _lines(_RAIL, _FRAMEWORK))
    assert report.exit_code == 0, (report.counters, report.failures[:3])
    assert report.counters["mapped"] == 20 and report.counters["degenerate"] == 0, report.counters
    rows = {line: row for (_sha, line), row in _selected(tmp_path / "c.partial").items()}
    assert sorted(rows) == [20, 21]
    assert (rows[20]["code"], rows[20]["detail"]) == ("select.not_execution_artefact", "autogen.rail_probe_no_agent")
    assert (rows[21]["code"], rows[21]["detail"]) == ("select.out_of_scope", "autogen.partial_trajectory")
    assert all(r["disposition"] == "not_imported" for r in rows.values())


def test_files_without_runs_register_every_row(tmp_path):
    """The phase 7-9 layout: run files with no run row are selected (no profile exclusion), and each row is registered on
    its line with the code of its kind, never one file-level entry (D-300)."""
    root = support.ROOT + "results/"
    extra = {root + "phase7/runs.jsonl": _lines(_RAIL, _RAIL, _RAIL), root + "phase9/runs.jsonl": _lines(_FRAMEWORK, _FRAMEWORK)}
    report = _import(tmp_path, tmp_path / "c", extra_files=extra)
    assert report.exit_code == 0, (report.counters, report.failures[:3])
    assert report.counters["mapped"] == 20 and report.counters["degenerate"] == 0, report.counters
    by_file: dict[str, list[tuple[int, str, str]]] = {}
    for (sha, line), row in _selected(tmp_path / "c.partial").items():
        by_file.setdefault(sha, []).append((line, row["code"], row["detail"]))
    shas = {f"sha256:{hashlib.sha256(data).hexdigest()}": label.rsplit("/", 2)[-2] for label, data in extra.items()}
    assert {shas[sha]: sorted(rows) for sha, rows in by_file.items()} == {
        "phase7": [(n, "select.not_execution_artefact", "autogen.rail_probe_no_agent") for n in range(3)],
        "phase9": [(n, "select.out_of_scope", "autogen.partial_trajectory") for n in range(2)],
    }
    paths = [r for r in _jsonl(tmp_path / "c.partial" / "register.jsonl")
             if "phase7" in json.dumps(r.get("subject", {})) or "phase9" in json.dumps(r.get("subject", {}))]
    assert paths == []  # no file-level entry stands in for the rows
