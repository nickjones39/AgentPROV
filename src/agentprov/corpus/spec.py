"""The corpus spec ``corpora/<corpus_id>/corpus-spec.toml``: the data-free build input of a corpus (HL H.1.6).

A corpus spec is version-controlled in the AgentPROV repository next to ``CARD.md`` (the datasheet prose, H.9) and
``CHANGES.toml`` (the changelog entries, L.1.3). Sealing copies all three, byte for byte, into the corpus ``rules/``
directory (H.1.2) and takes the corpus identity from the spec, never from the working manifest: the June-2024 and head
working trees both say ``agentdojo-upstream`` and become the two corpora ``agentdojo-upstream-2024-06`` and
``agentdojo-upstream-head`` (D-35).

:func:`load_spec` parses a spec strictly: TOML through :mod:`tomllib`, every table **closed** (an unknown key is an
error, so a typo cannot silently drop a setting), every value type-checked. Keys (H.1.6; the as-built additions are
marked):

=====================================  ===========================================================================
``corpus_id``                          ``^[a-z0-9]+(-[a-z0-9]+)*$``, at most 64 characters (H.1.1(3))
``corpus_version``                     SemVer 2.0.0 (L.1.3)
``title``                              at most 200 characters
``mode``                               ``import`` | ``live``
``[[sources]]``                        exactly one (H.1.1(1)): ``source_id`` (registry id), ``profile``
                                       (``"<profile id>@<int>"``), ``parts`` (registry part ids, at least one)
``[[sources.snapshots]]``              ``snapshot_id``; ``origin`` (a pinned origin, H.2.3; ``local`` and mutable refs
                                       refused); optional ``alt_origins``; optional ``include`` / ``exclude``
                                       (default: the source profile's ``[import]`` selection); ``raw_policy``
``[derive]``                           ``sem_profiles``, ``prov_specs``, ``views`` (⊆ ``transcript-v1``), ``options``
                                       (``context_encoding = "members"``, the only v0.1 value)
``[licence]``                          ``derived`` (SPDX id or ``"inherit"``); as built: ``decided_by`` (who decided
                                       the derived licence) and ``files`` (the names of the verbatim upstream licence
                                       files written to ``LICENSES/<source_id>/``; H.4.4; distinct, and distinct from
                                       ``NOTICE.md``, under the G.3.6 collision key)
``[layout]``                           ``shard_depth`` 1 | 2
``[live]``                             ``campaign``, ``run_plan`` (live corpora only)
``[scan]``                             as built (D-810): ``personas``, the persona files the release scan reads
``[withhold]``                         as built (D-964): ``decided_by``; ``objects`` (``"sha256:<hex>"`` of stored raw
                                       objects, each withheld alone) and/or ``executions`` (execution ids, each
                                       withheld with its primary object), reason ``secret``: the release-scan findings a
                                       review decided to withhold that no profile rule describes
=====================================  ===========================================================================

The spec holds no data and no number taken from data: counts are computed at sealing (H.2.1(3)).
"""

from __future__ import annotations

import os
import re
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from agentprov.errors import AgentProvError
from agentprov.ingest.names import collision_key

__all__ = [
    "CORPUS_ID_RE",
    "RAW_POLICIES",
    "SEMVER_RE",
    "CorpusSpec",
    "CorpusSpecError",
    "SnapshotSpec",
    "SourceSpec",
    "check_origin",
    "load_spec",
    "parse_spec",
    "selection_of",
]

CORPUS_ID_RE: Final = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
#: SemVer 2.0.0 (semver.org's recommended pattern, anchored by ``fullmatch``).
SEMVER_RE: Final = re.compile(
    r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?"
)
RAW_POLICIES: Final = ("include", "reference", "withhold")
MODES: Final = ("import", "live")
_REGISTRY_ID_RE: Final = re.compile(r"[a-z0-9][a-z0-9_.-]*")
_PROFILE_REF_RE: Final = re.compile(r"(?P<id>[a-z][a-z0-9_.-]*)@(?P<version>[1-9][0-9]*)")
_SEM_REF_RE: Final = re.compile(r"[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*@[1-9][0-9]*")
_SPDX_RE: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9.+-]*")
_LICENCE_FILE_RE: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")
_HEX40: Final = re.compile(r"[0-9a-f]{40}")
_SUBTREE_RE: Final = re.compile(r"(?:[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*)?")
_SELECT_CODE_RE: Final = re.compile(r"select\.[a-z_]+")
_PROV_SPECS: Final = ("agentprov-prov/0.1", "adprov-v2.3-compat")
_VIEWS: Final = ("transcript-v1",)
_MAX_TITLE: Final = 200

#: Origin kinds and their members (H.2.3, snapshot level). ``member`` is object-level only and ``local`` is refused.
_ORIGIN_KEYS: Final[Mapping[str, tuple[frozenset[str], frozenset[str]]]] = {
    # kind: (required, optional)
    "git": (frozenset({"repo", "commit"}), frozenset({"subtree", "subtrees", "subtree_sha1"})),
    "zenodo": (frozenset({"doi", "file"}), frozenset({"md5", "member_prefix", "parts"})),
    "hf": (frozenset({"dataset", "revision", "gated"}), frozenset({"path", "parts"})),
    "url": (frozenset({"url", "retrieved_at"}), frozenset()),
    "corpus": (frozenset({"corpus", "version", "producer_commit"}), frozenset()),
    "capture": (frozenset({"session_ids"}), frozenset()),
}


class CorpusSpecError(AgentProvError):
    """A corpus spec is malformed or names something it may not (``corpus.spec.invalid``, exit 2: a usage error)."""

    code = "corpus.spec.invalid"
    exit_code = 2


@dataclass(frozen=True, slots=True)
class SnapshotSpec:
    snapshot_id: str
    origin: Mapping[str, Any]
    raw_policy: str
    alt_origins: tuple[Mapping[str, Any], ...] = ()
    include: tuple[str, ...] | None = None  # None: the source profile's [import] include
    exclude: tuple[Mapping[str, Any], ...] | None = None  # None: the source profile's [import] exclude


@dataclass(frozen=True, slots=True)
class SourceSpec:
    source_id: str
    profile_id: str
    profile_version: int
    parts: tuple[str, ...]
    snapshots: tuple[SnapshotSpec, ...]

    @property
    def profile(self) -> str:
        return f"{self.profile_id}@{self.profile_version}"


@dataclass(frozen=True, slots=True)
class CorpusSpec:
    """A parsed ``corpus-spec.toml`` (H.1.6)."""

    corpus_id: str
    corpus_version: str
    title: str
    mode: str
    source: SourceSpec
    sem_profiles: tuple[str, ...]
    prov_specs: tuple[str, ...]
    views: tuple[str, ...]
    options: Mapping[str, Any]
    licence_derived: str
    licence_decided_by: str
    licence_files: tuple[str, ...]
    shard_depth: int
    live: Mapping[str, Any] | None = None
    data: Mapping[str, Any] = field(default_factory=dict)  # the parsed document, for the record
    #: D-810: the persona files (digests of the benchmark's fictional e-mail addresses) this corpus clears in its release
    #: scan, as ``(path relative to the spec, "sha256:<hex>")``; empty when the spec has no ``[scan]`` table
    persona_files: tuple[tuple[str, str], ...] = ()
    #: D-964: the stored raw objects (``"sha256:<hex>"``) and the executions (ids) the spec's ``[withhold]`` table lists,
    #: and who decided it; empty and ``None`` when the spec has no ``[withhold]`` table
    withhold_objects: tuple[str, ...] = ()
    withhold_executions: tuple[str, ...] = ()
    withhold_decided_by: str | None = None

    @property
    def sources(self) -> tuple[SourceSpec, ...]:
        return (self.source,)


def _closed(table: Mapping[str, Any], where: str, required: set[str], optional: set[str] = frozenset()) -> None:  # type: ignore[assignment]
    keys = set(table)
    missing = required - keys
    unknown = keys - required - set(optional)
    if missing:
        raise CorpusSpecError(f"{where}: missing {', '.join(sorted(missing))}")
    if unknown:
        raise CorpusSpecError(f"{where}: unknown key(s) {', '.join(sorted(unknown))} (the spec is closed, H.1.6)")


def _string(value: object, where: str, pattern: re.Pattern[str] | None = None, max_len: int | None = None) -> str:
    if not isinstance(value, str) or not value or (max_len is not None and len(value) > max_len):
        raise CorpusSpecError(f"{where}: a non-empty string" + (f" of at most {max_len} characters" if max_len else ""))
    if pattern is not None and pattern.fullmatch(value) is None:
        raise CorpusSpecError(f"{where}: malformed value")
    return value


def _strings(value: object, where: str, pattern: re.Pattern[str] | None = None, *, allow_empty: bool = True) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value) or (not allow_empty and not value):
        raise CorpusSpecError(f"{where}: an array of strings" + ("" if allow_empty else " (at least one)"))
    if pattern is not None and not all(pattern.fullmatch(v) for v in value):
        raise CorpusSpecError(f"{where}: malformed value")
    if len(set(value)) != len(value):
        raise CorpusSpecError(f"{where}: duplicate value")
    return tuple(value)


def check_origin(origin: object, where: str = "origin") -> dict[str, Any]:
    """A pinned snapshot-level origin (H.2.3), checked and copied. ``local`` (development only), ``member`` (object level)
    and any mutable reference are refused (H.1.6: "Mutable refs MUST be rejected")."""
    if not isinstance(origin, Mapping) or not isinstance(origin.get("kind"), str):
        raise CorpusSpecError(f"{where}: a table with a kind")
    kind = origin["kind"]
    if kind == "local":
        raise CorpusSpecError(f"{where}: a local origin is development only; a corpus spec names a pinned origin")
    if kind not in _ORIGIN_KEYS:
        raise CorpusSpecError(f"{where}: unknown or object-level origin kind")
    required, optional = _ORIGIN_KEYS[kind]
    _closed(origin, where, set(required) | {"kind"}, set(optional))
    out = dict(origin)
    if kind == "git":
        _string(out["repo"], f"{where}.repo", re.compile(r"https://[A-Za-z0-9.-]+/[A-Za-z0-9_.~/-]+"))
        _string(out["commit"], f"{where}.commit (a full 40-hex commit; mutable refs are refused)", _HEX40)
        if ("subtree" in out) == ("subtrees" in out):
            raise CorpusSpecError(f"{where}: exactly one of subtree (a string) and subtrees (an array) (D-33)")
        if "subtree" in out:
            if not isinstance(out["subtree"], str) or _SUBTREE_RE.fullmatch(out["subtree"]) is None:
                raise CorpusSpecError(f"{where}.subtree: a relative path without a trailing '/', or '' for the commit root")
        else:
            subtrees = _strings(out["subtrees"], f"{where}.subtrees", allow_empty=False)
            if len(subtrees) < 2 or list(subtrees) != sorted(subtrees) or not all(s and _SUBTREE_RE.fullmatch(s) for s in subtrees):
                raise CorpusSpecError(f"{where}.subtrees: two or more sorted non-empty relative paths (one tree is subtree)")
            if "subtree_sha1" in out:
                raise CorpusSpecError(f"{where}: subtree_sha1 names one tree; it goes with subtree")
        if "subtree_sha1" in out:
            _string(out["subtree_sha1"], f"{where}.subtree_sha1", _HEX40)
    elif kind == "hf":
        _string(out["revision"], f"{where}.revision (40 hex)", _HEX40)
        if not isinstance(out["gated"], bool):
            raise CorpusSpecError(f"{where}.gated: a boolean")
    elif kind == "corpus":
        _string(out["producer_commit"], f"{where}.producer_commit", _HEX40)
        _string(out["corpus"], f"{where}.corpus")
        _string(out["version"], f"{where}.version")
    elif kind == "zenodo":
        _string(out["doi"], f"{where}.doi", re.compile(r"10\.[0-9]{4,9}/[A-Za-z0-9._;()/:-]+"))
        _string(out["file"], f"{where}.file")
    if kind in ("zenodo", "hf") and "parts" in out:
        out["parts"] = _origin_parts(out["parts"], f"{where}.parts")
    if kind == "capture":
        _strings(out["session_ids"], f"{where}.session_ids", allow_empty=False)
    return out


def _origin_parts(value: object, where: str) -> list[dict[str, Any]]:
    """The byte parts of an archive stored as parts (``agentprov-corpus/0.2``; D-217, D-249): two or more
    ``{file, bytes, sha256, md5?}`` tables in the pin's order."""
    if not isinstance(value, list) or len(value) < 2:
        raise CorpusSpecError(f"{where}: an array of two or more {{file, bytes, sha256, md5?}} tables")
    out = []
    for i, part in enumerate(value):
        here = f"{where}[{i}]"
        if not isinstance(part, Mapping):
            raise CorpusSpecError(f"{here}: a table")
        _closed(part, here, {"file", "bytes", "sha256"}, {"md5"})
        _string(part["file"], f"{here}.file")
        if isinstance(part["bytes"], bool) or not isinstance(part["bytes"], int) or part["bytes"] < 0:
            raise CorpusSpecError(f"{here}.bytes: a non-negative integer")
        _string(part["sha256"], f"{here}.sha256", re.compile(r"sha256:[0-9a-f]{64}"))
        if "md5" in part:
            _string(part["md5"], f"{here}.md5", re.compile(r"[0-9a-f]{32}"))
        out.append(dict(part))
    return out


def _exclude(value: object, where: str) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list):
        raise CorpusSpecError(f"{where}: an array of {{glob, code, owner?}} tables")
    out: list[Mapping[str, Any]] = []
    for i, entry in enumerate(value):
        here = f"{where}[{i}]"
        if not isinstance(entry, Mapping):
            raise CorpusSpecError(f"{here}: a table")
        _closed(entry, here, {"glob", "code"}, {"owner", "owner_corpus", "note"})
        _string(entry["glob"], f"{here}.glob")
        _string(entry["code"], f"{here}.code", _SELECT_CODE_RE)
        out.append(dict(entry))
    return tuple(out)


def _snapshot(table: object, where: str) -> SnapshotSpec:
    if not isinstance(table, Mapping):
        raise CorpusSpecError(f"{where}: a table")
    _closed(table, where, {"snapshot_id", "origin", "raw_policy"}, {"alt_origins", "include", "exclude"})
    snapshot_id = _string(table["snapshot_id"], f"{where}.snapshot_id", _REGISTRY_ID_RE)
    raw_policy = table["raw_policy"]
    if raw_policy not in RAW_POLICIES:
        raise CorpusSpecError(f"{where}.raw_policy: one of {', '.join(RAW_POLICIES)} (H.4)")
    alt = table.get("alt_origins", [])
    if not isinstance(alt, list):
        raise CorpusSpecError(f"{where}.alt_origins: an array of origins")
    return SnapshotSpec(
        snapshot_id=snapshot_id,
        origin=check_origin(table["origin"], f"{where}.origin"),
        raw_policy=raw_policy,
        alt_origins=tuple(check_origin(o, f"{where}.alt_origins[{i}]") for i, o in enumerate(alt)),
        include=None if "include" not in table else _strings(table["include"], f"{where}.include", allow_empty=False),
        exclude=None if "exclude" not in table else _exclude(table["exclude"], f"{where}.exclude"),
    )


_PERSONA_PATH_RE: Final = re.compile(r"(?:\.\./)?[a-z0-9][a-z0-9_.-]*(?:/[a-z0-9][a-z0-9_.-]*)*")
_SHA256_RE: Final = re.compile(r"sha256:[0-9a-f]{64}")


def _scan_table(value: Any) -> tuple[tuple[str, str], ...]:
    """The optional ``[scan]`` table (D-810): ``personas = [{path, sha256}, ...]``, each a persona file next to the spec
    (``path`` relative to the spec's directory, at most one leading ``../``, a ``*.personas.toml`` name) with the sha256
    of its bytes. The table is closed; a spec without it is valid and clears no persona."""
    from agentprov.corpus.personas import PERSONA_NAME_RE

    if value is None:
        return ()
    if not isinstance(value, Mapping):
        raise CorpusSpecError("scan: a table")
    _closed(value, "scan", {"personas"})
    entries = value["personas"]
    if not isinstance(entries, list) or not entries:
        raise CorpusSpecError("scan.personas: an array of {path, sha256} (omit [scan] for none)")
    out: list[tuple[str, str]] = []
    for i, entry in enumerate(entries):
        where = f"scan.personas[{i}]"
        if not isinstance(entry, Mapping):
            raise CorpusSpecError(f"{where}: a table")
        _closed(entry, where, {"path", "sha256"})
        path = _string(entry["path"], f"{where}.path", _PERSONA_PATH_RE, 200)
        if PERSONA_NAME_RE.fullmatch(path.rsplit("/", 1)[-1]) is None or ".." in path.replace("../", "", 1).split("/"):
            raise CorpusSpecError(f"{where}.path: a <name>.personas.toml file, at most one leading ../")
        out.append((path, _string(entry["sha256"], f"{where}.sha256", _SHA256_RE)))
    if len({Path(p).name for p, _ in out}) != len(out):
        raise CorpusSpecError("scan.personas: two persona files share a name")
    return tuple(out)


def _withhold_table(value: Any) -> tuple[tuple[str, ...], tuple[str, ...], str | None]:
    """The optional ``[withhold]`` table (D-964): ``decided_by`` and at least one of ``objects`` (stored raw objects as
    ``"sha256:<hex>"``) and ``executions`` (execution ids), each list non-empty and without duplicates. Closed."""
    from agentprov.aer.ids import EXECUTION_ID_RE

    if value is None:
        return (), (), None
    if not isinstance(value, Mapping):
        raise CorpusSpecError("withhold: a table")
    _closed(value, "withhold", {"decided_by"}, {"objects", "executions"})
    decided_by = _string(value["decided_by"], "withhold.decided_by", max_len=300)
    if "objects" not in value and "executions" not in value:
        raise CorpusSpecError("withhold: objects or executions (omit [withhold] for none)")
    objects = _strings(value.get("objects", []), "withhold.objects", _SHA256_RE, allow_empty="objects" not in value)
    executions = _strings(value.get("executions", []), "withhold.executions", EXECUTION_ID_RE,
                          allow_empty="executions" not in value)
    return objects, executions, decided_by


def parse_spec(data: bytes, *, source: str = "corpus-spec.toml") -> CorpusSpec:
    """Parse and check a corpus spec (see the module docstring). :class:`CorpusSpecError` on any violation."""
    try:
        doc = tomllib.loads(data.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError):
        raise CorpusSpecError(f"{source}: not valid UTF-8 TOML") from None
    _closed(doc, source, {"corpus_id", "corpus_version", "title", "mode", "sources", "derive", "licence", "layout"},
            {"live", "scan", "withhold"})
    corpus_id = _string(doc["corpus_id"], "corpus_id", CORPUS_ID_RE, 64)
    version = _string(doc["corpus_version"], "corpus_version (SemVer 2.0.0)", SEMVER_RE)
    title = _string(doc["title"], "title", max_len=_MAX_TITLE)
    mode = doc["mode"]
    if mode not in MODES:
        raise CorpusSpecError("mode: import or live")
    sources = doc["sources"]
    if not isinstance(sources, list) or len(sources) != 1:
        raise CorpusSpecError("sources: exactly one [[sources]] table (a corpus has one source, H.1.1(1))")
    table = sources[0]
    if not isinstance(table, Mapping):
        raise CorpusSpecError("sources[0]: a table")
    _closed(table, "sources[0]", {"source_id", "profile", "parts", "snapshots"})
    match = _PROFILE_REF_RE.fullmatch(str(table["profile"])) if isinstance(table["profile"], str) else None
    if match is None:
        raise CorpusSpecError("sources[0].profile: '<profile id>@<int>' (R-11, AD-18)")
    snapshots_raw = table["snapshots"]
    if not isinstance(snapshots_raw, list) or not snapshots_raw:
        raise CorpusSpecError("sources[0].snapshots: at least one [[sources.snapshots]] table")
    snapshots = tuple(_snapshot(s, f"sources[0].snapshots[{i}]") for i, s in enumerate(snapshots_raw))
    if len({s.snapshot_id for s in snapshots}) != len(snapshots):
        raise CorpusSpecError("sources[0].snapshots: snapshot ids are unique within a corpus")
    source_spec = SourceSpec(
        source_id=_string(table["source_id"], "sources[0].source_id", _REGISTRY_ID_RE),
        profile_id=match["id"],
        profile_version=int(match["version"]),
        parts=_strings(table["parts"], "sources[0].parts", _REGISTRY_ID_RE, allow_empty=False),
        snapshots=snapshots,
    )

    derive = doc["derive"]
    if not isinstance(derive, Mapping):
        raise CorpusSpecError("derive: a table")
    _closed(derive, "derive", {"sem_profiles", "prov_specs", "views", "options"})
    sem_profiles = _strings(derive["sem_profiles"], "derive.sem_profiles", _SEM_REF_RE)
    prov_specs = _strings(derive["prov_specs"], "derive.prov_specs", allow_empty=False)
    if not set(prov_specs) <= set(_PROV_SPECS) or "agentprov-prov/0.1" not in prov_specs:
        raise CorpusSpecError("derive.prov_specs: agentprov-prov/0.1, optionally with adprov-v2.3-compat")
    views = _strings(derive["views"], "derive.views")
    if not set(views) <= set(_VIEWS):
        raise CorpusSpecError("derive.views: a subset of transcript-v1 (H.1.6)")
    options = derive["options"]
    if not isinstance(options, Mapping) or dict(options) != {"context_encoding": "members"}:
        raise CorpusSpecError("derive.options: {context_encoding = \"members\"}, the only v0.1 value (D7)")

    licence = doc["licence"]
    if not isinstance(licence, Mapping):
        raise CorpusSpecError("licence: a table")
    _closed(licence, "licence", {"derived", "decided_by", "files"})
    derived = _string(licence["derived"], "licence.derived")
    if derived != "inherit" and _SPDX_RE.fullmatch(derived) is None:
        raise CorpusSpecError("licence.derived: an SPDX id or \"inherit\"")
    decided_by = _string(licence["decided_by"], "licence.decided_by", max_len=200)
    files = _strings(licence["files"], "licence.files", _LICENCE_FILE_RE)
    # Compared under the G.3.6 collision key: on a case-insensitive volume "license" overwrites "LICENSE" and
    # "notice.md" overwrites the generated NOTICE.md.
    keys = [collision_key(name) for name in files]
    if collision_key("NOTICE.md") in keys:
        raise CorpusSpecError("licence.files: NOTICE.md (in any case) is generated at sealing (H.4.4)")
    if len(set(keys)) != len(keys):
        raise CorpusSpecError("licence.files: two names differ only in case or Unicode normalisation (G.3.6)")

    layout = doc["layout"]
    if not isinstance(layout, Mapping):
        raise CorpusSpecError("layout: a table")
    _closed(layout, "layout", {"shard_depth"})
    depth = layout["shard_depth"]
    if depth not in (1, 2) or isinstance(depth, bool):
        raise CorpusSpecError("layout.shard_depth: 1 or 2 (H.1.3)")

    persona_files = _scan_table(doc.get("scan"))
    withhold_objects, withhold_executions, withhold_decided_by = _withhold_table(doc.get("withhold"))
    live = doc.get("live")
    if (mode == "live") != (live is not None):
        raise CorpusSpecError("[live] is present exactly for a live corpus")
    if live is not None:
        if not isinstance(live, Mapping):
            raise CorpusSpecError("live: a table")
        _closed(live, "live", {"campaign", "run_plan"})
    return CorpusSpec(
        corpus_id=corpus_id,
        corpus_version=version,
        title=title,
        mode=str(mode),
        source=source_spec,
        sem_profiles=sem_profiles,
        prov_specs=prov_specs,
        views=views,
        options=dict(options),
        licence_derived=derived,
        licence_decided_by=decided_by,
        licence_files=files,
        shard_depth=int(depth),
        live=None if live is None else dict(live),
        data=doc,
        persona_files=persona_files,
        withhold_objects=withhold_objects,
        withhold_executions=withhold_executions,
        withhold_decided_by=withhold_decided_by,
    )


def load_spec(path: str | os.PathLike[str]) -> CorpusSpec:
    """Load ``corpora/<corpus_id>/corpus-spec.toml`` (H.1.6). The directory name must equal the spec's ``corpus_id``."""
    file = Path(path)
    try:
        data = file.read_bytes()
    except OSError as exc:
        raise CorpusSpecError(f"the corpus spec cannot be read ({type(exc).__name__})") from None
    spec = parse_spec(data, source=file.name)
    if file.parent.name and file.parent.name != spec.corpus_id and file.parent.parent.name == "corpora":
        raise CorpusSpecError("corpora/<corpus_id>/: the directory name differs from the spec's corpus_id")
    return spec


def selection_of(spec: SnapshotSpec, profile_import: Mapping[str, Any] | None) -> dict[str, Any]:
    """The effective selection of a snapshot (H.2.3 ``selection``): the spec's ``include``/``exclude`` or, when the spec
    omits them, the source profile's ``[import]``. Exclusion entries keep ``glob``, ``code`` and ``owner`` (``null`` when
    absent); notes are dropped (they are prose)."""
    imp = profile_import or {}
    include = list(spec.include) if spec.include is not None else [str(g) for g in imp.get("include", ())]
    raw_exclude: Sequence[Any] = spec.exclude if spec.exclude is not None else imp.get("exclude", ()) or ()
    exclude = [
        {"code": str(e.get("code") or "select.not_execution_artefact"), "glob": str(e["glob"]), "owner": None if e.get("owner") is None else str(e["owner"])}
        for e in raw_exclude
        if isinstance(e, Mapping) and "glob" in e
    ]
    return {"exclude": exclude, "include": include}
