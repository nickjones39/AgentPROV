"""Gate R3: the field-level diff of the native and the converted (v1) AER of one AgentDojo run (J.4.3, J.4.4).

The converted tree of the frozen baseline (``corpus-og-agentdojo-runs-prov``) was produced by AgentDojo-PROV's converter
from the June-2024 TraceLogger logs. Gates R1/R2 compare the bytes of the views; R3 compares the two **records**:
``project(AER_native)`` against ``project(AER_v1)``, one comparison record per execution, keyed by position (record
index per kind, message and part index), and classifies every field:

* ``equal``: present on both sides with the same JSON value;
* ``native_only`` / ``v1_only``: present on one side only;
* ``differs_expected(<rule>)``: present on both sides, different, and explained by a J.4.4 row;
* ``differs_unexpected``: anything else. R3 passes when there is none and every lineage record agrees (it is
  "reported", J.4.3: it never blocks a release).

A field present on one side only is counted under the J.4.4 row that explains it (:data:`EXPECTED_PRESENCE`); one that
no row names is reported as ``unexplained`` presence, never hidden.

**The projection.** Every record but the seal, minus the members that differ by design (J.4.4 row 1: ids, artefact
origins, the source key, the adapter and profile, rule citations and evidence metadata; ``ev``/``by`` except for
linkage), flattened to paths ``<kind>[<n>]/<member>/...``. The skip applies to a record's own members and to the ids
its ``after``/``input``/``related`` items name; payload below them (``args``, ``returned``, ``value``, ``ext``) is
compared member by member, whatever the member is called. Actor records are keyed by their id (``actors/<id>/...``):
both importers use the same role labels (``bench``, ``user``, ``agent``, ``env``, ``att``, ``def<n>``), so a reference
compares as the id it names.

**Lineage** (J.4.3): one record per matched pair, ``{v1_sha256, native_sha256, upstream_commit, upstream_path,
upstream_blob_sha1, rule, verdict}``; ``verdict`` is ``agree`` when the v1 AER's ``ext.adprov.derived_from_upstream``
names the native origin's repository, commit and path and the v1 AER carries no ``adprov.upstream_link_unresolved``.

Reads sealed AER records only (outputs of this package, not raw source). The report holds field patterns, counts,
digests and paths, never source text.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

__all__ = [
    "EXPECTED_DIFFERENCES",
    "EXPECTED_PRESENCE",
    "LINEAGE_RULE",
    "REPORT_FORMAT",
    "ReconciliationReport",
    "classify",
    "lineage",
    "pattern_of",
    "project",
]

LINEAGE_RULE: Final = "migration.converted_v1_from_native@1"
REPORT_FORMAT: Final = "agentprov-reconciliation/0.1"
#: Record members that differ by design (J.4.4 row 1; AD-04) or are evidence metadata: never compared. Applied to a
#: record's top-level members only; below them every member is compared by name, whatever it is called (tool-call and
#: tool-execution ``args``, ``returned``, ``value``, ``ext.<ns>`` are payload, CB-28).
_SKIP: Final = frozenset({
    "id", "ev", "evf", "by", "rule", "src", "unk", "hash", "canon", "ns", "aer", "adapter", "profile", "rules",
    "source_key", "ex", "artifacts", "dialect", "k",
})
#: Nested reference members that differ by design (J.4.4 row 1): ``<list member>`` -> the item members never compared
#: (the record ids an ``after`` edge or an object-form ``input`` item names; the cross-execution ids of ``related``).
_SKIP_ITEM: Final[Mapping[str, frozenset[str]]] = {
    "after": frozenset({"id"}),
    "input": frozenset({"id"}),
    "related": frozenset({"ex", "id"}),
}
_INDEX: Final = re.compile(r"\[\d+\]")
_POSITION: Final = re.compile(r"/\d+(?=/|$)")
_DEFENCE: Final = re.compile(r"^actors/def[0-9]+/")

#: J.4.4 rows for fields present on one side only: (category, field pattern) -> the row.
EXPECTED_PRESENCE: Final[Mapping[tuple[str, str], str]] = {
    ("native_only", "execution[*]/task/defense_id"): "pipeline/model/defence split",
    ("native_only", "actors/agent/model/requested"): "pipeline/model/defence split",
    ("native_only", "execution[*]/ext/agentdojo/error"): "run-level error (compared with ext.adprov.run_error)",
    ("v1_only", "execution[*]/ext/adprov/run_error"): "run-level error (compared with ext.agentdojo.error)",
    ("native_only", "execution[*]/ext/agentdojo/task_kind"): "benign attack label (SEM task-kind typing)",
    ("native_only", "message[*]/ext/agentdojo/calls_form"): "no-calls encoding",
    ("native_only", "message[*]/ext/agentdojo/content_state"): "no-calls encoding (source form of the content)",
    ("native_only", "message[*]/ext/agentdojo/tool_call_id"): "tool-call id status",
    ("v1_only", "message[*]/parts/*/provider_call_id"): "tool-call id status",
    ("v1_only", "tool_execution[*]/t/raw/start"): "tool timing (t.raw stub)",
    ("v1_only", "tool_execution[*]/t/raw/end"): "tool timing (t.raw stub)",
    ("native_only", "scope[*]/index"): "inferred passes (D.6.11 item 14)",
    # regeneration-batch item 5 (D-370): the TraceLogger mapper's environment load; the v2.3 converter wrote no such record
    ("native_only", "activity[*]/actor"): "environment load (regeneration-batch item 5)",
    ("native_only", "activity[*]/inputs/*"): "environment load (regeneration-batch item 5)",
    ("native_only", "activity[*]/scope"): "environment load (regeneration-batch item 5)",
    ("native_only", "activity[*]/type"): "environment load (regeneration-batch item 5)",
    ("native_only", "scope[*]/ext/agentdojo/pre_state_not_initial"): "inferred passes (D.6.11 item 14)",
    ("native_only", "tool_execution[*]/after/*/b"): "causal order basis (native source evidence)",
    ("native_only", "message[*]/ext/agentdojo/copy_of"): "defence-authored messages (repeat_user_prompt copies, D.6.6)",
    ("native_only", "message[*]/ext/agentdojo/system_prompt_variant"): "the system prompt's code state by digest (D-207)",
}
#: Prefixes that are one-sided by construction: the v1 importer's own record of the transcript (J.4.4 row 1, lineage)
#: and lexical hints of the v1 bytes (``ext.lex``, C.11.4).
_ONE_SIDED_PREFIXES: Final[Sequence[tuple[str, str, str]]] = (
    ("v1_only", "actors/harness/", "v1 importer record (the converter as harness actor)"),
    ("native_only", "actors/def*/", "pipeline/model/defence split (the defence actor)"),
    ("v1_only", "execution[*]/ext/adprov/", "v1 importer record (ext.adprov; lineage)"),
    ("v1_only", "message[*]/ext/adprov/", "v1 importer record (ext.adprov)"),
    ("v1_only", "tool_execution[*]/ext/adprov/", "v1 importer record (ext.adprov)"),
    ("v1_only", "execution[*]/ext/lex/", "v1 lexical hints (ext.lex)"),
    ("v1_only", "scope[*]/ext/lex/", "v1 lexical hints (ext.lex)"),
    ("v1_only", "message[*]/ext/lex/", "v1 lexical hints (ext.lex)"),
    ("v1_only", "tool_execution[*]/ext/lex/", "v1 lexical hints (ext.lex)"),
    ("native_only", "message[*]/ext/lex/", "native lexical hints (ext.lex)"),
    ("native_only", "tool_execution[*]/ext/lex/", "native lexical hints (ext.lex)"),
)


def _rounding(native: Any, v1: Any) -> bool:
    numbers = (int, float)
    return (isinstance(native, numbers) and isinstance(v1, numbers) and not isinstance(native, bool)
            and abs(float(native) - float(v1)) <= 0.0005)


def _auxiliary_call(native: Any, v1: Any) -> bool:
    """J.4.4 "defence-authored messages": the ``tool_filter`` defence's own model call is ``auxiliary`` in the native
    import (``agentdojo.tool_filter_aux_message@1``) and an ``agent`` call in the v1 import."""
    return native == "auxiliary" and v1 == "agent"


def _null_to_benign(native: Any, v1: Any) -> bool:
    return native is None and v1 == "benign"


def _defence_attribution(native: Any, v1: Any) -> bool:
    """J.4.4 "defence-authored messages": the native import attributes the ``tool_filter`` prompt and output to the
    defence actor ``def<n>`` (rule ``agentdojo.tool_filter_aux_message@1``); the v1 importer attributes them by role."""
    return isinstance(native, str) and re.fullmatch(r"def[0-9]+", native) is not None and v1 in ("user", "agent")


#: J.4.4 rows for fields present on both sides with different values: pattern -> (rule, predicate(native, v1)).
EXPECTED_DIFFERENCES: Final[Mapping[str, tuple[str, Callable[[Any, Any], bool]]]] = {
    "scope[*]/t/dur_s": ("rounding", _rounding),
    "execution[*]/task/attack_id": ("null->benign", _null_to_benign),
    "message[*]/actor": ("defence attribution", _defence_attribution),
    "model_call[*]/actor": ("defence attribution", _defence_attribution),
    "model_call[*]/role": ("defence attribution (auxiliary call)", _auxiliary_call),
}


def pattern_of(path: str) -> str:
    """A field path with record and array indices replaced by ``*`` (the report's unit); a defence actor ``def<n>`` is
    ``def*``."""
    return _DEFENCE.sub("actors/def*/", _POSITION.sub("/*", _INDEX.sub("[*]", path)))


def _flat(value: Any, path: str, out: dict[str, Any], skip: frozenset[str] = frozenset()) -> None:
    if isinstance(value, Mapping):
        for name, item in value.items():
            if name not in skip:
                _flat(item, f"{path}/{name}", out)
    elif isinstance(value, list):
        for n, item in enumerate(value):
            _flat(item, f"{path}/{n}", out)
    else:
        out[path] = value


def project(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """The comparison record of one AER (see the module docstring): field path -> JSON scalar."""
    out: dict[str, Any] = {}
    counts: Counter[str] = Counter()
    for record in records:
        kind = str(record.get("k"))
        if kind == "seal":
            continue
        if kind == "actor":
            _record(record, f"actors/{record.get('id')}", out)
            continue
        _record(record, f"{kind}[{counts[kind]}]", out)
        counts[kind] += 1
    return out


def _record(record: Mapping[str, Any], path: str, out: dict[str, Any]) -> None:
    """One record minus :data:`_SKIP` (top level only) and the :data:`_SKIP_ITEM` reference members."""
    for name, item in record.items():
        if name in _SKIP:
            continue
        drop = _SKIP_ITEM.get(name)
        if drop is not None and isinstance(item, list):
            for n, entry in enumerate(item):
                _flat(entry, f"{path}/{name}/{n}", out, drop)
        else:
            _flat(item, f"{path}/{name}", out)


def _presence(category: str, pattern: str) -> str:
    row = EXPECTED_PRESENCE.get((category, pattern))
    if row is not None:
        return row
    return next((r for side, prefix, r in _ONE_SIDED_PREFIXES if side == category and pattern.startswith(prefix)),
                "unexplained")


def classify(native: Mapping[str, Any], v1: Mapping[str, Any]) -> Counter[tuple[str, str, str]]:
    """Every field of one pair: ``(category, field pattern, J.4.4 row or rule)`` -> count."""
    out: Counter[tuple[str, str, str]] = Counter()
    for path in sorted(set(native) | set(v1)):
        pattern = pattern_of(path)
        if path not in v1:
            out[("native_only", pattern, _presence("native_only", pattern))] += 1
        elif path not in native:
            out[("v1_only", pattern, _presence("v1_only", pattern))] += 1
        elif native[path] == v1[path] and type(native[path]) is type(v1[path]):
            out[("equal", pattern, "")] += 1
        else:
            expected = EXPECTED_DIFFERENCES.get(pattern)
            if expected is not None and expected[1](native[path], v1[path]):
                out[("differs_expected", pattern, expected[0])] += 1
            else:
                out[("differs_unexpected", pattern, "")] += 1
    error_native = native.get("execution[0]/ext/agentdojo/error")
    error_v1 = v1.get("execution[0]/ext/adprov/run_error")
    if error_native is not None or error_v1 is not None:  # J.4.4 "run-level error": one fact, two homes
        same = (error_native is None) == (error_v1 is None)
        out[("equal" if same else "differs_unexpected", "run-level error", "")] += 1
    return out


@dataclass
class ReconciliationReport:
    """R3 over many pairs: per-category counts by field pattern, the unexplained cases and the lineage records."""

    pairs: int = 0
    categories: Counter[tuple[str, str, str]] = field(default_factory=Counter)
    unexplained: Counter[str] = field(default_factory=Counter)  # "<category>:<pattern>" -> pairs
    unexplained_items: dict[str, list[str]] = field(default_factory=dict)  # -> the first five items (labels only)
    lineage: list[dict[str, Any]] = field(default_factory=list)
    lineage_verdicts: Counter[str] = field(default_factory=Counter)

    def add(self, item: str, native: Mapping[str, Any], v1: Mapping[str, Any], record: Mapping[str, Any]) -> None:
        self.pairs += 1
        for (category, pattern, rule), n in classify(native, v1).items():
            self.categories[(category, pattern, rule)] += n
            if category == "differs_unexpected" or rule == "unexplained":
                key = f"{category}:{pattern}"
                self.unexplained[key] += 1
                firsts = self.unexplained_items.setdefault(key, [])
                if len(firsts) < 5:
                    firsts.append(item)
        self.lineage.append(dict(record))
        self.lineage_verdicts[str(record.get("verdict"))] += 1

    @property
    def passed(self) -> bool:
        """No ``differs_unexpected`` field and every lineage record agrees (J.4.3)."""
        return (not any(c == "differs_unexpected" for c, _p, _r in self.categories)
                and set(self.lineage_verdicts) <= {"agree"})

    def to_json(self, *, with_lineage: bool = False) -> dict[str, Any]:
        by_category: Counter[str] = Counter()
        for (category, _pattern, _rule), n in self.categories.items():
            by_category[category] += n
        out: dict[str, Any] = {
            "format": REPORT_FORMAT, "gate": "R3", "pairs": self.pairs, "passed": self.passed,
            "by_category": dict(sorted(by_category.items())),
            "fields": [{"category": c, "pattern": p, "rule": r, "count": n} for (c, p, r), n in sorted(self.categories.items())],
            "unexplained": [{"key": k, "pairs": n, "first_items": self.unexplained_items.get(k, [])}
                            for k, n in sorted(self.unexplained.items())],
            "lineage_rule": LINEAGE_RULE, "lineage_verdicts": dict(sorted(self.lineage_verdicts.items())),
        }  # fmt: skip
        if with_lineage:
            out["lineage"] = sorted(self.lineage, key=lambda r: str(r.get("upstream_path")))
        return out


def lineage(native_header: Mapping[str, Any], v1_header: Mapping[str, Any], *, native_sha256: str, v1_sha256: str,
            v1_issue_codes: Iterable[str]) -> dict[str, Any]:
    """The J.4.3 lineage record of one matched pair."""
    origin = ((native_header.get("artifacts") or [{}])[0] or {}).get("origin") or {}
    link = ((v1_header.get("ext") or {}).get("adprov") or {}).get("derived_from_upstream") or {}
    agree = (link.get("repo") == origin.get("repo") and link.get("commit") == origin.get("commit")
             and link.get("path") == origin.get("path") and "adprov.upstream_link_unresolved" not in set(v1_issue_codes))
    return {
        "v1_sha256": v1_sha256, "native_sha256": native_sha256, "upstream_commit": origin.get("commit"),
        "upstream_path": origin.get("path"), "upstream_blob_sha1": origin.get("blob_sha1"), "rule": LINEAGE_RULE,
        "verdict": "agree" if agree else "disagree",
    }
