"""D-550: the tier-4 round-trip cache never changes an outcome.

``validate --corpus`` gives the same report bytes with the cache off, cold and warm, in process and with workers
(``jobs`` 1 and 3), in both modes. A cache made by one path serves the other. An entry that is corrupt, partial, made
under another context, made for other bytes or of another shape is a miss: it is removed, never an error, never a
verdict. A round trip that did not complete is never stored. ``audit`` (``--release``) serves nothing and detects a
forged entry. The size bound evicts the least recently used entries, and concurrent writers leave whole entries.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path
from typing import Any

import pytest
import verify_support as vs

from agentprov.corpus.reader import CorpusReader
from agentprov.corpus.validation import validate_corpus
from agentprov.io.canonical import jcs_bytes
from agentprov.validate import cache as tc
from agentprov.validate import roundtrip
from agentprov.validate.cache import DiskCache, JobFidelity
from agentprov.validate.tiers import CheckOutcome, Finding

SPEC = "agentprov-prov/0.1"


def report_bytes(root: Path, **kwargs: Any) -> bytes:
    outcome = validate_corpus(CorpusReader.open(root), **kwargs)
    return json.dumps(outcome.report({"corpus_id": "x"}), sort_keys=True, indent=2, ensure_ascii=False).encode("utf-8")


def entries(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.json") if ".tmp-" not in p.name)


def prov_docs(root: Path) -> list[bytes]:
    reader = CorpusReader.open(root)
    return [reader.prov_bytes(row, SPEC) for row in reader.index()]


@pytest.mark.parametrize("mode", ["dev", "release"])
@pytest.mark.parametrize("jobs", [None, 1, 3])
def test_off_cold_and_warm_give_the_same_report(sealed: Path, tmp_path: Path, mode: str, jobs: int | None) -> None:
    off = report_bytes(sealed, mode=mode, jobs=jobs)
    cache = DiskCache(tmp_path / "c")
    assert report_bytes(sealed, mode=mode, jobs=jobs, cache=cache) == off
    assert cache.stats.stored == 3 and cache.stats.hits == 0
    assert len(entries(tmp_path / "c")) == 3
    warm = DiskCache(tmp_path / "c")
    assert report_bytes(sealed, mode=mode, jobs=jobs, cache=warm) == off
    assert warm.stats.hits == 3 and warm.stats.stored == 0 and warm.stats.rejected == 0


def test_a_cache_made_in_process_serves_the_jobs_and_back(sealed: Path, tmp_path: Path) -> None:
    off = report_bytes(sealed, mode="release")
    report_bytes(sealed, mode="release", cache=DiskCache(tmp_path / "a"))
    pooled = DiskCache(tmp_path / "a")
    assert report_bytes(sealed, mode="release", jobs=2, cache=pooled) == off
    assert pooled.stats.hits == 3
    report_bytes(sealed, mode="release", jobs=2, cache=DiskCache(tmp_path / "b"))
    local = DiskCache(tmp_path / "b")
    assert report_bytes(sealed, mode="release", cache=local) == off
    assert local.stats.hits == 3


def test_a_staged_hint_lowers_the_memory_charge_only(sealed: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """D-554 with D-550: a job whose cache hint is staged is charged at the cache-hit slope; the report is unchanged."""
    from agentprov.corpus import validation

    hits: list[str | None] = []
    real = validation.prov_charge

    def spy(prov_bytes: int, *, hit: str | None = None, cap: int | None = None) -> int:
        hits.append(hit)
        return real(prov_bytes, hit=hit, cap=cap)

    monkeypatch.setattr(validation, "prov_charge", spy)
    off = report_bytes(sealed, mode="dev", jobs=2)
    assert hits == [None] * 3
    hits.clear()
    assert report_bytes(sealed, mode="dev", jobs=2, cache=DiskCache(tmp_path / "c")) == off
    assert hits == [None] * 3  # cold: no hint is staged
    hits.clear()
    assert report_bytes(sealed, mode="dev", jobs=2, cache=DiskCache(tmp_path / "c")) == off
    assert hits == ["validate"] * 3


def test_a_tampered_document_is_not_served_its_old_entry(sealed: Path, tmp_path: Path) -> None:
    cache = DiskCache(tmp_path / "c")
    report_bytes(sealed, mode="release", cache=cache)
    prov = vs.first_file(sealed, "prov")
    prov.chmod(0o644)
    prov.write_bytes(prov.read_bytes() + b" ")
    off = report_bytes(sealed, mode="release")
    for jobs in (None, 2):
        assert report_bytes(sealed, mode="release", jobs=jobs, cache=DiskCache(tmp_path / "c")) == off


def _corruptions(data: bytes, doc: str) -> dict[str, bytes]:
    entry = json.loads(data)
    other = dict(entry, context={**entry["context"], "agentprov_code_sha256": "0" * 64})
    wrong_doc = dict(entry, doc_sha256="f" * 64)
    flipped = json.loads(data)
    flipped["outcomes"][0]["status"] = "fail"  # the outcomes digest no longer matches
    shape = dict(entry, outcomes=entry["outcomes"][:2])
    shape["outcomes_sha256"] = hashlib.sha256(jcs_bytes(shape["outcomes"])).hexdigest()
    skipped = json.loads(data)
    skipped["outcomes"][1] = {"check": "pv.roundtrip.graphs", "findings": [], "reason": "x", "status": "skipped"}
    skipped["outcomes_sha256"] = hashlib.sha256(jcs_bytes(skipped["outcomes"])).hexdigest()
    return {
        "empty": b"", "truncated": data[: len(data) // 2], "garbage": b"\x00\xff not json", "array": b"[]",
        "other context": jcs_bytes(other), "other document": jcs_bytes(wrong_doc), "flipped": jcs_bytes(flipped),
        "missing checks": jcs_bytes(shape), "skipped": jcs_bytes(skipped),
        "format": jcs_bytes(dict(entry, format="agentprov-tier4-cache/0")), "huge": b" " * (tc.MAX_ENTRY_BYTES + 1),
    }


@pytest.mark.parametrize("jobs", [None, 2])
def test_bad_entries_are_misses_and_are_removed(sealed: Path, tmp_path: Path, jobs: int | None) -> None:
    off = report_bytes(sealed, mode="release")
    root = tmp_path / "c"
    report_bytes(sealed, mode="release", cache=DiskCache(root))
    path = entries(root)[0]
    good = path.read_bytes()
    for name, bad in _corruptions(good, path.stem).items():
        path.write_bytes(bad)
        cache = DiskCache(root)
        assert report_bytes(sealed, mode="release", jobs=jobs, cache=cache) == off, name
        assert cache.stats.rejected == 1 and cache.stats.hits == 2 and cache.stats.stored == 1, name
        assert path.read_bytes() != bad, name  # removed, then written again from the fresh round trip


def test_a_forged_entry_is_served_but_audit_finds_and_replaces_it(sealed: Path, tmp_path: Path) -> None:
    """The trust model: an entry with the right context and digests is believed (the cache is as trusted as the local
    corpora). ``audit`` (what ``--release`` uses) never serves one; it compares and replaces."""
    off = report_bytes(sealed, mode="release")
    root = tmp_path / "c"
    report_bytes(sealed, mode="release", cache=DiskCache(root))
    path = entries(root)[0]
    entry = json.loads(path.read_bytes())
    entry["outcomes"][0] = {"check": "pv.roundtrip.model_equality", "findings": [
        {"code": "pv.roundtrip.model_differs", "detail": "forged", "where": "document"}], "status": "fail"}
    entry["outcomes_sha256"] = hashlib.sha256(jcs_bytes(entry["outcomes"])).hexdigest()
    path.write_bytes(jcs_bytes(entry))
    assert report_bytes(sealed, mode="release", cache=DiskCache(root)) != off  # believed
    audit = DiskCache(root, audit=True)
    assert report_bytes(sealed, mode="release", cache=audit) == off
    assert audit.stats.hits == 0 and audit.stats.audited == 3 and audit.stats.audit_mismatch == 1
    assert report_bytes(sealed, mode="release", cache=DiskCache(root)) == off  # replaced


def test_an_incomplete_round_trip_is_never_stored(sealed: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def out_of_memory(text: str, fmt: str, **kw: Any) -> Any:
        raise MemoryError

    monkeypatch.setattr(roundtrip, "_load", out_of_memory)
    cache = DiskCache(tmp_path / "c")
    report = json.loads(report_bytes(sealed, mode="release", cache=cache))
    assert report["counters"]["failed"] == 3
    assert cache.stats.stored == 0 and cache.stats.unstorable == 3 and not entries(tmp_path / "c")


def test_the_round_trip_off_never_touches_the_cache(sealed: Path, tmp_path: Path) -> None:
    from agentprov.aer.reader import load_aer_bytes
    from agentprov.validate import validate_prov

    reader = CorpusReader.open(sealed)
    row = reader.index()[0]
    aer = load_aer_bytes(reader.aer_bytes(row), verify=True)
    cache = DiskCache(tmp_path / "c")
    report = validate_prov(reader.prov_bytes(row, SPEC), aer, roundtrip=False, fidelity=cache)
    assert {o.status for o in report.outcomes if o.id.startswith("pv.roundtrip.")} == {"skipped"}
    assert cache.stats.as_json() == tc.CacheStats().as_json() and not (tmp_path / "c").exists()


def test_a_job_hint_is_used_only_for_its_document_and_context(sealed: Path, tmp_path: Path,
                                                               monkeypatch: pytest.MonkeyPatch) -> None:
    docs = prov_docs(sealed)
    cache = DiskCache(tmp_path / "c")
    report_bytes(sealed, mode="release", cache=cache)
    first = hashlib.sha256(docs[0]).hexdigest()
    hint = cache.hint(first)
    assert hint is not None
    assert JobFidelity(hint).lookup(docs[0]) is not None
    assert JobFidelity(hint).lookup(docs[1]) is None
    assert JobFidelity(b"{").lookup(docs[0]) is None
    monkeypatch.setattr(tc, "context_digest", lambda: "0" * 64)
    assert JobFidelity(hint).lookup(docs[0]) is None


def test_outcomes_survive_the_entry_exactly() -> None:
    outcomes = [CheckOutcome("pv.roundtrip.model_equality", "fail", (Finding("pv.roundtrip.model_differs", "b", "x"),),
                             reason="r", truncated=4),
                CheckOutcome("pv.roundtrip.graphs", "pass"), CheckOutcome("pv.roundtrip.completeness", "pass"),
                CheckOutcome("pv.roundtrip.datatypes", "pass"),
                CheckOutcome("pv.roundtrip.unqualified_layer", "not_applicable", reason="n")]
    assert tc.from_json(json.loads(json.dumps(tc.to_json(outcomes)))) == outcomes
    assert tc.storable(outcomes)
    load = [CheckOutcome(o.id, "fail", (Finding("pv.roundtrip.load", "document", "MemoryError"),)) for o in outcomes]
    assert not tc.storable(load) and not tc.storable(outcomes[:4]) and not tc.storable(outcomes[::-1])


def test_eviction_keeps_the_most_recently_used_within_the_bound(sealed: Path, tmp_path: Path) -> None:
    root = tmp_path / "c"
    report_bytes(sealed, mode="release", cache=DiskCache(root))
    paths = entries(root)
    for n, path in enumerate(paths):
        os.utime(path, (time.time() - 1000 + n, time.time() - 1000 + n))
    stale = paths[0].with_name(paths[0].name + ".tmp-1-abc")
    stale.write_bytes(b"partial")
    os.utime(stale, (time.time() - 7200, time.time() - 7200))
    keep = paths[-1].stat().st_size
    result = DiskCache(root).evict(keep)
    assert result["bytes_after"] <= keep and entries(root) == [paths[-1]] and not stale.exists()
    DiskCache(root).evict(0)
    assert not root.exists() or not any(root.iterdir())


def test_concurrent_writers_leave_whole_entries(sealed: Path, tmp_path: Path) -> None:
    root = tmp_path / "c"
    report_bytes(sealed, mode="release", cache=DiskCache(root))
    path = entries(root)[0]
    good = path.read_bytes()
    doc = path.stem
    outcomes = tc.from_json(json.loads(good)["outcomes"])
    assert outcomes is not None
    path.unlink()
    errors: list[BaseException] = []

    def write() -> None:
        try:
            for _ in range(20):
                DiskCache(root)._store(doc, outcomes)
                assert DiskCache(root)._read(doc) is not None or not path.exists()
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=write) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert DiskCache(root)._read(doc) == outcomes
    assert not [p for p in root.rglob("*") if ".tmp-" in p.name]


def test_the_cli_switch_and_the_release_audit(cli, sealed: Path, tmp_path: Path) -> None:
    home = Path(os.environ["AGENTPROV_HOME"])
    root = home / "cache" / "tier4"
    off = cli("validate", "--corpus", str(sealed), "--strict", "--report", "-", "--no-validation-cache")
    assert off.code == 0 and not root.exists()
    cold = cli("validate", "--corpus", str(sealed), "--strict", "--report", "-")
    warm = cli("validate", "--corpus", str(sealed), "--strict", "--report", "-", "--jobs", "2")
    assert cold.out == warm.out == off.out and len(entries(root)) == 3
    assert "stored 3" in cold.err and "hits 3" in warm.err
    release_off = cli("validate", "--corpus", str(sealed), "--release", "--report", "-", "--no-validation-cache")
    audit = cli("validate", "--corpus", str(sealed), "--release", "--report", "-")
    assert audit.out == release_off.out and audit.code == release_off.code
    assert "(audit)" in audit.err and "audited 3" in audit.err and "hits" not in audit.err
