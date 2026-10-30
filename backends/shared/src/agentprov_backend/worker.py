"""The T2 backend worker: ``<env>/bin/python -I -B -m agentprov_backend.worker`` (D.11.3, protocol
``agentprov-backend/0.1``; G.6.3).

Channels. stdin and stdout carry UTF-8 JSON Lines, one message per line, at most 1 MiB, each with
``"v": "agentprov-backend/0.1"``. At start-up the worker moves the protocol channel to a private duplicate of file
descriptor 1 and points fd 1 (and ``sys.stdout``) at stderr, so any library print goes to stderr and stdout carries
the protocol only. Evidence never travels over the pipe: capture logs, blobs and native logs are written into the
session directory, and ``cell_done`` reports their labels and digests. One cell runs at a time.

Messages (D.11.3; extensions marked +):

=========  ==========  ===================================================================================
direction  op          fields
=========  ==========  ===================================================================================
P -> W     hello       ``nonce``, ``expect{commit, lock_sha256, record_sha256, guarded_sources{}}`` (accepted and
                       not used: the parent checks; the worker only reports what it observes)
W -> P     hello_ok    ``nonce``, ``identity`` (``BenchmarkIdentity``), ``worker{python, agentprov_backend_version,
                       agentprov_capture_version, backend+}`` (``backend``: ``agentdojo``, ``autodojo`` or ``agentdyn``,
                       from the installed distribution's PEP 610 source, ``runner.select_backend``)
P -> W     plan +      ``req``, ``plan_toml`` (the run-plan file's text): the worker expands it
W -> P     plan_ok +   ``req``, ``plan`` (``RunPlan``: ``plan_sha256``, ``cells``, ``agent``, ``backend_config``)
W -> P     plan_refused + ``req``, ``error{type, message}``
P -> W     catalogue + ``req``, ``benchmark_version`` (optional; default the backend's): D-652
W -> P     catalogue_ok + ``req``, ``catalogue`` (``agentprov-backend-catalogue/0.1``: ``backend``,
                       ``benchmark_version``, ``benchmark_versions``, ``suites[{name, user_tasks, injection_tasks}]``,
                       ``attacks[{name, dos, refused, needs}]``; names and ids only)
W -> P     catalogue_refused + ``req``, ``error{type, message}``
P -> W     run_cell    ``req``, ``cell`` (``CellSpec``), ``agent`` (``AgentConfig``, no secrets), ``session{ex,
                       attempt, dir+}``, ``plan_sha256``, ``backend_config+``, ``attack_env`` (an object; unused by
                       the agentdojo backend; the autodojo backend reads ``AUTODOJO_CACHE_label`` and
                       ``AUTODOJO_VARIANT``, ``agentprov_backend.autodojo``), ``local_model`` (an object or
                       absent: T0's observation of a local model before this cell, recorded as the header note
                       ``agentdojo/local_model``; D-693)
W -> P     progress    ``req``, ``pass``, ``events`` (count only), after each pass
W -> P     step        ``req``, ``seq``, ``kind`` (pass_start, pass_end, model_call, tool_call, judgement,
                       capture) + metadata only (pass index, call/occurrence ids, statuses); droppable
W -> P     cell_done   ``req``, ``status``, ``artefacts[{label, sha256, role}]``, ``capture_head``, ``outcome``
P -> W     shutdown    --
P -> W     probe +     ``req``, ``agent``, ``session{ex, dir}``: the D.10.9 preflight probe as its own capture session
W -> P     probe_done + ``req``, ``status``, ``capture_head``, ``results{reachable, roles_accepted, roles,
                       roles_reason, http_status, params{configured, transmitted, not_transmitted}, tool_calls}``
                       (``roles``: ``runner.roles_verdict``, D-291), ``artefacts`` (all role
                       ``supporting``/``blob``: a probe session is never mapped to an execution)
W -> P     fatal       ``error{type, message}`` (message escaped); the worker then exits with status 2
=========  ==========  ===================================================================================

``session.dir`` (+) is the session's staging directory; without it the worker's working directory is the session
directory (the one-session-per-worker layout of G.6.3). ``session.ex`` is ``"ex_" + <session UUIDv7>`` minted by the
parent (the staging directory is named after it); without it the worker mints one.

Artefact roles: ``capture_log``, ``native_log``, ``blob``, ``supporting`` (anything else the worker wrote under
``raw/``). Files outside ``raw/`` (for example the parent's scripted-transport file) are not reported.

The network guard is installed from ``AGENTPROV_BLOCK_NETWORK=1`` before any benchmark import. Secrets: the redactor
is built from the values of the variables in the worker's environment whose names match the scrub pattern, plus the
agent's key variable (C.13.5); their names, never their values, appear anywhere.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import queue
import sys
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any, BinaryIO

PROTOCOL = "agentprov-backend/0.1"
MAX_LINE = 1024 * 1024
FATAL_EXIT = 2

__all__ = ["MAX_LINE", "PROTOCOL", "ProtocolError", "Worker", "decode_message", "encode_message", "main"]


class ProtocolError(ValueError):
    """A message that does not follow ``agentprov-backend/0.1``."""


def _reject_constant(name: str) -> Any:
    raise ProtocolError(f"non-standard JSON constant {name}")


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in items:
        if k in out:
            raise ProtocolError(f"duplicate key {k!r}")
        out[k] = v
    return out


def decode_message(line: bytes) -> dict[str, Any]:
    """Strictly decode one protocol line (bounded, UTF-8, an object with ``v`` and ``op``)."""
    if len(line) > MAX_LINE:
        raise ProtocolError("message exceeds 1 MiB")
    if not line.endswith(b"\n"):
        raise ProtocolError("message is not newline-terminated")
    try:
        msg = json.loads(line[:-1].decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_reject_constant)
    except UnicodeDecodeError:
        raise ProtocolError("message is not UTF-8") from None
    except ProtocolError:
        raise
    except ValueError as exc:
        raise ProtocolError(f"message is not JSON ({exc.__class__.__name__})") from None
    if not isinstance(msg, dict):
        raise ProtocolError("message is not an object")
    if msg.get("v") != PROTOCOL:
        raise ProtocolError(f"message protocol is not {PROTOCOL}")
    if not isinstance(msg.get("op"), str):
        raise ProtocolError("message has no op")
    return msg


def encode_message(op: str, **fields: Any) -> bytes:
    """One protocol line: compact JSON, ASCII-escaped, LF-terminated, ``v`` and ``op`` first-class members."""
    msg = {"v": PROTOCOL, "op": op, **fields}
    data = json.dumps(msg, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii") + b"\n"
    if len(data) > MAX_LINE:
        raise ProtocolError(f"{op} message exceeds 1 MiB")
    return data


def _escape(text: str) -> str:
    from agentprov_backend._jsonval import escape_text

    return escape_text(text, limit=2000)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def list_artefacts(session_dir: Path, capture_label: str, native_label: str) -> list[dict[str, str]]:
    raw = session_dir / "raw"
    out: list[dict[str, str]] = []
    if not raw.is_dir():
        return out
    for p in sorted(raw.rglob("*")):
        if not p.is_file() or p.is_symlink():
            continue
        label = p.relative_to(session_dir).as_posix()
        if label == capture_label:
            role = "capture_log"
        elif label == native_label:
            role = "native_log"
        elif label.startswith("raw/blobs/sha256/"):
            role = "blob"
        else:
            role = "supporting"
        out.append({"label": label, "sha256": _sha256_file(p), "role": role})
    return out


class Outbox:
    """The protocol writer: one writer thread draining a bounded queue, so live feedback never back-pressures the
    capture (MN N.1.14; DECISIONS D-8). ``step`` and ``progress`` messages are dropped when the queue is full (counted
    in ``dropped``); every other message is enqueued blocking. Order is preserved."""

    def __init__(self, out: BinaryIO, maxsize: int = 4096) -> None:
        self.out = out
        self.queue: queue.Queue[bytes | None] = queue.Queue(maxsize)
        self.dropped = 0
        self.error: BaseException | None = None
        self.thread = threading.Thread(target=self._run, name="agentprov-protocol-writer", daemon=True)
        self.thread.start()

    def _run(self) -> None:
        while True:
            data = self.queue.get()
            try:
                if data is None:
                    return
                if self.error is None:
                    self.out.write(data)
                    self.out.flush()
            except BaseException as exc:  # noqa: BLE001 - a closed pipe ends output, not the capture
                self.error = exc
            finally:
                self.queue.task_done()

    def put(self, data: bytes, *, droppable: bool) -> None:
        if droppable:
            try:
                self.queue.put_nowait(data)
            except queue.Full:
                self.dropped += 1
        else:
            self.queue.put(data)

    def flush(self) -> None:
        self.queue.join()

    def close(self) -> None:
        self.queue.put(None)
        self.thread.join(timeout=30)


class Worker:
    def __init__(self, out: BinaryIO, *, environ: Mapping[str, str] | None = None) -> None:
        self.outbox = Outbox(out)
        self.environ = dict(os.environ if environ is None else environ)
        self.backend: Any = None
        self.identity: Any = None
        self._step_seq = 0
        self._req: Any = None

    # ------------------------------------------------------------------ output

    def send(self, op: str, **fields: Any) -> None:
        self.outbox.put(encode_message(op, **fields), droppable=op in ("step", "progress"))

    def _notify(self, kind: str, meta: Mapping[str, Any]) -> None:
        safe = {k: v for k, v in meta.items() if v is None or isinstance(v, (bool, int, str))}
        for k, v in list(safe.items()):
            if isinstance(v, str) and len(v) > 64:
                safe[k] = v[:64]
        self.send("step", req=self._req, seq=self._step_seq, kind=kind, **safe)
        self._step_seq += 1
        if kind == "pass_end" and self._session is not None:
            self.send("progress", req=self._req, **{"pass": meta.get("pass"), "events": self._session.events})

    _session: Any = None

    # ------------------------------------------------------------------ ops

    def op_hello(self, msg: Mapping[str, Any]) -> None:
        import agentprov_capture

        import agentprov_backend
        from agentprov_backend.runner import select_backend

        nonce = msg.get("nonce")
        if not isinstance(nonce, str) or not nonce:
            raise ProtocolError("hello needs a nonce")
        self.backend = select_backend()
        self.identity = self.backend.identity()
        self.send("hello_ok", nonce=nonce, identity=self.identity.to_json(),
                  worker={"python": platform.python_version(),
                          "agentprov_backend_version": agentprov_backend.__version__,
                          "agentprov_capture_version": agentprov_capture.__version__,
                          "backend": self.backend.backend_id})

    def op_plan(self, msg: Mapping[str, Any]) -> None:
        from agentprov_backend.runner import load_plan, select_backend

        req = msg.get("req")
        text = msg.get("plan_toml")
        if not isinstance(text, str):
            raise ProtocolError("plan needs plan_toml")
        try:
            plan = load_plan(text, backend=self.backend if self.backend is not None else select_backend())
        except ValueError as exc:
            self.send("plan_refused", req=req, error={"type": type(exc).__name__, "message": _escape(str(exc))})
            return
        self.send("plan_ok", req=req, plan=plan.to_json())

    def op_catalogue(self, msg: Mapping[str, Any]) -> None:
        from agentprov_backend.runner import select_backend

        req = msg.get("req")
        version = msg.get("benchmark_version")
        if version is not None and not isinstance(version, str):
            raise ProtocolError("catalogue benchmark_version must be a string")
        backend = self.backend if self.backend is not None else select_backend()
        try:
            document = backend.catalogue(version)
        except ValueError as exc:
            self.send("catalogue_refused", req=req, error={"type": type(exc).__name__, "message": _escape(str(exc))})
            return
        self.send("catalogue_ok", req=req, catalogue=document)

    def op_run_cell(self, msg: Mapping[str, Any]) -> None:
        from agentprov_backend.runner import NOTE_MAX_BYTES, AgentConfig, CaptureSession, CellSpec, _json_size, build_redactor

        if self.backend is None:
            raise ProtocolError("run_cell before hello")
        req = msg.get("req")
        if not isinstance(req, (str, int)) or isinstance(req, bool):
            raise ProtocolError("run_cell needs a req id")
        cell = CellSpec.from_json(msg.get("cell") or {})
        agent = AgentConfig.from_json(msg.get("agent") or {})
        sess = msg.get("session") or {}
        if not isinstance(sess, Mapping):
            raise ProtocolError("session must be an object")
        ex = sess.get("ex")
        session_id = None
        if ex is not None:
            if not isinstance(ex, str) or not ex.startswith("ex_"):
                raise ProtocolError("session.ex must be 'ex_<uuid>'")
            session_id = ex[3:]
        attempt = sess.get("attempt", 0)
        if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 0:
            raise ProtocolError("session.attempt must be a non-negative integer")
        directory = Path(sess["dir"]) if isinstance(sess.get("dir"), str) else Path.cwd()
        if not directory.is_absolute() or not directory.is_dir():
            raise ProtocolError("session.dir must be an existing absolute directory")
        backend_config = msg.get("backend_config") or {}
        if not isinstance(backend_config, Mapping):
            raise ProtocolError("backend_config must be an object")
        plan_digest = msg.get("plan_sha256")
        attack_env = msg.get("attack_env") or {}
        if not isinstance(attack_env, Mapping):
            raise ProtocolError("attack_env must be an object")
        local_model = msg.get("local_model")
        if local_model is not None and (not isinstance(local_model, Mapping)
                                        or _json_size(local_model) > NOTE_MAX_BYTES):
            raise ProtocolError("local_model must be an object of at most 64 KiB")
        redactor = build_redactor(self.environ, agent)
        session = CaptureSession(directory, session_id=session_id, attempt=attempt, redactor=redactor,
                                 notify=self._notify)
        self._req, self._session, self._step_seq = req, session, 0
        try:
            result = self.backend.execute(cell, agent, session, backend_config=backend_config,
                                          plan_sha256=plan_digest if isinstance(plan_digest, str) else None,
                                          environ=self.environ, attack_env=attack_env, local_model=local_model)
        finally:
            self._session = None
        artefacts = list_artefacts(directory, session.capture_label, session.native_label)
        self.send("cell_done", req=req, status=result.status, artefacts=artefacts, capture_head=result.capture_head,
                  outcome=dict(result.outcome) if result.outcome is not None else None)
        self._req = None

    def op_probe(self, msg: Mapping[str, Any]) -> None:
        from agentprov_backend.runner import AgentConfig, CaptureSession, build_redactor, run_probe

        if self.backend is None:
            raise ProtocolError("probe before hello")
        req = msg.get("req")
        agent = AgentConfig.from_json(msg.get("agent") or {})
        sess = msg.get("session") or {}
        if not isinstance(sess, Mapping):
            raise ProtocolError("session must be an object")
        directory = Path(sess["dir"]) if isinstance(sess.get("dir"), str) else Path.cwd()
        if not directory.is_absolute() or not directory.is_dir():
            raise ProtocolError("session.dir must be an existing absolute directory")
        ex = sess.get("ex")
        if ex is not None and (not isinstance(ex, str) or not ex.startswith("ex_")):
            raise ProtocolError("session.ex must be 'ex_<uuid>'")
        session = CaptureSession(directory, session_id=ex[3:] if ex else None,
                                 redactor=build_redactor(self.environ, agent))
        result = run_probe(agent, session, self.backend, environ=self.environ)
        artefacts = list_artefacts(directory, session.capture_label, session.native_label)
        for a in artefacts:
            if a["role"] == "capture_log":
                a["role"] = "supporting"
        self.send("probe_done", req=req, status=result.pop("status"), capture_head=result.pop("capture_head"),
                  results=result, artefacts=artefacts)

    # ------------------------------------------------------------------ loop

    def serve(self, stdin: BinaryIO) -> int:
        try:
            return self._serve(stdin)
        finally:
            self.outbox.flush()
            self.outbox.close()

    def _serve(self, stdin: BinaryIO) -> int:
        while True:
            line = stdin.readline(MAX_LINE + 1)
            if not line:
                return 0
            try:
                msg = decode_message(line)
                op = msg["op"]
                if op == "hello":
                    self.op_hello(msg)
                elif op == "plan":
                    self.op_plan(msg)
                elif op == "catalogue":
                    self.op_catalogue(msg)
                elif op == "run_cell":
                    self.op_run_cell(msg)
                elif op == "probe":
                    self.op_probe(msg)
                elif op == "shutdown":
                    return 0
                else:
                    raise ProtocolError(f"unknown op {op!r}")
            except BaseException as exc:  # noqa: BLE001 - anything unexpected is fatal, reported, and exits
                try:
                    self.send("fatal", error={"type": type(exc).__name__, "message": _escape(str(exc))})
                except Exception:  # noqa: BLE001
                    pass
                import traceback

                traceback.print_exc(file=sys.stderr)
                return FATAL_EXIT


def main(worker_cls: type[Worker] = Worker) -> int:
    """Serve the protocol on stdin/stdout. ``worker_cls`` lets a backend package outside this one (the Inspect harness,
    D-662) reuse the channel set-up and the network guard with its own ``op_*`` methods."""
    # 1. the protocol channel is a private duplicate of fd 1; fd 1 and sys.stdout now go to stderr
    proto_fd = os.dup(1)
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    out = os.fdopen(proto_fd, "wb", buffering=0)
    # 2. the network guard, before any benchmark import
    from agentprov_backend.testing import netguard

    netguard.install_from_env()
    worker = worker_cls(out)  # type: ignore[arg-type]
    return worker.serve(sys.stdin.buffer)


if __name__ == "__main__":
    sys.exit(main())
