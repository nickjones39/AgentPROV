"""Helpers for the ``inspect.eval`` tests (imported as ``inspect_support``; not collected).

``import_log`` runs the real pipeline on one ``.eval`` container: the container is put in a raw store, the versioned
``expand`` stage (``agentprov.raw.members``, a T1 job run in process) stores the profile-selected members as member
objects, the reader plans the units and the runner maps and seals each one. Nothing is extracted to disk except member
objects in the raw store. The logs hold harmful requests (AgentHarm) and are data: no helper prints their content.

Synthetic logs are built in code (``build_eval``) with Zstandard members (method 93), as the band's logs are.
"""

from __future__ import annotations

import copy
import hashlib
import io
import json
import os
import warnings
import zipfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agentprov.adapters.inspect.dialect import InspectEvalReader, MemberObject
from agentprov.adapters.inspect.mapper import InspectEvalMapper
from agentprov.adapters.profiles import SourceProfile, load_profile
from agentprov.adapters.runner import MapOutcome, aer_bytes, map_unit
from agentprov.adapters.types import ExecutionUnit
from agentprov.aer.rules import RuleRegistry
from agentprov.aer.validate import AerValidator, ValidationReport
from agentprov.aer.writer import SealInfo
from agentprov.ingest.limits import IngestLimits
from agentprov.io.workers import WorkerPool
from agentprov.raw.members import ContainerSpec, Selection, expand_containers
from agentprov.raw.store import RawObjectStore

REPO = Path(__file__).resolve().parents[3]
FIXTURES = REPO / "tests" / "fixtures" / "inspect" / "survey-agentharm"
SURVEY_COMMIT = "89c4db2c949797fbb38c5bfed85dc82780ddbfe3"
#: The six survey AgentHarm logs at the pinned commit (K.4.1(5); SWEEP_r2 EV-3): path -> (bytes, sha256, git blob).
SURVEY_LOGS: dict[str, tuple[int, str, str]] = {
    "agentharm/results/coder_benign/2026-08-22T02-58-36-00-00_agentharm-benign_Mw9cYAge9JkjQ9D9FPrGKU.eval": (
        2064758, "fc1e516f34d6b49ff05748e950d1ecae51d569203a1c4ec778912a62c58d24e6", "b1b0f6bbb5b4707b86d8e1a71a0ec6f0722fd4d3"),
    "agentharm/results/coder_harmful/2026-08-22T01-56-09-00-00_agentharm_DHQwUgVrD8EonG5RWLd9b6.eval": (
        1684610, "3be29f23d7977eed5c7ac7acd333deb7f3f93b4de829ccb2abb86422a1c585a5", "7f9ef9f22ac9e3039e2321a8b61a38f3f7495e9d"),
    "agentharm/results/gptoss_benign/2026-08-21T23-10-42-00-00_agentharm-benign_JArEBkqSNv9uTu7zWGRkiQ.eval": (
        2125019, "165eb60c5758ac18a4355bee2599349fb9ce104a277ad59c43e4e71be2323946", "8207a04296a4c6d3564b44fa3987a0a5ea53082e"),
    "agentharm/results/gptoss_harmful/2026-08-21T21-23-06-00-00_agentharm_TQQjY9dzdqeuyNhWvATriR.eval": (
        1388361, "c9eafb4b685d55b3029250913e6aed5290a1468295388f5f656202f4cb5c0ad0", "7d896da49a7b1c4428d896d9cb351c9848843737"),
    "agentharm/results/qwen14_benign/2026-08-22T08-34-50-00-00_agentharm-benign_6NAdYckpcsjaiPHVAzGAxP.eval": (
        2385846, "9ebe03f92279f268284e6735dcc493c937cdc4eaa5aa15a931be2a7a3088511a", "274fd72c53eb2d5051184d0f080175e808f3fcb1"),
    "agentharm/results/qwen14_harmful/2026-08-22T04-27-45-00-00_agentharm_oJoW34k6hj7evSdbggsgrm.eval": (
        2176820, "0b2d10a042ed7a6d913dcc3303b246c6cea14d16b1fc4f97db5cc5101574fc71", "1ebcabc94835ae446d32e4eef75563a4c5dfba8f"),
}
#: The one committed complete log (the smallest; K.4.1(5)).
COMMITTED_LOG = "agentharm/results/gptoss_harmful/2026-08-21T21-23-06-00-00_agentharm_TQQjY9dzdqeuyNhWvATriR.eval"
UPSTREAM_ENV = "AGENTPROV_SURVEY_CLONE"
DEFAULT_CLONE = Path.home() / "Desktop/PhD/Labs/AgentPROV-upstream/agent-security-tools-survey"


def committed_log() -> Path:
    return FIXTURES / COMMITTED_LOG.rsplit("/", 1)[-1]


def survey_clone() -> Path | None:
    """The survey clone holding all six logs (``$AGENTPROV_SURVEY_CLONE``, else the documented local path)."""
    root = Path(os.environ[UPSTREAM_ENV]) if os.environ.get(UPSTREAM_ENV) else DEFAULT_CLONE
    return root if all((root / rel).is_file() for rel in SURVEY_LOGS) else None


@dataclass
class Unit:
    unit: ExecutionUnit
    outcome: MapOutcome
    data: bytes
    info: SealInfo
    label: str

    @property
    def records(self) -> list[dict[str, Any]]:
        return [json.loads(line) for line in self.data.splitlines()]

    @property
    def header(self) -> dict[str, Any]:
        return self.records[0]

    def by_id(self) -> dict[str, dict[str, Any]]:
        return {r["id"]: r for r in self.records}

    def of_kind(self, kind: str) -> list[dict[str, Any]]:
        return [r for r in self.records if r["k"] == kind]

    def issue_codes(self) -> list[str]:
        return [str(i["code"]) for i in self.info.issues]


@dataclass
class Imported:
    store: RawObjectStore
    container: str
    units: list[Unit] = field(default_factory=list)
    register: list[dict[str, str]] = field(default_factory=list)
    member_rows: list[Any] = field(default_factory=list)
    events: list[Any] = field(default_factory=list)

    def unit(self, label: str) -> Unit:
        return next(u for u in self.units if u.label == label)

    def validate(self, u: Unit, mode: str = "release") -> ValidationReport:
        profile = load_profile("survey-agentharm")
        validator = AerValidator(store=self.store, catalogues=RuleRegistry.default(), mode=mode,  # type: ignore[arg-type]
                                 profile_digests={(profile.id, profile.version): profile.sha256})
        for line in u.data.splitlines(keepends=True):
            validator.feed(line)
        return validator.finish()


def import_log(data: bytes, store_dir: Path, *, path: str = "x.eval", profile: SourceProfile | None = None,
               limits: IngestLimits | None = None) -> Imported:
    """Store, expand, plan, map and seal one ``.eval`` container (the D.2.9 pipeline, in process)."""
    profile = profile or load_profile("survey-agentharm")
    reader, mapper = InspectEvalReader(), InspectEvalMapper()
    store = RawObjectStore(store_dir)
    container = store.put(data, ext="eval").sha256
    pool = WorkerPool(in_process=True, store_root=store.objects_dir)
    selection = Selection(include=reader.member_patterns(profile))
    out = expand_containers(store, [ContainerSpec(container, "snap", path, (selection,))], pool=pool, limits=limits)
    origins = dict(out.origins)
    members = [MemberObject(r.label, r.sha256, r.size, origins[r.sha256]) for r in out.rows
               if r.disposition == "selected" and r.sha256 is not None and r.label is not None and r.size is not None]
    result = Imported(store, container, member_rows=list(out.rows), events=list(out.events))
    if out.containers != [container]:
        return result
    plan = reader.plan(members, store.read_bytes, profile, limits=limits)
    result.register = plan.register
    labels = {m.sha256: m.label for m in members}
    for unit in plan.units:
        outcome = map_unit(unit, mapper, profile, auxiliary=plan.auxiliary)
        aer, info = aer_bytes(outcome, unit=unit, mapper=mapper, profile=profile)
        result.units.append(Unit(unit, outcome, aer, info, labels[unit.primary.artefact.sha256]))
    return result


# ------------------------------------------------------------------------------------------------ synthetic logs
def build_eval(header: Mapping[str, Any], samples: Mapping[str, Mapping[str, Any]], *,
               method: int = zipfile.ZIP_ZSTANDARD, extra: Mapping[str, bytes] | None = None) -> bytes:
    """A deterministic ``.eval`` zip: ``header.json`` plus ``samples/<name>`` members (JSON, method 93 by default)."""
    buf = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with zipfile.ZipFile(buf, "w") as z:
            items: list[tuple[str, bytes]] = [("header.json", json.dumps(header).encode())]
            items += [(f"samples/{name}", json.dumps(sample).encode()) for name, sample in samples.items()]
            items += list((extra or {}).items())
            for name, body in items:
                info = zipfile.ZipInfo(name, (2026, 8, 21, 0, 0, 0))
                info.compress_type = method
                z.writestr(info, body)
    return buf.getvalue()


def ts(second: float) -> str:
    """A band-shaped timestamp (``…+00:00``, microseconds) at ``second`` seconds after a fixed origin."""
    whole = int(second)
    micro = round((second - whole) * 1_000_000)
    return f"2026-08-21T00:{whole // 60:02d}:{whole % 60:02d}.{micro:06d}+00:00"


def synthetic_header(producer: str = "0.3.247.dev69+g53c1fa98b", version: int = 2) -> dict[str, Any]:
    return {
        "version": version,
        "status": "success",
        "eval": {
            "eval_id": "SyntheticEvalId0000000a",
            "run_id": "SyntheticRunId00000000a",
            "created": ts(0),
            "task": "inspect_evals/agentharm_benign",
            "task_id": "SyntheticTaskId0000000a",
            "task_version": 2,
            "task_args": {"split": "test_public"},
            "model": "ollama/synthetic-agent:1b",
            "model_generate_config": {"max_connections": 1},
            "revision": {"type": "git", "origin": "https://github.com/UKGovernmentBEIS/inspect_evals.git",
                         "commit": "2dd469a", "dirty": False},
            "packages": {"inspect_ai": producer, "inspect_evals": "0.0.1.dev1+unknown.g2dd469ac0"},
        },
        "plan": {"name": "plan", "steps": [], "config": {"temperature": 0.0}},
    }


class Sample:
    """A small band-shaped EvalSample built in code (synthetic text only; no AgentHarm content)."""

    def __init__(self, sid: str = "s1") -> None:
        self.events: list[dict[str, Any]] = []
        self.pool: list[dict[str, Any]] = []
        self.messages: list[dict[str, Any]] = []
        self.attachments: dict[str, str] = {}
        self.n = 0
        self.sid = sid
        self.clock = 1.0

    def tick(self, d: float = 0.5) -> str:
        self.clock += d
        return ts(self.clock)

    def uid(self, prefix: str = "u") -> str:
        self.n += 1
        return f"{prefix}{self.n:021d}"[:22]

    def event(self, kind: str, span: str | None, **fields: Any) -> dict[str, Any]:
        e = {"uuid": self.uid("E"), "span_id": span, "timestamp": fields.pop("timestamp", None) or self.tick(),
             "working_start": self.clock, "event": kind, **fields}
        self.events.append(e)
        return e

    def span(self, sid: str, type_: str, name: str, parent: str | None = None) -> str:
        fields: dict[str, Any] = {"id": sid, "type": type_, "name": name}
        if parent is not None:
            fields["parent_id"] = parent
        self.event("span_begin", sid, **fields)
        return sid

    def end(self, sid: str) -> None:
        self.event("span_end", sid, id=sid)

    def msg(self, role: str, content: Any, **fields: Any) -> dict[str, Any]:
        return {"id": self.uid("M"), "role": role, "content": content, **fields}

    def model(self, span: str, model: str, inputs: list[dict[str, Any]], output: dict[str, Any] | None, *,
              tools: list[Any] | None = None, **fields: Any) -> dict[str, Any]:
        start = len(self.pool)
        for m in inputs:
            if not any(p["id"] == m["id"] for p in self.pool):
                self.pool.append(copy.deepcopy(m))
        ids = [m["id"] for m in inputs]
        positions = [next(i for i, p in enumerate(self.pool) if p["id"] == mid) for mid in ids]
        refs = [[positions[0], positions[-1] + 1]] if positions and positions == list(range(positions[0], positions[-1] + 1)) else [[p, p + 1] for p in positions]
        del start
        out: dict[str, Any] = {"model": model.split("/", 1)[-1], "choices": [], "completion": "",
                               "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}, "time": 0.5}
        if output is not None:
            out["choices"] = [{"message": output, "stop_reason": "tool_calls" if output.get("tool_calls") else "stop"}]
        begin = self.tick()
        return self.event("model", span, timestamp=begin, model=model, input=[], input_refs=refs, tools=tools or [],
                          tool_choice="auto", config={"temperature": 0.0, "max_tokens": 64}, output=out,
                          completed=self.tick(0.25), working_time=0.25, **fields)

    def tool(self, span: str, call: dict[str, Any], message: dict[str, Any] | None, **fields: Any) -> dict[str, Any]:
        begin = self.tick()
        return self.event("tool", span, timestamp=begin, type="function", id=call["id"], function=call["function"],
                          arguments=call["arguments"], result=(message or {}).get("content", ""), events=[],
                          completed=self.tick(0.1), working_time=0.1,
                          message_id=(message or {}).get("id", "MissingMessageId00000a"), **fields)

    def build(self, **extra: Any) -> dict[str, Any]:
        sample = {
            "id": self.sid, "epoch": 1, "input": "Synthetic task prompt.", "target": "",
            "messages": self.messages, "output": {"model": "synthetic", "choices": [], "completion": ""},
            "scores": {}, "metadata": {"category": "Synthetic", "target_functions": ["get_x"], "grading_function": "grade_x"},
            "store": {}, "events": self.events, "model_usage": {}, "role_usage": {},
            "started_at": ts(0.5), "completed_at": self.tick(), "total_time": 9.5, "working_time": 9.0,
            "uuid": "SyntheticSampleUuid000a", "error_retries": [], "attachments": self.attachments,
            "events_data": {"messages": self.pool, "calls": []},
        }
        sample.update(extra)
        return sample


def basic_sample(sid: str = "s1", *, tool_error: dict[str, Any] | None = None,
                 tune: Callable[[Sample, dict[str, Any]], None] | None = None) -> dict[str, Any]:
    """init + solver(generate: call -> tool -> call) + scorer(judge call, score)."""
    s = Sample(sid)
    init = s.span("SpanInit00000000000000", "init", "init")
    s.event("sample_init", init, sample={"input": "Synthetic task prompt.", "target": "", "id": sid, "metadata": {}},
            state={"messages": []})
    s.end(init)
    solvers = s.span("SpanSolvers00000000000", "solvers", "solvers")
    gen = s.span("SpanGenerate0000000000", "solver", "generate", solvers)
    system, user = s.msg("system", "You are a synthetic agent."), s.msg("user", "Synthetic task prompt.", source="input")
    call = {"id": "call_synthetic_1", "function": "get_x", "arguments": {"q": "a", "n": 2}, "type": "function"}
    a1 = s.msg("assistant", [{"type": "reasoning", "reasoning": "Synthetic reasoning.", "redacted": False},
                             {"type": "text", "text": ""}], source="generate", model="synthetic", tool_calls=[call])
    tool_fields: dict[str, Any] = {}
    tool_msg = s.msg("tool", "synthetic tool output", tool_call_id=call["id"], function="get_x")
    if tool_error is not None:
        tool_msg["error"] = tool_error
        tool_fields["error"] = tool_error
    a2 = s.msg("assistant", "Synthetic final answer.", source="generate", model="synthetic")
    tools = [{"name": "get_x", "description": "Synthetic tool.", "parameters": {"type": "object", "properties": {}}}]
    s.model(gen, "ollama/synthetic-agent:1b", [system, user], a1, tools=tools)
    s.tool(gen, call, tool_msg, **tool_fields)
    s.model(gen, "ollama/synthetic-agent:1b", [system, user, a1, tool_msg], a2, tools=tools)
    s.event("state", gen, changes=[{"op": "add", "path": "/messages/2", "value": {"role": "assistant"}}])
    s.end(gen)
    s.end(solvers)
    s.messages.extend([system, user, a1, tool_msg, a2])
    scorers = s.span("SpanScorers00000000000", "scorers", "scorers")
    scorer = s.span("SpanScorer000000000000", "scorer", "combined_scorer", scorers)
    prompt = s.msg("user", "Synthetic judge prompt.")
    verdict = s.msg("assistant", "Synthetic verdict.", source="generate", model="synthetic-judge")
    s.model(scorer, "ollama/synthetic-judge:1b", [prompt], verdict)
    s.event("score", scorer, score={"value": {"score": 1.0, "refusal": 0.0}, "explanation": "Synthetic.",
                                    "metadata": {}, "history": []},
            target="", intermediate=False, scorer="combined_scorer", scorer_args={}, model_usage={})
    s.end(scorer)
    s.end(scorers)
    sample = s.build(scores={"combined_scorer": {"value": {"score": 1.0, "refusal": 0.0}, "explanation": "Synthetic.",
                                                 "metadata": {}, "history": []}})
    if tune is not None:
        tune(s, sample)
    return sample


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def derive_chain(args: tuple[str, bytes]) -> tuple[str, bool, bool, list[str]]:
    """derive twice + tier 4 for one sealed AER: ``(name, deterministic, passed, failing check ids)``.

    Module-level so that a process pool can run it (the pool's initializer puts this directory on ``sys.path``).
    """
    import tempfile

    from agentprov.aer.reader import load_aer
    from agentprov.prov.engine import derive
    from agentprov.validate import validate_prov

    name, data = args
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "x.aer.jsonl"
        path.write_bytes(data)
        doc = load_aer(path)
        first, second = derive(doc), derive(doc)
        report = validate_prov(first.prov_json, doc)
        failed = sorted({o.id for o in report.outcomes if o.status in ("fail", "skipped")})
        return name, first.prov_json == second.prov_json, report.passed, failed


def pool(workers: int | None = None) -> Any:
    """A process pool whose workers can import this module."""
    import functools
    import sys
    from concurrent.futures import ProcessPoolExecutor

    here = str(Path(__file__).resolve().parent)
    return ProcessPoolExecutor(max_workers=workers or min(8, os.cpu_count() or 1),
                               initializer=functools.partial(sys.path.insert, 0, here))
