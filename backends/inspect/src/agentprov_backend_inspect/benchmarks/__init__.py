"""Benchmark descriptors of the Inspect harness (one module per backend id ``inspect-<benchmark>``; D-662)."""

from __future__ import annotations

from types import ModuleType

from agentprov_backend_inspect.benchmarks import agentharm

BENCHMARKS: dict[str, ModuleType] = {"agentharm": agentharm}


def for_backend(backend_id: str) -> ModuleType:
    """The descriptor of backend ``inspect-<benchmark>``."""
    prefix = "inspect-"
    if not backend_id.startswith(prefix) or backend_id[len(prefix):] not in BENCHMARKS:
        raise ValueError(f"unknown Inspect backend {backend_id!r}")
    return BENCHMARKS[backend_id[len(prefix):]]
