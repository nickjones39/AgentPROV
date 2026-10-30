"""Mapping one staged live session in process (docs/architecture C.13.1, D.10.0, D.10.4; layer L6).

A backend worker leaves one capture session in ``$AGENTPROV_HOME/staging/<session>/``: the event log, the blobs and the
native TraceLogger JSON (C.13.1). The product path (``agentprov run``, phase 8 stream D) stores these objects in the raw
store and runs the runner's ``container`` map job over them (:func:`agentprov.adapters.runner._job_map_container`); this
module is the same computation in process, for tests, tools and ``--in-process`` runs: :func:`stage_objects` lists and
reads the staging directory through :mod:`agentprov.ingest.paths` (no-follow, regular files, ``st_nlink == 1``, labels
resolved only under the session directory; G.3.6), and :func:`map_session` plans the session with the profile's reader
and maps it with the profile's mapper. Nothing here is specific to a benchmark: the reader and mapper come from the
registry through the profile (``[import] dialect`` and ``mapper``), as for every import.

The C.13.1 name ``capture_mapper.map_session(log, store) -> Path`` is realised here, not in the family module, because
mapping needs the runner's context (:class:`~agentprov.adapters.runner.MapContext`) and M.5.1 forbids the adapters layer
(L4) to import the runner (L6); see D.10.4a.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Callable, Mapping
from agentprov.adapters.profiles import load_profile
from agentprov.adapters.runner import MapOutcome, MemberRef, _family_classes, map_unit
from agentprov.adapters.types import ExecutionUnit, Origin
from agentprov.errors import AgentProvError, IngestError
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads
from agentprov.ingest.paths import discover, open_evidence, open_root

__all__ = ["capture_profile_id", "map_session", "stage_objects"]


def _session_of(labelled: dict[str, bytes], limits: IngestLimits) -> str:
    """The session UUIDv7 named by the first line of the session's capture log (``session.start.data.session``)."""
    logs = [raw for label, raw in labelled.items() if label.endswith(".capture.jsonl")]
    if len(logs) == 1:
        first = logs[0].split(b"\n", 1)[0]
        try:
            event = strict_json_loads(first, limits, record=True)
        except AgentProvError:
            event = None
        data = event.get("data") if isinstance(event, dict) else None
        session = data.get("session") if isinstance(data, dict) else None
        if isinstance(session, str):
            return session
    raise AgentProvError("the staging directory holds no capture log naming its session", code="adapter.session_unknown")


def capture_profile_id(log: bytes, limits: IngestLimits | None = None) -> str:
    """The live profile of the backend that wrote a capture log (D.11.9): ``session.start.data.backend.id`` names the
    backend, and the registry's backend descriptor names its profile. Never guessed from anything else; a log whose first
    line names no registered backend is refused (``adapter.backend_unknown``)."""
    from agentprov.adapters.registry import BACKENDS

    limits = limits or IngestLimits()
    try:
        event = strict_json_loads(log.split(b"\n", 1)[0], limits, record=True)
    except AgentProvError:
        event = None
    data = event.get("data") if isinstance(event, dict) and event.get("type") == "session.start" else None
    backend = data.get("backend") if isinstance(data, dict) else None
    backend_id = backend.get("id") if isinstance(backend, dict) else None
    descriptor = BACKENDS.get(backend_id) if isinstance(backend_id, str) else None
    if descriptor is None:
        raise AgentProvError("the capture log's session.start names no registered backend, so no live profile applies",
                             code="adapter.backend_unknown")
    return descriptor.profile


def stage_objects(
    directory: str | os.PathLike[str], *, session: str | None = None, limits: IngestLimits | None = None,
    origins: Mapping[str, Origin] | None = None,
) -> tuple[list[MemberRef], Callable[[str], bytes], list[dict[str, str]]]:
    """The regular files of a staging directory as ``(members, read, rejected)``.

    Every member has origin ``capture {session}`` (C.3.12; the session is read from the capture log when not given);
    ``read(sha256)`` returns its digest-checked bytes; ``rejected`` lists the entries that must not be ingested (links,
    special and hardlinked files) as register rows. ``origins`` overrides the origin of named labels, as
    ``agentprov run`` records a T0-verified origin for a staged file (the AutoDojo cache, D.11.9)."""
    limits = limits or IngestLimits()
    labelled: dict[str, bytes] = {}
    with open_root(directory) as root:
        found = discover(root, limits)
        for item in found.files:
            with open_evidence(root, item.label, limits, staging=True) as handle:
                raw = handle.read(limits.max_artefact_bytes + 1)
            if len(raw) > limits.max_artefact_bytes:  # ultrareview pipeline nit: the file grew after the size check
                raise IngestError("ingest.size.file", f"staged file of over {limits.max_artefact_bytes} bytes",
                                  limit=limits.max_artefact_bytes)
            labelled[item.label] = raw
    origin = Origin.capture(session or _session_of(labelled, limits))
    members: list[MemberRef] = []
    data: dict[str, bytes] = {}
    for label, raw in labelled.items():
        digest = hashlib.sha256(raw).hexdigest()
        data[digest] = raw
        members.append(MemberRef(label, digest, len(raw), (origins or {}).get(label, origin)))
    rejected = [{"label": r.label, "code": r.code, "detail": r.detail} for r in found.rejected]

    def read(sha256: str) -> bytes:
        try:
            return data[sha256]
        except KeyError:
            raise AgentProvError("object not staged", code="adapter.auxiliary_missing") from None

    return members, read, rejected


def map_session(
    directory: str | os.PathLike[str], *, session: str | None = None, profile_id: str | None = None,
    limits: IngestLimits | None = None, origins: Mapping[str, Origin] | None = None,
) -> tuple[MapOutcome | None, ExecutionUnit | None, list[dict[str, str]]]:
    """Plan and map the session staged in ``directory``: ``(outcome, unit, register rows)``. The outcome is ``None``
    when the session yields no unit (its register rows say why); seal it with :func:`~agentprov.adapters.runner.
    seal_outcome`. Without ``profile_id`` the profile is the one of the backend the log names
    (:func:`capture_profile_id`); a given profile that is not that backend's is reported by the mapper
    (``identity_conflict``), never replaced."""
    members, read, rejected = stage_objects(directory, session=session, limits=limits, origins=origins)
    if profile_id is None:
        logs = [m for m in members if m.label.endswith(".capture.jsonl")]
        if len(logs) != 1:
            raise AgentProvError("the staging directory holds no single capture log", code="adapter.session_unknown")
        profile_id = capture_profile_id(read(logs[0].sha256), limits)
    profile = load_profile(profile_id)
    imp = profile.data.get("import", {})
    reader, mapper = _family_classes(str(imp.get("dialect")), str(imp.get("mapper")))
    plan = reader.plan(members, read, profile, limits=limits or IngestLimits())
    register = rejected + list(plan.register)
    if not plan.units:
        return None, None, register
    unit = plan.units[0]
    return map_unit(unit, mapper, profile, auxiliary=plan.auxiliary), unit, register

