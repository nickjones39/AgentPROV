"""D-530: an archive download pin as a per-unit context tree (runner item R2).

A context role whose pin is a downloaded archive (RedCode's Qwen Code supplementary zip, Zenodo 23168099) is stored with
the pin's origin, expanded through the ``expand`` stage with the role's ``[import] context_artefacts`` globs (AD-12; never
extracted to disk), and its selected members are the role's context artefacts, with ``member`` origins. The manifest's
``snapshot.context[]`` entry records the pin and the stored container, so a re-map can rebuild the tree.

Inputs: one committed AgentOps-Bench run and its committed task YAMLs (byte-identical members, loaded and never printed),
packed into synthetic archives here. No network.
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

from agentprov.adapters.profiles import load_profile
from agentprov.adapters.runner.importer import ArchiveTree, ContextTree, import_source
from agentprov.corpus.writer import CorpusWriter
from agentprov.errors import AgentProvError

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "tests" / "adapters" / "agentops"))
import agentops_support  # noqa: E402

DOI = "10.5281/zenodo.9"


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines()] if path.exists() else []


def _pin(path: Path, data: bytes, role: str) -> dict[str, Any]:
    path.write_bytes(data)
    return {"role": role, "kind": "zenodo", "doi": DOI, "file": path.name, "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data), "md5": hashlib.md5(data, usedforsecurity=False).hexdigest()}


def _runs_tar(tmp: Path, labels: list[str]) -> dict[str, Any]:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz", format=tarfile.USTAR_FORMAT) as tar:
        for label in labels:
            data = agentops_support.run_bytes(label)
            info = tarfile.TarInfo(label)
            info.size, info.mtime = len(data), 0
            tar.addfile(info, io.BytesIO(data))
    runs_pin = dict(next(p for p in load_profile("agentops-bench-pilot").data["source"]["pins"] if p["role"] == "runs"))
    return {**runs_pin, **_pin(tmp / "traces.tar.gz", buf.getvalue(), "runs"), "doi": runs_pin["doi"]}


def _tasks_zip(tmp: Path, extra: dict[str, bytes] | None = None, name: str = "supp.zip") -> dict[str, Any]:
    """The task YAMLs as a zip with a fixed member timestamp, so the same members always give the same bytes."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, data in [*sorted(agentops_support.tasks_files().items()), *(extra or {}).items()]:
            archive.writestr(zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0)), data, zipfile.ZIP_DEFLATED)
    return _pin(tmp / name, buf.getvalue(), "tasks")


def _import(tmp: Path, runs: dict[str, Any], tasks: dict[str, Any]) -> tuple[Any, Path]:
    tree = ArchiveTree(tmp / runs["file"], pin=runs, sha256=runs["sha256"], size=runs["bytes"])
    context = ArchiveTree(tmp / tasks["file"], pin=tasks, sha256=tasks["sha256"], size=tasks["bytes"])
    with CorpusWriter(tmp / "c") as writer:
        report = import_source("agentops-bench", tree, corpus=writer, profile_id="agentops-bench-pilot",
                               part="pilot-v1-seeded", pin=runs, in_process=True, until="aer",
                               context_trees=[ContextTree("tasks", context, None, pin=tasks)])
    return report, tmp / "c.partial"


def test_an_archive_context_pin_is_stored_expanded_and_joins_each_unit(tmp_path):
    label = agentops_support.F["task_with_context"]
    runs = _runs_tar(tmp_path, [label])
    tasks = _tasks_zip(tmp_path, {"README.md": b"not a task\n", "src/harness.py": b"never read\n"})
    report, partial = _import(tmp_path, runs, tasks)
    assert report.exit_code == 0 and report.counters["mapped"] == 1
    (row,) = _jsonl(partial / "executions.jsonl")
    header = json.loads((partial / row["paths"]["aer"]).read_bytes().split(b"\n", 1)[0])
    assert header["ext"]["agentops"]["join"]["status"] == "joined"
    (task,) = [a for a in header["artifacts"] if a["role"] == "supporting"]
    assert task["origin"]["kind"] == "member" and task["origin"]["container"] == tasks["sha256"]
    assert task["origin"]["label"].startswith("tasks/")
    # the container is stored with the pin's origin; only the role's globs were decompressed (R-40)
    origins = _jsonl(partial / "raw" / "origins.jsonl")
    assert {"origin": {"doi": DOI, "file": "supp.zip", "kind": "zenodo"}, "sha256": "sha256:" + tasks["sha256"]} in origins
    members = {m["label"]: m["disposition"] for m in _jsonl(partial / "raw" / "members.jsonl")
               if str(m.get("container", "")).removeprefix("sha256:") == tasks["sha256"]}
    assert members["README.md"] == members["src/harness.py"] == "not_selected"
    assert {d for k, d in members.items() if k.startswith("tasks/")} == {"selected"}
    snapshot = json.loads((partial / "corpus.json").read_text("utf-8"))["sources"][0]["snapshots"][0]
    (ctx,) = snapshot["context"]
    assert ctx["role"] == "tasks" and ctx["pin"]["file"] == "supp.zip" and ctx["stored"] == len(agentops_support.tasks_files())
    assert ctx["input"] == {"kind": "archive", "label": "supp.zip", "bytes": tasks["bytes"], "sha256": "sha256:" + tasks["sha256"]}
    stages = json.loads((partial / "derivation.json").read_text("utf-8"))["stages"]
    assert sum(1 for s in stages if s["stage"] == "expand") == 2  # the runs tar and the context zip


def test_a_context_archive_whose_bytes_differ_from_its_pin_is_refused(tmp_path):
    runs = _runs_tar(tmp_path, [agentops_support.F["task_with_context"]])
    tasks = _tasks_zip(tmp_path)
    tasks_wrong = {**tasks, "sha256": "0" * 64}
    tree = ArchiveTree(tmp_path / runs["file"], pin=runs, sha256=runs["sha256"], size=runs["bytes"])
    context = ArchiveTree(tmp_path / tasks["file"], pin=tasks_wrong, sha256=tasks_wrong["sha256"], size=tasks["bytes"])
    with CorpusWriter(tmp_path / "c") as writer, pytest.raises(AgentProvError) as err:
        import_source("agentops-bench", tree, corpus=writer, profile_id="agentops-bench-pilot", part="pilot-v1-seeded",
                      pin=runs, in_process=True, until="aer", context_trees=[ContextTree("tasks", context, None)])
    # PR-4 (CB-20): refused by the store before publishing, so the swapped bytes never sit in the raw store under the
    # pin's origin
    assert err.value.code == "raw.object.mismatch"
    objects = tmp_path / "c.partial" / "raw" / "objects"
    assert not list(objects.rglob(tasks["sha256"] + ".*"))
    origins = tmp_path / "c.partial" / "raw" / "origins.jsonl"
    assert not origins.exists() or "supp.zip" not in origins.read_text("utf-8")


def test_a_corpus_with_an_archive_context_re_maps_identically(tmp_path, monkeypatch, capsys):
    """D-530 re-map: the recorded archive context (pin and stored container) is rebuilt from the corpus and expanded
    again; ``recompute --dry-run`` reports every execution and every corpus file identical."""
    from agentprov.cli.main import main

    labels = [agentops_support.F["task_with_context"], agentops_support.F["anthropic_payload"]]
    runs = _runs_tar(tmp_path, labels)
    tasks = _tasks_zip(tmp_path, {"README.md": b"not a task\n"})
    report, partial = _import(tmp_path, runs, tasks)
    assert report.exit_code == 0 and report.counters["mapped"] == 2
    monkeypatch.setenv("AGENTPROV_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("AGENTPROV_UPSTREAM_CACHE", raising=False)
    capsys.readouterr()
    code = main(["recompute", "--corpus", str(partial), "--dry-run", "--no-reuse", "--in-process", "--json", "--progress", "off"])
    summary = json.loads(capsys.readouterr().out)
    assert summary["refusal"] is None, summary["refusal"]
    assert summary["counters"]["unexplained_change"] == 0 and summary["counters"]["corpus_unexplained"] == 0, summary["notices"]
    assert summary["counters"]["identical"] == 2 and code == 0


def test_a_resume_with_other_per_unit_inputs_is_refused_nf25(tmp_path):
    """G4 (bug pass NF-25): a resumed snapshot must run with the context roles, pins, archive and pinned objects it
    recorded, or its units would mix joined and unjoined AERs; the same inputs resume."""
    from agentprov.adapters.runner.importer import IdentityRefusedError

    labels = [agentops_support.F["task_with_context"], agentops_support.F["anthropic_payload"]]
    runs = _runs_tar(tmp_path, labels)
    tasks = _tasks_zip(tmp_path)
    tree = ArchiveTree(tmp_path / runs["file"], pin=runs, sha256=runs["sha256"], size=runs["bytes"])

    def resume(contexts: list[ContextTree]) -> Any:
        with CorpusWriter(tmp_path / "c") as writer:
            return import_source("agentops-bench", tree, corpus=writer, profile_id="agentops-bench-pilot",
                                 part="pilot-v1-seeded", pin=runs, in_process=True, until="aer", context_trees=contexts)

    def context(pin: dict[str, Any]) -> ContextTree:
        return ContextTree("tasks", ArchiveTree(tmp_path / pin["file"], pin=pin, sha256=pin["sha256"], size=pin["bytes"]),
                           None, pin=pin)

    first = resume([context(tasks)])
    assert first.exit_code == 0 and first.counters["mapped"] == 2
    with pytest.raises(IdentityRefusedError):
        resume([])  # the context dropped
    other = _tasks_zip(tmp_path, {"README.md": b"another archive\n"}, name="other.zip")  # same role, another container
    with pytest.raises(IdentityRefusedError):
        resume([context(other)])
    again = resume([context(tasks)])
    assert again.exit_code == 0 and again.counters["skipped_resume"] == 2


def test_a_re_map_with_an_archive_context_absent_on_purpose_reports_unverified_pr5(tmp_path, monkeypatch, capsys):
    """PR-5 (BF-20, CB-6 for per-unit inputs): after the context archive is purged, ``recompute --dry-run`` and ``verify
    --level rederive`` used to end in exit 70 (KeyError) or ``corpus.rawtree.invalid``. The archive is now left out of
    the re-map, and the executions that needed it are reported unverified, not crashed or failed."""
    from agentprov.cli.main import main

    monkeypatch.setenv("AGENTPROV_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("AGENTPROV_UPSTREAM_CACHE", raising=False)
    labels = [agentops_support.F["task_with_context"], agentops_support.F["anthropic_payload"]]
    runs = _runs_tar(tmp_path, labels)
    tasks = _tasks_zip(tmp_path, {"README.md": b"not a task\n"})
    report, partial = _import(tmp_path, runs, tasks)
    assert report.exit_code == 0 and report.counters["mapped"] == 2

    def run(*argv: str) -> tuple[int, dict[str, Any]]:
        capsys.readouterr()
        code = main([*argv, "--json", "--progress", "off"])
        return code, json.loads(capsys.readouterr().out)

    capsys.readouterr()
    code = main(["purge", "sha256:" + tasks["sha256"], "--reason", "secret", "--corpus", str(partial), "--yes"])
    assert code == 0, capsys.readouterr().err[-400:]
    code, summary = run("recompute", "--corpus", str(partial), "--dry-run", "--no-reuse", "--in-process")
    assert summary["refusal"] is None, summary
    counters = summary["counters"]
    assert counters.get("unverified", 0) >= 1 and counters.get("unexplained_change", 0) == 0, summary
    assert counters.get("corpus_unexplained", 0) == 0 and code == 0, summary["notices"]  # RC-2: exit and corpus files too
    code, summary = run("verify", "--corpus", str(partial), "--level", "rederive", "--in-process")
    assert code == 0, summary
    # RC-13: a writing re-map records the role it re-mapped without (D-221 context_skipped), not silence
    out = tmp_path / "remapped"
    capsys.readouterr()
    code = main(["recompute", "--corpus", str(partial), "--out", str(out), "--no-reuse", "--in-process", "--progress", "off",
                 "-q"])
    snapshot = json.loads((out.with_name(out.name + ".partial") / "corpus.json").read_text("utf-8"))
    snapshot = snapshot["sources"][0]["snapshots"][0]
    assert snapshot.get("context_skipped") == ["tasks"], (code, snapshot.get("context"))
    assert not [c for c in snapshot.get("context") or () if c.get("role") == "tasks"]
