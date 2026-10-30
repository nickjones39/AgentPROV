"""Fixtures for the CLI tests (MN N.6; K.15).

``cli`` runs ``agentprov.cli.main.main`` in-process and returns exit code, stdout and stderr. ``host_probe`` replaces the
host probe of ``info`` (which would spawn the calibration worker) with a canned answer. ``valid_aer`` writes a valid,
sealed AER file and points the validator's catalogue loader at the synthetic ``tst`` catalogue those fixtures cite (the
adapter families that ship real catalogues do not exist yet).
"""

from __future__ import annotations

import dataclasses
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple

import pytest

_AER_TESTS = Path(__file__).resolve().parents[1] / "unit" / "aer"
if str(_AER_TESTS) not in sys.path:
    sys.path.insert(0, str(_AER_TESTS))

SCHEMA_PATH = Path(__file__).resolve().parent / "schemas" / "cli-summary-0.1.schema.json"


class Run(NamedTuple):
    code: int
    out: str
    err: str

    def json(self) -> Any:
        return json.loads(self.out)


@pytest.fixture
def cli(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> Callable[..., Run]:
    """Run the CLI in-process: ``cli("validate", "f.aer.jsonl", "--json")`` -> ``Run(code, out, err)``.

    ``$AGENTPROV_HOME`` is a fresh temporary directory and ``$AGENTPROV_UPSTREAM_CACHE`` is unset, so no test reads the
    user's fetch cache or corpora (a test that needs a cache seeds one and passes ``--cache-dir``)."""
    from agentprov.cli.main import main

    monkeypatch.delenv("AGENTPROV_PROGRESS", raising=False)
    monkeypatch.delenv("AGENTPROV_UPSTREAM_CACHE", raising=False)
    monkeypatch.setenv("AGENTPROV_HOME", str(tmp_path_factory.mktemp("agentprov-home")))

    def run(*argv: str) -> Run:
        capsys.readouterr()
        code = main(list(argv))
        out, err = capsys.readouterr()
        return Run(code, out, err)

    return run


@pytest.fixture(scope="session")
def summary_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def check_summary(summary_schema: dict[str, Any]) -> Callable[[Any], None]:
    import jsonschema

    def check(document: Any) -> None:
        jsonschema.Draft202012Validator(summary_schema).validate(document)

    return check


@pytest.fixture
def host_probe(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Replace ``info``'s host probe: the real profile (no child process) and a canned isolation grade."""
    from agentprov.cli import info
    from agentprov.host import detect_host

    isolation = {"grade": "watchdog", "reasons": [], "calibration": "ok", "default_workers": 4}
    record = detect_host(probe=False).to_record()
    monkeypatch.setattr(info, "_probe_host", lambda: (record, isolation))
    return {"record": record, "isolation": isolation}


@pytest.fixture
def valid_aer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A valid sealed ``.aer.jsonl`` file; its synthetic ``tst`` rule catalogue is made loadable by the validator."""
    import aer_support as s

    from agentprov.aer.canon import dumps_line
    from agentprov.cli import checks

    records = s.example_records()
    path = tmp_path / "ok.aer.jsonl"
    path.write_bytes(b"".join(dumps_line(r) for r in [*records, s.seal_record(records)]))
    monkeypatch.setattr(checks, "_catalogues", s.make_registry)
    return path


@pytest.fixture
def raw_store(tmp_path: Path) -> Path:
    """A store directory (``objects/<h0h1>/<sha256>.json``) holding the artefact the example AER cites."""
    import aer_support as s

    shard = tmp_path / "store" / "objects" / s.ARTEFACT_SHA[:2]
    shard.mkdir(parents=True)
    (shard / f"{s.ARTEFACT_SHA}.json").write_bytes(s.ARTEFACT_BYTES)
    return tmp_path / "store"


@pytest.fixture
def broken_aer(tmp_path: Path) -> Path:
    path = tmp_path / "bad.aer.jsonl"
    path.write_bytes(b"this is not json\n")
    return path


@pytest.fixture
def host_with(monkeypatch: pytest.MonkeyPatch) -> Callable[..., Any]:
    """``host_with(memory_bytes, **changes)``: make ``agentprov.host.detect_host`` return the real profile with fields replaced."""
    from agentprov import host
    from agentprov.host import detect_host

    base = detect_host(probe=False)

    def make(memory_bytes: int | None, **changes: Any) -> Any:
        profile = dataclasses.replace(base, memory_bytes=memory_bytes, **changes)
        monkeypatch.setattr(host, "detect_host", lambda **_kw: profile)
        return profile

    return make
