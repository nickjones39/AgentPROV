"""The AER validator: streaming, single pass, every invariant and error code of C.17 (D8 tier 2).

:class:`AerValidator` is fed one line at a time (:meth:`~AerValidator.feed`) and holds the id table, the part
table, the ``after`` graph and the accounting tallies, never the records. :meth:`~AerValidator.finish` runs the
end-of-stream checks (seal, accounting, unresolved references, cycles) and returns a :class:`ValidationReport`.

* Authoritative: the JSON Schema ``schemas/aer-0.1.schema.json`` is published for consumers and differentially
  tested against the *structural subset* checked by :mod:`agentprov.aer._structure`.
* Release vs dev: findings marked (R) in C.17 are errors in ``release`` mode and warnings in ``dev`` mode.
* Skipped checks are listed in ``report.skipped`` and never count as passed (``report.passed`` is False while
  anything was skipped). Corpus-tier invariants (V27, V28, V29) are not checkable on one file and are listed in
  ``report.deferred``.
* Findings never contain text taken from the file: only codes, invariants, line numbers, JSON Pointers into the
  record, fixed reason labels and ids that already matched the local-id grammar. Anything else would be hostile
  source text and is shown as a length and a digest.

Parsing of each line goes through ``agentprov.ingest.loaders`` (via :func:`agentprov.aer.canon.loads_strict`).
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any, Final, Literal

from agentprov.aer import READABLE_VERSIONS, RECORD_KINDS, _structure
from agentprov.aer import types as T
from agentprov.aer.accounting import CORE_CHECK_IDS, Accounting, AccountingTally, fold_status
from agentprov.aer.canon import (
    I_JSON_MAX,
    CanonError,
    LexHints,
    dumps_line,
    loads_strict,
    pointer_escape,
    utf16_order,
)
from agentprov.aer.evidence import (
    asserted_fields,
    effective_tag,
    effective_tags,
    is_prefix,
    tag_class,
)
from agentprov.aer.ids import (
    canonical_key_loc,
    import_execution_id,
    mapping_id,
    split_part_id,
)
from agentprov.aer.locators import LocatorError, LocatorResolver, RawStore, pointer_exists, pointer_get
from agentprov.aer.rules import (
    CatalogueUnavailableError,
    RuleCatalogue,
    RuleEntry,
    RuleRegistry,
    rule_id_of,
)
from agentprov.io.canonical import jcs_bytes, sha256_hex

__all__ = [
    "MAX_LINE_BYTES",
    "AerValidator",
    "Finding",
    "ValidationReport",
    "iter_lines",
    "validate_file",
    "validate_records",
]

Mode = Literal["dev", "release"]
MAX_LINE_BYTES: Final = 16 * 1024 * 1024
#: C.2.1(6): a string value whose UTF-8 encoding exceeds 1 MiB is stored as a blob and referenced. Enforced for
#: ``aer/0.2`` records (D-216); the frozen ``aer/0.1`` rules never checked it (D-14).
MAX_INLINE_STRING_BYTES: Final = 1024 * 1024
MAX_FINDINGS: Final = 2000
_SENTINELS: Final = frozenset({"", "0", "unknown", "none", "null", "n/a", "na", "-"})
_SAFE: Final = re.compile(r"[A-Za-z0-9_#./:@+-]{0,64}")
_TIME_FIELDS: Final = frozenset({"start", "end", "start_naive", "end_naive"})
_TOKEN_FIELDS: Final = (
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "reasoning_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
)
_ALL_KINDS: Final = RECORD_KINDS
_INVARIANT: Final = {
    "aer.schema.kind": "AER-V04",
    "aer.schema.required": "AER-V07",
    "aer.schema.oneof": "AER-V07",
    "aer.schema.additional": "AER-V06",
    "aer.schema.pattern": "AER-V06",
    "aer.unk.reason": "AER-V16",
    "aer.subtype.missing": "AER-V30",
    "aer.blob.ref": "AER-V18",
}


def _list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: object) -> list[Any]:
    """A list-typed field as a list; any other value (a schema finding of its own) as empty, never iterated."""
    return value if isinstance(value, list) else []


def _hashable(*values: object) -> bool:
    """Whether every value is a JSON scalar (a hostile seal may hold objects where strings belong)."""
    return all(v is None or isinstance(v, str | int | float | bool) for v in values)


def _safe(text: object) -> str:
    """``text`` if it is plainly an identifier, else a length and digest: hostile text is never echoed."""
    if isinstance(text, str) and _SAFE.fullmatch(text):
        return text
    raw = str(text).encode("utf-8", "replace")
    return f"<{len(raw)}B sha256:{sha256_hex(raw)[:12]}>"


@dataclass(frozen=True, slots=True)
class Finding:
    """One validator finding."""

    code: str
    invariant: str
    line: int | None  # 0-based line number; None for end-of-stream findings
    pointer: str  # JSON Pointer into the record (or "" for the whole line)
    severity: str  # "error" | "warning"
    detail: str = ""

    def to_json(self) -> dict[str, object]:
        out: dict[str, object] = {
            "code": self.code,
            "invariant": self.invariant,
            "pointer": self.pointer,
            "severity": self.severity,
        }
        if self.line is not None:
            out["line"] = self.line
        if self.detail:
            out["detail"] = self.detail
        return out


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """Result of validating one AER file."""

    findings: tuple[Finding, ...]
    skipped: tuple[str, ...]
    deferred: tuple[str, ...]
    n_records: int
    execution_digest: str | None
    accounting_status: str | None
    mode: str
    truncated: bool = False
    ex: str | None = None
    #: error findings not stored because ``MAX_FINDINGS`` was reached (counted, never silently dropped)
    dropped_errors: int = 0
    _errors: tuple[Finding, ...] = field(default=(), repr=False)

    @property
    def errors(self) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.severity == "error")

    @property
    def warnings(self) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.severity == "warning")

    @property
    def ok(self) -> bool:
        """No error findings, stored or dropped by the findings cap."""
        return not self.errors and not self.dropped_errors

    @property
    def passed(self) -> bool:
        """No error findings *and* nothing skipped: a skipped check never counts as passed (D8)."""
        return self.ok and not self.skipped

    def codes(self) -> list[str]:
        return [f.code for f in self.findings]


@dataclass(slots=True)
class _Info:
    kind: str
    sub: str | None = None  # actor.kind / scope.kind / decision.verdict / fixture.kind
    n_parts: int = 0


@dataclass(slots=True)
class _Pending:
    line: int
    pointer: str
    target: str
    invariant: str
    kind_hint: str = ""


type Cond = Callable[[_Info], bool]
type RefSpec = tuple[str, object, frozenset[str], Cond | None]


def _kinds(*names: str) -> frozenset[str]:
    return frozenset(names)


_PART_ANY: Final = "part:*"
_PART_CALL: Final = "part:tool_call"


def _time_key(value: str) -> tuple[str, str]:
    """Sortable key of an RFC 3339 instant (fixed-width up to the seconds, then the padded fraction)."""
    main = value[:19]
    frac = value[20:].rstrip("Z") if len(value) > 19 and value[19] == "." else ""
    return main, frac.ljust(40, "0")


class AerValidator:
    """Streaming validator of one ``.aer.jsonl`` file.

    ``store`` is the raw store (locators and artefacts are verified against it; ``None`` skips those checks and
    says so in the report). ``catalogues`` supplies rule catalogues by the header's ``rules`` map. ``mode`` is
    ``"dev"`` or ``"release"`` (C.17 (R) marks). ``profile_digests`` maps ``(profile id, version)`` to the SHA-256
    of the package-resource profile (AER-V35); when absent that check is skipped.
    """

    def __init__(
        self,
        *,
        store: RawStore | None,
        catalogues: RuleRegistry,
        mode: Mode = "release",
        profile_digests: Mapping[tuple[str, int], str] | None = None,
    ) -> None:
        if mode not in ("dev", "release"):
            raise ValueError("mode must be 'dev' or 'release'")
        self._store = store
        self._cats = catalogues
        self._mode = mode
        self._profile_digests = profile_digests
        self._findings: list[Finding] = []
        self._truncated = False
        self._dropped_errors = 0
        self._skipped: set[str] = set()
        self._n = 0
        self._hasher = hashlib.sha256()
        self._pending_line: bytes | None = None
        self._header: dict[str, Any] | None = None
        self._seal: dict[str, Any] | None = None
        self._seal_line = -1
        self._ids: dict[str, _Info] = {}
        self._parts: dict[str, str] = {}
        self._artefact_ids: dict[str, dict[str, Any]] = {}
        self._pending: list[_Pending] = []
        self._after: dict[str, list[str]] = {}
        self._forward_after = False
        self._blobs: set[str] = set()
        self._tally = AccountingTally()
        self._run_scopes = 0
        self._catalogues: dict[str, RuleCatalogue | None] = {}
        self._declared: dict[str, int] = {}
        self._ns: dict[str, str] = {}
        self._identities: set[str] = set()
        self._verify_pending: dict[str, int] = {}
        self._resolver: LocatorResolver | None = None
        self._rule_cache: dict[str, RuleEntry | None] = {}
        self._finished = False
        self._ex: str | None = None

    # ------------------------------------------------------------------------------------------ reporting
    def _add(
        self,
        code: str,
        invariant: str,
        line: int | None,
        pointer: str = "",
        detail: str = "",
        *,
        release_only: bool = False,
    ) -> None:
        severity = "warning" if release_only and self._mode == "dev" else "error"
        if len(self._findings) >= MAX_FINDINGS:
            self._truncated = True
            if severity == "error":
                self._dropped_errors += 1
            return
        self._findings.append(Finding(code, invariant, line, pointer, severity, detail))

    def _skip(self, what: str) -> None:
        self._skipped.add(what)

    # ------------------------------------------------------------------------------------------ feed
    def feed(self, line: bytes, *, oversize: bool = False) -> None:
        """Validate the next line, **including its terminating LF** (a missing LF is a finding).

        ``oversize=True`` says the line exceeded :data:`MAX_LINE_BYTES` and ``line`` is only its head: the line is
        reported and not parsed.
        """
        if self._finished:
            raise RuntimeError("validator already finished")
        index = self._n
        self._n += 1
        if self._pending_line is not None:
            self._hasher.update(self._pending_line)
        self._pending_line = line
        if self._seal is not None:  # anything after the seal
            self._add("aer.order.envelope", "AER-V03", self._seal_line, "", "seal_not_last")
            self._seal = None
        if oversize or len(line) > MAX_LINE_BYTES:
            self._add("ingest.jsonl.line_too_long", "AER-V01", index)
            return
        if index == 0 and line.startswith(b"\xef\xbb\xbf"):
            self._add("ingest.json.bom", "AER-V01", index)
            return
        body = line
        if body.endswith(b"\n"):
            body = body[:-1]
            if body.endswith(b"\r"):
                self._add("ingest.jsonl.crlf", "AER-V01", index)
                body = body[:-1]
        else:
            self._add("ingest.jsonl.no_final_newline", "AER-V01", index)
        if body == b"":
            self._add("ingest.jsonl.blank", "AER-V01", index)
            return
        if b"\x00" in body:
            self._add("ingest.jsonl.nul", "AER-V01", index)
            return
        try:
            record = loads_strict(body)
        except CanonError as exc:
            self._add(exc.code, "AER-V02", index)
            return
        if not isinstance(record, dict):
            self._add("aer.schema.pattern", "AER-V06", index, "", "type_object")
            return
        try:
            canonical = dumps_line(record)[:-1]
        except CanonError:
            canonical = None
        if canonical != body:
            self._add("aer.jcs.noncanonical", "AER-V02", index)
        self._record(index, record)

    def feed_checked(self, line: bytes) -> list[Finding]:
        """:meth:`feed` and return the findings that this line produced (the writer's per-record gate)."""
        before = len(self._findings)
        self.feed(line)
        return list(self._findings[before:])

    @property
    def n_unresolved(self) -> int:
        """References seen so far that name no earlier record (each is a forward or dangling reference)."""
        return len(self._pending)

    @property
    def blob_digests(self) -> tuple[str, ...]:
        """Sorted unique ``sha256:<hex>`` digests of every well-formed ``$blob`` seen so far."""
        return tuple(sorted(self._blobs))

    def accounting_so_far(
        self, issues: Sequence[Mapping[str, object]] = (), extra_checks: Sequence[Mapping[str, Any]] = ()
    ) -> Accounting:
        """The accounting of the records fed so far (what the writer puts in the seal)."""
        return self._tally.finish(issues, extra_checks)

    # ------------------------------------------------------------------------------------------ dispatch
    def _record(self, index: int, rec: dict[str, Any]) -> None:
        kind = rec.get("k")
        if kind == "seal":
            if index == 0:
                self._add("aer.order.envelope", "AER-V03", index, "/k", "seal_first")
            if str((self._header or {}).get("aer", "0.1")) != "0.1":  # D-216 for the seal too (pre-round review #30)
                for pointer in _long_strings(rec, ""):
                    self._add("aer.string.inline_limit", "AER-V01", index, pointer, "over_1_mib")
            self._seal, self._seal_line = rec, index
            return
        # the format version of the file: the header's own value, then the header's for every later record (D-212)
        version = (str(rec.get("aer")) if kind == "execution" else str((self._header or {}).get("aer", "0.1")))
        findings = _structure.check_record(rec, version=version if version in READABLE_VERSIONS else "0.1")
        for code, pointer, key in findings:
            code = self._reclassify(rec, code, pointer, key)
            self._add(code, _INVARIANT.get(code, "AER-V06"), index, pointer, key, release_only=code == "aer.sentinel")
        if version != "0.1":  # D-216: C.2.1(6) under aer/0.2
            for pointer in _long_strings(rec, ""):
                self._add("aer.string.inline_limit", "AER-V01", index, pointer, "over_1_mib")
        if any(code == "aer.schema.kind" for code, _p, _k in findings):
            return
        if index == 0 and kind != "execution":
            self._add("aer.order.envelope", "AER-V03", index, "/k", "first_not_execution")
        if index > 0 and kind == "execution":
            self._add("aer.order.envelope", "AER-V03", index, "/k", "execution_not_first")
        if kind == "execution" and index == 0:
            self._header_checks(index, rec)
        self._common(index, rec)

    @staticmethod
    def _reclassify(rec: Mapping[str, Any], code: str, pointer: str, key: str) -> str:
        """A deny-listed placeholder in a typed time field is ``aer.sentinel``, not a pattern error (C.7.3)."""
        if code == "aer.schema.pattern" and key == "pattern":
            tokens = pointer.split("/")
            if len(tokens) == 3 and tokens[1] == "t" and tokens[2] in _TIME_FIELDS:
                value = rec.get("t", {}).get(tokens[2]) if isinstance(rec.get("t"), dict) else None
                if isinstance(value, str) and value.lower() in _SENTINELS:
                    return "aer.sentinel"
        return code

    # ------------------------------------------------------------------------------------------ header
    def _task_not_captured(self) -> bool:
        """The header names no task id and declares it ``not_captured`` (``aer/0.2``, D-219)."""
        header = self._header or {}
        task = header.get("task")
        unk = header.get("unk")
        return (str(header.get("aer")) != "0.1" and isinstance(task, dict) and "task_id" not in task
                and isinstance(unk, dict) and unk.get("/task/task_id") == "not_captured")

    def _header_checks(self, index: int, rec: dict[str, Any]) -> None:
        self._header = rec
        rules = rec.get("rules")
        if isinstance(rules, dict):
            self._declared = {k: v for k, v in rules.items() if isinstance(v, int) and not isinstance(v, bool)}
        ns = rec.get("ns")
        if isinstance(ns, dict):
            self._ns = {k: v for k, v in ns.items() if isinstance(v, str)}
            for prefix in sorted(self._ns):
                if prefix in T.RESERVED_PREFIXES:
                    self._add("aer.ext.undeclared", "AER-V23", index, "/ns/" + prefix, "reserved_prefix_redeclared")
        for namespace, version in sorted(self._declared.items()):
            try:
                self._catalogues[namespace] = self._cats.get(namespace, version)
            except CatalogueUnavailableError:
                self._catalogues[namespace] = None
                self._add("aer.rule.missing", "AER-V15", index, "/rules/" + _safe(namespace), "catalogue_unavailable")
        artefacts = rec.get("artifacts")
        if isinstance(artefacts, list):
            for k, entry in enumerate(artefacts):
                if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
                    continue
                if entry["id"] in self._artefact_ids:
                    self._add("aer.id.duplicate", "AER-V04", index, f"/artifacts/{k}/id")
                self._artefact_ids.setdefault(entry["id"], entry)
                origin = entry.get("origin")
                if isinstance(origin, dict) and origin.get("kind") == "local":
                    self._add("aer.schema.pattern", "AER-V20", index, f"/artifacts/{k}/origin/kind", "local_origin",
                              release_only=True)
        self._check_identity(index, rec)
        if self._store is not None:
            self._resolver = LocatorResolver(rec, self._store)
            for k, entry in enumerate(artefacts if isinstance(artefacts, list) else []):
                if isinstance(entry, dict) and isinstance(entry.get("id"), str):
                    try:
                        self._resolver.artefact_bytes(entry["id"])
                    except LocatorError as exc:
                        self._add(exc.code, "AER-V20", index, f"/artifacts/{k}")
        else:
            self._skip("raw-store checks (V20, V21): no store given")
        profile = rec.get("profile")
        if isinstance(profile, dict) and isinstance(profile.get("id"), str) and isinstance(profile.get("version"), int):
            if self._profile_digests is None:
                self._skip("profile digest (V35): no package profile digests given")
            else:
                expected = self._profile_digests.get((profile["id"], profile["version"]))
                if expected is None:
                    self._skip("profile digest (V35): profile not shipped")
                elif expected != profile.get("sha256"):
                    self._add("aer.blob.digest", "AER-V35", index, "/profile/sha256", "profile_digest",
                              release_only=True)

    def _check_identity(self, index: int, rec: dict[str, Any]) -> None:
        """AER-V22: ``source_key`` and ``ex``."""
        ex = rec.get("ex")
        self._ex = ex if isinstance(ex, str) else None
        source_key, mode = rec.get("source_key"), rec.get("mode")
        if not isinstance(source_key, dict) or not isinstance(source_key.get("sha256"), str):
            return
        want_role = "primary" if mode == "import" else "capture_log"
        listed = [
            a
            for a in _list(rec.get("artifacts"))
            if isinstance(a, dict) and a.get("sha256") == source_key["sha256"] and a.get("role") == want_role
        ]
        if not listed:
            self._add("aer.id.execution", "AER-V22", index, "/source_key/sha256", "no_artefact_with_role")
        loc = source_key.get("loc")
        if mode == "import" and isinstance(loc, dict):
            adapter, profile = rec.get("adapter"), rec.get("profile")
            try:
                key = canonical_key_loc(loc)
                expected = import_execution_id(
                    mapping_id(str(adapter["id"]), str(profile["id"])), source_key["sha256"], key  # type: ignore[index]
                )
            except (ValueError, KeyError, TypeError):
                self._add("aer.id.execution", "AER-V22", index, "/source_key/loc", "not_canonical_key_form")
            else:
                if expected != ex:
                    self._add("aer.id.execution", "AER-V22", index, "/ex", "ex_differs_from_import_execution_id")
        elif mode == "live":
            capture = rec.get("capture")
            session = capture.get("session") if isinstance(capture, dict) else None
            if loc != {} or ex != "ex_" + str(session):
                self._add("aer.id.execution", "AER-V22", index, "/ex", "live_ex_or_loc")
            log = capture.get("log") if isinstance(capture, dict) else None
            entry = self._artefact_ids.get(str(log))
            if entry is None or entry.get("role") != "capture_log":
                self._add("aer.ref.dangling", "AER-V22", index, "/capture/log", "capture_log_artefact")

    # ------------------------------------------------------------------------------------------ records
    def _common(self, index: int, rec: dict[str, Any]) -> None:
        kind: str = rec["k"]
        rid = rec.get("id")
        if not isinstance(rid, str):
            return
        if rid in self._ids:
            self._add("aer.id.duplicate", "AER-V04", index, "/id", _safe(rid))
        if kind == "scope" and rec.get("kind") == "run":
            self._run_scopes += 1
        if kind != "execution":
            self._tally.feed(rec)
        self._evidence(index, rec)
        self._unknowns(index, rec)
        self._extensions(index, rec)
        self._sources(index, rec)
        self._values(index, rec)
        self._references(index, rec)
        self._declarations(index, rec)
        self._kind_rules(index, rec)
        info = _Info(kind)
        if kind in ("actor", "scope", "decision", "fixture"):
            sub = {"actor": "kind", "scope": "kind", "decision": "verdict", "fixture": "kind"}[kind]
            value = rec.get(sub)
            info.sub = value if isinstance(value, str) else None
        if kind == "actor":
            code = rec.get("code")
            if isinstance(code, dict):
                for name in ("commit", "wheel_sha256"):
                    if isinstance(code.get(name), str):
                        self._identities.add(code[name])
        if kind == "message" and isinstance(rec.get("parts"), list):
            info.n_parts = len(rec["parts"])
            for k, part in enumerate(rec["parts"]):
                if isinstance(part, dict) and isinstance(part.get("t"), str):
                    self._parts[f"{rid}#{k}"] = part["t"]
        self._ids.setdefault(rid, info)

    # -------------------------------------------------------------------------------------- evidence
    def _unk_covers(self, rec: Mapping[str, Any], pointer: str, *, both: bool = False) -> bool:
        unk = rec.get("unk")
        if not isinstance(unk, dict):
            return False
        return any(is_prefix(q, pointer) or (both and is_prefix(pointer, q)) for q in unk if isinstance(q, str))

    def _rule_entry(self, rule_id: str) -> RuleEntry | None:
        if rule_id not in self._rule_cache:
            entry = None
            namespace = rule_id.split(".", 1)[0]
            cat = self._catalogues.get(namespace)
            if cat is not None:
                found = cat.get(rule_id)
                entry = found if found is not None and found.citable else None
            self._rule_cache[rule_id] = entry
        return self._rule_cache[rule_id]

    def _evidence(self, index: int, rec: dict[str, Any]) -> None:
        if not isinstance(rec.get("ev"), str):
            return
        evf = _dict(rec.get("evf"))
        for key in evf:
            if isinstance(key, str) and not (pointer_exists(rec, key) or self._unk_covers(rec, key)):
                self._add("aer.ref.dangling", "AER-V11", index, "/evf" + key, "evf_pointer")
        tags = effective_tags(rec)
        if any(not _structure._RE["tag"].fullmatch(t) for t in tags):
            return  # structure already reported the bad tag
        bare_o = "O" in tags
        any_o = any(tag_class(t) == "O" for t in tags)
        has_by = "by" in rec
        if bare_o and not has_by:
            self._add("aer.schema.required", "AER-V12", index, "/by", "by_for_bare_O")
        if has_by and not bare_o:
            self._add("aer.schema.additional", "AER-V12", index, "/by", "by_without_bare_O")
        if any_o and not rec.get("src"):
            self._add("aer.schema.required", "AER-V13", index, "/src", "src_for_observed")
        self._rule_coverage(index, rec, evf)

    def _rule_coverage(self, index: int, rec: dict[str, Any], evf: Mapping[str, Any]) -> None:
        refs = [r for r in _as_list(rec.get("rule")) if isinstance(r, str)]
        scoped: list[tuple[str, str]] = []  # (rule id, pointer)
        unscoped: list[str] = []
        for ref in refs:
            rid, sep, pointer = ref.partition("#")
            (scoped.append((rid, pointer)) if sep else unscoped.append(rid))
            if self._rule_entry(rid) is None and not self._known_missing(rid):
                self._add("aer.rule.missing", "AER-V15", index, "/rule", _safe(rid))
        # F-1 (pre-round review #37): a scoped rule's own pointer is evaluated too when a value is there, so a D value below
        # an evf key whose only applicable rule is I-class is refused as it is with an evf key (C.6.4). An absent pointer
        # that an unk declaration covers holds no value: the rule justifies the declaration (C.7), not a derived value.
        pointers = ["/" + f for f in asserted_fields(rec)] + [k for k in evf if isinstance(k, str)] + [
            p for _r, p in scoped if pointer_exists(rec, p)]
        seen: set[str] = set()
        has_i_pointer = False
        for pointer in pointers:
            if pointer in seen:
                continue
            seen.add(pointer)
            cls = tag_class(effective_tag(rec, pointer))
            if cls not in ("D", "I"):
                continue
            has_i_pointer = has_i_pointer or cls == "I"
            applicable = self._applicable(scoped, unscoped, pointer)
            if not applicable:
                self._add("aer.rule.missing", "AER-V14", index, pointer, "no_applicable_rule")
                continue
            if cls == "D" and any(self._class_of(r) == "I" for r in applicable):
                self._add("aer.rule.class", "AER-V14", index, pointer, "D_pointer_with_I_rule")
        if has_i_pointer and not any(self._class_of(r) == "I" for r in [*unscoped, *(r for r, _ in scoped)]):
            self._add("aer.rule.class", "AER-V14", index, "/rule", "I_pointer_without_I_rule")
        for _rule, pointer in scoped:
            if not (pointer_exists(rec, pointer) or self._unk_covers(rec, pointer, both=True)):
                self._add("aer.ref.dangling", "AER-V14", index, "/rule", "scoped_rule_pointer")
            elif tag_class(effective_tag(rec, pointer)) == "O" and not self._unk_covers(rec, pointer, both=True):
                self._add("aer.rule.class", "AER-V14", index, "/rule", "scoped_rule_on_O_value")
        self._verified_assumptions(index, [*unscoped, *(r for r, _ in scoped)])

    def _known_missing(self, rule_id: str) -> bool:
        """True when the namespace's catalogue is unavailable or undeclared and has been reported already."""
        namespace = rule_id.split(".", 1)[0]
        return namespace in self._catalogues and self._catalogues[namespace] is None

    def _class_of(self, rule_id: str) -> str | None:
        entry = self._rule_entry(rule_id)
        return entry.cls if entry is not None else None

    @staticmethod
    def _applicable(scoped: Sequence[tuple[str, str]], unscoped: Sequence[str], pointer: str) -> list[str]:
        matching = [(r, p) for r, p in scoped if is_prefix(p, pointer)]
        if matching:
            longest = max(len(p) for _, p in matching)
            return [r for r, p in matching if len(p) == longest]
        return list(unscoped)

    def _verified_assumptions(self, index: int, rule_ids: Iterable[str]) -> None:
        """AER-V34 (R): remember the first citation of each rule that has a ``verified`` assumption.

        The framework identity may be recorded by an actor that comes later in the file, so the comparison is made
        at the end of the stream (:meth:`_finish_verified`).
        """
        for rid in dict.fromkeys(rule_ids):
            entry = self._rule_entry(rid)
            if entry is not None and entry.verified_identities():
                self._verify_pending.setdefault(rid, index)

    def _finish_verified(self) -> None:
        for rid, line in self._verify_pending.items():
            entry = self._rule_entry(rid)
            identities = entry.verified_identities() if entry is not None else ()
            if not any(i.rsplit("@", 1)[-1] in self._identities or i.split(":", 1)[-1] in self._identities for i in identities):
                self._add("aer.rule.class", "AER-V34", line, "/rule", "verified_identity_not_recorded", release_only=True)

    # -------------------------------------------------------------------------------------- unknowns
    def _unknowns(self, index: int, rec: dict[str, Any]) -> None:
        unk = rec.get("unk")
        if isinstance(unk, dict):
            for pointer, reason in unk.items():
                if isinstance(reason, str) and reason in T.UNKNOWN_REASON_SET and reason != "ambiguous" and pointer_exists(rec, pointer):
                    self._add("aer.unk.conflict", "AER-V16", index, "/unk" + pointer, "value_beside_unk")
        if rec.get("k") == "message" and isinstance(rec.get("parts"), list):
            for k, part in enumerate(rec["parts"]):
                if (
                    isinstance(part, dict)
                    and part.get("t") == "tool_result"
                    and "responds_to" not in part
                    and not self._unk_covers(rec, f"/parts/{k}/responds_to")
                ):
                    self._add("aer.schema.required", "AER-V07", index, f"/parts/{k}/responds_to", "responds_to_or_unk")

    # -------------------------------------------------------------------------------------- extensions
    def _extensions(self, index: int, rec: dict[str, Any]) -> None:
        ext = rec.get("ext")
        if not isinstance(ext, dict):
            return
        kind_fields = _structure.KIND_FIELDS.get(rec["k"], frozenset())
        for prefix, content in ext.items():
            if prefix == "lex":
                self._check_lex(index, rec, content)
                continue
            if self._header is not None and prefix not in self._ns:
                self._add("aer.ext.undeclared", "AER-V23", index, "/ext/" + _safe(prefix), "namespace_not_declared")
            if isinstance(content, dict):
                for member in content:
                    if member in kind_fields:
                        self._add("aer.ext.shadows_core", "AER-V23", index, f"/ext/{_safe(prefix)}/{_safe(member)}",
                                  "duplicates_core_slot", release_only=True)

    def _check_lex(self, index: int, rec: dict[str, Any], lex: Any) -> None:
        if not isinstance(lex, dict):
            return
        hints = LexHints.from_dict(lex)
        for pointer, keys in sorted(hints.ord.items()):
            try:
                target = pointer_get(rec, pointer)
            except KeyError:
                self._add("aer.ref.dangling", "AER-V18", index, "/ext/lex/ord", "lex_pointer")
                continue
            if not isinstance(target, dict):
                self._add("aer.ref.dangling", "AER-V18", index, "/ext/lex/ord", "lex_ord_not_object")
            elif sorted(keys) != sorted(target) or len(set(keys)) != len(keys) or keys == utf16_order(list(target)):
                self._add("aer.schema.pattern", "AER-V18", index, "/ext/lex/ord", "lex_ord_not_a_permutation")
        for pointer in sorted(hints.flt):
            try:
                target = pointer_get(rec, pointer)
            except KeyError:
                self._add("aer.ref.dangling", "AER-V18", index, "/ext/lex/flt", "lex_pointer")
                continue
            is_number = (isinstance(target, int | float) and not isinstance(target, bool)) or (
                isinstance(target, dict) and set(target) == {"$int"}
            )
            if not is_number:
                self._add("aer.ref.dangling", "AER-V18", index, "/ext/lex/flt", "lex_flt_not_number")

    # -------------------------------------------------------------------------------------- locators
    def _sources(self, index: int, rec: dict[str, Any]) -> None:
        src = rec.get("src")
        if not isinstance(src, list):
            return
        for k, loc in enumerate(src):
            if not isinstance(loc, dict):
                continue
            artefact = loc.get("a")
            if isinstance(artefact, str) and artefact not in self._artefact_ids:
                self._add("aer.locator.dangling", "AER-V21", index, f"/src/{k}/a", "artefact_not_listed")
                continue
            if self._resolver is None:
                if "o" in loc and isinstance(artefact, str):
                    try:
                        pointer_get(self._artefact_ids[artefact].get("origin"), loc["o"])
                    except KeyError:
                        self._add("aer.locator.dangling", "AER-V21", index, f"/src/{k}", "origin_pointer")
                continue
            try:
                self._resolver.resolve(loc)
            except LocatorError as exc:
                self._add(exc.code, "AER-V21", index, f"/src/{k}")

    # -------------------------------------------------------------------------------------- values
    def _values(self, index: int, rec: dict[str, Any]) -> None:
        self._walk_numbers_and_blobs(index, rec)
        self._sentinels(index, rec)
        self._times(index, rec)

    def _walk_numbers_and_blobs(self, index: int, rec: dict[str, Any]) -> None:
        stack: list[tuple[Any, str]] = [(rec, "")]
        while stack:
            value, at = stack.pop()
            if isinstance(value, bool):
                continue
            if isinstance(value, int) and abs(value) > I_JSON_MAX:
                self._add("aer.schema.pattern", "AER-V18", index, at, "integer_outside_i_json")
            elif isinstance(value, float) and not (value == value and abs(value) != float("inf")):
                self._add("aer.schema.pattern", "AER-V18", index, at, "non_finite_number")
            elif isinstance(value, list):
                stack.extend((v, f"{at}/{i}") for i, v in enumerate(value))
            elif isinstance(value, dict):
                if set(value) == {"$lit"} and isinstance(value["$lit"], dict):
                    # C.11.3: the body's first-level member names are literal source keys, never reserved forms
                    body = value["$lit"]
                    stack.extend((v, f"{at}/$lit/{str(k).replace('~', '~0').replace('/', '~1')}") for k, v in body.items())
                elif "$blob" in value and isinstance(value["$blob"], str):
                    self._blob(index, at, value)
                elif set(value) == {"$int"} and isinstance(value["$int"], str):
                    try:
                        in_range = abs(int(value["$int"])) <= I_JSON_MAX
                    except ValueError:
                        in_range = False
                    if in_range:
                        self._add("aer.schema.pattern", "AER-V18", index, at, "int_wrapper_in_range")
                else:
                    stack.extend((v, f"{at}/{str(k).replace('~', '~0').replace('/', '~1')}") for k, v in value.items())

    def _blob(self, index: int, at: str, ref: dict[str, Any]) -> None:
        digest = ref["$blob"]
        if not _structure._RE["digest"].fullmatch(digest):
            return  # structure reports aer.blob.ref
        self._blobs.add(digest)
        if self._store is None:
            self._skip("raw-store checks (V20, V21): no store given")
            return
        hexdigest = digest[7:]
        try:
            if not self._store.has(hexdigest):
                self._add("aer.blob.missing", "AER-V21", index, at, "blob_not_stored")
            elif isinstance(ref.get("bytes"), int) and self._store.size(hexdigest) != ref["bytes"]:
                self._add("aer.blob.digest", "AER-V21", index, at, "blob_size")
        except KeyError:
            self._add("aer.blob.missing", "AER-V21", index, at, "blob_not_stored")

    def _typed_strings(self, rec: Mapping[str, Any]) -> Iterator[tuple[str, Any]]:
        """Typed string fields subject to the deny-list (C.7.3); verbatim fields are never listed."""
        kind = rec["k"]
        if kind == "execution" and isinstance(rec.get("task"), dict):
            for name, value in rec["task"].items():
                yield f"/task/{name}", value
        if kind == "actor":
            if "version" in rec:
                yield "/version", rec["version"]
            for group in ("model", "code"):
                if isinstance(rec.get(group), dict):
                    for name, value in rec[group].items():
                        yield f"/{group}/{name}", value
        if kind == "tool_execution" and "name" in rec:
            yield "/name", rec["name"]
        if isinstance(rec.get("t"), dict):
            for name in _TIME_FIELDS:
                if name in rec["t"]:
                    yield f"/t/{name}", rec["t"][name]
        if kind == "message" and isinstance(rec.get("parts"), list):
            for k, part in enumerate(rec["parts"]):
                if isinstance(part, dict) and part.get("t") in ("tool_call", "tool_result") and "name" in part:
                    yield f"/parts/{k}/name", part["name"]

    def _sentinels(self, index: int, rec: dict[str, Any]) -> None:
        for pointer, value in self._typed_strings(rec):
            if isinstance(value, str) and value.lower() in _SENTINELS and not pointer.startswith("/t/"):
                if not self._unk_covers(rec, pointer, both=True):
                    self._add("aer.sentinel", "AER-V17", index, pointer, "placeholder", release_only=True)
        if rec["k"] == "message" and rec.get("role") == "assistant" and isinstance(rec.get("parts"), list):
            for k, part in enumerate(rec["parts"]):
                if (
                    isinstance(part, dict)
                    and part.get("t") == "text"
                    and part.get("text") == ""
                    and not self._unk_covers(rec, f"/parts/{k}/text", both=True)
                ):
                    self._add("aer.sentinel", "AER-V17", index, f"/parts/{k}/text", "empty_text_for_null",
                              release_only=True)
        usage = rec.get("usage")
        if isinstance(usage, dict):
            tokens = [usage[n] for n in _TOKEN_FIELDS if n in usage and not isinstance(usage[n], bool)]
            if tokens and all(isinstance(n, int | float) and n == 0 for n in tokens):
                self._add("aer.sentinel", "AER-V17", index, "/usage", "all_zero_usage", release_only=True)

    def _times(self, index: int, rec: dict[str, Any]) -> None:
        t = rec.get("t")
        if not isinstance(t, dict):
            return
        for lo, hi in (("start", "end"), ("start_naive", "end_naive")):
            a, b = t.get(lo), t.get(hi)
            if (
                isinstance(a, str)
                and isinstance(b, str)
                and _structure._RE["time" if lo == "start" else "time_naive"].fullmatch(a)
                and _structure._RE["time" if lo == "start" else "time_naive"].fullmatch(b)
                and _time_key(a) > _time_key(b)
            ):
                self._add("aer.order.time", "AER-V19", index, f"/t/{lo}", "start_after_end")
        ms, me = t.get("mono_start_ns"), t.get("mono_end_ns")
        if isinstance(ms, int | float) and isinstance(me, int | float) and ms > me:
            self._add("aer.order.time", "AER-V19", index, "/t/mono_start_ns", "start_after_end")
        if self._header is not None and self._header.get("mode") == "import":
            for name in ("mono_start_ns", "mono_end_ns"):
                if name in t:
                    self._add("aer.schema.additional", "AER-V19", index, f"/t/{name}", "mono_only_live")

    # -------------------------------------------------------------------------------------- references
    def _ref_specs(self, rec: Mapping[str, Any]) -> Iterator[RefSpec]:
        kind: str = rec["k"]
        k = _kinds
        actor, scope = k("actor"), k("scope")
        if kind == "actor":
            yield "/on_behalf_of", rec.get("on_behalf_of"), actor, None
        elif kind == "scope":
            yield "/parent", rec.get("parent"), scope, None
            yield "/actor", rec.get("actor"), actor, None
            yield "/spawned_by", rec.get("spawned_by"), k("tool_execution", "model_call"), None
        elif kind == "message":
            yield "/scope", rec.get("scope"), scope, None
            yield "/actor", rec.get("actor"), actor, None
            yield "/generated_by", rec.get("generated_by"), k("model_call", "tool_execution", "decision"), None
            for i, part in enumerate(_as_list(rec.get("parts"))):
                if isinstance(part, dict) and part.get("t") == "tool_result":
                    yield f"/parts/{i}/responds_to", part.get("responds_to"), k(_PART_CALL), None
        elif kind == "model_call":
            yield "/actor", rec.get("actor"), actor, None
            yield "/scope", rec.get("scope"), scope, None
            for i, item in enumerate(_as_list(rec.get("input"))):
                if isinstance(item, str):
                    yield f"/input/{i}", item, k("message"), None
                elif isinstance(item, dict):
                    yield f"/input/{i}/id", item.get("id"), k("message"), None
            yield "/tools", rec.get("tools"), k("fixture"), lambda info: info.sub == "tool_definitions"
            yield "/retry_of", rec.get("retry_of"), k("model_call"), None
        elif kind == "tool_execution":
            yield "/actor", rec.get("actor"), actor, None
            yield "/scope", rec.get("scope"), scope, None
            yield "/call", rec.get("call"), k(_PART_CALL), None
            yield "/requested_by", rec.get("requested_by"), actor, None
            yield "/authorised_by", rec.get("authorised_by"), k("decision"), lambda info: info.sub in ("allow", "modify")
        elif kind == "decision":
            yield "/actor", rec.get("actor"), actor, None
            yield "/scope", rec.get("scope"), scope, None
            yield "/subject", rec.get("subject"), k(_PART_CALL, "tool_execution", "message", "model_call"), None
            if isinstance(rec.get("original"), str):
                yield "/original", rec["original"], k(_PART_ANY), None
        elif kind == "state_change":
            yield "/scope", rec.get("scope"), scope, None
            yield "/cause", rec.get("cause"), k("tool_execution", "scope", "decision", "model_call"), None
        elif kind == "fixture":
            yield "/actor", rec.get("actor"), actor, None
        elif kind == "judgement":
            yield "/actor", rec.get("actor"), actor, None
            yield "/subject", rec.get("subject"), (_ALL_KINDS - {"seal"}) | k(_PART_ANY), None
            yield "/revises", rec.get("revises"), k("judgement"), None
            yield "/generated_by", rec.get("generated_by"), k("model_call", "scope"), None
            for i, item in enumerate(_as_list(rec.get("inputs"))):
                yield f"/inputs/{i}", item, (_ALL_KINDS - {"execution", "seal"}) | k(_PART_ANY), None
        elif kind == "activity":
            yield "/actor", rec.get("actor"), actor, None
            yield "/scope", rec.get("scope"), scope, None
            for i, item in enumerate(_as_list(rec.get("inputs"))):
                yield f"/inputs/{i}", item, k("message", "fixture", "artefact", "judgement", "state_change", _PART_ANY), None
        elif kind == "artefact":
            yield "/generated_by", rec.get("generated_by"), k("activity", "model_call", "tool_execution"), None
        for i, edge in enumerate(_as_list(rec.get("after"))):
            if isinstance(edge, dict):
                yield f"/after/{i}/id", edge.get("id"), _ALL_KINDS - {"seal"}, None

    def _references(self, index: int, rec: dict[str, Any]) -> None:
        rid = rec["id"]
        for pointer, target, allowed, cond in self._ref_specs(rec):
            if not isinstance(target, str):
                continue
            self._resolve(index, pointer, target, allowed, cond)
        for edge in _as_list(rec.get("after")):
            if isinstance(edge, dict) and isinstance(edge.get("id"), str):
                self._after.setdefault(rid, []).append(edge["id"])
                if edge["id"] == rid:
                    self._add("aer.order.cycle", "AER-V09", index, "/after", "self_edge")
                elif edge["id"] not in self._ids:
                    self._forward_after = True

    def _resolve(self, index: int, pointer: str, target: str, allowed: frozenset[str], cond: Cond | None) -> None:
        invariant = "AER-V09" if pointer.startswith("/after/") else "AER-V08"
        if "#" in target:
            if _structure._RE["part_id"].fullmatch(target):
                try:
                    base, ordinal = split_part_id(target)
                except ValueError:  # a part id whose ordinal is out of any range: dangling below
                    base, ordinal = target.partition("#")[0], -1
            else:
                base, ordinal = target, -1
            info = self._ids.get(base)
            if info is None:
                self._pending.append(_Pending(index, pointer, target, invariant))
                return
            if info.kind != "message" or not 0 <= ordinal < info.n_parts:
                self._add("aer.ref.dangling", "AER-V10", index, pointer, _safe(target))
                return
            part_type = self._parts.get(target)
            if _PART_ANY not in allowed and f"part:{part_type}" not in allowed:
                self._add("aer.ref.kind", invariant, index, pointer, _safe(target))
            return
        info = self._ids.get(target)
        if info is None:
            self._pending.append(_Pending(index, pointer, target, invariant))
        elif info.kind not in allowed or (cond is not None and not cond(info)):
            self._add("aer.ref.kind", invariant, index, pointer, _safe(target))

    # -------------------------------------------------------------------------------------- declarations
    def _declared_in_catalogue(self, namespace: str, name: str, attr: str) -> bool:
        cat = self._catalogues.get(namespace)
        return cat is not None and name in getattr(cat, attr)

    def _declarations(self, index: int, rec: dict[str, Any]) -> None:
        """AER-V30: declared ``subtype`` values and ``activity``/``artefact`` types."""
        values: list[tuple[str, str, str]] = []  # (pointer, value, separator)
        if isinstance(rec.get("subtype"), str):
            values.append(("/subtype", rec["subtype"], "."))
        if rec["k"] in ("activity", "artefact") and isinstance(rec.get("type"), str):
            values.append(("/type", rec["type"], ":"))
        for pointer, value, sep in values:
            namespace = value.partition(sep)[0]
            if namespace in T.RESERVED_PREFIXES or (self._header is not None and namespace not in self._ns):
                self._add("aer.ext.undeclared", "AER-V30", index, pointer, "namespace_not_declared")
                continue
            attr = "subtypes" if sep == "." else "types"
            if not self._declared_in_catalogue(namespace, value, attr):
                self._add("aer.subtype.undeclared", "AER-V30", index, pointer, "not_declared_in_catalogue")
        if rec["k"] == "activity" and isinstance(rec.get("type"), str):
            if rec["type"].partition(":")[2] in T.SPECIALISED_KIND_NAMES:
                self._add("aer.activity.shadows_kind", "AER-V30", index, "/type", "specialised_kind_exists")

    def _kind_rules(self, index: int, rec: dict[str, Any]) -> None:
        if rec["k"] == "artefact" and isinstance(rec.get("content_ref"), dict) and isinstance(rec.get("sha256"), str):
            blob = rec["content_ref"].get("$blob")
            if isinstance(blob, str) and blob[7:] != rec["sha256"]:
                self._add("aer.blob.digest", "AER-V31", index, "/sha256", "sha256_differs_from_content_ref")

    # ------------------------------------------------------------------------------------------ finish
    def finish(self) -> ValidationReport:
        """End-of-stream checks; returns the report. The validator cannot be fed afterwards."""
        if self._finished:
            raise RuntimeError("validator already finished")
        self._finished = True
        n = self._n
        digest = status = None
        if n < 2:
            self._add("aer.order.envelope", "AER-V03", None, "", "fewer_than_two_lines")
        elif self._seal is None:
            self._add("aer.order.envelope", "AER-V03", n - 1, "", "last_not_seal")
        if n and self._header is None and not any(f.code == "aer.order.envelope" for f in self._findings):
            self._add("aer.order.envelope", "AER-V03", 0, "", "first_not_execution")
        if self._run_scopes != 1 and self._header is not None:
            self._add("aer.schema.oneof", "AER-V07", None, "", "exactly_one_run_scope")
        if self._header is not None and self._task_not_captured() and (n != 3 or self._run_scopes != 1):
            # D-219: only a degenerate AER (header, its run scope, seal) may leave its task unnamed
            self._add("aer.schema.required", "AER-V07", 0, "/task/task_id", "only_degenerate")
        self._finish_references()
        self._finish_verified()
        if self._seal is not None:
            digest, status = self._finish_seal(self._seal, self._seal_line)
        return ValidationReport(
            findings=tuple(self._findings),
            skipped=tuple(sorted(self._skipped)),
            deferred=(
                "AER-V27: execution.related targets (corpus tier)",
                "AER-V28: re-mapping reproduces the file (corpus tier)",
                "AER-V29: byte-exact view gate for ext.lex (corpus tier)",
            ),
            n_records=n,
            execution_digest=digest,
            accounting_status=status,
            mode=self._mode,
            truncated=self._truncated,
            ex=self._ex,
            dropped_errors=self._dropped_errors,
        )

    def _finish_references(self) -> None:
        for pending in self._pending:
            base = pending.target.partition("#")[0]
            if base in self._ids:
                self._add("aer.ref.forward", pending.invariant, pending.line, pending.pointer, _safe(pending.target))
            else:
                self._add("aer.ref.dangling", pending.invariant, pending.line, pending.pointer, _safe(pending.target))
        if self._forward_after and self._has_cycle():
            self._add("aer.order.cycle", "AER-V09", None, "", "after_cycle")

    def _has_cycle(self) -> bool:
        state: dict[str, int] = {}
        for root in self._after:
            if state.get(root):
                continue
            stack = [(root, iter(self._after.get(root, [])))]
            state[root] = 1
            while stack:
                node, children = stack[-1]
                advanced = False
                for child in children:
                    mark = state.get(child, 0)
                    if mark == 1:
                        return True
                    if mark == 0:
                        state[child] = 1
                        stack.append((child, iter(self._after.get(child, []))))
                        advanced = True
                        break
                if not advanced:
                    state[node] = 2
                    stack.pop()
        return False

    # -------------------------------------------------------------------------------------- seal
    def _finish_seal(self, seal: dict[str, Any], line: int) -> tuple[str | None, str | None]:
        for code, pointer, key in _structure.check_record(seal):
            self._add(code, _INVARIANT.get(code, "AER-V05"), line, pointer, key)
        execution_digest = self._hasher.hexdigest()
        if isinstance(seal.get("n_records"), int) and seal["n_records"] != self._n:
            self._add("aer.seal.count", "AER-V24", line, "/n_records", "line_count")
        if isinstance(seal.get("records_sha256"), str) and seal["records_sha256"] != execution_digest:
            self._add("aer.seal.digest", "AER-V24", line, "/records_sha256", "execution_digest")
        issues = _list(seal.get("issues"))
        accounting = _dict(seal.get("accounting"))
        checks = _list(accounting.get("checks"))
        self._seal_references(line, issues, checks)
        self._seal_blobs(line, seal)
        recomputed = self._tally.finish(
            [i for i in issues if isinstance(i, dict)],
        )
        core_seal = [c for c in checks if isinstance(c, dict) and c.get("id") in CORE_CHECK_IDS]
        want = [dict(c) for c in recomputed.checks]
        if _canon(core_seal) != _canon(want):
            self._add("aer.seal.accounting", "AER-V25", line, "/accounting/checks", "core_checks_differ")
        verdicts = [str(c.get("verdict")) for c in checks if isinstance(c, dict)]
        if all(v in T.ACCOUNTING_VERDICTS for v in verdicts) and accounting.get("status") != fold_status(verdicts):
            self._add("aer.seal.accounting", "AER-V25", line, "/accounting/status", "status_not_the_fold")
        mirrored = {
            (i.get("code"), i.get("rule"), tuple(i["ids"]))
            for i in issues
            if isinstance(i, dict) and isinstance(i.get("ids"), list) and _hashable(i.get("code"), i.get("rule"), *i["ids"])
        }
        for c in checks:
            if isinstance(c, dict) and c.get("verdict") in ("inconsistent", "unverifiable"):
                mirror = (f"accounting_{c['verdict']}", c.get("id"), (c.get("scope"),))
                if not _hashable(c.get("id"), c.get("scope")) or mirror not in mirrored:
                    self._add("aer.seal.accounting", "AER-V25", line, "/issues", "verdict_not_mirrored")
        # pre-round review #27: the converse; an accounting_<verdict> issue mirrors a check of that id, scope and verdict
        # (C.12.3), and only inconsistent and unverifiable verdicts have mirrors
        produced = {(f"accounting_{c['verdict']}", c.get("id"), (c.get("scope"),)) for c in checks
                    if isinstance(c, dict) and c.get("verdict") in ("inconsistent", "unverifiable")
                    and _hashable(c.get("id"), c.get("scope"))}
        for n, i in enumerate(issues):
            if isinstance(i, dict) and isinstance(i.get("code"), str) and i["code"].startswith("accounting_"):
                mirror_key = (i.get("code"), i.get("rule"), tuple(i["ids"])) if isinstance(i.get("ids"), list) \
                    and _hashable(i.get("code"), i.get("rule"), *i["ids"]) else None
                if mirror_key not in produced:
                    self._add("aer.seal.accounting", "AER-V25", line, f"/issues/{n}", "mirror_without_check")
        return execution_digest, accounting.get("status") if isinstance(accounting.get("status"), str) else None

    def _seal_references(self, line: int, issues: list[Any], checks: list[Any]) -> None:
        for i, issue in enumerate(issues):
            if not isinstance(issue, dict):
                continue
            for j, target in enumerate(_as_list(issue.get("ids"))):
                if isinstance(target, str) and target not in self._ids and target not in self._parts:
                    self._add("aer.ref.dangling", "AER-V08", line, f"/issues/{i}/ids/{j}", _safe(target))
            rule = issue.get("rule")
            if isinstance(rule, str):
                self._seal_rule(line, f"/issues/{i}/rule", rule_id_of(rule))
            code = issue.get("code")
            if isinstance(code, str) and "." in code and code not in T.CORE_ISSUE_CODES:
                namespace, _, tail = code.partition(".")
                cat = self._catalogues.get(namespace)
                if cat is None or tail not in cat.issue_codes:
                    self._add("aer.subtype.undeclared", "AER-V25", line, f"/issues/{i}/code", "issue_code_not_declared")
        for i, check in enumerate(checks):
            if not isinstance(check, dict):
                continue
            scope = check.get("scope")
            if isinstance(scope, str) and scope not in self._ids:
                self._add("aer.ref.dangling", "AER-V08", line, f"/accounting/checks/{i}/scope", _safe(scope))
            if isinstance(check.get("id"), str):
                self._seal_rule(line, f"/accounting/checks/{i}/id", check["id"])

    def _seal_rule(self, line: int, pointer: str, rule_id: str) -> None:
        if self._rule_entry(rule_id) is None and not self._known_missing(rule_id):
            self._add("aer.rule.missing", "AER-V15", line, pointer, _safe(rule_id))

    def _seal_blobs(self, line: int, seal: dict[str, Any]) -> None:
        listed = seal.get("blobs")
        if listed is None:
            if self._blobs:
                self._add("aer.blob.ref", "AER-V21", line, "/blobs", "blobs_required")
            return
        if not isinstance(listed, list) or not all(isinstance(b, str) for b in listed):
            return
        if listed != sorted(set(listed)) or set(listed) != self._blobs:
            self._add("aer.blob.ref", "AER-V21", line, "/blobs", "blobs_differ_from_references")


def _canon(value: object) -> bytes:
    try:
        return jcs_bytes(value)
    except ValueError:
        return b"\xff"


# ---------------------------------------------------------------------------------------------- entry points
def _long_strings(value: object, at: str) -> Iterator[str]:
    """The pointers of every string value (member names included) whose UTF-8 encoding exceeds
    :data:`MAX_INLINE_STRING_BYTES` (C.2.1(6); D-216)."""
    if isinstance(value, str):
        # a str of n code points has between n and 4n UTF-8 bytes: encode only when it can be over the limit
        if len(value) * 4 > MAX_INLINE_STRING_BYTES and len(value.encode("utf-8", "surrogatepass")) > MAX_INLINE_STRING_BYTES:
            yield at
    elif isinstance(value, dict):
        for key, element in value.items():
            token = pointer_escape(str(key))
            if len(str(key)) * 4 > MAX_INLINE_STRING_BYTES and len(str(key).encode("utf-8", "surrogatepass")) > MAX_INLINE_STRING_BYTES:
                yield f"{at}/{token}"
            yield from _long_strings(element, f"{at}/{token}")
    elif isinstance(value, list):
        for i, element in enumerate(value):
            yield from _long_strings(element, f"{at}/{i}")


def iter_lines(stream: IO[bytes]) -> Iterator[tuple[bytes, bool]]:
    """LF-delimited lines of a binary stream (never ``splitlines``); lines above the cap are flagged, not held."""
    while True:
        chunk = stream.readline(MAX_LINE_BYTES + 2)
        if not chunk:
            return
        if len(chunk) > MAX_LINE_BYTES and not chunk.endswith(b"\n"):
            head = chunk[:1024]
            while True:  # drain the rest of the oversize line in bounded reads
                rest = stream.readline(1 << 20)
                if not rest or rest.endswith(b"\n"):
                    break
            yield head, True
            continue
        yield chunk, False


def validate_file(
    path: Path | str,
    *,
    store: RawStore | None,
    catalogues: RuleRegistry,
    mode: Mode = "release",
    profile_digests: Mapping[tuple[str, int], str] | None = None,
) -> ValidationReport:
    """Validate one ``.aer.jsonl`` file (binary mode: no newline translation, no locale encoding)."""
    validator = AerValidator(store=store, catalogues=catalogues, mode=mode, profile_digests=profile_digests)
    with open(path, "rb") as stream:
        for line, oversize in iter_lines(stream):
            validator.feed(line, oversize=oversize)
    return validator.finish()


def validate_records(
    records: Iterable[Mapping[str, object]],
    *,
    store: RawStore | None,
    catalogues: RuleRegistry,
    mode: Mode = "release",
    profile_digests: Mapping[tuple[str, int], str] | None = None,
) -> ValidationReport:
    """Validate in-memory records by serialising each as its canonical line (test and writer-gate helper)."""
    validator = AerValidator(store=store, catalogues=catalogues, mode=mode, profile_digests=profile_digests)
    for record in records:
        validator.feed(dumps_line(record))
    return validator.finish()
