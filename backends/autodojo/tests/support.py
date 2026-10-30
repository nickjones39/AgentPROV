"""Helpers for the AutoDojo backend tests (no ``agentprov`` import; Python 3.12 backend environment, the fork
installed as ``agentdojo``)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agentprov_backend.autodojo import AutoDojoBackend
from agentprov_backend.runner import AgentConfig, CaptureSession, CellResult, CellSpec, build_redactor
from agentprov_backend.testing import ScriptedTransport, step_from_dict
from agentprov_backend.testing.scenarios import (
    AUTODOJO_CACHE_LABEL,
    AUTODOJO_SCENARIOS,
    Scenario,
    autodojo_cache_bytes,
)

_BACKEND: AutoDojoBackend | None = None


def backend() -> AutoDojoBackend:
    global _BACKEND
    if _BACKEND is None:
        _BACKEND = AutoDojoBackend()
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

    def notes(self, kind: str, ns: str | None = None) -> list[Any]:
        return [e["data"]["payload"] for e in self.of("note")
                if e["data"]["kind"] == kind and (ns is None or e["data"]["ns"] == ns)]

    def items(self) -> dict[str, dict[str, Any]]:
        return {i["id"]: i for i in self.of("instrumentation")[0]["data"]["items"]}

    def native(self) -> dict[str, Any]:
        return json.loads((self.dir / self.session.native_label).read_bytes())

    def judgements(self) -> dict[str, tuple[Any, str]]:
        (out,) = self.of("outcome")
        return {j["name"]: (j["value"], j["origin"]) for j in out["data"]["judgements"]}


def read_events(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_bytes().splitlines()]


def stage_cache(session_dir: Path, data: bytes | None = None, label: str = AUTODOJO_CACHE_LABEL) -> Path:
    """Stage the cache where the parent would (``raw/attack/...``)."""
    path = session_dir / label
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(autodojo_cache_bytes() if data is None else data)
    return path


def run_cell(tmp_path: Path, cell: Mapping[str, Any] | CellSpec, agent: Mapping[str, Any] | AgentConfig,
             steps: Sequence[Any], *, backend_config: Mapping[str, Any] | None = None,
             environ: Mapping[str, str] | None = None, attack_env: Mapping[str, Any] | None = None,
             stage: bool = True, session_dir: Path | None = None) -> Run:
    cell = cell if isinstance(cell, CellSpec) else CellSpec.from_json(cell)
    agent = agent if isinstance(agent, AgentConfig) else AgentConfig.from_json(agent)
    script = [s if not isinstance(s, Mapping) else step_from_dict(s) for s in steps]
    tr = ScriptedTransport(script, model=agent.model_requested)
    d = session_dir or (tmp_path / "session")
    d.mkdir(parents=True, exist_ok=True)
    if stage and cell.attack == "autodojo":
        stage_cache(d)
    session = CaptureSession(d, redactor=build_redactor(environ or {}, agent))
    result = backend().execute(cell, agent, session, backend_config=backend_config or {}, inner_transport=tr,
                               environ=environ or {}, plan_sha256="0" * 64, attack_env=attack_env)
    return Run(d, session, result, tr, read_events(session.capture_path))


def run_scenario(tmp_path: Path, name: str | Scenario, **kw: Any) -> Run:
    sc = AUTODOJO_SCENARIOS[name] if isinstance(name, str) else name
    kw.setdefault("backend_config", sc.backend_config)
    kw.setdefault("attack_env", dict(sc.attack_env))
    return run_cell(tmp_path, sc.cell, sc.agent, sc.steps, **kw)


def assert_capture_invariants(run: Run) -> None:
    """The log verifies sealed; every ``llm.request`` has ``input_at``/``n_messages``; request blobs are the bytes the
    scripted server received; every referenced blob and the native log verify."""
    from agentprov_capture.verify import verify_file

    report = verify_file(run.session.capture_path)
    assert report.sealed and not report.issues, report
    assert report.status == run.result.status
    assert report.head == run.result.capture_head
    reqs = run.of("llm.request")
    for e in reqs:
        assert e["data"]["input_at"] == list(range(e["data"]["n_messages"]))
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
