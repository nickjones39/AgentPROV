"""Corpus layout: the paths of HL H.1.2, sharding, ``.partial`` trees and the write guards (HL H.1.3, H.1.5; MN M.1.2).

Every path of the H.1.2 tree (working and sealed), the shard of an execution id, the directory-name mapping of version
identifiers, the closed-world file-name grammar (:func:`classify_relpath`) and tree walk (:func:`iter_tree`),
``assert_writable`` and the git work-tree guard.

* No path component comes from source data (H.1.3(1)): execution ids are ``ex_`` plus base32 or a UUIDv7, the shard is a
  hash of the id, and raw objects are addressed by digest. Paths are ASCII, use ``/`` and are at most 200 characters.
* ``assert_writable`` raises :class:`SealedCorpusError` (exit 4) when any ancestor directory holds a ``corpus.json``
  with ``"sealed": true`` (H.1.5(2)). A manifest that cannot be read or parsed is refused too, because "not sealed"
  cannot be established; it fails closed.
* The git guard (H.1.5(5)) is split: :func:`find_git_work_tree` is pure, and :func:`assert_outside_git_work_tree`
  takes the ``git check-ignore`` decision from the caller. This module may not import ``subprocess`` (MN M.5.3); a
  caller that cannot say a path is ignored is refused.
* **Closed world** (H.1.5(4), H.5.3). :func:`classify_relpath` is the H.1.2/H.1.3 grammar: it names the role of a
  corpus-relative path, or returns ``None`` for a path that may not exist in a corpus (a dotfile such as ``.DS_Store``,
  a source-derived name, a wrong shard). :func:`iter_tree` walks a tree without following a link (through
  :func:`agentprov.ingest.paths.discover`) and reports every file that the grammar refuses, every link or special file,
  and every empty directory. Two entries belong to a *working* tree only: ``.agentprov.lock`` and the raw store's
  ``raw/tmp/`` (in-flight writes; an empty ``raw/tmp/`` is left behind by every import). They are reported with their
  own codes, so that sealing (phase 11, U3) can remove an empty ``raw/tmp/`` and refuse anything else.
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final

from agentprov.aer.ids import EXECUTION_ID_RE
from agentprov.errors import AgentProvError, IngestError
from agentprov.ingest.loaders import strict_json_loads
from agentprov.ingest.paths import discover
from agentprov.ingest.quote import escape_untrusted
from agentprov.raw.store import EXTENSIONS
from agentprov.sem.types import sem_profile_dir

__all__ = [
    "CHECKSUMS",
    "MANIFEST",
    "CorpusLayout",
    "GitWorkTreeRefusedError",
    "SealedCorpusError",
    "TreeFinding",
    "TreeScan",
    "assert_outside_git_work_tree",
    "assert_writable",
    "classify_relpath",
    "dirname",
    "find_git_work_tree",
    "iter_tree",
    "partial_dir",
    "shard",
]

MAX_PATH_CHARS: Final = 200
_PROFILE_ID_RE: Final = re.compile(r"[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*")
PARTIAL_SUFFIX: Final = ".partial"

# H.1.2 fixed files, as corpus-relative labels
MANIFEST: Final = "corpus.json"
EXECUTIONS: Final = "executions.jsonl"
REGISTER: Final = "register.jsonl"
DERIVATION: Final = "derivation.json"
CHECKSUMS: Final = "checksums.sha256"
DATASHEET: Final = "DATASHEET.md"
CHANGELOG: Final = "CHANGELOG.md"
WITHHELD: Final = "WITHHELD.json"
LOCK: Final = ".agentprov.lock"  # working trees only
RAW_TMP: Final = "raw/tmp"  # working trees only (in-flight raw writes)
#: The transcript view of the AgentDojo family (H.1.2 ``views/``; the only v0.1 view).
TRANSCRIPT_VIEW: Final = "transcript-v1"
#: The published schemas (AD-10 row 13; the withheld ledger's since D-230, its 0.2 since D-311, its 0.3 since D-454) that
#: ``schemas/`` may hold: the 0.1 files and, since ``aer/0.2`` (D-212), the ``aer-0.2``/``corpus-0.2`` pair a corpus of
#: format ``agentprov-corpus/0.2`` carries.
SCHEMA_FILES: Final = frozenset({"aer-0.1.schema.json", "corpus-0.1.schema.json", "capture-0.1.schema.json",
                                 "withheld-0.1.schema.json", "withheld-0.2.schema.json",
                                 "withheld-0.3.schema.json", "withheld-0.4.schema.json", "withheld-0.5.schema.json",
                                 "aer-0.2.schema.json", "corpus-0.2.schema.json"})


class SealedCorpusError(AgentProvError):
    """A write was aimed into a sealed corpus tree, or its sealed state could not be established (exit 4)."""

    code = "corpus.sealed"
    exit_code = 4


class GitWorkTreeRefusedError(AgentProvError):
    """The output directory is inside a git work tree and is not git-ignored (H.1.5(5); exit 4)."""

    code = "corpus.in_git_work_tree"
    exit_code = 4


def dirname(version_id: str) -> str:
    """``dirname(v) = v.replace("/", "-").replace("@", "-")`` (H.1.3(4)): ``agentprov-prov/0.1`` becomes ``agentprov-prov-0.1``."""
    return version_id.replace("/", "-").replace("@", "-")


def shard(ex: str, depth: int = 1) -> str:
    """The execution shard: ``sha256(ex)[:2]`` (``depth=1``) or ``[:2]/[2:4]`` (``depth=2``) (H.1.3(2)).

    The id is hashed, not used raw, because live ids are time-ordered UUIDv7 and would put a campaign in one directory.
    """
    if EXECUTION_ID_RE.fullmatch(ex) is None:
        raise ValueError("not an execution id")
    if depth not in (1, 2):
        raise ValueError("shard depth is 1 or 2")
    digest = hashlib.sha256(ex.encode("ascii")).hexdigest()
    return digest[:2] if depth == 1 else f"{digest[:2]}/{digest[2:4]}"


def partial_dir(final: str | os.PathLike[str]) -> Path:
    """The working tree ``<DIR>.partial`` beside the final directory ``<DIR>`` (H.1.5(1))."""
    path = Path(final)
    return path.with_name(path.name + PARTIAL_SUFFIX)


class CorpusLayout:
    """The paths of one corpus tree (working or sealed). Nothing here touches the disk."""

    def __init__(self, root: str | os.PathLike[str], *, shard_depth: int = 1) -> None:
        if shard_depth not in (1, 2):
            raise ValueError("shard depth is 1 or 2")
        self.root = Path(root)
        self.shard_depth = shard_depth

    # fixed files
    @property
    def manifest(self) -> Path:
        return self.root / "corpus.json"

    @property
    def executions(self) -> Path:
        return self.root / "executions.jsonl"

    @property
    def register(self) -> Path:
        return self.root / "register.jsonl"

    @property
    def raw(self) -> Path:
        return self.root / "raw"

    @property
    def objects(self) -> Path:
        return self.raw / "objects"

    @property
    def origins(self) -> Path:
        return self.raw / "origins.jsonl"

    @property
    def members(self) -> Path:
        return self.raw / "members.jsonl"

    @property
    def lock(self) -> Path:
        return self.root / ".agentprov.lock"

    @property
    def derivation(self) -> Path:
        return self.root / "derivation.json"

    @property
    def validation_results(self) -> Path:
        return self.root / "validation" / "results.jsonl"

    @property
    def validation_summary(self) -> Path:
        return self.root / "validation" / "summary.json"

    @property
    def checksums(self) -> Path:
        """``checksums.sha256``: every other file of the tree (H.5.3); written last, at sealing."""
        return self.root / CHECKSUMS

    @property
    def datasheet(self) -> Path:
        return self.root / DATASHEET

    @property
    def changelog(self) -> Path:
        return self.root / CHANGELOG

    @property
    def withheld(self) -> Path:
        """``WITHHELD.json``: present iff anything is withheld (A4; G.9.5)."""
        return self.root / WITHHELD

    @property
    def references(self) -> Path:
        """``raw/REFERENCES.json``: referenced (not included) objects; present iff any (H.4.3)."""
        return self.raw / "REFERENCES.json"

    @property
    def tombstones(self) -> Path:
        """``raw/tombstones.jsonl``: purged objects (G.9.6); present iff any."""
        return self.raw / "tombstones.jsonl"

    @property
    def raw_tmp(self) -> Path:
        """``raw/tmp/``: the raw store's in-flight writes. Working trees only; it must be gone when a corpus is sealed."""
        return self.raw / "tmp"

    @property
    def licenses(self) -> Path:
        return self.root / "LICENSES"

    @property
    def licence_derived(self) -> Path:
        """``LICENSES/DERIVED.txt``: the licence text of the AgentPROV-derived artefacts (H.4.4)."""
        return self.licenses / "DERIVED.txt"

    def licence_file(self, source_id: str, name: str = "LICENSE") -> Path:
        """``LICENSES/<source_id>/<name>``: a verbatim upstream licence file, or the generated ``NOTICE.md`` (H.4.4)."""
        relative = f"LICENSES/{source_id}/{name}"
        if classify_relpath(relative) != "licence":
            raise ValueError("not a licence path of the H.1.2 grammar")
        return self.root.joinpath(*PurePosixPath(relative).parts)

    @property
    def schemas(self) -> Path:
        return self.root / "schemas"

    def schema(self, name: str) -> Path:
        """``schemas/<name>``, one of the published schemas (AD-10 row 13)."""
        if name not in SCHEMA_FILES:
            raise ValueError("not a published schema")
        return self.schemas / name

    @property
    def rules(self) -> Path:
        """``rules/``: a record of the profiles and catalogues used, never an authority (AD-14)."""
        return self.root / "rules"

    @property
    def rules_spec(self) -> Path:
        return self.rules / "corpus-spec.toml"

    @property
    def rules_card(self) -> Path:
        return self.rules / "CARD.md"

    @property
    def rules_changes(self) -> Path:
        return self.rules / "CHANGES.toml"

    def rules_profile(self, profile_name: str) -> Path:
        """``rules/<profile_name>.profile.toml`` (a byte copy of a package profile, D4, D6)."""
        return self._rules_file(f"rules/{profile_name}.profile.toml")

    def rules_catalogue(self, namespace: str) -> Path:
        """``rules/<ns>.rules.toml`` (a byte copy of a rule catalogue, R-09)."""
        return self._rules_file(f"rules/{namespace}.rules.toml")

    def rules_prov(self, spec: str) -> Path:
        """``rules/prov/<spec_dir>.toml``: the provenance spec's rule catalogue (D7), e.g. ``agentprov-prov-0.1.toml``."""
        return self._rules_file(f"rules/prov/{dirname(spec)}.toml")

    def _rules_file(self, relative: str) -> Path:
        if classify_relpath(relative) != "rules":
            raise ValueError("not a rules/ path of the H.1.2 grammar")
        return self.root.joinpath(*PurePosixPath(relative).parts)

    @property
    def views(self) -> Path:
        return self.root / "views"

    def view_relpath(self, view: str, ex: str) -> str:
        """``views/<view>/<ss>/<ex>.transcript.json``; ``transcript-v1`` is the only v0.1 view (H.1.2)."""
        if view != TRANSCRIPT_VIEW:
            raise ValueError("transcript-v1 is the only v0.1 view")
        relative = f"views/{view}/{shard(ex, self.shard_depth)}/{ex}.transcript.json"
        _check_relative(relative)
        return relative

    def view_path(self, view: str, ex: str) -> Path:
        return self.root.joinpath(*PurePosixPath(self.view_relpath(view, ex)).parts)

    # per-execution paths
    def aer_relpath(self, ex: str) -> str:
        """``aer/<ss>/<ex>.aer.jsonl``, relative to the corpus root and ``/``-separated (H.1.3, H.3.1 ``paths.aer``)."""
        relative = f"aer/{shard(ex, self.shard_depth)}/{ex}.aer.jsonl"
        _check_relative(relative)
        return relative

    def aer_path(self, ex: str) -> Path:
        return self.root.joinpath(*PurePosixPath(self.aer_relpath(ex)).parts)

    def sem_relpath(self, profile: str, ex: str) -> str:
        """``sem/<sem_profile_dir>/<ss>/<ex>.sem.jsonl`` (C.14.1; HL H.1.2; RESOLUTIONS §3.6), sharded like the AER.

        ``profile`` is the reference ``<profile id>@<version>`` that keys the index (H.3.4); ``<sem_profile_dir>`` is
        ``<profile id>-<version>`` (:func:`agentprov.sem.types.sem_profile_dir`), e.g. ``sem/agentdojo.suites-1/<ss>/<ex>.sem.jsonl``.
        """
        profile_id, _, number = profile.rpartition("@")
        version = int(number) if number.isdigit() and not number.startswith("0") else 0
        if _PROFILE_ID_RE.fullmatch(profile_id) is None or version < 1:
            raise ValueError("not a semantics profile id and version")
        relative = f"sem/{sem_profile_dir(profile_id, version)}/{shard(ex, self.shard_depth)}/{ex}.sem.jsonl"
        _check_relative(relative)
        return relative

    def sem_path(self, profile: str, ex: str) -> Path:
        return self.root.joinpath(*PurePosixPath(self.sem_relpath(profile, ex)).parts)

    def prov_relpath(self, spec: str, ex: str) -> str:
        """``prov/<spec_dir>/<ss>/<ex>.prov.json`` (H.1.2, H.1.3(4)); ``spec`` is a version id such as ``agentprov-prov/0.1``."""
        relative = f"prov/{dirname(spec)}/{shard(ex, self.shard_depth)}/{ex}.prov.json"
        _check_relative(relative)
        return relative

    def prov_path(self, spec: str, ex: str) -> Path:
        return self.root.joinpath(*PurePosixPath(self.prov_relpath(spec, ex)).parts)


def _check_relative(relative: str) -> None:
    if len(relative) > MAX_PATH_CHARS or not relative.isascii() or relative.startswith("/") or "\\" in relative:
        raise ValueError("a corpus path is ASCII, relative, uses '/', and has at most 200 characters")


# ----------------------------------------------------------------------------------------------- closed-world grammar
_FIXED: Final[dict[str, str]] = {
    MANIFEST: "manifest",
    EXECUTIONS: "index",
    REGISTER: "register",
    DERIVATION: "derivation",
    CHECKSUMS: "checksums",
    DATASHEET: "datasheet",
    CHANGELOG: "changelog",
    WITHHELD: "withheld",
    "raw/origins.jsonl": "origins",
    "raw/members.jsonl": "members",
    "raw/tombstones.jsonl": "tombstones",
    "raw/REFERENCES.json": "references",
    "validation/results.jsonl": "validation_results",
    "validation/summary.json": "validation_summary",
    "LICENSES/DERIVED.txt": "licence",
    "rules/corpus-spec.toml": "rules",
    "rules/CARD.md": "rules",
    "rules/CHANGES.toml": "rules",
}
_SS: Final = r"(?P<ss>[0-9a-f]{2}(?:/[0-9a-f]{2})?)"
_EX: Final = r"(?P<ex>ex_[a-z0-9-]{26,36})"
_SPEC_DIR: Final = r"[a-z0-9][a-z0-9.-]*"
_GRAMMAR: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    ("raw_object", re.compile(r"raw/objects/(?P<h>[0-9a-f]{2})/(?P<sha>[0-9a-f]{64})\.(?P<ext>[a-z]+)")),
    ("aer", re.compile(rf"aer/{_SS}/{_EX}\.aer\.jsonl")),
    ("sem", re.compile(rf"sem/[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*-[1-9][0-9]*/{_SS}/{_EX}\.sem\.jsonl")),
    ("prov", re.compile(rf"prov/{_SPEC_DIR}/{_SS}/{_EX}\.prov\.json")),
    ("view", re.compile(rf"views/{TRANSCRIPT_VIEW}/{_SS}/{_EX}\.transcript\.json")),
    ("licence", re.compile(r"LICENSES/[a-z0-9][a-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*")),
    ("schema", re.compile(r"schemas/(?P<schema>[a-z0-9.-]+\.schema\.json)")),
    ("rules", re.compile(r"rules/[a-z0-9][a-z0-9_.-]*\.(?:profile|rules)\.toml")),
    ("rules", re.compile(rf"rules/prov/{_SPEC_DIR}\.toml")),
    ("rules", re.compile(r"rules/personas/[a-z0-9][a-z0-9_.-]*\.personas\.toml")),
)


def classify_relpath(relative: str) -> str | None:
    """The H.1.2 role of a corpus-relative path, or ``None`` when no file of that name may exist in a corpus.

    The grammar is H.1.2 with H.1.3: ASCII, ``/``-separated, at most 200 characters, no component from source data, no
    dotfile; execution files sit in the shard computed from their id (depth 1 or 2); raw objects sit in the shard of their
    digest with an extension of the closed map (:data:`agentprov.raw.store.EXTENSIONS`). Roles: ``manifest``, ``index``,
    ``register``, ``derivation``, ``checksums``, ``datasheet``, ``changelog``, ``withheld``, ``origins``, ``members``,
    ``tombstones``, ``references``, ``validation_results``, ``validation_summary``, ``licence``, ``schema``, ``rules``,
    ``raw_object``, ``aer``, ``sem``, ``prov``, ``view``. The working-tree entries (``.agentprov.lock``, ``raw/tmp/*``)
    are not in the grammar.
    """
    if (
        not isinstance(relative, str)
        or not relative
        or len(relative) > MAX_PATH_CHARS
        or not relative.isascii()
        or relative.startswith("/")
        or "\\" in relative
        or any(part in ("", ".", "..") or part.startswith(".") for part in relative.split("/"))
    ):
        return None
    if relative in _FIXED:
        return _FIXED[relative]
    for role, pattern in _GRAMMAR:
        match = pattern.fullmatch(relative)
        if match is None:
            continue
        groups = match.groupdict()
        if role == "raw_object":
            return role if groups["h"] == groups["sha"][:2] and groups["ext"] in EXTENSIONS else None
        if role == "schema":
            return role if groups["schema"] in SCHEMA_FILES else None
        if "ex" in groups:
            ex, ss = groups["ex"], groups["ss"]
            if EXECUTION_ID_RE.fullmatch(ex) is None or ss not in (shard(ex, 1), shard(ex, 2)):
                return None
        return role
    return None


@dataclass(frozen=True, slots=True)
class TreeFinding:
    """One entry of a corpus tree that the closed world does not admit (H.1.5(4)).

    ``label`` is the corpus-relative path. A label the grammar admits is shown as it is (its characters are a closed ASCII
    set); any other label comes from the file system of a possibly downloaded tree and is untrusted, so it is held
    escaped (:func:`agentprov.ingest.quote.escape_untrusted`, truncated) and is display text only, never a path.

    Codes: ``corpus.tree.stray`` (a file outside the H.1.2 grammar, e.g. ``.DS_Store``), ``corpus.tree.link`` (a
    symbolic link; never followed), ``corpus.tree.special`` (not a regular file), ``corpus.tree.hardlink`` (only when
    hard links are refused), ``corpus.tree.name`` (a name that is not a valid label), ``corpus.tree.empty_dir``,
    ``corpus.tree.raw_tmp`` (``raw/tmp/`` or anything in it) and ``corpus.tree.lock`` (``.agentprov.lock``).
    """

    code: str
    label: str
    detail: str = ""


#: Findings that a *working* tree normally has: the lock of a running writer and the raw store's temporary directory.
WORKING_ONLY_CODES: Final = frozenset({"corpus.tree.raw_tmp", "corpus.tree.lock"})
_INGEST_TO_TREE: Final[dict[str, str]] = {
    "ingest.path.symlink": "corpus.tree.link",
    "ingest.path.special": "corpus.tree.special",
    "ingest.path.hardlink": "corpus.tree.hardlink",
}


@dataclass(frozen=True, slots=True)
class TreeScan:
    """The result of :func:`iter_tree`: the admitted files (label → (role, size)) and the findings, both sorted."""

    root: Path
    files: tuple[tuple[str, str, int], ...]  # (label, role, size), sorted by label bytes
    findings: tuple[TreeFinding, ...]

    @property
    def closed(self) -> bool:
        """True when nothing outside the H.1.2 grammar was found (the state a sealed tree must be in)."""
        return not self.findings

    def blocking(self, *, working: bool) -> tuple[TreeFinding, ...]:
        """The findings that violate the closed world for a tree in this state: a working tree tolerates the
        :data:`WORKING_ONLY_CODES` entries; a sealed tree tolerates nothing."""
        return tuple(f for f in self.findings if not (working and f.code in WORKING_ONLY_CODES))

    def labels(self) -> tuple[str, ...]:
        return tuple(label for label, _, _ in self.files)


def _shown(label: str) -> str:
    return label if classify_relpath(label) is not None else escape_untrusted(label, max_chars=120)


def _empty_dirs(root: str) -> list[str]:
    """Labels of the directories below ``root`` that hold nothing (no link is followed; nothing is opened but listings)."""
    found: list[str] = []
    pending: list[tuple[str, str]] = [(root, "")]
    while pending:
        path, prefix = pending.pop()
        try:
            with os.scandir(path) as it:
                entries = list(it)
        except OSError:
            continue
        if not entries and prefix:
            found.append(prefix.rstrip("/"))
        for entry in entries:
            try:
                is_dir = stat.S_ISDIR(entry.stat(follow_symlinks=False).st_mode)
            except OSError:
                continue
            if is_dir:
                pending.append((entry.path, prefix + entry.name + "/"))
    return found


def iter_tree(root: str | os.PathLike[str], *, allow_hardlinks: bool = True) -> TreeScan:
    """Walk the corpus tree at ``root`` without following links and check it against the closed world (H.1.5(4)).

    The walk is :func:`agentprov.ingest.paths.discover` (``os.scandir`` with ``follow_symlinks=False`` on directory
    descriptors; nothing is opened or read). Hard links are admitted by default: a recomputed corpus may share raw
    objects with its source by hard link (``recompute --link-raw``, D-32), and a hard link changes no byte. Every file
    whose label :func:`classify_relpath` refuses is a ``corpus.tree.stray`` finding; ``.agentprov.lock`` and ``raw/tmp/``
    get their own codes (see :class:`TreeFinding`); an empty directory is ``corpus.tree.empty_dir``, except an empty
    ``raw/tmp/``, which is ``corpus.tree.raw_tmp``. The result is deterministic (sorted by label bytes).
    """
    discovery = discover(root, allow_hardlinks=allow_hardlinks)
    files: list[tuple[str, str, int]] = []
    findings: list[TreeFinding] = []
    for item in discovery.files:
        label = item.label
        if label in (LOCK, LOCK + ".break"):  # the lock, or its break token (io.atomic.LockFile._break)
            findings.append(TreeFinding("corpus.tree.lock", label))
        elif label.startswith(RAW_TMP + "/"):
            findings.append(TreeFinding("corpus.tree.raw_tmp", _shown(label), "an in-flight raw write"))
        else:
            role = classify_relpath(label)
            if role is None:
                findings.append(TreeFinding("corpus.tree.stray", _shown(label), "not a file of the H.1.2 tree"))
            else:
                files.append((label, role, item.size))
    for label in discovery.skipped:  # `.DS_Store` and AppleDouble `._*` files
        findings.append(TreeFinding("corpus.tree.stray", _shown(label), "an operating-system metadata file"))
    for rejection in discovery.rejected:
        code = _INGEST_TO_TREE.get(rejection.code, "corpus.tree.name")
        findings.append(TreeFinding(code, _shown(rejection.label), rejection.code))
    for label in _empty_dirs(discovery.root):
        code = "corpus.tree.raw_tmp" if label == RAW_TMP else "corpus.tree.empty_dir"
        findings.append(TreeFinding(code, _shown(label), "an empty directory"))
    files.sort(key=lambda f: f[0].encode("utf-8"))
    findings.sort(key=lambda f: (f.label.encode("utf-8"), f.code))
    return TreeScan(Path(discovery.root), tuple(files), tuple(findings))


def assert_writable(path: str | os.PathLike[str]) -> None:
    """Refuse to write inside a sealed corpus (H.1.5(2)).

    Raises :class:`SealedCorpusError` if ``path`` or any ancestor holds a ``corpus.json`` with ``"sealed": true``, or one
    that cannot be read and parsed (fail closed). The path need not exist.
    """
    resolved = Path(os.path.realpath(path))
    for directory in (resolved, *resolved.parents):
        manifest = directory / "corpus.json"
        try:
            data = manifest.read_bytes()
        except (FileNotFoundError, NotADirectoryError):
            continue
        except OSError:
            raise SealedCorpusError("a corpus.json above the output path cannot be read", code="corpus.sealed.unverifiable") from None
        try:
            document = strict_json_loads(data)
        except IngestError:
            raise SealedCorpusError("a corpus.json above the output path cannot be parsed", code="corpus.sealed.unverifiable") from None
        if isinstance(document, dict) and document.get("sealed") is True:
            raise SealedCorpusError("refusing to write inside a sealed corpus; a correction is a new corpus version")


def find_git_work_tree(path: str | os.PathLike[str]) -> Path | None:
    """The nearest ancestor of ``path`` (or itself) that has a ``.git`` entry (directory, or file for a linked tree)."""
    resolved = Path(os.path.realpath(path))
    for directory in (resolved, *resolved.parents):
        if os.path.lexists(directory / ".git"):
            return directory
    return None


def assert_outside_git_work_tree(
    path: str | os.PathLike[str], *, is_ignored: Callable[[Path, Path], bool] | None = None
) -> None:
    """Exported corpora never enter git (H.1.5(5), D9): refuse a path inside a work tree unless it is git-ignored.

    ``is_ignored(work_tree, path)`` is the caller's ``git check-ignore`` decision. Without it, a path inside a work tree is
    refused (fail closed).
    """
    tree = find_git_work_tree(path)
    if tree is None:
        return
    resolved = Path(os.path.realpath(path))
    if is_ignored is not None and is_ignored(tree, resolved):
        return
    raise GitWorkTreeRefusedError("the output directory is inside a git work tree and is not git-ignored")
