"""The Inspect backend worker: ``agentprov-backend/0.1`` with Inspect-shaped plans (D-662, D-663; design §2).

Run as ``<env>/bin/python -I -B -m agentprov_backend_inspect.worker`` (``agentprov run`` under the T2 controls). It
subclasses the shared :class:`agentprov_backend.worker.Worker` and reuses its channel set-up and network guard through
``worker.main(worker_cls=...)``. Ops:

==========  ============================================================================================================
``hello``   ``hello_ok.identity``: ``inspect_ai`` (version, PEP 610 source, RECORD digest), the benchmark distribution,
            ``task_files_sha256`` of the task package, the provisioned dataset's digests, the lock, Python, platform
``plan``    ``plan_toml`` (:mod:`.plan`) -> ``plan_ok.plan`` (the cells, ``plan_sha256``) or ``plan_refused``
``catalogue`` ``agentprov-inspect-catalogue/0.1`` (:mod:`.catalogue`) -> ``catalogue_ok`` or ``catalogue_refused``
``run_cell`` the campaign's message (``agentprov.cli.live.campaign``): ``cell`` (a cell of ``plan_ok``), ``agent``
            (T0's agent table), ``session{ex, attempt, dir}``, ``plan_sha256``, ``backend_config`` (``plan_ok``'s) ->
            one Inspect ``eval()`` of the cell's samples; ``cell_done{status, artefacts, capture_head, outcome}``
==========  ============================================================================================================

A cell's session directory holds ``raw/capture/<session>.capture.jsonl`` (the wire log, D-665 (b)), its blobs, and
``raw/inspect/<timestamp>_<task>_<id>.eval`` (Inspect's own log, role ``native_log``: the artefact the import maps).

Inspect settings the harness fixes, never the plan (design §2.2): ``log_model_api=True``, ``log_format="eval"``,
``display="none"``, ``retry_on_error=0`` (a re-run is a new attempt), ``fail_on_error=False`` (a failed sample is kept
and imported as such), ``score=True``, no model cache, ``log_dir`` inside the session. The dataset comes from the
environment, digest-checked, never from the network; ``INSPECT_EVALS_CACHE_DIR`` is set under the worker's home before
``inspect_evals`` is first imported (it reads the variable once, at import).
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import os
import platform
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from agentprov_backend.worker import ProtocolError, Worker, _escape, list_artefacts
from agentprov_backend.worker import main as _shared_main

import agentprov_backend_inspect
from agentprov_backend_inspect.benchmarks import for_backend
from agentprov_backend_inspect.plan import (
    InspectCell,
    InspectPlan,
    PlanError,
    load_plan,
    run_spec,
    split_ids_from_dataset,
)

__all__ = ["INSTRUMENTATION", "InspectWorker", "main"]

#: D.10.7-shaped items every Inspect session declares (design §4.3). ``recorded``: what the session holds about it.
INSTRUMENTATION: tuple[dict[str, Any], ...] = (
    {"id": "inspect.harness_settings@2", "kind": "harness_policy", "recorded": "full",
     "detail": "log_model_api=True, log_format=eval, retry_on_error=0, fail_on_error=False, no model cache, "
               "display=none, max_retries=1 per model call for the agent and every judge with the provider SDK's own "
               "retries off (D-740); set by the harness, never by the plan"},
    {"id": "inspect.recording_http_client@1", "kind": "behaviour_preserving", "recorded": "full",
     "detail": "each model's provider client sends through the shared async recording transport; the header shows "
               "model_args.http_client = null"},
    {"id": "inspect.dataset_offline@1", "kind": "harness_policy", "recorded": "full",
     "detail": "the pinned dataset is provisioned from the environment, digest-checked; no download"},
)
SCRIPTED_ITEM: dict[str, Any] = {"id": "inspect.transport_scripted@1", "kind": "test_only", "recorded": "full",
                                 "detail": "scripted transport: no network, no key; the session is test_only"}

_HEX64 = re.compile(r"[0-9a-f]{64}")  # plan_ok's plan_sha256: bare hex, as the shared runner's


def _backend_id() -> str:
    """The backend this environment was built for: the ``backend`` member of ``<sys.prefix>/AGENTPROV_ENV.json``
    (written by ``agentprov backends build``, as the lock digest is); ``AGENTPROV_INSPECT_BACKEND`` overrides it in
    development environments that have no marker."""
    import json

    value = os.environ.get("AGENTPROV_INSPECT_BACKEND", "")
    if value:
        return value
    marker = Path(sys.prefix) / "AGENTPROV_ENV.json"
    try:
        doc = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        doc = None
    backend = doc.get("backend") if isinstance(doc, dict) else None
    if not isinstance(backend, str) or not backend.startswith("inspect-"):
        raise ProtocolError("the environment marker names no Inspect backend")
    return backend


def _cache_dir() -> Path:
    """The worker's ``INSPECT_EVALS_CACHE_DIR``: under its (T2) home, set before ``inspect_evals`` is imported."""
    path = Path(os.environ.get("HOME", ".")).resolve() / "inspect_evals_cache"
    os.environ["INSPECT_EVALS_CACHE_DIR"] = str(path)
    return path


class InspectWorker(Worker):
    def __init__(self, out: Any, *, environ: Mapping[str, str] | None = None) -> None:
        super().__init__(out, environ=environ)
        self.backend_id = _backend_id()
        self.bench = for_backend(self.backend_id)
        self.cache_dir = _cache_dir()
        self._provisioned: dict[str, str] | None = None

    # ------------------------------------------------------------------ helpers

    def _dataset(self) -> dict[str, str]:
        from agentprov_backend_inspect.provision import provision_session, verify_dataset

        if self._provisioned is None:
            target = self.cache_dir / self.bench.CACHE_SUBDIR
            if target.exists():
                self._provisioned = verify_dataset(target, self.bench.DATASET_FILES)
            else:
                self._provisioned = provision_session(self.bench, self.cache_dir)
        return self._provisioned

    def _split_ids(self) -> dict[str, list[str]]:
        from agentprov_backend_inspect.provision import env_dataset_dir

        return split_ids_from_dataset(self.bench, env_dataset_dir(self.bench))

    def _identity(self) -> dict[str, Any]:
        import importlib.metadata

        from agentprov_backend.identity import _dist_source, lock_digest, record_digest

        from agentprov_backend_inspect.identity import task_files_sha256
        from agentprov_backend_inspect.provision import env_dataset_dir, verify_dataset

        inspect_dist = importlib.metadata.distribution("inspect-ai")
        bench_dist = importlib.metadata.distribution(self.bench.PACKAGE)
        site = Path(str(bench_dist.locate_file("")))
        files_digest, n_files = task_files_sha256(site / self.bench.TASK_PACKAGE_DIR)
        lock, lock_source = lock_digest()
        return {
            "distribution": "inspect-ai", "version_reported": inspect_dist.version,
            "source": _dist_source(inspect_dist), "record_digest": record_digest(inspect_dist),
            "benchmark": {"distribution": self.bench.PACKAGE, "version": bench_dist.version,
                          "source": _dist_source(bench_dist), "record_digest": record_digest(bench_dist)},
            "task_files_sha256": files_digest, "task_files": n_files,
            "dataset": {"repo": self.bench.DATASET_REPO, "revision": self.bench.DATASET_REVISION,
                        "files": verify_dataset(env_dataset_dir(self.bench), self.bench.DATASET_FILES)},
            "lock_sha256": lock, "lock_source": lock_source,
            "python": platform.python_version(), "platform": platform.platform(),
        }

    def _load_plan(self, text: Any) -> InspectPlan:
        if not isinstance(text, str):
            raise ProtocolError("plan_toml must be a string")
        return load_plan(text, self.bench, self.backend_id, self._split_ids())

    # ------------------------------------------------------------------ ops

    def op_hello(self, msg: Mapping[str, Any]) -> None:
        import agentprov_backend
        import agentprov_capture

        nonce = msg.get("nonce")
        if not isinstance(nonce, str) or not nonce:
            raise ProtocolError("hello needs a nonce")
        self.backend = self
        self.identity = self._identity()
        self.send("hello_ok", nonce=nonce, identity=self.identity,
                  worker={"python": platform.python_version(),
                          "agentprov_backend_version": agentprov_backend.__version__,
                          "agentprov_capture_version": agentprov_capture.__version__,
                          "agentprov_backend_inspect_version": agentprov_backend_inspect.__version__,
                          "backend": self.backend_id})

    def op_plan(self, msg: Mapping[str, Any]) -> None:
        req = msg.get("req")
        try:
            plan = self._load_plan(msg.get("plan_toml"))
        except PlanError as exc:
            self.send("plan_refused", req=req, error={"type": type(exc).__name__, "message": _escape(str(exc))})
            return
        self.send("plan_ok", req=req, plan=plan.to_json())

    def op_catalogue(self, msg: Mapping[str, Any]) -> None:
        from agentprov_backend_inspect.catalogue import build_catalogue

        req = msg.get("req")
        try:
            document = build_catalogue(self.bench, self.backend_id)
        except ValueError as exc:
            self.send("catalogue_refused", req=req, error={"type": type(exc).__name__, "message": _escape(str(exc))})
            return
        self.send("catalogue_ok", req=req, catalogue=document)

    def op_run_cell(self, msg: Mapping[str, Any]) -> None:
        req = msg.get("req")
        if not isinstance(req, (str, int)) or isinstance(req, bool):
            raise ProtocolError("run_cell needs a req id")
        if self.identity is None:
            raise ProtocolError("run_cell before hello")
        try:
            plan, cell = run_spec(self.bench, self.backend_id, msg.get("backend_config"), msg.get("agent"),
                                  msg.get("cell"), self._split_ids())
        except PlanError as exc:
            raise ProtocolError(f"run_cell refused: {exc}") from None
        plan_sha256 = msg.get("plan_sha256")
        if not isinstance(plan_sha256, str) or not _HEX64.fullmatch(plan_sha256):
            raise ProtocolError("run_cell needs the plan_sha256 of plan_ok")
        sess = msg.get("session") or {}
        if not isinstance(sess, Mapping):
            raise ProtocolError("session must be an object")
        ex, attempt = sess.get("ex"), sess.get("attempt", 0)
        if not isinstance(ex, str) or not ex.startswith("ex_"):
            raise ProtocolError("session.ex must be 'ex_<uuid>'")
        if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 0:
            raise ProtocolError("session.attempt must be a non-negative integer")
        directory = Path(sess["dir"]) if isinstance(sess.get("dir"), str) else Path.cwd()
        if not directory.is_absolute() or not directory.is_dir():
            raise ProtocolError("session.dir must be an existing absolute directory")
        status, head, outcome, native = self._run(plan, cell, directory, ex[3:], attempt, plan_sha256)
        native_label = native.relative_to(directory).as_posix() if native is not None else ""
        session_label = f"raw/capture/{ex[3:]}.capture.jsonl"
        self.send("cell_done", req=req, status=status, artefacts=list_artefacts(directory, session_label, native_label),
                  capture_head=head, outcome=outcome)

    def op_probe(self, msg: Mapping[str, Any]) -> None:
        """The D.10.9 preflight probe through the cell's Inspect model and recording transport (D-742; replaces the
        shared op, whose AgentDojo LLM element this environment does not have). Its capture session has role
        ``supporting``: never mapped, never stored."""
        from agentprov_backend.session import CaptureSession

        from agentprov_backend_inspect.models import inspect_model_name
        from agentprov_backend_inspect.plan import model_spec
        from agentprov_backend_inspect.probe import PROBE_ITEM, run_probe

        if self.identity is None:
            raise ProtocolError("probe before hello")
        req = msg.get("req")
        agent = msg.get("agent") or {}
        try:
            spec = model_spec(agent, "agent")
        except PlanError as exc:
            raise ProtocolError(f"probe refused: {exc}") from None
        params = agent.get("params") if isinstance(agent, Mapping) else None
        params = dict(params) if isinstance(params, Mapping) else {}
        sess = msg.get("session") or {}
        if not isinstance(sess, Mapping):
            raise ProtocolError("session must be an object")
        directory = Path(sess["dir"]) if isinstance(sess.get("dir"), str) else Path.cwd()
        if not directory.is_absolute() or not directory.is_dir():
            raise ProtocolError("session.dir must be an existing absolute directory")
        ex = sess.get("ex")
        if ex is not None and (not isinstance(ex, str) or not ex.startswith("ex_")):
            raise ProtocolError("session.ex must be 'ex_<uuid>'")
        scripted = spec.transport == "scripted"
        session = CaptureSession(directory, session_id=ex[3:] if ex else None, redactor=self._redactor_for((spec,)),
                                 notify=self._notify)
        inspect_version = importlib.metadata.version("inspect-ai")
        lock = self.identity.get("lock_sha256") if isinstance(self.identity, Mapping) else None
        session.start({
            "cell": {"benchmark": self.bench.BENCHMARK, "task_id": "preflight_probe", "suite": "probe"},
            "backend": {"id": self.backend_id, "version": agentprov_backend_inspect.__version__},
            "runtime": {"lock_sha256": str(lock or "0" * 64), "python": platform.python_version(),
                        "platform": platform.platform()},
            "actors": {"agent": {"kind": "llm_agent", "model": {"requested": inspect_model_name(spec),
                                                               "endpoint": spec.endpoint}},
                       "harness": {"kind": "harness", "name": "inspect_ai"}},
            "config_sha256": "0" * 64,
            "instrumentation": [*INSTRUMENTATION, PROBE_ITEM, *([SCRIPTED_ITEM] if scripted else [])],
            "identity": {"agent": {"endpoint_host": "scripted.invalid" if scripted else _host(spec.base_url),
                                   "model_requested": inspect_model_name(spec), "provider": spec.endpoint,
                                   "sdk": {"name": "inspect_ai", "version": inspect_version}},
                         "benchmark": {"name": self.bench.BENCHMARK, "dist": self.bench.PACKAGE,
                                       "dist_version": importlib.metadata.version(self.bench.PACKAGE)},
                         "harness": {"dist": "inspect-ai", "version": inspect_version}},
        })
        status = "complete"
        try:
            result = run_probe(spec, params, session, session_dir=directory, environ=self.environ)
        except Exception as exc:  # noqa: BLE001 - recorded in the probe session (a model that cannot be built)
            session.record_error(exc, fatal=True, where="probe")
            status = "errored"
            result = {"reachable": False, "roles_accepted": False, "roles": "unknown", "roles_reason": "no_reply",
                      "http_status": None, "params": {"configured": params, "transmitted": {}, "not_transmitted": []},
                      "tool_calls": "error"}
        session.note("inspect", "preflight_result", result)
        head = session.close(status)
        artefacts = list_artefacts(directory, session.capture_label, session.native_label)
        for a in artefacts:
            if a["role"] == "capture_log":
                a["role"] = "supporting"
        self.send("probe_done", req=req, status=status, capture_head=head, results=result, artefacts=artefacts)

    # ------------------------------------------------------------------ the cell

    def _redactor(self, plan: InspectPlan) -> Any:
        return self._redactor_for((plan.agent, *plan.judges.values()))

    def _redactor_for(self, specs: tuple[Any, ...]) -> Any:
        import pwd
        import socket

        from agentprov_capture.redact import Redactor, Secret, secrets_from_environ

        secrets = secrets_from_environ(self.environ)
        for spec in specs:
            name = spec.api_key_env
            if name and self.environ.get(name) and name not in {s.name for s in secrets}:
                secrets.append(Secret(name, self.environ[name]))
        try:
            home: str | None = pwd.getpwuid(os.getuid()).pw_dir
        except (KeyError, OSError):
            home = None
        try:
            host: str | None = socket.gethostname()
        except OSError:
            host = None
        redactor = Redactor(secrets, home=home, host=host)
        short = [s.api_key_env for s in specs if s.api_key_env in redactor.ignored]
        if short:
            raise ProtocolError("an API key value is too short to be scanned for; refusing to run")
        return redactor

    def _run(self, plan: InspectPlan, cell: InspectCell, directory: Path, session_id: str, attempt: int,
             plan_sha256: str) -> tuple[str, str | None, dict[str, Any] | None, Path | None]:
        import importlib.metadata

        from agentprov_backend.session import CaptureSession

        from agentprov_backend_inspect.models import build_model, inspect_model_name
        from agentprov_backend_inspect.wire import WireObserver

        scripted = plan.agent.transport == "scripted"
        dataset = self._dataset()
        session = CaptureSession(directory, session_id=session_id, attempt=attempt, redactor=self._redactor(plan),
                                 notify=self._notify)
        judge_actors = {role: f"judge{i}" for i, role in enumerate(sorted(plan.judges))}
        actors: dict[str, Any] = {
            "agent": {"kind": "llm_agent", "model": {"requested": inspect_model_name(plan.agent),
                                                     "endpoint": plan.agent.endpoint}},
            "harness": {"kind": "harness", "name": "inspect_ai"},
            "benchmark": {"kind": "benchmark", "name": self.bench.BENCHMARK},
            **{actor: {"kind": "judge", "role": role, "model": {"requested": inspect_model_name(plan.judges[role]),
                                                                "endpoint": plan.judges[role].endpoint}}
               for role, actor in judge_actors.items()},
        }
        inspect_version = importlib.metadata.version("inspect-ai")
        bench_version = importlib.metadata.version(self.bench.PACKAGE)
        lock = self.identity.get("lock_sha256") if isinstance(self.identity, Mapping) else None
        instrumentation = [*INSTRUMENTATION, *([SCRIPTED_ITEM] if scripted else [])]
        session.start({
            "cell": {"benchmark": self.bench.BENCHMARK, "task_id": cell.cell_key, "suite": cell.task},
            "backend": {"id": self.backend_id, "version": agentprov_backend_inspect.__version__},
            "runtime": {"lock_sha256": str(lock or "0" * 64), "python": platform.python_version(),
                        "platform": platform.platform()},
            "actors": actors,
            "config_sha256": plan_sha256,
            "instrumentation": instrumentation,
            "identity": {
                "agent": {"endpoint_host": "scripted.invalid" if scripted else _host(plan.agent.base_url),
                          "model_requested": inspect_model_name(plan.agent), "provider": plan.agent.endpoint,
                          "sdk": {"name": "inspect_ai", "version": inspect_version}},
                "benchmark": {"name": self.bench.BENCHMARK, "dist": self.bench.PACKAGE, "dist_version": bench_version},
                "harness": {"dist": "inspect-ai", "version": inspect_version},
            },
            # T0 compares this note with hello_ok at ingest (agentprov.cli.live.staging.check_capture_identity)
            "notes": [("inspect", "identity_digests", dict(self.identity or {})),
                      ("inspect", "cell", {"task": cell.task, "params": dict(cell.params),
                                           "samples": list(cell.sample_ids), "plan_sha256": plan_sha256,
                                           "task_files_sha256": (self.identity or {}).get("task_files_sha256"),
                                           "dataset": dict(sorted(dataset.items()))})],
        })
        status, native, outcome = "errored", None, None
        try:
            agent = build_model(plan.agent, WireObserver(session, role="agent", actor="agent", configured={}),
                                session_dir=directory, environ=self.environ)
            judges = {role: build_model(spec, WireObserver(session, role="auxiliary", actor=judge_actors[role],
                                                           configured={}), session_dir=directory, environ=self.environ,
                                        role=role)
                      for role, spec in plan.judges.items()}
            native, outcome = self._eval(plan, cell, agent, judges, directory / "raw" / "inspect")
            # D-743: Inspect's log status stays "success" when a sample errors (fail_on_error=False), so a cell with an
            # errored sample is incomplete: T0 counts it inconclusive (exit 1) and the session says which samples
            errored = outcome.pop("errored_ids", None) or []
            if errored:
                session.note("inspect", "samples_errored", {"count": len(errored), "sample_ids": list(errored)})
            status = "complete" if outcome.get("status") == "success" and not errored else "incomplete"
        except Exception as exc:  # noqa: BLE001 - recorded in the session, reported as an errored cell
            session.record_error(exc, fatal=True)
        if native is not None:
            session.note("inspect", "native_log", {"label": native.relative_to(directory).as_posix(),
                                                   "sha256": hashlib.sha256(native.read_bytes()).hexdigest()})
        head = session.close(status)
        return status, head, outcome, native

    def _eval(self, plan: InspectPlan, cell: InspectCell, agent: Any, judges: Mapping[str, Any],
              log_dir: Path) -> tuple[Path, dict[str, Any]]:
        from inspect_ai import eval as inspect_eval

        from agentprov_backend_inspect.models import MAX_RETRIES

        log_dir.mkdir(parents=True, exist_ok=True)
        args = self.bench.task_args(dict(cell.params), dict(judges))
        logs = inspect_eval(
            cell.task, model=agent, task_args=args, sample_id=list(cell.sample_ids), epochs=plan.epochs,
            message_limit=plan.limits["message_limit"], token_limit=plan.limits["token_limit"],
            time_limit=plan.limits["time_limit_s"], max_connections=plan.max_connections,
            log_dir=str(log_dir), log_format="eval", display="none", log_model_api=True, retry_on_error=0,
            fail_on_error=False, score=True, max_retries=MAX_RETRIES,
        )
        if len(logs) != 1:
            raise RuntimeError(f"inspect eval wrote {len(logs)} logs, expected one")
        log = logs[0]
        written = sorted(log_dir.glob("*.eval"))
        if len(written) != 1:
            raise RuntimeError(f"{len(written)} .eval files in the session's log directory, expected one")
        samples = list(log.samples or [])
        errored = [str(s.id) for s in samples if getattr(s, "error", None) is not None]
        return written[0], {"status": str(log.status), "samples": len(samples), "samples_errored": len(errored),
                            "errored_ids": errored}


def _host(url: str | None) -> str:
    from urllib.parse import urlsplit

    return urlsplit(str(url or "")).hostname or "unknown"


def main() -> int:
    return _shared_main(worker_cls=InspectWorker)


if __name__ == "__main__":
    sys.exit(main())
