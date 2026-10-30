"""The frozen baseline lock and the tree-listing digest (docs/architecture J.1.4, J.1.5).

``migration/baseline.lock.json`` pins the AgentDojo-PROV baseline: the commit and tag, the digests of the 13 tracked
files, the baseline environment, the results recorded at freeze time and the five gitignored corpus trees (which the git
commit cannot cover). It is generated once from ``investigation/baseline/baseline.json`` plus J.1.4 and then frozen
(``tools/migration/make_baseline_lock.py``); gate G0 (:mod:`agentprov.migration.gates`) verifies the baseline against it.

A **tree listing digest** is computed exactly as J.1.4 says: enumerate regular files under the root (no symlinks), skip
``.DS_Store`` and AppleDouble ``._*`` files, keep those matching the predicate, form POSIX relative paths, take the
SHA-256 of each file's bytes, sort by relative path in code-point order, build ``"<hex>  <relpath>\\n"`` per file (the
``shasum`` line format) and take the SHA-256 of the UTF-8 listing. The files are read, never written.
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from agentprov.errors import AgentProvError
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads

LOCK_FORMAT: Final = "agentprov-baseline-lock/1"
#: ``<repo>/src/agentprov/migration/lock.py`` -> ``<repo>``.
REPO_ROOT: Final = Path(__file__).resolve().parents[3]
DEFAULT_LOCK_PATH: Final = REPO_ROOT / "migration" / "baseline.lock.json"

_HEX64: Final = re.compile(r"[0-9a-f]{64}")
_HEX40: Final = re.compile(r"[0-9a-f]{40}")

#: The three predicates of J.1.4, by the name the lock records. They take the POSIX path relative to the tree root.
PREDICATES: Final[dict[str, Callable[[str], bool]]] = {
    "transcript": lambda rel: rel.endswith(".transcript.json"),
    "graph": lambda rel: rel.endswith(".json") and not rel.endswith(".transcript.json") and "/prov/" in rel,
    "json": lambda rel: rel.endswith(".json"),
}

#: The tree pins every lock must carry (J.1.5): name -> (root relative to the old repo, predicate).
TREE_SPECS: Final[dict[str, tuple[str, str]]] = {
    "release_transcripts": ("corpus/corpus-prov", "transcript"),
    "release_graphs": ("corpus/corpus-prov", "graph"),
    "converted_transcripts": ("corpus/corpus-og-agentdojo-runs-prov", "transcript"),
    "converted_graphs": ("corpus/corpus-og-agentdojo-runs-prov", "graph"),
    "native_runs": ("runs", "json"),
}


class LockError(AgentProvError):
    """The baseline lock is missing, malformed or inconsistent (no fixture text in the message)."""

    code = "migration.lock.invalid"
    exit_code = 3


# ------------------------------------------------------------------------------------------------ tree listing


@dataclass(frozen=True, slots=True)
class TreeListing:
    """Result of :func:`tree_listing`: ``entries`` are ``(relpath, sha256)`` sorted by path (code-point order)."""

    files: int
    listing_sha256: str
    entries: tuple[tuple[str, str], ...] = field(repr=False)


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _regular_files(root: Path) -> list[tuple[str, str]]:
    """``(relpath, abspath)`` of every regular, non-symlink file under ``root`` (no ``.DS_Store``, no ``._*``)."""
    found: list[tuple[str, str]] = []
    stack = [str(root)]
    prefix_len = len(str(root)) + 1
    while stack:
        directory = stack.pop()
        with os.scandir(directory) as it:
            for entry in it:
                name = entry.name
                if name == ".DS_Store" or name.startswith("._"):
                    continue
                mode = entry.stat(follow_symlinks=False).st_mode
                if stat.S_ISDIR(mode):
                    stack.append(entry.path)
                elif stat.S_ISREG(mode):
                    found.append((entry.path[prefix_len:].replace(os.sep, "/"), entry.path))
    return found


def tree_listing(root: Path, predicate: Callable[[str], bool], *, workers: int = 8) -> TreeListing:
    """The J.1.4 tree listing digest of ``root`` for the files whose relative path satisfies ``predicate``.

    ``workers`` threads hash the files (the result does not depend on it). Raises :class:`FileNotFoundError` when
    ``root`` is not a directory.
    """
    root = Path(root)
    if not root.is_dir():
        raise FileNotFoundError(f"not a directory: {root.name}")
    selected = sorted((rel, path) for rel, path in _regular_files(root) if predicate(rel))
    if workers > 1 and len(selected) > 1:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            digests = list(pool.map(_sha256_file, (path for _, path in selected), chunksize=64))
    else:
        digests = [_sha256_file(path) for _, path in selected]
    entries = tuple((rel, digest) for (rel, _), digest in zip(selected, digests, strict=True))
    listing = "".join(f"{digest}  {rel}\n" for rel, digest in entries)
    return TreeListing(len(entries), hashlib.sha256(listing.encode("utf-8")).hexdigest(), entries)


# ------------------------------------------------------------------------------------------------ the lock model


@dataclass(frozen=True, slots=True)
class TagPin:
    name: str
    object: str
    pushed: bool


@dataclass(frozen=True, slots=True)
class FrameworkPin:
    remote: str
    commit: str
    describe: str
    tag: TagPin
    existing_tags: Mapping[str, str]  # tag name -> the commit it peels to (J.1.1)
    package: Mapping[str, str]
    tracked_files: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class EnvironmentPin:
    python: str
    uv: str
    agentdojo: str
    pip_freeze_sha256: str
    packages: Mapping[str, str]
    #: sha256 of ``migration/baseline-requirements.txt`` (J.1.6); ``None`` until that hash-locked export is committed.
    requirements_lock_sha256: str | None
    #: sha256 of the ``agentdojo_prov`` 1.0.0 wheel built from the 579a908 export (J.1.6); ``None`` until it is built.
    baseline_wheel_sha256: str | None


@dataclass(frozen=True, slots=True)
class TreePin:
    root: str
    predicate: str
    files: int
    listing_sha256: str


@dataclass(frozen=True, slots=True)
class BaselineLock:
    """Typed mirror of ``migration/baseline.lock.json`` (J.1.5). ``results`` and ``investigation_record`` are data."""

    lock: str
    frozen_on: str
    framework: FrameworkPin
    environment: EnvironmentPin
    results: Mapping[str, Any]
    trees: Mapping[str, TreePin]
    investigation_record: Mapping[str, str]

    def to_json(self) -> dict[str, Any]:
        """The JSON form, in the key order of J.1.5."""
        fw, env = self.framework, self.environment
        return {
            "lock": self.lock,
            "frozen_on": self.frozen_on,
            "framework": {
                "remote": fw.remote,
                "commit": fw.commit,
                "describe": fw.describe,
                "tag": {"name": fw.tag.name, "object": fw.tag.object, "pushed": fw.tag.pushed},
                "existing_tags": dict(fw.existing_tags),
                "package": dict(fw.package),
                "tracked_files": dict(fw.tracked_files),
            },
            "environment": {
                "python": env.python,
                "uv": env.uv,
                "agentdojo": env.agentdojo,
                "pip_freeze_sha256": env.pip_freeze_sha256,
                "packages": dict(env.packages),
                "requirements_lock_sha256": env.requirements_lock_sha256,
                "baseline_wheel_sha256": env.baseline_wheel_sha256,
            },
            "results": dict(self.results),
            "trees": {
                name: {"root": t.root, "predicate": t.predicate, "files": t.files, "listing_sha256": t.listing_sha256}
                for name, t in self.trees.items()
            },
            "investigation_record": dict(self.investigation_record),
        }


def _expect(cond: bool, problems: list[str], message: str) -> None:
    if not cond:
        problems.append(message)


def _is_str_map(value: object, pattern: re.Pattern[str] | None = None) -> bool:
    return isinstance(value, dict) and all(
        isinstance(k, str) and isinstance(v, str) and (pattern is None or pattern.fullmatch(v)) for k, v in value.items()
    )


def _parse(raw: object) -> BaselineLock:
    problems: list[str] = []
    if not isinstance(raw, dict):
        raise LockError("the baseline lock must be a JSON object")
    _expect(raw.get("lock") == LOCK_FORMAT, problems, f"lock must be {LOCK_FORMAT!r}")
    _expect(isinstance(raw.get("frozen_on"), str), problems, "frozen_on must be a string")
    fw = raw.get("framework")
    env = raw.get("environment")
    trees = raw.get("trees")
    if not isinstance(fw, dict) or not isinstance(env, dict) or not isinstance(trees, dict):
        raise LockError("the baseline lock needs framework, environment and trees objects")
    tag = fw.get("tag")
    _expect(isinstance(tag, dict), problems, "framework.tag must be an object")
    tag = tag if isinstance(tag, dict) else {}
    _expect(isinstance(fw.get("commit"), str) and _HEX40.fullmatch(fw["commit"]) is not None, problems, "framework.commit must be 40 hex")
    _expect(isinstance(tag.get("name"), str), problems, "framework.tag.name must be a string")
    _expect(isinstance(tag.get("object"), str) and _HEX40.fullmatch(tag["object"]) is not None, problems, "framework.tag.object must be 40 hex")
    _expect(isinstance(tag.get("pushed"), bool), problems, "framework.tag.pushed must be a bool")
    for key in ("remote", "describe"):
        _expect(isinstance(fw.get(key), str), problems, f"framework.{key} must be a string")
    _expect(_is_str_map(fw.get("existing_tags"), _HEX40), problems, "framework.existing_tags must map names to 40 hex")
    _expect(_is_str_map(fw.get("package")), problems, "framework.package must map strings to strings")
    _expect(_is_str_map(fw.get("tracked_files"), _HEX64), problems, "framework.tracked_files must map paths to 64 hex")
    for key in ("python", "uv", "agentdojo"):
        _expect(isinstance(env.get(key), str), problems, f"environment.{key} must be a string")
    _expect(isinstance(env.get("pip_freeze_sha256"), str) and _HEX64.fullmatch(env["pip_freeze_sha256"]) is not None, problems, "environment.pip_freeze_sha256 must be 64 hex")
    _expect(_is_str_map(env.get("packages")), problems, "environment.packages must map strings to strings")
    for key in ("requirements_lock_sha256", "baseline_wheel_sha256"):
        value = env.get(key)
        _expect(value is None or (isinstance(value, str) and _HEX64.fullmatch(value) is not None), problems, f"environment.{key} must be 64 hex or null")
    _expect(isinstance(raw.get("results"), dict), problems, "results must be an object")
    _expect(_is_str_map(raw.get("investigation_record"), _HEX64), problems, "investigation_record must map names to 64 hex")
    _expect(set(trees) == set(TREE_SPECS), problems, f"trees must be exactly {sorted(TREE_SPECS)}")
    pins: dict[str, TreePin] = {}
    for name, spec in TREE_SPECS.items():
        item = trees.get(name)
        if not isinstance(item, dict):
            continue
        ok = (
            item.get("root") == spec[0]
            and item.get("predicate") == spec[1]
            and isinstance(item.get("files"), int)
            and not isinstance(item.get("files"), bool)
            and isinstance(item.get("listing_sha256"), str)
            and _HEX64.fullmatch(item["listing_sha256"]) is not None
        )
        _expect(ok, problems, f"trees.{name} must have root {spec[0]!r}, predicate {spec[1]!r}, files and listing_sha256")
        if ok:
            pins[name] = TreePin(item["root"], item["predicate"], item["files"], item["listing_sha256"])
    if problems:
        raise LockError("invalid baseline lock: " + "; ".join(problems))
    return BaselineLock(
        lock=raw["lock"],
        frozen_on=raw["frozen_on"],
        framework=FrameworkPin(
            remote=fw["remote"],
            commit=fw["commit"],
            describe=fw["describe"],
            tag=TagPin(tag["name"], tag["object"], tag["pushed"]),
            existing_tags=dict(fw["existing_tags"]),
            package=dict(fw["package"]),
            tracked_files=dict(fw["tracked_files"]),
        ),
        environment=EnvironmentPin(
            python=env["python"],
            uv=env["uv"],
            agentdojo=env["agentdojo"],
            pip_freeze_sha256=env["pip_freeze_sha256"],
            packages=dict(env["packages"]),
            requirements_lock_sha256=env.get("requirements_lock_sha256"),
            baseline_wheel_sha256=env.get("baseline_wheel_sha256"),
        ),
        results=dict(raw["results"]),
        trees={name: pins[name] for name in TREE_SPECS},
        investigation_record=dict(raw["investigation_record"]),
    )


def parse_lock(data: bytes) -> BaselineLock:
    """Parse and validate lock bytes (strict JSON through the tier-1 loader)."""
    try:
        raw = strict_json_loads(data, IngestLimits())
    except AgentProvError as exc:
        raise LockError(f"the baseline lock is not strict JSON ({exc.code})") from None
    return _parse(raw)


def load_lock(path: Path | None = None) -> BaselineLock:
    """Load ``migration/baseline.lock.json`` (default: the repository's). Raises :class:`LockError` on any defect."""
    target = Path(path) if path is not None else DEFAULT_LOCK_PATH
    try:
        data = target.read_bytes()
    except OSError as exc:
        raise LockError(f"cannot read the baseline lock: {exc.__class__.__name__}") from None
    return parse_lock(data)


def lock_sha256(path: Path | None = None) -> str:
    """sha256 of the lock file's bytes (the ``baseline_lock_sha256`` of every gate report)."""
    target = Path(path) if path is not None else DEFAULT_LOCK_PATH
    return hashlib.sha256(target.read_bytes()).hexdigest()
