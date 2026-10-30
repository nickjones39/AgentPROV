"""Helpers for the Mandate and survey-runs profile tests (``tests/adapters/agentdojo/test_mandate.py``, ``test_survey.py``;
docs/architecture D.6.15): synthetic v1.k14 logs, and the real fixtures under ``tests/fixtures/{mandate,survey}`` (byte-identical
blobs of the pinned repositories, loaded programmatically and never printed, R-42).
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from agentdojo_support import Mapped, base_log, map_bytes

from agentprov.adapters.profiles import load_profile
from agentprov.adapters.types import Origin
from agentprov.testing import golden

REPO = Path(__file__).resolve().parents[3]
FIXTURES = REPO / "tests" / "fixtures"
DIGESTS = Path(__file__).resolve().parent
REGEN = "AGENTPROV_REGEN_AGENTDOJO_AER"

SOURCES = {
    "mandate": {
        "profile": "mandate-agentdojo-eval",
        "repo": "https://github.com/jwilliamsc/mandate-agentdojo-eval",
        "commit": "fa62a977584962f7b4b24a40772a83345fd920d4",
        "licence": "MIT (Copyright (c) 2026 Mandate Labs; publisher unverified)",
    },
    "survey": {
        "profile": "survey-runs",
        "repo": "https://github.com/Forever-CodingNoob/agent-security-tools-survey",
        "commit": "89c4db2c949797fbb38c5bfed85dc82780ddbfe3",
        "licence": "CC-BY-4.0 (Jhih-Jhong Lin)",
    },
}


def blocks(text: str | None) -> list[dict[str, Any]]:
    return [{"type": "text", "content": text}]


def v1_log(**overrides: Any) -> dict[str, Any]:
    """The synthetic ``base_log`` as AgentDojo 0.1.35 writes it (content blocks, ``placeholder_args``; one send_money call
    answered by id, then a final text reply)."""
    doc = copy.deepcopy(base_log())
    for message in doc["messages"]:
        if message["content"] is not None:
            message["content"] = blocks(message["content"])
        for call in message.get("tool_calls") or ():
            call["placeholder_args"] = None
        if message["role"] == "tool":
            message["tool_call"]["placeholder_args"] = None
    doc["messages"][-1]["tool_calls"] = []
    doc.update(benchmark_version="v1.2.1", evaluation_timestamp="2026-08-17 10:22:40", agentdojo_package_version="0.1.35")
    doc.update(overrides)
    return doc


def call(function: str, args: dict[str, Any], call_id: str) -> dict[str, Any]:
    return {"function": function, "args": args, "id": call_id, "placeholder_args": None}


def turn(*calls: dict[str, Any], text: str | None = None) -> dict[str, Any]:
    return {"role": "assistant", "content": blocks(text) if text is not None else None, "tool_calls": list(calls)}


def result(c: dict[str, Any], text: str, error: str | None = None) -> dict[str, Any]:
    return {"role": "tool", "content": blocks(text), "tool_call_id": c["id"], "tool_call": c, "error": error}


def final(text: str = "Done.") -> dict[str, Any]:
    return {"role": "assistant", "content": blocks(text), "tool_calls": []}


def log_with(messages: list[dict[str, Any]], **overrides: Any) -> dict[str, Any]:
    doc = v1_log(**overrides)
    doc["messages"] = [doc["messages"][0], doc["messages"][1], *messages]
    return doc


def fixture_entries(name: str) -> list[dict[str, Any]]:
    root = FIXTURES / name
    if not (root / "SOURCE.json").is_file():
        pytest.skip(f"the {name} fixtures are not present")
    return list(json.loads((root / "SOURCE.json").read_bytes()))


def fixture_bytes(name: str, entry: dict[str, Any]) -> bytes:
    raw = (FIXTURES / name / entry["sample_file"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == entry["sha256"] and golden.git_blob_sha1(raw) == entry["git_blob_sha1"]
    return raw


def map_fixture(name: str, entry: dict[str, Any]) -> Mapped:
    src = SOURCES[name]
    origin = Origin.git(src["repo"], src["commit"], entry["original_path"], entry["git_blob_sha1"])
    return map_bytes(fixture_bytes(name, entry), entry["original_path"], profile=load_profile(src["profile"]), origin=origin)


def map_synthetic(profile_id: str, doc: dict[str, Any], path: str, *, repo: str | None = None, commit: str | None = None) -> Mapped:
    """A synthetic log mapped under profile ``profile_id`` at ``path`` (origin: the profile's pinned repository)."""
    name = "mandate" if profile_id.startswith("mandate") else "survey"
    src = SOURCES[name]
    raw = json.dumps(doc, indent=4).encode("utf-8")
    origin = Origin.git(repo or src["repo"], commit or src["commit"], path, golden.git_blob_sha1(raw))
    return map_bytes(raw, path, profile=load_profile(profile_id), origin=origin)


def ok(m: Mapped) -> None:
    report = m.validate()
    assert report.ok and report.passed, [(f.code, f.pointer) for f in report.errors]
