"""The expected-differences register of gate C (docs/architecture J.3.4): ``migration/expected_differences.toml``.

Gate C compares the frozen baseline package with AgentPROV on the same inputs. Every difference it tolerates is listed
in the register; **a difference not listed fails the gate, and a listed difference whose observed count exceeds its
bound fails too** (J.3.4). The register lives beside the baseline lock in the repository's ``migration/`` directory
(the J.1.5 location; ``migration/`` there is the repository directory, not the package).

An entry (J.3.4's form, plus ``defect`` and ``match``)::

    [[difference]]
    id           = "XD-C6-F02-discarded-model-calls"
    comparison   = "C6"
    defect       = "F-02"            # the B.9 defect id or the spec section it cites (C6 entries MUST carry one)
    applies_to   = ["scenario:*"]    # the items it may absorb (fnmatch over item ids)
    match        = ["deviation:F-02/*"]   # the observation keys it absorbs (fnmatch)
    old          = "..."             # the old behaviour, in words (no payload text)
    new          = "..."
    evidence     = "B_audit.md B.9 F-02"
    max_per_item = 8                 # bound on the observations it absorbs per item

A comparison reports **observations** ``(comparison, item, key)``: one per difference instance (a JSON Pointer of a
byte diff, a detected deviation). :func:`check` assigns every observation to the entries that match it: none is an
*unlisted* difference, more than one is *ambiguous* (each deviation must have exactly one entry), and an entry that
absorbs more than ``max_per_item`` observations of one item is *over its bound*. With ``expected`` (item -> entry ids,
e.g. a C6 scenario's declared deviations) the set of entries hit on each item must equal the expected set: an expected
deviation that was not observed (*missing*) fails like an unexpected one. Every failure carries ids and keys only, never
payload text (MP-6).
"""

from __future__ import annotations

import re
import tomllib
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any, Final

from agentprov.errors import AgentProvError
from agentprov.migration.lock import REPO_ROOT

__all__ = [
    "DEFAULT_REGISTER_PATH",
    "REGISTER_FORMAT",
    "CheckResult",
    "ExpectedDifference",
    "Observation",
    "Register",
    "RegisterError",
    "check",
    "load_register",
    "parse_register",
]

REGISTER_FORMAT: Final = "agentprov-expected-differences/1"
DEFAULT_REGISTER_PATH: Final = REPO_ROOT / "migration" / "expected_differences.toml"
COMPARISONS: Final = frozenset({"C1", "C2", "C3", "C4", "C5", "C6", "C7"})
_ID: Final = re.compile(r"XD-C[1-7]-[A-Za-z0-9][A-Za-z0-9.-]*")
_DEFECT: Final = re.compile(r"(?:F-\d{2}|[A-Q]\.\d+(?:\.\d+)*)")
_FIELDS: Final = frozenset({"id", "comparison", "defect", "applies_to", "match", "old", "new", "evidence", "max_per_item"})


class RegisterError(AgentProvError):
    """The register is missing or malformed (the message names the entry and the member, never file text)."""

    code = "migration.xd.invalid"
    exit_code = 3


@dataclass(frozen=True, slots=True)
class ExpectedDifference:
    id: str
    comparison: str
    applies_to: tuple[str, ...]
    match: tuple[str, ...]
    old: str
    new: str
    evidence: str
    max_per_item: int
    defect: str | None = None

    def applies(self, obs: Observation) -> bool:
        return (obs.comparison == self.comparison and any(fnmatchcase(obs.item, p) for p in self.applies_to)
                and any(fnmatchcase(obs.key, p) for p in self.match))


@dataclass(frozen=True, slots=True)
class Register:
    entries: tuple[ExpectedDifference, ...]

    def by_id(self) -> dict[str, ExpectedDifference]:
        return {e.id: e for e in self.entries}

    def for_comparison(self, comparison: str) -> tuple[ExpectedDifference, ...]:
        return tuple(e for e in self.entries if e.comparison == comparison)


@dataclass(frozen=True, slots=True, order=True)
class Observation:
    """One difference instance: ``key`` is ``<kind>:<detail>`` (e.g. ``v1:/meta/capture``, ``deviation:F-02/c3``)."""

    comparison: str
    item: str
    key: str


@dataclass
class CheckResult:
    hits: dict[tuple[str, str], int] = field(default_factory=dict)  # (entry id, item) -> observations absorbed
    unlisted: list[Observation] = field(default_factory=list)
    ambiguous: list[tuple[Observation, tuple[str, ...]]] = field(default_factory=list)
    over_bound: list[tuple[str, str, int, int]] = field(default_factory=list)  # (entry, item, count, max)
    missing: list[tuple[str, str]] = field(default_factory=list)  # (item, expected entry not hit)
    unexpected: list[tuple[str, str]] = field(default_factory=list)  # (item, entry hit but not expected)

    @property
    def ok(self) -> bool:
        return not (self.unlisted or self.ambiguous or self.over_bound or self.missing or self.unexpected)

    def failures(self) -> list[dict[str, str]]:
        out = [{"item": o.item, "check": "xd.unlisted", "detail": o.key} for o in self.unlisted]
        out += [{"item": o.item, "check": "xd.ambiguous", "detail": f"{o.key} -> {', '.join(ids)}"}
                for o, ids in self.ambiguous]
        out += [{"item": item, "check": "xd.over_bound", "detail": f"{eid}: {n} > {bound}"}
                for eid, item, n, bound in self.over_bound]
        out += [{"item": item, "check": "xd.missing", "detail": eid} for item, eid in self.missing]
        out += [{"item": item, "check": "xd.unexpected", "detail": eid} for item, eid in self.unexpected]
        return out

    def counts_by_entry(self) -> dict[str, int]:
        totals: Counter[str] = Counter()
        for (eid, _), n in self.hits.items():
            totals[eid] += n
        return dict(sorted(totals.items()))


def _strings(entry: str, name: str, value: Any) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or not all(isinstance(v, str) and v for v in value):
        raise RegisterError(f"{entry}: {name} must be a non-empty list of strings")
    return tuple(value)


def _text(entry: str, name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RegisterError(f"{entry}: {name} must be a non-empty string")
    return value


def parse_register(document: Mapping[str, Any]) -> Register:
    """Validate a parsed register document (see the module docstring)."""
    head = document.get("register")
    if not isinstance(head, Mapping) or head.get("format") != REGISTER_FORMAT:
        raise RegisterError(f"the register must start with [register] format = {REGISTER_FORMAT!r}")
    raw = document.get("difference", [])
    if not isinstance(raw, list):
        raise RegisterError("[[difference]] must be an array of tables")
    entries: list[ExpectedDifference] = []
    seen: set[str] = set()
    for k, item in enumerate(raw):
        if not isinstance(item, Mapping):
            raise RegisterError(f"difference #{k} is not a table")
        eid = item.get("id")
        if not isinstance(eid, str) or not _ID.fullmatch(eid):
            raise RegisterError(f"difference #{k}: id must match XD-C<n>-<name>")
        if eid in seen:
            raise RegisterError(f"{eid}: duplicate id")
        seen.add(eid)
        unknown = set(item) - _FIELDS
        if unknown:
            raise RegisterError(f"{eid}: unknown members {sorted(unknown)}")
        comparison = item.get("comparison")
        if comparison not in COMPARISONS or not eid.startswith(f"XD-{comparison}-"):
            raise RegisterError(f"{eid}: comparison must be one of C1..C7 and agree with the id")
        defect = item.get("defect")
        if defect is not None and (not isinstance(defect, str) or not _DEFECT.fullmatch(defect)):
            raise RegisterError(f"{eid}: defect must be a B.9 id (F-nn) or a spec section (e.g. D.7.3)")
        if comparison == "C6" and defect is None:
            raise RegisterError(f"{eid}: a C6 entry must cite its defect id or spec section (J.3.4)")
        bound = item.get("max_per_item")
        if not isinstance(bound, int) or isinstance(bound, bool) or bound < 1:
            raise RegisterError(f"{eid}: max_per_item must be a positive integer")
        entries.append(ExpectedDifference(
            id=eid, comparison=comparison, applies_to=_strings(eid, "applies_to", item.get("applies_to")),
            match=_strings(eid, "match", item.get("match", ["*"])), old=_text(eid, "old", item.get("old")),
            new=_text(eid, "new", item.get("new")), evidence=_text(eid, "evidence", item.get("evidence")),
            max_per_item=bound, defect=defect,
        ))
    return Register(tuple(entries))


def load_register(path: Path = DEFAULT_REGISTER_PATH) -> Register:
    try:
        document = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise RegisterError("the expected-differences register is missing") from None
    except (tomllib.TOMLDecodeError, UnicodeDecodeError):
        raise RegisterError("the expected-differences register is not valid TOML") from None
    return parse_register(document)


def check(observations: Iterable[Observation], register: Register, *,
          expected: Mapping[str, Sequence[str]] | None = None) -> CheckResult:
    """Assign every observation to the register (see the module docstring)."""
    result = CheckResult()
    hits: Counter[tuple[str, str]] = Counter()
    known = register.by_id()
    for obs in sorted(observations):
        matched = tuple(e.id for e in register.entries if e.applies(obs))
        if not matched:
            result.unlisted.append(obs)
        elif len(matched) > 1:
            result.ambiguous.append((obs, matched))
        else:
            hits[(matched[0], obs.item)] += 1
    result.hits = dict(sorted(hits.items()))
    for (eid, item), n in result.hits.items():
        if n > known[eid].max_per_item:
            result.over_bound.append((eid, item, n, known[eid].max_per_item))
    if expected is not None:
        for item, ids in sorted(expected.items()):
            unknown = [i for i in ids if i not in known]
            if unknown:
                raise RegisterError(f"{item}: expected entries {unknown} are not in the register")
            hit = {eid for (eid, it) in result.hits if it == item}
            result.missing += [(item, eid) for eid in sorted(set(ids) - hit)]
            result.unexpected += [(item, eid) for eid in sorted(hit - set(ids))]
    return result
