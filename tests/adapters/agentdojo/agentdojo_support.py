"""Helpers for the ``agentdojo.tracelogger`` adapter tests (docs/architecture D.6.10; K.6.2).

Real inputs: the native June-2024 logs N-C01…N-C09 of the golden index and the C.16.1 artefact
(``tests/fixtures/agentdojo/v0.k11/``), loaded programmatically. They are third-party data holding prompt-injection
payloads by design: no helper here prints their content (G.8.1 item 5; R-42). Every other test builds a synthetic
TraceLogger log in code, written the way ``TraceLogger.save`` writes it (``json.dumps(..., indent=4)``).
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


from agentprov.adapters.agentdojo.dialect import TraceLoggerReader
from agentprov.adapters.agentdojo.mapper import TraceLoggerMapper
from agentprov.adapters.profiles import SourceProfile, load_profile, parse_profile
from agentprov.adapters.runner import MapOutcome, aer_bytes, map_unit
from agentprov.adapters.types import ArtefactRef, ExecutionUnit, Origin
from agentprov.aer.rules import RuleRegistry
from agentprov.aer.validate import AerValidator, ValidationReport
from agentprov.aer.writer import SealInfo
from agentprov.ingest.limits import IngestLimits
from agentprov.testing import golden

REPO_URL = "https://github.com/ethz-spylab/agentdojo"
C274885 = "c274885610efaaafec38b6d3eb07152ba7ff3f94"
REPO = Path(__file__).resolve().parents[3]
PROFILE_PATH = REPO / "src" / "agentprov" / "adapters" / "agentdojo" / "profiles" / "agentdojo-upstream.profile.toml"
C161_PATH = "runs/gpt-4o-2024-05-13-transformers_pi_detector/banking/user_task_13/important_instructions/injection_task_7.json"
C161_SHA256 = "99e641af97e56971dd67308beec96ac08fdca7063141f3714389733ba845cc8a"
C161_BLOB = "4cbf084087345a813c6d93e99aa2d37eec2ca507"


def git_blob(data: bytes) -> str:
    return golden.git_blob_sha1(data)


class _Store:
    def __init__(self, raw: bytes) -> None:
        self.sha, self.raw = hashlib.sha256(raw).hexdigest(), raw

    def has(self, sha256: str) -> bool:
        return sha256 == self.sha

    def size(self, sha256: str) -> int:
        return len(self.raw)

    def read_bytes(self, sha256: str) -> bytes:
        return self.raw


@dataclass
class Mapped:
    raw: bytes
    outcome: MapOutcome
    data: bytes
    info: SealInfo
    profile: SourceProfile

    @property
    def records(self) -> list[dict[str, Any]]:
        return [json.loads(line) for line in self.data.splitlines()]

    @property
    def header(self) -> dict[str, Any]:
        return self.records[0]

    def get(self, rid: str) -> dict[str, Any]:
        return next(r for r in self.records if r.get("id") == rid)

    def of_kind(self, kind: str) -> list[dict[str, Any]]:
        return [r for r in self.records if r.get("k") == kind]

    @property
    def codes(self) -> list[str]:
        return [i["code"] for i in self.info.issues]

    def issues(self, code: str) -> list[dict[str, Any]]:
        return [i for i in self.info.issues if i["code"] == code]

    def validate(self) -> ValidationReport:
        validator = AerValidator(store=_Store(self.raw), catalogues=RuleRegistry.default(), mode="release",
                                 profile_digests={(self.profile.id, self.profile.version): self.profile.sha256})
        for line in self.data.splitlines(keepends=True):
            validator.feed(line)
        return validator.finish()


def map_bytes(raw: bytes, path: str, *, profile: SourceProfile | None = None, origin: Origin | None = None) -> Mapped:
    """Sniff, parse, map and seal ``raw`` as the pinned log at ``path`` (or under ``origin``)."""
    profile = profile or load_profile("agentdojo-upstream")
    reader, mapper = TraceLoggerReader(), TraceLoggerMapper()
    limits = IngestLimits()
    sniff = reader.sniff(raw, label=path, limits=limits)
    assert sniff.match, sniff.reasons
    origin = origin or Origin.git(REPO_URL, C274885, path, git_blob(raw))
    artefact = ArtefactRef("a0", hashlib.sha256(raw).hexdigest(), len(raw), "application/json", origin, "primary",
                           mapper.prov_primary(sniff.flags))  # type: ignore[arg-type]
    item = next(reader.parse(raw, artefact, limits=limits))
    outcome = map_unit(ExecutionUnit(item), mapper, profile)
    data, info = aer_bytes(outcome)
    return Mapped(raw, outcome, data, info, profile)


def log_bytes(doc: Mapping[str, Any]) -> bytes:
    """A log serialised as ``TraceLogger.save`` writes it (logging.py l. 247-263 @ c274885)."""
    return json.dumps(doc, indent=4).encode("utf-8")


SYSTEM = "You are a helpful assistant."


def base_log(**overrides: Any) -> dict[str, Any]:
    """A synthetic v0.k11 log: one call answered by id, then a final text reply (attacked, no defence)."""
    doc: dict[str, Any] = {
        "suite_name": "banking",
        "pipeline_name": "gpt-4o-2024-05-13",
        "user_task_id": "user_task_1",
        "injection_task_id": "injection_task_2",
        "attack_type": "important_instructions",
        "injections": {"vec_b": "payload B", "vec_a": "payload A"},
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": "Pay the bill."},
            {"role": "assistant", "content": None,
             "tool_calls": [{"function": "send_money", "args": {"recipient": "X", "amount": 10.0}, "id": "call_1"}]},
            {"role": "tool", "content": "done", "tool_call_id": "call_1",
             "tool_call": {"function": "send_money", "args": {"recipient": "X", "amount": 10.0}, "id": "call_1"}, "error": None},
            {"role": "assistant", "content": "Paid.", "tool_calls": None},
        ],
        "error": None,
        "utility": True,
        "security": False,
        "duration": 3.0,
    }
    doc.update(overrides)
    return doc


def path_of(doc: Mapping[str, Any], pipeline_dir: str | None = None) -> str:
    attack = doc.get("attack_type") or "none"
    return (f"runs/{pipeline_dir or doc['pipeline_name']}/{doc['suite_name']}/{doc['user_task_id']}/{attack}/"
            f"{doc.get('injection_task_id') or 'none'}.json")


def map_log(doc: Mapping[str, Any], *, pipeline_dir: str | None = None, profile: SourceProfile | None = None,
            path: str | None = None) -> Mapped:
    return map_bytes(log_bytes(doc), path or path_of(doc, pipeline_dir), profile=profile)


def june_entry() -> str:
    """The ``verified_code`` line of the profile that verifies the June-2024 code (c274885), as it stands in the file."""
    return next(ln for ln in PROFILE_PATH.read_text(encoding="utf-8").splitlines(keepends=True)
                if ln.lstrip().startswith('{ commit = "c274885610efaaafec38b6d3eb07152ba7ff3f94"'))


def profile_with(replace: Mapping[str, str]) -> SourceProfile:
    """The shipped profile with textual replacements (dev-only variants for tests)."""
    text = PROFILE_PATH.read_text(encoding="utf-8")
    for old, new in replace.items():
        assert old in text, old
        text = text.replace(old, new)
    return parse_profile(text.encode("utf-8"), source="test-variant")


def new_log(**overrides: Any) -> dict[str, Any]:
    return copy.deepcopy(base_log(**overrides))


def native_entries() -> list[golden.GoldenEntry]:
    return list(golden.native_logs()) if golden.golden_available() else []


def map_native(entry: golden.GoldenEntry) -> Mapped:
    o = entry.origin
    raw = entry.native_bytes()
    origin = Origin.git(o["repo"], o["commit"], o["path"], o["git_blob_sha1"])
    return map_bytes(raw, o["path"], origin=origin)


def c161_bytes() -> bytes:
    raw = (golden.fixtures_root() / "agentdojo" / "v0.k11" / C161_PATH).read_bytes()
    golden.assert_matches_sha256(raw, C161_SHA256, what="C.16.1 artefact")
    return raw
