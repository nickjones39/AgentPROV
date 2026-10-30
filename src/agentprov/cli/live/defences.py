"""T0's side of defended live runs (D-670, D-675, D-679; docs/reports/defence-backends/design.md §3.2, §3.7).

The registry is data in the backend harness package (``backends/shared/src/agentprov_backend/defences.toml``). The core
never imports ``agentprov_backend``: T0 reads the repository copy as TOML, checks a run's defence against it and against
the live profile **before** anything is spawned, and checks that the built environment holds the same registry bytes
and the provisioned files the entry pins. The worker validates the registry fully and builds the pipeline.

Refusals (``UnsupportedCapability``, exit 5; the caller formats them): a name that is not in the registry, an entry
the backend does not build, a defence the live profile does not allow (D-677: `agentdojo-live` v3 allows the first set,
D-671; its v1 and v2, and every `autodojo-live` version, allow none), a suite outside the entry's, provisioned files that are missing. A registry that
differs between the repository and the environment is an environment condition (exit 3).

``provision`` copies a provisioned entry's pinned files from the bare fetch cache (``agentprov.raw.fetch``: ``git
ls-tree``/``cat-file`` only, ``GIT_NO_LAZY_FETCH``; never a network access without ``--allow-network``) into
``<env>/agentprov_defences/<id>/`` after checking each file's blob id and sha256. Nothing is copied into the repository.
"""

from __future__ import annotations

import hashlib
import os
import re
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

__all__ = [
    "REGISTRY_FORMAT",
    "REGISTRY_RELPATH",
    "DefenceRefused",
    "Entry",
    "allowed_defences",
    "check_defence",
    "check_environment",
    "installed_registry",
    "load_registry",
    "plan_defence",
    "hf_cache_dir",
    "provision",
    "provision_weights",
    "provisioned_dir",
    "registry_path",
    "registry_values",
    "verify_provisioned",
]

REGISTRY_FORMAT: Final = "agentprov-defence-registry/0.1"
REGISTRY_RELPATH: Final = "backends/shared/src/agentprov_backend/defences.toml"
_ID = re.compile(r"[a-z][a-z0-9_]*")
_HEX40 = re.compile(r"[0-9a-f]{40}")
_HEX64 = re.compile(r"[0-9a-f]{64}")
#: Bound on a provisioned file (defence code, not data).
MAX_PROVISIONED_BYTES: Final = 8 * 1024 * 1024


class DefenceRefused(Exception):
    """A defence the run cannot use; ``lines`` explain why (the caller turns it into ``UnsupportedCapability``)."""

    def __init__(self, what: str, *lines: str) -> None:
        super().__init__(what)
        self.what = what
        self.lines = lines


@dataclass(frozen=True)
class Entry:
    id: str
    backends: tuple[str, ...]
    provider: str
    suites: tuple[str, ...]
    aux_llm: str
    licence: str
    files: tuple[Mapping[str, str], ...] = ()
    repo: str | None = None
    commit: str | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)
    #: pinned model files (D-672): {repo, revision, hosts, files: [{path, sha256, size}]}
    weights: tuple[Mapping[str, Any], ...] = ()
    #: Python modules the entry needs in the environment (``assets.python``; the backend's ``defences`` group)
    python: tuple[str, ...] = ()


def _table(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def registry_path(root: Path) -> Path:
    return root / REGISTRY_RELPATH


def _entry(raw: Any) -> Entry:
    if not isinstance(raw, Mapping) or not isinstance(raw.get("id"), str) or not _ID.fullmatch(raw["id"]):
        raise ValueError("an entry without a valid id")
    backends, suites = raw.get("backends"), raw.get("suites")
    if not (isinstance(backends, list) and all(isinstance(b, str) for b in backends)) or \
            not (isinstance(suites, list) and all(isinstance(s, str) for s in suites)):
        raise ValueError(f"entry {raw['id']}: backends and suites must be lists of names")
    code = _table(raw.get("code"))
    files = _list(code.get("files"))
    for f in files:
        if not (isinstance(f, Mapping) and isinstance(f.get("path"), str) and _HEX40.fullmatch(str(f.get("blob_sha1")))
                and _HEX64.fullmatch(str(f.get("sha256")))):
            raise ValueError(f"entry {raw['id']}: a malformed code file")
        parts = f["path"].split("/")
        if f["path"].startswith("/") or any(p in ("", ".", "..") for p in parts) or "\\" in f["path"]:
            raise ValueError(f"entry {raw['id']}: a code file path is not a relative label")
    licence = _table(raw.get("licence"))
    weights = []
    for w in _list(raw.get("weights")):
        w = _table(w)
        if not (isinstance(w.get("repo"), str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*",
                                                                w["repo"]) and _HEX40.fullmatch(str(w.get("revision")))):
            raise ValueError(f"entry {raw['id']}: a malformed weights table")
        wfiles = []
        for f in _list(w.get("files")):
            f = _table(f)
            parts = str(f.get("path", "")).split("/")
            if not (_HEX64.fullmatch(str(f.get("sha256"))) and isinstance(f.get("size"), int)) \
                    or any(p in ("", ".", "..") for p in parts) or "\\" in str(f.get("path", "")):
                raise ValueError(f"entry {raw['id']}: a malformed weights file")
            wfiles.append(dict(f))
        hosts = [str(h) for h in _list(w.get("hosts"))]
        weights.append({"repo": w["repo"], "revision": w["revision"], "hosts": hosts, "files": wfiles})
    python = tuple(str(m) for m in _list(_table(raw.get("assets")).get("python")))
    return Entry(id=raw["id"], backends=tuple(backends), provider=str(raw.get("provider")), suites=tuple(suites),
                 aux_llm=str(raw.get("aux_llm", "none")), licence=str(licence.get("spdx", "")),
                 files=tuple(dict(f) for f in files), repo=code.get("repo"), commit=code.get("commit"), raw=raw,
                 weights=tuple(weights), python=python)


def load_registry(path: Path) -> dict[str, Entry]:
    """The registry's entries by id (a light check: the worker validates every member)."""
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"the defence registry cannot be read ({type(exc).__name__})") from None
    if data.get("format") != REGISTRY_FORMAT or not isinstance(data.get("defence", []), list):
        raise ValueError("the defence registry has another format")
    out: dict[str, Entry] = {}
    for raw in data.get("defence", []):
        entry = _entry(raw)
        if entry.id in out:
            raise ValueError(f"duplicate defence {entry.id}")
        out[entry.id] = entry
    return out


def registry_values(root: Path) -> tuple[frozenset[str], frozenset[str]]:
    """The ``provider`` and ``aux_llm`` values the repository's registry uses (F-15): what a worker's catalogue may
    report for a defence, since its defences are the registry's entries. Read from the data, never a hand list, so a new
    provider kind (``port``, D-674) is accepted once an entry uses it."""
    entries = load_registry(registry_path(root)).values()
    return frozenset(e.provider for e in entries), frozenset(e.aux_llm for e in entries)


def plan_defence(document: Mapping[str, Any]) -> str | None:
    """The defence a plan document names (``[plan] defence`` or ``defense``); ``None`` for none."""
    plan = _table(document.get("plan"))
    value = plan.get("defence", plan.get("defense"))
    return None if value in (None, "none") else str(value)


def allowed_defences(live: Mapping[str, Any]) -> tuple[str, ...]:
    """The ids the live profile allows (``[family.<family>.live] defences``; absent in profiles v1: none)."""
    value = live.get("defences")
    return tuple(str(v) for v in value) if isinstance(value, list | tuple) else ()


def check_defence(defence: str, *, backend: str, suites: Sequence[str], live: Mapping[str, Any], root: Path,
                  profile_label: str) -> Entry:
    """T0's check before anything is spawned (see the module docstring); raises :class:`DefenceRefused`."""
    try:
        registry = load_registry(registry_path(root))
    except ValueError as exc:
        raise DefenceRefused("the defence registry", str(exc)) from None
    entry = registry.get(defence)
    if entry is None:
        listed = ", ".join(sorted(e for e, v in registry.items() if backend in v.backends)) or "none"
        raise DefenceRefused(f"defence {defence}", f"It is not in the defence registry ({REGISTRY_RELPATH}). The "
                             f"{backend} backend builds: {listed} (D-670, D-671).")
    if backend not in entry.backends:
        raise DefenceRefused(f"defence {defence} for the {backend} backend",
                             f"The registry builds it on: {', '.join(entry.backends)}.")
    if defence not in allowed_defences(live):
        raise DefenceRefused(f"defence {defence} under {profile_label}",
                             f"The live profile {profile_label} allows no such defence (its `defences` list; "
                             "agentdojo-live v3 allows the first set, D-671, D-677).")
    if "*" not in entry.suites:
        outside = [s for s in suites if s not in entry.suites]
        if outside:
            raise DefenceRefused(f"defence {defence} on {', '.join(outside)}",
                                 f"It runs on {', '.join(entry.suites)} only.")
    return entry


def installed_registry(env: Path) -> Path | None:
    """The registry file of the ``agentprov_backend`` installed in ``env`` (``lib/python3.*/site-packages``)."""
    lib = env / "lib"
    if not lib.is_dir():
        return None
    for child in sorted(lib.iterdir()):
        candidate = child / "site-packages" / "agentprov_backend" / "defences.toml"
        if child.name.startswith("python3.") and candidate.is_file() and not candidate.is_symlink():
            return candidate
    return None


def provisioned_dir(env: Path, entry: Entry) -> Path:
    return env / "agentprov_defences" / entry.id


def hf_cache_dir(env: Path) -> Path:
    """The environment's offline Hugging Face hub cache (the worker's ``HF_HUB_CACHE``; D-672)."""
    return env / "agentprov_defences" / "hf"


def _snapshot(env: Path, weights: Mapping[str, Any]) -> Path:
    org, name = str(weights["repo"]).split("/", 1)
    return hf_cache_dir(env) / f"models--{org}--{name}" / "snapshots" / str(weights["revision"])


def _site_packages(env: Path) -> Path | None:
    lib = env / "lib"
    found = sorted(c / "site-packages" for c in lib.iterdir() if c.name.startswith("python3.")) if lib.is_dir() else []
    return found[0] if found else None


def verify_provisioned(env: Path, entry: Entry) -> str | None:
    """Why the entry's provisioned files are not usable in ``env`` (``None``: they are): its pinned code, its Python
    modules (the ``defences`` dependency group) and every pinned weights file, by sha256."""
    site = _site_packages(env)
    for module in entry.python:
        if site is None or not ((site / module).is_dir() or (site / f"{module}.py").is_file()):
            return (f"the Python module {module} is not installed in the environment (agentprov backends build ... "
                    f"--defence-assets {entry.id})")
    for weights in entry.weights:
        root = _snapshot(env, weights)
        for f in weights["files"]:
            p = root / f["path"]
            if not p.is_file() or p.is_symlink() or p.stat().st_size != f["size"]:
                return (f"its pinned weights file {weights['repo']}/{f['path']} is not provisioned (agentprov backends "
                        f"build ... --defence-assets {entry.id})")
            if _sha256_file(p) != f["sha256"]:
                return f"its provisioned weights file {weights['repo']}/{f['path']} differs from the pinned sha256"
    for f in entry.files:
        p = provisioned_dir(env, entry) / f["path"]
        if not p.is_file() or p.is_symlink():
            return f"its pinned file {f['path']} is not provisioned (agentprov backends build ... --defence-assets {entry.id})"
        if p.stat().st_size > MAX_PROVISIONED_BYTES or hashlib.sha256(p.read_bytes()).hexdigest() != f["sha256"]:
            return f"its provisioned file {f['path']} differs from the pinned sha256"
    return None


def check_environment(env: Path, entry: Entry, root: Path) -> tuple[str | None, str | None]:
    """``(environment problem, refusal)`` once the environment is known: the installed registry must be the
    repository's (else exit 3: rebuild), and a provisioned entry's files must be present and pinned (else exit 5)."""
    installed = installed_registry(env)
    repo = registry_path(root)
    if installed is None or hashlib.sha256(installed.read_bytes()).hexdigest() != hashlib.sha256(repo.read_bytes()).hexdigest():
        return ("the environment's defence registry differs from the repository's; rebuild the environment "
                "(agentprov backends build)"), None
    if entry.provider in ("provisioned", "port") or entry.weights or entry.python:
        return None, verify_provisioned(env, entry)
    return None, None


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def provision_weights(env: Path, entry: Entry, *, cache_dir: Path, allow_network: bool) -> list[dict[str, Any]]:
    """Copy the entry's pinned weights from the fetch cache (``url/<sha256>``; fetched there by ``agentprov.raw.fetch``
    with the sha256 pin, only under ``--allow-network``) into the environment's offline hub cache, with
    ``refs/main`` naming the pinned revision; returns the marker records."""
    import shutil

    from agentprov.raw.fetch import Fetcher, Recipe

    records = []
    fetcher = Fetcher(cache_dir, allow_network=allow_network, consent="--allow-network" if allow_network else "",
                      large_download_consent=allow_network)
    for weights in entry.weights:
        snap = _snapshot(env, weights)
        snap.mkdir(parents=True, exist_ok=True)
        done = {}
        for f in weights["files"]:
            url = f"https://huggingface.co/{weights['repo']}/resolve/{weights['revision']}/{f['path']}"
            recipe = Recipe(kind="url", url=url, sha256=f["sha256"], size=f["size"], hosts=tuple(weights["hosts"]))
            cached = recipe.cache_path(cache_dir)
            if not cached.is_file():
                if not allow_network:
                    raise ValueError(f"{weights['repo']}/{f['path']} (sha256 {f['sha256'][:12]}) is not in the fetch "
                                     "cache; run again with --allow-network to fetch it (the user's consent is needed)")
                fetcher.fetch(recipe)
            if cached.stat().st_size != f["size"] or _sha256_file(cached) != f["sha256"]:
                raise ValueError(f"the cached {weights['repo']}/{f['path']} differs from its pin")
            target = snap / f["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name(target.name + ".partial")
            shutil.copyfile(cached, tmp)
            os.replace(tmp, target)
            os.chmod(target, 0o444)
            done[f["path"]] = f["sha256"]
        refs = snap.parent.parent / "refs"
        refs.mkdir(parents=True, exist_ok=True)
        (refs / "main").write_text(str(weights["revision"]), encoding="ascii")
        records.append({"repo": weights["repo"], "revision": weights["revision"], "files": done})
    return records


def _git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data, usedforsecurity=False).hexdigest()


def _provision_local(env: Path, entry: Entry, source_dir: Path) -> dict[str, Any]:
    """``--defence-source DIR``: each pinned file from ``DIR/<path>``, accepted only as a regular file inside DIR whose
    size is within the bound and whose sha256 and git blob id are the registry's pins (no network; the bytes are the
    pinned ones whatever tree they were read from)."""
    from agentprov.io.atomic import atomic_write_bytes

    base = source_dir.resolve()
    record: dict[str, str] = {}
    for f in entry.files:
        p = source_dir / f["path"]
        if p.is_symlink() or not p.is_file() or not p.resolve().is_relative_to(base):
            raise ValueError(f"{f['path']} is not a regular file inside --defence-source")
        if p.stat().st_size > MAX_PROVISIONED_BYTES:
            raise ValueError(f"{f['path']} is larger than the provisioning bound")
        data = p.read_bytes()
        if hashlib.sha256(data).hexdigest() != f["sha256"] or _git_blob_sha1(data) != f["blob_sha1"]:
            raise ValueError(f"{f['path']} in --defence-source is not the pinned blob {f['blob_sha1'][:12]}")
        target = provisioned_dir(env, entry) / f["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(target, data)
        os.chmod(target, 0o444)
        record[f["path"]] = f["sha256"]
    return {"repo": entry.repo, "commit": entry.commit, "files": record, "source": "local (sha256 and blob id verified)"}


def provision(env: Path, entry: Entry, *, cache_dir: Path, allow_network: bool,
              source_dir: Path | None = None) -> dict[str, Any]:
    """Copy the entry's pinned files from the bare fetch cache (or, with ``source_dir`` holding all of them, from that
    local tree, verified by digest) into the environment (see the module docstring); returns the marker record
    ``{repo, commit, files}``."""
    from agentprov.io.atomic import atomic_write_bytes
    from agentprov.raw.fetch import Fetcher, Recipe

    if entry.provider not in ("provisioned", "port") or entry.repo is None or entry.commit is None or not entry.files:
        raise ValueError(f"defence {entry.id} has no pinned code to provision")
    if source_dir is not None and all((source_dir / f["path"]).is_file() for f in entry.files):
        # the local tree holds this entry's files (each still verified by sha256 and blob id); another entry of the same
        # build whose files the tree lacks comes from the fetch cache, so one build provisions every named entry
        return _provision_local(env, entry, source_dir)
    recipe = Recipe(kind="git", repo=entry.repo, commit=entry.commit)
    fetcher = Fetcher(cache_dir, allow_network=allow_network, consent="--allow-network" if allow_network else "")
    if not fetcher.plan(recipe).cached:
        if not allow_network:
            raise ValueError(f"the pinned commit {entry.commit[:12]} of {entry.repo} is not in the fetch cache; run "
                             "again with --allow-network to fetch it (the user's consent is needed)")
        fetcher.fetch(recipe)
    tree, _undecodable = fetcher.git_tree(recipe)
    by_path = {e.path: e for e in tree if e.is_blob and not e.is_symlink}
    wanted = []
    for f in entry.files:
        e = by_path.get(f["path"])
        if e is None or e.oid != f["blob_sha1"]:
            raise ValueError(f"{f['path']} at {entry.commit[:12]} is not the pinned blob {f['blob_sha1'][:12]}")
        if e.size is not None and e.size > MAX_PROVISIONED_BYTES:
            raise ValueError(f"{f['path']} is larger than the provisioning bound")
        wanted.append(e)
    root = provisioned_dir(env, entry)
    record: dict[str, str] = {}
    for blob in fetcher.iter_git_blobs(recipe, wanted):
        pinned = next(f for f in entry.files if f["path"] == blob.entry.path)
        if blob.sha256 != pinned["sha256"]:
            raise ValueError(f"{blob.entry.path}: the cached blob's sha256 differs from the pin")
        target = root / blob.entry.path
        target.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(target, blob.data)
        os.chmod(target, 0o444)
        record[blob.entry.path] = blob.sha256
    return {"repo": entry.repo, "commit": entry.commit, "files": record}
