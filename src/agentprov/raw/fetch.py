"""Pinned, verified, extraction-free acquisition (docs/architecture G.7.5, MN N.1.11 and N.2.2, HL H.2.3 and H.4.3).

Recipes are **data**: a :class:`Recipe` is built from a source profile's ``[[source.pins]]`` row (kind ``git``, ``zenodo``,
``hf`` or ``url``), never from corpus content or the command line. This module is the one home of network access and of
the ``git`` subprocess in the raw layer (MN M.5.3); nothing else in the core opens a socket for acquisition.

**Network only on request.** No function here touches the network unless the :class:`Fetcher` was built with
``allow_network=True`` (the CLI's ``--allow-network``). Without it a request that is not already satisfied by the cache
raises :class:`NetworkRefusedError` (exit 4) before any socket or ``git fetch`` is attempted. A recipe whose files are all
in the cache needs no network. Every network action is logged with its host and purpose, never with a payload.

**git** (extraction-free, G.7.5). The commit must be 40 lower-case hex digits (:class:`~agentprov.raw.origins.OriginUnpinnedError`
otherwise). The cache is a bare repository at ``<cache>/git/<host>/<owner>/<repo>.git`` (a Hugging Face dataset,
``https://huggingface.co/datasets/<owner>/<name>``, at ``<cache>/git/huggingface.co/datasets/<owner>/<name>.git``); ``git fetch --depth 1`` brings in
the one commit with ``transfer.fsckObjects`` on, hooks disabled and the file protocol refused. No working tree is ever
created. Files are read with ``git ls-tree`` and ``git cat-file --batch``; every blob's SHA-1 is recomputed
(``"blob <size>\\0" + bytes``) and compared with its tree entry while it is read, and its SHA-256 is computed on the way into
the raw store. Symlink blobs (mode 120000) are data and never resolved; gitlinks (160000) are listed and not fetched. The
``git`` executable comes from ``shutil.which``; its argv is built only from validated recipe data (a 40-hex commit, an
https URL of a fixed shape, relative path prefixes), never from artefact content, and never with ``shell=True``.

**git history** (D.6.16; opt-in, a second store). The depth-1 store cannot say when a blob entered the repository. On request
(:meth:`Fetcher.fetch_history`, the CLI's ``--history``) the pinned commit is fetched with its **full history and no blobs**
(``--filter=blob:none``: commits and trees only) into a sibling bare store ``<cache>/git-history/<host>/<owner>/<repo>.git``,
hardened as above. It is a separate store so that the promisor configuration a filtered fetch needs never touches the
depth-1 store; every later git command on it runs with ``GIT_NO_LAZY_FETCH=1``, so reading it can never fetch a missing
blob. From it the introducing commit of every blob of the pinned tree is computed (:mod:`agentprov.raw.history`) and cached
as ``<cache>/git-history/<host>/<owner>/<repo>.index/<commit>.jsonl``, keyed by the pinned commit. The index is derived
data: an import that finds it records ``introduced_in_commit`` on the ``git`` origin of each file; one that does not leaves
the field out (no network, no recomputation).

**HTTPS** (Zenodo, Hugging Face, plain URL). ``urllib`` with TLS verification, https only. Redirects go through a handler
that requires https on every hop, follows only hosts on the recipe's allow-list and drops credentials on any host change.
A gated-source token is read from the environment variable the recipe names, attached with ``add_unredirected_header`` and
only for the host the recipe declares, and is never stored or logged. The response is streamed to a temporary file under
the cache, capped at ``max_artefact_bytes``, and published only after its byte count, MD5 (a transport check) and SHA-256
(the pin) match; a mismatch leaves nothing behind. A download of ``LARGE_DOWNLOAD_BYTES`` or more needs the explicit large
download consent (U-07), whether its size is pinned, announced or only counted as it streams.

**Acquisitions log.** Each real retrieval appends one JCS line to ``<cache>/acquisitions.jsonl`` (kind, repo or DOI, commit
or file, digests, sizes, ``retrieved_at``, the consent recorded, ...). The log lives beside the cache, outside every
corpus: immutable origins carry no retrieval times (H.2.3). A download's row is appended before the file is published; a
cached git commit without its row counts as not cached (ultra raw-withhold #7), so no acquisition stays unrecorded.

Tests inject a fake :class:`Transport` and a local bare repository (``remote_urls`` with ``file_protocol=True``); no test
touches the network.
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
import os
import re
import shutil
import ssl
import subprocess
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any, Final, Protocol
from urllib.parse import quote, urlsplit

from agentprov.errors import AgentProvError, IngestError
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import iter_jsonl
from agentprov.ingest.paths import open_evidence
from agentprov.io.atomic import _fsync_dir, atomic_write_bytes
from agentprov.io.canonical import jcs_bytes, sha256_hex
from agentprov.raw.history import (
    HistoryIndex,
    build_index,
    introducing_commits,
    parse_history_log,
    parse_plain_ls_tree,
)
from agentprov.raw.origins import Origin, OriginLog, OriginUnpinnedError
from agentprov.raw.store import read_tombstones

__all__ = [
    "ACQUISITIONS_NAME",
    "GIT_MIN_VERSION",
    "LARGE_DOWNLOAD_BYTES",
    "AcquisitionLog",
    "AbsentBlobError",
    "BlobMismatchError",
    "DigestMismatchError",
    "FetchEnvironmentError",
    "FetchError",
    "FetchPlan",
    "FetchResult",
    "FetchedBlob",
    "Fetcher",
    "HistoryResult",
    "HttpResponse",
    "LargeDownloadRefusedError",
    "NetworkRefusedError",
    "NotCachedError",
    "Recipe",
    "RedirectRefusedError",
    "SafeRedirectHandler",
    "StoredBlob",
    "Transport",
    "TombstonedDownloadError",
    "TreeEntry",
    "UrllibTransport",
    "check_git_version",
    "is_split_pin",
    "parse_ls_tree",
    "part_recipes",
    "recipes_from_source",
    "require_split_consent",
    "resolve_cache_dir",
    "split_pin_record",
    "verify_download",
    "verify_parts",
]

_LOG = logging.getLogger(__name__)

ACQUISITIONS_NAME: Final = "acquisitions.jsonl"
#: git must be at least this version (CVE-2024-32002, CVE-2025-48384; G.7.5).
GIT_MIN_VERSION: Final = (2, 50, 1)
#: A download at least this large needs the explicit consent of U-07 (Addendum B-2).
LARGE_DOWNLOAD_BYTES: Final = 100 * 1024 * 1024
DEFAULT_TIMEOUT: Final = 60.0
GIT_FETCH_TIMEOUT: Final = 1800.0
#: The history store and its indexes (D.6.16) live under this directory of the cache.
HISTORY_DIR: Final = "git-history"
#: The ``mode`` of the acquisitions row of a history fetch (the depth-1 fetch is ``bare-depth-1``).
HISTORY_MODE: Final = "bare-full-history-blobless"
#: Reading the history store must never fetch a missing blob (it holds none): git >= 2.44.
_NO_LAZY: Final = {"GIT_NO_LAZY_FETCH": "1"}
_CHUNK: Final = 1 << 20

_HEX40: Final = re.compile(r"[0-9a-f]{40}")
_HEX64: Final = re.compile(r"[0-9a-f]{64}")
_HEX32: Final = re.compile(r"[0-9a-f]{32}")
_HOST: Final = re.compile(r"[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?")
_SEGMENT: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}")
_DOI_ZENODO: Final = re.compile(r"10\.5281/zenodo\.([0-9]{1,12})")
_ENV_NAME: Final = re.compile(r"[A-Z][A-Z0-9_]{0,63}")
_ZENODO_VERSION: Final = re.compile(r"[!-~](?:[ -~]{0,62}[!-~])?")
_REF_PATH: Final = re.compile(r"[^\x00-\x1f\x7f]{1,1024}")
_SIZE: Final = re.compile(r"[0-9]{1,19}")
#: An acquisition stamp (``Fetcher._stamp``): RFC 3339 UTC to the second.
RETRIEVED_AT: Final = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
#: ``git ls-tree -l`` prints this for the size of an object it cannot read (absent from a partial clone).
_ABSENT_SIZE: Final = "BAD"
#: Hugging Face git repositories: only datasets are addressed, under their own cache namespace (D.16.18 item 13).
_HF_HOST: Final = "huggingface.co"
_HF_DATASETS: Final = "datasets"
_HF_NAMESPACES: Final = frozenset({"datasets", "models", "spaces"})

#: Redirect hosts followed per origin kind (in addition to the origin's own host; G.7.5). Profiles may add more.
_DEFAULT_HOSTS: Final[Mapping[str, tuple[str, ...]]] = {
    "zenodo": ("zenodo.org",),
    "hf": (
        "huggingface.co", "cdn-lfs.huggingface.co", "cdn-lfs-us-1.hf.co", "cas-bridge.xethub.hf.co",
        "us.aws.cdn.hf.co",  # LFS objects redirect here since 2026-10 (D-831)
    ),
    "url": (),
}
_ENV_ALLOW: Final = (
    "PATH", "SYSTEMROOT", "TEMP", "TMP", "TMPDIR", "SSL_CERT_FILE", "SSL_CERT_DIR",
    "HTTPS_PROXY", "https_proxy", "NO_PROXY", "no_proxy", "ALL_PROXY", "all_proxy",
)  # fmt: skip
_GIT_ENV: Final = {
    # never fetch a missing object from a promisor remote: a partial clone used as a seed source, or as a remote through
    # the file protocol, would otherwise contact its upstream (network use without consent; git >= 2.44)
    "GIT_NO_LAZY_FETCH": "1",
    "GIT_LFS_SKIP_SMUDGE": "1",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_ASKPASS": "",
    "LC_ALL": "C",
}


# --------------------------------------------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------------------------------------------


class FetchError(AgentProvError):
    """A fetch failed or could not be verified (``raw.fetch.*``; exit 1)."""

    code = "raw.fetch.error"
    exit_code = 1


class NetworkRefusedError(FetchError):
    """The request needs the network and ``--allow-network`` was not given (N.1.11(1)). Exit 4."""

    code = "raw.fetch.network_refused"
    exit_code = 4


class LargeDownloadRefusedError(FetchError):
    """A large download without the explicit consent of U-07. Exit 4."""

    code = "raw.fetch.consent_required"
    exit_code = 4


class FetchEnvironmentError(FetchError):
    """``git`` is missing or too old, or the cache lies inside a repository. Exit 3."""

    code = "raw.fetch.environment"
    exit_code = 3


class NotCachedError(FetchError):
    """The requested commit or file is not in the cache and the network is not allowed to fill it."""

    code = "raw.fetch.not_cached"


class DigestMismatchError(FetchError):
    """Fetched bytes differ from the pinned size or digest; nothing was stored (``raw.fetch.digest``)."""

    code = "raw.fetch.digest"


class BlobMismatchError(FetchError):
    """A git blob's recomputed SHA-1 differs from its tree entry (``raw.fetch.blob_sha1``)."""

    code = "raw.fetch.blob_sha1"


class AbsentBlobError(FetchError):
    """A blob of the pinned tree is not in the store (``git ls-tree -l`` prints ``BAD`` for its size): the store came from a
    partial clone. It is never fetched lazily (``GIT_NO_LAZY_FETCH``); ``paths`` names the absent entries (labels only)."""

    code = "raw.fetch.blob_absent"

    def __init__(self, message: str, *, paths: Sequence[str] = ()) -> None:
        super().__init__(message)
        self.paths: tuple[str, ...] = tuple(paths)


class TombstonedDownloadError(FetchError):
    """The pinned or downloaded SHA-256 was purged from this cache (``<cache>/tombstones.jsonl``; G.9.6, D-46)."""

    code = "raw.fetch.tombstoned"


class RedirectRefusedError(FetchError):
    """A redirect left https, left the allow-list or lacked a target (``raw.fetch.redirect``)."""

    code = "raw.fetch.redirect"


# --------------------------------------------------------------------------------------------------------------
# Small validators
# --------------------------------------------------------------------------------------------------------------


def _split_repo(url: str) -> tuple[str, tuple[str, ...], str]:
    """``https://<host>/<owner>/<repo>[.git]`` -> ``(host, (owner,), repo)``; anything else is refused.

    On ``huggingface.co`` a dataset repository ``https://huggingface.co/datasets/<owner>/<name>[.git]`` gives
    ``(host, ("datasets", owner), name)`` (D.16.18 item 13), so it is cached under ``git/huggingface.co/datasets/``. Its other
    namespaces (``spaces``, ``models``) are refused, and so is a two-part path whose owner is one of those names, which
    would otherwise share a cache directory with a dataset.
    """
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.query or parts.fragment or parts.username or parts.password or parts.port:
        raise FetchError("a git repository is an https URL without credentials, port, query or fragment", code="raw.fetch.recipe")
    host = (parts.hostname or "").lower()
    pieces = parts.path.strip("/").split("/")
    pieces[-1] = pieces[-1].removesuffix(".git") if pieces else ""
    if host == _HF_HOST and len(pieces) == 3 and pieces[0] == _HF_DATASETS:
        namespace: tuple[str, ...] = (_HF_DATASETS, pieces[1])
        pieces = pieces[1:]
    elif host == _HF_HOST and pieces[0].lower() in _HF_NAMESPACES:
        raise FetchError("a huggingface.co git repository is https://huggingface.co/datasets/<owner>/<name>", code="raw.fetch.recipe")
    else:
        namespace = (pieces[0],)
    if _HOST.fullmatch(host) is None or len(pieces) != 2 or not all(_SEGMENT.fullmatch(p) for p in pieces):
        raise FetchError("a git repository URL has the shape https://<host>/<owner>/<repo>", code="raw.fetch.recipe")
    return host, namespace, pieces[1]


def _check_relpath(path: str) -> str:
    parts = path.split("/")
    body = parts[:-1] if path.endswith("/") else parts
    if (
        _REF_PATH.fullmatch(path) is None
        or path.startswith(("/", "-"))
        or "\\" in path
        or any(p in ("", ".", "..") for p in body)
    ):
        raise FetchError("a path prefix is a relative path without '..', empty parts or control characters", code="raw.fetch.recipe")
    return path


def _digest_field(value: object, name: str, pattern: re.Pattern[str]) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or pattern.fullmatch(value.lower()) is None:
        raise FetchError(f"recipe field {name!r} is malformed", code="raw.fetch.recipe")
    return value.lower()


def _int_field(value: object, name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > 2**53 - 1:
        raise FetchError(f"recipe field {name!r} must be a non-negative integer", code="raw.fetch.recipe")
    return value


# --------------------------------------------------------------------------------------------------------------
# Recipes
# --------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Recipe:
    """What to acquire: one pinned origin from a profile (data; validated on creation).

    ``kind`` is ``git`` (``repo``, ``commit``, ``paths``), ``zenodo`` (``doi``, ``file``; optionally ``record``, the record
    id, which must equal the version DOI's, and ``version``, the deposit's version label, both recorded with the pin;
    D-201), ``hf`` (``repo`` is the dataset id, ``revision``, ``file`` the path in the dataset) or ``url`` (``url``, with a
    ``sha256`` pin). The digests
    ``sha256`` (the pin), ``md5`` (a transport check) and ``size`` are optional but at least one digest is required for the
    HTTP kinds: a download with nothing to verify against is refused. ``hosts`` adds redirect hosts; ``token_env`` names the
    environment variable that holds a gated-source token, sent only to ``token_host``.
    """

    kind: str
    role: str = ""
    primary: bool = False
    repo: str | None = None
    commit: str | None = None
    paths: tuple[str, ...] = ()
    expected_files: int | None = None
    expected_bytes: int | None = None
    doi: str | None = None
    revision: str | None = None
    file: str | None = None
    url: str | None = None
    sha256: str | None = None
    md5: str | None = None
    size: int | None = None
    hosts: tuple[str, ...] = ()
    token_env: str | None = None
    token_host: str | None = None
    record: int | None = None
    version: str | None = None
    gated: bool | None = None  # hf: whether the dataset is gated, as the profile records it (H.2.3; D-249)

    def __post_init__(self) -> None:
        if self.kind == "git":
            self._check_git()
        elif self.kind in ("zenodo", "hf", "url"):
            self._check_http()
        else:
            raise FetchError(f"unknown recipe kind {self.kind!r}", code="raw.fetch.recipe")
        for host in self.hosts:
            if _HOST.fullmatch(host) is None:
                raise FetchError("a redirect host is a lower-case DNS name", code="raw.fetch.recipe")
        if self.token_env is not None and (_ENV_NAME.fullmatch(self.token_env) is None or not self.token_host):
            raise FetchError("a token needs an upper-case variable name and the host it is sent to", code="raw.fetch.recipe")

    def _check_git(self) -> None:
        if self.repo is None:
            raise FetchError("a git recipe needs a repository", code="raw.fetch.recipe")
        _split_repo(self.repo)
        if self.commit is None or _HEX40.fullmatch(self.commit) is None:
            raise OriginUnpinnedError("a git recipe needs a full 40-hex commit, never a branch, a tag or an empty value")
        for path in self.paths:
            _check_relpath(path)

    def _check_http(self) -> None:
        if self.kind == "zenodo":
            if self.doi is None or _DOI_ZENODO.fullmatch(self.doi) is None:
                raise FetchError("a zenodo recipe needs a version DOI 10.5281/zenodo.<id>", code="raw.fetch.recipe")
            # D-530 item 4: a deposit's file key may hold '/' (a GitHub-integration snapshot is
            # ``<owner>/<repo>-<tag>.zip``); it is checked as an hf path is, and names a file, never a directory
            if self.file is None or self.file.endswith("/"):
                raise FetchError("a zenodo recipe needs the file name inside the deposit", code="raw.fetch.recipe")
            _check_relpath(self.file)
            record = _DOI_ZENODO.fullmatch(self.doi)
            if self.record is not None and (record is None or str(self.record) != record.group(1)):
                raise FetchError("a zenodo pin's record id must be the record of its version DOI", code="raw.fetch.recipe")
            if self.version is not None and _ZENODO_VERSION.fullmatch(self.version) is None:
                raise FetchError("a zenodo pin's version label is 1-64 printable ASCII characters", code="raw.fetch.recipe")
        elif self.kind == "hf":
            if self.repo is None or self.revision is None or self.file is None:
                raise FetchError("an hf recipe needs a dataset, a revision and a file path", code="raw.fetch.recipe")
            if _HEX40.fullmatch(self.revision) is None:
                raise OriginUnpinnedError("an hf recipe needs a full 40-hex revision, never a branch or a tag")
            if not all(_SEGMENT.fullmatch(p) for p in self.repo.split("/")) or len(self.repo.split("/")) != 2:
                raise FetchError("an hf dataset is <owner>/<name>", code="raw.fetch.recipe")
            _check_relpath(self.file)
        else:
            if self.url is None:
                raise FetchError("a url recipe needs a URL", code="raw.fetch.recipe")
            host, _ = self._url_host_path(self.url)
            if _HOST.fullmatch(host) is None:
                raise FetchError("a url recipe needs an https URL with a DNS host", code="raw.fetch.recipe")
            if self.sha256 is None:
                raise FetchError("a url recipe is mutable and needs a sha256 pin", code="raw.fetch.recipe")
        for name, value, pattern in (("sha256", self.sha256, _HEX64), ("md5", self.md5, _HEX32)):
            if value is not None and pattern.fullmatch(value) is None:
                raise FetchError(f"recipe field {name!r} is malformed", code="raw.fetch.recipe")
        if self.sha256 is None and self.md5 is None:
            raise FetchError("a download recipe needs at least one digest (sha256 preferred) to verify against", code="raw.fetch.unverifiable")

    @staticmethod
    def _url_host_path(url: str) -> tuple[str, str]:
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.username or parts.password or parts.fragment:
            raise FetchError("a url recipe needs an https URL without credentials", code="raw.fetch.recipe")
        return (parts.hostname or "").lower(), parts.path

    # -- derived facts --------------------------------------------------------------------------------------
    @property
    def host(self) -> str:
        if self.kind == "git":
            return _split_repo(self.repo or "")[0]
        if self.kind == "zenodo":
            return "zenodo.org"
        if self.kind == "hf":
            return "huggingface.co"
        return self._url_host_path(self.url or "")[0]

    @property
    def download_url(self) -> str:
        """The https URL of an HTTP recipe (built from validated parts only)."""
        if self.kind == "zenodo":
            record = _DOI_ZENODO.fullmatch(self.doi or "")
            assert record is not None and self.file is not None
            return f"https://zenodo.org/records/{record.group(1)}/files/{'/'.join(quote(part, safe='') for part in self.file.split('/'))}?download=1"
        if self.kind == "hf":
            assert self.repo and self.revision and self.file
            return f"https://huggingface.co/datasets/{self.repo}/resolve/{self.revision}/{quote(self.file, safe='/')}"
        assert self.url is not None
        return self.url

    @property
    def allowed_hosts(self) -> frozenset[str]:
        return frozenset({self.host, *_DEFAULT_HOSTS.get(self.kind, ()), *self.hosts})

    def cache_path(self, cache: Path) -> Path:
        """Where the recipe's result lives under ``cache``: the bare repository, or the downloaded file."""
        if self.kind == "git":
            host, namespace, repo = _split_repo(self.repo or "")
            return cache.joinpath("git", host, *namespace, f"{repo}.git")
        if self.kind == "zenodo":
            record = _DOI_ZENODO.fullmatch(self.doi or "")
            assert record is not None and self.file is not None
            return cache / "zenodo" / record.group(1) / Path(*self.file.split("/"))
        if self.kind == "hf":
            assert self.repo and self.revision and self.file
            return cache / "hf" / self.repo.replace("/", "--") / self.revision / Path(*self.file.split("/"))
        assert self.sha256 is not None
        return cache / "url" / self.sha256

    def origin_label(self) -> str:
        """A short non-secret description for messages and the log."""
        if self.kind == "git":
            return f"git {self.repo}@{(self.commit or '')[:12]}"
        if self.kind == "zenodo":
            return f"zenodo {self.doi}:{self.file}"
        if self.kind == "hf":
            return f"hf {self.repo}@{(self.revision or '')[:12]}:{self.file}"
        return f"url {self.host}"

    @classmethod
    def from_pin(
        cls,
        pin: Mapping[str, Any],
        *,
        canonical_repo: str | None = None,
        paths: Sequence[str] | None = None,
    ) -> Recipe:
        """A recipe from one ``[[source.pins]]`` row of a profile (D.4.2). Unknown pin keys (note, date, ...) are ignored.

        ``paths`` overrides the pin's ``tree`` as the set of path prefixes to read. A git pin without a 40-hex commit
        raises ``raw.origin.unpinned`` (exit 3).
        """
        kind = pin.get("kind")
        if not isinstance(kind, str):
            raise FetchError("a pin needs a kind", code="raw.fetch.recipe")
        role = pin.get("role", "")
        common: dict[str, Any] = {
            "kind": kind, "role": role if isinstance(role, str) else "", "primary": pin.get("primary") is True,
        }  # fmt: skip
        if kind == "git":
            repo = pin.get("repo", canonical_repo)
            tree = pin.get("tree")
            chosen = tuple(paths) if paths else ((tree,) if isinstance(tree, str) and tree else ())
            return cls(
                **common,
                repo=repo if isinstance(repo, str) else None,
                commit=pin.get("commit") if isinstance(pin.get("commit"), str) else None,
                paths=chosen,
                expected_files=_int_field(pin.get("expected_files"), "expected_files"),
                expected_bytes=_int_field(pin.get("expected_bytes"), "expected_bytes"),
            )
        hosts = pin.get("hosts", ())
        if not isinstance(hosts, (list, tuple)) or not all(isinstance(h, str) for h in hosts):
            raise FetchError("pin hosts must be a list of strings", code="raw.fetch.recipe")
        token_env, token_host = pin.get("token_env"), pin.get("token_host")
        return cls(
            **common,
            doi=pin.get("doi") if isinstance(pin.get("doi"), str) else None,
            repo=pin.get("dataset", pin.get("repo")) if isinstance(pin.get("dataset", pin.get("repo")), str) else None,
            revision=pin.get("revision") if isinstance(pin.get("revision"), str) else None,
            file=pin.get("file", pin.get("path")) if isinstance(pin.get("file", pin.get("path")), str) else None,
            url=pin.get("url") if isinstance(pin.get("url"), str) else None,
            sha256=_digest_field(pin.get("sha256"), "sha256", _HEX64),
            md5=_digest_field(pin.get("md5"), "md5", _HEX32),
            size=_int_field(pin.get("bytes", pin.get("size")), "bytes"),
            hosts=tuple(hosts),
            token_env=token_env if isinstance(token_env, str) else None,
            token_host=token_host if isinstance(token_host, str) else None,
            record=_int_field(pin.get("record"), "record") if kind == "zenodo" else None,
            version=pin.get("version") if kind == "zenodo" and isinstance(pin.get("version"), str) else None,
            gated=pin.get("gated") if kind == "hf" and isinstance(pin.get("gated"), bool) else None,
        )

    def pin_record(self) -> dict[str, Any]:
        """What a download pin records about its file (D-201): kind and role, for Zenodo the version DOI with its record id
        and version label, for Hugging Face the dataset and revision, else the URL; the file name, size and digests.
        ``None`` values are left out. It becomes the working manifest's snapshot ``pin`` (H.2.3); :func:`verify_download`
        checks a local copy against it."""
        out: dict[str, Any] = {"kind": self.kind, "role": self.role or None, "file": self.file, "bytes": self.size,
                               "sha256": self.sha256, "md5": self.md5}
        if self.kind == "zenodo":
            found = _DOI_ZENODO.fullmatch(self.doi or "")
            out.update(doi=self.doi, record=int(found.group(1)) if found else None, version=self.version)
        elif self.kind == "hf":
            out.update(repo=self.repo, revision=self.revision, gated=self.gated)
        elif self.kind == "url":
            out.update(url=self.url)
        return {k: v for k, v in sorted(out.items()) if v is not None}


def recipes_from_source(source: Mapping[str, Any]) -> tuple[list[Recipe], list[tuple[str, str]]]:
    """The recipes of a profile's ``[source]`` table, in file order, and the pins that are not fetchable yet.

    Returns ``(recipes, skipped)``; ``skipped`` holds ``(role, reason)`` for a download pin that lacks a file name or a
    digest (a Zenodo DOI alone is a documented alternative origin, D.4.3, not a recipe). Pins of other kinds are ignored.
    A pin that is not a full 40-hex revision raises ``raw.origin.unpinned`` (exit 3): a profile defect is loud.
    """
    canonical = source.get("canonical_repo")
    pins = source.get("pins", ())
    recipes: list[Recipe] = []
    skipped: list[tuple[str, str]] = []
    for pin in pins if isinstance(pins, (list, tuple)) else ():
        if not isinstance(pin, Mapping) or pin.get("kind") not in ("git", "zenodo", "hf", "url"):
            continue
        try:
            recipes.append(Recipe.from_pin(pin, canonical_repo=canonical if isinstance(canonical, str) else None))
        except OriginUnpinnedError:
            raise
        except FetchError as exc:
            if exc.code not in ("raw.fetch.recipe", "raw.fetch.unverifiable") or pin.get("kind") == "git":
                raise
            skipped.append((str(pin.get("role", "")), str(exc)))
    return recipes, skipped


# --------------------------------------------------------------------------------------------------------------
# Cache directory
# --------------------------------------------------------------------------------------------------------------


def verify_download(stream: IO[bytes], name: str, recipe: Recipe) -> tuple[str, str, int]:
    """Check a local copy of a download pin's file against the pin, offline (``import --input FILE --verify-against-pin``;
    D-201). ``name`` is the copy's file name, which must equal the last segment of the pinned ``file`` (a Zenodo or Hugging
    Face pin; a URL pin names no file). The bytes are streamed once: size, MD5 (when pinned) and SHA-256 must match. A pin
    without a SHA-256 cannot vouch for an imported object (the raw store and every AER artefact are SHA-256 addressed), so
    it raises ``raw.fetch.unverifiable``. Returns ``(sha256, md5, size)``; a mismatch raises
    :class:`DigestMismatchError` (``raw.fetch.digest``)."""
    if recipe.kind not in ("zenodo", "hf", "url"):
        raise FetchError("only a download pin (zenodo, hf, url) vouches for a single downloaded file", code="raw.fetch.recipe")
    if recipe.sha256 is None:
        raise FetchError("the pin records no SHA-256, so it cannot vouch for the file; pin the SHA-256 in the profile",
                         code="raw.fetch.unverifiable")
    if recipe.file is not None and name != recipe.file.rsplit("/", 1)[-1]:
        raise DigestMismatchError("the file name differs from the pinned file name")
    sha, md5 = hashlib.sha256(), hashlib.md5(usedforsecurity=False)  # MD5 only as the deposit's published transport check
    size = 0
    while chunk := stream.read(_CHUNK):
        size += len(chunk)
        sha.update(chunk)
        md5.update(chunk)
    Fetcher._check_digests(recipe, sha.hexdigest(), md5.hexdigest(), size, where="the input file")
    return sha.hexdigest(), md5.hexdigest(), size


# --------------------------------------------------------------------------------------------------------------
# Split download pins (D-249): one archive cut into byte parts, each part pinned
# --------------------------------------------------------------------------------------------------------------

#: The ``archive`` value of a download pin whose file is cut into byte parts (``parts``: in order, each pinned).
SPLIT_ZIP: Final = "split-zip"
_PART_KEYS: Final = frozenset({"file", "bytes", "size", "sha256", "md5"})
_WHOLE_FILE_KEYS: Final = ("sha256", "md5", "bytes", "size")


def is_split_pin(pin: Mapping[str, Any] | None) -> bool:
    """Whether ``pin`` declares an archive stored as byte parts (``archive = "split-zip"`` with ``parts``)."""
    return isinstance(pin, Mapping) and pin.get("archive") == SPLIT_ZIP


def part_recipes(pin: Mapping[str, Any]) -> list[Recipe]:
    """One recipe per part of a split download pin, in the pin's order (D-249).

    The pin is a Zenodo or Hugging Face download pin whose ``file`` names the logical archive (its label; it exists
    upstream only as the parts) and whose ``parts`` list ``{file, bytes, sha256, md5?}`` in order. Each part is pinned like
    a single download (``sha256`` required: the raw store is SHA-256 addressed). The pin itself carries no whole-file
    digest. Order is the pin's; part file names locate the parts and are verified with their digests, never sorted.
    """
    if not is_split_pin(pin) or pin.get("kind") not in ("zenodo", "hf"):
        raise FetchError("a split archive is a zenodo or hf download pin with archive = \"split-zip\"", code="raw.fetch.recipe")
    if any(key in pin for key in _WHOLE_FILE_KEYS):
        raise FetchError("a split pin pins its parts, not a whole file", code="raw.fetch.recipe")
    logical, parts = pin.get("file", pin.get("path")), pin.get("parts")
    if not isinstance(logical, str) or not isinstance(parts, (list, tuple)) or len(parts) < 2:
        raise FetchError("a split pin names its logical file and at least two parts", code="raw.fetch.recipe")
    base = {k: v for k, v in pin.items() if k not in ("parts", "archive", "file", "path")}
    recipes, files = [], set()
    for part in parts:
        if not isinstance(part, Mapping) or not set(part) <= _PART_KEYS or not isinstance(part.get("file"), str):
            raise FetchError("a split part is {file, bytes, sha256, md5?}", code="raw.fetch.recipe")
        if part.get("sha256") is None:
            raise FetchError("a split part needs its SHA-256", code="raw.fetch.unverifiable")
        if part["file"] in files or part["file"] == logical:
            raise FetchError("split part files are distinct from each other and from the logical file", code="raw.fetch.recipe")
        files.add(part["file"])
        recipes.append(Recipe.from_pin({**base, **part}))
    return recipes


def split_pin_record(pin: Mapping[str, Any]) -> dict[str, Any]:
    """What a split download pin records (the working manifest's snapshot ``pin``, D-201/D-249): the deposit fields of a
    part's record, the logical ``file``, ``archive`` and the ordered ``parts`` with their sizes and digests."""
    recipes = part_recipes(pin)
    first = recipes[0].pin_record()
    out = {k: v for k, v in first.items() if k not in ("file", "bytes", "sha256", "md5")}
    out.update(archive=SPLIT_ZIP, file=pin.get("file", pin.get("path")),
               parts=[{k: v for k, v in r.pin_record().items() if k in ("file", "bytes", "sha256", "md5")} for r in recipes])
    return dict(sorted(out.items()))


def require_split_consent(recipes: Sequence[Recipe], consent: bool) -> int:
    """The total pinned size of a split archive's parts; U-07's consent is needed when it reaches the large-download
    threshold, whatever each part's size (D-249). A part without a pinned size counts as large."""
    total = sum(r.size for r in recipes if r.size is not None)
    if (total >= LARGE_DOWNLOAD_BYTES or any(r.size is None for r in recipes)) and not consent:
        raise LargeDownloadRefusedError(
            f"a split archive of {len(recipes)} parts totalling {total} bytes; a large download needs the explicit "
            "consent of U-07 (--i-consent-to-large-download)"
        )
    return total


def verify_parts(open_part: Callable[[str], IO[bytes]], recipes: Sequence[Recipe]) -> list[tuple[str, int]]:
    """``verify_download`` for every part of a split pin, in the pin's order: ``open_part(name)`` opens the local copy whose
    file name is the part's (the name only locates it; size, MD5 when pinned and SHA-256 are checked). Returns
    ``[(sha256, size), ...]`` in order; the first mismatch raises (``raw.fetch.digest``)."""
    out = []
    for recipe in recipes:
        assert recipe.file is not None
        name = recipe.file.rsplit("/", 1)[-1]
        with open_part(name) as handle:
            sha256, _md5, size = verify_download(handle, name, recipe)
        out.append((sha256, size))
    return out


def resolve_cache_dir(explicit: str | os.PathLike[str] | None = None, env: Mapping[str, str] | None = None) -> Path:
    """``--cache-dir``, else ``$AGENTPROV_UPSTREAM_CACHE``, else ``$AGENTPROV_HOME/cache`` (default home ``~/.agentprov``).

    The directory must lie outside every git repository (G.7.5): a path with a ``.git`` ancestor is refused (exit 3). It is
    not created here.
    """
    env = os.environ if env is None else env
    if explicit:
        chosen = Path(explicit)
    elif env.get("AGENTPROV_UPSTREAM_CACHE"):
        chosen = Path(env["AGENTPROV_UPSTREAM_CACHE"])
    else:
        home = env.get("AGENTPROV_HOME")
        chosen = (Path(home) if home else Path.home() / ".agentprov") / "cache"
    chosen = chosen.expanduser().absolute()
    for ancestor in (chosen, *chosen.parents):
        if (ancestor / ".git").exists():
            raise FetchEnvironmentError("the fetch cache must lie outside every git repository and working directory")
    return chosen


# --------------------------------------------------------------------------------------------------------------
# Acquisitions log
# --------------------------------------------------------------------------------------------------------------

_SECRET_KEYS: Final = frozenset({"token", "authorization", "password", "secret", "key"})


class AcquisitionLog:
    """``<cache>/acquisitions.jsonl``: one JCS line per real retrieval, appended with a single ``write`` (never rewritten)."""

    def __init__(self, path: Path, limits: IngestLimits | None = None) -> None:
        self.path = path
        self.limits = limits or IngestLimits()

    def append(self, row: Mapping[str, Any]) -> None:
        if _SECRET_KEYS & {str(k).lower() for k in row}:
            raise FetchError("an acquisitions row never carries a credential", code="raw.fetch.log")
        line = jcs_bytes(dict(row)) + b"\n"
        try:  # ultra raw-withhold #7: a log that cannot be written is a typed refusal (the caller publishes nothing)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_BINARY", 0), 0o644)
            try:
                view = memoryview(line)
                while view:
                    view = view[os.write(fd, view):]
                os.fsync(fd)
            finally:
                os.close(fd)
        except OSError as exc:
            raise FetchError(f"the acquisitions log cannot be written ({type(exc).__name__})", code="raw.fetch.log") from None

    def rows(self) -> list[dict[str, Any]]:
        """Every object row, read through the bounded strict JSONL loader (no link followed). A torn line (an append cut
        short) or a corrupt one is :class:`FetchError` ``raw.fetch.log`` (ultra raw-withhold #9), fail closed."""
        if not os.path.lexists(self.path):
            return []
        out: list[dict[str, Any]] = []
        try:
            with open_evidence(self.path.parent, self.path.name, self.limits) as handle:
                for _line, _offset, value in iter_jsonl(handle, self.limits):
                    if isinstance(value, dict):
                        out.append(value)
        except IngestError as exc:
            raise FetchError(f"{ACQUISITIONS_NAME} cannot be read safely ({exc.code})", code="raw.fetch.log") from None
        except OSError as exc:
            raise FetchError(f"{ACQUISITIONS_NAME} cannot be read ({type(exc).__name__})", code="raw.fetch.log") from None
        return out


# --------------------------------------------------------------------------------------------------------------
# HTTP layer
# --------------------------------------------------------------------------------------------------------------


class HttpResponse(Protocol):
    """What the downloader needs from a response (a fake in the tests)."""

    status: int
    headers: Mapping[str, str]
    url: str

    def read(self, n: int = -1, /) -> bytes: ...
    def close(self) -> None: ...


class Transport(Protocol):
    """The HTTP seam: ``open`` returns a response or raises. Redirect policy is the transport's job."""

    def open(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        unredirected: Mapping[str, str],
        timeout: float,
        allowed_hosts: frozenset[str],
    ) -> HttpResponse: ...


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Follow a redirect only to an https URL on the allow-list; credentials never travel to another host (R-43; SEC-24)."""

    max_redirections = 5

    def __init__(self, allowed_hosts: frozenset[str]) -> None:
        self.allowed_hosts = allowed_hosts

    def redirect_request(
        self, req: urllib.request.Request, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> urllib.request.Request | None:
        target = urlsplit(newurl)
        if target.scheme != "https":
            raise RedirectRefusedError("a redirect left https (a downgrade is refused)")
        host = (target.hostname or "").lower()
        if host not in self.allowed_hosts:
            raise RedirectRefusedError("a redirect went to a host that is not on the allow-list")
        if target.username or target.password:
            raise RedirectRefusedError("a redirect carried credentials in the URL")
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is None:
            return None
        # drop every credential header on any host change (add_unredirected_header values are not copied by urllib)
        if host != (urlsplit(req.full_url).hostname or "").lower():
            for name in list(new.headers):
                if name.lower() in ("authorization", "cookie", "proxy-authorization"):
                    del new.headers[name]
        return new


class UrllibTransport:
    """The production transport: ``urllib`` with certificate verification and the safe redirect handler."""

    def open(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        unredirected: Mapping[str, str],
        timeout: float,
        allowed_hosts: frozenset[str],
    ) -> HttpResponse:
        request = urllib.request.Request(url, headers=dict(headers), method="GET")  # noqa: S310 - https validated by Recipe
        for name, value in unredirected.items():
            request.add_unredirected_header(name, value)
        opener = urllib.request.build_opener(
            SafeRedirectHandler(allowed_hosts), urllib.request.HTTPSHandler(context=ssl.create_default_context())
        )
        try:
            return opener.open(request, timeout=timeout)  # noqa: S310
        except urllib.error.HTTPError as exc:
            raise FetchError(f"the server answered HTTP {exc.code}", code="raw.fetch.http_status") from None
        except (urllib.error.URLError, TimeoutError, ssl.SSLError, OSError) as exc:
            raise FetchError(f"the download failed ({type(exc).__name__})", code="raw.fetch.transport") from None


# --------------------------------------------------------------------------------------------------------------
# Results
# --------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TreeEntry:
    """One ``git ls-tree`` row: mode, object type, blob id, size (None for a gitlink) and path."""

    mode: str
    type: str
    oid: str
    size: int | None
    path: str

    @property
    def is_blob(self) -> bool:
        return self.type == "blob" and self.mode != "160000"

    @property
    def is_symlink(self) -> bool:
        return self.mode == "120000"

    @property
    def is_gitlink(self) -> bool:
        return self.mode == "160000"


@dataclass(frozen=True, slots=True)
class FetchedBlob:
    """A verified git blob: its tree entry, recomputed SHA-1 (equal to the entry's) and SHA-256, and the bytes."""

    entry: TreeEntry
    sha256: str
    data: bytes = field(repr=False)


@dataclass(frozen=True, slots=True)
class StoredBlob:
    """A blob written to a raw store, with the origin that records where it came from."""

    path: str
    blob_sha1: str
    sha256: str
    size: int
    created: bool
    origin: Origin


@dataclass(frozen=True, slots=True)
class FetchPlan:
    """What :meth:`Fetcher.plan` would do (no network, no writes): the target and whether the cache already has it."""

    recipe: Recipe
    target: Path
    cached: bool
    needs_network: bool
    host: str
    purpose: str
    expected_bytes: int | None = None
    large: bool = False


@dataclass(frozen=True, slots=True)
class FetchResult:
    """The outcome of :meth:`Fetcher.fetch`.

    ``network_used`` is false when the cache already held the result. For ``git``: ``tree`` is the commit's tree id,
    ``files``/``bytes`` the number and total size of the blobs under the recipe's paths (gitlinks excluded) and
    ``gitlinks`` the number of submodule entries recorded and not fetched. For downloads: ``sha256``, ``md5`` and ``bytes``
    of the file. ``problems`` lists mismatches with the profile's expectations (file count, size): they do not abort the
    fetch, the caller decides (the CLI exits 1).
    """

    recipe: Recipe
    path: Path
    network_used: bool
    sha256: str | None = None
    md5: str | None = None
    bytes: int | None = None
    tree: str | None = None
    files: int | None = None
    gitlinks: int = 0
    verified: str = ""
    problems: tuple[str, ...] = ()
    #: D-455: when the downloaded file was retrieved, from its acquisition record (``None`` for git, and for a cached file
    #: the cache's log does not record); never the time of this call.
    retrieved_at: str | None = None


@dataclass(frozen=True, slots=True)
class HistoryResult:
    """The outcome of :meth:`Fetcher.fetch_history`: the history store, the index and what was fetched (``network_used``
    false when the store already held the pinned commit; ``index_created`` false when the index file already existed)."""

    recipe: Recipe
    store: Path
    index_path: Path
    index: HistoryIndex
    index_sha256: str
    network_used: bool
    index_created: bool
    fetched_bytes: int = 0


def check_git_version(text: str) -> tuple[int, ...]:
    """Parse ``git --version`` output; :class:`FetchEnvironmentError` when it is not recognisable or older than 2.50.1."""
    match = re.search(r"git version (\d+)\.(\d+)\.(\d+)", text)
    if match is None:
        raise FetchEnvironmentError("cannot read the git version")
    version = tuple(int(g) for g in match.groups())
    if version < GIT_MIN_VERSION:
        raise FetchEnvironmentError(
            "git is older than 2.50.1 (CVE-2024-32002, CVE-2025-48384); upgrade it before fetching"
        )
    return version


def parse_ls_tree(data: bytes) -> tuple[list[TreeEntry], int]:
    """Parse ``git ls-tree -r -z -l --full-tree`` output. Returns the entries and the number of undecodable paths skipped.

    A size of ``-`` (a gitlink) becomes ``None``. A size of ``BAD`` means the object is absent from the store (a partial
    clone; git prints it when it may not fetch lazily): every such entry is collected and :class:`AbsentBlobError` is
    raised, so a tree with absent blobs is refused with a typed code, never half-read. Any other non-decimal size is
    ``raw.fetch.git``.
    """
    entries: list[TreeEntry] = []
    absent: list[str] = []
    skipped = 0
    for record in data.split(b"\0"):
        if not record:
            continue
        head, tab, raw_path = record.partition(b"\t")
        fields = head.split()
        if not tab or len(fields) != 4:
            raise FetchError("unexpected git ls-tree output", code="raw.fetch.git")
        mode, kind, oid, size = (f.decode("ascii", "replace") for f in fields)
        if _HEX40.fullmatch(oid) is None:
            raise FetchError("unexpected object id in git ls-tree output", code="raw.fetch.git")
        if size not in ("-", _ABSENT_SIZE) and _SIZE.fullmatch(size) is None:
            raise FetchError("unexpected object size in git ls-tree output", code="raw.fetch.git")
        try:
            path = raw_path.decode("utf-8")
        except UnicodeDecodeError:
            path = None
        if size == _ABSENT_SIZE:
            absent.append(path if path is not None else raw_path.decode("utf-8", "backslashreplace"))
            continue
        if path is None:
            skipped += 1
            continue
        entries.append(TreeEntry(mode, kind, oid, None if size == "-" else int(size), path))
    if absent:
        raise AbsentBlobError(
            f"{len(absent)} object(s) of the pinned tree are absent from the store (a partial clone?); they are never "
            "fetched lazily: seed from a complete clone or fetch the pin",
            paths=sorted(absent),
        )
    return sorted(entries, key=lambda e: e.path.encode("utf-8")), skipped


def _now_utc() -> datetime:
    return datetime.now(UTC)


# --------------------------------------------------------------------------------------------------------------
# The fetcher
# --------------------------------------------------------------------------------------------------------------


class Fetcher:
    """Acquire recipes into ``cache_dir``. See the module docstring for the guarantees.

    ``allow_network`` is the only switch that lets a socket or ``git fetch`` run. ``consent`` is the text recorded in the
    acquisitions log (for example ``"--allow-network"``). ``large_download_consent`` lifts the U-07 guard.
    ``remote_urls``/``file_protocol`` are a **test seam**: they replace the https remote of a git recipe by a local
    repository URL and allow git's file protocol; the CLI never sets them.
    """

    def __init__(
        self,
        cache_dir: Path,
        *,
        allow_network: bool = False,
        consent: str = "",
        large_download_consent: bool = False,
        transport: Transport | None = None,
        git: str | None = None,
        now: Callable[[], datetime] = _now_utc,
        limits: IngestLimits | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        env: Mapping[str, str] | None = None,
        remote_urls: Mapping[str, str] | None = None,
        file_protocol: bool = False,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.allow_network = allow_network
        self.consent = consent
        self.large_download_consent = large_download_consent
        self._transport = transport
        self._git = git
        self._git_checked = False
        self._now = now
        self.limits = limits or IngestLimits()
        self.timeout = timeout
        self._env = os.environ if env is None else env
        self._remote_urls = dict(remote_urls or {})
        self._file_protocol = file_protocol
        self.log = AcquisitionLog(self.cache_dir / ACQUISITIONS_NAME, self.limits)
        self._history_cache: dict[tuple[str, str], HistoryIndex | None] = {}

    # -- policy ---------------------------------------------------------------------------------------------
    def _write_lock(self) -> Any:
        """The cache's write lock (N.1.9 G6a), taken only around a write: cached reads never lock."""
        from agentprov.io.locks import fetch_cache_lock

        return fetch_cache_lock(self.cache_dir, command="fetch")

    def _require_network(self, host: str, purpose: str) -> None:
        if not self.allow_network:
            raise NetworkRefusedError(f"{purpose} needs the network; rerun with --allow-network (N.1.11)")
        _LOG.info("network host=%s purpose=%s", host, purpose)

    def _stamp(self) -> str:
        return self._now().astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    # -- git plumbing -----------------------------------------------------------------------------------------
    def _git_exe(self) -> str:
        if self._git is None:
            found = shutil.which("git")
            if found is None:
                raise FetchEnvironmentError("git is not installed")
            self._git = str(Path(found).absolute())
        if not self._git_checked:
            try:
                done = subprocess.run([self._git, "--version"], capture_output=True, timeout=30, check=False, env=self._git_env())  # noqa: S603
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise FetchEnvironmentError(f"git could not be run ({type(exc).__name__})") from None
            check_git_version(done.stdout.decode("utf-8", "replace"))
            self._git_checked = True
        return self._git

    def _git_env(self) -> dict[str, str]:
        env = {k: self._env[k] for k in _ENV_ALLOW if k in self._env}
        env.update(_GIT_ENV)
        return env

    def _hardening(self) -> list[str]:
        # https only: no downgrade to http, git:// or ssh, and no redirect to a host outside the recipe (a renamed
        # repository fails loudly and its recipe is updated); the file protocol only under the test seam (CB-25)
        return [
            "-c", f"core.hooksPath={os.devnull}",
            "-c", "protocol.allow=never",
            "-c", "protocol.https.allow=always",
            "-c", f"protocol.file.allow={'always' if self._file_protocol else 'never'}",
            "-c", "protocol.ext.allow=never",
            "-c", "http.followRedirects=false",
            "-c", "transfer.fsckObjects=true",
            "-c", "core.symlinks=false",
        ]  # fmt: skip

    def _run_git(self, args: Sequence[str], *, timeout: float = 120.0, env_extra: Mapping[str, str] | None = None) -> bytes:
        exe = self._git_exe()
        try:
            done = subprocess.run(  # noqa: S603 - argv built from validated recipe data, no shell
                [exe, *self._hardening(), *args], capture_output=True, timeout=timeout, check=False,
                env={**self._git_env(), **(env_extra or {})},
            )
        except subprocess.TimeoutExpired:
            raise FetchError("git timed out", code="raw.fetch.git") from None
        if done.returncode != 0:
            raise FetchError(f"git {args[0] if args else ''} failed (exit {done.returncode})", code="raw.fetch.git")
        return done.stdout

    def _has_commit(self, bare: Path, commit: str) -> bool:
        if not (bare / "objects").is_dir():
            return False
        exe = self._git_exe()
        done = subprocess.run(  # noqa: S603
            [exe, *self._hardening(), "-C", str(bare), "cat-file", "-e", f"{commit}^{{commit}}"],
            capture_output=True, timeout=60, check=False, env=self._git_env(),
        )  # fmt: skip
        return done.returncode == 0

    # -- planning -----------------------------------------------------------------------------------------------
    def plan(self, recipe: Recipe) -> FetchPlan:
        """What :meth:`fetch` would do. No network, no writes (``--dry-run``)."""
        target = recipe.cache_path(self.cache_dir)
        if recipe.kind == "git":
            assert recipe.commit is not None
            cached = self._git_cached(recipe, target)
            purpose = f"fetch commit {recipe.commit[:12]} of {recipe.repo}"
            return FetchPlan(recipe, target, cached, not cached, recipe.host, purpose)
        cached = target.is_file()
        size = recipe.size
        return FetchPlan(
            recipe, target, cached, not cached, recipe.host, f"download {recipe.file or recipe.url}", size,
            size is None or size >= LARGE_DOWNLOAD_BYTES,  # an unsized download may need consent (D-249)
        )  # fmt: skip

    # -- git ------------------------------------------------------------------------------------------------------
    def fetch(self, recipe: Recipe) -> FetchResult:
        """Make ``recipe`` available in the cache and verify what can be verified without reading every blob."""
        if recipe.kind == "git":
            return self._fetch_git(recipe)
        return self._fetch_http(recipe)

    def _fetch_git(self, recipe: Recipe) -> FetchResult:
        assert recipe.repo is not None and recipe.commit is not None
        bare = recipe.cache_path(self.cache_dir)
        used = False
        if not self._git_cached(recipe, bare):
            again = " again (the cached commit has no acquisitions row)" if self._has_commit(bare, recipe.commit) else ""
            self._require_network(recipe.host, f"fetching commit {recipe.commit[:12]} of {recipe.repo}{again}")
            self._git_exe()
            with self._write_lock():  # G6a: one writer of the cache; a concurrent fetch refuses clearly
                if not self._git_cached(recipe, bare):  # another process may have fetched it meanwhile
                    bare.parent.mkdir(parents=True, exist_ok=True)
                    if not (bare / "objects").is_dir():
                        self._run_git(["init", "-q", "--bare", "--template=", str(bare)])
                    remote = self._remote_urls.get(recipe.repo, recipe.repo)
                    self._run_git(
                        ["-C", str(bare), "fetch", "-q", "--depth", "1", "--no-recurse-submodules", "--", remote,
                         recipe.commit],
                        timeout=GIT_FETCH_TIMEOUT,
                    )
                    used = True
                    if not self._has_commit(bare, recipe.commit):
                        raise FetchError("the fetched repository does not hold the pinned commit", code="raw.fetch.git")
        tree = self._run_git(["-C", str(bare), "rev-parse", "--verify", f"{recipe.commit}^{{tree}}"]).decode("ascii", "replace").strip()
        if _HEX40.fullmatch(tree) is None:
            raise FetchError("git returned an unexpected tree id", code="raw.fetch.git")
        entries, skipped = self.git_tree(recipe)
        blobs = [e for e in entries if e.is_blob]
        total = sum(e.size or 0 for e in blobs)
        problems: list[str] = []
        if recipe.expected_files is not None and len(blobs) != recipe.expected_files:
            problems.append(f"expected {recipe.expected_files} files under the pinned tree, found {len(blobs)}")
        if recipe.expected_bytes is not None and total != recipe.expected_bytes:
            problems.append(f"expected {recipe.expected_bytes} bytes under the pinned tree, found {total}")
        if skipped:
            problems.append(f"{skipped} path(s) are not valid UTF-8 and were skipped")
        gitlinks = sum(1 for e in entries if e.is_gitlink)
        if used:
            self.log.append(
                {
                    "kind": "git", "repo": recipe.repo, "commit": recipe.commit, "tree": tree, "mode": "bare-depth-1",
                    "store": str(bare.relative_to(self.cache_dir)), "paths": list(recipe.paths), "files": len(blobs),
                    "bytes": total, "retrieved_at": self._stamp(), "consent": self.consent,
                }
            )  # fmt: skip
        return FetchResult(
            recipe, bare, used, bytes=total, tree=tree, files=len(blobs), gitlinks=gitlinks,
            verified="commit-id+fsck" if used else "cached", problems=tuple(problems),
        )  # fmt: skip

    def _git_cached(self, recipe: Recipe, bare: Path) -> bool:
        """Whether the pinned commit is in the bare store **and** its acquisition is recorded (ultra raw-withhold #7). The
        row is written after the fetch, which cannot be taken back out of the store; a commit whose row was lost (the
        append failed) counts as not cached, so the next fetch with the network records it instead of using an
        unrecorded acquisition for good."""
        assert recipe.commit is not None
        if not self._has_commit(bare, recipe.commit):
            return False
        store = str(bare.relative_to(self.cache_dir)) if bare.is_relative_to(self.cache_dir) else None
        return any(row.get("kind") == "git" and row.get("repo") == recipe.repo and row.get("commit") == recipe.commit
                   and self._same_store(row.get("store"), store, bare) for row in self.log.rows())

    def _same_store(self, recorded: object, store: str | None, bare: Path) -> bool:
        """Whether an acquisition row's ``store`` names this bare store (V-1). Rows record the cache-relative path; rows
        written before that (2026-10-08) record an absolute one, which counts when it resolves to the same bare store
        **under the cache root**. Anything else (another directory, a path outside the cache) does not: fail closed."""
        if not isinstance(recorded, str):
            return False
        if store is not None and recorded == store:
            return True
        path = Path(recorded)
        if not path.is_absolute():
            return False
        root = self.cache_dir.resolve()
        resolved = path.resolve()
        return resolved.is_relative_to(root) and resolved == bare.resolve()

    def git_tree(self, recipe: Recipe) -> tuple[list[TreeEntry], int]:
        """The tree entries under the recipe's paths (``git ls-tree``), sorted by path; and the count of undecodable paths.

        Needs the commit in the cache; never uses the network (:class:`NotCachedError` otherwise).
        """
        assert recipe.commit is not None
        bare = recipe.cache_path(self.cache_dir)
        if not self._has_commit(bare, recipe.commit):
            raise NotCachedError(f"commit {recipe.commit[:12]} of {recipe.repo} is not in the cache")
        args = ["-C", str(bare), "ls-tree", "-r", "-z", "-l", "--full-tree", recipe.commit]
        if recipe.paths:
            args += ["--", *recipe.paths]
        return parse_ls_tree(self._run_git(args, timeout=600.0))

    def iter_git_blobs(self, recipe: Recipe, entries: Sequence[TreeEntry] | None = None) -> Iterator[FetchedBlob]:
        """Yield every blob of the recipe (or of ``entries``) with its SHA-1 recomputed and its SHA-256 computed.

        Gitlinks are skipped (recorded, not fetched). A symlink blob is yielded as data and never resolved. A blob whose
        recomputed SHA-1 differs from its tree entry raises :class:`BlobMismatchError`; one larger than
        ``max_artefact_bytes`` raises :class:`FetchError` (``ingest.size.file``).
        """
        assert recipe.commit is not None
        chosen = list(entries) if entries is not None else self.git_tree(recipe)[0]
        wanted = [e for e in chosen if e.is_blob]
        if not wanted:
            return
        bare = recipe.cache_path(self.cache_dir)
        if not self._has_commit(bare, recipe.commit):
            raise NotCachedError(f"commit {recipe.commit[:12]} of {recipe.repo} is not in the cache")
        exe = self._git_exe()
        proc = subprocess.Popen(  # noqa: S603 - argv from validated data; no shell
            [exe, *self._hardening(), "-C", str(bare), "cat-file", "--batch"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=self._git_env(),
        )  # fmt: skip
        try:
            assert proc.stdin is not None and proc.stdout is not None
            for entry in wanted:
                proc.stdin.write(entry.oid.encode("ascii") + b"\n")
                proc.stdin.flush()
                yield self._read_blob(proc.stdout, entry)
        finally:
            with contextlib.suppress(OSError):
                if proc.stdin is not None:
                    proc.stdin.close()
            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            if proc.stdout is not None:
                proc.stdout.close()

    def _read_blob(self, out: IO[bytes], entry: TreeEntry) -> FetchedBlob:
        header = out.readline(256).split()
        if len(header) != 3 or header[0].decode("ascii", "replace") != entry.oid or header[1] != b"blob":
            raise FetchError("git cat-file did not return the requested blob", code="raw.fetch.git")
        size = int(header[2])
        if size > self.limits.max_artefact_bytes:
            raise FetchError("a blob exceeds max_artefact_bytes", code="ingest.size.file")
        data = _read_exact(out, size)
        if out.read(1) != b"\n":
            raise FetchError("git cat-file framing error", code="raw.fetch.git")
        sha1 = hashlib.sha1(b"blob %d\0" % size, usedforsecurity=False)  # git object id, not a security digest
        sha1.update(data)
        if sha1.hexdigest() != entry.oid or (entry.size is not None and entry.size != size):
            raise BlobMismatchError("a blob's SHA-1 or size differs from its tree entry")
        return FetchedBlob(entry, sha256_hex(data), data)

    def store_git(
        self,
        recipe: Recipe,
        store: Any,
        origins: OriginLog | None = None,
        entries: Sequence[TreeEntry] | None = None,
    ) -> list[StoredBlob]:
        """Stream the recipe's verified blobs into a :class:`~agentprov.raw.store.RawObjectStore`.

        Each object is stored under its SHA-256 (``expected_sha256`` checked by the store) and recorded with the
        ``git`` origin ``{repo, commit, path, blob_sha1}`` (G.7.5; no retrieval time, H.2.3) in ``origins`` when given. When the
        recipe's history index is cached (:meth:`fetch_history`), the origin also carries ``introduced_in_commit`` (D.6.16).
        """
        assert recipe.repo is not None and recipe.commit is not None
        stored: list[StoredBlob] = []
        history = self.history_index(recipe)  # cached index only: no network, no computation (D.6.16)
        for blob in self.iter_git_blobs(recipe, entries):
            path = blob.entry.path
            ext = "json" if path.endswith(".json") else "jsonl" if path.endswith(".jsonl") else "bin"
            put = store.put_chunks([blob.data], ext=ext, expected_sha256=blob.sha256)
            introduced = history.lookup(path, blob.entry.oid) if history is not None else None
            origin = Origin.git(recipe.repo, recipe.commit, path, blob.entry.oid, introduced_in_commit=introduced)
            if origins is not None:
                origins.add(blob.sha256, origin)
            stored.append(StoredBlob(path, blob.entry.oid, blob.sha256, len(blob.data), put.created, origin))
        return stored

    # -- https ----------------------------------------------------------------------------------------------------
    # -- git history (D.6.16) -----------------------------------------------------------------------------------
    def history_store(self, recipe: Recipe) -> Path:
        """The blobless full-history bare store of a git recipe's repository (a sibling of the depth-1 store)."""
        assert recipe.kind == "git"
        host, namespace, repo = _split_repo(recipe.repo or "")
        return self.cache_dir.joinpath(HISTORY_DIR, host, *namespace, f"{repo}.git")

    def history_index_path(self, recipe: Recipe) -> Path:
        """Where the index of the recipe's pinned commit lives: ``<repo>.index/<commit>.jsonl``, keyed by the commit."""
        assert recipe.kind == "git" and recipe.commit is not None
        host, namespace, repo = _split_repo(recipe.repo or "")
        return self.cache_dir.joinpath(HISTORY_DIR, host, *namespace, f"{repo}.index", f"{recipe.commit}.jsonl")

    def _has_history_commit(self, bare: Path, commit: str) -> bool:
        if not (bare / "objects").is_dir() or (bare / "shallow").exists():
            return False
        exe = self._git_exe()
        done = subprocess.run(  # noqa: S603
            [exe, *self._hardening(), "-C", str(bare), "cat-file", "-e", f"{commit}^{{commit}}"],
            capture_output=True, timeout=60, check=False, env={**self._git_env(), **_NO_LAZY},
        )  # fmt: skip
        return done.returncode == 0

    def plan_history(self, recipe: Recipe) -> FetchPlan:
        """What :meth:`fetch_history` would do. No network, no writes. ``cached`` means the index file exists."""
        assert recipe.kind == "git" and recipe.commit is not None
        target = self.history_store(recipe)
        indexed = self.history_index_path(recipe).is_file()
        have = indexed or self._has_history_commit(target, recipe.commit)
        purpose = f"fetch the blobless full history of {recipe.repo} up to commit {recipe.commit[:12]}"
        return FetchPlan(recipe, target, indexed, not have, recipe.host, purpose)

    def history_index(self, recipe: Recipe) -> HistoryIndex | None:
        """The cached history index of the recipe's pinned commit, or ``None`` when there is none. Never touches the network
        and never computes anything; a present but corrupt or mismatching file raises :class:`~agentprov.raw.history.HistoryError`."""
        if recipe.kind != "git" or recipe.commit is None:
            return None
        key = (recipe.repo or "", recipe.commit)
        if key in self._history_cache:
            return self._history_cache[key]
        path = self.history_index_path(recipe)
        found = None
        if path.is_file():
            found = HistoryIndex.from_bytes(path.read_bytes(), expect_repo=recipe.repo, expect_commit=recipe.commit)
        self._history_cache[key] = found
        return found

    def fetch_history(self, recipe: Recipe) -> HistoryResult:
        """Make the introducing-commit index of ``recipe`` available: fetch the blobless full history of the pinned commit if
        the history store lacks it (network, ``--allow-network``), compute the index from the store (offline), write it.

        One acquisitions row is appended when the network was used. Idempotent: with the index file present nothing is
        fetched, computed or written.
        """
        assert recipe.kind == "git" and recipe.repo is not None and recipe.commit is not None
        bare = self.history_store(recipe)
        path = self.history_index_path(recipe)
        existing = self.history_index(recipe)
        if existing is not None:
            return HistoryResult(recipe, bare, path, existing, sha256_hex(path.read_bytes()), False, False)
        if not self._has_history_commit(bare, recipe.commit):  # refuse an offline fetch before taking the lock
            self._require_network(recipe.host, f"fetching the blobless history of {recipe.repo} up to {recipe.commit[:12]}")
        with self._write_lock():  # G6a: the history store and its index file have one writer
            existing = self.history_index(recipe)
            if existing is not None:
                return HistoryResult(recipe, bare, path, existing, sha256_hex(path.read_bytes()), False, False)
            return self._fetch_history_locked(recipe, bare, path)

    def _fetch_history_locked(self, recipe: Recipe, bare: Path, path: Path) -> HistoryResult:
        assert recipe.repo is not None and recipe.commit is not None
        used = False
        before = _tree_bytes(bare)
        if not self._has_history_commit(bare, recipe.commit):
            self._require_network(recipe.host, f"fetching the blobless history of {recipe.repo} up to {recipe.commit[:12]}")
            self._git_exe()
            bare.parent.mkdir(parents=True, exist_ok=True)
            if not (bare / "objects").is_dir():
                self._run_git(["init", "-q", "--bare", "--template=", str(bare)])
            remote = self._remote_urls.get(recipe.repo, recipe.repo)
            for key, value in (
                ("remote.origin.url", remote), ("remote.origin.promisor", "true"), ("remote.origin.partialclonefilter", "blob:none"),
            ):
                self._run_git(["-C", str(bare), "config", key, value], env_extra=_NO_LAZY)
            self._run_git(
                ["-C", str(bare), "fetch", "-q", "--filter=blob:none", "--no-recurse-submodules", "--", "origin", recipe.commit],
                timeout=GIT_FETCH_TIMEOUT, env_extra=_NO_LAZY,
            )
            used = True
            if not self._has_history_commit(bare, recipe.commit):
                raise FetchError("the fetched history does not hold the pinned commit (or is shallow)", code="raw.fetch.git")
        grown = max(0, _tree_bytes(bare) - before)
        index: HistoryIndex | None = None
        digest = ""
        try:  # the row is written even when the index cannot be computed: the network was used
            index = self._compute_history_index(recipe, bare)
            data = index.to_bytes()
            path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_bytes(path, data)
            self._history_cache[(recipe.repo, recipe.commit)] = index
            digest = sha256_hex(data)
        finally:
            if used:
                row: dict[str, Any] = {
                    "kind": "git", "repo": recipe.repo, "commit": recipe.commit, "mode": HISTORY_MODE, "filter": "blob:none",
                    "store": str(bare.relative_to(self.cache_dir)), "bytes": grown, "retrieved_at": self._stamp(),
                    "consent": self.consent,
                }  # fmt: skip
                if index is not None:
                    row.update(
                        tree=index.tree, commits=index.history_commits, entries=len(index.rows),
                        index=str(path.relative_to(self.cache_dir)), index_sha256=digest,
                    )  # fmt: skip
                else:
                    row["index"] = None
                self.log.append(row)
        assert index is not None
        return HistoryResult(recipe, bare, path, index, digest, used, True, grown)

    def _compute_history_index(self, recipe: Recipe, bare: Path) -> HistoryIndex:
        """The index of the pinned tree from the history store. Offline: ``GIT_NO_LAZY_FETCH`` and no blob is read."""
        assert recipe.repo is not None and recipe.commit is not None
        commit = recipe.commit
        env = _NO_LAZY
        tree_id = self._run_git(["-C", str(bare), "rev-parse", "--verify", f"{commit}^{{tree}}"], env_extra=env).decode("ascii", "replace").strip()
        if _HEX40.fullmatch(tree_id) is None:
            raise FetchError("git returned an unexpected tree id", code="raw.fetch.git")
        tree, skipped = parse_plain_ls_tree(
            self._run_git(["-C", str(bare), "ls-tree", "-r", "-z", "--full-tree", commit], timeout=600.0, env_extra=env)
        )
        log = self._run_git(
            ["-C", str(bare), "log", "--format=%x01%H %P %ct", "--raw", "-z", "--no-renames", "--no-ext-diff", "--root", "-m",
             "--abbrev=40", commit, "--"],
            timeout=GIT_FETCH_TIMEOUT, env_extra=env,
        )  # fmt: skip
        walked = self._run_git(["-C", str(bare), "rev-list", "--count", commit, "--"], env_extra=env).decode("ascii", "replace").strip()
        best = introducing_commits(parse_history_log(log), tree)
        return build_index(
            recipe.repo, commit, tree_id, tree, best, history_commits=int(walked) if walked.isdigit() else None, skipped_paths=skipped
        )

    def _fetch_http(self, recipe: Recipe) -> FetchResult:
        target = recipe.cache_path(self.cache_dir)
        purged = read_tombstones(self.cache_dir, self.limits) if self.cache_dir.is_dir() else frozenset()
        if recipe.sha256 is not None and recipe.sha256 in purged:  # never downloaded again, never contacted (D-46)
            raise TombstonedDownloadError(f"{recipe.origin_label()} was purged from this cache; it is not fetched again")
        if target.is_file():
            sha256, md5, size = _digests(target)
            self._check_digests(recipe, sha256, md5, size, where="the cached file")
            return FetchResult(recipe, target, False, sha256=sha256, md5=md5, bytes=size, verified=_verified(recipe),
                               retrieved_at=self.recorded_retrieval(target, sha256))  # fmt: skip
        self._require_network(recipe.host, f"downloading {recipe.origin_label()}")
        with self._write_lock():  # G6a: one download per cache at a time; a concurrent one refuses clearly
            if target.is_file():  # another process downloaded it meanwhile
                sha256, md5, size = _digests(target)
                self._check_digests(recipe, sha256, md5, size, where="the cached file")
                return FetchResult(recipe, target, False, sha256=sha256, md5=md5, bytes=size, verified=_verified(recipe))
            # ultra raw-withhold #8: a purge --cache that applied between the read above and this lock is honoured
            purged = read_tombstones(self.cache_dir, self.limits) if self.cache_dir.is_dir() else frozenset()
            if recipe.sha256 is not None and recipe.sha256 in purged:
                raise TombstonedDownloadError(f"{recipe.origin_label()} was purged from this cache; it is not fetched again")
            return self._download(recipe, target, purged)

    def _download(self, recipe: Recipe, target: Path, purged: frozenset[str]) -> FetchResult:
        if recipe.size is not None and recipe.size >= LARGE_DOWNLOAD_BYTES and not self.large_download_consent:
            raise LargeDownloadRefusedError(
                f"{recipe.file or recipe.url} from {recipe.host} is {recipe.size} bytes; "
                "a large download needs the explicit consent of U-07 (--i-consent-to-large-download)"
            )
        if self._transport is None:
            self._transport = UrllibTransport()
        cap = self.limits.max_artefact_bytes if recipe.size is None else min(self.limits.max_artefact_bytes, recipe.size)
        unredirected: dict[str, str] = {}
        if recipe.token_env and recipe.token_host == recipe.host:
            token = self._env.get(recipe.token_env)
            if token:
                unredirected["Authorization"] = f"Bearer {token}"
        response = self._transport.open(
            recipe.download_url,
            headers={"User-Agent": "agentprov-fetch", "Accept": "*/*"},
            unredirected=unredirected,
            timeout=self.timeout,
            allowed_hosts=recipe.allowed_hosts,
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(f".{target.name}.part-{os.getpid()}")
        h_sha, h_md5 = hashlib.sha256(), hashlib.md5(usedforsecurity=False)  # MD5 is Zenodo's published transport check
        count = 0
        try:
            if response.status != 200:
                raise FetchError(f"the server answered HTTP {response.status}", code="raw.fetch.http_status")
            declared = response.headers.get("Content-Length")
            if declared and declared.isdigit():
                if int(declared) > cap:
                    raise FetchError("the announced size exceeds the allowed size", code="ingest.size.file")
                if int(declared) >= LARGE_DOWNLOAD_BYTES and not self.large_download_consent:
                    raise LargeDownloadRefusedError(
                        f"{recipe.file or recipe.url} from {recipe.host} is {declared} bytes; "
                        "a large download needs the explicit consent of U-07 (--i-consent-to-large-download)"
                    )
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
            with os.fdopen(fd, "wb") as out:
                while chunk := response.read(_CHUNK):
                    count += len(chunk)
                    if count > cap:
                        raise FetchError("the download exceeds the allowed size", code="ingest.size.file")
                    if count >= LARGE_DOWNLOAD_BYTES and not self.large_download_consent:  # unsized and unannounced
                        raise LargeDownloadRefusedError(
                            f"{recipe.file or recipe.url} from {recipe.host} reached {count} bytes without a pinned or "
                            "announced size; a large download needs the explicit consent of U-07 (--i-consent-to-large-download)"
                        )
                    h_sha.update(chunk)
                    h_md5.update(chunk)
                    out.write(chunk)
                out.flush()
                os.fsync(out.fileno())
            self._check_digests(recipe, h_sha.hexdigest(), h_md5.hexdigest(), count, where="the download")
            if h_sha.hexdigest() in purged:  # an unpinned (MD5-only) download of a purged file
                raise TombstonedDownloadError(f"{recipe.origin_label()} was purged from this cache; it is not kept")
            # ultra raw-withhold #7: the row first, then the publish. A failed append publishes nothing (a published file
            # without its row was taken as recorded by every later run); a failed publish leaves the row of a real
            # retrieval whose bytes are not cached, which recorded_retrieval never reads (it needs the cached file).
            row = self._http_row(recipe, target, h_sha.hexdigest(), h_md5.hexdigest(), count)
            self.log.append(row)
            os.chmod(tmp, 0o444)
            os.replace(tmp, target)
            _fsync_dir(target.parent)
        except BaseException:
            with contextlib.suppress(FileNotFoundError):
                tmp.unlink()
            raise
        finally:
            response.close()
        return FetchResult(
            recipe, target, True, sha256=h_sha.hexdigest(), md5=h_md5.hexdigest(), bytes=count, verified=_verified(recipe),
            problems=() if recipe.sha256 else ("no sha256 is pinned: pin this value in the profile",),
            retrieved_at=row["retrieved_at"],
        )  # fmt: skip

    def recorded_retrieval(self, target: Path, sha256: str) -> str | None:
        """When the cached file ``target`` with ``sha256`` was retrieved: the ``retrieved_at`` of the last acquisition row
        that recorded these bytes at that cache path (D-455), else ``None``. Nothing is inferred from file times."""
        record = target.relative_to(self.cache_dir).as_posix()
        stamps = [row["retrieved_at"] for row in self.log.rows()
                  if row.get("record") == record and row.get("sha256") == sha256
                  and isinstance(row.get("retrieved_at"), str) and RETRIEVED_AT.fullmatch(row["retrieved_at"])]  # fmt: skip
        return stamps[-1] if stamps else None

    @staticmethod
    def _check_digests(recipe: Recipe, sha256: str, md5: str, size: int, *, where: str) -> None:
        if recipe.size is not None and size != recipe.size:
            raise DigestMismatchError(f"{where} has {size} bytes, the pin says {recipe.size}")
        if recipe.md5 is not None and md5 != recipe.md5:
            raise DigestMismatchError(f"{where} does not match the pinned MD5")
        if recipe.sha256 is not None and sha256 != recipe.sha256:
            raise DigestMismatchError(f"{where} does not match the pinned SHA-256")

    def _http_row(self, recipe: Recipe, target: Path, sha256: str, md5: str, size: int) -> dict[str, Any]:
        row: dict[str, Any] = {
            "kind": recipe.kind, "file": recipe.file, "url": recipe.download_url, "bytes": size, "md5": md5, "sha256": sha256,
            "verified": _verified(recipe), "retrieved_at": self._stamp(), "consent": self.consent,
            "record": target.relative_to(self.cache_dir).as_posix(),
        }  # fmt: skip
        if recipe.kind == "zenodo":
            row["doi"] = recipe.doi
            row["md5_published"] = recipe.md5 is not None
        elif recipe.kind == "hf":
            row["repo"], row["revision"] = recipe.repo, recipe.revision
        return {k: v for k, v in row.items() if v is not None}


def _verified(recipe: Recipe) -> str:
    return "+".join(n for n, v in (("size", recipe.size), ("md5", recipe.md5), ("sha256", recipe.sha256)) if v is not None)


def _tree_bytes(root: Path) -> int:
    """The total size of the files under ``root`` (0 when it does not exist): what a fetch added to a store."""
    total = 0
    for base, _dirs, names in os.walk(root):
        for name in names:
            with contextlib.suppress(OSError):
                total += os.lstat(os.path.join(base, name)).st_size
    return total


def _read_exact(stream: IO[bytes], size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = stream.read(min(remaining, _CHUNK))
        if not chunk:
            raise FetchError("git cat-file ended early", code="raw.fetch.git")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _digests(path: Path) -> tuple[str, str, int]:
    sha, md5 = hashlib.sha256(), hashlib.md5(usedforsecurity=False)
    size = 0
    with open(path, "rb") as fh:
        while chunk := fh.read(_CHUNK):
            size += len(chunk)
            sha.update(chunk)
            md5.update(chunk)
    return sha.hexdigest(), md5.hexdigest(), size
