"""Gate B: ``adprov-v2.3-compat`` graph bytes (J.3.3; K.7.1; EF E.8.3).

For every golden transcript/graph pair of ``golden_index.json``: parse the stored transcript with the strict loader, run the
ported ``build_prov`` with default flags, serialise with the baseline layout and compare **bytes** with the stored graph
(and its sha256 from the index). Nothing here compares parsed dicts with ``==`` (K.1; E.8.3(2)).

This is J's check **B2** (directly on ``strict_json_loads(T)``, isolating port faults from view faults). B1, the same run on
``views.transcript_v1.render(map(T))``, joins this file with the v1 view (phase 4, other component).

Golden inputs are located by ``agentprov.testing.golden.golden_dir()`` when that module exists and otherwise by a local
resolver with the same contract: the environment variable ``AGENTPROV_GOLDEN_DIR``, default
``tests/fixtures/agentdojo_prov_v1/golden`` relative to the repository. The files are third-party research data that contain
prompt-injection payloads by design: failures print only paths, a JSON pointer and sha256 values, never content.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, NamedTuple

import pytest

from agentprov.ingest.loaders import strict_json_loads
from agentprov.prov.compat.adprov_v2_3 import SPEC
from agentprov.prov.compat.adprov_v2_3.conformance import ProvValidator
from agentprov.prov.compat.adprov_v2_3.validate import validate_prov_document

REPO = Path(__file__).resolve().parents[2]
GOLDEN_ENV = "AGENTPROV_GOLDEN_DIR"
GOLDEN_DEFAULT = Path("tests") / "fixtures" / "agentdojo_prov_v1" / "golden"


class Pair(NamedTuple):
    id: str
    transcript: Path
    graph: Path
    transcript_sha256: str
    graph_sha256: str


def _golden_dir() -> Path:
    try:
        from agentprov.testing.golden import golden_dir  # written by the golden-fixture component
    except ImportError:
        env = os.environ.get(GOLDEN_ENV)
        return Path(env) if env else REPO / GOLDEN_DEFAULT
    return Path(golden_dir())


def _load_pairs() -> tuple[Path, list[Pair]]:
    """The v1 transcript/graph pairs of the golden index, in either of its two layouts.

    * the research workspace's ``golden_index.json`` (an object with ``traces``; paths ``golden/<corpus>/...`` relative to
      the golden directory), and
    * the repository fixture index (a list of entries with ``kind == "v1_pair"`` and ``files[]`` of ``role``/``path``/
      ``sha256``, J.2.2; paths relative to ``tests/fixtures``, i.e. two levels above the golden directory).
    """
    root = _golden_dir()
    index = root / "golden_index.json"
    if not index.is_file():
        return root, []
    data = json.loads(index.read_text(encoding="utf-8"))
    pairs: list[Pair] = []
    if isinstance(data, dict):
        for t in data["traces"]:
            pairs.append(
                Pair(
                    t["id"],
                    root / t["golden_transcript"].removeprefix("golden/"),
                    root / t["golden_graph"].removeprefix("golden/"),
                    t["transcript_sha256"],
                    t["graph_sha256"],
                )
            )
    else:
        fixtures = root.parent.parent
        for entry in data:
            if entry.get("kind") != "v1_pair":
                continue
            files = {f["role"]: f for f in entry["files"]}
            tr, gr = files["v1_transcript"], files["compat_graph"]
            pairs.append(Pair(entry["id"], fixtures / tr["path"], fixtures / gr["path"], tr["sha256"], gr["sha256"]))
    return root, pairs


ROOT, PAIRS = _load_pairs()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _first_difference(a: bytes, b: bytes) -> str:
    """JSON pointer of the first differing member of two JSON documents (``"/"`` if they parse equal), best effort."""

    def walk(x: Any, y: Any, pointer: str) -> str | None:
        if type(x) is not type(y):
            return pointer or "/"
        if isinstance(x, dict):
            keys_x, keys_y = list(x), list(y)
            for kx, ky in zip(keys_x, keys_y, strict=False):
                if kx != ky:
                    return f"{pointer}/{kx}".replace("~", "~0")
            if len(keys_x) != len(keys_y):
                return pointer or "/"
            for key in keys_x:
                hit = walk(x[key], y[key], f"{pointer}/{key.replace('~', '~0').replace('/', '~1')}")
                if hit:
                    return hit
            return None
        if isinstance(x, list):
            for i, (ix, iy) in enumerate(zip(x, y, strict=False)):
                hit = walk(ix, iy, f"{pointer}/{i}")
                if hit:
                    return hit
            return pointer or "/" if len(x) != len(y) else None
        return None if (x == y and repr(x) == repr(y)) else pointer or "/"

    try:
        return walk(json.loads(a), json.loads(b), "") or "(same members; serialisation differs)"
    except ValueError:
        return "(not JSON)"


def _missing_reason() -> str:
    return f"golden fixtures not found at {ROOT} (set {GOLDEN_ENV})"


def _require_golden() -> None:
    """Skip locally when the fixtures are absent; fail in CI, where a skipped gate would be no gate."""
    if not PAIRS:
        if os.environ.get("CI"):
            pytest.fail(_missing_reason())
        pytest.skip(_missing_reason())


def _pair_ids() -> list[Any]:
    return [pytest.param(t, id=t.id) for t in PAIRS] or [pytest.param(None, id="no-golden-fixtures")]


def test_the_golden_set_covers_the_released_and_converted_pairs():
    _require_golden()
    ids = {t.id for t in PAIRS}
    assert {f"R{n:02d}" for n in range(1, 9)} | {f"C{n:02d}" for n in range(1, 8)} <= ids


@pytest.mark.parametrize("trace", _pair_ids())
def test_gate_b_compat_graph_bytes_equal_the_stored_graph(trace):
    _require_golden()
    transcript_path, graph_path = trace.transcript, trace.graph
    transcript_bytes, stored = transcript_path.read_bytes(), graph_path.read_bytes()
    # the fixtures are what the index says they are (a corrupted fixture must not read as a port failure)
    assert _sha256(transcript_bytes) == trace.transcript_sha256, f"{transcript_path}: fixture sha256 differs from the index"
    assert _sha256(stored) == trace.graph_sha256, f"{graph_path}: fixture sha256 differs from the index"

    doc = SPEC.build(strict_json_loads(transcript_bytes))
    produced = SPEC.serialise(doc)
    assert produced == stored, (
        f"{trace.id}: compat graph differs from {graph_path}; first difference at JSON pointer "
        f"{_first_difference(produced, stored)}; produced sha256 {_sha256(produced)}, stored sha256 {_sha256(stored)}"
    )
    assert _sha256(produced) == trace.graph_sha256


@pytest.mark.parametrize("trace", _pair_ids())
def test_the_ported_validators_accept_the_stored_graph(trace):
    """J.3.3 acceptance: the ported ``validate_prov_document`` and the five conformance checks pass (RM-22 one-off check)."""
    _require_golden()
    doc = json.loads(trace.graph.read_bytes())
    result = validate_prov_document(doc)
    assert result.ok, f"{trace.id}: validate_prov_document: {len(result.errors)} error(s)"
    report = ProvValidator(ProvValidator.ALL_CHECKS).validate(doc)
    statuses = {c.name: c.status for c in report.checks}
    assert report.valid, f"{trace.id}: conformance statuses {statuses}"
    required = {"schema", "round_trip", "completeness", "constraints"}
    assert all(statuses[name] == "pass" for name in required), f"{trace.id}: {statuses}"
    # shacl needs the optional `shacl` extra; it may be skipped only when pyshacl is not installed
    assert statuses["shacl"] == "pass" or statuses["shacl"] == "skipped", f"{trace.id}: {statuses}"
