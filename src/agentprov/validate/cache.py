"""The tier-4 round-trip result cache (D8 tier 4; proposal D-550, prov-perf; ``docs/reports/prov-perf/cache-design.md``).

The PROV-O round trip (:mod:`agentprov.validate.roundtrip`, the ``pv.roundtrip.*`` checks) is 65-81 % of the pipeline's
CPU and most of its memory. Its outcome is a pure function of the PROV-JSON bytes, the code that runs it and the
libraries it calls. The other tier-4 checks (structure, constraints, linkage, profiles) also read the AER and the SEM
documents, are cheap, and are never cached. This module keeps completed round trips, so a document whose inputs are
unchanged is never round-tripped twice: re-validation, ``recompute``, ``verify --level rederive`` and post-checks reuse
the outcome of the first validation.

**Key.** The document's sha256 and the *context*: the sha256 of every ``agentprov`` source file (it covers the
validation stage's ``engine_code_sha256`` and the ``prov`` engine and serialiser code the round trip calls), the name,
version and file digest of each library in :data:`LIBRARIES`, the Python build, and the tier-4 options of the round
trip. Any change is a miss. An entry lives at ``<root>/<context digest>/<doc[:2]>/<doc>.json``.

**Value.** The round-trip outcomes exactly as :func:`agentprov.validate.roundtrip.check` returned them (statuses, every
finding, reasons, truncation counts), with the full context and the digest of the outcomes. An entry is used only when
it parses, its context equals this process's, it names the requested document, its digest matches and every outcome
has the expected shape; anything else is a miss (the file is removed), never an error.

**What is stored.** A completed round trip only (:func:`storable`): never a ``skipped`` outcome and never a
``pv.roundtrip.load`` finding, because a library failure (``MemoryError``, ``RecursionError``, an exception from the
environment) need not recur.

**Where.** ``$AGENTPROV_HOME/cache/tier4`` by default: local, outside every corpus and the repository, never shipped.
Writes go to a unique temporary name beside the entry and are renamed into place (atomic under concurrent writers).
The size is bounded (:data:`DEFAULT_MAX_BYTES`): :meth:`DiskCache.evict` removes the least recently used entries.

**Who reads it.** T1 workers cannot read ``$AGENTPROV_HOME`` (G.4.4), so the parent does every read and write. In
process, :class:`DiskCache` is the ``fidelity`` handle of :func:`~agentprov.validate.prov.validate_prov`. A job gets a
:class:`JobFidelity`: the parent's prefetched entry for the document it expects (a *hint*, used only when the bytes
the job validates have that digest and the job's context is the hint's), and it hands back what it computed for the
parent to store (:meth:`DiskCache.store_frame`).
"""

from __future__ import annotations

import contextlib
import functools
import hashlib
import os
import platform
import secrets
import sys
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path
from typing import Any, Final, Protocol

from agentprov.io.canonical import jcs_bytes, sha256_hex
from agentprov.validate.tiers import CheckOutcome, Finding

__all__ = ["CACHE_FORMAT", "DEFAULT_MAX_BYTES", "LIBRARIES", "CacheStats", "DiskCache", "Fidelity", "JobFidelity",
           "context", "context_digest", "default_root", "from_json", "storable"]

CACHE_FORMAT: Final = "agentprov-tier4-cache/1"
#: The round trip's check ids, in the order :func:`agentprov.validate.roundtrip.check` returns them.
ROUNDTRIP_IDS: Final = ("pv.roundtrip.model_equality", "pv.roundtrip.graphs", "pv.roundtrip.completeness",
                        "pv.roundtrip.datatypes", "pv.roundtrip.unqualified_layer")
#: The distributions the round trip runs (``prov`` and ``rdflib``) and those they may load; absent ones are recorded so.
LIBRARIES: Final = ("prov", "rdflib", "pyparsing", "isodate", "lxml", "python-dateutil", "six")
#: Library files that hold code (data and tests shipped inside a wheel do not decide an outcome).
_CODE_SUFFIXES: Final = (".py", ".so", ".pyd", ".dylib", ".dll", ".pth")
_PACKAGE_SUFFIXES: Final = (".py", ".toml", ".json", ".ttl")
_PACKAGE_ROOT: Final = Path(__file__).resolve().parents[1]
#: The default bound on the cache's size (entries are about 1-2 KB; a full round of every corpus is far below it).
DEFAULT_MAX_BYTES: Final = 2 * 1024**3
#: The largest entry written or read (a round trip keeps at most MAX_FINDINGS findings per check).
MAX_ENTRY_BYTES: Final = 8 * 1024**2
_STATUSES: Final = frozenset(("pass", "fail", "skipped", "not_applicable"))
_TMP: Final = ".tmp-"


# ============================================================================================================ context
@functools.cache
def context() -> dict[str, Any]:
    """Everything besides the document that can change a round-trip outcome (computed once per process, about 0.1 s).

    The code digest covers every ``agentprov`` source file, so it moves with the validation stage digest
    (``validate/``, ``aer/validate.py``, ``aer/accounting.py``, ``sem/validate.py``), the ``prov`` engine digest (whose
    ``prov/serialise/nquads.py`` the round trip calls), the vocabulary (``vocab/``, ``prov/vocab``) and the strict
    loader; a change anywhere is a miss (safe, if sometimes wasteful)."""
    from agentprov.prov.vocab import VOCAB_VERSION
    from agentprov.validate.roundtrip import SURROGATE
    from agentprov.validate.tiers import MAX_FINDINGS

    return {
        "agentprov_code_sha256": _package_digest(),
        "libraries": {name: _library(name) for name in LIBRARIES},
        "options": {"max_findings": MAX_FINDINGS, "roundtrip": True, "scope": "pv.roundtrip", "surrogate": SURROGATE},
        "python": {"cache_tag": str(sys.implementation.cache_tag), "implementation": platform.python_implementation(),
                   "machine": platform.machine(), "version": sys.version},
        "validation_code_sha256": _package_digest(("validate/", "aer/validate.py", "aer/accounting.py", "sem/validate.py")),
        "vocabulary": {"version": VOCAB_VERSION, "sha256": _package_digest(("vocab/", "prov/vocab"))},
    }


@functools.cache
def context_digest() -> str:
    return sha256_hex(jcs_bytes({"format": CACHE_FORMAT, "context": context()}))


def _package_digest(prefixes: Sequence[str] = ()) -> str:
    """``sha256(JCS([[relpath, sha256(file)], ...]))`` over the package's source files (under ``prefixes`` when given),
    CRLF normalised, as the stage ``code_sha256`` does."""
    entries: list[list[str]] = []
    for path in sorted(p for p in _PACKAGE_ROOT.rglob("*") if p.is_file()):
        rel = path.relative_to(_PACKAGE_ROOT).as_posix()
        if path.suffix not in _PACKAGE_SUFFIXES or "__pycache__" in rel:
            continue
        if prefixes and not any(rel == p or rel.startswith(p) for p in prefixes):
            continue
        entries.append([rel, sha256_hex(path.read_bytes().replace(b"\r\n", b"\n"))])
    return sha256_hex(jcs_bytes(entries))


def _library(name: str) -> dict[str, str]:
    try:
        dist = metadata.distribution(name)
    except metadata.PackageNotFoundError:
        return {"version": "absent"}
    digest = hashlib.sha256()
    for file in sorted(dist.files or (), key=str):
        if not str(file).endswith(_CODE_SUFFIXES):
            continue
        try:
            data = Path(str(file.locate())).read_bytes()
        except OSError:
            data = b"\x00missing"
        digest.update(f"{file}\x00{len(data)}\x00".encode("utf-8", "surrogateescape"))
        digest.update(hashlib.sha256(data).digest())
    return {"sha256": digest.hexdigest(), "version": str(dist.version)}


# ============================================================================================================ outcomes
def storable(outcomes: Sequence[CheckOutcome]) -> bool:
    """A completed round trip: the expected checks in order, none skipped, no library failure (module docstring)."""
    if tuple(o.id for o in outcomes) != ROUNDTRIP_IDS:
        return False
    return not any(o.status == "skipped" or any(f.code == "pv.roundtrip.load" for f in o.findings) for o in outcomes)


def to_json(outcomes: Sequence[CheckOutcome]) -> list[dict[str, Any]]:
    return [o.as_json() for o in outcomes]


def from_json(data: Any) -> list[CheckOutcome] | None:
    """The outcomes of :func:`to_json` back, exactly; ``None`` for anything of another shape."""
    if not isinstance(data, list):
        return None
    out: list[CheckOutcome] = []
    for item in data:
        if not isinstance(item, dict) or set(item) - {"check", "status", "findings", "reason", "truncated"}:
            return None
        check, status, findings = item.get("check"), item.get("status"), item.get("findings")
        reason, truncated = item.get("reason", ""), item.get("truncated", 0)
        if not (isinstance(check, str) and status in _STATUSES and isinstance(findings, list)
                and isinstance(reason, str) and type(truncated) is int and truncated >= 0):
            return None
        if ("reason" in item and not reason) or ("truncated" in item and not truncated):
            return None  # as_json() omits an empty reason and a zero count
        parsed: list[Finding] = []
        for f in findings:
            if (not isinstance(f, dict) or set(f) != {"code", "detail", "where"}
                    or not all(isinstance(v, str) for v in f.values())):
                return None
            parsed.append(Finding(f["code"], f["where"], f["detail"]))
        out.append(CheckOutcome(check, status, tuple(parsed), reason=reason, truncated=truncated))
    return out if storable(out) else None


def _hint(doc_sha256: str, outcomes: Sequence[CheckOutcome]) -> dict[str, Any]:
    """The part of an entry a job needs (and the round-trip frame a job returns)."""
    body = to_json(outcomes)
    return {"context_sha256": context_digest(), "doc_sha256": doc_sha256, "outcomes": body,
            "outcomes_sha256": sha256_hex(jcs_bytes(body))}


def _check_hint(data: Any, doc_sha256: str | None) -> tuple[str, list[CheckOutcome]] | None:
    """``(doc digest, outcomes)`` of a hint or frame made under this process's context, else ``None``."""
    if not isinstance(data, dict) or data.get("context_sha256") != context_digest():
        return None
    doc, body = data.get("doc_sha256"), data.get("outcomes")
    if not isinstance(doc, str) or len(doc) != 64 or (doc_sha256 is not None and doc != doc_sha256):
        return None
    try:
        if data.get("outcomes_sha256") != sha256_hex(jcs_bytes(body)):
            return None
    except Exception:  # a value JCS cannot represent
        return None
    outcomes = from_json(body)
    return None if outcomes is None else (doc, outcomes)


# ============================================================================================================ handles
class Fidelity(Protocol):
    """What :func:`~agentprov.validate.prov.validate_prov` asks of a cache handle."""

    def lookup(self, prov_json: bytes) -> list[CheckOutcome] | None: ...

    def store(self, prov_json: bytes, outcomes: Sequence[CheckOutcome]) -> None: ...


@dataclass
class CacheStats:
    """Counters of one handle (diagnostics only: they never enter a report, a row or a digest)."""

    hits: int = 0
    misses: int = 0
    stored: int = 0
    rejected: int = 0  # entries present but unusable (corrupt, partial, other shape): removed, counted as misses
    unstorable: int = 0  # round trips that did not complete (never stored)
    audited: int = 0  # audit mode: entries compared with a fresh round trip
    audit_mismatch: int = 0
    errors: int = 0  # I/O errors on the cache (never raised)

    def as_json(self) -> dict[str, int]:
        return {k: int(v) for k, v in sorted(vars(self).items())}

    def add(self, other: CacheStats) -> None:
        for k, v in vars(other).items():
            setattr(self, k, getattr(self, k) + v)


class DiskCache:
    """The parent's cache over a directory (module docstring). ``audit=True`` never serves an entry: every document is
    round-tripped, an existing entry is compared with the fresh outcome (a mismatch is counted and the entry replaced).
    """

    def __init__(self, root: Path | None = None, *, max_bytes: int = DEFAULT_MAX_BYTES, audit: bool = False) -> None:
        self.root = Path(root) if root is not None else default_root()
        self.max_bytes = max_bytes
        self.audit = audit
        self.stats = CacheStats()

    # paths ----------------------------------------------------------------------------------------------------------
    def _dir(self) -> Path:
        return self.root / context_digest()

    def path_for(self, doc_sha256: str) -> Path:
        return self._dir() / doc_sha256[:2] / f"{doc_sha256}.json"

    # reads ----------------------------------------------------------------------------------------------------------
    def _read(self, doc_sha256: str) -> list[CheckOutcome] | None:
        path = self.path_for(doc_sha256)
        try:
            with open(path, "rb") as fh:
                data = fh.read(MAX_ENTRY_BYTES + 1)
        except FileNotFoundError:
            return None
        except OSError:
            self.stats.errors += 1
            return None
        outcomes = self._parse(data, doc_sha256)
        if outcomes is None:
            self.stats.rejected += 1
            with contextlib.suppress(OSError):
                path.unlink()
            return None
        with contextlib.suppress(OSError):
            os.utime(path)  # least recently used = oldest mtime (evict)
        return outcomes

    @staticmethod
    def _parse(data: bytes, doc_sha256: str) -> list[CheckOutcome] | None:
        if len(data) > MAX_ENTRY_BYTES:
            return None
        from agentprov.ingest.loaders import strict_json_loads

        try:
            entry = strict_json_loads(data)
        except Exception:
            return None
        if (not isinstance(entry, dict) or entry.get("format") != CACHE_FORMAT or entry.get("context") != context()
                or entry.get("doc_sha256") != doc_sha256):
            return None
        checked = _check_hint(entry, doc_sha256)
        return None if checked is None else checked[1]

    def lookup(self, prov_json: bytes) -> list[CheckOutcome] | None:
        if self.audit:
            return None
        outcomes = self._read(sha256_hex(prov_json))
        if outcomes is None:
            self.stats.misses += 1
        else:
            self.stats.hits += 1
        return outcomes

    def hint(self, doc_sha256: str) -> bytes | None:
        """The JCS bytes of a job hint for the document ``doc_sha256``, from a usable entry (``None`` on a miss)."""
        if self.audit:
            return None
        outcomes = self._read(doc_sha256)
        if outcomes is None:
            self.stats.misses += 1
            return None
        self.stats.hits += 1
        return jcs_bytes(_hint(doc_sha256, outcomes))

    # writes ---------------------------------------------------------------------------------------------------------
    def store(self, prov_json: bytes, outcomes: Sequence[CheckOutcome]) -> None:
        self._store(sha256_hex(prov_json), outcomes)

    def store_frame(self, prov_json: bytes, frame: Any) -> None:
        """Store the round-trip frame a job returned for ``prov_json`` (ignored unless made under this context for
        exactly these bytes)."""
        doc = sha256_hex(prov_json)
        checked = _check_hint(frame, doc)
        if checked is None:
            self.stats.unstorable += 1
            return
        self._store(doc, checked[1])

    def _store(self, doc_sha256: str, outcomes: Sequence[CheckOutcome]) -> None:
        if not storable(outcomes):
            self.stats.unstorable += 1
            return
        if self.audit:
            previous = self._read(doc_sha256)
            if previous is not None:
                self.stats.audited += 1
                if list(previous) == list(outcomes):
                    return
                self.stats.audit_mismatch += 1
        try:
            data = jcs_bytes({"format": CACHE_FORMAT, "context": context(), **_hint(doc_sha256, outcomes),
                              "written": int(time.time())})
        except Exception:  # a finding JCS cannot represent (a lone surrogate): not cached
            self.stats.unstorable += 1
            return
        if len(data) > MAX_ENTRY_BYTES:
            self.stats.unstorable += 1
            return
        path = self.path_for(doc_sha256)
        tmp = path.with_name(f"{path.name}{_TMP}{os.getpid()}-{secrets.token_hex(6)}")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(tmp, "xb") as fh:
                fh.write(data)
            os.replace(tmp, path)
        except OSError:
            self.stats.errors += 1
            with contextlib.suppress(OSError):
                tmp.unlink()
            return
        self.stats.stored += 1

    # eviction -------------------------------------------------------------------------------------------------------
    def evict(self, max_bytes: int | None = None, *, stale_tmp_seconds: float = 3600.0) -> dict[str, int]:
        """Bound the cache to ``max_bytes`` (default the handle's): remove the least recently used entries (any
        context) until it fits, and temporary files older than ``stale_tmp_seconds``. Never raises."""
        limit = self.max_bytes if max_bytes is None else max_bytes
        files: list[tuple[float, int, str]] = []
        removed = total = 0
        now = time.time()
        for path, st in _walk(self.root):
            if _TMP in path.rsplit("/", 1)[-1]:
                if now - st.st_mtime > stale_tmp_seconds:
                    with contextlib.suppress(OSError):
                        os.unlink(path)
                        removed += 1
                continue
            files.append((st.st_mtime, st.st_size, path))
            total += st.st_size
        kept = total
        if total > limit:
            for _mtime, size, path in sorted(files):
                if kept <= limit:
                    break
                with contextlib.suppress(OSError):
                    os.unlink(path)
                    removed += 1
                    kept -= size
        for directory in _dirs(self.root):  # empty shard and context directories
            with contextlib.suppress(OSError):
                os.rmdir(directory)
        return {"bytes_before": total, "bytes_after": kept, "removed": removed}


def _walk(root: Path) -> Iterable[tuple[str, os.stat_result]]:
    stack = [str(root)]
    while stack:
        try:
            with os.scandir(stack.pop()) as it:
                for entry in it:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                        elif entry.is_file(follow_symlinks=False):
                            yield entry.path, entry.stat(follow_symlinks=False)
                    except OSError:
                        continue
        except OSError:
            continue


def _dirs(root: Path) -> list[str]:
    out: list[str] = []
    with contextlib.suppress(OSError):
        for context_dir in os.scandir(root):
            if context_dir.is_dir(follow_symlinks=False):
                with contextlib.suppress(OSError):
                    out += [e.path for e in os.scandir(context_dir.path) if e.is_dir(follow_symlinks=False)]
                out.append(context_dir.path)
    return out


@dataclass
class JobFidelity:
    """The handle of a T1 job (no file access): ``hint`` is the parent's entry for the document it expects (the bytes
    of :meth:`DiskCache.hint`, re-checked here); ``computed`` collects a completed round trip for the parent to store
    (:meth:`frame`)."""

    hint: bytes | None = None
    collect: bool = True
    computed: dict[str, Any] | None = field(default=None, init=False)
    used: bool = field(default=False, init=False)

    def lookup(self, prov_json: bytes) -> list[CheckOutcome] | None:
        if self.hint is None:
            return None
        from agentprov.ingest.loaders import strict_json_loads

        try:
            data = strict_json_loads(self.hint)
        except Exception:
            return None
        checked = _check_hint(data, sha256_hex(prov_json))
        if checked is None:
            return None
        self.used = True
        return checked[1]

    def store(self, prov_json: bytes, outcomes: Sequence[CheckOutcome]) -> None:
        if self.collect and storable(outcomes):
            self.computed = _hint(sha256_hex(prov_json), outcomes)

    def frame(self) -> dict[str, Any] | None:
        """``{"fidelity": ...}`` for the job to emit when it computed a storable round trip, else ``None``."""
        return None if self.computed is None else {"fidelity": self.computed}


def default_root(environ: Mapping[str, str] | None = None) -> Path:
    """``$AGENTPROV_HOME/cache/tier4`` (``~/.agentprov`` by default), absolute."""
    raw = (os.environ if environ is None else environ).get("AGENTPROV_HOME")
    home = Path(raw).expanduser() if raw else Path.home() / ".agentprov"
    return Path(os.path.abspath(home)) / "cache" / "tier4"
