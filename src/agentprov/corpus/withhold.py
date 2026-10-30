"""Withholding at sealing: what leaves a corpus version and why (HL H.4.1, H.4.5; G.9.5, G.9.6; D-230..D-236).

:func:`plan_withholding` decides, from the working corpus, which raw objects and which executions a sealed corpus version
withholds. Sealing (:func:`agentprov.corpus.package.seal`) then renames their files into the private sidecar
``DIR.withheld/`` (never deleting anything), writes ``WITHHELD.json`` (:mod:`agentprov.corpus.withheld`) and gives every
withheld execution the register entry ``release.withheld``. Four causes, each recorded as the entry's ``basis``:

* **purge** (G.9.6, P-3): every object listed in ``raw/tombstones.jsonl``; reason and date from the tombstone. Its
  executions are withheld: those whose index row cites the object or, for a container, one of its members (the set
  :mod:`agentprov.corpus.purge` gave ``release.withheld``).
* **raw_policy** (H.4.1): a snapshot whose corpus-spec raw policy is ``withhold``. Every execution a row of that snapshot
  records is withheld (a row shared with another snapshot too: *withhold wins*), with every object such a row cites and
  every object whose origin that snapshot's pin vouched for (members follow their container). Reason ``licence``.
* **profile_rule**: the source profile's ``[withhold]`` policy (:func:`parse_policy`; D-146's canary credentials). Each
  rule is a literal **marker** or a bounded **pattern**, searched in every stored raw object and in every derived file
  (AER, SEM, PROV, view) of every execution, and in the stored archives **decoded** (D-450, D-452,
  :mod:`agentprov.corpus.withhold_scan`, which states what is recognised and read: the members the corpus does not store
  as objects of their own, decompressed by the bounded ``expand`` job in T1, nested archives too; detector
  ``agentprov-withhold-decoded/1``), so a canary in a deflated member the profile never selected is found. A decoded hit withholds the archive object only (object level, as a container: the executions'
  own objects were scanned as stored), and only when no other cause withholds it already, so that basis stays. A hit in
  a raw object withholds the object; with ``scope = "executions"``
  (the default) also the executions that cite it (as for purge). A hit in a derived file always withholds that
  execution, and its primary object with it (the value came from the raw evidence, possibly in another encoding).
  Only rule ids are recorded, never a match. An **issue** rule (D-311) selects executions instead of bytes: every
  execution whose AER seal carries the named issue code (its index row's ``issues`` or a register entry ``map.<code>``
  for it) is withheld with its primary object, exactly as a derived-file hit is; the other executions that cite that
  object stay released (D-235). The source itself flags what to withhold (MCPHunt's canary flags, D-289 (c)); the code
  must be one the catalogue of its namespace declares (:func:`check_issue_codes`), and :func:`issue_backstop` re-checks
  the selection from the released register.
* **container** (AD-12): an archive whose selected member is withheld holds that member's bytes, so it is withheld too
  (object level only; its other members, stored as their own objects, stay). Two more links hold the same bytes and
  are closed the same way, in both directions (D-315): a split descriptor and its byte parts (D-244, D-249; the parts
  are the archive's bytes, and a value can straddle two parts) are withheld as one unit, and a carved blob and the
  object it was carved from (D-218; the same value, possibly decoded) are withheld together.

* **unscanned** (D-454): a policy with byte rules needs every stored archive read in decoded form. An archive that
  cannot be (beyond the limits, nested deeper than ``max_archive_depth``, a deferred codec, a rejected member, an entry
  the local-header read of D-453 cannot decode) and that no other cause withholds is withheld itself, unread: reason the
  policy's, object level only (its good members, stored as their own objects, and their executions stay released), and
  the archives that hold it are closed as containers. The ledger is then ``agentprov-withheld/0.3``; the plan lists each
  such archive's container chain and code, which the seal report prints. Before D-454 such an archive refused the seal
  (D-450).

An object withheld for several causes gets one entry: the first reason of :data:`agentprov.corpus.withheld.REASONS` and
the first basis of :data:`agentprov.corpus.withheld.BASES_03`, with the union of the affected executions. A ``release.withheld``
register entry for an execution no cause explains refuses the seal (:class:`WithholdError`, exit 4): withholding is never
inferred from the register alone.

**Pattern grammar** (a profile is reviewed package data, but the bytes it is matched against are untrusted, G.3): a
sequence of atoms, each optionally followed by ``?``, ``{n}`` or ``{m,n}`` (n <= 256); an atom is a literal ASCII
character, an escaped punctuation character, ``\\d``, ``\\w``, ``\\s`` or a character class ``[...]`` of literals and
ranges (``^`` negation allowed). No group, alternation, ``.``, ``*``, ``+``, open-ended repetition, anchor, back-reference
or look-around, so every match is at most :attr:`Rule.width` bytes long and matching never backtracks badly. Raw bytes are
scanned in 1 MiB chunks with an overlap of ``width - 1`` bytes, so a match across a chunk boundary is found.
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final, Literal

from agentprov.corpus.index import IndexRow, primary_role
from agentprov.corpus.layout import TRANSCRIPT_VIEW
from agentprov.corpus.register import RegisterEntry
from agentprov.corpus.withheld import (
    BASES_03,
    NOTE_MAX,
    REASONS,
    SCOPES,
    WithheldDocument,
    WithheldExecution,
    WithheldFinding,
    WithheldObject,
    WithheldPolicy,
    one_line_note,
    sorted_origins,
)
from agentprov.errors import AgentProvError
from agentprov.raw.members import MemberRow

if TYPE_CHECKING:
    from agentprov.corpus.withhold_scan import DecodedScan
from agentprov.raw.origins import OriginRow

__all__ = [
    "DETECTOR",
    "ISSUE_CODE",
    "UNSCANNED_RULE",
    "Rule",
    "WithholdError",
    "WithholdPlan",
    "WithholdPolicy",
    "check_issue_codes",
    "compile_pattern",
    "declared_issue_codes",
    "issue_backstop",
    "load_policy",
    "member_closure",
    "parse_policy",
    "plan_withholding",
    "scan_chunks",
]

#: The ``finding.detector`` of a profile-rule hit (the in-process scanner of this module, version 1).
DETECTOR: Final = "agentprov-withhold/1"
#: Fixed ``detail`` texts of the ``release.withheld`` entries sealing adds (HL H.6.2: generated text).
#: Generated ``public_note`` texts of the D-315 links (a split descriptor and its parts; a carved blob and its source).
LINK_NOTES: Final[Mapping[str, str]] = {
    "part": "a byte part of a split archive whose descriptor or another part is withheld (D-244, D-315)",
    "descriptor": "the descriptor of a split archive one of whose byte parts is withheld (D-244, D-315)",
    "carved": "a value carved from a withheld object (D-218, D-315)",
    "source": "the object a withheld carved value was taken from (D-218, D-315)",
}
DETAILS: Final[Mapping[str, str]] = {
    "purge": "a cited raw object was purged (G.9.6)",
    "raw_policy": "the snapshot's raw policy is withhold (H.4.1)",
    "profile_rule": "a source-profile withholding rule matched (H.4.5)",
}
_CHUNK: Final = 1 << 20
_RULE_ID: Final = re.compile(r"[a-z0-9][a-z0-9_.-]{0,63}")
_SCAN_RULE: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}")
_MAX_REPEAT: Final = 256
_MAX_PATTERN: Final = 256
_MIN_MARKER: Final = 4
_MAX_MARKER: Final = 256
_TABLE_KEYS: Final = frozenset({"reason", "public_note", "rules", "scan_rules"})
_RULE_KEYS: Final = frozenset({"id", "marker", "pattern", "issue", "scope", "reason", "public_note"})
_SELECTORS: Final = ("marker", "pattern", "issue")
#: An AER seal issue code ``<namespace>.<code>`` (C.3.13); its register and index form is ``map.<namespace>.<code>``.
ISSUE_CODE: Final = re.compile(r"[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*")


class WithholdError(AgentProvError):
    """A withholding policy or plan the build refuses (a malformed ``[withhold]`` table, an unexplained
    ``release.withheld`` entry); exit 4, nothing written."""

    code = "corpus.withhold.invalid"
    exit_code = 4


# ================================================================================================ the policy
@dataclass(frozen=True)
class Rule:
    """One ``[[withhold.rules]]`` entry: a literal marker or a compiled bounded pattern, never printed, or an AER seal
    issue code (``kind = "issue"``, D-311), which selects executions and is never matched against bytes."""

    id: str
    kind: str  # marker | pattern | issue | address | object
    scope: str  # executions | object
    reason: str
    public_note: str
    needle: bytes | None = field(default=None, repr=False)
    regex: re.Pattern[bytes] | None = field(default=None, repr=False)
    width: int = 1
    code: str | None = None  # kind issue: "<namespace>.<code>"
    #: kind ``address`` (D-810): the digests (:func:`agentprov.corpus.personas.address_digest`) of the e-mail addresses to
    #: withhold; the rule matches a file that holds one of them. Never a literal address.
    digests: frozenset[str] = field(default=frozenset(), repr=False)
    #: kind ``address`` (D-961): the digests of class ``withhold-object`` (in no execution's records). The rule matches
    #: them too. A raw object an address rule hits is withheld alone (D-963, for either class): executions are withheld
    #: only through their own records, a derived file that holds a listed address.
    object_digests: frozenset[str] = field(default=frozenset(), repr=False)
    #: kind ``object`` (D-964): the stored raw objects (sha256 hex) and the executions (ids) the corpus spec's
    #: ``[withhold]`` table lists. Never matched against bytes: each object is withheld alone, each execution with its
    #: primary object, as a derived-file hit is.
    listed_objects: frozenset[str] = field(default=frozenset())
    listed_executions: frozenset[str] = field(default=frozenset())

    @property
    def register_code(self) -> str:
        """The register and index form of an issue rule's code (``map.<namespace>.<code>``, H.6.3)."""
        assert self.code is not None
        return f"map.{self.code}"

    def hits(self, data: bytes) -> bool:
        if self.kind == "address":
            from agentprov.corpus.personas import address_digest, find_addresses

            return any(address_digest(raw) in self.digests or address_digest(raw) in self.object_digests
                       for _start, raw in find_addresses(data + b"\x00"))
        if self.needle is not None:
            return self.needle in data
        assert self.regex is not None
        return self.regex.search(data) is not None


@dataclass(frozen=True)
class WithholdPolicy:
    """The source profile's ``[withhold]`` policy (see the module docstring)."""

    profile_id: str
    profile_version: int
    profile_sha256: str  # "sha256:<hex>"
    rules: tuple[Rule, ...]
    scan_rules: tuple[str, ...] = ()
    #: The deepest archive level the profile's ``[[import.nested]]`` declarations allow (D-382), or ``None``: the decoded
    #: scan opens archives as deep as the import may (D-452). Not part of the recorded policy.
    archive_depth: int | None = None

    @property
    def ref(self) -> str:
        return f"{self.profile_id}@{self.profile_version}"

    @property
    def byte_rules(self) -> tuple[Rule, ...]:
        """The marker, pattern and address rules: those scanned over bytes."""
        return tuple(r for r in self.rules if r.kind not in ("issue", "object"))

    @property
    def issue_rules(self) -> tuple[Rule, ...]:
        """The issue rules (D-311): those that select executions by an AER seal issue code."""
        return tuple(r for r in self.rules if r.kind == "issue")

    @property
    def listed_rules(self) -> tuple[Rule, ...]:
        """The object rules (D-964): the objects and executions the corpus spec lists."""
        return tuple(r for r in self.rules if r.kind == "object")

    @property
    def width(self) -> int:
        return max((r.width for r in self.byte_rules), default=1)

    def record(self) -> WithheldPolicy:
        return WithheldPolicy(self.profile_id, self.profile_version, self.profile_sha256,
                              tuple((r.id, r.kind, r.scope) for r in self.rules), self.scan_rules)


def _refuse(message: str) -> WithholdError:
    return WithholdError(f"[withhold]: {message}", code="corpus.withhold.policy")


def _class_width(pattern: str, i: int) -> int:
    """The index after the character class starting at ``pattern[i] == '['``; refuses what the grammar excludes."""
    j = i + 1
    if j < len(pattern) and pattern[j] == "^":
        j += 1
    first = True
    while j < len(pattern):
        c = pattern[j]
        if c == "]" and not first:
            return j + 1
        if c == "[":
            raise _refuse("a pattern's character class holds no nested class")
        if c == "\\":
            if j + 1 >= len(pattern) or not (pattern[j + 1] in "dws" or not pattern[j + 1].isalnum()):
                raise _refuse("a pattern escape is \\d, \\w, \\s or escaped punctuation")
            j += 2
        else:
            j += 1
        first = False
    raise _refuse("a pattern's character class is not closed")


def compile_pattern(pattern: str) -> tuple[re.Pattern[bytes], int]:
    """Check ``pattern`` against the bounded grammar of the module docstring; return the compiled bytes pattern and the
    length of its longest match. :class:`WithholdError` for anything outside the grammar."""
    if not isinstance(pattern, str) or not pattern or len(pattern) > _MAX_PATTERN or not pattern.isascii():
        raise _refuse(f"a pattern is 1 to {_MAX_PATTERN} ASCII characters")
    if any(not c.isprintable() for c in pattern):
        raise _refuse("a pattern holds no control character")
    width = 0
    i = 0
    while i < len(pattern):
        c = pattern[i]
        if c == "[":
            i = _class_width(pattern, i)
        elif c == "\\":
            if i + 1 >= len(pattern) or not (pattern[i + 1] in "dws" or not pattern[i + 1].isalnum()):
                raise _refuse("a pattern escape is \\d, \\w, \\s or escaped punctuation")
            i += 2
        elif c in "()|.*+^$" or c in "?{}]":
            raise _refuse("a pattern has no group, alternation, '.', '*', '+', anchor or stray quantifier")
        else:
            i += 1
        repeat = 1
        if i < len(pattern) and pattern[i] == "?":
            i += 1
        elif i < len(pattern) and pattern[i] == "{":
            end = pattern.find("}", i)
            match = re.fullmatch(r"([0-9]+)(?:,([0-9]+))?", pattern[i + 1:end]) if end > i else None
            if match is None:
                raise _refuse("a pattern repetition is {n} or {m,n}")
            low, high = int(match.group(1)), int(match.group(2) or match.group(1))
            if not 0 <= low <= high <= _MAX_REPEAT or high == 0:
                raise _refuse(f"a pattern repetition is bounded: 0 <= m <= n <= {_MAX_REPEAT}, n >= 1")
            repeat = high
            i = end + 1
        width += repeat
    try:
        regex = re.compile(pattern.encode("ascii"))
    except re.error:
        raise _refuse("a pattern does not compile") from None
    return regex, width


def _note(value: object, where: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > NOTE_MAX or one_line_note(value) != value:
        raise _refuse(f"{where} public_note is one line of 1 to {NOTE_MAX} printable characters")
    return value


def parse_policy(profile: Mapping[str, Any], *, profile_id: str, profile_version: int, profile_sha256: str,
                 issue_declared: Callable[[str], bool] | None = None) -> WithholdPolicy | None:
    """The ``[withhold]`` table of a parsed source profile, or ``None`` when it has none (closed keys; strict)::

        [withhold]
        reason = "secret"                  # secret | personal_data | takedown | licence
        public_note = "planted canary credential (benchmark design); value never recorded"
        scan_rules = ["generic-api-key"]   # optional: release-scan rule ids the deposit backstop enforces

        [[withhold.rules]]
        id = "canary-marker"
        marker = "CANARY-"                 # a literal tag, never a secret value itself
        scope = "executions"               # or "object"; optional reason / public_note override the table's

        [[withhold.rules]]
        id = "canary-flagged"
        issue = "mcphunt.canary_flagged"   # D-311: an AER seal issue code; no scope (the execution and its primary)

    ``issue_declared`` answers whether a catalogue declares an issue code (:func:`declared_issue_codes`); when given, an
    issue rule whose code it does not declare is refused here (:func:`check_issue_codes` applies it later otherwise).
    """
    table = profile.get("withhold")
    if table is None:
        return None
    if not isinstance(table, Mapping) or not set(table) <= _TABLE_KEYS or "reason" not in table or "rules" not in table:
        raise _refuse("the table holds reason, public_note, rules and optionally scan_rules")
    reason = table["reason"]
    if reason not in REASONS:
        raise _refuse(f"reason is one of {', '.join(REASONS)}")
    note = _note(table.get("public_note"), "the table's")
    scan_rules = table.get("scan_rules", [])
    if not isinstance(scan_rules, list) or not all(isinstance(s, str) and _SCAN_RULE.fullmatch(s) for s in scan_rules):
        raise _refuse("scan_rules are release-scan rule ids")
    rules_in = table["rules"]
    if not isinstance(rules_in, list) or not rules_in:
        raise _refuse("at least one [[withhold.rules]] entry")
    rules: list[Rule] = []
    for n, entry in enumerate(rules_in):
        where = f"rule {n + 1}"
        if not isinstance(entry, Mapping) or not set(entry) <= _RULE_KEYS or "id" not in entry or (
                sum(key in entry for key in _SELECTORS) != 1):
            raise _refuse(f"{where} has an id and exactly one of marker, pattern or issue")
        rid = entry["id"]
        if not isinstance(rid, str) or _RULE_ID.fullmatch(rid) is None:
            raise _refuse(f"{where}: the id is [a-z0-9][a-z0-9_.-]*, at most 64 characters")
        if "issue" in entry and "scope" in entry:
            raise _refuse(f"rule {rid}: an issue rule has no scope (it withholds the execution and its primary object)")
        scope = entry.get("scope", "executions")
        if scope not in SCOPES:
            raise _refuse(f"rule {rid}: scope is executions or object")
        rule_reason = entry.get("reason", reason)
        if rule_reason not in REASONS:
            raise _refuse(f"rule {rid}: reason is one of {', '.join(REASONS)}")
        rule_note = _note(entry["public_note"], f"rule {rid}'s") if "public_note" in entry else note
        if "issue" in entry:
            code = entry["issue"]
            if not isinstance(code, str) or len(code) > 128 or ISSUE_CODE.fullmatch(code) is None:
                raise _refuse(f"rule {rid}: an issue is an AER seal issue code <namespace>.<code>")
            rules.append(Rule(rid, "issue", "executions", rule_reason, rule_note, code=code))
        elif "marker" in entry:
            marker = entry["marker"]
            if not isinstance(marker, str) or not _MIN_MARKER <= len(marker) <= _MAX_MARKER or one_line_note(marker) != marker:
                raise _refuse(f"rule {rid}: a marker is one line of {_MIN_MARKER} to {_MAX_MARKER} printable characters")
            needle = marker.encode("utf-8")
            rules.append(Rule(rid, "marker", scope, rule_reason, rule_note, needle=needle, width=len(needle)))
        else:
            regex, width = compile_pattern(entry["pattern"])
            rules.append(Rule(rid, "pattern", scope, rule_reason, rule_note, regex=regex, width=width))
    ids = [r.id for r in rules]
    if len(set(ids)) != len(ids):
        raise _refuse("rule ids are unique")
    codes = [r.code for r in rules if r.code is not None]
    if len(set(codes)) != len(codes):
        raise _refuse("an issue code is named by one rule")
    policy = WithholdPolicy(profile_id, profile_version, profile_sha256, tuple(sorted(rules, key=lambda r: r.id)),
                            tuple(sorted(set(scan_rules))), _declared_depth(profile))
    if issue_declared is not None:
        check_issue_codes(policy, issue_declared)
    return policy


def _declared_depth(profile: Mapping[str, Any]) -> int | None:
    """The largest ``max_depth`` of the profile's ``[[import.nested]]`` declarations (D-382), or ``None``. The import
    validated them; a value that is not a positive integer is ignored here (the global depth applies)."""
    imp = profile.get("import")
    nested = imp.get("nested") if isinstance(imp, Mapping) else None
    depths = [n["max_depth"] for n in nested if isinstance(n, Mapping) and type(n.get("max_depth")) is int
              and n["max_depth"] > 0] if isinstance(nested, list) else []  # fmt: skip
    return max(depths, default=None)


def check_issue_codes(policy: WithholdPolicy | None, issue_declared: Callable[[str], bool]) -> None:
    """Refuse an issue rule whose code no catalogue declares (``corpus.withhold.policy``): the trigger is bound to the
    closed, versioned ``issue_codes`` of the catalogue its namespace names (AD-18), never to free text."""
    for rule in () if policy is None else policy.issue_rules:
        assert rule.code is not None
        if not issue_declared(rule.code):
            raise _refuse(f"rule {rule.id}: the issue code is not declared by the {rule.code.split('.', 1)[0]} catalogue "
                          "this corpus uses")


def declared_issue_codes(catalogues: Mapping[str, int]) -> Callable[[str], bool]:
    """Whether the catalogue of a code's namespace, at the version ``catalogues`` records for it (a corpus's
    ``derivation.json`` or ``rule_catalogues``), declares the code. Catalogues are read as package data through
    :func:`agentprov.aer.rules.load_catalogue` (AD-14), which never imports an adapter family; a namespace the corpus does
    not use declares nothing."""
    from agentprov.aer.rules import load_catalogue

    cache: dict[str, frozenset[str] | None] = {}

    def declared(code: str) -> bool:
        namespace, _, tail = code.partition(".")
        if namespace not in cache:
            version = catalogues.get(namespace)
            try:
                cache[namespace] = None if version is None else load_catalogue(namespace, version).issue_codes
            except AgentProvError:
                cache[namespace] = None
        codes = cache[namespace]
        return codes is not None and tail in codes

    return declared


# ================================================================================================ scanning
def scan_chunks(chunks: Iterable[bytes], rules: Sequence[Rule]) -> frozenset[str]:
    """The ids of the rules that match anywhere in the concatenated ``chunks`` (a match may straddle two chunks). Only
    rule ids leave this function; the bytes are never logged or kept."""
    if not rules:
        return frozenset()
    keep = max(r.width for r in rules) - 1
    hit: set[str] = set()
    tail = b""
    iterator = iter(chunks)
    try:
        for chunk in iterator:
            if not chunk:
                continue
            window = tail + chunk
            for rule in rules:
                if rule.id not in hit and rule.hits(window):
                    hit.add(rule.id)
            if len(hit) == len(rules):
                break
            tail = window[-keep:] if keep else b""
    finally:
        close = getattr(iterator, "close", None)
        if callable(close):
            close()
    return frozenset(hit)


# ================================================================================================ the plan
@dataclass(frozen=True)
class WithholdPlan:
    """What sealing withholds: the ``WITHHELD.json`` document (``None`` when nothing is withheld), the stored objects to
    move (bare hex -> corpus label), the withheld executions and the register entries to add."""

    document: WithheldDocument | None
    objects: frozenset[str] = frozenset()
    executions: frozenset[str] = frozenset()
    present: Mapping[str, str] = field(default_factory=dict)
    register: tuple[RegisterEntry, ...] = ()
    #: D-454: one line per archive withheld because the decoded scan could not read it: its container chain (escaped
    #: labels, outermost first) and the closed code; the seal report prints them
    unscanned: tuple[str, ...] = ()
    #: D-453: how many stored archives the decoded scan read by their local headers (``scanned_partial``)
    partial: int = 0

    @property
    def empty(self) -> bool:
        return self.document is None


@dataclass
class _Cause:
    reason: str
    basis: str
    note: str
    decided_on: str | None
    finding: WithheldFinding | None = None
    affected: set[str] = field(default_factory=set)


@dataclass
class _Facts:
    """What the planner reads from the working corpus (injected so that the plan is a pure function of it)."""

    rows: Sequence[IndexRow]
    register: Sequence[RegisterEntry]
    members: Sequence[MemberRow]
    origins: Sequence[OriginRow]
    present: Mapping[str, tuple[str, int]]  # bare hex -> (label, size) of every stored object
    tombstones: Sequence[Any]  # agentprov.corpus.purge.Tombstone
    snapshots: Mapping[str, tuple[str, Mapping[str, Any] | None]]  # snapshot id -> (raw policy, recorded pin)
    stream: Callable[[str], Iterable[bytes]]  # corpus label -> chunks (stored-object limits)
    derived: Callable[[IndexRow], list[str]]  # the derived files of a row that exist
    artefacts: Callable[[IndexRow], Sequence[Mapping[str, Any]]]  # the AER header's artifacts[]
    #: the decoded scan (D-450): (stored objects, the rows of raw/members.jsonl, byte rules)
    decode: Callable[[Mapping[str, str], Sequence[MemberRow], Sequence[Rule]], DecodedScan] | None = None


class _Planner:
    def __init__(self, facts: _Facts, policy: WithholdPolicy | None, decided_on: str | None) -> None:
        self.f = facts
        self.policy = policy
        self.decided_on = decided_on
        self.causes: dict[str, list[_Cause]] = {}
        self.cites: dict[str, set[str]] = {}
        for row in facts.rows:
            for ref in row.raw:
                self.cites.setdefault(ref.sha256, set()).add(row.ex)
        self.member_of: dict[str, set[str]] = {}  # member -> containers that selected it
        self.selected: dict[str, set[str]] = {}  # container -> its selected members
        #: ultra raw-withhold EXTRA (the #6 pattern): what _size_and_media and _chain read per object, indexed in this one
        #: pass instead of a pass over every member row per object (objects x rows for a large archive)
        self.member_sizes: dict[str, set[int]] = {}  # member -> the sizes its rows record
        self.listed_in: dict[str, MemberRow] = {}  # member -> its selected, labelled row of least (container, label)
        for m in facts.members:
            if m.disposition == "selected" and m.sha256 is not None:
                self.member_of.setdefault(m.sha256, set()).add(m.container)
                self.selected.setdefault(m.container, set()).add(m.sha256)
            if m.sha256 is not None and m.size is not None:
                self.member_sizes.setdefault(m.sha256, set()).add(m.size)
            if m.sha256 is not None and m.disposition == "selected" and m.label is not None:
                least = self.listed_in.get(m.sha256)
                if least is None or (m.container, m.label) < (least.container, least.label or ""):
                    self.listed_in[m.sha256] = m  # the first of equal keys stays, as min() kept it
        self.origins: dict[str, list[dict[str, Any]]] = {}
        for o in facts.origins:
            self.origins.setdefault(o.sha256, []).append(o.origin.to_json())
        self.links: dict[str, set[tuple[str, str]]] = {}  # object -> (linked object, LINK_NOTES key) (D-315)
        for _sha, (descriptor, parts), (blob, source) in _links(facts.origins):
            for part in parts:
                self.links.setdefault(descriptor, set()).add((part, "part"))
                self.links.setdefault(part, set()).add((descriptor, "descriptor"))
            if blob is not None and source is not None:
                self.links.setdefault(blob, set()).add((source, "source"))
                self.links.setdefault(source, set()).add((blob, "carved"))
        self.rows = {row.ex: row for row in facts.rows}
        self.unscanned: dict[str, str] = {}  # stored archive -> why it could not be read in decoded form (D-450)
        self.partial = 0  # stored archives read by their local headers (D-453)
        self.decoded_hits: dict[str, list[_Cause]] = {}  # stored archive -> its decoded-scan hits (D-450)
        self.flagged: dict[str, set[str]] = {}  # register code -> executions with an entry of that code
        for entry in facts.register:
            if "ex" in entry.subject:
                self.flagged.setdefault(entry.code, set()).add(entry.subject["ex"])

    def add(self, sha: str, cause: _Cause) -> None:
        self.causes.setdefault(sha, []).append(cause)

    def citing(self, sha: str) -> set[str]:
        """Executions whose row cites the object or, for a container, one of its selected members at any nesting level
        (purge's set: both walk the closure of :func:`member_closure`; CB-1). The container map is the one built once in
        ``__init__``, so a call costs the closure's size, not a pass over every member row."""
        out = set(self.cites.get(sha, ()))
        for member in _closure(self.selected, sha):
            out |= self.cites.get(member, set())
        return out

    # -------------------------------------------------------------------------------------- causes
    def purged(self) -> None:
        for tomb in self.f.tombstones:
            self.add(tomb.sha256, _Cause(tomb.reason, "purge",
                                         f"purged from the private raw store ({tomb.reason}); tombstone dated {tomb.date} (G.9.6)",
                                         tomb.date, affected=self.citing(tomb.sha256)))

    def _snapshots_of(self, sha: str, seen: frozenset[str] = frozenset()) -> set[str]:
        """The snapshots whose pin vouched for an origin of the object (a member: its containers')."""
        from agentprov.corpus.manifest import origin_matches_pin

        out: set[str] = set()
        for origin in self.origins.get(sha, ()):
            if origin.get("kind") in ("member", "carved"):  # a derived object: its container's or source's snapshots
                container = origin.get("container" if origin.get("kind") == "member" else "from")
                hexed = container[7:] if isinstance(container, str) and container.startswith("sha256:") else container
                if isinstance(hexed, str) and hexed not in seen:
                    out |= self._snapshots_of(hexed, seen | {sha})
                continue
            out.update(sid for sid, (_, pin) in self.f.snapshots.items() if origin_matches_pin(origin, pin))
        return out

    def raw_policy(self) -> None:
        held = sorted(sid for sid, (policy, _) in self.f.snapshots.items() if policy == "withhold")
        if not held:
            return
        every = len(held) == len(self.f.snapshots)
        rows = {row.ex for row in self.f.rows if set(row.snapshot_ids) & set(held)}
        objects: dict[str, str] = {}  # sha -> snapshot id named in the note
        for ex in sorted(rows):
            sid = sorted(set(self.rows[ex].snapshot_ids) & set(held))[0]
            for ref in self.rows[ex].raw:
                objects.setdefault(ref.sha256, sid)
        for sha in sorted(set(self.origins) | set(self.f.present)):
            if sha in objects:
                continue
            found = sorted(set(held) & (set(held) if every else self._snapshots_of(sha)))
            if found:
                objects[sha] = found[0]
        for sha, sid in sorted(objects.items()):
            self.add(sha, _Cause("licence", "raw_policy", f"snapshot {sid} has raw policy withhold (H.4.1)",
                                 self.decided_on, affected=self.citing(sha) & rows))

    def profile_rules(self) -> None:
        policy = self.policy
        if policy is None:
            return
        rules = {r.id: r for r in policy.rules}
        byte_rules = policy.byte_rules

        def finding(label: str, rule: Rule, detector: str = DETECTOR) -> WithheldFinding:
            return WithheldFinding(detector, f"{policy.ref}:{rule.id}", f"{label}:{rule.id}")

        for row in self.f.rows:  # issue rules (D-311): the execution and its primary object, as a derived hit
            for rule in policy.issue_rules:
                if rule.register_code in row.issues or row.ex in self.flagged.get(rule.register_code, ()):
                    primary = next(ref.sha256 for ref in row.raw if ref.role == primary_role(row.mode))
                    self.add(primary, _Cause(rule.reason, "profile_rule", rule.public_note, self.decided_on,
                                             finding(row.aer_path, rule), {row.ex}))
        for rule in policy.listed_rules:  # D-964: what the corpus spec lists, by digest and id, never by value
            for sha in sorted(rule.listed_objects):
                if sha not in self.f.present:
                    raise WithholdError("the corpus spec's [withhold] lists a raw object this corpus does not store "
                                        "(D-964)", code="corpus.withhold.policy")
                self.add(sha, _Cause(rule.reason, "profile_rule", rule.public_note, self.decided_on,
                                     finding(self.f.present[sha][0], rule)))
            for ex in sorted(rule.listed_executions):
                if ex not in self.rows:
                    raise WithholdError("the corpus spec's [withhold] lists an execution this corpus does not hold "
                                        "(D-964)", code="corpus.withhold.policy")
                row = self.rows[ex]
                primary = next(ref.sha256 for ref in row.raw if ref.role == primary_role(row.mode))
                self.add(primary, _Cause(rule.reason, "profile_rule", rule.public_note, self.decided_on,
                                         finding(row.aer_path, rule), {row.ex}))
        if not byte_rules:
            return
        for sha, (label, _size) in sorted(self.f.present.items()):
            for rid in sorted(scan_chunks(self.f.stream(label), byte_rules)):
                rule = rules[rid]
                # D-963: an address withholds executions only through their own records (the derived-file hits below),
                # never through a raw object they share; the object is withheld alone (D-961 for withhold-object digests)
                affected = self.citing(sha) if rule.scope == "executions" and rule.kind != "address" else set()
                self.add(sha, _Cause(rule.reason, "profile_rule", rule.public_note, self.decided_on, finding(label, rule),
                                     affected))
        if self.f.decode is not None:  # D-450: every stored archive in decoded form, its unselected members too
            from agentprov.corpus.withhold_scan import DECODED_DETECTOR

            decoded = self.f.decode({sha: label for sha, (label, _size) in self.f.present.items()}, self.f.members,
                                    byte_rules)  # fmt: skip
            for sha, found in sorted(decoded.hits.items()):
                label = self.f.present[sha][0]
                self.decoded_hits[sha] = [_Cause(rules[rid].reason, "profile_rule", rules[rid].public_note,
                                                 self.decided_on, finding(label, rules[rid], DECODED_DETECTOR))
                                          for rid in sorted(found)]  # fmt: skip
            self.unscanned = dict(decoded.unscanned)
            self.partial = len(decoded.partial)
        for row in self.f.rows:
            for label in self.f.derived(row):
                for rid in sorted(scan_chunks(self.f.stream(label), byte_rules)):
                    rule = rules[rid]
                    primary = next(ref.sha256 for ref in row.raw if ref.role == primary_role(row.mode))
                    self.add(primary, _Cause(rule.reason, "profile_rule", rule.public_note, self.decided_on,
                                             finding(label, rule), {row.ex}))

    def containers(self) -> None:
        pending = sorted(self.causes)
        done: set[str] = set()
        while pending:
            sha = pending.pop()
            if sha in done:
                continue
            done.add(sha)
            reason = _first(REASONS, [c.reason for c in self.causes[sha]])
            for container in sorted(self.member_of.get(sha, ())):
                if container not in self.f.present and container not in self.causes:
                    continue  # a container that is neither stored nor withheld holds no released bytes here
                if self._close(container, reason, "an archive that holds a withheld member object (AD-12)"):
                    done.discard(container)
                    pending.append(container)
            for linked, kind in sorted(self.links.get(sha, ())):  # D-315: split parts, carved blobs, both ways
                if linked not in self.origins:
                    continue  # no origin row, so nothing is stored or listed for it here
                if self._close(linked, reason, LINK_NOTES[kind]):
                    done.discard(linked)
                    pending.append(linked)

    def _close(self, target: str, reason: str, note: str) -> bool:
        """Give ``target`` its one container cause, holding the first reason (REASONS order) of everything it holds: a
        later member with a higher-priority reason upgrades it, so the result does not depend on the order in which the
        members are reached. ``True`` when the cause is new or changed (the closure then carries it outward)."""
        held = next((c for c in self.causes.get(target, ()) if c.basis == "container"), None)
        if held is None:
            self.add(target, _Cause(reason, "container", note, self.decided_on))
            return True
        if REASONS.index(reason) < REASONS.index(held.reason):
            held.reason = reason
            return True
        return False

    # -------------------------------------------------------------------------------------- the document
    def _size_and_media(self, sha: str) -> tuple[int | None, str | None]:
        size = self.f.present[sha][1] if sha in self.f.present else None
        if size is None:
            sizes = self.member_sizes.get(sha, set())
            size = next(iter(sizes)) if len(sizes) == 1 else None
        media: str | None = None
        for ex in sorted(self.cites.get(sha, ())):
            for art in self.f.artefacts(self.rows[ex]):
                if art.get("sha256") != sha:
                    continue
                if isinstance(art.get("media"), str) and re.fullmatch(r"[a-z]+/[A-Za-z0-9.+-]+", art["media"]):
                    media = media or art["media"]
                if size is None and isinstance(art.get("bytes"), int) and not isinstance(art["bytes"], bool):
                    size = art["bytes"]
            if media is not None and size is not None:
                break
        return size, media

    def build(self) -> WithholdPlan:
        self.purged()
        self.raw_policy()
        self.profile_rules()
        self.containers()
        # D-450: an archive whose decoded members match a rule, and that nothing above withholds, is withheld itself
        # (object level, as a container: its executions' own objects were scanned as stored); then its groups and the
        # archives that hold it are closed as for any withheld object. An archive already withheld keeps its basis.
        fresh = [sha for sha in sorted(self.decoded_hits) if sha not in self.causes]
        for sha in fresh:
            for cause in self.decoded_hits[sha]:
                self.add(sha, cause)
        if fresh:
            self.containers()
        # D-454: an archive the decoded scan still cannot read, and that nothing above withholds, is withheld itself (object
        # level: its good members, stored as their own objects, and their executions stay released); the archives that
        # hold it are closed as for any withheld object. The reason is the policy's.
        unread = sorted(sha for sha in self.unscanned if sha not in self.causes)
        if unread:
            assert self.policy is not None  # only byte rules start the decoded scan
            # the policy's reason: its byte rules' (they share the table's unless one overrides it; the first wins)
            reason = _first(REASONS, [r.reason for r in self.policy.rules if r.kind not in ("issue", "object")])
        for sha in unread:
            self.add(sha, _Cause(reason, "unscanned", UNSCANNED_NOTE, self.decided_on))
        if unread:
            self.containers()
        unscanned_lines = tuple(f"{self._chain(sha)} ({self.unscanned[sha]})" for sha in unread)
        listed = {e.subject["ex"] for e in self.f.register if e.code == "release.withheld" and "ex" in e.subject}
        if not self.causes:
            _refuse_unexplained(listed, set())
            return WithholdPlan(None, partial=self.partial)
        executions: set[str] = set()
        entries: list[WithheldObject] = []
        for sha in sorted(self.causes):
            causes = self.causes[sha]
            if not self.origins.get(sha):
                raise WithholdError("a withheld object has no origin in raw/origins.jsonl; its pinned origin cannot be "
                                    "recorded (H.4.5)", code="corpus.withhold.no_origin")
            reason = _first(REASONS, [c.reason for c in causes])
            basis = _first(BASES_03, [c.basis for c in causes if c.reason == reason])
            chosen = next(c for c in causes if c.reason == reason and c.basis == basis)
            findings = sorted((c.finding for c in causes if c.basis == "profile_rule" and c.finding is not None),
                              key=lambda f: (f.fingerprint, f.rule))
            affected = set().union(*(c.affected for c in causes))
            executions |= affected
            size, media = self._size_and_media(sha)
            entries.append(WithheldObject(
                sha256=sha, origins=sorted_origins(self.origins[sha]), reason=reason, basis=basis,
                public_note=one_line_note(chosen.note), affected_executions=tuple(sorted(affected, key=_ascii)),
                bytes=size, media_type=media, decided_on=chosen.decided_on,
                finding=findings[0] if basis == "profile_rule" else None,
            ))  # fmt: skip
        _refuse_unexplained(listed, executions)
        # an execution's detail names the cause that withheld it: per object, the first (reason, basis) among the causes
        # that carry it (purge, raw_policy or profile_rule; the container and unscanned closures withhold no execution,
        # so an entry upgraded by a member's reason never lends it its basis), then the first basis over its objects
        basis_of: dict[str, str] = {}
        for causes in self.causes.values():
            for ex in set().union(*(c.affected for c in causes)):
                carrying = [c for c in causes if ex in c.affected]
                top = _first(REASONS, [c.reason for c in carrying])
                basis = _first(BASES_03, [c.basis for c in carrying if c.reason == top])
                basis_of[ex] = _first(BASES_03, [b for b in (basis_of.get(ex), basis) if b is not None])
        new_entries = tuple(
            RegisterEntry(subject={"ex": ex}, code="release.withheld", severity="info", stage="package",
                          disposition="withheld", detail=DETAILS[basis_of[ex]])
            for ex in sorted(executions - listed, key=_ascii)
        )  # fmt: skip
        withheld_executions = tuple(
            WithheldExecution(ex, tuple(self.rows[ex].snapshot_ids), self.rows[ex].to_json()["digests"])
            for ex in sorted(executions, key=_ascii)
        )  # fmt: skip
        document = WithheldDocument(tuple(entries), withheld_executions,
                                    () if self.policy is None else (self.policy.record(),))
        present = {sha: self.f.present[sha][0] for sha in self.causes if sha in self.f.present}
        return WithholdPlan(document, frozenset(self.causes), frozenset(executions), present, new_entries,
                            unscanned_lines, self.partial)

    def _chain(self, sha: str) -> str:
        """The container chain of a stored object for the seal report: the labels from the outermost stored container down
        to it (``<container>!/<member>``), escaped; its corpus label when no container lists it."""
        from agentprov.ingest.quote import escape_untrusted_line

        names: list[str] = []
        current, seen = sha, set()
        while current not in seen and len(names) < 8:
            seen.add(current)
            row = self.listed_in.get(current)
            if row is None:
                break
            names.append(escape_untrusted_line(row.label or "", max_chars=120))
            current = row.container
        top = self.f.present.get(current, (current[:12], 0))[0]
        return "!/".join([escape_untrusted_line(top, max_chars=120), *reversed(names)])


def member_closure(members: Iterable[MemberRow], digest: str) -> set[str]:
    """Every member object selected below the container ``digest`` in ``raw/members.jsonl``, at every nesting level (a
    nested archive's members, its nested archives' members, ...). Purge and the seal planner both use it, so the
    executions a purge registers as withheld are exactly those the seal explains (CB-1: one level used to miss the
    executions of a nested archive's members, and a purge-only fix would make the seal refuse its own register)."""
    below: dict[str, set[str]] = {}
    for row in members:
        if row.disposition == "selected" and row.sha256 is not None:
            below.setdefault(row.container, set()).add(row.sha256)
    return _closure(below, digest)


def _closure(below: Mapping[str, set[str]], digest: str) -> set[str]:
    """The closure of :func:`member_closure` over a prebuilt container -> selected members map (the planner keeps one)."""
    out: set[str] = set()
    pending = [digest]
    while pending:
        for member in below.get(pending.pop(), ()):
            if member not in out and member != digest:  # a cycle (a member that is an ancestor) ends here
                out.add(member)
                pending.append(member)
    return out


def _links(origins: Iterable[OriginRow]) -> Iterator[tuple[str, tuple[str, tuple[str, ...]], tuple[str | None, str | None]]]:
    """For every origin row: ``(object, (descriptor, its parts), (carved blob, its source))``, the parts empty and the
    pair ``(None, None)`` when the row is not of that kind (D-244, D-218). Digests are bare hex."""
    for row in origins:
        data = row.origin.data
        parts: tuple[str, ...] = ()
        pair: tuple[str | None, str | None] = (None, None)
        if row.origin.kind == "split":
            parts = tuple(str(p).removeprefix("sha256:") for p in data.get("parts", ()))
        elif row.origin.kind == "carved":
            pair = (row.sha256, str(data.get("from", "")).removeprefix("sha256:"))
        yield row.sha256, (row.sha256, parts), pair


def linked_objects(origins: Iterable[OriginRow]) -> list[tuple[str, tuple[str, ...]]]:
    """The groups of objects D-315 withholds together, as ``(kind, members)``: ``split`` (a descriptor, then its parts)
    and ``carved`` (a blob, then its source); bare hex. ``chain`` checks that ``WITHHELD.json`` lists every member of a
    group or none."""
    groups: list[tuple[str, tuple[str, ...]]] = []
    for _sha, (descriptor, parts), (blob, source) in _links(origins):
        if parts:
            groups.append(("split", (descriptor, *parts)))
        if blob is not None and source:
            groups.append(("carved", (blob, source)))
    return groups


def _refuse_unexplained(listed: set[str], executions: set[str]) -> None:
    unexplained = listed - executions
    if unexplained:
        raise WithholdError(f"{len(unexplained)} execution(s) have release.withheld in the register but no tombstone, "
                            "withhold snapshot or profile rule explains it; withholding is never inferred from the "
                            "register alone (H.4.5)", code="corpus.withhold.unexplained")


def _first(order: Sequence[str], values: Iterable[str]) -> str:
    found = set(values)
    return next(v for v in order if v in found)


def _ascii(ex: str) -> bytes:
    return ex.encode("ascii")


def plan_withholding(
    *,
    rows: Sequence[IndexRow],
    register: Sequence[RegisterEntry],
    members: Sequence[MemberRow],
    origins: Sequence[OriginRow],
    present: Mapping[str, tuple[str, int]],
    tombstones: Sequence[Any],
    snapshots: Mapping[str, tuple[str, Mapping[str, Any] | None]],
    stream: Callable[[str], Iterable[bytes]],
    derived: Callable[[IndexRow], list[str]],
    artefacts: Callable[[IndexRow], Sequence[Mapping[str, Any]]],
    policy: WithholdPolicy | None = None,
    decided_on: str | None = None,
    decode: Callable[[Mapping[str, str], Sequence[MemberRow], Sequence[Rule]], DecodedScan] | None
    | Literal["default"] = "default",
) -> WithholdPlan:
    """Plan what a seal withholds (see the module docstring). Pure: every read goes through the callables given.
    ``decode`` is the decoded scan of the stored archives (D-450): by default
    :func:`agentprov.corpus.withhold_scan.scan_archives` over ``stream``; ``None`` turns it off (only tests do)."""
    if decode == "default":
        decode = _default_decode(stream, None if policy is None else policy.archive_depth)
    facts = _Facts(rows, register, members, origins, present, tombstones, snapshots, stream, derived, artefacts, decode)
    return _Planner(facts, policy, decided_on).build()


def _default_decode(
    stream: Callable[[str], Iterable[bytes]], archive_depth: int | None,
) -> Callable[[Mapping[str, str], Sequence[MemberRow], Sequence[Rule]], DecodedScan]:
    def decode(objects: Mapping[str, str], members: Sequence[MemberRow], rules: Sequence[Rule]) -> DecodedScan:
        from agentprov.corpus.withhold_scan import scan_archives

        return scan_archives(objects, stream, rules, max_depth=archive_depth, members=members)

    return decode


def derived_labels(layout: Any, row: IndexRow, exists: Callable[[str], bool]) -> list[str]:
    """The derived files of ``row`` that exist: AER, SEM, PROV and the transcript view (H.1.2)."""
    labels = [row.aer_path, *sorted((row.sem_paths or {}).values()), *sorted((row.prov_paths or {}).values())]
    labels.append(layout.view_relpath(TRANSCRIPT_VIEW, row.ex))
    return [label for label in labels if exists(label)]


def execution_labels(layout: Any, execution: WithheldExecution) -> list[str]:
    """Every derived file a withheld execution had (from its recorded digests; the view path too)."""
    labels = [layout.aer_relpath(execution.ex)]
    labels += [layout.sem_relpath(p, execution.ex) for p in execution.sem_profiles()]
    labels += [layout.prov_relpath(s, execution.ex) for s in execution.prov_specs()]
    labels.append(layout.view_relpath(TRANSCRIPT_VIEW, execution.ex))
    return labels


# ================================================================================================ the backstop
def released_labels(labels: Iterable[str]) -> list[str]:
    """The files of a sealed tree a withholding rule must not match: every file except the byte copies of package data
    (``rules/**``, which hold the profile and so its markers, and ``schemas/**``) and ``checksums.sha256``."""
    return sorted(label for label in labels
                  if not label.startswith(("rules/", "schemas/")) and label != "checksums.sha256")  # fmt: skip


#: The rule id under which :func:`rescan` reports an archive it could not read in decoded form when the caller gives no
#: ``unscanned`` collector; never a valid rule id (:data:`_RULE_ID`), so it cannot be taken for one.
UNSCANNED_RULE: Final = "<unscanned>"
#: The generated ``public_note`` of an archive withheld because the decoded scan could not read it (D-454).
UNSCANNED_NOTE: Final = "an archive the withholding scan could not read in decoded form is withheld unread (D-454)"
_RAW_OBJECT: Final = re.compile(r"raw/objects/[0-9a-f]{2}/(?P<sha>[0-9a-f]{64})\.[a-z]+")


def listed_backstop(policy: WithholdPolicy, labels: Iterable[str], rows: Iterable[IndexRow]) -> list[tuple[str, str]]:
    """``(kind, id)`` for every object (``"object"``, sha256 hex) or execution (``"execution"``, id) the corpus spec's
    ``[withhold]`` table lists (D-964) that the sealed tree still releases: a listed object among ``labels`` (the
    released files) or a listed execution with an index row. The backstop of ``verify --level chain``
    (``withheld.listed_released``) and of the deposit builder."""
    objects = {m["sha"] for label in labels if (m := _RAW_OBJECT.fullmatch(label))}
    ids = {row.ex for row in rows}
    out: list[tuple[str, str]] = []
    for rule in policy.listed_rules:
        out += [("object", sha) for sha in sorted(rule.listed_objects & objects)]
        out += [("execution", ex) for ex in sorted(rule.listed_executions & ids)]
    return out


def rescan(labels: Iterable[str], stream: Callable[[str], Iterable[bytes]], policy: WithholdPolicy, *,
           unscanned: list[tuple[str, str]] | None = None, decode: bool = True) -> list[tuple[str, str]]:
    """``(label, rule id)`` for every released file a rule of ``policy`` matches (:func:`released_labels`); the backstop of
    ``verify --level chain`` (``withheld.rule_hit``) and of the deposit builder. Never the match itself.

    Every released stored archive is also read in decoded form (D-450, :mod:`agentprov.corpus.withhold_scan`); a hit in
    it is reported with the archive's label. An archive that cannot be read decoded is appended to ``unscanned`` as
    ``(label, code)``; without that collector it is reported as a hit of :data:`UNSCANNED_RULE`, so a backstop that
    does not know the code still fails. ``decode=False`` (tests only) skips the decoded scan.
    """
    hits: list[tuple[str, str]] = []
    if not policy.byte_rules:
        return hits
    labels = list(labels)
    released = released_labels(labels)
    for label in released:
        hits.extend((label, rid) for rid in sorted(scan_chunks(stream(label), policy.byte_rules)))
    if decode:
        from agentprov.corpus.withhold_scan import scan_archives

        objects = {m["sha"]: label for label in released if (m := _RAW_OBJECT.fullmatch(label))}
        decoded = scan_archives(objects, stream, policy.byte_rules, max_depth=policy.archive_depth,
                                members=_released_members(labels, stream))
        hits.extend((objects[sha], rid) for sha in sorted(decoded.hits) for rid in sorted(decoded.hits[sha]))
        for sha, code in sorted(decoded.unscanned.items()):
            if unscanned is not None:
                unscanned.append((objects[sha], code))
            else:
                hits.append((objects[sha], UNSCANNED_RULE))
    return hits


def _released_members(labels: Iterable[str], stream: Callable[[str], Iterable[bytes]]) -> list[MemberRow]:
    """The rows of the released ``raw/members.jsonl`` (D-231) that ``raw/origins.jsonl`` confirms: a stored row counts
    only if a ``member`` origin of its object names the same container and label, so an edited ``members.jsonl`` alone
    cannot make a member be skipped. A file that does not parse gives nothing: every member is then read through its
    container (stricter, never laxer); ``chain`` reports the files themselves."""
    from agentprov.raw.members import decode_members
    from agentprov.raw.origins import decode_origins

    present = set(labels)
    if "raw/members.jsonl" not in present or "raw/origins.jsonl" not in present:
        return []
    try:
        rows = decode_members(b"".join(stream("raw/members.jsonl")))
        origins = decode_origins(b"".join(stream("raw/origins.jsonl")))
    except (AgentProvError, TypeError):  # ultra raw-withhold #10: a field of the wrong type does not parse either
        return []
    confirmed = {(o.sha256, str(o.origin.data.get("container", "")).removeprefix("sha256:"), o.origin.data.get("label"))
                 for o in origins if o.origin.kind == "member"}  # fmt: skip
    return [m if m.disposition != "selected" or (m.sha256, m.container, m.label) in confirmed
            else dataclasses.replace(m, sha256=None, disposition="not_selected") for m in rows]  # read through its container


def issue_backstop(policy: WithholdPolicy, register: Iterable[RegisterEntry], rows: Iterable[IndexRow],
                   seal_codes: Mapping[str, Iterable[str]] | None = None) -> list[tuple[str, str]]:
    """``(ex, rule id)`` for every **released** execution that carries the code of an issue rule (D-311): an index row
    whose ``issues`` holds ``map.<code>``, a register entry ``map.<code>`` for a released execution (the register keeps
    the entries of withheld executions too, D-231, so the selection is re-derived from released files), or, when
    ``seal_codes`` (execution id -> its AER seal's issue codes) is given, the AER seal itself. Execution ids and rule ids
    only."""
    rules = policy.issue_rules
    if not rules:
        return []
    released = {row.ex: row for row in rows}
    flagged: dict[str, set[str]] = {}
    for entry in register:
        if "ex" in entry.subject:
            flagged.setdefault(entry.code, set()).add(entry.subject["ex"])
    hits: set[tuple[str, str]] = set()
    for rule in rules:
        assert rule.code is not None
        for ex, row in released.items():
            in_seal = seal_codes is not None and rule.code in set(seal_codes.get(ex, ()))
            if rule.register_code in row.issues or ex in flagged.get(rule.register_code, ()) or in_seal:
                hits.add((ex, rule.id))
    return sorted(hits, key=lambda h: (h[0].encode("ascii"), h[1]))


def issue_carriers(policy: WithholdPolicy, register: Iterable[RegisterEntry]) -> dict[str, set[str]]:
    """Issue rule id -> the executions the register records with its code (released or withheld; D-231)."""
    by_code = {rule.register_code: rule.id for rule in policy.issue_rules}
    out: dict[str, set[str]] = {rid: set() for rid in by_code.values()}
    for entry in register:
        if entry.code in by_code and "ex" in entry.subject:
            out[by_code[entry.code]].add(entry.subject["ex"])
    return out


#: The id of the rule that withholds the e-mail addresses a corpus's persona files list as class ``withhold`` (D-810).
ADDRESS_RULE_ID: Final = "email-withheld"
ADDRESS_NOTE: Final = "an e-mail address that may identify a third party (D-810)"
#: The id of the rule that withholds what the corpus spec's ``[withhold]`` table lists (D-964).
LISTED_RULE_ID: Final = "secret-withheld"
LISTED_NOTE: Final = "a credential-like value a release-scan review could not show to be synthetic (D-964)"


def withhold_listed(spec_bytes: bytes) -> tuple[frozenset[str], frozenset[str]]:
    """``(objects, executions)`` of a corpus spec's ``[withhold]`` table (D-964): the stored raw objects as sha256 hex and
    the execution ids; both empty for a spec without the table."""
    from agentprov.corpus.spec import CorpusSpecError, parse_spec

    try:
        spec = parse_spec(spec_bytes)
    except CorpusSpecError as exc:
        raise WithholdError(f"the corpus spec is not valid ({exc})", code="corpus.withhold.policy") from None
    return frozenset(o.removeprefix("sha256:") for o in spec.withhold_objects), frozenset(spec.withhold_executions)


def load_policy(data: bytes, *, profile_id: str, profile_version: int, catalogues: Mapping[str, int],
                addresses: frozenset[str] = frozenset(),
                object_addresses: frozenset[str] = frozenset(),
                listed: tuple[frozenset[str], frozenset[str]] = (frozenset(), frozenset())) -> WithholdPolicy | None:
    """:func:`policy_of_profile`, then :func:`check_issue_codes` against the catalogues the corpus records (namespace ->
    version): what sealing, ``chain`` and the deposit builder read. ``addresses`` are the digests of the persona files'
    ``withhold`` class and ``object_addresses`` those of ``withhold-object`` (:func:`withhold_address_classes`): they add
    one ``address`` rule (:data:`ADDRESS_RULE_ID`, scope ``executions``, reason ``personal_data``) to the profile's
    policy, or make that its only rule. A raw object the rule hits is withheld alone (D-961, D-963). The
    backstops only match bytes, so they may pass both classes as ``addresses``. ``listed`` is ``(objects, executions)``
    of the corpus spec's ``[withhold]`` table (:func:`withhold_listed`): they add one ``object`` rule
    (:data:`LISTED_RULE_ID`, reason ``secret``, D-964) the same way."""
    import hashlib

    policy = policy_of_profile(data, profile_id=profile_id, profile_version=profile_version)
    check_issue_codes(policy, declared_issue_codes(catalogues))
    added: list[Rule] = []
    if addresses or object_addresses:
        from agentprov.corpus.personas import EMAIL_AHEAD, EMAIL_BEHIND

        added.append(Rule(id=ADDRESS_RULE_ID, kind="address", scope="executions", reason="personal_data",
                          public_note=ADDRESS_NOTE, width=EMAIL_AHEAD + EMAIL_BEHIND + 2,
                          digests=addresses - object_addresses, object_digests=object_addresses))
    objects, executions = listed
    if objects or executions:
        added.append(Rule(id=LISTED_RULE_ID, kind="object", scope="object", reason="secret", public_note=LISTED_NOTE,
                          listed_objects=frozenset(objects), listed_executions=frozenset(executions)))
    if not added:
        return policy
    if policy is None:
        return WithholdPolicy(profile_id, profile_version, "sha256:" + hashlib.sha256(data).hexdigest(),
                              tuple(sorted(added, key=lambda r: r.id)))
    for rule in added:
        if any(r.id == rule.id for r in policy.rules):
            raise WithholdError(f"[withhold]: the rule id {rule.id} is reserved (D-810, D-964)",
                                code="corpus.withhold.policy")
    return dataclasses.replace(policy, rules=tuple(sorted((*policy.rules, *added), key=lambda r: r.id)))


def withhold_addresses(spec_bytes: bytes, read: Callable[[str], bytes | None]) -> frozenset[str]:
    """The digests of the ``withhold`` and ``withhold-object`` classes together (:func:`withhold_address_classes`): what
    the byte backstops match."""
    held, objects = withhold_address_classes(spec_bytes, read)
    return held | objects


def withhold_address_classes(spec_bytes: bytes, read: Callable[[str], bytes | None]) -> tuple[frozenset[str], frozenset[str]]:
    """``(withhold, withhold-object)``: the digests of the two classes of the persona files a corpus spec names (D-810;
    one ``address`` rule withholds both: the raw objects that hold one, each alone, and the executions whose own derived
    records hold one, D-961, D-963). ``read(name)`` gives a
    persona file's bytes by its file name (from the working directory beside the spec, or from ``rules/personas/`` of a
    sealed tree), or ``None``. A missing or invalid file is a :class:`WithholdError`, as is a digest that has two classes."""
    from agentprov.corpus.personas import PersonaError, persona_digests
    from agentprov.corpus.spec import CorpusSpecError, parse_spec

    try:
        spec = parse_spec(spec_bytes)
    except CorpusSpecError as exc:
        raise WithholdError(f"the corpus spec is not valid ({exc})", code="corpus.withhold.policy") from None
    files = []
    for relative, _digest in spec.persona_files:
        data = read(relative.rsplit("/", 1)[-1])
        if data is None:
            raise WithholdError("a persona file the spec names is missing (D-810)", code="corpus.withhold.policy")
        files.append(data)
    try:
        found = persona_digests(files)
        return found["withhold"], found["withhold-object"]
    except PersonaError as exc:
        raise WithholdError(f"a persona file is not valid: {exc}", code="corpus.withhold.policy") from None


def policy_of_profile(data: bytes, *, profile_id: str, profile_version: int) -> WithholdPolicy | None:
    """The ``[withhold]`` policy of a source-profile file (its digest becomes the policy's), or ``None``."""
    import hashlib
    import tomllib

    try:
        doc = tomllib.loads(data.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError):
        raise WithholdError("the source profile is not valid UTF-8 TOML", code="corpus.withhold.policy") from None
    return parse_policy(doc, profile_id=profile_id, profile_version=profile_version,
                        profile_sha256="sha256:" + hashlib.sha256(data).hexdigest())
