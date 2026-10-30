"""Shared fixtures for the ``agentprov-prov/0.1`` tests: every golden v1 pair mapped to an AER and derived once per
session (J.3.5 gate D on the golden scope).

The golden pairs and the skip rule are those of ``tests/golden/test_v1_round_trip.py`` (loaded from its file, so the
pair index and ``_require()`` exist once): without fixtures the tests skip with the golden reason, and under ``CI`` they
fail instead. Only ids, rule names and QNames are ever printed (R-42).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from agentprov.adapters.runner import aer_bytes, map_artefact
from agentprov.aer.reader import AerDocument, load_aer
from agentprov.prov.engine import ProvDerivation, derive

GOLDEN_MODULE = Path(__file__).resolve().parents[1] / "golden" / "test_v1_round_trip.py"


def _golden_module() -> ModuleType:
    name = "agentprov_tests_golden_v1_pairs"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, GOLDEN_MODULE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@dataclass(frozen=True, slots=True)
class GoldenDerivation:
    """One golden pair: its AER (read back from disk) and the engine's derivation of it."""

    id: str
    aer: AerDocument
    derivation: ProvDerivation

    @property
    def prov_json(self) -> bytes:
        return self.derivation.prov_json

    def document(self) -> dict[str, Any]:
        """A fresh, mutable copy of the decoded PROV-JSON document."""
        doc = json.loads(self.derivation.prov_json)
        assert isinstance(doc, dict)
        return doc


def golden_pair_ids() -> list[str]:
    return [p.id for p in _golden_module().PAIRS]


@pytest.fixture(scope="session")
def golden_derivations(tmp_path_factory: pytest.TempPathFactory) -> dict[str, GoldenDerivation]:
    """Pair id -> :class:`GoldenDerivation` for every golden pair (mapped with profile ``adprov-v1``)."""
    module = _golden_module()
    module._require()
    out: dict[str, GoldenDerivation] = {}
    root = tmp_path_factory.mktemp("golden-aer")
    for pair in module.PAIRS:
        outcome, _ = map_artefact(module._source(pair), module._origin(pair), profile_id="adprov-v1")
        data, _ = aer_bytes(outcome)
        path = root / f"{pair.id}.aer.jsonl"
        path.write_bytes(data)
        aer = load_aer(path)
        out[pair.id] = GoldenDerivation(pair.id, aer, derive(aer))
    return out


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Parametrise ``golden_id`` with every golden pair id (one placeholder id when there are none, so the
    ``golden_derivations`` fixture reports the skip or, under ``CI``, the failure)."""
    if "golden_id" in metafunc.fixturenames:
        metafunc.parametrize("golden_id", golden_pair_ids() or ["no-golden-fixtures"])
