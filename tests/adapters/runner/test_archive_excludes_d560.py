"""D-560: an archive input registers the members a profile ``exclude`` entry names, as a directory input does (D-191).

The ``expand`` selection of an archive input is the profile's include globs only (R-40), so a member that only an exclude
entry names is a ``not_selected`` row of ``raw/members.jsonl``. It is now also registered with the entry's code and counted
in ``selection_excluded``; it is still never decompressed. The directory-input control is
``test_profile_selection.py::test_out_of_scope_executions_are_registered_not_dropped_d191``.

Inputs: the committed FooBench fixture and one committed AgentOps-Bench run (byte-identical members, loaded and never
printed); out-of-scope members carry synthetic bytes, which no stage reads. No network.
"""

from __future__ import annotations

import hashlib
import io
import json
import sys
import tarfile
import zipfile
from pathlib import Path
from typing import Any

import pytest

import agentprov.adapters.runner as runner_pkg
import agentprov.adapters.runner.importer as importer
from agentprov.adapters.profiles import load_profile, parse_profile
from agentprov.adapters.runner.importer import ArchiveTree, import_source
from agentprov.corpus.writer import CorpusWriter

REPO = Path(__file__).resolve().parents[3]
FOO = REPO / "tests" / "fixtures" / "foobench"
FOO_PROFILE = REPO / "src" / "agentprov" / "adapters" / "foobench" / "profiles" / "foobench.profile.toml"
sys.path.insert(0, str(REPO / "tests" / "adapters" / "agentops"))
import agentops_support  # noqa: E402


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines()] if path.exists() else []


def _foo_profile(monkeypatch: pytest.MonkeyPatch, extra_excludes: str) -> None:
    text = FOO_PROFILE.read_text("utf-8")
    anchor = '  { glob = "**/._*", code = "select.not_execution_artefact" },\n'
    assert anchor in text
    profile = parse_profile(text.replace(anchor, anchor + extra_excludes).encode("utf-8"), source="test-variant")
    monkeypatch.setattr(importer, "load_profile", lambda _pid: profile)
    monkeypatch.setattr(runner_pkg, "load_profile", lambda _pid: profile)


def _zip(path: Path, members: dict[str, bytes]) -> dict[str, Any]:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    path.write_bytes(buf.getvalue())
    return {"role": "fixture", "kind": "zenodo", "doi": "10.5281/zenodo.1", "record": 1, "version": "v1",
            "file": path.name, "sha256": hashlib.sha256(buf.getvalue()).hexdigest(), "bytes": len(buf.getvalue())}


def _import(tmp: Path, pin: dict[str, Any], source: str, profile_id: str, part: str) -> tuple[Any, Path]:
    tree = ArchiveTree(tmp / pin["file"], pin=pin, sha256=pin["sha256"], size=pin["bytes"])
    with CorpusWriter(tmp / "c") as writer:
        report = import_source(source, tree, corpus=writer, profile_id=profile_id, part=part, pin=pin, in_process=True,
                               until="aer")
    return report, tmp / "c.partial"


def test_a_member_only_an_exclude_entry_names_is_registered_and_never_decompressed(tmp_path, monkeypatch):
    _foo_profile(monkeypatch, '  { glob = "deposit/notes/**", code = "select.out_of_scope", note = "D-143" },\n')
    pin = _zip(tmp_path / "deposit.zip", {
        **{f"deposit/traces/{name}": (FOO / name).read_bytes() for name in ("trace-001.jsonl", "sub-trace-001.jsonl",
                                                                              "screenshot-0.png")},
        "deposit/notes/a.txt": b"out of scope\n", "deposit/notes/sub/b.txt": b"out of scope\n",
        "deposit/notes/._a.txt": b"\x00\x05\x16\x07", "deposit/README.txt": b"neither selected nor excluded\n",
    })
    report, partial = _import(tmp_path, pin, "foobench", "foobench", "fixture")
    # the FooBench trace seals with its fixture issues either way (as in test_deferrals_part_a); only selection matters
    assert report.counters["mapped"] == 1 and report.counters["excluded"] == 2
    rows = [r for r in _jsonl(partial / "register.jsonl") if r["stage"] == "select"]
    assert {r["subject"]["path"] for r in rows} == {"deposit.zip!/deposit/notes/a.txt", "deposit.zip!/deposit/notes/sub/b.txt"}
    assert all(r["code"] == "select.out_of_scope" and r["disposition"] == "not_imported" for r in rows)
    members = {m["label"]: m for m in _jsonl(partial / "raw" / "members.jsonl")}
    # still outside the expand selection: recorded, never decompressed or stored (R-40); the AppleDouble stray and the
    # unmatched README stay unregistered, as for a directory input
    assert {members[k]["disposition"] for k in ("deposit/notes/a.txt", "deposit/notes/._a.txt", "deposit/README.txt")} == {"not_selected"}
    assert members["deposit/notes/a.txt"].get("sha256") is None
    snapshot = json.loads((partial / "corpus.json").read_text("utf-8"))["sources"][0]["snapshots"][0]
    assert snapshot["counts"]["selection_excluded"] == 2


def test_agentops_out_of_scope_runs_in_an_archive_are_registered_select_out_of_scope(tmp_path):
    """The AgentOps-Bench shape (docs/reports/phase10i/README.md §10.4 finding 3): the clean and noisy runs of the
    non-safety domains are named only by ``select.out_of_scope`` entries; the per-model rollups by
    ``select.not_execution_artefact``. Every one is registered; the in-scope run is mapped."""
    label = agentops_support.F["task_with_context"]  # an adversarial run, in scope
    out_of_scope = [
        "pilot_v1_seeded/gpt55/openai_gpt-5.5/clean/code_001_run1.json",
        "pilot_v1_seeded/gpt55/openai_gpt-5.5/noisy/research_011_run2.json",
        "pilot_v1_seeded/gpt55/openai_gpt-5.5/clean/data_analysis_003_run3.json",
        "pilot_v1_seeded/gpt55/openai_gpt-5.5/noisy/tool_use_020_run1.json",
    ]
    rollups = ["pilot_v1_seeded/gpt55/gpt55_report.json", "pilot_v1_seeded/_combined/summary.md"]
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz", format=tarfile.USTAR_FORMAT) as tar:
        for name, data in [(label, agentops_support.run_bytes(label)), *((n, b"{}") for n in out_of_scope + rollups),
                           ("pilot_v1_seeded/gpt55/openai_gpt-5.5/clean/._code_001_run1.json", b"\x00\x05\x16\x07")]:
            info = tarfile.TarInfo(name)
            info.size, info.mtime = len(data), 0
            tar.addfile(info, io.BytesIO(data))
    (tmp_path / "traces.tar.gz").write_bytes(buf.getvalue())
    runs_pin = dict(next(p for p in load_profile("agentops-bench-pilot").data["source"]["pins"] if p["role"] == "runs"))
    pin = {**runs_pin, "file": "traces.tar.gz", "sha256": hashlib.sha256(buf.getvalue()).hexdigest(),
           "bytes": len(buf.getvalue()), "md5": hashlib.md5(buf.getvalue(), usedforsecurity=False).hexdigest()}
    report, partial = _import(tmp_path, pin, "agentops-bench", "agentops-bench-pilot", "pilot-v1-seeded")
    assert report.exit_code == 0 and report.counters["mapped"] == 1
    rows = {r["subject"]["path"]: r["code"] for r in _jsonl(partial / "register.jsonl") if r["stage"] == "select"}
    assert rows == {**{f"traces.tar.gz!/{n}": "select.out_of_scope" for n in out_of_scope},
                    **{f"traces.tar.gz!/{n}": "select.not_execution_artefact" for n in rollups}}
    assert report.counters["excluded"] == len(out_of_scope) + len(rollups)
