"""D-935: a stored PROV-JSON document is parsed under its own size limit (256 MiB, not the 64 MiB raw-input limit), and a
source profile may raise its prov and validate jobs' memory cap (``[import] prov_rss_bytes``). Neither changes a byte."""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

import import_support as support
import pytest

import agentprov.validate.prov as vprov
from agentprov.adapters.profiles import ProfileError, _check_import, load_profile, worker_caps
from agentprov.adapters.runner.importer import LocalTree, import_source
from agentprov.cli.checks import _validate_limits
from agentprov.corpus.writer import CorpusWriter
from agentprov.ingest.limits import MIB, PROV_DOCUMENT_JSON_BYTES, IngestLimits, prov_document_limits
from agentprov.ingest.loaders import strict_json_loads
from agentprov.io.workers import RSS_CAP_CEILING, WorkerLimits

GIB = 1 << 30


def test_the_prov_document_limit_is_256_mib_and_raise_only() -> None:
    assert PROV_DOCUMENT_JSON_BYTES == 256 * MIB
    assert prov_document_limits().max_json_bytes == 256 * MIB
    assert prov_document_limits(IngestLimits(max_json_bytes=512 * MIB)).max_json_bytes == 512 * MIB
    assert prov_document_limits(IngestLimits(max_json_depth=7)).max_json_depth == 7  # every other limit is kept
    assert IngestLimits().max_json_bytes == 64 * MIB  # raw input is unchanged


def test_a_document_over_64_mib_parses_under_the_prov_limit_only() -> None:
    doc = b'{"entity": "' + b"x" * (64 * MIB + 1) + b'"}'
    with pytest.raises(Exception):  # noqa: B017, PT011 - the raw-input limit refuses it (ingest.size.file)
        strict_json_loads(doc)
    assert len(strict_json_loads(doc, prov_document_limits())["entity"]) == 64 * MIB + 1


def test_the_validator_parses_prov_under_the_prov_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[Any] = []

    def spy(data: Any, limits: Any = None, **kw: Any) -> Any:
        seen.append(limits)
        raise ValueError("stop")

    monkeypatch.setattr(vprov, "strict_json_loads", spy)
    report = vprov.validate_prov(b"{}", aer=None)  # type: ignore[arg-type]
    assert seen and seen[0].max_json_bytes == PROV_DOCUMENT_JSON_BYTES
    assert [o.id for o in report.outcomes] == ["pv.prov_structure.document"]


@pytest.mark.parametrize("cap", [WorkerLimits().for_kind("prov").rss_bytes, 16 * GIB])
def test_a_prov_cap_from_the_prov_default_to_the_ceiling_is_accepted(cap: int) -> None:
    _check_import({"dialect": "d", "mapper": "m", "prov_rss_bytes": cap}, "p", ["head"])


@pytest.mark.parametrize("cap", [2 * GIB, RSS_CAP_CEILING + 1, True, "16 GiB"])
def test_a_lower_larger_or_non_integer_prov_cap_is_refused(cap: Any) -> None:
    with pytest.raises(ProfileError, match="prov_rss_bytes"):
        _check_import({"dialect": "d", "mapper": "m", "prov_rss_bytes": cap}, "p", ["head"])


def _with(profile_id: str, **imp: int) -> Any:
    profile = load_profile(profile_id)
    return dataclasses.replace(profile, data={**profile.data, "import": {**profile.data["import"], **imp}})


def test_worker_caps_by_kind() -> None:
    assert worker_caps(load_profile("agentdojo-upstream")) == {}
    caps = worker_caps(_with("agentdojo-upstream", map_rss_bytes=4 * GIB, prov_rss_bytes=16 * GIB))
    assert caps == {"map": 4 * GIB, "prov": 16 * GIB, "validate": 16 * GIB}


def test_the_validate_cli_reads_the_cap_of_the_recorded_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    import agentprov.adapters.profiles as profiles

    assert _validate_limits({"sources": [{"profile": {"id": "agentdojo-upstream", "version": 2}}]}) is None
    capped = _with("agentdojo-upstream", prov_rss_bytes=16 * GIB)
    monkeypatch.setattr(profiles, "load_profile", lambda *_a, **_k: capped)
    limits = _validate_limits({"sources": [{"profile": {"id": "agentdojo-upstream", "version": 2}}]})
    assert limits.for_kind("validate").rss_bytes == 16 * GIB
    assert _validate_limits({"sources": [{"profile": "not-a-table"}]}) is None


def test_the_cap_rides_on_every_prov_job_and_changes_no_byte(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import agentprov.adapters.runner.importer as importer
    from agentprov.io.workers import WorkerPool

    support.require_golden()
    for cap in (None, 16 * GIB):
        profile = _with("agentdojo-upstream", **({} if cap is None else {"prov_rss_bytes": cap}))
        monkeypatch.setattr(importer, "load_profile", lambda *_a, _p=profile, **_k: _p)
        jobs: list[Any] = []
        run = WorkerPool.run

        def spy(self: WorkerPool, batch: Any, *a: Any, _jobs: list[Any] = jobs, _run: Any = run, **k: Any) -> Any:
            batch = list(batch)
            _jobs.extend(j for j in batch if j.kind == "prov")
            return _run(self, batch, *a, **k)

        monkeypatch.setattr(WorkerPool, "run", spy)
        root, out = tmp_path / f"in{cap}", tmp_path / f"c{cap}"
        support.agentdojo_tree(root, count=2)
        with CorpusWriter(out) as corpus:
            import_source("agentdojo", LocalTree(root), corpus=corpus, profile_id="agentdojo-upstream",
                               part="2024-06", until="validation", in_process=True, pin_check=support.vouch(root))
        prov = b"".join(p.read_bytes() for p in sorted(Path(f"{out}.partial").glob("prov/*/*/*.prov.json")))
        assert jobs and prov
        if cap is None:
            assert all(j.limits is None for j in jobs)
            plain = prov
        else:
            assert all(j.limits.for_kind("prov").rss_bytes == cap for j in jobs)
            assert prov == plain  # worker limits enter no digest
        monkeypatch.undo()


def test_derive_reads_the_cap_of_the_recorded_profile_through_its_catalogues(monkeypatch: pytest.MonkeyPatch) -> None:
    import agentprov.adapters.profiles as profiles
    from agentprov.cli.derive import catalogues
    from agentprov.corpus.derive import PROV_CAP, Derivation

    assert catalogues().worker_caps("agentdojo-upstream", 2) == {}
    monkeypatch.setattr(profiles, "load_profile", lambda *_a, **_k: _with("agentdojo-upstream", prov_rss_bytes=16 * GIB))
    cats = catalogues()
    assert cats.worker_caps("agentdojo-upstream", 2)["prov"] == 16 * GIB

    class Fake:  # only what _prov_cap reads
        src_stages: Any
        catalogues = cats

    fake = Fake()
    fake.src_stages = {"aer": {"name": "aer", "profile": "agentdojo-upstream@2"}}
    assert Derivation._prov_cap(fake) == 16 * GIB  # type: ignore[arg-type]
    fake.src_stages = {}
    assert Derivation._prov_cap(fake) == PROV_CAP  # type: ignore[arg-type]
