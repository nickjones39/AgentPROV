"""Live capture versus the native TraceLogger log of the same execution (docs/architecture K.9.1, D.10.4).

For every captured session that announces a native log (``native.log``), both artefacts are mapped (the capture with
``agentdojo.capture``, the native JSON with ``agentdojo.tracelogger`` under the same live profile) and compared:

1. ``common_projection`` of the two AERs is equal as JCS bytes (last pass: roles and parts; executions and statuses;
   fixtures; judgements). The mapper runs the same comparison, so the capture AER carries no ``live_native_divergence``.
2. No contradiction and capture at least as informative: every unknown the capture declares on a scored-pass message is
   declared on the corresponding native message as well (K.9.1 items 2 and 3, restricted to message parts).
3. Times are excluded from the projection (item 4); the native run start is naive local time and is only kept.
4. One declared exception to 2 (D-656 Q4): the text of a reasoning part the provider returned as an empty thinking
   block with a signature is withheld by the capture (``anthropic_messages.thinking_omitted@1``, listed in
   ``ext.agentdojo.thinking_omitted``), while the native log can only state its empty text. The capture is the more
   accurate record there; ``native_comparable`` compares the empty text both hold.

Inputs as in ``tests/integration/test_live_mapping.py`` (frozen sessions; ``AGENTPROV_LIVE_ARTEFACTS`` items carry the
``live_artefacts`` marker). Skips with its reason when no session holds a native log.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "adapters" / "agentdojo"))

from capture_support import live_sessions, map_staged_session  # noqa: E402

from agentprov.adapters.agentdojo.capture_mapper import native_comparable  # noqa: E402
from agentprov.adapters.agentdojo.dialect import TraceLoggerReader  # noqa: E402
from agentprov.adapters.agentdojo.mapper import TraceLoggerMapper  # noqa: E402
from agentprov.adapters.runner import map_unit  # noqa: E402
from agentprov.adapters.types import ArtefactRef, ExecutionUnit  # noqa: E402
from agentprov.ingest.limits import IngestLimits  # noqa: E402
from agentprov.testing.projections import common_projection, projection_bytes, projection_differences  # noqa: E402


def _params() -> list[Any]:
    found = [pytest.param(path, id=sid, marks=[pytest.mark.live_artefacts] if live else [])
             for sid, path, live in live_sessions()]
    return found or [pytest.param(None, id="no-capture-sessions")]


def _native_records(m: Any) -> list[dict[str, Any]] | None:
    native = next((a for a in m.header["artifacts"] if a["role"] == "native_log"), None)
    if native is None:
        return None
    raw = m.objects[native["sha256"]]
    reader = TraceLoggerReader()
    from agentprov.adapters.types import Origin

    artefact = ArtefactRef("a0", native["sha256"], len(raw), "application/json", Origin.from_json(native["origin"]),
                           "primary", "native")
    item = next(reader.parse(raw, artefact, limits=IngestLimits()))
    outcome = map_unit(ExecutionUnit(primary=item), TraceLoggerMapper(), m.profile)
    assert not outcome.degenerate, outcome.error_code
    return outcome.records


@pytest.mark.parametrize("staged", _params())
def test_live_and_native_projections_agree(staged: Path | None) -> None:
    if staged is None:
        pytest.skip("no capture/0.1 session under tests/fixtures/capture/ and AGENTPROV_LIVE_ARTEFACTS unset")
    m = map_staged_session(staged)
    native = _native_records(m)
    if native is None:
        pytest.skip("the session announces no native TraceLogger log")
    live_projection, native_projection = common_projection(native_comparable(m.records)), common_projection(native)
    assert projection_bytes(live_projection) == projection_bytes(native_projection), \
        projection_differences(live_projection, native_projection)
    assert "live_native_divergence" not in m.codes
    # capture is at least as informative on the scored pass's messages (by position)
    live_scored = _scored_messages(native_comparable(m.records))
    native_scored = _scored_messages(native)
    assert len(live_scored) == len(native_scored)
    for live_msg, native_msg in zip(live_scored, native_scored, strict=True):
        omitted = {f"/parts/{k}/text" for k in live_msg.get("ext", {}).get("agentdojo", {}).get("thinking_omitted", ())}
        live_unknown = {p for p in live_msg.get("unk", {}) if p.startswith("/parts/")} - omitted
        native_unknown = {p for p in native_msg.get("unk", {}) if p.startswith("/parts/")}
        assert live_unknown <= native_unknown, (live_msg["id"], sorted(live_unknown - native_unknown))


def _scored_messages(records: list[Any]) -> list[Any]:
    attempts = [r for r in records if r.get("k") == "scope" and r.get("kind") == "attempt"]
    scored = [r for r in attempts if r.get("scored") is True] or attempts[-1:]
    discarded = {r["id"] for r in records if r.get("k") == "model_call" and r.get("status") == "discarded"}
    scope = scored[-1]["id"] if scored else None
    return [r for r in records if r.get("k") == "message" and r.get("scope") == scope
            and r.get("generated_by") not in discarded]
