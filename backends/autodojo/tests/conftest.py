"""Backend-project test configuration (D.11.5): every test is ``backend_autodojo``; the network guard is installed for
the whole session (offline guarantee); sleeps are no-ops (the SDK's, the fork's tenacity back-off; they never change
what is sent). No key variable is set by any test except fake sentinels."""

from __future__ import annotations

import time

import pytest

from agentprov_backend.testing import netguard


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        item.add_marker(pytest.mark.backend_autodojo)


@pytest.fixture(scope="session", autouse=True)
def _offline() -> object:
    netguard.install()
    yield
    netguard.uninstall()


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    slept: list[float] = []
    monkeypatch.setattr(time, "sleep", lambda s: slept.append(s))
    return slept
