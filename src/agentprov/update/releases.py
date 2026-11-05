"""The newest release of the public repository (D-1065): the GitHub releases API, read as untrusted data.

One request, ``GET https://api.github.com/repos/nickjones39/AgentPROV/releases?per_page=20`` (no key, no cookie), through
the core's fetch transport (``agentprov.raw.fetch``: TLS verified, redirects only to an https host on the allow-list,
which is ``api.github.com`` alone here), HTTP 200 and at most :data:`MAX_API_BYTES`. The answer is parsed strictly
(``agentprov.ingest``) and kept only where it matches: a tag ``vX.Y.Z``, ``draft`` and ``prerelease`` false, a
``published_at`` in UTC, asset names of a closed alphabet and sizes in range. An asset's download address is never
taken from the answer: it is built from the tag and the name (``https://github.com/<repo>/releases/download/<tag>/<name>``)
and an answer that names another one is refused. The release notes are plain text, escaped for display
(:func:`agentprov.ingest.quote.escape_untrusted`) and cut at :data:`NOTES_MAX_CHARS`.

A download goes to ``github.com`` and may be redirected only to GitHub's asset hosts (:data:`DOWNLOAD_HOSTS`).

The last check is cached in ``$AGENTPROV_HOME/update/check.json`` with the UTC time it was made; ``check --if-stale``
fetches at most once a day in this machine's local time, as ``prices refresh --if-stale`` (D-1062).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import platform as _platform
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final
from urllib.parse import urlsplit

from agentprov.errors import AgentProvError, IngestError
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads
from agentprov.ingest.quote import escape_untrusted

__all__ = [
    "API_HOST", "API_URL", "CACHE_FORMAT", "CHECK_FORMAT", "DOWNLOAD_HOSTS", "PLATFORMS", "REPOSITORY", "Asset",
    "Release", "UpdateError", "bundle_asset_name", "check_document", "check_due", "download", "fetch_releases",
    "latest_release", "parse_releases", "platform_label", "read_cache", "update_dir", "version_key", "write_cache",
]  # fmt: skip

#: The public repository whose releases are the updates (the development repository is private).
REPOSITORY: Final = "nickjones39/AgentPROV"
API_HOST: Final = "api.github.com"
API_URL: Final = f"https://{API_HOST}/repos/{REPOSITORY}/releases?per_page=20"
#: A release download starts at github.com and is redirected to GitHub's asset hosts; nowhere else.
DOWNLOAD_HOSTS: Final = frozenset({"github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com"})
RELEASE_PAGE: Final = f"https://github.com/{REPOSITORY}/releases/tag/"
DOWNLOAD_BASE: Final = f"https://github.com/{REPOSITORY}/releases/download/"
CHECK_FORMAT: Final = "agentprov-update-check/0.1"
CACHE_FORMAT: Final = "agentprov-update-cache/0.1"
MAX_API_BYTES: Final = 8 * 1024 * 1024
MAX_RELEASES: Final = 100
MAX_ASSETS: Final = 200
#: the largest asset accepted (a bundle is a few hundred MB)
MAX_ASSET_BYTES: Final = 2 * 1024 * 1024 * 1024
NOTES_MAX_CHARS: Final = 8000
FETCH_TIMEOUT_S: Final = 30.0
DOWNLOAD_TIMEOUT_S: Final = 120.0
CHECKSUM_ASSET: Final = "SHA256SUMS"
SIGNATURE_ASSET: Final = "SHA256SUMS.sig"
#: the bundles of the release (gui/tools/build_bundle.py, named as the release publishes them)
PLATFORMS: Final = ("macos-arm64", "macos-x86_64", "windows-x64", "windows-arm64", "linux-x86_64", "linux-aarch64")
_EXT: Final = {"macos": ".dmg", "windows": ".zip", "linux": ".tar.gz"}
_TAG: Final = re.compile(r"v(\d{1,6}\.\d{1,6}\.\d{1,6})")
_ASSET_NAME: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,199}")
_UTC: Final = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
#: the PEP 440 subset the project's versions use: X.Y.Z, a pre-release, a post-release, a dev release, a local label
_VERSION: Final = re.compile(r"(\d{1,6})\.(\d{1,6})\.(\d{1,6})(?:(a|b|rc)(\d{1,6}))?(?:\.post(\d{1,6}))?"
                             r"(?:\.dev(\d{1,6}))?(?:\+[A-Za-z0-9.]{1,64})?")
_PRE: Final = {"a": 0, "b": 1, "rc": 2}
_LIMITS: Final = IngestLimits().replace(max_json_bytes=MAX_API_BYTES, max_json_depth=16)


class UpdateError(AgentProvError):
    """An update answer, file or step that cannot be used (``update.*``; the message names the problem, never data).
    Exit 1."""

    code = "update.invalid"
    exit_code = 1


# --------------------------------------------------------------------------------------------------------------
# Versions and platforms
# --------------------------------------------------------------------------------------------------------------


def version_key(text: object) -> tuple[Any, ...] | None:
    """A sort key in PEP 440 order for the versions the project uses (``0.1.1``, ``0.2.0rc1``, ``0.2.0.dev3``,
    ``0.1.1.post1``, a ``+local`` label ignored); ``None`` for anything else (never guessed)."""
    if not isinstance(text, str):
        return None
    m = _VERSION.fullmatch(text)
    if m is None:
        return None
    release = tuple(int(m.group(i)) for i in (1, 2, 3))
    label, number, post, dev = m.group(4), m.group(5), m.group(6), m.group(7)
    if label is None:  # X.devN sorts before every pre-release of X; X and X.postN after them
        pre = (-1, 0) if post is None and dev is not None else (3, 0)
    else:
        pre = (_PRE[label], int(number))
    return (release, pre, -1 if post is None else int(post), (1, 0) if dev is None else (0, int(dev)))


def platform_label(system: str | None = None, machine: str | None = None) -> str | None:
    """This machine's bundle label (:data:`PLATFORMS`), or ``None`` where no bundle is built."""
    system = sys.platform if system is None else system
    arch = (_platform.machine() if machine is None else machine).lower()
    arm = arch in ("arm64", "aarch64", "armv8", "armv8l")
    x86 = arch in ("x86_64", "amd64", "x64")
    if not (arm or x86):
        return None
    if system == "darwin":
        return "macos-arm64" if arm else "macos-x86_64"
    if system == "win32":
        return "windows-arm64" if arm else "windows-x64"
    if system.startswith("linux"):
        return "linux-aarch64" if arm else "linux-x86_64"
    return None


def bundle_asset_name(label: str) -> str:
    """The release's file for a bundle label: ``AgentPROV-macos-arm64.dmg``, ``AgentPROV-windows-x64.zip``, ..."""
    if label not in PLATFORMS:
        raise UpdateError("not a bundle platform", code="update.platform")
    return f"AgentPROV-{label}{_EXT[label.split('-', 1)[0]]}"


# --------------------------------------------------------------------------------------------------------------
# The releases answer
# --------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Asset:
    name: str
    size: int
    url: str  # built from the tag and the name, never taken from the answer

    def to_json(self) -> dict[str, Any]:
        return {"name": self.name, "size": self.size, "url": self.url}


@dataclass(frozen=True, slots=True)
class Release:
    tag: str
    version: str
    published_at: str | None  # UTC, ``YYYY-MM-DDTHH:MM:SSZ``
    url: str
    notes: str  # escaped for display, at most NOTES_MAX_CHARS plus the truncation marker
    notes_truncated: bool
    assets: tuple[Asset, ...]

    def asset(self, name: str) -> Asset | None:
        return next((a for a in self.assets if a.name == name), None)

    def to_json(self) -> dict[str, Any]:
        return {"tag": self.tag, "version": self.version, "published_at": self.published_at, "url": self.url,
                "notes": self.notes, "notes_truncated": self.notes_truncated,
                "assets": [a.to_json() for a in self.assets]}


def _asset_url(tag: str, name: str) -> str:
    return f"{DOWNLOAD_BASE}{tag}/{name}"


def _release(entry: Mapping[str, Any], *, cached: bool = False) -> Release | None:
    """One release of the answer (or of the cache), or ``None`` when it is not a final release of the project."""
    given_tag = entry.get("tag_name" if not cached else "tag")
    m = _TAG.fullmatch(given_tag) if isinstance(given_tag, str) else None
    if m is None:
        return None
    tag = m.group(0)
    if not cached and (entry.get("draft") is not False or entry.get("prerelease") is not False):
        return None  # a draft, a pre-release, or a release that does not say
    published = entry.get("published_at")
    raw_assets = entry.get("assets")
    if not isinstance(raw_assets, list) or len(raw_assets) > MAX_ASSETS:
        raise UpdateError("the releases answer has a malformed asset list", code="update.response")
    assets: dict[str, Asset] = {}
    for a in raw_assets:
        if not isinstance(a, dict):
            raise UpdateError("the releases answer has a malformed asset", code="update.response")
        name, size = a.get("name"), a.get("size")
        if not isinstance(name, str) or not _ASSET_NAME.fullmatch(name) or ".." in name:
            continue  # an asset this client never asks for
        if not cached and a.get("state", "uploaded") != "uploaded":
            continue
        if type(size) is not int or not 0 <= size <= MAX_ASSET_BYTES:
            raise UpdateError("the releases answer gives an asset size out of range", code="update.response")
        url = _asset_url(tag, name)
        given = a.get("browser_download_url" if not cached else "url")
        if not isinstance(given, str) or given.casefold() != url.casefold():
            raise UpdateError("the releases answer names a download that is not this repository's release file "
                              "(another host or path)", code="update.response.host")
        if name in assets:
            raise UpdateError("the releases answer lists an asset twice", code="update.response")
        assets[name] = Asset(name, size, url)
    body = entry.get("body" if not cached else "notes")
    text = body.replace("\r\n", "\n").replace("\r", "\n") if isinstance(body, str) else ""
    if cached:
        if len(text) > NOTES_MAX_CHARS + 200:
            raise UpdateError("the cached release notes are too long", code="update.cache")
        notes, truncated = escape_untrusted(text), entry.get("notes_truncated") is True
    else:
        notes, truncated = escape_untrusted(text, max_chars=NOTES_MAX_CHARS), len(text) > NOTES_MAX_CHARS
    return Release(tag=tag, version=m.group(1), published_at=published if isinstance(published, str)
                   and _UTC.fullmatch(published) else None, url=RELEASE_PAGE + tag, notes=notes,
                   notes_truncated=truncated, assets=tuple(sorted(assets.values(), key=lambda x: x.name)))


def parse_releases(data: bytes) -> list[Release]:
    """The final releases of a ``/releases`` answer (drafts, pre-releases and tags other than ``vX.Y.Z`` left out).
    A structural defect refuses the whole answer (:class:`UpdateError`)."""
    if len(data) > MAX_API_BYTES:
        raise UpdateError("the releases answer is larger than 8 MiB", code="update.response.size")
    try:
        doc = strict_json_loads(data, _LIMITS)
    except IngestError as exc:
        raise UpdateError(f"the releases answer is not strict JSON ({exc.code})", code="update.response") from None
    if not isinstance(doc, list) or len(doc) > MAX_RELEASES:
        raise UpdateError("the releases answer is not a list of releases", code="update.response")
    out = []
    for entry in doc:
        if not isinstance(entry, dict):
            raise UpdateError("the releases answer holds a non-object", code="update.response")
        release = _release(entry)
        if release is not None:
            out.append(release)
    return out


def latest_release(releases: Sequence[Release]) -> Release | None:
    """The release with the highest version (not the newest by date: a fix of an older line can come later)."""
    keyed = [(version_key(r.version), r) for r in releases]
    usable = [(k, r) for k, r in keyed if k is not None]  # always all: the tag pattern is X.Y.Z
    return max(usable, key=lambda kr: kr[0])[1] if usable else None


def _check_response(response: Any, allowed: frozenset[str]) -> None:
    """HTTP 200 from an https URL on the allow-list (the final URL, after any redirect)."""
    from agentprov.raw.fetch import FetchError

    status = getattr(response, "status", 200)
    if status != 200:
        raise FetchError(f"the server answered HTTP {status}", code="raw.fetch.http_status")
    final = urlsplit(str(getattr(response, "url", "") or ""))
    if final.scheme != "https" or (final.hostname or "").lower() not in allowed:
        raise UpdateError("the answer came from a host that is not on the allow-list", code="update.response.host")


def fetch_releases(transport: Any) -> bytes:
    """GET :data:`API_URL` through ``transport`` (an ``agentprov.raw.fetch.Transport``; the tests pass a fake). The
    caller has checked ``--allow-network``."""
    from agentprov.versions import __version__

    response = transport.open(API_URL, headers={"Accept": "application/vnd.github+json", "X-GitHub-Api-Version":
                                                "2022-11-28", "User-Agent": f"agentprov/{__version__}"},
                              unredirected={}, timeout=FETCH_TIMEOUT_S, allowed_hosts=frozenset({API_HOST}))
    try:
        _check_response(response, frozenset({API_HOST}))
        declared = (getattr(response, "headers", None) or {}).get("Content-Length")
        if declared and str(declared).isdigit() and int(declared) > MAX_API_BYTES:
            raise UpdateError("the releases answer is larger than 8 MiB", code="update.response.size")
        data = response.read(MAX_API_BYTES + 1)
    finally:
        response.close()
    if len(data) > MAX_API_BYTES:
        raise UpdateError("the releases answer is larger than 8 MiB", code="update.response.size")
    return bytes(data)


def download(transport: Any, asset: Asset, target: Path, *, max_bytes: int | None = None) -> str:
    """Stream ``asset`` into ``target`` (written as a ``.part`` sibling, renamed when complete) and return its sha256.
    The size must be the one the release lists, at most ``max_bytes``; nothing else is trusted until the caller has
    checked the digest."""
    from agentprov.versions import __version__

    cap = min(MAX_ASSET_BYTES, max_bytes if max_bytes is not None else MAX_ASSET_BYTES)
    if asset.size > cap:
        raise UpdateError(f"{asset.name} is larger than this client accepts", code="update.download.size")
    if not asset.url.startswith(DOWNLOAD_BASE):
        raise UpdateError("not a release download of the repository", code="update.response.host")
    response = transport.open(asset.url, headers={"Accept": "application/octet-stream",
                                                  "User-Agent": f"agentprov/{__version__}"},
                              unredirected={}, timeout=DOWNLOAD_TIMEOUT_S, allowed_hosts=DOWNLOAD_HOSTS)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.part-{os.getpid()}")
    digest, count = hashlib.sha256(), 0
    try:
        _check_response(response, DOWNLOAD_HOSTS)
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0), 0o600)
        with os.fdopen(fd, "wb") as out:
            while chunk := response.read(1024 * 1024):
                count += len(chunk)
                if count > asset.size:
                    raise UpdateError(f"{asset.name} is longer than the release lists", code="update.download.size")
                digest.update(chunk)
                out.write(chunk)
        if count != asset.size:
            raise UpdateError(f"{asset.name} is shorter than the release lists", code="update.download.size")
        os.replace(tmp, target)
    finally:
        response.close()
        tmp.unlink(missing_ok=True)
    return digest.hexdigest()


# --------------------------------------------------------------------------------------------------------------
# The document and the cache
# --------------------------------------------------------------------------------------------------------------


def update_dir(home: Path) -> Path:
    """``$AGENTPROV_HOME/update``: the cached check, the staged downloads and the install record."""
    return Path(home) / "update"


def utc_text(moment: dt.datetime) -> str:
    return moment.astimezone(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def check_due(checked_at: str | None, now: dt.datetime | None = None) -> bool:
    """"Once a day": true when there is no check, or the last one was made on an earlier day than ``now``, both in this
    machine's local time zone (the user's day, not UTC's; D-1062's rule)."""
    if not isinstance(checked_at, str) or not _UTC.fullmatch(checked_at):
        return True
    written = dt.datetime.fromisoformat(checked_at.replace("Z", "+00:00"))
    current = now if now is not None else dt.datetime.now(dt.UTC)
    return written.astimezone().date() < current.astimezone().date()


def write_cache(home: Path, release: Release | None, checked_at: dt.datetime) -> Path:
    from agentprov.io.replace_retry import atomic_write_bytes_retrying

    path = update_dir(home) / "check.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {"format": CACHE_FORMAT, "repository": REPOSITORY, "checked_at": utc_text(checked_at),
           "release": None if release is None else release.to_json()}
    atomic_write_bytes_retrying(path, json.dumps(doc, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n")
    return path


def read_cache(home: Path) -> tuple[str, Release | None] | None:
    """The last check (its UTC time and the release it found), or ``None`` when there is none or it is not readable
    (the cache is re-validated as the answer was: a damaged file is a missing check, never trusted)."""
    path = update_dir(home) / "check.json"
    try:
        with open(path, "rb") as fh:
            data = fh.read(MAX_API_BYTES + 1)
        doc = strict_json_loads(data.rstrip(b"\n"), _LIMITS)
    except (OSError, IngestError):
        return None
    if not isinstance(doc, dict) or doc.get("format") != CACHE_FORMAT or doc.get("repository") != REPOSITORY:
        return None
    checked = doc.get("checked_at")
    if not isinstance(checked, str) or not _UTC.fullmatch(checked):
        return None
    raw = doc.get("release")
    if raw is None:
        return checked, None
    if not isinstance(raw, dict):
        return None
    try:
        release = _release(raw, cached=True)
    except UpdateError:
        return None
    return (checked, release) if release is not None else None


def check_document(release: Release | None, *, core: str, gui: str | None, label: str | None, checked_at: str | None,
                   fetched: bool, auto_check: bool, due: bool) -> dict[str, Any]:
    """``agentprov update check --format json`` (:data:`CHECK_FORMAT`)."""
    latest = version_key(release.version) if release is not None else None

    def behind(current: str | None) -> bool | None:
        if current is None:
            return None  # not known (no bundle named)
        if latest is None:
            return False  # no release to be behind
        key = version_key(current)
        return None if key is None else bool(key < latest)

    flags = {"core": behind(core), "gui": behind(gui)}
    known = [v for v in flags.values() if v is not None]
    if release is None:
        available: bool | None = False
    else:
        available = any(known) if known else None
    asset = release.asset(bundle_asset_name(label)) if release is not None and label is not None else None
    return {
        "format": CHECK_FORMAT, "repository": REPOSITORY, "checked_at": checked_at, "fetched": fetched,
        "current": {"core": core, "gui": gui}, "latest": release.version if release else None,
        "tag": release.tag if release else None, "update_available": available, "behind": flags,
        "published_at": release.published_at if release else None, "release_url": release.url if release else None,
        "notes": release.notes if release else "", "notes_truncated": bool(release and release.notes_truncated),
        "platform": label, "assets": [asset.to_json()] if asset is not None else [],
        "checksum_asset": _named(release, CHECKSUM_ASSET), "signature_asset": _named(release, SIGNATURE_ASSET),
        "auto_check": auto_check, "check_due": due,
    }  # fmt: skip


def _named(release: Release | None, name: str) -> dict[str, Any] | None:
    asset = release.asset(name) if release is not None else None
    return asset.to_json() if asset is not None else None
