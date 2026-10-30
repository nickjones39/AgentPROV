"""Provenance of an AutoDojo attack cache (docs/architecture D.11.3 rule 5 "Attack cache" and "Cache provenance (MN-r12)").

A file given as ``--autodojo-cache PATH`` is copied from the fork by the user, so T0 verifies it before anything is
staged or spawned. This module is that verification; it is a library for ``agentprov run`` (the caller wires it in) and
imports nothing from ``agentdojo`` or ``agentprov_backend``.

Public API
----------
:func:`verify_autodojo_cache` ``(path, *, cache_dir, allow_network, fetcher=None, limits=None, repo=AUTODOJO_REPO,
commit=AUTODOJO_COMMIT) -> VerifiedCache``

1. reads ``path`` through :mod:`agentprov.ingest` (a regular file opened without following links, at most
   ``IngestLimits.max_json_bytes``), parses it with the strict JSON loader and checks its shape (below);
2. computes its SHA-256 and its git blob SHA-1 (``"blob <size>\\0" + bytes``);
3. looks the blob id up in the tree of the pinned fork commit (``repo`` at ``commit``, default
   ``https://github.com/xhOwenMa/AutoDojo`` at ``aa458794b7eb7f082e94daeac4c0f55bfc0c90cc``) in the bare fetch cache of
   :mod:`agentprov.raw.fetch` (G.7.5): ``git ls-tree`` and ``git cat-file`` only, no checkout. A commit that is not in
   the cache is fetched only when ``allow_network`` is true;
4. confirms the match by reading the one matching blob (its SHA-1 is recomputed by the fetch layer) and comparing its
   SHA-256 with the file's;
5. returns a :class:`VerifiedCache` with the SHA-256, the size, the blob SHA-1, the matching tree ``path`` (the
   bytewise-smallest when several paths hold the same blob), every matching path, the verified ``bytes`` (so the caller
   stores exactly what was checked) and ``origin = Origin.git(repo, commit, path, blob_sha1)`` (C.3.12).

``commit`` and ``repo`` exist as a test seam (a synthetic local repository); ``agentprov run`` passes neither. A
``fetcher`` is optional: it must have been built for the same ``cache_dir`` and with the same network flag.

Errors (all :class:`~agentprov.errors.AgentProvError`, stable ``code``; the exit code is the N.1.3 one):

========================================  ====  =============================================================================
``cli.usage.autodojo_cache``               2    :class:`AutodojoCacheUsageError`: unreadable, oversized or malformed file,
                                                a shape violation, a bad ``--autodojo-variant`` (nothing is fetched)
``cli.environment.autodojo_cache_commit``  3    :class:`AutodojoCacheNotCachedError`: the pinned commit is not in the bare
                                                cache and ``allow_network`` is false (nothing is read from the network)
``cli.environment.autodojo_cache_blob``    3    :class:`AutodojoCacheUnverifiedError`: no path in the pinned tree holds the
                                                file's blob id (or the matching blob differs in bytes); nothing is run
========================================  ====  =============================================================================

A network or git failure while filling the cache is the fetch layer's own :class:`~agentprov.raw.fetch.FetchError`.

Cache shape (what ``AutoDojoAttack`` reads, ``agentdojo/attacks/autodojo_attack.py`` at the pinned commit): a top-level
object with ``"injection_tasks"``, a non-empty mapping ``task_id -> vector_id -> {"variants": [str, ...],
"original": str (optional)}``. Other keys are tolerated and ignored (the optimiser writes metadata). The attack silently
falls back to the injection task's goal for a vector whose variant list is shorter than the variant index, so
:func:`check_variant` refuses an index that no vector can serve and reports how many vectors would fall back.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from agentprov.cli.common import CliUsageError
from agentprov.errors import AgentProvError, IngestError
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads
from agentprov.ingest.paths import open_evidence, open_root
from agentprov.ingest.quote import escape_untrusted
from agentprov.io.canonical import sha256_hex
from agentprov.raw.fetch import Fetcher, Recipe
from agentprov.raw.origins import Origin

__all__ = [
    "AUTODOJO_COMMIT",
    "AUTODOJO_REPO",
    "AutodojoCacheNotCachedError",
    "AutodojoCacheUnverifiedError",
    "AutodojoCacheUsageError",
    "CacheShape",
    "VerifiedCache",
    "check_variant",
    "git_blob_sha1",
    "parse_variant",
    "validate_cache_shape",
    "verify_autodojo_cache",
]

#: The pinned fork (profile ``autodojo-live``, ``[source.pins]`` and ``[family.agentdojo.live] pins``; D.11.2). A test
#: keeps this equal to the profile.
AUTODOJO_REPO: Final = "https://github.com/xhOwenMa/AutoDojo"
AUTODOJO_COMMIT: Final = "aa458794b7eb7f082e94daeac4c0f55bfc0c90cc"

_DISPLAY: Final = 80
_VARIANT: Final = re.compile(r"[0-9]{1,9}")


class AutodojoCacheUsageError(CliUsageError):
    """The cache file or ``--autodojo-variant`` is unusable (exit 2). The message names the first problem only."""

    code = "cli.usage.autodojo_cache"


class AutodojoCacheNotCachedError(AgentProvError):
    """The pinned fork commit is not in the bare fetch cache and the network is not allowed (exit 3, D.11.3 rule 5)."""

    code = "cli.environment.autodojo_cache_commit"
    exit_code = 3


class AutodojoCacheUnverifiedError(AgentProvError):
    """No path in the pinned fork tree holds the cache file's blob id (exit 3, D.11.3 rule 5); nothing is run."""

    code = "cli.environment.autodojo_cache_blob"
    exit_code = 3


@dataclass(frozen=True, slots=True)
class CacheShape:
    """Counts of a validated cache: injection tasks, (task, vector) cells, variants in all and per-cell bounds."""

    tasks: int
    cells: int
    variants: int
    min_variants: int
    max_variants: int
    #: ``cells_serving[k]`` is the number of cells that have a variant of index ``k`` (the cells that variant ``k`` serves)
    cells_serving: tuple[int, ...] = field(default=(), repr=False)


@dataclass(frozen=True, slots=True)
class VerifiedCache:
    """A cache file verified against the pinned fork tree (D.11.3 rule 5)."""

    sha256: str
    size: int
    blob_sha1: str
    #: the matching tree path (bytewise-smallest of ``matching_paths``)
    path: str
    matching_paths: tuple[str, ...]
    repo: str
    commit: str
    origin: Origin
    shape: CacheShape
    #: the exact bytes that were hashed, parsed and matched against the pinned blob
    data: bytes = field(repr=False)
    #: whether this call had to fetch the commit (network used)
    fetched: bool = False


def git_blob_sha1(data: bytes) -> str:
    """The git object id of ``data`` as a blob (``sha1("blob <size>\\0" + data)``); an identifier, not a security digest."""
    digest = hashlib.sha1(b"blob %d\0" % len(data), usedforsecurity=False)
    digest.update(data)
    return digest.hexdigest()


def _name(value: object) -> str:
    return escape_untrusted(value if isinstance(value, str) else str(value), max_chars=_DISPLAY)


def _usage(message: str) -> AutodojoCacheUsageError:
    return AutodojoCacheUsageError(f"agentprov run: --autodojo-cache: {message}")


def validate_cache_shape(document: object) -> CacheShape:
    """Strict, bounded shape check of a parsed cache (module docstring). :class:`AutodojoCacheUsageError` on a violation."""
    if not isinstance(document, Mapping):
        raise _usage("the top level must be a JSON object")
    tasks = document.get("injection_tasks")
    if not isinstance(tasks, Mapping):
        raise _usage('"injection_tasks" must be an object mapping task ids to vector ids')
    cells = 0
    total = 0
    lengths: list[int] = []
    for task_id, by_vector in tasks.items():
        if not isinstance(task_id, str) or not task_id:
            raise _usage("an injection task id must be a non-empty string")
        if not isinstance(by_vector, Mapping):
            raise _usage(f"injection task {_name(task_id)!r} must map vector ids to entries")
        for vector_id, entry in by_vector.items():
            where = f"{_name(task_id)!r}/{_name(vector_id)!r}"
            if not isinstance(vector_id, str) or not vector_id:
                raise _usage(f"a vector id of injection task {_name(task_id)!r} must be a non-empty string")
            if not isinstance(entry, Mapping):
                raise _usage(f"entry {where} must be an object")
            variants = entry.get("variants")
            if not isinstance(variants, list) or not all(isinstance(v, str) for v in variants):
                raise _usage(f'"variants" of {where} must be an array of strings')
            if "original" in entry and not isinstance(entry["original"], str):  # the attack calls .strip() on it
                raise _usage(f'"original" of {where} must be a string when present')
            cells += 1
            total += len(variants)
            lengths.append(len(variants))
    if cells == 0:
        raise _usage('"injection_tasks" holds no (task, vector) entry')
    longest = max(lengths)
    serving = tuple(sum(1 for n in lengths if n > k) for k in range(longest))
    return CacheShape(
        tasks=len(tasks), cells=cells, variants=total, min_variants=min(lengths), max_variants=longest,
        cells_serving=serving,
    )  # fmt: skip


def parse_variant(text: str) -> int:
    """``--autodojo-variant`` as an integer ``>= 0`` (plain ASCII digits, at most nine). Usage error otherwise."""
    if not isinstance(text, str) or _VARIANT.fullmatch(text) is None:
        raise AutodojoCacheUsageError(
            f"agentprov run: --autodojo-variant must be an integer >= 0 (ASCII digits), got {_name(text)!r}"
        )
    return int(text)


def check_variant(variant: int, shape: CacheShape) -> int:
    """Refuse a variant index that no cell of the cache can serve; return the number of cells that would fall back.

    ``AutoDojoAttack`` replaces a missing variant by the injection task's goal without a message, so an index beyond every
    variant list would turn the whole run into a different attack. A partial fall-back is allowed and returned so the
    caller can record it.
    """
    if isinstance(variant, bool) or not isinstance(variant, int) or variant < 0:
        raise AutodojoCacheUsageError("agentprov run: --autodojo-variant must be an integer >= 0")
    if variant >= shape.max_variants:
        raise AutodojoCacheUsageError(
            f"agentprov run: --autodojo-variant {variant} is beyond every variant list of the cache "
            f"(the longest has {shape.max_variants}); every vector would fall back to the injection task goal"
        )
    return shape.cells - shape.cells_serving[variant]


def _read_bounded(path: str | Path, limits: IngestLimits) -> bytes:
    target = Path(path)
    cap = limits.max_json_bytes
    try:
        with open_root(target.parent) as root, open_evidence(root, target.name, limits, allow_hardlinks=True) as stream:
            data = stream.read(cap + 1)
    except IngestError as exc:
        raise _usage(f"cannot be read safely ({exc.code})") from None
    except OSError as exc:
        raise _usage(f"cannot be read ({type(exc).__name__})") from None
    if len(data) > cap:
        raise _usage(f"is larger than {cap} bytes (ingest.size.file)")
    return data


def verify_autodojo_cache(
    path: str | Path,
    *,
    cache_dir: str | Path,
    allow_network: bool,
    fetcher: Fetcher | None = None,
    limits: IngestLimits | None = None,
    repo: str = AUTODOJO_REPO,
    commit: str = AUTODOJO_COMMIT,
) -> VerifiedCache:
    """Verify ``path`` against the tree of the pinned fork commit (module docstring); see there for the contract."""
    limits = limits or IngestLimits()
    data = _read_bounded(path, limits)
    try:
        document = strict_json_loads(data, limits)
    except IngestError as exc:
        raise _usage(f"is not valid strict JSON ({exc.code})") from None
    shape = validate_cache_shape(document)
    del document
    sha256 = sha256_hex(data)
    blob_sha1 = git_blob_sha1(data)

    recipe = Recipe(kind="git", repo=repo, commit=commit)
    if fetcher is None:
        fetcher = Fetcher(Path(cache_dir), allow_network=allow_network, consent="--allow-network" if allow_network else "")
    elif fetcher.cache_dir != Path(cache_dir):
        raise ValueError("the fetcher was built for another cache directory")
    fetched = False
    if not fetcher.plan(recipe).cached:
        if not allow_network:
            raise AutodojoCacheNotCachedError(
                f"the pinned AutoDojo commit {commit[:12]} is not in the fetch cache and the network is not allowed; "
                "run again with --allow-network to fetch it (D.11.3 rule 5)"
            )
        fetched = fetcher.fetch(recipe).network_used
    entries, _undecodable = fetcher.git_tree(recipe)
    matching = sorted(
        (e for e in entries if e.is_blob and not e.is_symlink and e.oid == blob_sha1 and e.size in (None, len(data))),
        key=lambda e: e.path.encode("utf-8", "surrogateescape"),
    )
    if not matching:
        raise AutodojoCacheUnverifiedError(
            f"no file of the pinned AutoDojo tree ({repo}@{commit[:12]}) has the blob id {blob_sha1}; the cache file is "
            "not an unmodified copy of a file of the fork, so nothing was run (D.11.3 rule 5)"
        )
    chosen = matching[0]
    blob = next(iter(fetcher.iter_git_blobs(recipe, [chosen])))
    if blob.sha256 != sha256:
        raise AutodojoCacheUnverifiedError("the blob of the pinned AutoDojo tree differs from the cache file in bytes")
    return VerifiedCache(
        sha256=sha256,
        size=len(data),
        blob_sha1=blob_sha1,
        path=chosen.path,
        matching_paths=tuple(e.path for e in matching),
        repo=repo,
        commit=commit,
        origin=Origin.git(repo, commit, chosen.path, blob_sha1),
        shape=shape,
        data=data,
        fetched=fetched,
    )

