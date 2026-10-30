"""Helpers for the AgentDojo backend tests (no ``agentprov`` import; Python 3.12 backend environment)."""

from __future__ import annotations

import contextlib
import json
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from agentprov_backend.runner import (
    AgentConfig,
    AgentDojoBackend,
    CaptureSession,
    CellResult,
    CellSpec,
    build_redactor,
)
from agentprov_backend.testing import ScriptedTransport, step_from_dict
from agentprov_backend.testing.scenarios import PATCHES, SCENARIOS, Scenario

_BACKEND: AgentDojoBackend | None = None


def backend() -> AgentDojoBackend:
    global _BACKEND
    if _BACKEND is None:
        _BACKEND = AgentDojoBackend()
    return _BACKEND


@dataclass
class Run:
    dir: Path
    session: CaptureSession
    result: CellResult
    transport: ScriptedTransport
    events: list[dict[str, Any]] = field(default_factory=list)

    def of(self, type_: str) -> list[dict[str, Any]]:
        return [e for e in self.events if e["type"] == type_]

    def blob(self, ref: Mapping[str, Any]) -> bytes:
        h = ref["$blob"].split(":", 1)[1]
        return (self.dir / "raw" / "blobs" / "sha256" / h[:2] / h).read_bytes()

    def json_blob(self, ref: Mapping[str, Any]) -> Any:
        return json.loads(self.blob(ref))

    def notes(self, kind: str) -> list[Any]:
        return [e["data"]["payload"] for e in self.of("note") if e["data"]["kind"] == kind]

    def instrumentation_ids(self) -> list[str]:
        return [i["id"] for i in self.of("instrumentation")[0]["data"]["items"]]

    def native(self) -> dict[str, Any]:
        return json.loads((self.dir / self.session.native_label).read_bytes())

    def judgements(self) -> dict[str, tuple[Any, str]]:
        (out,) = self.of("outcome")
        return {j["name"]: (j["value"], j["origin"]) for j in out["data"]["judgements"]}


def read_events(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_bytes().splitlines()]


def run_cell(tmp_path: Path, cell: Mapping[str, Any] | CellSpec, agent: Mapping[str, Any] | AgentConfig,
             steps: Sequence[Any], *, backend_config: Mapping[str, Any] | None = None,
             environ: Mapping[str, str] | None = None, patch: str | None = None,
             transport: ScriptedTransport | None = None, session_dir: Path | None = None,
             local_model: Mapping[str, Any] | None = None) -> Run:
    cell = cell if isinstance(cell, CellSpec) else CellSpec.from_json(cell)
    agent = agent if isinstance(agent, AgentConfig) else AgentConfig.from_json(agent)
    script = [s if not isinstance(s, Mapping) else step_from_dict(s) for s in steps]
    tr = transport or ScriptedTransport(script, model=agent.model_requested)
    d = session_dir or (tmp_path / "session")
    d.mkdir(parents=True, exist_ok=True)
    session = CaptureSession(d, redactor=build_redactor(environ or {}, agent))
    ctx = PATCHES[patch]() if patch else contextlib.nullcontext()
    with ctx:
        result = backend().execute(cell, agent, session, backend_config=backend_config or {}, inner_transport=tr,
                                   environ=environ or {}, plan_sha256="0" * 64, local_model=local_model)
    return Run(d, session, result, tr, read_events(session.capture_path))


def run_scenario(tmp_path: Path, name: str | Scenario, **kw: Any) -> Run:
    sc = SCENARIOS[name] if isinstance(name, str) else name
    kw.setdefault("patch", sc.patch)
    kw.setdefault("backend_config", sc.backend_config)
    return run_cell(tmp_path, sc.cell, sc.agent, sc.steps, **kw)


def with_agent(sc: Scenario, **changes: Any) -> Scenario:
    return replace(sc, agent={**sc.agent, **changes})


def assert_capture_invariants(run: Run) -> None:
    """Common assertions for every produced session: the log verifies sealed; every ``llm.request`` carries
    ``input_at`` and ``n_messages``; every blob it references exists with its digest; every request blob is the exact
    body the scripted server received; the ``native.log`` digest matches."""
    import hashlib

    from agentprov_capture.verify import verify_file

    report = verify_file(run.session.capture_path)
    assert report.sealed and not report.issues, report
    assert report.status == run.result.status
    assert report.head == run.result.capture_head
    reqs = run.of("llm.request")
    detached = {c for e in run.of("note") if e["data"]["kind"] == "defence_detached_input"
                for c in e["data"]["payload"]["calls"]}
    for e in reqs:
        if e["data"]["call"] in detached:  # a defence's own conversation (D-670): no pass positions
            assert e["data"]["n_messages"] == 0 and "input_at" not in e["data"], e["data"]["call"]
            continue
        assert "input_at" in e["data"] and "n_messages" in e["data"], e["data"]["call"]
        assert e["data"]["input_at"] == list(range(e["data"]["n_messages"]))
    # the recording transport never modified a request: blob bytes == bytes the inner transport received
    assert [run.blob(e["data"]["request"]) for e in reqs] == run.transport.bodies
    for line in run.session.capture_path.read_bytes().splitlines():
        for m in _blob_refs(json.loads(line)):
            data = run.blob(m)
            assert hashlib.sha256(data).hexdigest() == m["$blob"].split(":", 1)[1] and len(data) == m["bytes"]
    for e in run.of("native.log"):
        data = (run.dir / e["data"]["path"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == e["data"]["sha256"]


def _blob_refs(value: Any) -> Iterator[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        if "$blob" in value:
            yield value
            return
        for v in value.values():
            yield from _blob_refs(v)
    elif isinstance(value, list):
        for v in value:
            yield from _blob_refs(v)


def pass_message_lists(run: Run) -> list[list[dict[str, Any]]]:
    return [run.json_blob(e["data"]["messages"]) for e in run.of("pass.end")]
