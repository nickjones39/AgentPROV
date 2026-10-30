"""Fixtures for the ``verify`` / ``validate --corpus`` tests (phase 11, U4; K.12.5, K.12.15, Q.19).

Sealed test corpora come from U3/U5's helpers (``seal_support`` / ``release_support``: three golden June-2024 AgentDojo
logs, licence-cleared fixtures whose text is never printed); working corpora from U2's ``derive_support``. Each test
gets its own copy.

The tampering devices are in ``verify_support``.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple

import pytest

_TESTS = Path(__file__).resolve().parents[1]
for _here in (_TESTS / "adapters", _TESTS / "unit" / "raw", _TESTS / "unit" / "corpus", _TESTS / "unit" / "release",
              Path(__file__).resolve().parent):
    if str(_here) not in sys.path:
        sys.path.insert(0, str(_here))

SCHEMA_PATH = _TESTS / "cli" / "schemas" / "cli-summary-0.1.schema.json"


class Run(NamedTuple):
    code: int
    out: str
    err: str

    def json(self) -> Any:
        return json.loads(self.out)


@pytest.fixture
def cli(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch,
        tmp_path_factory: pytest.TempPathFactory) -> Callable[..., Run]:
    """Run the CLI in-process with a fresh ``$AGENTPROV_HOME`` (no user cache or corpus is read)."""
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
def sealed(tmp_path_factory: pytest.TempPathFactory, tmp_path: Path) -> Path:
    """A fresh copy of the sealed three-log test corpus ``mini-mit``."""
    import release_support as rs

    return rs.sealed(tmp_path_factory, tmp_path / "corpora")
