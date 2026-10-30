"""Runner fixes of core review D, routing RD-3 (findings CD-5..CD-9; ``adapters/runner/importer.py``).

Archive inputs are built here from synthetic Inspect logs (``inspect_support``; no real sample, no fixture file) and
imported in process into a corpus under ``tmp_path``.
"""

from __future__ import annotations

import hashlib
import io
import json
import sys
import zipfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from agentprov.adapters.runner.importer import ArchiveTree, import_source
from agentprov.corpus.writer import CorpusWriter

_TESTS = Path(__file__).resolve().parents[2]
if str(_TESTS / "adapters" / "inspect") not in sys.path:
    sys.path.insert(0, str(_TESTS / "adapters" / "inspect"))
import inspect_support as insp  # noqa: E402

SOURCE, PROFILE, PART = "agent-security-tools-survey", "survey-agentharm", "agentharm"
LOGS = "agentharm/results/m"


def _eval(n: int, samples: Mapping[str, dict[str, Any]] | None = None) -> bytes:
    """A synthetic Inspect log whose header ids make its bytes distinct; ``samples`` defaults to one sample ``s<n>``."""
    header = insp.synthetic_header()
    header["eval"]["eval_id"] = f"SyntheticEvalId{n:08d}"
    header["eval"]["run_id"] = f"SyntheticRunId{n:09d}"
    if samples is None:
        sample = insp.basic_sample(f"s{n}")
        sample["uuid"] = f"SynthUuid{n:013d}"
        samples = {f"s{n}_epoch_1.json": sample}
    return insp.build_eval(header, dict(samples))


def _shared_sample() -> dict[str, Any]:
    sample = insp.basic_sample("s0")
    sample["uuid"] = "SynthUuid0000000000000"
    return sample


def _zip(members: Mapping[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        for name, data in members.items():
            info = zipfile.ZipInfo(name, (2026, 6, 10, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, data)
    return buf.getvalue()


def _archive(root: Path, members: Mapping[str, bytes]) -> tuple[dict[str, Any], ArchiveTree]:
    data = _zip(members)
    root.mkdir(parents=True, exist_ok=True)
    (root / "logs.zip").write_bytes(data)
    sha = hashlib.sha256(data).hexdigest()
    pin = {"role": "fixture", "kind": "zenodo", "doi": "10.5281/zenodo.7", "record": 7, "file": "logs.zip",
           "sha256": sha, "bytes": len(data)}
    return pin, ArchiveTree(root / "logs.zip", pin=pin, sha256=sha, size=len(data))


def _import(tmp_path: Path, members: Mapping[str, bytes], corpus: Path | None = None, **kwargs: Any) -> Any:
    pin, tree = _archive(tmp_path / "in", members)
    with CorpusWriter(corpus or tmp_path / "corpus") as writer:
        return import_source(SOURCE, tree, corpus=writer, profile_id=PROFILE, part=PART, pin=pin, in_process=True,
                             until="aer", **kwargs)


def _register(corpus: Path) -> list[dict[str, Any]]:
    path = corpus / "register.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def _index(corpus: Path) -> list[dict[str, Any]]:
    path = corpus / "executions.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


# ------------------------------------------------------------------------------------------------ CD-5
def test_a_member_byte_identical_to_one_already_selected_in_the_run_collapses(tmp_path):
    """Two different containers holding one byte-identical sample member (an eval-retry reusing a sample): the later
    copy is ``dedup.collapsed`` (H.7.2, D-385) and mapped once, never a second ``ex`` that crashes the index flush."""
    shared = {"s0_epoch_1.json": _shared_sample()}
    report = _import(tmp_path, {f"{LOGS}/a.eval": _eval(1, shared), f"{LOGS}/b.eval": _eval(2, shared)})
    assert report.exit_code == 0, report.counters
    assert report.counters["mapped"] == 1 and report.counters["duplicates"] == 1
    collapsed = [e for e in report.register if e["code"] == "dedup.collapsed"]
    assert len(collapsed) == 1 and collapsed[0]["subject"]["path"].endswith("b.eval!/samples/s0_epoch_1.json")


# ------------------------------------------------------------------------------------------------ CD-6
def _header_only() -> bytes:
    """An Inspect log of a run that errored before any sample: an in-band header and no samples/* member."""
    header = insp.synthetic_header()
    header["eval"]["eval_id"] = "SyntheticEvalId99999999"
    header["status"] = "error"
    return insp.build_eval(header, {})


def test_a_container_that_yields_no_execution_gets_a_disposition(tmp_path):
    """H.6.1 R1: every candidate has exactly one disposition. A container with no selected member, or whose plan has
    no unit and no row, is registered ``select.not_execution_artefact`` instead of vanishing from the accounting."""
    no_member = _zip({"notes/readme.txt": b"not a log\n"})
    for name, data in (("empty.eval", no_member), ("errored.eval", _header_only())):
        corpus = tmp_path / name / "corpus"
        report = _import(tmp_path / name, {f"{LOGS}/a.eval": _eval(1), f"{LOGS}/{name}": data}, corpus=corpus)
        assert report.exit_code == 0 and report.counters["mapped"] == 1, report.counters
        mine = [e for e in report.register if e["subject"].get("path", "").endswith(f"/{name}")]
        assert [(e["code"], e["disposition"]) for e in mine] == [("select.not_execution_artefact", "not_imported")], name


# ------------------------------------------------------------------------------------------------ CD-7
def test_with_a_limit_the_raw_store_does_not_depend_on_the_batch_size(tmp_path):
    """D.2.9 item 9: outputs are byte-identical for any batch size, ``--limit`` included. A container is stored and
    expanded only if the limit was not reached before it."""
    members = {f"{LOGS}/{k}.eval": _eval(k) for k in range(3)}
    outputs = {}
    for size in (1, 256):
        report = _import(tmp_path / f"b{size}", members, corpus=tmp_path / f"b{size}" / "corpus", limit=1, batch_size=size)
        assert report.counters["mapped"] == 1
        root = Path(report.corpus_root)
        outputs[size] = {f: (root / f).read_bytes() for f in ("raw/members.jsonl", "raw/origins.jsonl", "executions.jsonl")}
    assert outputs[1] == outputs[256]


# ------------------------------------------------------------------------------------------------ CD-8
def test_a_listing_pin_is_checked_over_the_listing_not_the_include_path_subset(tmp_path):
    """J.1.4: the listing digest covers the pinned tree. ``include_paths`` narrows what is imported, not what the pin is
    checked against, so a byte-exact pinned file is never ``raw.origin.blob_mismatch`` under a filter."""
    from agentprov.adapters.profiles import load_profile
    from agentprov.adapters.registry import READERS
    from agentprov.adapters.runner import resolve_factory
    from agentprov.adapters.runner.importer import ImportFilters, LocalTree, PinCheck, listing_sha256

    root = tmp_path / "tree"
    files = {"m/prov/a/x.transcript.json": b"{}", "m/prov/b/y.transcript.json": b"[]"}
    for rel, data in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(data)
    pin = {"role": "release", "kind": "git", "repo": "https://github.com/nickjones39/agentdojo-prov",
           "commit": "579a908354b93361efe0905ffb7623256aa96a06", "tree": "corpus/corpus-prov", "expected_files": 2,
           "listing_sha256": listing_sha256([(k, hashlib.sha256(v).hexdigest()) for k, v in files.items()])}
    profile = load_profile("adprov-v1")
    hook = resolve_factory(READERS[str(profile.data["import"]["dialect"])])().listing_origin
    check = PinCheck("listing", pin, listing_origin=hook)
    with CorpusWriter(tmp_path / "corpus") as writer:
        report = import_source("adprov", LocalTree(root), corpus=writer, profile_id="adprov-v1", part="release", pin=pin,
                               pin_check=check, filters=ImportFilters(include_paths=("m/prov/a/*",)), in_process=True,
                               until="aer")
    assert check.listing_ok
    assert [e for e in report.register if e["code"] == "raw.origin.blob_mismatch"] == []


# ------------------------------------------------------------------------------------------------ CD-9
def test_a_resumed_container_drops_its_stale_failure_entries(tmp_path, monkeypatch):
    """A container whose plan job failed (a transient worker limit) has no index row, so the next run on the same
    working corpus maps it again. Its earlier ``map.adapter_defect`` / ``worker.limit.*`` entries must not survive the
    success; a run that fails again records them again."""
    import agentprov.adapters.runner as runner_pkg
    from agentprov.io.workers import WorkerLimitError

    members = {f"{LOGS}/a.eval": _eval(1)}
    corpus = tmp_path / "corpus"
    original = runner_pkg._job_map_container

    def stopped(ctx: Any, limits: Any) -> Any:
        raise WorkerLimitError("wall")

    monkeypatch.setattr(runner_pkg, "_job_map_container", stopped)
    first = _import(tmp_path / "run1", members, corpus=corpus)
    assert first.exit_code != 0 and {e["code"] for e in first.register} >= {"map.adapter_defect"}
    monkeypatch.setattr(runner_pkg, "_job_map_container", original)
    second = _import(tmp_path / "run2", members, corpus=corpus)
    assert second.exit_code == 0 and second.counters["mapped"] == 1
    stale = [e for e in _register(Path(second.corpus_root)) if e["code"] == "map.adapter_defect"
             or e["code"].startswith("worker.limit.")]
    assert stale == []
