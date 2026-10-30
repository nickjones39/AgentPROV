"""Fixtures for the ``adprov.transcript_v1`` adapter tests (docs/architecture K.6.2, K.7.2).

Golden inputs are located through ``agentprov.testing.golden.golden_dir()`` (``$AGENTPROV_GOLDEN_DIR``, default
``tests/fixtures/agentdojo_prov_v1/golden``). Two index layouts are accepted: the repository index of J.2.2 (a list of
entries) and the research workspace's ``golden_index.json`` (an object with ``traces``). The files are third-party data
holding prompt-injection payloads by design: no helper here prints their content (G.8.1 item 5; R-42).

Synthetic transcripts are built in code with the baseline writer's own serialisation (``json.dumps(doc, indent=2)``), so
every synthetic field is inside the byte gates (J.2.5, R-32) without a fixture file.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from agentprov.adapters.profiles import load_profile
from agentprov.adapters.runner import MapOutcome, aer_bytes, map_artefact
from agentprov.adapters.types import Origin
from agentprov.aer.rules import RuleRegistry
from agentprov.aer.validate import AerValidator, ValidationReport
from agentprov.aer.writer import SealInfo
from agentprov.testing import golden
from agentprov.views.transcript_v1 import render, serialise

BASELINE_COMMIT = "579a908354b93361efe0905ffb7623256aa96a06"


@dataclass(frozen=True)
class Pair:
    id: str
    transcript: Path
    graph: Path
    transcript_sha256: str
    graph_sha256: str
    corpus_relpath: str  # the path inside the frozen AgentDojo-PROV corpus (the origin's path)


def load_pairs() -> list[Pair]:
    """Golden v1 pairs in either index layout (empty when the fixtures are absent)."""
    root = golden.golden_dir()
    index = root / "golden_index.json"
    if not index.is_file():
        return []
    data = json.loads(index.read_bytes())
    pairs: list[Pair] = []
    if isinstance(data, dict):
        for t in data["traces"]:
            source = str(t["source_transcript"])
            relpath = source.split("/corpus/", 1)[1] if "/corpus/" in source else t["golden_transcript"].removeprefix("golden/")
            pairs.append(Pair(t["id"], root / t["golden_transcript"].removeprefix("golden/"),
                              root / t["golden_graph"].removeprefix("golden/"), t["transcript_sha256"], t["graph_sha256"],
                              relpath))
    else:
        fixtures = root.parent.parent
        for entry in data:
            if entry.get("kind") != "v1_pair":
                continue
            files = {f["role"]: f for f in entry["files"]}
            tr, gr = files["v1_transcript"], files["compat_graph"]
            relpath = str(entry.get("origin", {}).get("corpus_relpath") or tr["path"])
            pairs.append(Pair(entry["id"], fixtures / tr["path"], fixtures / gr["path"], tr["sha256"], gr["sha256"], relpath))
    return pairs


def corpus_origin(relpath: str) -> Origin:
    return Origin.corpus("AgentDojo-PROV", "2.3", relpath, producer_commit=BASELINE_COMMIT)


class _Store:
    """In-memory ``RawStore`` for the validator (locators resolve against the digest-checked bytes)."""

    def __init__(self, *objects: bytes) -> None:
        self.objects = {hashlib.sha256(o).hexdigest(): o for o in objects}

    def has(self, sha256: str) -> bool:
        return sha256 in self.objects

    def size(self, sha256: str) -> int:
        return len(self.objects[sha256])

    def read_bytes(self, sha256: str) -> bytes:
        return self.objects[sha256]


@dataclass
class Mapped:
    raw: bytes
    outcome: MapOutcome
    data: bytes
    info: SealInfo

    @property
    def records(self) -> list[dict[str, Any]]:
        return [json.loads(line) for line in self.data.splitlines()]

    def by_id(self) -> dict[str, dict[str, Any]]:
        return {r["id"]: r for r in self.records}

    def of_kind(self, kind: str) -> list[dict[str, Any]]:
        return [r for r in self.records if r["k"] == kind]

    @property
    def header(self) -> dict[str, Any]:
        return self.records[0]

    def issue_codes(self) -> list[str]:
        return [i["code"] for i in self.info.issues]

    def view_bytes(self) -> bytes:
        return serialise(render(self.records[:-1]))

    def validate(self, mode: str = "release") -> ValidationReport:
        profile = load_profile("adprov-v1")
        validator = AerValidator(store=_Store(self.raw), catalogues=RuleRegistry.default(), mode=mode,  # type: ignore[arg-type]
                                 profile_digests={(profile.id, profile.version): profile.sha256})
        for line in self.data.splitlines(keepends=True):
            validator.feed(line)
        return validator.finish()


def map_v1(raw: bytes, relpath: str = "corpus-prov/synthetic/prov/direct/x.transcript.json") -> Mapped:
    outcome, _unit = map_artefact(raw, corpus_origin(relpath), profile_id="adprov-v1")
    data, info = aer_bytes(outcome)
    return Mapped(raw, outcome, data, info)


def dump(doc: Mapping[str, Any]) -> bytes:
    """The baseline writer's serialisation (transcript.py:282-283)."""
    return json.dumps(doc, indent=2).encode("utf-8")


SYSTEM = "You are a helpful assistant (synthetic fixture)."


def released_doc(**meta_overrides: Any) -> dict[str, Any]:
    """A small released transcript/v1 document (the generator's key layout), built in code."""
    meta: dict[str, Any] = {
        "model": "synth",
        "model_id": "example/synthetic-model-1",
        "suite": "banking",
        "user_task_id": "user_task_1",
        "injection_task_id": "injection_task_2",
        "attack_type": "direct",
        "injections": {"vector_a": "PAYLOAD-A (synthetic)"},
        "utility": True,
        "security": False,
        "started_at": "2026-06-01T10:00:00.000001+00:00",
        "ended_at": "2026-06-01T10:00:05.5+00:00",
        "wall_clock_s": 5.5,
        "agentdojo_version": "0.1.35",
        "benchmark_version": "v1.2.2",
        "model_config": {
            "temperature": 0.0,
            "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120, "n_llm_calls": 2},
            "finish_reasons": ["tool_calls", "stop"],
        },
    }
    meta.update(meta_overrides)
    content = "result text (synthetic)"
    turns = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": "Do the synthetic task."},
        {"role": "assistant", "text": "", "tool_calls": [{"id": "call_1", "function": "get_balance", "args": {"z": 1, "a": 2.0}}]},
        {"role": "tool", "tool_call_id": "call_1", "function": "get_balance", "args": {"z": 1, "a": 2.0}, "content": content,
         "content_sha256": "sha256:" + hashlib.sha256(content.encode()).hexdigest(), "error": None,
         "started_at": "2026-06-01T10:00:01.000001+00:00", "ended_at": "2026-06-01T10:00:01.000002+00:00"},
        {"role": "assistant", "text": "Done."},
    ]
    return {"adprov_schema": "transcript/v1", "meta": meta, "turns": turns}


def converted_doc(**meta_overrides: Any) -> dict[str, Any]:
    """A small converted transcript/v1 document (convert_runs.run_to_meta layout)."""
    meta: dict[str, Any] = {
        "model": "pipe-x",
        "model_id": "pipe-x",
        "suite": "slack",
        "user_task_id": "user_task_3",
        "injection_task_id": "injection_task_1",
        "attack_type": "important_instructions",
        "injections": {"vector_b": "PAYLOAD-B (synthetic)"},
        "utility": False,
        "security": True,
        "started_at": None,
        "ended_at": None,
        "wall_clock_s": 2.0,
        "agentdojo_version": None,
        "benchmark_version": None,
        "source": "agentdojo_native_run_log",
        "pipeline_name": "pipe-x",
        "timing_stubbed": True,
    }
    meta.update(meta_overrides)
    content = "converted result (synthetic)"
    turns = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": "Do the converted task."},
        {"role": "assistant", "text": None, "tool_calls": [{"id": None, "function": "read_channel", "args": {"channel": "general"}}]},
        {"role": "tool", "tool_call_id": None, "function": "read_channel", "args": {"channel": "general"}, "content": content,
         "content_sha256": "sha256:" + hashlib.sha256(content.encode()).hexdigest(), "error": None,
         "started_at": "0", "ended_at": "0"},
        {"role": "assistant", "text": "All done."},
    ]
    return {"adprov_schema": "transcript/v1", "meta": meta, "turns": turns}


def tool_turn(call_id: Any, function: str, args: Any, content: str, *, error: Any = None, timing: tuple[str, str] | None = None,
              digest: str | None = None) -> dict[str, Any]:
    turn: dict[str, Any] = {"role": "tool", "tool_call_id": call_id, "function": function, "args": copy.deepcopy(args),
                            "content": content, "content_sha256": digest or "sha256:" + hashlib.sha256(content.encode()).hexdigest(),
                            "error": error}
    if timing is not None:
        turn["started_at"], turn["ended_at"] = timing
    return turn


@pytest.fixture(scope="session")
def golden_pairs() -> dict[str, Pair]:
    pairs = load_pairs()
    if not pairs:
        pytest.skip(golden.golden_skip_reason() or "golden fixtures not found")
    return {p.id: p for p in pairs}


@pytest.fixture(scope="session")
def map_golden(golden_pairs: dict[str, Pair]) -> Callable[[str], Mapped]:
    cache: dict[str, Mapped] = {}

    def get(pair_id: str) -> Mapped:
        if pair_id not in golden_pairs:
            pytest.skip(f"golden pair {pair_id} is not in this golden set")
        if pair_id not in cache:
            pair = golden_pairs[pair_id]
            raw = pair.transcript.read_bytes()
            golden.assert_matches_sha256(raw, pair.transcript_sha256, what=f"{pair_id} transcript")
            cache[pair_id] = map_v1(raw, pair.corpus_relpath)
        return cache[pair_id]

    return get


class V1Tools:
    """The helpers above, handed to tests as one fixture (``--import-mode=importlib`` forbids importing conftest)."""

    map = staticmethod(map_v1)
    dump = staticmethod(dump)
    released = staticmethod(released_doc)
    converted = staticmethod(converted_doc)
    tool_turn = staticmethod(tool_turn)
    origin = staticmethod(corpus_origin)
    Store = _Store


@pytest.fixture(scope="session")
def v1() -> type[V1Tools]:
    return V1Tools
