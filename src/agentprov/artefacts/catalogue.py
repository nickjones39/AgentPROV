"""Artefact catalogues: schema, loader, discovery and reference checks (docs/architecture D.15.2; DECISIONS D-12).

A catalogue is the file ``agentprov/adapters/<family>/artefacts.toml``. It is *data*, owned by the adapter family that
reads the source (invariants 1 and 9), reviewed in git, and read only through :mod:`importlib.resources`. This module
never imports an adapter module: it navigates the package directory tree (``resources.files("agentprov") / "adapters"``)
and parses the files it finds, so the shared layer holds no source knowledge and adding a family needs no change here.

File shape (``format`` is optional; ``version`` is the integer that ``corpus.json`` records, like a rule catalogue)::

    version = 1
    family = "adprov"                       # must equal the directory name when loaded by discovery
    namespaces = ["adprov"]                 # optional; the <ns> of the entry ids (default: [family])

    [[artefact]]
    id = "adprov.art.timing_stub"           # <ns>.art.<name>, stable
    title = "..."                           # plain text, no source content
    description = "..."
    scope = { profiles = ["adprov-v1"], parts = ["converted-legacy"], sources = ["adprov-v1"] }
    cause = "baseline_converter"            # upstream_harness | benchmark | provider | baseline_converter | capture | unknown
    detector = { rule = "adprov.timing_stub_is_unknown@1", class = "D" }
    claims = ["artefact.generic.sentinel_time#raw_sentinel"]   # optional, see below
    recorded_as = { issues = [...], notes = [...], sem = [...] }
    handling = { class = "CR", rule = "adprov.timing_stub_is_unknown@1" }
    expected = [{ snapshot = "...", count = 68620, basis = "...", unit = "tool_turns", status = "unverified" }]
    manuscript = true
    refs = ["audit/legacy_replay.md section 3.6 D4"]

Fields beyond D.15.2 (implementation resolutions, D.15.8): ``claims`` lists generic detectors (and optionally one
variant, ``artefact.generic.<name>#<variant>``) that the entry wholly accounts for, so the safety net does not report
their hits as unclassified; ``recorded_as`` is a table with the three kinds D.15.2 names; ``scope`` is a table of
``profiles``/``parts``/``sources`` lists (only ``profiles`` restricts matching, because an AER header names its profile
but not its registry part); ``expected`` rows may carry ``unit`` (default ``"executions"``) and ``status``
(``"unverified"`` by default, D.15.6 requires it until a full-snapshot import has confirmed the count).

An entry may name a **generic detector** as its ``detector.rule`` (``artefact.generic.<name>``, no version): such an
entry accounts for every hit of that detector. Any other ``detector.rule`` and ``handling.rule`` must be a rule id that
exists in some rule catalogue (the ``aer`` catalogue, an adapter family's ``rules/*.rules.toml`` or the ``aprov``
engine catalogue); :func:`check_references` reports the ones that do not.
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass, field
from functools import cache
from importlib import resources
from importlib.resources.abc import Traversable
from typing import Any, Final

from agentprov.aer import rules as aer_rules
from agentprov.aer.types import CORE_ISSUE_CODES
from agentprov.errors import AgentProvError
from agentprov.io.canonical import sha256_hex

__all__ = [
    "CATALOGUE_FILE",
    "CAUSES",
    "DETECTOR_CLASSES",
    "GENERIC_PREFIX",
    "HANDLING_CLASSES",
    "UNCLASSIFIED_PREFIX",
    "ArtefactCatalogue",
    "ArtefactCatalogueError",
    "ArtefactEntry",
    "Expected",
    "Problem",
    "check_references",
    "discover_catalogues",
    "families_with_catalogues",
    "known_issue_codes",
    "known_rule_ids",
    "load_catalogue",
    "parse_catalogue",
]

CATALOGUE_FILE: Final = "artefacts.toml"
CATALOGUE_FORMAT: Final = "agentprov-artefact-catalogue/0.1"
#: Prefix of the generic (source-neutral) detectors: ``artefact.generic.<name>`` (D.15.2).
GENERIC_PREFIX: Final = "artefact.generic."
#: Prefix of the findings no catalogue entry claims: ``artefact.unclassified.<detector>`` (D.15.3).
UNCLASSIFIED_PREFIX: Final = "artefact.unclassified."

CAUSES: Final = frozenset({"upstream_harness", "benchmark", "provider", "baseline_converter", "capture", "unknown"})
HANDLING_CLASSES: Final = ("CR", "DR", "RJ", "FO", "NR")  # D.15.1, in table order
DETECTOR_CLASSES: Final = ("O", "D", "I")  # evidence class of the detection (C.6.1)

_ID_RE: Final = re.compile(r"([a-z][a-z0-9_]*)\.art\.[a-z][a-z0-9_]*")
_NS_RE: Final = re.compile(r"[a-z][a-z0-9_]*")
_GENERIC_RE: Final = re.compile(r"artefact\.generic\.[a-z][a-z0-9_]*")
_CLAIM_RE: Final = re.compile(r"(artefact\.generic\.[a-z][a-z0-9_]*)(?:#([A-Za-z0-9_.@:\-]{1,80}))?")
_TOKEN_RE: Final = re.compile(r"[A-Za-z0-9_.:\-]{1,64}")
_SCOPE_KEYS: Final = frozenset({"profiles", "parts", "sources"})
_RECORDED_KEYS: Final = frozenset({"issues", "notes", "sem"})
_ENTRY_KEYS: Final = frozenset(
    {"id", "title", "description", "scope", "cause", "detector", "claims", "recorded_as", "handling", "expected",
     "manuscript", "refs"}
)  # fmt: skip
_TOP_KEYS: Final = frozenset({"version", "family", "namespaces", "format", "artefact"})
_MAX_TEXT: Final = 4000


class ArtefactCatalogueError(AgentProvError):
    """A catalogue file is malformed (broken package data, exit 70) or a family's catalogue is not shipped."""

    code = "artefacts.catalogue_invalid"


@dataclass(frozen=True, slots=True)
class Expected:
    """A known count per pinned snapshot: a regression expectation, never a gate that hides data (D.15.2)."""

    snapshot: str
    count: int
    basis: str
    unit: str = "executions"
    status: str = "unverified"  # "unverified" until a full-snapshot import has confirmed it (D.15.6)


@dataclass(frozen=True, slots=True)
class ArtefactEntry:
    """One catalogue entry (D.15.2)."""

    id: str
    title: str
    description: str
    cause: str
    detector_rule: str  # a generic detector id (no version) or a rule id ``ns.name@n``
    detector_class: str  # "O" | "D" | "I"
    handling_class: str  # "CR" | "DR" | "RJ" | "FO" | "NR"
    handling_rule: str | None = None
    claims: tuple[str, ...] = ()
    issues: tuple[str, ...] = ()  # recorded_as.issues
    notes: tuple[str, ...] = ()  # recorded_as.notes
    sem: tuple[str, ...] = ()  # recorded_as.sem
    profiles: tuple[str, ...] = ()  # scope.profiles (empty: every profile)
    parts: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()
    expected: tuple[Expected, ...] = ()
    manuscript: bool = False
    refs: tuple[str, ...] = ()

    @property
    def namespace(self) -> str:
        return self.id.split(".", 1)[0]

    @property
    def detector_is_generic(self) -> bool:
        return self.detector_rule.startswith(GENERIC_PREFIX)

    def applies_to(self, profile_id: str | None) -> bool:
        """``scope.profiles`` restricts the entry to those profiles; empty means every profile."""
        return not self.profiles or (profile_id is not None and profile_id in self.profiles)


@dataclass(frozen=True, slots=True)
class ArtefactCatalogue:
    """A loaded, schema-checked catalogue (immutable). ``digest`` is the SHA-256 of the file bytes."""

    family: str
    version: int
    namespaces: tuple[str, ...]
    entries: tuple[ArtefactEntry, ...]
    digest: str = ""
    source: str = ""
    _by_id: Mapping[str, ArtefactEntry] = field(default_factory=dict, repr=False, compare=False)

    def get(self, entry_id: str) -> ArtefactEntry | None:
        return self._by_id.get(entry_id)

    def header(self) -> dict[str, Any]:
        """What ``corpus.json`` records for a catalogue: ``{family, version, sha256}`` (like a rule catalogue)."""
        return {"family": self.family, "sha256": self.digest, "version": self.version}


@dataclass(frozen=True, slots=True)
class Problem:
    """A defect found by :func:`check_references`: the entry id, the field and a plain-text message."""

    entry: str
    field: str
    message: str

    def __str__(self) -> str:
        return f"{self.entry}: {self.field}: {self.message}"


# --------------------------------------------------------------------------------------------------------------
# Parsing and schema validation
# --------------------------------------------------------------------------------------------------------------


def _text(value: object, where: str, problems: list[str], *, required: bool = True) -> str:
    if not isinstance(value, str) or (required and not value.strip()) or len(value) > _MAX_TEXT:
        problems.append(f"{where}: must be a non-empty string of at most {_MAX_TEXT} characters")
        return ""
    if any(ord(c) < 0x20 and c not in "\n\t" or 0x7F <= ord(c) <= 0x9F for c in value):
        problems.append(f"{where}: contains a control character")
    return value


def _strings(value: object, where: str, problems: list[str], *, pattern: re.Pattern[str] | None = None) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(x, str) and x for x in value):
        problems.append(f"{where}: must be an array of non-empty strings")
        return ()
    if len(set(value)) != len(value):
        problems.append(f"{where}: must not repeat an item")
    if pattern is not None:
        for item in value:
            if pattern.fullmatch(item) is None:
                problems.append(f"{where}: {item!r} is not well formed")
    return tuple(value)


def _table(value: object, where: str, allowed: Collection[str], problems: list[str]) -> Mapping[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        problems.append(f"{where}: must be a table")
        return {}
    for key in sorted(set(value) - set(allowed)):
        problems.append(f"{where}: unknown key {key!r}")
    return value


def _is_rule_id(text: str) -> bool:
    return aer_rules.RULE_ID_RE.fullmatch(text) is not None


def _parse_expected(rows: object, where: str, problems: list[str]) -> tuple[Expected, ...]:
    if rows is None:
        return ()
    if not isinstance(rows, list):
        problems.append(f"{where}: must be an array of tables")
        return ()
    out: list[Expected] = []
    for i, row in enumerate(rows):
        at = f"{where}[{i}]"
        if not isinstance(row, dict):
            problems.append(f"{at}: must be a table")
            continue
        _table(row, at, {"snapshot", "count", "basis", "unit", "status"}, problems)
        count = row.get("count")
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            problems.append(f"{at}.count: must be a non-negative integer")
            count = 0
        status = row.get("status", "unverified")
        if status not in ("unverified", "verified"):
            problems.append(f"{at}.status: must be 'unverified' or 'verified'")
        out.append(
            Expected(
                snapshot=_text(row.get("snapshot"), f"{at}.snapshot", problems),
                count=count,
                basis=_text(row.get("basis"), f"{at}.basis", problems),
                unit=_text(row.get("unit", "executions"), f"{at}.unit", problems),
                status=str(status),
            )
        )
    return tuple(out)


def _parse_entry(table: object, index: int, namespaces: tuple[str, ...], problems: list[str]) -> ArtefactEntry | None:
    here = f"artefact #{index}"
    if not isinstance(table, dict):
        problems.append(f"{here}: must be a table")
        return None
    entry_id = table.get("id")
    if isinstance(entry_id, str) and entry_id:
        here = entry_id
    start = len(problems)
    _table(table, here, _ENTRY_KEYS, problems)
    match = _ID_RE.fullmatch(entry_id) if isinstance(entry_id, str) else None
    if match is None:
        problems.append(f"{here}: id must be <ns>.art.<name>")
    elif match.group(1) not in namespaces:
        problems.append(f"{here}: namespace {match.group(1)!r} is not one of this catalogue's namespaces {list(namespaces)}")
    title = _text(table.get("title"), f"{here}.title", problems)
    description = _text(table.get("description"), f"{here}.description", problems)
    cause = table.get("cause")
    if cause not in CAUSES:
        problems.append(f"{here}.cause: must be one of {sorted(CAUSES)}")
    scope = _table(table.get("scope"), f"{here}.scope", _SCOPE_KEYS, problems)
    profiles = _strings(scope.get("profiles"), f"{here}.scope.profiles", problems, pattern=_TOKEN_RE)
    parts = _strings(scope.get("parts"), f"{here}.scope.parts", problems, pattern=_TOKEN_RE)
    sources = _strings(scope.get("sources"), f"{here}.scope.sources", problems, pattern=_TOKEN_RE)

    detector = table.get("detector")
    det = _table(detector, f"{here}.detector", {"rule", "class"}, problems)
    if not isinstance(detector, dict):
        problems.append(f"{here}.detector: required table {{rule, class}}")
    rule = det.get("rule")
    if not isinstance(rule, str) or not (_GENERIC_RE.fullmatch(rule) or _is_rule_id(rule)):
        problems.append(f"{here}.detector.rule: must be a rule id '<ns>.<name>@<n>' or a generic detector 'artefact.generic.<name>'")
        rule = ""
    det_class = det.get("class")
    if det_class not in DETECTOR_CLASSES:
        problems.append(f"{here}.detector.class: must be one of {list(DETECTOR_CLASSES)}")

    claims = _strings(table.get("claims"), f"{here}.claims", problems)
    for claim in claims:
        if _CLAIM_RE.fullmatch(claim) is None:
            problems.append(f"{here}.claims: {claim!r} must be 'artefact.generic.<name>' or 'artefact.generic.<name>#<variant>'")
    recorded = _table(table.get("recorded_as"), f"{here}.recorded_as", _RECORDED_KEYS, problems)
    issues = _strings(recorded.get("issues"), f"{here}.recorded_as.issues", problems, pattern=_TOKEN_RE)
    notes = _strings(recorded.get("notes"), f"{here}.recorded_as.notes", problems, pattern=_TOKEN_RE)
    sem = _strings(recorded.get("sem"), f"{here}.recorded_as.sem", problems, pattern=_TOKEN_RE)

    handling = table.get("handling")
    han = _table(handling, f"{here}.handling", {"class", "rule"}, problems)
    if not isinstance(handling, dict):
        problems.append(f"{here}.handling: required table {{class, rule}}")
    han_class = han.get("class")
    if han_class not in HANDLING_CLASSES:
        problems.append(f"{here}.handling.class: must be one of {list(HANDLING_CLASSES)}")
    han_rule = han.get("rule")
    if han_rule is not None and (not isinstance(han_rule, str) or not _is_rule_id(han_rule)):
        problems.append(f"{here}.handling.rule: must be a rule id '<ns>.<name>@<n>'")
        han_rule = None
    if han_class in ("CR", "DR") and han_rule is None:
        problems.append(f"{here}.handling.rule: class {han_class} needs the rule that implements it")

    manuscript = table.get("manuscript", False)
    if not isinstance(manuscript, bool):
        problems.append(f"{here}.manuscript: must be a boolean")
        manuscript = False
    refs = _strings(table.get("refs"), f"{here}.refs", problems)
    expected = _parse_expected(table.get("expected"), f"{here}.expected", problems)
    if len(problems) > start:
        return None
    return ArtefactEntry(
        id=str(entry_id),
        title=title,
        description=description,
        cause=str(cause),
        detector_rule=str(rule),
        detector_class=str(det_class),
        handling_class=str(han_class),
        handling_rule=han_rule,
        claims=claims,
        issues=issues,
        notes=notes,
        sem=sem,
        profiles=profiles,
        parts=parts,
        sources=sources,
        expected=expected,
        manuscript=manuscript,
        refs=refs,
    )


def parse_catalogue(data: bytes, *, source: str = "<bytes>", family: str | None = None) -> ArtefactCatalogue:
    """Parse and schema-check a catalogue; :class:`ArtefactCatalogueError` lists every defect found.

    ``family`` (given by discovery) must equal the file's ``family``. The check that rule ids exist is separate
    (:func:`check_references`) because it needs the other catalogues.
    """
    try:
        doc = tomllib.loads(data.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise ArtefactCatalogueError(f"{source}: not valid TOML/UTF-8") from exc
    problems: list[str] = []
    for key in sorted(set(doc) - _TOP_KEYS):
        problems.append(f"unknown top-level key {key!r}")
    version = doc.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        problems.append("version: must be a positive integer")
        version = 0
    fam = doc.get("family")
    if not isinstance(fam, str) or _NS_RE.fullmatch(fam) is None:
        problems.append("family: must be a bare name")
        fam = ""
    elif family is not None and fam != family:
        problems.append(f"family: {fam!r} does not match its directory {family!r}")
    if doc.get("format", CATALOGUE_FORMAT) != CATALOGUE_FORMAT:
        problems.append(f"format: must be {CATALOGUE_FORMAT!r}")
    namespaces = _strings(doc.get("namespaces", [fam] if fam else []), "namespaces", problems, pattern=_NS_RE)
    rows = doc.get("artefact", [])
    if not isinstance(rows, list):
        problems.append("artefact: must be an array of tables")
        rows = []
    entries: list[ArtefactEntry] = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        entry = _parse_entry(row, index, namespaces, problems)
        if entry is None:
            continue
        if entry.id in seen:
            problems.append(f"{entry.id}: duplicate id")
        seen.add(entry.id)
        entries.append(entry)
    if problems:
        shown = "; ".join(problems[:12]) + (f"; ... ({len(problems)} defects)" if len(problems) > 12 else "")
        raise ArtefactCatalogueError(f"{source}: {shown}")
    ordered = tuple(sorted(entries, key=lambda e: e.id))
    return ArtefactCatalogue(
        family=fam,
        version=version,
        namespaces=namespaces,
        entries=ordered,
        digest=sha256_hex(data),
        source=source,
        _by_id={e.id: e for e in ordered},
    )


# --------------------------------------------------------------------------------------------------------------
# Discovery (package data only; no adapter module is imported)
# --------------------------------------------------------------------------------------------------------------


def _adapters_root() -> Traversable:
    # `resources.files("agentprov")` imports only the top package; the rest is directory navigation.
    return resources.files("agentprov") / "adapters"


def families_with_catalogues() -> tuple[str, ...]:
    """The adapter families that ship an ``artefacts.toml``, sorted."""
    names = [
        child.name
        for child in _adapters_root().iterdir()
        if child.is_dir() and not child.name.startswith(("_", ".")) and (child / CATALOGUE_FILE).is_file()
    ]
    return tuple(sorted(names))


def load_catalogue(family: str) -> ArtefactCatalogue:
    """The catalogue of ``family`` from package resources."""
    if _NS_RE.fullmatch(family) is None:
        raise ArtefactCatalogueError("a family is a bare name")
    node = _adapters_root() / family / CATALOGUE_FILE
    if not node.is_file():
        raise ArtefactCatalogueError(f"family {family!r} ships no {CATALOGUE_FILE}", code="artefacts.unavailable")
    return parse_catalogue(node.read_bytes(), source=f"agentprov.adapters.{family}:{CATALOGUE_FILE}", family=family)


def discover_catalogues() -> tuple[ArtefactCatalogue, ...]:
    """Every shipped catalogue, sorted by family. The result is deterministic and reads no adapter module."""
    return tuple(load_catalogue(family) for family in families_with_catalogues())


# --------------------------------------------------------------------------------------------------------------
# The rule and issue-code universe (rule catalogues, found without importing adapters)
# --------------------------------------------------------------------------------------------------------------


@cache
def _rule_catalogues() -> tuple[aer_rules.RuleCatalogue, ...]:
    found = [aer_rules.load_catalogue("aer")]
    for child in sorted(_adapters_root().iterdir(), key=lambda c: c.name):
        folder = child / "rules"
        if not child.is_dir() or not folder.is_dir():
            continue
        for node in sorted(folder.iterdir(), key=lambda c: c.name):
            if node.is_file() and node.name.endswith(".rules.toml"):
                found.append(aer_rules.parse_catalogue(node.read_bytes(), source=f"agentprov.adapters.{child.name}:rules/{node.name}"))
    return tuple(found)


@cache
def known_rule_ids() -> frozenset[str]:
    """Every rule id (``ns.name@n``) of the ``aer`` catalogue, the adapter families' catalogues and the ``aprov`` engine."""
    from agentprov.prov.specs import load_spec

    ids = {rid for catalogue in _rule_catalogues() for rid in catalogue.rules}
    ids.update(load_spec().rules)
    return frozenset(ids)


@cache
def known_issue_codes() -> frozenset[str]:
    """The core issue codes (C.12.3) plus ``<ns>.<code>`` for every code a rule catalogue declares."""
    codes = set(CORE_ISSUE_CODES)
    for catalogue in _rule_catalogues():
        codes.update(f"{catalogue.namespace}.{code}" for code in catalogue.issue_codes)
    return frozenset(codes)


def check_references(
    catalogue: ArtefactCatalogue,
    *,
    rule_ids: Collection[str] | None = None,
    issue_codes: Collection[str] | None = None,
    generic_detectors: Collection[str] | None = None,
) -> list[Problem]:
    """Cross-check a catalogue against the rule catalogues (D.15.7: "every ``detector`` and ``handling`` rule id exists").

    Reported, sorted by entry and field: a ``detector.rule`` or ``handling.rule`` that is neither a known rule id nor (for
    the detector) a registered generic detector; a ``claims`` item naming an unregistered generic detector or an unknown
    variant of a closed-variant detector; a ``recorded_as.issues`` code that is neither a core code nor declared by a rule
    catalogue. The three arguments default to the shipped universe and exist so tests can supply their own.
    """
    from agentprov.artefacts.detectors import DETECTORS

    rules = known_rule_ids() if rule_ids is None else frozenset(rule_ids)
    codes = known_issue_codes() if issue_codes is None else frozenset(issue_codes)
    generic = frozenset(DETECTORS) if generic_detectors is None else frozenset(generic_detectors)
    problems: list[Problem] = []
    for entry in catalogue.entries:
        if entry.detector_is_generic:
            if entry.detector_rule not in generic:
                problems.append(Problem(entry.id, "detector.rule", f"{entry.detector_rule} is not a registered generic detector"))
        elif entry.detector_rule not in rules:
            problems.append(Problem(entry.id, "detector.rule", f"{entry.detector_rule} is in no rule catalogue"))
        if entry.handling_rule is not None and entry.handling_rule not in rules:
            problems.append(Problem(entry.id, "handling.rule", f"{entry.handling_rule} is in no rule catalogue"))
        for claim in entry.claims:
            match = _CLAIM_RE.fullmatch(claim)
            if match is None:
                continue  # reported by the schema check
            name, variant = match.group(1), match.group(2)
            if name not in generic:
                problems.append(Problem(entry.id, "claims", f"{name} is not a registered generic detector"))
                continue
            known = DETECTORS[name].variants if name in DETECTORS else None
            if variant is not None and known is not None and variant not in known:
                problems.append(Problem(entry.id, "claims", f"{variant!r} is not a variant of {name}"))
        for code in entry.issues:
            if code not in codes:
                problems.append(Problem(entry.id, "recorded_as.issues", f"{code} is neither a core issue code nor declared by a rule catalogue"))
    return sorted(problems, key=lambda p: (p.entry, p.field, p.message))


def claim_parts(claim: str) -> tuple[str, str | None]:
    """Split ``artefact.generic.<name>[#<variant>]`` into ``(name, variant or None)``."""
    match = _CLAIM_RE.fullmatch(claim)
    if match is None:
        raise ValueError("not a claim")
    return match.group(1), match.group(2)


def iter_entries(catalogues: Iterable[ArtefactCatalogue]) -> list[ArtefactEntry]:
    """All entries of ``catalogues`` in a deterministic order (by family, then id)."""
    out: list[ArtefactEntry] = []
    for catalogue in sorted(catalogues, key=lambda c: (c.family, c.version)):
        out.extend(catalogue.entries)
    return out
