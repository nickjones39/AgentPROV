"""Backend-project test configuration: every test is ``backend_agentdojo``; the network guard is installed for the
whole session (D.10.8 offline guarantee); sleeps are no-ops (the SDK's and agentdojo's retry back-off, and the
``gateway_compat`` waits, would otherwise make retry scenarios slow; they never change what is sent)."""

from __future__ import annotations

import time

import pytest

from agentprov_backend.testing import netguard


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        item.add_marker(pytest.mark.backend_agentdojo)


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
