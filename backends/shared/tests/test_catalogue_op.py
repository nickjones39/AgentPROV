"""The worker op ``catalogue`` (D-652) with a stub backend: no benchmark package is needed.

The real ``runner.catalogue`` reads ``agentdojo``'s suite and attack registries; it is exercised by the backend
projects' environments. Here: the reply framing, the refusal of an unknown version, and the protocol error for a
non-string version."""

from __future__ import annotations

import io
import json
from typing import Any

import pytest

from agentprov_backend.worker import ProtocolError, Worker


class _Backend:
    backend_id = "agentdojo"

    def catalogue(self, version: str | None = None) -> dict[str, Any]:
        if version == "v9":
            raise ValueError("unknown benchmark version 'v9'")
        return {"backend": "agentdojo", "format": "agentprov-backend-catalogue/0.1", "benchmark_version": version or "v1.2.2",
                "benchmark_versions": ["v1.2.2"], "suites": [], "attacks": []}


def _replies(*messages: dict[str, Any]) -> list[dict[str, Any]]:
    out = io.BytesIO()
    worker = Worker(out)
    worker.backend = _Backend()
    for msg in messages:
        worker.op_catalogue(msg)
    worker.outbox.close()
    return [json.loads(line) for line in out.getvalue().splitlines()]


def test_catalogue_ok_and_refused() -> None:
    ok, refused = _replies({"op": "catalogue", "req": "a"}, {"op": "catalogue", "req": "b", "benchmark_version": "v9"})
    assert ok["op"] == "catalogue_ok" and ok["req"] == "a" and ok["catalogue"]["benchmark_version"] == "v1.2.2"
    assert refused["op"] == "catalogue_refused" and "v9" in refused["error"]["message"]


def test_a_non_string_version_is_a_protocol_error() -> None:
    worker = Worker(io.BytesIO())
    worker.backend = _Backend()
    with pytest.raises(ProtocolError):
        worker.op_catalogue({"op": "catalogue", "req": "a", "benchmark_version": 3})
