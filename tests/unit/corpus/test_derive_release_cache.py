"""D-1068 P5: a ``derive``/``recompute`` of a release-mode corpus never serves a cached round trip.

``validate --release`` and ``verify --level rederive --release`` always used the cache in audit mode (it recomputes
every round trip and compares the entries it finds). A recompute takes its mode from the source corpus, and before
D-1068 a release-mode source still got hints from the cache. The CLI now opens the cache in audit mode for it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import derive_support as ds
import pytest

import agentprov.cli.checks as checks
import agentprov.corpus.derive as derive_mod
from agentprov.cli.main import main


@pytest.fixture(autouse=True)
def _home(monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory) -> None:
    monkeypatch.setenv("AGENTPROV_HOME", str(tmp_path_factory.mktemp("home")))
    monkeypatch.delenv("AGENTPROV_PROGRESS", raising=False)


@pytest.fixture(scope="module")
def source(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return ds.agentdojo_corpus(tmp_path_factory.mktemp("release-cache-src"), count=1)


@pytest.mark.parametrize("mode", ["dev", "release"])
def test_a_release_mode_recompute_opens_the_cache_in_audit_mode(source: Path, monkeypatch: pytest.MonkeyPatch,
                                                                   capsys: pytest.CaptureFixture[str], mode: str) -> None:
    seen: list[bool] = []
    real = checks.validation_cache

    def recorder(ctx: Any, *, audit: bool = False, notices: list[str] | None = None) -> Any:
        seen.append(audit)
        return real(ctx, audit=audit, notices=notices)

    monkeypatch.setattr(checks, "validation_cache", recorder)
    monkeypatch.setattr(derive_mod, "_mode_of", lambda _stages: mode)
    main(["recompute", "--corpus", str(source), "--dry-run", "--json", "--progress", "off", "--in-process"])
    capsys.readouterr()
    assert seen == [mode == "release"]
