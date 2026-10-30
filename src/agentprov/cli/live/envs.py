"""Backend environments: location, ``uv sync`` command, marker and T0 identity digests (MN N.2.10, M.1.7 rules 2-4;
D.10.6, D.10.10 item 3, D.11.2; G.6.2, G.6.3).

**Repository root** (M.4): the nearest ancestor of the current directory whose ``pyproject.toml`` declares
``name = "agentprov"``. ``backends build`` and ``run`` need it, because the backend projects are not in the wheel
(exit 3 outside a checkout).

**Environment name** ``<backend>-<commit8>`` (M.1.7 rule 2): ``commit8`` is the first 8 hex digits of the pinned fork
commit for a git-pinned backend (AutoDojo, AgentDyn), and of the sha256 of the backend project's ``uv.lock`` for a backend
pinned by version (AgentDojo, ``agentdojo==0.1.35`` from PyPI). A PyPI wheel has no commit; the lock pins every wheel by
hash, so its digest names exactly one resolved environment, and a re-lock (a deliberate change, G.7.1(4)) yields a new
directory instead of silently mutating the old one.

**T0 identity** (D.10.6, M.1.7 rule 4). From the environment's files and the lock, and without importing anything from
the environment: the lock digest, each watched distribution's dist-info ``RECORD`` digest and the verification of every
file the ``RECORD`` lists with a hash (so a modified guarded source or a modified ``RECORD`` is found), the PEP 610
``direct_url.json`` source (none for a registry wheel: ``{"kind": "pypi"}``), and the sha256 of the guarded source
*files* (the modules that hold the D.10.6 guarded names). The worker's ``hello_ok`` reports ``inspect.getsource``
digests per qualified name, which T0 cannot compute without importing; they are compared with the values the build
recorded in the marker from the build-time ``hello`` (whose files T0 has verified since), never accepted on the
worker's word alone (SR-09(3), R-39).

**Backend kinds** (D-662, D-663): :data:`BACKEND_KINDS` names, per backend id, the project directory under
``backends/``, the primary distribution (``agentdojo``; ``inspect-ai`` for the Inspect harness), the watched
distributions, the guarded modules, the path packages rebuilt on every build, the worker module, the hello members
compared with the build record and, for Inspect, the task package directories whose content digest
(``task_files_sha256``: JCS of ``{"files": {relative path: sha256}}``) T0 computes and the worker must report. The
AgentDojo and AutoDojo entries are the constants they always had, so their markers are unchanged. An Inspect
environment also provisions its pinned dataset from AgentPROV's fetch cache (``[tool.agentprov.dataset]``; offline
only: a file missing from the cache refuses the build).
"""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import os
import re
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from agentprov.errors import AgentProvError, BackendUnavailable, IdentityMismatch

__all__ = [
    "BACKEND_IDS",
    "BACKEND_KINDS",
    "BackendKind",
    "backend_kind",
    "check_dataset",
    "dataset_dir",
    "dataset_recipe",
    "provision_dataset",
    "ENV_MARKER",
    "FORK_GUARDED_MODULES",
    "GUARDED_MODULES",
    "MARKER_FORMAT",
    "NLTK_DIR",
    "SCRUBBED_UV_VARIABLES",
    "BackendProject",
    "EnvIdentity",
    "RepositoryRootMissing",
    "agentprov_home",
    "backend_project",
    "check_nltk",
    "compute_identity",
    "env_dir",
    "env_python",
    "lock_wheel",
    "nltk_data_dir",
    "nltk_recipe",
    "pinned_source",
    "provision_nltk",
    "read_marker",
    "repository_root",
    "site_packages",
    "uv_environment",
    "uv_sync_argv",
]

ENV_MARKER: Final = "AGENTPROV_ENV.json"
MARKER_FORMAT: Final = "agentprov-backend-env/0.1"
#: The distributions whose RECORD T0 verifies: the benchmark and the two shared packages the worker runs.
WATCHED_DISTRIBUTIONS: Final = ("agentdojo", "agentprov-backend", "agentprov-capture")
#: Modules holding the guarded qualified names of D.10.6 and D.10.10 item 7 (``agentprov_backend.identity
#: .GUARDED_NAMES``; a core test checks the two lists by AST, never by import).
GUARDED_MODULES: Final = (
    "agentdojo.agent_pipeline.llms.anthropic_llm",
    "agentdojo.agent_pipeline.llms.openai_llm",
    "agentdojo.agent_pipeline.tool_execution",
    "agentdojo.benchmark",
    "agentdojo.functions_runtime",
    "agentdojo.logging",
    "agentdojo.task_suite.task_suite",
)
#: Per-backend extra guarded modules (``agentprov_backend.identity.AUTODOJO_GUARDED_NAMES`` and
#: ``AGENTDYN_GUARDED_NAMES``, modules not already in :data:`GUARDED_MODULES`; a core test checks them by AST).
FORK_GUARDED_MODULES: Final[Mapping[str, tuple[str, ...]]] = {
    "autodojo": ("agentdojo.attacks.autodojo_attack", "agentdojo.attacks.base_attacks"),
    "agentdyn": ("agentdojo.agent_pipeline.agent_pipeline",),
}
#: Where the NLTK data of a backend environment lives (D.11.2): ``<env>/nltk_data``, passed to the worker as
#: ``NLTK_DATA``; ``punkt_tab`` stays an unextracted zip (nltk >= 3.9 reads it from the zip).
NLTK_DIR: Final = "nltk_data"
PUNKT_TAB_RELPATH: Final = ("tokenizers", "punkt_tab.zip")
#: G.6.2: the ``UV_*`` variables that redirect resolution, configuration or environment files. ``backends build``
#: goes further and passes **no** ``UV_*`` variable except :data:`UV_KEPT` (cache and interpreter locations, which
#: change where bytes are stored, not which bytes are resolved: every wheel is checked against the lock's hash).
SCRUBBED_UV_VARIABLES: Final = (
    "UV_INDEX_URL", "UV_EXTRA_INDEX_URL", "UV_DEFAULT_INDEX", "UV_FIND_LINKS", "UV_INSECURE_HOST",
    "UV_KEYRING_PROVIDER", "UV_CONFIG_FILE", "UV_NO_SOURCES", "UV_ENV_FILE",
)  # fmt: skip
UV_KEPT: Final = ("UV_CACHE_DIR", "UV_PYTHON_INSTALL_DIR", "UV_PYTHON_BIN_DIR")
#: The shared path packages: rebuilt on every build so their RECORD describes the current sources (M.1.7 note).
SHARED_PACKAGES: Final = ("agentprov-capture", "agentprov-backend")
#: ``hello_ok.identity`` members compared with the build-time ``hello`` record (they need imports to compute).
HELLO_RECORDED_KEYS: Final = (
    "distribution", "version_reported", "guarded_sources", "suite_set", "benchmark_version",
    "default_system_prompt_sha256", "tool_definitions_sha256",
)  # fmt: skip
#: The Inspect worker's recorded hello members (``agentprov_backend_inspect.worker._identity``).
INSPECT_HELLO_KEYS: Final = ("distribution", "version_reported", "benchmark", "dataset", "task_files_sha256")
#: Where an Inspect environment holds its provisioned dataset (``agentprov_backend_inspect.provision``).
DATASETS_DIR: Final = ("share", "agentprov", "datasets")


@dataclass(frozen=True)
class InspectCallBound:
    """D-740: the model calls one sample of an Inspect task makes besides its agent calls, derived from the pinned task
    code and valid only for it (``task_files_sha256`` of ``task_dir``). ``per_agent_call``: judge calls per agent call
    (AgentHarm's refusal judge reads every assistant message); ``per_sample``: judge calls per sample (AgentHarm's
    grading functions call the semantic judge at most 3 times, none in a loop; ``docs/reports/inspect-harness/
    cell-bound.md`` section 2, re-derived by ``tests/cli/test_inspect_cell_bound.py``)."""

    task_dir: str
    task_files_sha256: str
    per_agent_call: int
    per_sample: int


#: inspect_evals 0.20.0's ``agentharm`` package (both tasks share its scorer).
_AGENTHARM_020: Final = InspectCallBound("inspect_evals/agentharm",
                                         "sha256:4ba500beea6be8103cbab9559e1f9d8672322451817ac3170dc9a6376832a398", 1, 3)
#: D-740: the retries the Inspect worker allows per model call (``GenerateConfig.max_retries``; the provider SDK's own
#: retries are off), so one logical call is at most ``1 + INSPECT_MAX_RETRIES`` billed responses. The worker's
#: ``agentprov_backend_inspect.models.MAX_RETRIES`` must equal it (a test checks).
INSPECT_MAX_RETRIES: Final = 1


@dataclass(frozen=True)
class BackendKind:
    """What T0 needs to know about one backend id (D-662)."""

    project: str  # the project directory under backends/
    primary: str = "agentdojo"  # the benchmark distribution of hello.expect and check_hello
    watched: tuple[str, ...] = WATCHED_DISTRIBUTIONS
    guarded_modules: tuple[str, ...] = GUARDED_MODULES
    rebuilt: tuple[str, ...] = SHARED_PACKAGES
    task_dirs: tuple[str, ...] = ()  # site-packages directories hashed as task_files_sha256 (Inspect)
    worker_module: str = "agentprov_backend.worker"
    hello_keys: tuple[str, ...] = HELLO_RECORDED_KEYS
    call_bounds: Mapping[str, InspectCallBound] = field(default_factory=dict)  # Inspect task -> its judge calls (D-740)


BACKEND_KINDS: Final[Mapping[str, BackendKind]] = {
    "agentdojo": BackendKind("agentdojo"),
    "autodojo": BackendKind("autodojo", guarded_modules=(*GUARDED_MODULES, *FORK_GUARDED_MODULES["autodojo"])),
    "agentdyn": BackendKind("agentdyn", guarded_modules=(*GUARDED_MODULES, *FORK_GUARDED_MODULES["agentdyn"])),
    "inspect-agentharm": BackendKind(
        "inspect/envs/agentharm", primary="inspect-ai",
        watched=("inspect-ai", "inspect-evals", "agentprov-backend-inspect", "agentprov-backend", "agentprov-capture"),
        guarded_modules=(), rebuilt=(*SHARED_PACKAGES, "agentprov-backend-inspect"),
        task_dirs=("inspect_evals/agentharm",), worker_module="agentprov_backend_inspect.worker",
        hello_keys=INSPECT_HELLO_KEYS,
        call_bounds={"inspect_evals/agentharm": _AGENTHARM_020, "inspect_evals/agentharm_benign": _AGENTHARM_020}),
}
BACKEND_IDS: Final = tuple(BACKEND_KINDS)


def backend_kind(backend: str) -> BackendKind:
    try:
        return BACKEND_KINDS[backend]
    except KeyError:
        raise BackendUnavailable(f"unknown backend {backend!r}") from None
_HEX64: Final = re.compile(r"[0-9a-f]{64}")
_MARKER_MAX: Final = 1024 * 1024


class RepositoryRootMissing(AgentProvError):
    """``backends build`` / ``run`` outside a repository checkout (M.4; N.2.10). Exit 3."""

    code = "backend.repository_missing"
    exit_code = 3


def agentprov_home(environ: Mapping[str, str] | None = None) -> Path:
    """``$AGENTPROV_HOME``, default ``~/.agentprov`` (M.4), as an absolute path: workers run with a cwd inside it, so a
    relative home would resolve against the wrong directory."""
    raw = (os.environ if environ is None else environ).get("AGENTPROV_HOME")
    return Path(os.path.abspath(Path(raw).expanduser() if raw else Path.home() / ".agentprov"))


def repository_root(start: str | os.PathLike[str] | None = None) -> Path:
    """The nearest ancestor of ``start`` (default: the current directory) whose ``pyproject.toml`` declares
    ``name = "agentprov"`` (M.4). Raises :class:`RepositoryRootMissing` when there is none."""
    here = Path(os.path.abspath(start if start is not None else os.getcwd()))
    for candidate in (here, *here.parents):
        pyproject = candidate / "pyproject.toml"
        try:
            if not pyproject.is_file():
                continue
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
            continue
        if (data.get("project") or {}).get("name") == "agentprov":
            return candidate
    raise RepositoryRootMissing(
        "this command needs the AgentPROV repository checkout (the backend projects are not in the wheel); run it "
        "from inside the repository"
    )


@dataclass(frozen=True)
class BackendProject:
    """``backends/<backend>/``: its lock digest, ``[tool.uv]`` settings and the environment it names."""

    backend: str
    root: Path  # repository root
    project: Path
    lock_sha256: str
    exclude_newer: str | None
    no_build_packages: tuple[str, ...]
    commit: str | None  # pinned fork commit (git-pinned backends); None for a PyPI pin
    commit8: str
    commit8_source: str  # "lock_sha256" | "fork_commit"
    fork_repo: str | None = None  # the pinned fork's git URL (git-pinned backends)
    fork_subdirectory: str | None = None
    nltk: Mapping[str, Any] | None = None  # ``[tool.agentprov.nltk]`` of the project (D.11.2), when declared
    dataset: Mapping[str, Any] | None = None  # ``[tool.agentprov.dataset]`` (Inspect, D-663), when declared

    @property
    def env_name(self) -> str:
        return f"{self.backend}-{self.commit8}"


def backend_project(backend: str, root: Path) -> BackendProject:
    """Read ``backends/<backend>/`` (trusted repository files). Exit 3 when the project or its lock is missing."""
    rel = backend_kind(backend).project
    project = root / "backends" / rel
    lock = project / "uv.lock"
    pyproject = project / "pyproject.toml"
    if not lock.is_file() or not pyproject.is_file():
        raise BackendUnavailable(f"backends/{rel} has no pyproject.toml or uv.lock in this checkout")
    lock_bytes = lock.read_bytes()
    lock_sha = hashlib.sha256(lock_bytes).hexdigest()
    try:
        config = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise BackendUnavailable(f"backends/{rel}/pyproject.toml cannot be read: {type(exc).__name__}") from None
    uv = (config.get("tool") or {}).get("uv") or {}
    exclude_newer = uv.get("exclude-newer")
    no_build = tuple(str(n) for n in uv.get("no-build-package", ()))
    commit = _fork_commit(config)
    if commit is not None:
        commit8, source = commit[:8], "fork_commit"
    else:
        commit8, source = lock_sha[:8], "lock_sha256"
    entry = (((config.get("tool") or {}).get("uv") or {}).get("sources") or {}).get("agentdojo")
    entry = entry if isinstance(entry, Mapping) and commit is not None else {}
    nltk = ((config.get("tool") or {}).get("agentprov") or {}).get("nltk")
    dataset = ((config.get("tool") or {}).get("agentprov") or {}).get("dataset")
    return BackendProject(backend, root, project, lock_sha, str(exclude_newer) if exclude_newer else None, no_build,
                          commit, commit8, source,
                          str(entry["git"]) if isinstance(entry.get("git"), str) else None,
                          str(entry["subdirectory"]) if isinstance(entry.get("subdirectory"), str) else None,
                          dict(nltk) if isinstance(nltk, Mapping) else None,
                          dict(dataset) if isinstance(dataset, Mapping) else None)


def _fork_commit(config: Mapping[str, Any]) -> str | None:
    sources = ((config.get("tool") or {}).get("uv") or {}).get("sources") or {}
    entry = sources.get("agentdojo")
    rev = entry.get("rev") if isinstance(entry, Mapping) else None
    return rev if isinstance(rev, str) and re.fullmatch(r"[0-9a-f]{40}", rev) else None


def pinned_source(project: BackendProject) -> dict[str, str] | None:
    """The PEP 610 source the installed fork must report (``_direct_url`` shape), or ``None`` for a PyPI pin."""
    if project.commit is None or project.fork_repo is None:
        return None
    out = {"kind": "git", "repo": project.fork_repo, "commit": project.commit}
    if project.fork_subdirectory is not None:
        out["subdirectory"] = project.fork_subdirectory
    return out


def lock_wheel(project: BackendProject, distribution: str = "agentdojo") -> dict[str, Any] | None:
    """The lock's entry for ``distribution``: ``{version, source, wheel_sha256}`` (the wheel hash pins a PyPI build)."""
    data = tomllib.loads((project.project / "uv.lock").read_text(encoding="utf-8"))
    for package in data.get("package", ()):
        if package.get("name") != distribution:
            continue
        wheels = [w for w in package.get("wheels", ()) if isinstance(w, Mapping)]
        hashes = sorted({str(w.get("hash", "")).removeprefix("sha256:") for w in wheels if w.get("hash")})
        return {"version": package.get("version"), "source": dict(package.get("source") or {}),
                "wheel_sha256": hashes[0] if len(hashes) == 1 else None}
    return None


def env_dir(project: BackendProject, home: Path) -> Path:
    return home / "envs" / project.env_name


def env_python(env: Path) -> Path:
    """The environment's interpreter: ``bin/python`` (POSIX) or ``Scripts/python.exe`` (Windows), whichever exists."""
    for candidate in (env / "bin" / "python", env / "Scripts" / "python.exe"):
        if candidate.exists():
            return candidate
    return env / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def site_packages(env: Path) -> Path:
    """The environment's single ``site-packages`` directory."""
    found = sorted(env.glob("lib/python*/site-packages")) + sorted(env.glob("Lib/site-packages"))
    found = [p for p in found if p.is_dir() and not p.is_symlink()]
    if len(found) != 1:
        raise BackendUnavailable(f"the backend environment has {len(found)} site-packages directories, expected one")
    return found[0]


def uv_sync_argv(project: BackendProject, *, offline: bool, uv: str = "uv", groups: Sequence[str] = ()) -> list[str]:
    """``uv sync --locked --no-config`` with the project's ``exclude-newer`` and no-build list passed explicitly (M.1.7
    phase-2 note: ``--no-config`` also drops the project's own ``[tool.uv]``, after which ``--locked`` reports the lock
    stale), the shared path packages reinstalled, the dev group left out (the worker needs no test tools), and files
    copied rather than hard-linked from the cache (the environment never shares inodes with the cache). ``groups`` adds
    dependency groups (the backend's ``defences`` group, D-672, when a build provisions a defence that needs it)."""
    argv = [uv, "sync", "--locked", "--no-config", "--no-dev", "--link-mode", "copy"]
    for group in groups:
        argv += ["--group", group]
    if offline:
        argv.append("--offline")
    if project.exclude_newer:
        argv += ["--exclude-newer", project.exclude_newer]
    for name in project.no_build_packages:
        argv += ["--no-build-package", name]
    for name in backend_kind(project.backend).rebuilt:
        argv += ["--reinstall-package", name]
    argv += ["--project", str(project.project)]
    return argv


def uv_environment(environ: Mapping[str, str], env: Path) -> dict[str, str]:
    """The environment of the ``uv`` process (G.6.2): the parent's, minus every ``UV_*`` variable except
    :data:`UV_KEPT`, minus ``VIRTUAL_ENV``, minus every variable whose name marks a secret (K.3.4 scrub pattern; no
    ``.env`` value is ever in it, because ``.env`` is read into a private mapping), plus ``UV_PROJECT_ENVIRONMENT``."""
    from agentprov_capture.redact import secrets_from_environ

    secret_names = {s.name for s in secrets_from_environ(environ)}
    out = {
        k: v for k, v in environ.items()
        if not (k.startswith("UV_") and k not in UV_KEPT) and k != "VIRTUAL_ENV" and k not in secret_names
    }  # fmt: skip
    out["UV_PROJECT_ENVIRONMENT"] = str(env)
    return out


# ------------------------------------------------------------------------------------------------ marker
def read_marker(env: Path) -> dict[str, Any] | None:
    """The marker of ``env`` (strict loader, bounded; the file lives where T2 can write, so it is untrusted input), or
    ``None`` when absent."""
    from agentprov.errors import IngestError
    from agentprov.ingest.limits import IngestLimits
    from agentprov.ingest.loaders import strict_json_loads

    path = env / ENV_MARKER
    if not path.is_file() or path.is_symlink():
        return None
    data = path.read_bytes()
    if len(data) > _MARKER_MAX:
        raise IdentityMismatch("the backend environment marker is oversized")
    try:
        doc = strict_json_loads(data, IngestLimits())
    except IngestError:
        raise IdentityMismatch("the backend environment marker is not strict JSON") from None
    if not isinstance(doc, dict) or doc.get("format") != MARKER_FORMAT:
        raise IdentityMismatch(f"the backend environment marker is not {MARKER_FORMAT}")
    return doc


# ------------------------------------------------------------------------------------------------ NLTK (D.11.2)
NLTK_CONSENT: Final = "--allow-network: agentprov backends build autodojo (NLTK punkt_tab; D.11.2)"


def nltk_recipe(project: BackendProject) -> Any:
    """The pinned ``punkt_tab`` download of ``[tool.agentprov.nltk]`` as a ``raw.fetch.Recipe`` (kind ``url``), or
    ``None`` when the project declares no recipe or has not pinned it yet (``url`` and ``sha256`` both required; a
    digest is never guessed)."""
    from agentprov.raw.fetch import Recipe

    cfg = project.nltk or {}
    url, sha256 = cfg.get("url"), cfg.get("sha256")
    if not (isinstance(url, str) and url and isinstance(sha256, str) and sha256):
        return None
    size = cfg.get("bytes")
    md5 = cfg.get("md5")
    return Recipe(kind="url", role="nltk_punkt_tab", url=url, sha256=sha256,
                  md5=md5 if isinstance(md5, str) else None, size=size if isinstance(size, int) else None)


def nltk_data_dir(env: Path) -> Path:
    return env / NLTK_DIR


def provision_nltk(env: Path, project: BackendProject, environ: Mapping[str, str], *, allow_network: bool,
                   consent: str = NLTK_CONSENT) -> dict[str, Any]:
    """Provision ``punkt_tab`` into ``<env>/nltk_data/tokenizers/punkt_tab.zip`` (unextracted) from the pinned recipe
    (D.11.2). The zip comes from the verified fetch cache (``raw.fetch``: ``<cache>/url/<sha256>``, digest checked on
    every use); without ``--allow-network`` a file that is not cached is not fetched. Returns the marker record
    ``{status, sha256, path, url, reason}``: ``status`` is ``provisioned``, ``recipe_unpinned``, ``not_cached`` or
    ``not_declared``; ``sha256`` is set only when provisioned. A cache whose bytes do not match the pin is an error
    (exit 3)."""
    from agentprov.io.atomic import atomic_write_bytes
    from agentprov.raw.fetch import FetchError, Fetcher, NetworkRefusedError, resolve_cache_dir

    cfg = project.nltk
    target = nltk_data_dir(env).joinpath(*PUNKT_TAB_RELPATH)
    record: dict[str, Any] = {"package": "tokenizers/punkt_tab", "path": f"{NLTK_DIR}/" + "/".join(PUNKT_TAB_RELPATH),
                              "url": (cfg or {}).get("url") or None, "sha256": None}
    if cfg is None:
        return {**record, "status": "not_declared", "reason": "the backend project declares no NLTK data"}
    recipe = nltk_recipe(project)
    if recipe is None:
        return {**record, "status": "recipe_unpinned",
                "reason": "[tool.agentprov.nltk] has no pinned url and sha256: no acquisition has been made"}
    try:
        cache = resolve_cache_dir(None, environ)
        result = Fetcher(cache, allow_network=allow_network, consent=consent, env=environ).fetch(recipe)
    except NetworkRefusedError:
        return {**record, "status": "not_cached",
                "reason": "punkt_tab is not in the verified cache; rerun with --allow-network to fetch it"}
    except FetchError as exc:
        raise BackendUnavailable(f"NLTK punkt_tab: {exc}") from None
    data = result.path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != recipe.sha256:
        raise BackendUnavailable("NLTK punkt_tab: the cached file does not match its pinned sha256")
    target.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_bytes(target, data)
    return {**record, "status": "provisioned", "sha256": digest, "bytes": len(data), "reason": None,
            "fetched": bool(result.network_used)}


def check_nltk(env: Path, marker: Mapping[str, Any]) -> str | None:
    """``--offline-check`` / run-time check: when the marker records ``nltk_sha256``, the provisioned zip must still
    have that digest (exit 3 otherwise). Returns the ``NLTK_DATA`` directory to pass to the worker, or ``None`` when
    the environment has no NLTK data (a filter-defence run on it is refused)."""
    digest = marker.get("nltk_sha256")
    if digest is None:
        return None
    if not isinstance(digest, str) or _HEX64.fullmatch(digest) is None:
        raise IdentityMismatch("the marker's nltk_sha256 is malformed")
    path = nltk_data_dir(env).joinpath(*PUNKT_TAB_RELPATH)
    try:
        data = _read_regular(path, env, 512 * 1024 * 1024)
    except (IdentityMismatch, OSError):
        raise IdentityMismatch("the provisioned NLTK punkt_tab zip is missing") from None
    if hashlib.sha256(data).hexdigest() != digest:
        raise IdentityMismatch("the provisioned NLTK punkt_tab zip differs from the marker's nltk_sha256")
    return str(nltk_data_dir(env))


# ------------------------------------------------------------------------------------------------ datasets (Inspect)
_DATASET_PATH: Final = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.\-]{0,127}(?:/[A-Za-z0-9_][A-Za-z0-9_.\-]{0,127}){0,7}")
_SLUG: Final = re.compile(r"[a-z0-9][a-z0-9_\-]{0,63}")
_HF_REPO: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.\-]{0,95}/[A-Za-z0-9][A-Za-z0-9_.\-]{0,95}")
_DATASET_MAX_BYTES: Final = 256 * 1024 * 1024


def dataset_recipe(project: BackendProject) -> dict[str, Any] | None:
    """``[tool.agentprov.dataset]`` of an Inspect environment project, checked (trusted repository data, but a typo
    must not become a path): ``kind = "hf"``, ``repo``, a 40-hex ``revision``, the ``benchmark`` slug and
    ``files = [{path, sha256, bytes}]``. ``None`` when the project declares none."""
    raw = project.dataset
    if raw is None:
        return None
    files = raw.get("files")
    ok = (raw.get("kind") == "hf" and isinstance(raw.get("repo"), str) and _HF_REPO.fullmatch(raw["repo"])
          and isinstance(raw.get("revision"), str) and re.fullmatch(r"[0-9a-f]{40}", raw["revision"])
          and isinstance(raw.get("benchmark"), str) and _SLUG.fullmatch(raw["benchmark"])
          and isinstance(files, list) and files)
    if not ok or not isinstance(files, list):
        raise BackendUnavailable(f"backends/{backend_kind(project.backend).project}: [tool.agentprov.dataset] is malformed")
    out = []
    for f in files:
        if not (isinstance(f, Mapping) and isinstance(f.get("path"), str) and _DATASET_PATH.fullmatch(f["path"])
                and ".." not in f["path"].split("/") and isinstance(f.get("sha256"), str) and _HEX64.fullmatch(f["sha256"])
                and isinstance(f.get("bytes"), int) and not isinstance(f["bytes"], bool)
                and 0 <= f["bytes"] <= _DATASET_MAX_BYTES):
            raise BackendUnavailable("[tool.agentprov.dataset]: a file entry is malformed")
        out.append({"path": f["path"], "sha256": f["sha256"], "bytes": f["bytes"]})
    return {"kind": "hf", "repo": raw["repo"], "revision": raw["revision"], "benchmark": raw["benchmark"], "files": out}


def dataset_dir(env: Path, recipe: Mapping[str, Any]) -> Path:
    """``<env>/share/agentprov/datasets/<benchmark>/<revision>`` (``agentprov_backend_inspect.provision``)."""
    return env.joinpath(*DATASETS_DIR, str(recipe["benchmark"]), str(recipe["revision"]))


def provision_dataset(env: Path, project: BackendProject, environ: Mapping[str, str]) -> dict[str, Any] | None:
    """Copy the pinned dataset files from AgentPROV's fetch cache (``<cache>/hf/<repo>/<revision>/<path>``, fetched
    earlier with the user's consent and logged in ``acquisitions.jsonl``) into the environment, read-only, checking each
    file's size and sha256 before and after the copy. Offline only: a missing or mismatched file refuses the build.
    Returns the marker record ``{kind, repo, revision, benchmark, files: {path: sha256}}``, or ``None``.

    No symlink is followed below the cache root or below ``env`` (rebuild-window final re-check nit): a cached file
    is read through :func:`agentprov.ingest.paths.open_evidence` (every component checked, a regular file), every
    directory on the way to a copy is checked, and a copy is created exclusively (``O_CREAT | O_EXCL`` fails on an
    existing link), so a planted link can neither feed other bytes in nor redirect the write out of the environment.
    The cache root and ``env`` themselves may be links the operator chose."""
    from agentprov.raw.fetch import resolve_cache_dir

    recipe = dataset_recipe(project)
    if recipe is None:
        return None
    cache = resolve_cache_dir(None, environ)
    dest = dataset_dir(env, recipe)
    digests: dict[str, str] = {}
    for f in recipe["files"]:
        data = _read_no_follow(cache, "/".join(("hf", recipe["repo"], recipe["revision"], f["path"])), int(f["bytes"]))
        if data is None:
            raise BackendUnavailable(f"dataset {recipe['repo']}@{recipe['revision'][:12]}: {f['path']} is not in the "
                                     "fetch cache with its pinned size; fetch the pinned snapshot first (it needs the "
                                     "user's consent)")
        if hashlib.sha256(data).hexdigest() != f["sha256"]:
            raise BackendUnavailable(f"dataset {recipe['repo']}: the cached {f['path']} does not match its pinned sha256")
        target = dest.joinpath(*f["path"].split("/"))
        if _symlink_below(env, target.parent):
            raise BackendUnavailable(f"dataset {recipe['repo']}: a directory on the way to {f['path']} in the "
                                     "environment is a symlink")
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_symlink():
            raise BackendUnavailable(f"dataset {recipe['repo']}: {f['path']} in the environment is a symlink")
        if target.exists():
            target.chmod(0o644)
            target.unlink()
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
        with os.fdopen(fd, "wb") as out:
            out.write(data)
        if hashlib.sha256(_read_regular(target, env)).hexdigest() != f["sha256"]:  # pragma: no cover - a copy of bytes
            raise BackendUnavailable(f"dataset {recipe['repo']}: the copy of {f['path']} does not match its pin")
        digests[f["path"]] = f["sha256"]
    return {"kind": "hf", "repo": recipe["repo"], "revision": recipe["revision"], "benchmark": recipe["benchmark"],
            "files": dict(sorted(digests.items()))}


def _symlink_below(root: Path, path: Path) -> bool:
    """Whether a component of ``path`` below ``root`` (``root`` itself excluded) is a symlink."""
    current = root
    for part in path.relative_to(root).parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _read_no_follow(root: Path, label: str, size: int) -> bytes | None:
    """The bytes of the regular file ``label`` below ``root``, reached through no symlink (``open_evidence``), when it
    has ``size`` bytes; ``None`` otherwise (missing, a link on the way, not regular, another size)."""
    from agentprov.errors import IngestError
    from agentprov.ingest.paths import open_evidence

    try:
        with open_evidence(root, label, allow_hardlinks=True) as handle:
            data = handle.read(size + 1)
    except (IngestError, OSError):
        return None
    return data if len(data) == size else None


def check_dataset(env: Path, project: BackendProject, marker: Mapping[str, Any]) -> None:
    """``--offline-check`` and ``run``: the marker's dataset record equals the project's recipe, and every file in the
    environment still has its pinned sha256 (exit 3 otherwise). Nothing to check for a project without a recipe."""
    recipe = dataset_recipe(project)
    recorded = marker.get("dataset")
    if recipe is None:
        if recorded is not None:
            raise IdentityMismatch("the marker records a dataset the project does not declare")
        return
    expected = {f["path"]: f["sha256"] for f in recipe["files"]}
    if not isinstance(recorded, Mapping) or recorded.get("files") != dict(sorted(expected.items())) \
            or recorded.get("revision") != recipe["revision"] or recorded.get("repo") != recipe["repo"]:
        raise IdentityMismatch("the marker's dataset record differs from the project's [tool.agentprov.dataset]")
    root = dataset_dir(env, recipe)
    for rel, digest in expected.items():
        try:
            data = _read_regular(root.joinpath(*rel.split("/")), env)
        except (IdentityMismatch, OSError):
            raise IdentityMismatch(f"the provisioned dataset lacks {rel}") from None
        if hashlib.sha256(data).hexdigest() != digest:
            raise IdentityMismatch(f"the provisioned dataset file {rel} differs from its pin")


# ------------------------------------------------------------------------------------------------ T0 identity
@dataclass(frozen=True)
class DistIdentity:
    name: str
    version: str
    record_sha256: str
    source: dict[str, str]
    files_verified: int

    def to_json(self) -> dict[str, Any]:
        return {"name": self.name, "version": self.version, "record_sha256": self.record_sha256,
                "source": dict(self.source), "files_verified": self.files_verified}


@dataclass(frozen=True)
class EnvIdentity:
    """What T0 computed from the environment's files (D.10.6)."""

    lock_sha256: str
    distributions: dict[str, DistIdentity]
    guarded_files: dict[str, str]  # "<module path>.py" -> sha256
    primary: str = "agentdojo"
    task_files: dict[str, str] = field(default_factory=dict)  # Inspect task dir -> "sha256:<hex>" (D-663)

    def to_json(self) -> dict[str, Any]:
        out = {
            "lock_sha256": self.lock_sha256,
            "distributions": {k: v.to_json() for k, v in sorted(self.distributions.items())},
            "guarded_files": dict(sorted(self.guarded_files.items())),
        }
        if self.task_files:  # only Inspect environments: AgentDojo/AutoDojo markers are unchanged
            out["task_files"] = dict(sorted(self.task_files.items()))
        return out

    def expect(self, commit: str | None) -> dict[str, Any]:
        """``hello.expect`` (D.11.3): computed by T0 before spawn."""
        bench = self.distributions[self.primary]
        return {"commit": commit, "lock_sha256": self.lock_sha256, "record_sha256": bench.record_sha256,
                "guarded_sources": dict(sorted(self.guarded_files.items()))}


def _normalise(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _dist_info(sp: Path, name: str) -> Path:
    wanted = _normalise(name)
    found = []
    for entry in sorted(sp.iterdir()):
        if entry.name.endswith(".dist-info") and entry.is_dir() and not entry.is_symlink():
            if _normalise(entry.name[: -len(".dist-info")].rsplit("-", 1)[0]) == wanted:
                found.append(entry)
    if len(found) != 1:
        raise IdentityMismatch(f"distribution {name}: {len(found)} dist-info directories in the backend environment")
    return found[0]


def _read_regular(path: Path, root: Path, limit: int = 256 * 1024 * 1024) -> bytes:
    """Read a file of the environment: a regular file (no symlink in the last component) inside ``root``."""
    resolved = Path(os.path.realpath(path))
    try:
        resolved.relative_to(os.path.realpath(root))
    except ValueError:
        raise IdentityMismatch(f"{path.name}: the path leaves the backend environment") from None
    if path.is_symlink() or not resolved.is_file():
        raise IdentityMismatch(f"{path.name}: not a regular file")
    if resolved.stat().st_size > limit:
        raise IdentityMismatch(f"{path.name}: oversized")
    return resolved.read_bytes()


def _metadata_version(dist_info: Path, env: Path) -> str:
    text = _read_regular(dist_info / "METADATA", env).decode("utf-8", "replace")
    for line in text.splitlines():
        if line.startswith("Version:"):
            return line.split(":", 1)[1].strip()
        if not line.strip():
            break
    raise IdentityMismatch(f"{dist_info.name}: METADATA has no Version")


def _direct_url(dist_info: Path, env: Path) -> dict[str, str]:
    """The PEP 610 source, in the shape the worker reports (``agentprov_backend.identity._dist_source``)."""
    from agentprov.errors import IngestError
    from agentprov.ingest.limits import IngestLimits
    from agentprov.ingest.loaders import strict_json_loads

    path = dist_info / "direct_url.json"
    if not path.exists():
        return {"kind": "pypi"}
    try:
        doc = strict_json_loads(_read_regular(path, env, 1024 * 1024), IngestLimits())
    except IngestError:
        return {"kind": "unreadable_direct_url"}
    if not isinstance(doc, dict):
        return {"kind": "unreadable_direct_url"}
    url = doc.get("url", "")
    vcs = doc.get("vcs_info")
    if isinstance(vcs, dict):
        out = {"kind": str(vcs.get("vcs", "vcs")), "repo": str(url), "commit": str(vcs.get("commit_id", ""))}
        if isinstance(doc.get("subdirectory"), str):
            out["subdirectory"] = doc["subdirectory"]
        return out
    if isinstance(doc.get("dir_info"), dict):
        return {"kind": "dir", "editable": str(bool(doc["dir_info"].get("editable", False))).lower()}
    archive = doc.get("archive_info")
    if isinstance(archive, dict):
        out = {"kind": "url", "url": str(url)}
        h = archive.get("hash") or ""
        if isinstance(h, str) and h.startswith("sha256="):
            out["wheel_sha256"] = h.split("=", 1)[1]
        return out
    return {"kind": "unknown"}


def _record_rows(data: bytes) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    for row in csv.reader(io.StringIO(data.decode("utf-8"))):
        if not row:
            continue
        path = row[0]
        digest = row[1] if len(row) > 1 else ""
        size = row[2] if len(row) > 2 else ""
        rows.append((path, digest, size))
    return rows


def _verify_record(dist_info: Path, sp: Path, env: Path, record: bytes) -> tuple[int, list[str]]:
    """Verify every hashed RECORD entry against the installed file. Returns ``(n_verified, problems)``."""
    problems: list[str] = []
    verified = 0
    for rel, digest, _size in _record_rows(record):
        if not digest:
            continue  # RECORD itself, and files the installer could not hash
        algo, _, value = digest.partition("=")
        if algo != "sha256":
            problems.append(f"{rel}: unsupported hash {algo!r}")
            continue
        target = Path(os.path.normpath(sp / rel))
        try:
            data = _read_regular(target, env)
        except (IdentityMismatch, OSError):
            problems.append(f"{rel}: missing or not a regular file")
            continue
        actual = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode("ascii")
        if actual != value:
            problems.append(f"{rel}: content differs from its RECORD hash")
        else:
            verified += 1
    return verified, problems


def compute_identity(env: Path, project: BackendProject, *, distributions: Sequence[str] | None = None) -> EnvIdentity:
    """The T0 identity of ``env`` (D.10.6). Raises :class:`IdentityMismatch` when a RECORD entry does not verify, a
    guarded source file is missing or unlisted, or a distribution is absent. Imports nothing from the environment."""
    kind = backend_kind(project.backend)
    primary = kind.primary
    if distributions is None:
        distributions = kind.watched
    sp = site_packages(env)
    dists: dict[str, DistIdentity] = {}
    problems: list[str] = []
    record_hashes: dict[str, str] = {}
    for name in distributions:
        info = _dist_info(sp, name)
        record = _read_regular(info / "RECORD", env)
        verified, issues = _verify_record(info, sp, env, record)
        problems.extend(f"{name}: {p}" for p in issues)
        if name == primary:
            record_hashes = {rel: d for rel, d, _s in _record_rows(record)}
        dists[name] = DistIdentity(name, _metadata_version(info, env), hashlib.sha256(record).hexdigest(),
                                   _direct_url(info, env), verified)
    guarded: dict[str, str] = {}
    pinned = pinned_source(project)
    if pinned is not None and primary in dists and dists[primary].source != pinned:
        # identity is the observed commit from PEP 610, never the version string the fork shares (D.11.2, R-49)
        got = dists[primary].source
        problems.append(f"{primary} PEP 610 source is {got.get('kind')} {got.get('repo', '')}@{got.get('commit', '')[:12]}, "
                        f"not the pinned {pinned['repo']}@{pinned['commit'][:12]}")
    if primary in dists:
        for module in kind.guarded_modules:
            rel = module.replace(".", "/") + ".py"
            if not record_hashes.get(rel):
                problems.append(f"guarded source {rel} is not listed with a hash in the {primary} RECORD")
                continue
            try:
                guarded[rel] = hashlib.sha256(_read_regular(sp / rel, env)).hexdigest()
            except (IdentityMismatch, OSError):
                problems.append(f"guarded source {rel} is missing")
    task_files: dict[str, str] = {}
    for rel_dir in kind.task_dirs:
        try:
            task_files[rel_dir] = task_files_sha256(sp / rel_dir, env)
        except (IdentityMismatch, OSError):
            problems.append(f"task package {rel_dir} is missing")
    if problems:
        shown = "; ".join(problems[:5]) + (f"; and {len(problems) - 5} more" if len(problems) > 5 else "")
        raise IdentityMismatch(f"the backend environment does not match its RECORD files: {shown}")
    return EnvIdentity(project.lock_sha256, dists, guarded, primary, task_files)


def task_files_sha256(directory: Path, env: Path) -> str:
    """``"sha256:<hex>"`` of JCS ``{"files": {posix relative path: sha256}}`` over every regular file under
    ``directory`` (``__pycache__`` and symlinks excluded): the same value as
    ``agentprov_backend_inspect.identity.task_files_sha256`` (D-663; a backend test pins the algorithm)."""
    from agentprov.io.canonical import jcs_bytes

    if directory.is_symlink() or not directory.is_dir():
        raise IdentityMismatch(f"{directory.name}: not a directory")
    files: dict[str, str] = {}
    for root, dirs, names in os.walk(directory, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__" and not (Path(root) / d).is_symlink())
        for name in sorted(names):
            path = Path(root) / name
            if path.is_symlink() or not path.is_file():
                continue
            files[path.relative_to(directory).as_posix()] = hashlib.sha256(_read_regular(path, env)).hexdigest()
    return "sha256:" + hashlib.sha256(jcs_bytes({"files": files})).hexdigest()


def check_against_marker(identity: EnvIdentity, marker: Mapping[str, Any], project: BackendProject) -> None:
    """The T0 identity must equal what the build recorded, and the marker's lock must be the checkout's lock."""
    if marker.get("status") != "complete":
        raise BackendUnavailable("the backend environment build did not complete; run 'agentprov backends build "
                                 f"{project.backend}' again")
    if marker.get("backend") != project.backend:
        raise IdentityMismatch("the marker names another backend")
    if marker.get("lock_sha256") != project.lock_sha256:
        raise IdentityMismatch("the marker's lock_sha256 differs from backends/<b>/uv.lock in this checkout")
    if marker.get("commit") != project.commit:
        raise IdentityMismatch("the marker's commit differs from the project's pinned commit")
    recorded = marker.get("t0_identity")
    if not isinstance(recorded, Mapping):
        raise IdentityMismatch("the marker records no T0 identity")
    current = identity.to_json()
    built_files = recorded.get("guarded_files")
    if isinstance(built_files, Mapping) and set(built_files) != set(current["guarded_files"]):
        # the guarded-module list of this checkout differs from the one the environment was built under (for example
        # D-656 added anthropic_llm.py): not tampering, but the build record cannot vouch for the new modules
        raise IdentityMismatch(f"T0 identity mismatch: the guarded-source list changed since this environment was "
                               f"built; rebuild it with 'agentprov backends build {project.backend}'")
    for key in ("lock_sha256", "guarded_files"):
        if recorded.get(key) != current[key]:
            raise IdentityMismatch(f"T0 identity mismatch: {key} differs from the build record")
    if recorded.get("task_files") != current.get("task_files"):
        raise IdentityMismatch("T0 identity mismatch: task_files differs from the build record")
    rec_dists = recorded.get("distributions") or {}
    for name, dist in current["distributions"].items():
        before = rec_dists.get(name) if isinstance(rec_dists, Mapping) else None
        if not isinstance(before, Mapping):
            raise IdentityMismatch(f"T0 identity mismatch: {name} is not in the build record")
        for key in ("version", "record_sha256", "source"):
            if before.get(key) != dist[key]:
                raise IdentityMismatch(f"T0 identity mismatch: {name} {key} differs from the build record")


def safe_backend(value: Any) -> str:
    return value if isinstance(value, str) and value in BACKEND_IDS else "unknown"


def check_hello(hello: Mapping[str, Any], identity: EnvIdentity, marker: Mapping[str, Any] | None,
                backend: str | None = None) -> None:
    """Cross-check ``hello_ok`` (D.11.3 rule 1): the worker's report must equal T0's own digests and, for the members
    T0 cannot compute, the build-time record; with ``backend``, the backend the worker selected
    (``hello_ok.worker.backend``) must be it. Raises :class:`IdentityMismatch` (exit 3)."""
    ident = hello.get("identity")
    if not isinstance(ident, Mapping):
        raise IdentityMismatch("hello_ok carries no identity")
    worker_info = hello.get("worker")
    if backend is not None and isinstance(worker_info, Mapping) and worker_info.get("backend", backend) != backend:
        raise IdentityMismatch(f"IdentityMismatch: the worker runs the {safe_backend(worker_info.get('backend'))} "
                               f"backend, not {backend}")
    bench = identity.distributions.get(identity.primary)
    pairs: list[tuple[str, Any, Any]] = [("lock_sha256", ident.get("lock_sha256"), identity.lock_sha256)]
    for digest in identity.task_files.values():  # Inspect (D-663): the worker reports the digest T0 computed itself
        pairs.append(("task_files_sha256", ident.get("task_files_sha256"), digest))
    if bench is not None:
        pairs += [
            ("record_digest", ident.get("record_digest"), bench.record_sha256),
            ("source", ident.get("source"), bench.source),
            ("version_reported", ident.get("version_reported"), bench.version),
        ]
    if marker is not None:
        built = marker.get("hello_identity")
        if not isinstance(built, Mapping):
            raise IdentityMismatch("the marker records no build-time hello identity")
        kind = BACKEND_KINDS.get(str(backend if backend is not None else marker.get("backend")), BACKEND_KINDS["agentdojo"])
        pairs += [(key, ident.get(key), built.get(key)) for key in kind.hello_keys]
        python = marker.get("python")
        worker = hello.get("worker")
        if isinstance(worker, Mapping) and worker.get("python") != python:
            pairs.append(("worker.python", worker.get("python"), python))
    for key, reported, expected in pairs:
        if reported != expected:
            raise IdentityMismatch(f"IdentityMismatch: hello_ok {key} differs from the T0 digests")
