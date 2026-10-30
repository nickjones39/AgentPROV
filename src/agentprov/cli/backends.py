"""``agentprov backends build {agentdojo,autodojo,agentdyn}`` (MN N.2.10, N.2.1b; M.1.7 rules 2-4; G.6.2; D.11.2).

Builds ``$AGENTPROV_HOME/envs/<backend>-<commit8>/`` from ``backends/<backend>/`` of the repository checkout:

1. ``uv sync --locked --no-config`` (:func:`agentprov.cli.live.envs.uv_sync_argv`) with ``UV_PROJECT_ENVIRONMENT`` set
   to that directory and a scrubbed environment (no ``UV_*`` but the cache and interpreter locations, no secret-named
   variable; :func:`~agentprov.cli.live.envs.uv_environment`). ``--exclude-newer`` and the no-build list are passed
   explicitly because ``--no-config`` drops the project's ``[tool.uv]`` (M.1.7 note). Without ``--allow-network`` the
   sync runs ``--offline``: it succeeds only from the uv cache and never touches the network (N.2.1b(2)).
2. The T0 identity of the result (RECORD verification, guarded source files, PEP 610 source, lock digest).
3. A preliminary marker, then one ``hello`` to the built worker, whose identity is recorded (the members T0 cannot
   compute without importing) and cross-checked against the T0 digests.
4. The ``sandbox-exec`` feasibility probe (G.4.10; ``not_applicable`` off macOS).
5. The final marker ``AGENTPROV_ENV.json`` (``status: complete``), written last and atomically: a directory without a
   complete marker is an unfinished build, and ``run`` refuses it.

**AutoDojo** (D.11.2; ``autodojo-<commit8>`` from the pinned fork commit). The same steps, plus: the installed fork's
PEP 610 ``direct_url.json`` must name the pinned repository, commit and subdirectory (``envs.pinned_source``; else
``IdentityMismatch``, exit 3), the fork's extra guarded modules are hashed, ``hello_ok.worker.backend`` must be
``autodojo``, and NLTK ``punkt_tab`` is provisioned from the recipe ``[tool.agentprov.nltk]`` of
``backends/autodojo/pyproject.toml`` (``envs.provision_nltk``: verified fetch cache, network only with
``--allow-network``, the zip kept unextracted under ``<env>/nltk_data``). The marker records ``fork``, ``nltk`` and
``nltk_sha256`` (``null`` when not provisioned, with a notice: a filter-defence run on such an environment is refused).

**AgentDyn** (D-680..D-682; ``agentdyn-<commit8>`` from the pinned AgentDyn commit). As AutoDojo, without NLTK: the
PEP 610 source must name ``https://github.com/SaFo-Lab/AgentDyn`` at the pinned commit (no subdirectory),
``agentdojo.agent_pipeline.agent_pipeline`` is hashed as AgentDyn's extra guarded module, and
``hello_ok.worker.backend`` must be ``agentdyn``. The choice ``agentdyn`` is offered together with the registry's
``BACKENDS["agentdyn"]`` (the GUI's build form lists ``sorted(BACKENDS)`` and a parity test compares the two).

``--offline-check`` verifies an existing build without network (marker, lock, RECORD and guarded files, the PEP 610 pin,
the NLTK zip's digest, the ``hello`` identity). It writes only the ``hello`` probe's scratch directories under
``$AGENTPROV_HOME`` (removed afterwards) and, like a run, holds the environment's use lock and live staging, so it is
refused while the environment is being rebuilt. ``--dry-run`` prints the plan and writes
nothing. ``.env`` is never passed to ``uv``; neither build needs a value from it, so it is not read (``--env-file`` is
accepted and ignored with a notice).
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from agentprov.cli.common import CommandResult, Context, redact_personal, safe_text
from agentprov.errors import AgentProvError, BackendUnavailable
from agentprov.progress import ProgressEvent

__all__ = ["register", "run_backends"]

HELLO_TIMEOUT_S: Final = 300.0


class UvMissing(AgentProvError):
    code = "backend.uv_missing"
    exit_code = 3


def register(sub: Any, shared: argparse.ArgumentParser) -> None:
    p = sub.add_parser(
        "backends",
        parents=[shared],
        help="backend environments (build)",
        description="Backend environments for live runs (N.2.10).",
        allow_abbrev=False,
    )
    p.set_defaults(command="backends", handler=run_backends, feedback=False)
    actions = p.add_subparsers(dest="backends_action", metavar="ACTION")
    b = actions.add_parser(
        "build",
        parents=[shared],
        help="build $AGENTPROV_HOME/envs/<backend>-<commit8>/ with uv sync --locked --no-config",
        description="Build a backend environment from backends/<backend>/ (N.2.10). Without --allow-network the sync "
        "runs offline from the uv cache.",
        allow_abbrev=False,
    )
    from agentprov.cli.live.envs import BACKEND_IDS

    b.add_argument("backend", choices=list(BACKEND_IDS), metavar="BACKEND", help=", ".join(BACKEND_IDS))
    b.add_argument("--offline-check", action="store_true", help="verify an existing build; no network, no writes")
    b.add_argument("--allow-network", action="store_true", help="let uv download packages (otherwise --offline)")
    b.add_argument("--defence-assets", metavar="ID[,ID...]",
                   help="also provision these registry defences' pinned code from the fetch cache into the environment "
                        "(D-670; backends/shared/src/agentprov_backend/defences.toml)")
    b.add_argument("--defence-source", metavar="DIR",
                   help="read --defence-assets' pinned code from this local tree instead of the fetch cache; each file "
                        "is accepted only by its pinned sha256 and git blob id (no network)")
    b.add_argument("--env-file", metavar="PATH", help="the .env file (not read by the agentdojo build)")
    b.add_argument("--dry-run", action="store_true", help="print the plan; run and write nothing")


def run_backends(ctx: Context) -> CommandResult:
    from agentprov.cli.common import CliUsageError

    args = ctx.args
    if getattr(args, "backends_action", None) != "build":
        raise CliUsageError("agentprov backends: an action is required (build)")
    if args.offline_check and args.dry_run:
        raise CliUsageError("agentprov backends build: --offline-check and --dry-run are exclusive")
    from agentprov.cli.live import envs

    root = envs.repository_root()
    project = envs.backend_project(args.backend, root)
    home = envs.agentprov_home(ctx.env)
    env = envs.env_dir(project, home)
    result = CommandResult(dry_run=bool(args.dry_run))
    result.counters = {}
    if args.offline_check:
        from agentprov.io.locks import backend_use, held, staging_use

        # G6a, as a run: refused while the environment is being rebuilt; the hello probe uses live staging (D #14)
        command = "backends build --offline-check"
        with held(backend_use(home, project.env_name, command=command), staging_use(home, command=command)):
            return _offline_check(project, env, home, result)
    uv = shutil.which("uv", path=ctx.env.get("PATH"))
    offline = not args.allow_network
    assets = _defence_assets(args, project, root)
    groups = ["defences"] if any(entry.python for entry in assets) else []  # D-672: the backend's optional group
    argv = envs.uv_sync_argv(project, offline=offline, uv=uv or "uv", groups=groups)
    if args.env_file:
        result.notices.append(f"--env-file: the {args.backend} build needs no value from .env; it was not read")
    if args.dry_run:
        for entry in assets:
            if entry.files:
                result.output(f"  defence {entry.id}: copy {len(entry.files)} pinned file(s) of {entry.repo}@"
                              f"{(entry.commit or '')[:12]} from the fetch cache into <env>/agentprov_defences/{entry.id}/")
            for w in entry.weights:
                result.output(f"  defence {entry.id}: copy {len(w['files'])} pinned weights file(s) of {w['repo']}@"
                              f"{w['revision'][:12]} from the fetch cache into <env>/agentprov_defences/hf/")
            if entry.python:
                result.output(f"  defence {entry.id}: install the dependency group defences ({', '.join(entry.python)})")
        return _dry_run(project, env, argv, offline, result)
    if uv is None:
        raise UvMissing("uv is not on PATH; install uv (https://docs.astral.sh/uv/) to build backend environments")
    from agentprov.io.locks import backend_build, held, staging_use

    # G6a: one build per environment, never under a live run; the build's hello probe uses live staging
    with backend_build(home, project.env_name), held(staging_use(home, command="backends build")):
        return _build(project, env, home, argv, offline, result, ctx, assets)


def _dry_run(project: Any, env: Path, argv: list[str], offline: bool, result: CommandResult) -> CommandResult:
    from agentprov.cli.live.envs import SCRUBBED_UV_VARIABLES, UV_KEPT

    result.output(f"backend {project.backend}: environment {redact_personal(str(env))}")
    result.output(f"  commit8 {project.commit8} (from {project.commit8_source}); lock sha256 {project.lock_sha256}")
    result.output("  would run: " + " ".join(safe_text(a, 300) for a in argv))
    result.output(f"  UV_PROJECT_ENVIRONMENT={redact_personal(str(env))}; every other UV_* variable is dropped except "
                  f"{', '.join(UV_KEPT)} (G.6.2 list: {', '.join(SCRUBBED_UV_VARIABLES)})")
    result.output("  network: " + ("none (uv --offline: the build uses the uv cache only)" if offline else "allowed (--allow-network)"))
    if project.commit is not None:
        result.output(f"  identity: PEP 610 direct_url.json of agentdojo must name {project.fork_repo}@{project.commit}")
    if project.nltk is not None:
        from agentprov.cli.live.envs import nltk_recipe

        recipe = nltk_recipe(project)
        result.output("  NLTK punkt_tab: " + ("not pinned in [tool.agentprov.nltk]; nltk_sha256 will be null" if recipe is None
                      else f"pinned sha256 {recipe.sha256[:16]}...; from the verified cache"
                      + ("" if offline else " (fetched if absent)") + " into <env>/nltk_data, unextracted"))
    recipe = envs_dataset_recipe(project)
    if recipe is not None:
        result.output(f"  dataset: {recipe['repo']}@{recipe['revision'][:12]} ({len(recipe['files'])} files, pinned "
                      "sha256) from the fetch cache into <env>/share/agentprov/datasets, offline only")
    result.output("  then: T0 identity, hello identity, sandbox-exec feasibility probe, marker AGENTPROV_ENV.json")
    result.notices.append("dry run: nothing was run and nothing was written")
    return result


def envs_dataset_recipe(project: Any) -> dict[str, Any] | None:
    from agentprov.cli.live.envs import dataset_recipe

    return dataset_recipe(project)


def _python_version(python: Path) -> str:
    proc = subprocess.run(  # noqa: S603 - the built environment's interpreter
        [str(python), "-I", "-B", "-c", "import platform,sys;sys.stdout.write(platform.python_version())"],
        capture_output=True, env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}, timeout=60, check=False,
    )  # fmt: skip
    version = proc.stdout.decode("ascii", "replace").strip()
    if proc.returncode != 0 or not version:
        raise BackendUnavailable("the built environment's interpreter does not start")
    return version


def _uv_version(uv: str) -> str | None:
    try:
        proc = subprocess.run([uv, "--version"], capture_output=True, timeout=30, check=False)  # noqa: S603
    except (OSError, subprocess.TimeoutExpired):
        return None
    return proc.stdout.decode("utf-8", "replace").strip() or None


def _write_marker(env: Path, marker: dict[str, Any]) -> None:
    from agentprov.cli.live.envs import ENV_MARKER
    from agentprov.io.atomic import atomic_write_bytes

    atomic_write_bytes(env / ENV_MARKER, (json.dumps(marker, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))


def hello_once(env: Path, home: Path, expect: dict[str, Any], *, nltk_data: str | None = None,
               worker_module: str = "agentprov_backend.worker") -> dict[str, Any]:
    """Spawn the built worker, send one ``hello`` and shut it down; returns ``hello_ok``. Uses a scratch staging and
    T2 home under ``$AGENTPROV_HOME`` (removed afterwards)."""
    from agentprov.cli.live.envs import env_python
    from agentprov.cli.live.worker import BackendWorker, WorkerSpec, make_private_dir, worker_environment

    scratch = home / "staging" / f"build-{uuid.uuid4().hex}"
    t2home = home / "t2home" / scratch.name
    make_private_dir(scratch)
    make_private_dir(t2home)
    worker = BackendWorker(WorkerSpec(
        argv=[str(env_python(env)), "-I", "-B", "-m", worker_module],
        env=worker_environment(home=t2home, block_network=True, nltk_data=nltk_data), cwd=scratch,
        stderr_path=scratch / "worker.stderr.log",
    ))  # fmt: skip
    try:
        worker.start()
        nonce = uuid.uuid4().hex
        reply = worker.request("hello", "hello_ok", HELLO_TIMEOUT_S, nonce=nonce, expect=expect)
        if reply.get("nonce") != nonce:
            raise BackendUnavailable("the worker answered hello with another nonce")
        return reply
    except AgentProvError as exc:
        raise BackendUnavailable(f"the built worker did not answer hello: {exc}") from None
    finally:
        worker.shutdown()
        shutil.rmtree(scratch, ignore_errors=True)
        shutil.rmtree(t2home, ignore_errors=True)


def _defence_assets(args: Any, project: Any, root: Path) -> list[Any]:
    """The registry entries named by ``--defence-assets`` (usage error for an unknown id, another backend's entry, or an
    entry with nothing this build can provision yet)."""
    from agentprov.cli.common import CliUsageError
    from agentprov.cli.live.defences import load_registry, registry_path

    names = [n for n in (args.defence_assets or "").split(",") if n]
    if not names:
        return []
    try:
        registry = load_registry(registry_path(root))
    except ValueError as exc:
        raise CliUsageError(f"agentprov backends build: {exc}") from None
    out = []
    for name in names:
        entry = registry.get(name)
        if entry is None or project.backend not in entry.backends:
            raise CliUsageError(f"agentprov backends build: --defence-assets {safe_text(name, 60)} is not a registry "
                                f"defence of the {project.backend} backend")
        if entry.provider not in ("provisioned", "port") and not entry.weights and not entry.python:
            pending = entry.raw.get("assets_pending")
            raise CliUsageError(f"agentprov backends build: {name} has no pinned code, weights or modules to provision"
                                + (f" ({safe_text(str(pending), 200)})" if pending else ""))
        out.append(entry)
    return out


def _build(project: Any, env: Path, home: Path, argv: list[str], offline: bool, result: CommandResult,
           ctx: Context, assets: list[Any] | None = None) -> CommandResult:
    from agentprov.cli.live import envs, sandbox

    progress = ctx.progress  # no stderr feedback; --progress-file gets main's start line, one unit per stage, the end
    clock = [time.monotonic()]

    def begin(stage: str) -> None:
        progress.emit(ProgressEvent("stage", stage=stage, fields={"phase": "begin"}))  # 0.2 (D-393)
        progress.emit(ProgressEvent("unit_start", unit=stage))

    begin("uv_sync")

    def step(stage: str, following: str | None = None) -> None:  # N.1.14: build stages are the units of a build
        now = time.monotonic()
        progress.emit(ProgressEvent("unit_done", unit=stage, status="ok", duration_s=now - clock[0]))
        progress.emit(ProgressEvent("stage", stage=stage, duration_s=now - clock[0], fields={"phase": "end"}))
        clock[0] = now
        if following is not None:
            begin(following)

    env.parent.mkdir(parents=True, exist_ok=True)
    marker_path = env / envs.ENV_MARKER
    if marker_path.exists():
        marker_path.unlink()  # a rebuild is unfinished until its own marker is written
    proc = subprocess.run(  # noqa: S603 - uv with an explicit argv; no shell
        argv, env=envs.uv_environment(ctx.env, env), capture_output=True, cwd=project.root, check=False,
    )  # fmt: skip
    if proc.returncode != 0:
        tail = proc.stderr.decode("utf-8", "replace").strip().splitlines()[-3:]
        for line in tail:
            result.error(f"  uv: {safe_text(line, 300)}")
        hint = " (offline: the uv cache lacks a locked package; rerun with --allow-network)" if offline else ""
        raise BackendUnavailable(f"uv sync --locked failed for backends/{project.backend}{hint}")
    step("uv_sync", "identity")
    python = envs.env_python(env)
    version = _python_version(python)
    identity = envs.compute_identity(env, project)
    kind = envs.backend_kind(project.backend)
    wheel = envs.lock_wheel(project, kind.primary)
    marker: dict[str, Any] = {
        "format": envs.MARKER_FORMAT,
        "backend": project.backend,
        "status": "building",
        "env_name": project.env_name,
        "commit": project.commit,
        "commit8": project.commit8,
        "commit8_source": project.commit8_source,
        "lock_sha256": project.lock_sha256,
        "lock_wheel": wheel,
        "python": version,
        "nltk_sha256": None,
        "built_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "uv": {"version": _uv_version(argv[0]), "argv": [redact_personal(a) for a in argv[1:]], "offline": offline},
        "t0_identity": identity.to_json(),
    }
    if project.commit is not None:
        marker["fork"] = envs.pinned_source(project)
    if project.dataset is not None:  # Inspect (D-663): the pinned dataset, offline from the fetch cache
        marker["dataset"] = envs.provision_dataset(env, project, ctx.env)
    step("identity", "nltk" if project.nltk is not None else "hello")
    nltk_data: str | None = None
    if project.nltk is not None:
        nltk = envs.provision_nltk(env, project, ctx.env, allow_network=not offline)
        marker["nltk"] = nltk
        marker["nltk_sha256"] = nltk.get("sha256")
        if nltk["status"] == "provisioned":
            nltk_data = str(envs.nltk_data_dir(env))
        else:
            result.notices.append(f"NLTK punkt_tab not provisioned ({nltk['status']}): nltk_sha256 is null, so a "
                                  "filter-defence run on this environment is refused")
        step("nltk", "hello")
    if assets:
        from agentprov.cli.live.defences import provision, provision_weights
        from agentprov.raw.fetch import resolve_cache_dir

        cache_dir = resolve_cache_dir(env=ctx.env)
        marker["defence_assets"] = {}
        marker["groups"] = ["defences"] if any(entry.python for entry in assets) else []
        for entry in assets:
            try:
                record: dict[str, Any] = {}
                if entry.files:
                    source = Path(ctx.args.defence_source) if getattr(ctx.args, "defence_source", None) else None
                    record = provision(env, entry, cache_dir=cache_dir, allow_network=not offline, source_dir=source)
                if entry.weights:
                    record["weights"] = provision_weights(env, entry, cache_dir=cache_dir, allow_network=not offline)
                marker["defence_assets"][entry.id] = record
            except ValueError as exc:
                raise BackendUnavailable(f"defence {entry.id}: {safe_text(str(exc), 300)}") from None
    _write_marker(env, marker)  # the worker reads lock_sha256 from it (D.10.10 item 3); status "building" until the end
    hello = hello_once(env, home, identity.expect(project.commit), nltk_data=nltk_data, worker_module=kind.worker_module)
    envs.check_hello(hello, identity, None, backend=project.backend)
    marker["hello_identity"] = hello["identity"]
    marker["hello_worker"] = hello.get("worker")
    step("hello", "sandbox_probe")
    probe = sandbox.probe(python, home / "staging")
    step("sandbox_probe", "marker")
    marker["sandbox_probe"] = probe
    marker["sandbox_status"] = probe["status"]
    marker["status"] = "complete"
    _write_marker(env, marker)
    step("marker")
    result.counters = {"files_verified": sum(d.files_verified for d in identity.distributions.values())}
    result.output(f"agentprov backends build: {project.env_name} built at {redact_personal(str(env))}")
    primary = identity.distributions[kind.primary]
    result.output(f"  python {version}; {kind.primary} {primary.version} "
                  f"(RECORD sha256 {primary.record_sha256[:16]}...); lock {project.lock_sha256[:16]}...")
    if "dataset" in marker:
        result.output(f"  dataset {marker['dataset']['repo']}@{marker['dataset']['revision'][:12]}: "
                      f"{len(marker['dataset']['files'])} files provisioned (sha256 verified)")
    for rel_dir, digest in identity.task_files.items():
        result.output(f"  task files {rel_dir}: {digest[:23]}...")
    if project.commit is not None:
        result.output(f"  fork {project.fork_repo}@{project.commit} (PEP 610 direct_url.json verified)")
    for did, record in (marker.get("defence_assets") or {}).items():
        if record.get("files"):
            result.output(f"  defence {did}: {len(record['files'])} pinned file(s) of {record['repo']}@{record['commit'][:12]}")
        for w in record.get("weights", []):
            result.output(f"  defence {did}: {len(w['files'])} pinned weights file(s) of {w['repo']}@{w['revision'][:12]}")
    if project.nltk is not None:
        result.output(f"  NLTK punkt_tab: {marker['nltk']['status']}"
                      + (f" (sha256 {marker['nltk_sha256'][:16]}...)" if marker["nltk_sha256"] else ""))
    result.output(f"  sandbox-exec feasibility probe: {probe['status']}" + (f" ({safe_text(probe['reason'], 200)})" if probe.get("reason") else ""))
    result.notices.append(f"sandbox-exec feasibility probe: {probe['status']} ({platform.system()})")
    return result


def _check_defence_assets(env: Path, marker: dict[str, Any], project: Any) -> None:
    """``--offline-check``: every provisioned defence the marker records is still its pinned bytes."""
    from agentprov.cli.live.defences import load_registry, registry_path, verify_provisioned

    recorded = marker.get("defence_assets") or {}
    if not recorded:
        return
    registry = load_registry(registry_path(project.root))
    for did in sorted(recorded):
        entry = registry.get(did)
        problem = "it is no longer in the registry" if entry is None else verify_provisioned(env, entry)
        if problem is not None:
            raise BackendUnavailable(f"defence {did}: {safe_text(problem, 300)}; rebuild with --defence-assets {did}")


def _offline_check(project: Any, env: Path, home: Path, result: CommandResult) -> CommandResult:
    from agentprov.cli.live import envs

    marker = envs.read_marker(env)
    if marker is None:
        raise BackendUnavailable(f"no built environment {project.env_name} (or no marker); run 'agentprov backends build "
                                 f"{project.backend}'")
    identity = envs.compute_identity(env, project)
    envs.check_against_marker(identity, marker, project)
    nltk_data = envs.check_nltk(env, marker)
    envs.check_dataset(env, project, marker)
    _check_defence_assets(env, marker, project)
    hello = hello_once(env, home, identity.expect(project.commit), nltk_data=nltk_data,
                       worker_module=envs.backend_kind(project.backend).worker_module)
    envs.check_hello(hello, identity, marker, backend=project.backend)
    result.counters = {"files_verified": sum(d.files_verified for d in identity.distributions.values())}
    result.output(f"agentprov backends build --offline-check: {project.env_name} verified (marker, lock, RECORD, guarded "
                  "files, hello identity" + (", NLTK punkt_tab" if nltk_data else "")
                  + (", task files, dataset" if project.dataset is not None else "") + ")")
    if project.nltk is not None and nltk_data is None:
        result.notices.append("this environment has no NLTK punkt_tab (nltk_sha256 null): filter-defence runs are refused")
    result.notices.append(f"sandbox-exec feasibility probe recorded: {safe_text(str(marker.get('sandbox_status')), 40)}")
    return result
