"""The environment is the pinned AutoDojo fork (identity from PEP 610, never the version string; D.11.2, R-49), and
the harness selects the AutoDojo backend for it."""

import importlib.metadata
import importlib.util
import json

import pytest

pytestmark = pytest.mark.backend_autodojo

PINNED_COMMIT = "aa458794b7eb7f082e94daeac4c0f55bfc0c90cc"


def test_fork_commit_from_pep610_direct_url():
    dist = importlib.metadata.distribution("agentdojo")
    raw = dist.read_text("direct_url.json")
    assert raw is not None, "agentdojo was not installed from a direct URL"
    info = json.loads(raw)
    assert info["vcs_info"]["vcs"] == "git"
    assert info["vcs_info"]["commit_id"] == PINNED_COMMIT
    assert info["url"] == "https://github.com/xhOwenMa/AutoDojo" and info["subdirectory"] == "agentdojo"


def test_the_fork_shares_the_stock_name_and_version():
    assert importlib.metadata.version("agentdojo") == "0.1.35"


def test_agentprov_core_is_not_importable():
    assert importlib.util.find_spec("agentprov") is None


def test_the_worker_selects_the_autodojo_backend():
    from agentprov_backend.autodojo import AutoDojoBackend
    from agentprov_backend.identity import AUTODOJO_GUARDED_NAMES
    from agentprov_backend.runner import select_backend

    backend = select_backend()
    assert isinstance(backend, AutoDojoBackend) and backend.backend_id == "autodojo"
    ident = backend.identity()
    assert ident.source == {"kind": "git", "repo": "https://github.com/xhOwenMa/AutoDojo", "commit": PINNED_COMMIT,
                            "subdirectory": "agentdojo"}
    for module, name in AUTODOJO_GUARDED_NAMES:
        assert f"{module}.{name}" in ident.guarded_sources
    assert ident.lock_source == "project_lock"


def test_another_commit_is_refused(monkeypatch):
    from agentprov_backend import identity
    from agentprov_backend.attacks import UnsupportedConfiguration
    from agentprov_backend.autodojo import AutoDojoBackend

    real = identity._dist_source
    monkeypatch.setattr(identity, "_dist_source", lambda d: {**real(d), "commit": "0" * 40})
    with pytest.raises(UnsupportedConfiguration, match="not the AutoDojo fork"):
        AutoDojoBackend().identity()
