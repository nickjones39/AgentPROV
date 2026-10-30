"""The git history index: for every blob of a pinned tree, the commit that introduced it (docs/architecture D.6.16, C.3.12).

A depth-1 pinned store (``raw.fetch``) holds one commit, so it cannot say *when* a log file entered the repository. The
upstream history can: a log that exists at ``(path, blob)`` in commit ``C`` was written before ``C`` was committed, so the
committer date of the earliest commit holding it is an **upper bound on the run time**. This module holds the pure part:
the log parser, the selection rule and the index file. Running ``git`` is the job of :class:`~agentprov.raw.fetch.Fetcher`
(MN M.5.3: the one home of the git subprocess in the raw layer).

**The rule (``introduced_in_commit``).** For a pinned tree entry ``(path, blob)`` the *introducing commits* are the commits
reachable from the pinned commit whose tree holds ``blob`` at ``path`` and none of whose parents does (a root commit has no
parent). The recorded commit is the introducing commit with the smallest ``(committer date, commit id)``. All parents of a
merge are considered (``git log -m``), so a merge that brings the blob in from neither parent (a conflict resolution) is
an introducing commit, and a merge that merely joins a branch that already held it is not. The walk is over the **full**
history, not the first-parent line: a pull request's own commits are older than its merge commit and give the tighter, still
valid, bound. Renames are not followed (``--no-renames``): a file moved to a new path is introduced at the new path by the
move, which is what holds for that path.

**What it is not.** The date is a claim of the committer's clock (it can be skewed or rewritten by a rebase, which only makes
it later, never earlier than the work), so it is an upper bound and never an event time: no PROV time, no timestamp of any
record. Nothing here is a guess: a blob with no introducing commit in the walked history makes the whole index refused
(:class:`HistoryError`), never a partial one.

**Index file** (``agentprov-history-index/1``, JSON Canonicalization Scheme lines, deterministic): line 1 is the header
(``repo``, ``commit``, ``tree``, ``commits`` = introducing commit -> RFC 3339 UTC date, counts, the digest of the rows);
each further line is ``{"b": blob_sha1, "c": introducing_commit, "p": path}``, sorted by path (UTF-8 bytes). The file holds
no retrieval time; it is keyed by the pinned commit and recomputable from the history store.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Final

from agentprov.errors import AgentProvError
from agentprov.io.canonical import jcs_bytes

__all__ = [
    "FULL_INDEX_FORMAT",
    "INDEX_FORMAT",
    "INDEX_RULE",
    "FullHistoryIndex",
    "HistoryError",
    "HistoryIndex",
    "build_full_index",
    "build_index",
    "introducing_commits",
    "parse_history_log",
    "parse_plain_ls_tree",
    "rfc3339_utc",
]

INDEX_FORMAT: Final = "agentprov-history-index/1"
FULL_INDEX_FORMAT: Final = "agentprov-history-index-full/1"
INDEX_RULE: Final = (
    "earliest (committer date, commit id) among the commits reachable from the pinned commit whose tree holds the blob at "
    "the path and none of whose parents does; full history, all parents, no rename following"
)
_HEX40: Final = re.compile(r"[0-9a-f]{40}")
_DATE: Final = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
_MAX_EPOCH: Final = 253402300800  # 10000-01-01T00:00:00Z, exclusive: datetime cannot render a later year
_ADDED: Final = frozenset({"A", "M", "T"})


class HistoryError(AgentProvError):
    """The history cannot give an introducing commit for every blob, or an index file is malformed or does not match."""

    code = "raw.history.invalid"
    exit_code = 1


def rfc3339_utc(epoch: int) -> str:
    """A git committer timestamp (seconds since the epoch) as ``YYYY-MM-DDTHH:MM:SSZ`` in UTC."""
    if not 0 <= epoch < _MAX_EPOCH:
        raise HistoryError("a commit timestamp is out of range", code="raw.history.date")
    return datetime.fromtimestamp(epoch, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------------------------------------------
# Parsing git output (bytes; untrusted)
# --------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LogCommit:
    """One block of ``git log -m --raw -z``: a commit (or, for a merge, its diff against one parent) and its additions."""

    commit: str
    parents: int
    epoch: int
    added: tuple[tuple[str, str], ...] = field(default_factory=tuple)  # (path, new blob id)


def parse_plain_ls_tree(data: bytes) -> tuple[dict[str, str], int]:
    """``git ls-tree -r -z`` (no ``-l``: the blobs need not be present) as ``{path: blob id}`` of the regular blobs and
    symlinks, and the number of undecodable paths skipped. Gitlinks (mode 160000) are not blobs and are left out."""
    out: dict[str, str] = {}
    skipped = 0
    for record in data.split(b"\0"):
        if not record:
            continue
        head, tab, raw_path = record.partition(b"\t")
        fields = head.split()
        if not tab or len(fields) != 3:
            raise HistoryError("unexpected git ls-tree output", code="raw.history.git")
        mode, kind, oid = (f.decode("ascii", "replace") for f in fields)
        if _HEX40.fullmatch(oid) is None:
            raise HistoryError("unexpected object id in git ls-tree output", code="raw.history.git")
        if kind != "blob" or mode == "160000":
            continue
        try:
            out[raw_path.decode("utf-8")] = oid
        except UnicodeDecodeError:
            skipped += 1
    return out, skipped


def parse_history_log(data: bytes) -> Iterator[LogCommit]:
    """The blocks of ``git log --format=%x01%H %P %ct --raw -z --no-renames --root -m --abbrev=40``.

    The stream is NUL-separated: a header token starts with SOH (``\\x01``) and holds ``<commit> <parents...> <epoch>``;
    a raw token ``:<omode> <nmode> <ooid> <noid> <status>`` (git puts a newline in front of the first one) is followed by
    exactly one path token. The path token is consumed unconditionally, so a path that starts with ``:``, SOH or a newline
    cannot be mistaken for a header. Only additions and
    modifications are kept (status A, M, T: the blob at the path differs from the parent's).
    """
    tokens = data.split(b"\0")
    if tokens and tokens[-1] == b"":
        tokens.pop()
    current: tuple[str, int, int] | None = None
    added: list[tuple[str, str]] = []
    i = 0
    while i < len(tokens):
        token = tokens[i].lstrip(b"\n")  # a newline separates a header from the raw records that follow it
        if token.startswith(b"\x01"):
            if current is not None:
                yield LogCommit(*current, tuple(added))
            fields = token[1:].decode("ascii", "replace").split()
            if len(fields) < 2 or _HEX40.fullmatch(fields[0]) is None or not fields[-1].isdigit():
                raise HistoryError("unexpected git log header", code="raw.history.git")
            parents = fields[1:-1]
            if not all(_HEX40.fullmatch(p) for p in parents):
                raise HistoryError("unexpected parent id in a git log header", code="raw.history.git")
            current = (fields[0], len(parents), int(fields[-1]))
            added = []
            i += 1
        elif token.startswith(b":") and current is not None:
            meta = token[1:].decode("ascii", "replace").split()
            if len(meta) != 5 or i + 1 >= len(tokens):
                raise HistoryError("unexpected git log raw record", code="raw.history.git")
            nmode, noid, status = meta[1], meta[3], meta[4]
            path_token = tokens[i + 1]
            i += 2
            if status[:1] in _ADDED and nmode != "160000" and _HEX40.fullmatch(noid):
                try:
                    added.append((path_token.decode("utf-8"), noid))
                except UnicodeDecodeError:
                    continue
        elif token == b"":
            i += 1
        else:
            raise HistoryError("unexpected token in git log output", code="raw.history.git")
    if current is not None:
        yield LogCommit(*current, tuple(added))


# --------------------------------------------------------------------------------------------------------------
# The selection rule
# --------------------------------------------------------------------------------------------------------------


def introducing_commits(blocks: Iterable[LogCommit], tree: Mapping[str, str] | None,
                        *, prefix: str = "") -> dict[tuple[str, str], tuple[int, str]]:
    """``{(path, blob): (committer epoch, commit)}`` for the pinned ``tree`` (``{path: blob}``): the earliest introducing
    commit (module docstring). Consecutive blocks of one commit are its diffs against each parent; an entry introduces
    the blob only when it appears in the diff against **every** parent (``max(1, parents)`` blocks).

    ``tree=None`` selects **every** ``(path, blob)`` the walked history ever added under ``prefix`` (a full-history index,
    :class:`FullHistoryIndex`; deferrals part B): the same rule, applied to superseded versions too."""
    best: dict[tuple[str, str], tuple[int, str]] = {}
    seen: dict[tuple[str, str], int] = {}
    last: str | None = None
    need = 1
    epoch = 0

    def flush() -> None:
        for key, count in seen.items():
            if count >= need:
                candidate = (epoch, last or "")
                if key not in best or candidate < best[key]:
                    best[key] = candidate
        seen.clear()

    for block in blocks:
        if block.commit != last:
            if last is not None:
                flush()
            last, need, epoch = block.commit, max(1, block.parents), block.epoch
        for path, oid in block.added:
            if (tree.get(path) == oid) if tree is not None else path.startswith(prefix):
                key = (path, oid)
                seen[key] = seen.get(key, 0) + 1
    if last is not None:
        flush()
    return best


# --------------------------------------------------------------------------------------------------------------
# The index
# --------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class HistoryIndex:
    """``(path, blob)`` -> introducing commit, with each commit's committer date, for one pinned commit of one repository."""

    repo: str
    commit: str
    tree: str
    commits: Mapping[str, str]  # introducing commit -> RFC 3339 UTC committer date
    rows: Mapping[tuple[str, str], str]  # (path, blob sha1) -> introducing commit
    history_commits: int | None = None  # commits walked (diagnostic)
    skipped_paths: int = 0

    def lookup(self, path: str, blob_sha1: str) -> str | None:
        """The introducing commit of ``blob_sha1`` at ``path`` of the pinned tree, or ``None`` when the index has no row."""
        return self.rows.get((path, blob_sha1))

    def date_of(self, commit: str) -> str | None:
        return self.commits.get(commit)

    def to_bytes(self) -> bytes:
        ordered = sorted(self.rows, key=lambda k: (k[0].encode("utf-8"), k[1]))
        body = b"".join(jcs_bytes({"b": blob, "c": self.rows[(path, blob)], "p": path}) + b"\n" for path, blob in ordered)
        header = {
            "format": INDEX_FORMAT, "repo": self.repo, "commit": self.commit, "tree": self.tree,
            "rule": INDEX_RULE, "entries": len(ordered), "introducing_commits": len(self.commits),
            "history_commits": self.history_commits, "skipped_paths": self.skipped_paths,
            "commits": {c: self.commits[c] for c in sorted(self.commits)},
            "rows_sha256": hashlib.sha256(body).hexdigest(),
        }  # fmt: skip
        return jcs_bytes(header) + b"\n" + body

    @classmethod
    def from_bytes(cls, data: bytes, *, expect_repo: str | None = None, expect_commit: str | None = None) -> HistoryIndex:
        """Parse and verify an index file (digest of the rows, formats, referential integrity). :class:`HistoryError` otherwise."""
        head_line, newline, body = data.partition(b"\n")
        if not newline:
            raise HistoryError("a history index has a header line and rows")
        try:
            header = json.loads(head_line)
        except ValueError:
            raise HistoryError("the history index header is not JSON") from None
        if not isinstance(header, dict) or header.get("format") != INDEX_FORMAT:
            raise HistoryError("not an agentprov history index of this format")
        if hashlib.sha256(body).hexdigest() != header.get("rows_sha256"):
            raise HistoryError("the history index rows do not match their recorded digest")
        repo, commit, tree, commits = header.get("repo"), header.get("commit"), header.get("tree"), header.get("commits")
        if not (isinstance(repo, str) and isinstance(commit, str) and isinstance(tree, str) and isinstance(commits, dict)):
            raise HistoryError("the history index header is malformed")
        if _HEX40.fullmatch(commit) is None or _HEX40.fullmatch(tree) is None:
            raise HistoryError("the history index names a commit or tree that is not 40-hex")
        if (expect_repo is not None and repo != expect_repo) or (expect_commit is not None and commit != expect_commit):
            raise HistoryError("the history index belongs to another repository or commit")
        for c, d in commits.items():
            if not (isinstance(d, str) and _HEX40.fullmatch(c) and _DATE.fullmatch(d)):
                raise HistoryError("the history index has a malformed commit date")
        rows: dict[tuple[str, str], str] = {}
        for line in body.splitlines():
            row = json.loads(line)
            path, blob, intro = row.get("p"), row.get("b"), row.get("c")
            if not (isinstance(path, str) and isinstance(blob, str) and _HEX40.fullmatch(blob) and intro in commits):
                raise HistoryError("a history index row is malformed or names an unlisted commit")
            rows[(path, blob)] = intro
        if len(rows) != header.get("entries"):
            raise HistoryError("the history index entry count differs from its rows")
        walked, skipped = header.get("history_commits"), header.get("skipped_paths", 0)
        return cls(repo, commit, tree, dict(commits), rows, walked if isinstance(walked, int) else None,
                   skipped if isinstance(skipped, int) else 0)


def build_index(
    repo: str, commit: str, tree_id: str, tree: Mapping[str, str], best: Mapping[tuple[str, str], tuple[int, str]],
    *, history_commits: int | None = None, skipped_paths: int = 0,
) -> HistoryIndex:
    """The index of ``tree`` from the selection ``best``. Every blob must have an introducing commit; otherwise the walked
    history does not reach where the blob was added (a shallow or grafted store) and :class:`HistoryError` is raised."""
    missing = [p for p, oid in tree.items() if (p, oid) not in best]
    if missing:
        raise HistoryError(
            f"{len(missing)} blob(s) of the pinned tree have no introducing commit in the walked history "
            "(is the history store shallow?)",
            code="raw.history.incomplete",
        )
    rows = {(p, oid): best[(p, oid)][1] for p, oid in tree.items()}
    commits = {c: rfc3339_utc(epoch) for (epoch, c) in {best[k] for k in rows}}
    return HistoryIndex(repo, commit, tree_id, commits, rows, history_commits, skipped_paths)


# --------------------------------------------------------------------------------------------------------------
# The full-history index (deferrals part B)
# --------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FullHistoryIndex:
    """Every ``(path, blob)`` the history of ``commit`` ever added under ``prefix``, with its introducing commit (the rule
    of :data:`INDEX_RULE`), and the pins whose tree still holds it (``[]``: a superseded version, the ``history`` part).

    File format ``agentprov-history-index-full/1`` (JCS lines, deterministic, no retrieval time): a header (``repo``,
    ``commit`` = the tip walked, ``prefix``, ``pins`` = role -> commit, ``commits`` = introducing commit -> RFC 3339 UTC
    committer date, counts, ``rows_sha256``), then one row ``{"b", "c", "p", "pins"}`` per version, sorted by path bytes and
    blob id. It is derived data, recomputable from a full-history store; for the pinned trees it agrees row for row with
    each pin's :class:`HistoryIndex`.
    """

    repo: str
    commit: str
    prefix: str
    pins: Mapping[str, str]  # role -> pinned commit
    commits: Mapping[str, str]
    rows: Mapping[tuple[str, str], tuple[str, tuple[str, ...]]]  # (path, blob) -> (introducing commit, pin roles)
    history_commits: int | None = None

    def to_bytes(self) -> bytes:
        ordered = sorted(self.rows, key=lambda k: (k[0].encode("utf-8"), k[1]))
        body = b"".join(
            jcs_bytes({"b": blob, "c": self.rows[(path, blob)][0], "p": path, "pins": list(self.rows[(path, blob)][1])}) + b"\n"
            for path, blob in ordered
        )
        superseded = sum(1 for _c, roles in self.rows.values() if not roles)
        header = {
            "format": FULL_INDEX_FORMAT, "repo": self.repo, "commit": self.commit, "prefix": self.prefix,
            "pins": dict(sorted(self.pins.items())), "rule": INDEX_RULE, "entries": len(ordered), "superseded": superseded,
            "introducing_commits": len(self.commits), "history_commits": self.history_commits,
            "commits": {c: self.commits[c] for c in sorted(self.commits)},
            "rows_sha256": hashlib.sha256(body).hexdigest(),
        }  # fmt: skip
        return jcs_bytes(header) + b"\n" + body

    def pinned_rows(self, role: str) -> dict[tuple[str, str], str]:
        """``(path, blob) -> introducing commit`` of the versions the pin ``role`` holds (to compare with its index)."""
        return {key: intro for key, (intro, roles) in self.rows.items() if role in roles}


def build_full_index(
    repo: str, commit: str, prefix: str, pins: Mapping[str, Mapping[str, str]], pin_commits: Mapping[str, str],
    best: Mapping[tuple[str, str], tuple[int, str]], *, history_commits: int | None = None,
) -> FullHistoryIndex:
    """The full-history index from the selection ``best`` (``introducing_commits(..., None, prefix=prefix)``), the pinned
    trees ``pins`` (role -> ``{path: blob}``) and their commits ``pin_commits`` (role -> commit). A pinned blob under ``prefix`` with no introducing commit means the walked
    history is incomplete: :class:`HistoryError` (``raw.history.incomplete``), never a partial index."""
    for role, tree in pins.items():
        missing = [p for p, oid in tree.items() if p.startswith(prefix) and (p, oid) not in best]
        if missing:
            raise HistoryError(f"{len(missing)} blob(s) of pin {role} have no introducing commit in the walked history",
                               code="raw.history.incomplete")
    rows = {
        key: (intro, tuple(sorted(role for role, tree in pins.items() if tree.get(key[0]) == key[1])))
        for key, (_epoch, intro) in best.items()
    }
    commits = {c: rfc3339_utc(epoch) for (epoch, c) in set(best.values())}
    return FullHistoryIndex(repo, commit, prefix, dict(pin_commits), commits, rows, history_commits)
