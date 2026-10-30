"""SEC-25: ``purge`` of a leaked credential (G.10 SEC-25; K.12.11; G.9.5, G.9.6; MN N.2.15; D-46; T-25).

A working corpus is imported (release mode, so that it could be sealed) from two synthetic AgentDojo logs; one tool output
carries a credential-shaped sentinel assembled at run time (no source file holds it whole). Then
``agentprov purge sha256:<object> --reason secret --corpus ... --yes`` runs end to end, with ``-vv`` and ``--log-file``.

* The object is gone; the tombstone row is exactly ``{date, reason, sha256}``; neither the tombstone file, the register,
  stdout, stderr nor the DEBUG log file holds the value or any 8-character fragment of it; the execution that cites the
  object gets ``release.withheld``.
* ``verify --level chain`` reports the object ``tombstoned`` (never missing), which fails release mode.
* A purged working corpus seals as a corpus version that withholds the object and the execution derived from it
  (``WITHHELD.json``; P-3, resolved by D-230..D-236): no sealed byte holds the value, and the execution's AER is renamed
  into the private sidecar ``DIR.withheld/`` (G.9.5: kept in the private store). The end-to-end purge -> re-version ->
  seal -> ``verify --release`` path is ``test_sec25_withholding.py``.
* Finding F-12C-05 (D-46 open item): a re-import of the same source after the purge stores the purged object again,
  beside its tombstone (``xfail(strict=True)``, routed to phase 12b).

The phase-11 tests (``tests/cli/test_purge_cmd.py``, ``tests/unit/corpus/test_purge.py``) cover usage, confirmation, the
dry run, idempotence, containers and the cache; here the input is a real import and the checks are the secret's.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import corpus_harness as harness
import pytest
from corpus_harness import verify

cli = harness.cli  # the corpus_harness fixtures, bound in this module so pytest finds them
sealed = harness.sealed

SECRET = "sk-" + "live-" + "SENTINEL" + "-" + "0123456789abcdefghij"
FRAGMENTS = [SECRET[i:i + 8] for i in range(len(SECRET) - 7)]


def _fragments_in(data: bytes | str) -> list[str]:
    text = data.decode("utf-8", "replace") if isinstance(data, bytes) else data
    return [f for f in FRAGMENTS if f in text]


def _import(inp: Path, corpus: Path) -> Any:
    import import_support as support
    import seal_support as ss

    from agentprov.adapters.runner.importer import LocalTree, import_source
    from agentprov.corpus.writer import CorpusWriter

    with CorpusWriter(corpus) as writer:
        return import_source("agentdojo", LocalTree(inp), corpus=writer, part="2024-06", workers=1, mode="release",
                             pin_check=support.vouch(inp), pin=ss.PIN)


@pytest.fixture(scope="module")
def leaked_template(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    import agentdojo_support as ad

    base = tmp_path_factory.mktemp("sec25-leaked")
    inp = base / "in"
    leaking = ad.base_log()
    leaking["messages"][3]["content"] = f"api key: {SECRET}"
    clean = ad.base_log(user_task_id="user_task_2")
    for doc in (leaking, clean):
        path = inp / ad.path_of(doc)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(ad.log_bytes(doc))
    corpus = base / "c"
    assert _import(inp, corpus).exit_code == 0
    leak = hashlib.sha256((inp / ad.path_of(leaking)).read_bytes()).hexdigest()
    rows = [json.loads(line) for line in (base / "c.partial" / "executions.jsonl").read_bytes().split(b"\n") if line]
    ex = next(r["ex"] for r in rows if r["raw"][0]["sha256"] == "sha256:" + leak)
    return {"inp": inp, "partial": base / "c.partial", "leak": leak, "ex": ex}


@pytest.fixture
def leaked(leaked_template: dict[str, Any], tmp_path: Path) -> dict[str, Any]:
    """A fresh copy of the working corpus (``<tmp>/c.partial``) for each test."""
    import shutil

    partial = tmp_path / "c.partial"
    shutil.copytree(leaked_template["partial"], partial, symlinks=True)
    return {**leaked_template, "corpus": tmp_path / "c", "partial": partial}


def _object(partial: Path, sha: str) -> list[Path]:
    return list((partial / "raw" / "objects" / sha[:2]).glob(sha + ".*"))


def _purge(cli: Any, leaked: dict[str, Any], tmp_path: Path) -> Any:
    log = tmp_path / "purge.log"
    run = cli("-vv", "--log-file", str(log), "purge", "sha256:" + leaked["leak"], "--reason", "secret", "--corpus",
              str(leaked["corpus"]), "--yes", "--json")
    return run, log


def test_sec25_the_leak_is_stored_before_the_purge(leaked):
    """Control: the sentinel really is in the raw store and the AER before the purge."""
    (stored,) = _object(leaked["partial"], leaked["leak"])
    assert SECRET.encode() in stored.read_bytes()


def test_sec25_purge_removes_the_object_and_leaves_a_tombstone_without_the_value(cli, leaked, tmp_path):
    run, log = _purge(cli, leaked, tmp_path)
    assert run.code == 0, run.err
    assert run.json()["counters"] == {"executions_withheld": 1, "objects_removed": 1, "tombstones_written": 1}
    partial = leaked["partial"]
    assert _object(partial, leaked["leak"]) == []
    tombstones = (partial / "raw" / "tombstones.jsonl").read_bytes()
    (row,) = [json.loads(line) for line in tombstones.split(b"\n") if line]
    assert set(row) == {"date", "reason", "sha256"} and row["reason"] == "secret"
    assert row["sha256"] == "sha256:" + leaked["leak"]
    register = (partial / "register.jsonl").read_bytes()
    withheld = [json.loads(line) for line in register.split(b"\n") if line and b"release.withheld" in line]
    assert [e["subject"].get("ex") for e in withheld] == [leaked["ex"]]
    for surface, data in (("tombstones", tombstones), ("register", register), ("stdout", run.out), ("stderr", run.err),
                          ("log file", log.read_bytes())):
        assert _fragments_in(data) == [], surface
    assert log.stat().st_size > 0  # the DEBUG log was written, and still holds no fragment


def test_sec25_verify_reports_the_purged_object_as_tombstoned_never_as_missing(cli, leaked, tmp_path):
    assert _purge(cli, leaked, tmp_path)[0].code == 0
    run = verify(cli, leaked["corpus"], "--level", "chain")
    found = run.codes()
    assert found.get("raw.tombstoned") == 1 and "raw.object.missing" not in found
    failure = next(f for f in run.json()["failures"] if f["code"] == "raw.tombstoned")
    assert failure["detail"].startswith("tombstoned: purged ") and "(secret)" in failure["detail"]
    assert _fragments_in(run.out + run.err) == []


def test_sec25_a_purged_working_corpus_seals_with_the_value_withheld_so_it_never_reaches_a_release(cli, leaked, tmp_path):
    """P-3 resolved: sealing withholds the purged object and its execution instead of refusing (before D-230 the seal
    failed ``raw.tombstoned``). No sealed file holds a fragment; the private sidecar keeps the AER."""
    import seal_support as ss

    from agentprov.corpus.package import seal

    assert _purge(cli, leaked, tmp_path)[0].code == 0
    report = seal(leaked["corpus"], corpus_version="0.1.0", inputs=ss.inputs())
    assert report.counters["withheld_objects"] == 1 and report.counters["withheld_executions"] == 1
    sealed_files = [p for p in leaked["corpus"].rglob("*") if p.is_file()]
    # fragments that are hex only also occur in the test producer commit (0123456789abcdef...): not evidence of the value
    distinct = [f for f in FRAGMENTS if set(f) - set("0123456789abcdef")]
    holding = {p.name: n for p in sealed_files if (n := sum(1 for f in distinct if f.encode() in p.read_bytes()))}
    assert sealed_files and holding == {}, holding  # file names and counts only, never a fragment
    sidecar = leaked["corpus"].with_name("c.withheld")
    assert any(_fragments_in(p.read_bytes()) for p in sidecar.rglob("*.aer.jsonl"))
    assert _fragments_in(repr(report)) == []


def test_sec25_a_sealed_corpus_is_never_purged(cli, sealed):
    """Control on the sealed side (G.9.6): a sealed corpus is refused (exit 4) and unchanged."""
    from agentprov.testing import fs_guard

    target = sorted(p.name.split(".")[0] for p in (sealed / "raw" / "objects").rglob("*") if p.is_file())[0]
    with fs_guard.unchanged(sealed):
        run = cli("purge", "sha256:" + target, "--reason", "secret", "--corpus", str(sealed), "--yes")
    assert run.code == 4



def test_sec25_a_reimport_never_stores_a_tombstoned_object_again(cli, leaked, tmp_path):
    """F-12C-05. After the purge, ``import`` of the same input into the same working corpus (a resume: both executions
    are ``skipped_resume``) writes the purged object back into the raw store. Expected: a tombstoned digest is never
    stored again (G.9.6; D-46 "blocking tombstoned digests at ingest", moved to phase 12); the candidate is registered
    instead. Was: the object, with the credential, came back. Fixed in phase 12b (D-61): the raw store never publishes a
    digest listed in its ``tombstones.jsonl``."""
    assert _purge(cli, leaked, tmp_path)[0].code == 0
    report = _import(leaked["inp"], leaked["corpus"])
    assert report.counters["skipped_resume"] == 2
    assert _object(leaked["partial"], leaked["leak"]) == []
