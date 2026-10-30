"""The Inspect semantics profile ``inspect.atia@1`` for the ATIA logs (docs/architecture D.9.15, D.9.10; C.14;
DECISIONS D-307 addendum: orchestrator request 2026-10-21; fail-closed like D-601's ``inspect.whistlebench@1``).

* **Tools are fail-closed.** The code that ran (task, solver ``use_sample_tools`` and its tool registry) is not
  available at a pinned identity: the logs' header revisions are not public, and the files at the pinned commit lie
  outside the pinned ``logs/`` tree and post-date the logs. So this version knows no tool (rule
  ``inspect.untabulated_tool@1``, class I). Every ``tool_call`` part and ``tool_execution`` gets ``role``
  ``["unknown"]``, and every ``tool_result`` part gets ``integrity`` ``unknown``. There is no taint policy. The samples'
  ``harmful_tools`` and ``benign_tools`` metadata is a benchmark label, not tool code, and is not read.
* **No outcome.** The scorer ``harmful_tool_invoked`` records ``C`` or ``I``; its code is not available at a pinned
  identity, and its polarity is inverted in the two status-``error`` logs (pre-check PC-atia-benchmark-01). The scorer
  table is empty, so no judgement gets an outcome annotation: no claim or polarity is guessed from a name or a value.

The profile reads only the AER. It imports only the standard library and ``agentprov.{aer,sem}``; no other adapter
family and no ``inspect_ai`` code (D.13.1).
"""

from __future__ import annotations

import tomllib
from collections.abc import Iterator, Mapping
from typing import TYPE_CHECKING, Final

from agentprov.aer.types import Json
from agentprov.sem.profiles import SemanticsProfileError
from agentprov.sem.types import Annotation, Premise, TaintPolicy

if TYPE_CHECKING:
    from agentprov.aer.reader import AerDocument

__all__ = ["PROFILE_ID", "InspectAtiaProfile"]

PROFILE_ID: Final = "inspect.atia"
#: The inspect rule catalogue version each profile version cites (H.2.5: one catalogue version per corpus).
CATALOGUE_OF: Final[Mapping[int, int]] = {1: 2}
_TABLES: Final = "tables.toml"
_RULE_TOOLS: Final = "inspect.untabulated_tool@1"


class InspectAtiaProfile:
    """``inspect.atia@1``: fail-closed tools, no scorer claims."""

    ns: Mapping[str, Json] = {}

    def __init__(self, profile_id: str, version: int, files: Mapping[str, bytes], sha256: str) -> None:
        if profile_id != PROFILE_ID or version not in CATALOGUE_OF or set(files) != {_TABLES}:
            raise SemanticsProfileError(f"not the ATIA semantics profile: {profile_id}@{version}")
        self._id, self._version, self._sha256 = profile_id, version, sha256
        doc = tomllib.loads(files[_TABLES].decode("utf-8"))
        if set(doc) != {"tool_policy"}:
            raise SemanticsProfileError("inspect.atia@1 holds a tool policy only (no scorer table)")
        policy = doc["tool_policy"]
        if policy != {"known_tools": [], "role": ["unknown"], "integrity": "unknown"}:
            raise SemanticsProfileError("inspect.atia@1 knows no tool: every tool is fail-closed")

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
        return {"inspect": CATALOGUE_OF[self._version]}

    @property
    def taint_policy(self) -> TaintPolicy | None:
        return None

    def annotate(self, aer: AerDocument) -> Iterator[Annotation]:
        """Yield the annotations in AER file order (deterministic; reads only the AER)."""
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
