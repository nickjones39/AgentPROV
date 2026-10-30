"""Regeneration-batch item 55 (core review D, CD-33): the reference family never truncates silently.

A hand-off whose sub-agent file is not expanded (the nesting limit of 4, or a cycle back to a file already on the
hand-off chain) raises ``foobench.handoff_not_expanded`` on the hand-off's execution and still cites the file.
Units are built in memory from synthetic traces (never committed).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from agentprov.adapters.foobench.dialect import FooJsonlReader
from agentprov.adapters.foobench.mapper import FooMapper
from agentprov.adapters.profiles import load_profile
from agentprov.adapters.runner import aer_bytes, map_unit
from agentprov.adapters.types import ArtefactRef, ExecutionUnit, Origin
from agentprov.aer.rules import RuleRegistry
from agentprov.ingest.limits import IngestLimits

COMMIT = "ce45a3d560629e2ec6fa9633315eb1afa187891c"


def _lines(events: list[dict[str, Any]]) -> bytes:
    return b"".join(json.dumps(e, separators=(",", ":")).encode() + b"\n" for e in events)


def _ref(aid: str, name: str, data: bytes, role: str) -> ArtefactRef:
    sha1 = hashlib.sha1(b"blob %d\0" % len(data) + data, usedforsecurity=False).hexdigest()
    origin = Origin.git("https://github.com/nickjones39/AgentPROV", COMMIT, f"x/{name}", sha1)
    return ArtefactRef(aid, hashlib.sha256(data).hexdigest(), len(data), "application/x-ndjson", origin, role, "native")


def _handoff(i: int, sub_file: str | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = [
        {"type": "llm_request", "id": f"r{i}", "actor": "agent",
         "add": [{"id": f"u{i}", "role": "user", "author": "user", "text": "go"}], "context": [f"u{i}"]},
        {"type": "llm_response", "request": f"r{i}",
         "reply": {"id": f"a{i}", "role": "assistant", "calls": [{"id": f"c{i}", "name": "transfer", "args": {}}]}},
    ]
    if sub_file is not None:
        out.append({"type": "handoff", "call": f"c{i}", "name": "transfer", "to": "researcher", "sub_file": sub_file,
                    "result": "done"})
    return out


def _map(subs: dict[str, str | None]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """``subs`` maps each sub-agent file to the file it hands off to (``None``: no hand-off); the primary hands off to
    ``sub-a.jsonl``."""
    primary = _lines([{"schema": "foobench/1", "task": "t1", "agent_model": "m"}, *_handoff(0, "sub-a.jsonl")])
    files = {name: _lines([{"schema": "foobench/1", "parent": {"run": "x"}}, *_handoff(n + 1, target)])
             for n, (name, target) in enumerate(sorted(subs.items()))}
    ref = _ref("a0", "p.jsonl", primary, "primary")
    (item,) = list(FooJsonlReader().parse(primary, ref, limits=IngestLimits()))
    unit = ExecutionUnit(primary=item, auxiliary={name: _ref(f"a{n + 1}", name, data, "supporting")
                                                  for n, (name, data) in enumerate(sorted(files.items()))})
    profile, registry = load_profile("foobench"), RuleRegistry.default()
    outcome = map_unit(unit, FooMapper(), profile, registry=registry, auxiliary=files)
    data, info = aer_bytes(outcome, registry=registry, unit=unit, mapper=FooMapper(), profile=profile)
    assert not outcome.degenerate
    return [json.loads(line) for line in data.splitlines()], list(info.issues)


def _not_expanded(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [i for i in issues if i["code"] == "foobench.handoff_not_expanded"]


def test_a_handoff_cycle_is_expanded_once_and_reported():
    records, issues = _map({"sub-a.jsonl": "sub-a.jsonl"})
    subagents = [r for r in records if r["k"] == "scope" and r.get("kind") == "subagent"]
    assert len(subagents) == 2  # sub-a's scope, and the scope of its hand-off back to itself (not expanded)
    [issue] = _not_expanded(issues)
    assert issue["ids"] == [subagents[-1]["spawned_by"]] and "cycle" in issue["detail"]


def test_a_handoff_beyond_the_nesting_limit_is_reported_and_cited():
    chain = {"sub-a.jsonl": "sub-b.jsonl", "sub-b.jsonl": "sub-c.jsonl", "sub-c.jsonl": "sub-d.jsonl",
             "sub-d.jsonl": "sub-e.jsonl", "sub-e.jsonl": None}
    records, issues = _map(chain)
    [issue] = _not_expanded(issues)
    assert "nesting limit 4" in issue["detail"]
    assert len(records[0]["artifacts"]) == 6  # every supplied file is cited, the unexpanded sub-e.jsonl too


def test_a_handoff_within_the_limit_raises_nothing():
    _records, issues = _map({"sub-a.jsonl": "sub-b.jsonl", "sub-b.jsonl": None})
    assert _not_expanded(issues) == []
