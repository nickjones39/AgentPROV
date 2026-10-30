"""The Inspect semantics profile ``inspect.agentharm@1`` for the survey's AgentHarm logs (docs/architecture D.9; C.14; R-37).

* **Tools are fail-closed.** AgentHarm's tool list is not available offline, so this version knows no tool (rule
  ``inspect.tools_fail_closed@1``, class I): every ``tool_call`` part and ``tool_execution`` gets ``role``
  ``["unknown"]``, every ``tool_result`` part gets ``integrity`` ``unknown``. There is no taint policy (``None``): with
  every request role unknown, a policy would mark every pair.
* **Outcomes.** One ``outcome`` annotation per ``judgement`` that records a value and whose origin is not
  ``harness_default`` (C.14.3), for the scorers in ``tables.toml`` (rule ``inspect.scorer_claim_table@1``, class I).
  The claim, ``score`` and ``scale`` come from the scorer table and the judgement; the claim for ``score`` depends on
  the AER's ``task.suite`` because its polarity does. A judgement of an unlisted scorer, a value outside its declared
  scale, or a missing value gets no annotation: no claim or polarity is guessed.

The profile reads only the AER. It imports only the standard library and ``agentprov.{aer,sem}``; no other adapter
family and no ``inspect_ai`` code (D.13.1).
"""

from __future__ import annotations

import tomllib
from collections.abc import Iterator, Mapping
from typing import TYPE_CHECKING, Any, Final

from agentprov.adapters.inspect.semantics.atia import PROFILE_ID as ATIA_ID
from agentprov.adapters.inspect.semantics.atia import InspectAtiaProfile
from agentprov.adapters.inspect.semantics.whistlebench import PROFILE_ID as WHISTLEBENCH_ID
from agentprov.adapters.inspect.semantics.whistlebench import InspectWhistleBenchProfile
from agentprov.aer.types import Json
from agentprov.sem.profiles import SemanticsProfileError
from agentprov.sem.types import CORE_OUTCOME_CLAIMS, Annotation, Premise, TaintPolicy

if TYPE_CHECKING:
    from agentprov.aer.reader import AerDocument

__all__ = ["PROFILE_ID", "InspectAgentHarmProfile", "build_profile"]

PROFILE_ID: Final = "inspect.agentharm"
_TABLES: Final = "tables.toml"
_RULE_TOOLS: Final = "inspect.tools_fail_closed@1"
_RULE_SCORER: Final = "inspect.scorer_claim_table@1"
_KINDS: Final = ("graded", "flag")
_SCALES: Final = ("unit_interval", "binary")


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


class InspectAgentHarmProfile:
    """``inspect.agentharm@1``: fail-closed tools and the AgentHarm scorer table."""

    ns: Mapping[str, Json] = {}

    def __init__(self, profile_id: str, version: int, files: Mapping[str, bytes], sha256: str) -> None:
        if profile_id != PROFILE_ID or version not in (1, 2) or _TABLES not in files:  # 2: on inspect v2 (D-31)
            raise SemanticsProfileError(f"not an Inspect semantics profile: {profile_id}@{version}")
        self._id, self._version, self._sha256 = profile_id, version, sha256
        doc = tomllib.loads(files[_TABLES].decode("utf-8"))
        policy = doc["tool_policy"]
        if policy["known_tools"] or policy["role"] != ["unknown"] or policy["integrity"] != "unknown":
            raise SemanticsProfileError("inspect.agentharm@1 knows no tool: every tool is fail-closed")
        self._scorers: dict[str, dict[str, Any]] = {}
        for entry in doc.get("scorer", []):
            name = entry["judgement"]
            claims = [entry["claim"], *entry.get("claim_by_suite", {}).values()]
            if (name in self._scorers or entry["kind"] not in _KINDS or entry["scale"] not in _SCALES
                    or any(not c.startswith("inspect.") or c in CORE_OUTCOME_CLAIMS for c in claims)):
                raise SemanticsProfileError(f"scorer {name!r}: malformed entry")
            self._scorers[name] = entry

    @property
    def id(self) -> str:
        return self._id

    @property
    def version(self) -> int:
        return self._version

    @property
    def sha256(self) -> str:
        return self._sha256

    @property
    def rules(self) -> Mapping[str, int]:
        return {"inspect": 1 if self.version == 1 else 2}  # @2: @1 on the inspect catalogue version 2 (D-31, option B)

    @property
    def taint_policy(self) -> TaintPolicy | None:
        return None

    # ---------------------------------------------------------------------------------------------- annotate
    def annotate(self, aer: AerDocument) -> Iterator[Annotation]:
        """Yield the annotations in AER file order (deterministic; reads only the AER)."""
        suite = aer.header.get("task", {}).get("suite")
        header_id = str(aer.header.get("id", "exec"))
        for rec in aer.records:
            kind = rec.get("k")
            if kind == "message" and isinstance(rec.get("parts"), list):
                mid = str(rec["id"])
                for index, part in enumerate(rec["parts"]):
                    if not isinstance(part, dict):
                        continue
                    if part.get("t") == "tool_call":
                        yield Annotation(f"{mid}#{index}", "role", ["unknown"], "I", (_RULE_TOOLS,),
                                         (Premise(mid, f"/parts/{index}/name"),))
                    elif part.get("t") == "tool_result":
                        yield Annotation(f"{mid}#{index}", "integrity", "unknown", "I", (_RULE_TOOLS,),
                                         (Premise(mid, f"/parts/{index}/t"),))
            elif kind == "tool_execution":
                yield Annotation(str(rec["id"]), "role", ["unknown"], "I", (_RULE_TOOLS,), (Premise(str(rec["id"]), "/name"),))
            elif kind == "judgement":
                annotation = self._outcome(rec, suite if isinstance(suite, str) else None, header_id)
                if annotation is not None:
                    yield annotation

    def _outcome(self, rec: Mapping[str, Any], suite: str | None, header_id: str) -> Annotation | None:
        value = rec.get("value")
        entry = self._scorers.get(str(rec.get("name")))
        if rec.get("origin") == "harness_default" or entry is None or value is None:
            return None  # C.14.3: never for a harness default; no claim for an unlisted scorer or an unrecorded value
        flag = entry["kind"] == "flag"
        if flag:
            if not (isinstance(value, bool) or (_is_number(value) and value in (0, 1))):
                return None
        elif not _is_number(value) or not 0 <= value <= 1:
            return None
        claim = entry["claim"]
        premises = [Premise(str(rec["id"]), "/name"), Premise(str(rec["id"]), "/value"), Premise(str(rec["id"]), "/origin")]
        by_suite = entry.get("claim_by_suite")
        if by_suite:
            claim = by_suite.get(suite, claim)
            premises.append(Premise(header_id, "/task/suite"))
        outcome: dict[str, Json] = {"claim": claim}
        if flag:
            outcome["holds"] = bool(value)
        if _is_number(value):
            outcome["score"] = value
        outcome["scale"] = entry["scale"]
        return Annotation(str(rec["id"]), "outcome", outcome, "I", (_RULE_SCORER,), tuple(premises))


def build_profile(profile_id: str, version: int, files: Mapping[str, bytes],
                  sha256: str) -> InspectAgentHarmProfile | InspectWhistleBenchProfile | InspectAtiaProfile:
    """The entry point of :func:`agentprov.adapters.semantics_profiles.load_semantics_profile` (C.14.1).
    ``inspect.whistlebench`` lives in :mod:`agentprov.adapters.inspect.semantics.whistlebench` (D-601 addendum) and
    ``inspect.atia`` in :mod:`agentprov.adapters.inspect.semantics.atia` (D-307 addendum)."""
    if profile_id == WHISTLEBENCH_ID:
        return InspectWhistleBenchProfile(profile_id, version, files, sha256)
    if profile_id == ATIA_ID:
        return InspectAtiaProfile(profile_id, version, files, sha256)
    return InspectAgentHarmProfile(profile_id, version, files, sha256)
