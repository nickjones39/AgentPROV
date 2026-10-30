"""The Inspect semantics profile ``inspect.whistlebench`` for the WhistleBench logs (docs/architecture D.9.14; C.14;
DECISIONS D-601 addenda).

* **Version 1** (as recorded): every tool is fail-closed (rule ``inspect.untabulated_tool@1``, class I) and no judgement
  gets an outcome, since the task and scorer code was not available at the pin.
* **Version 2**: the tool table and the scorer table read from the pinned ``highagency/`` code (each entry cites a path
  and a git blob id; class I, since the logs' producing commits are not in the pinned history):

  - a listed tool gets the table's roles (``tool_call`` part, ``tool_execution``) and output integrity (``tool_result``
    part) under ``inspect.tool_table@1``; an unlisted tool is fail-closed under ``inspect.unknown_tool@1``;
  - a recorded, non-default judgement whose name and AER ``task.suite`` the scorer table lists, and whose value is the
    letter grade ``C`` or ``I``, gets an ``outcome`` with the table's claim and ``holds`` (true for ``C``) under
    ``inspect.scorer_letter_table@1``. Anything else gets no outcome: no claim or polarity is guessed.

There is no taint policy (the benchmark has no attacker, D-147). The profile reads only the AER. It imports only the
standard library and ``agentprov.{aer,sem}``; no other adapter family and no ``inspect_ai`` or benchmark code (D.13.1).
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Iterator, Mapping
from typing import TYPE_CHECKING, Any, Final

from agentprov.aer.types import Json
from agentprov.sem.profiles import SemanticsProfileError
from agentprov.sem.types import CORE_OUTCOME_CLAIMS, INTEGRITY_VALUES, ROLE_VALUES, Annotation, Premise, TaintPolicy

if TYPE_CHECKING:
    from agentprov.aer.reader import AerDocument

__all__ = ["PROFILE_ID", "InspectWhistleBenchProfile"]

PROFILE_ID: Final = "inspect.whistlebench"
#: The inspect rule catalogue version each profile version cites (H.2.5: one catalogue version per corpus).
CATALOGUE_OF: Final[Mapping[int, int]] = {1: 2, 2: 2}
_TABLES: Final = "tables.toml"
_RULE_UNTABULATED: Final = "inspect.untabulated_tool@1"
_RULE_TOOL_TABLE: Final = "inspect.tool_table@1"
_RULE_UNKNOWN_TOOL: Final = "inspect.unknown_tool@1"
_RULE_SCORER: Final = "inspect.scorer_letter_table@1"
_LETTERS: Final = {"C": True, "I": False}
_BLOB: Final = re.compile(r"[0-9a-f]{40}")
_LINES: Final = re.compile(r"[1-9][0-9]*(-[1-9][0-9]*)?(, [1-9][0-9]*(-[1-9][0-9]*)?)*")
_CLAIM: Final = re.compile(r"inspect\.[a-z][a-z0-9_]*")


def _code(entry: Mapping[str, Any], at: str) -> None:
    """Every table entry cites code by path, git blob id and line range (D-601 addendum 2)."""
    code = entry.get("code")
    if not isinstance(code, list) or not code:
        raise SemanticsProfileError(f"{at}: cites no code")
    for c in code:
        if (not isinstance(c, Mapping) or set(c) - {"path", "blob", "lines", "note"}
                or not isinstance(c.get("path"), str) or not c["path"].startswith("highagency/")
                or not isinstance(c.get("blob"), str) or _BLOB.fullmatch(c["blob"]) is None
                or not isinstance(c.get("lines"), str) or _LINES.fullmatch(c["lines"]) is None):
            raise SemanticsProfileError(f"{at}: a code citation is {{path, blob, lines, note?}}")


class InspectWhistleBenchProfile:
    """``inspect.whistlebench@1`` (fail-closed) and ``@2`` (tool and scorer tables)."""

    ns: Mapping[str, Json] = {}

    def __init__(self, profile_id: str, version: int, files: Mapping[str, bytes], sha256: str) -> None:
        if profile_id != PROFILE_ID or version not in CATALOGUE_OF or set(files) != {_TABLES}:
            raise SemanticsProfileError(f"not the WhistleBench semantics profile: {profile_id}@{version}")
        self._id, self._version, self._sha256 = profile_id, version, sha256
        doc = tomllib.loads(files[_TABLES].decode("utf-8"))
        self._tools: dict[str, tuple[list[str], str]] = {}
        self._scorers: dict[str, tuple[frozenset[str], str]] = {}
        if version == 1:
            if set(doc) != {"tool_policy"}:
                raise SemanticsProfileError("inspect.whistlebench@1 holds a tool policy only (no scorer table)")
            if doc["tool_policy"] != {"known_tools": [], "role": ["unknown"], "integrity": "unknown"}:
                raise SemanticsProfileError("inspect.whistlebench@1 knows no tool: every tool is fail-closed")
            return
        if set(doc) - {"code", "tool", "scorer"} or not isinstance(doc.get("code"), Mapping):
            raise SemanticsProfileError("inspect.whistlebench@2 holds [code], [[tool]] and [[scorer]] only")
        for i, entry in enumerate(doc.get("tool", [])):
            at = f"tool[{i}]"
            name, roles, integrity = entry.get("name"), entry.get("roles"), entry.get("integrity")
            if (set(entry) - {"name", "roles", "integrity", "code", "reason"} or not isinstance(name, str)
                    or name in self._tools or not isinstance(roles, list) or not roles
                    or not all(r in ROLE_VALUES and r != "unknown" for r in roles)
                    or integrity not in INTEGRITY_VALUES or integrity == "trusted"
                    or not isinstance(entry.get("reason"), str)):
                raise SemanticsProfileError(f"{at}: malformed tool entry (integrity is never trusted)")
            _code(entry, at)
            self._tools[name] = (list(roles), str(integrity))
        for i, entry in enumerate(doc.get("scorer", [])):
            at = f"scorer[{i}]"
            name, suites, claim = entry.get("judgement"), entry.get("suites"), entry.get("claim")
            if (set(entry) - {"judgement", "suites", "claim", "code", "reason"} or not isinstance(name, str)
                    or name in self._scorers or not isinstance(suites, list) or not suites
                    or not all(isinstance(s, str) and s for s in suites)
                    or not isinstance(claim, str) or _CLAIM.fullmatch(claim) is None or claim in CORE_OUTCOME_CLAIMS
                    or not isinstance(entry.get("reason"), str)):
                raise SemanticsProfileError(f"{at}: malformed scorer entry (a namespaced claim, listed suites)")
            _code(entry, at)
            self._scorers[name] = (frozenset(suites), claim)

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

    def _tool(self, name: object) -> tuple[list[Json], str, str]:
        if self._version == 1:
            return ["unknown"], "unknown", _RULE_UNTABULATED
        found = self._tools.get(name) if isinstance(name, str) else None
        if found is None:
            return ["unknown"], "unknown", _RULE_UNKNOWN_TOOL
        return [*found[0]], found[1], _RULE_TOOL_TABLE

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
                        roles, _integrity, rule = self._tool(part.get("name"))
                        yield Annotation(f"{mid}#{index}", "role", roles, "I", (rule,),
                                         (Premise(mid, f"/parts/{index}/name"),))
                    elif part.get("t") == "tool_result":
                        _roles, integrity, rule = self._tool(part.get("name"))
                        premises = [Premise(mid, f"/parts/{index}/t")]
                        if rule == _RULE_TOOL_TABLE:
                            premises.append(Premise(mid, f"/parts/{index}/name"))
                        yield Annotation(f"{mid}#{index}", "integrity", integrity, "I", (rule,), tuple(premises))
            elif kind == "tool_execution":
                roles, _integrity, rule = self._tool(rec.get("name"))
                yield Annotation(str(rec["id"]), "role", roles, "I", (rule,), (Premise(str(rec["id"]), "/name"),))
            elif kind == "judgement" and self._scorers:
                annotation = self._outcome(rec, suite if isinstance(suite, str) else None, header_id)
                if annotation is not None:
                    yield annotation

    def _outcome(self, rec: Mapping[str, Any], suite: str | None, header_id: str) -> Annotation | None:
        entry = self._scorers.get(str(rec.get("name")))
        value = rec.get("value")
        if (rec.get("origin") == "harness_default" or entry is None or suite not in entry[0]
                or not isinstance(value, str) or value not in _LETTERS):
            return None  # C.14.3: never for a harness default; no claim for an unlisted scorer, suite or value
        rid = str(rec["id"])
        premises = (Premise(rid, "/name"), Premise(rid, "/value"), Premise(rid, "/origin"), Premise(header_id, "/task/suite"))
        return Annotation(rid, "outcome", {"claim": entry[1], "holds": _LETTERS[value]}, "I", (_RULE_SCORER,), premises)
