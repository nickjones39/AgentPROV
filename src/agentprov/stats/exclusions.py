"""Rate exclusions declared by adapter families as data (D.16.17 item 4; CLAUDE.md rule 9; D-48).

``stats`` holds no source name and no source-specific issue code. Which executions or values a rate leaves out (harness
failures, unresolved re-runs, harness-imposed defaults, …) is declared by the adapter family that knows the source, in
its own package data ``agentprov/adapters/<family>/rates.toml``, found without importing any adapter module (as the
artefact catalogues are, D.15.3). Outcome-only and scenario records need no declaration: every rate's population is
already ``unit == agent_execution ∧ execution_observed`` (R-28; C.3.16), a core, source-neutral rule.

Format (version 1; unknown keys are refused, so a typo cannot silently widen or narrow a denominator)::

    version = 1
    family = "<family>"                       # must equal the directory name
    [[exclusion]]
    id = "<ns>.rate.<name>"                   # stable id, reported with the tables
    profiles = ["<profile id>", …]            # the source profiles it applies to (required, non-empty)
    issue_codes = ["map.<ns>.<code>", …]      # index-row issue codes (register codes, H.6.3): a carrying execution is excluded
    judgement_origins = ["harness_default"]   # C.3.10 judgement origins whose values an outcome rate leaves out
    rates = ["field_groups", "unknowns", "outcome"]   # the rates it applies to
    basis = "<spec section or decision>"

``field_groups`` and ``unknowns`` are applied by ``stats`` (the execution leaves the table's population and is counted in
the row's ``excluded`` column). ``outcome`` and ``judgement_origins`` are declared for outcome-rate consumers: ``stats``
v0.1 computes no outcome rate, reports the declarations in its output and leaves them to the consumer.
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cache
from importlib import resources
from typing import Any, Final

from agentprov.corpus.index import IndexRow
from agentprov.errors import AgentProvError

__all__ = ["RATE_FILE", "RATES", "Exclusion", "ExclusionError", "declared_exclusions", "excluded_from", "parse_exclusions"]

RATE_FILE: Final = "rates.toml"
RATES: Final = ("field_groups", "unknowns", "outcome")
_ORIGINS: Final = frozenset({"checker", "harness_default", "harness_rule", "recomputed"})  # C.3.10
_ID_RE: Final = re.compile(r"[a-z][a-z0-9_]*\.rate\.[a-z][a-z0-9_]*")
_CODE_RE: Final = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+")
_PROFILE_RE: Final = re.compile(r"[a-z][a-z0-9_.-]*")
_KEYS: Final = frozenset({"id", "profiles", "issue_codes", "judgement_origins", "rates", "basis"})


class ExclusionError(AgentProvError):
    """A family's ``rates.toml`` is malformed (a defect of the installed package; exit 70)."""

    code = "stats.exclusions.invalid"
    exit_code = 70


@dataclass(frozen=True, slots=True)
class Exclusion:
    """One declared exclusion (see the module docstring)."""

    id: str
    family: str
    profiles: tuple[str, ...]
    issue_codes: tuple[str, ...]
    judgement_origins: tuple[str, ...]
    rates: tuple[str, ...]
    basis: str

    def matches(self, row: IndexRow) -> bool:
        """Whether the execution of ``row`` is excluded (its profile is in scope and it carries a declared issue code)."""
        return row.profile.rpartition("@")[0] in self.profiles and any(code in self.issue_codes for code in row.issues)

    def to_json(self) -> dict[str, Any]:
        return {"basis": self.basis, "family": self.family, "id": self.id, "issue_codes": list(self.issue_codes),
                "judgement_origins": list(self.judgement_origins), "profiles": list(self.profiles), "rates": list(self.rates)}  # fmt: skip


def _strings(value: object, what: str, pattern: re.Pattern[str] | None = None, allowed: Iterable[str] | None = None,
             *, required: bool = False) -> tuple[str, ...]:  # fmt: skip
    if value is None and not required:
        return ()
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value) or (required and not value):
        raise ExclusionError(f"{what}: a {'non-empty ' if required else ''}list of strings")
    if pattern is not None and not all(pattern.fullmatch(v) for v in value):
        raise ExclusionError(f"{what}: a malformed value")
    if allowed is not None and not set(value) <= set(allowed):
        raise ExclusionError(f"{what}: a value outside {sorted(allowed)}")
    return tuple(sorted(set(value)))


def parse_exclusions(data: bytes, family: str) -> tuple[Exclusion, ...]:
    """Parse one family's ``rates.toml`` (see the module docstring)."""
    try:
        doc = tomllib.loads(data.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError):
        raise ExclusionError(f"{family}/{RATE_FILE}: not valid TOML") from None
    if set(doc) - {"version", "family", "exclusion"} or doc.get("version") != 1 or doc.get("family") != family:
        raise ExclusionError(f"{family}/{RATE_FILE}: a document is {{version = 1, family = <its directory>, [[exclusion]]}}")
    out = []
    for table in doc.get("exclusion", []):
        if not isinstance(table, dict) or set(table) - _KEYS or not {"id", "profiles", "rates", "basis"} <= set(table):
            raise ExclusionError(f"{family}/{RATE_FILE}: an exclusion is {{id, profiles, issue_codes?, judgement_origins?, rates, basis}}")
        eid = table["id"]
        if not isinstance(eid, str) or _ID_RE.fullmatch(eid) is None or not isinstance(table["basis"], str) or not table["basis"]:
            raise ExclusionError(f"{family}/{RATE_FILE}: an exclusion id is <ns>.rate.<name> and has a basis")
        what = f"{family}/{RATE_FILE} {eid}"
        exclusion = Exclusion(
            id=eid, family=family,
            profiles=_strings(table["profiles"], f"{what} profiles", _PROFILE_RE, required=True),
            issue_codes=_strings(table.get("issue_codes"), f"{what} issue_codes", _CODE_RE),
            judgement_origins=_strings(table.get("judgement_origins"), f"{what} judgement_origins", allowed=_ORIGINS),
            rates=_strings(table["rates"], f"{what} rates", allowed=RATES, required=True), basis=table["basis"],
        )  # fmt: skip
        if not exclusion.issue_codes and not exclusion.judgement_origins:
            raise ExclusionError(f"{what}: declares neither issue codes nor judgement origins")
        out.append(exclusion)
    ids = [e.id for e in out]
    if len(set(ids)) != len(ids):
        raise ExclusionError(f"{family}/{RATE_FILE}: duplicate exclusion id")
    return tuple(out)


@cache
def declared_exclusions() -> tuple[Exclusion, ...]:
    """Every exclusion declared by a shipped family, sorted by id (package data only; no adapter module is imported)."""
    root = resources.files("agentprov").joinpath("adapters")
    out: list[Exclusion] = []
    for child in sorted(root.iterdir(), key=lambda c: c.name):
        if child.is_dir() and not child.name.startswith(("_", ".")) and child.joinpath(RATE_FILE).is_file():
            out.extend(parse_exclusions(child.joinpath(RATE_FILE).read_bytes(), child.name))
    return tuple(sorted(out, key=lambda e: e.id))


def excluded_from(row: IndexRow, rate: str, exclusions: Iterable[Exclusion]) -> tuple[str, ...]:
    """The ids of the exclusions that take ``row`` out of ``rate``'s population (empty: it stays in)."""
    return tuple(e.id for e in exclusions if rate in e.rates and e.matches(row))
