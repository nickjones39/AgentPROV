"""``CaptureSession``: one ``capture/0.1`` session per cell attempt (D.10.1, D.10.2; C.13).

The session owns the ``agentprov_capture.log.CaptureLog`` writer and implements the ``CaptureHooks`` protocol of
D.10.1, which the harness elements (pass recorder, executor mirror, recording runtime, LLM spans, recording attack)
call. It writes into a session staging directory (C.13.1; the phase-8 contract):

* ``raw/capture/<session>.capture.jsonl`` -- the hash-chained event log;
* ``raw/blobs/sha256/<hex[0:2]>/<hex>`` -- content-addressed blobs (wire bodies, pass dumps, snapshots, tracebacks);
* ``raw/capture/<session>.native.json`` -- the stock TraceLogger JSON, moved there unchanged from the transient
  TraceLogger directory ``raw/native-tmp/`` once the stock runner has finished with it (D.10.10 item 1).

Benchmark values are converted to JSON and encoded under C.11.3 (``_jsonval``) before they enter an event. Nothing
here decides an outcome or an accounting verdict (C.12.4): the session records.

The session is also referred to as ``runner.CaptureSession`` (it is re-exported there, D.10.1).
"""

from __future__ import annotations

import json
import secrets
import time
import traceback as _tb
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from agentprov_backend._jsonval import encode_value, escape_text, to_jsonable

__all__ = ["CaptureSession", "INLINE_RETURN_MAX", "serialise_messages", "uuid7"]

#: A tool's native return is recorded inline in ``tool.result.returned`` up to this many bytes of JSON, else as a blob.
INLINE_RETURN_MAX = 2048
CAPTURE_VERSION = "0.1"
CANON = "jcs-rfc8785"


def uuid7() -> str:
    """A UUIDv7 (RFC 9562): 48-bit Unix milliseconds, version 7, variant 10, 74 random bits."""
    ms = time.time_ns() // 1_000_000
    rand = int.from_bytes(secrets.token_bytes(10), "big")
    rand_a = rand >> 62 & 0xFFF
    rand_b = rand & ((1 << 62) - 1)
    value = (ms & ((1 << 48) - 1)) << 80 | 0x7 << 76 | rand_a << 64 | 0b10 << 62 | rand_b
    h = f"{value:032x}"
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


def _tracelogger_default(o: Any) -> Any:
    # exactly the `default` of agentdojo 0.1.35 TraceLogger.save (logging.py:256)
    from pydantic import BaseModel

    return o.model_dump() if isinstance(o, BaseModel) else o


def serialise_messages(messages: Sequence[Any]) -> tuple[bytes, bool]:
    """The pass's native message list as JSON bytes, serialised the way the stock TraceLogger serialises its
    ``messages`` member (``json.dumps`` with its ``default``; insertion order; Python float spelling; ASCII), without
    indentation. Returns ``(bytes, exact)``; ``exact`` is False when that failed and a JSON-mode dump was used."""
    try:
        return json.dumps(list(messages), default=_tracelogger_default).encode("ascii"), True
    except (TypeError, ValueError):
        return json.dumps(to_jsonable(list(messages))).encode("ascii"), False


class CaptureSession:
    """One capture session (one cell attempt). See the module docstring for the files it writes."""

    def __init__(
        self,
        session_dir: Path,
        *,
        session_id: str | None = None,
        attempt: int = 0,
        redactor: Any = None,
        clock: Callable[[], Any] | None = None,
        mono_ns: Callable[[], int] | None = None,
        notify: Callable[[str, Mapping[str, Any]], None] | None = None,
        env_snapshots: bool = True,
    ) -> None:
        self.dir = Path(session_dir)
        self.session = session_id or uuid7()
        self.ex = "ex_" + self.session
        self.attempt = attempt
        self.env_snapshots = env_snapshots
        self._redactor = redactor
        self._clock = clock
        self._mono_ns = mono_ns
        self._notify = notify
        self._log: Any = None
        self._closed_head: str | None = None
        self._n_call = 0
        self._n_occ = 0
        self._n_pass = 0
        self._pass: int | None = None
        self._pass_before: dict[int, Any] = {}
        self._actors: set[str] = set()
        self._observed: dict[str, dict[str, int]] = {}
        self._runtime: dict[str, dict[str, Any]] = {}
        self.current_occ: str | None = None
        self.current_span: Any = None
        self.last_messages: Sequence[Any] = []
        self.problems: list[str] = []
        self.final_status: str | None = None
        self.pipeline_errors = 0
        #: the active defence gate (``defences._GateContext``) while a gate executor runs; the recording runtime
        #: reports its calls to it
        self.gate: Any = None
        #: tool messages -> their occurrence id (``bind_message``); the message object is kept so its id is not reused
        self._message_occ: dict[int, tuple[Any, str]] = {}

    # ------------------------------------------------------------------ paths

    @property
    def capture_label(self) -> str:
        return f"raw/capture/{self.session}.capture.jsonl"

    @property
    def native_label(self) -> str:
        return f"raw/capture/{self.session}.native.json"

    @property
    def capture_path(self) -> Path:
        return self.dir / self.capture_label

    @property
    def blobs_dir(self) -> Path:
        return self.dir / "raw" / "blobs"

    @property
    def native_tmp_dir(self) -> Path:
        return self.dir / "raw" / "native-tmp"

    @property
    def started(self) -> bool:
        return self._log is not None

    @property
    def closed(self) -> bool:
        return self._closed_head is not None

    @property
    def current_pass(self) -> int | None:
        return self._pass

    @property
    def events(self) -> int:
        """Events written so far (the writer's count: redaction flag notes included)."""
        return 0 if self._log is None else int(self._log.n_events)

    @property
    def poisoned(self) -> bool:
        """A failed redaction scan or write poisoned the log: nothing more can be written; ``close`` seals it
        ``errored`` (C.13.10 item 6)."""
        return self._log is not None and bool(self._log.poisoned)

    @property
    def redactor(self) -> Any:
        return self._redactor

    # ------------------------------------------------------------------ writing

    def _open(self) -> None:
        from agentprov_capture.log import CaptureLog

        self.capture_path.parent.mkdir(parents=True, exist_ok=True)
        self.blobs_dir.mkdir(parents=True, exist_ok=True)
        kwargs: dict[str, Any] = {"blobs_dir": self.blobs_dir}
        if self._clock is not None:
            kwargs["clock"] = self._clock
        if self._mono_ns is not None:
            kwargs["mono_ns"] = self._mono_ns
        if self._redactor is not None:
            kwargs["redactor"] = self._redactor
        self._log = CaptureLog(self.capture_path, self.session, **kwargs)

    def emit(self, type_: str, data: dict[str, Any], *, actor: str | None = None, in_pass: bool = True) -> int:
        if self._log is None:
            raise RuntimeError("capture session not started")
        if actor is not None and actor not in self._actors:
            actor = None
        return int(self._log.emit(type_, data, pass_=self._pass if in_pass else None, actor=actor))

    def put_blob(self, data: bytes, media: str, *, non_content: bool | None = None) -> dict[str, Any]:
        if self._log is None:
            raise RuntimeError("capture session not started")
        return self._log.put_blob(bytes(data), media, non_content=non_content)

    def put_json_blob(self, value: Any) -> dict[str, Any]:
        import rfc8785

        return self.put_blob(rfc8785.dumps(encode_value(to_jsonable(value))), "application/json")

    def step(self, kind: str, **meta: Any) -> None:
        """A droppable live-feedback step (MN N.1.14): metadata only, never evidence."""
        if self._notify is None:
            return
        try:
            self._notify(kind, {"pass": self._pass, **meta})
        except Exception:  # noqa: BLE001 - feedback never breaks capture
            pass

    def next_call(self) -> str:
        call = f"c{self._n_call}"
        self._n_call += 1
        return call

    def next_occ(self) -> str:
        occ = f"o{self._n_occ}"
        self._n_occ += 1
        return occ

    # ------------------------------------------------------------------ lifecycle (D.10.1)

    def start(self, header: Mapping[str, Any]) -> None:
        """Emit ``session.start``, ``instrumentation`` and ``identity`` (C.13.3 order), then the header's notes.

        ``header`` keys: ``cell``, ``backend``, ``runtime``, ``actors``, ``config_sha256``, ``instrumentation`` (list
        of items), ``identity`` (the event data), and optionally ``notes`` (list of ``(ns, kind, payload)``)."""
        from agentprov_capture import __version__ as capture_version

        if self._log is not None:
            raise RuntimeError("capture session already started")
        self._open()
        self._actors = set(header["actors"])
        data = {
            "capture": CAPTURE_VERSION,
            "session": self.session,
            "ex": self.ex,
            "attempt": self.attempt,
            "cell": header["cell"],
            "writer": {"dist": "agentprov-capture", "version": capture_version},
            "backend": dict(header["backend"]),
            "runtime": dict(header["runtime"]),
            "actors": header["actors"],
            "config_sha256": header["config_sha256"],
        }
        self.emit("session.start", data, in_pass=False)
        self.emit("instrumentation", {"items": list(header["instrumentation"])}, in_pass=False)
        self.emit("identity", dict(header["identity"]), in_pass=False)
        for ns, kind, payload in header.get("notes", ()):
            self.note(ns, kind, payload)
        self.step("capture", event="start")

    def hooks(self) -> CaptureSession:
        return self

    def span(self, role: str, actor: str, messages: Sequence[Any] = ()) -> Any:
        from agentprov_backend.gateway import LlmSpan

        return LlmSpan(self, role, actor, messages)

    def add_native(self, label: str, media: str = "application/json") -> None:
        """``native.log``: the TraceLogger JSON at ``label`` (relative to the session directory)."""
        import hashlib

        data = (self.dir / label).read_bytes()
        self.emit("native.log", {"path": label, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)},
                  in_pass=False)

    def record_error(self, exc: BaseException, *, fatal: bool, where: str = "cell") -> None:
        """``error``: type, escaped message and the traceback as a ``text/x-python-traceback`` blob. Both are
        non-content surfaces for the redactor (C.13.10 item 9: literal secrets, URLs, key patterns, home path and host
        name are redacted there). Nothing is written once the log is poisoned."""
        if where == "pipeline":
            self.pipeline_errors += 1
        if self.poisoned or self._log is None:
            return
        text = "".join(_tb.format_exception(type(exc), exc, exc.__traceback__))
        tb_blob = self.put_blob(text.encode("utf-8", "backslashreplace"), "text/x-python-traceback", non_content=True)
        message = escape_text(str(exc))
        self.emit("error", {"where": where, "exception": {"type": type(exc).__name__, "message": message},
                            "traceback": tb_blob, "fatal": bool(fatal)}, in_pass=where == "pipeline")
        self.step("capture", event="error", fatal=bool(fatal))

    def declare_observed(self, item_id: str, keys: Sequence[str]) -> None:
        self._observed.setdefault(item_id, {k: 0 for k in keys})

    def count(self, item_id: str, key: str, n: int = 1) -> None:
        if item_id in self._observed:
            self._observed[item_id][key] = self._observed[item_id].get(key, 0) + n

    def observed(self) -> dict[str, dict[str, int]]:
        return {k: dict(v) for k, v in self._observed.items()}

    def close(self, status: str) -> str:
        """``session.end`` (closing the chain); returns the chain head. Emits the per-execution observed counts of the
        declared instrumentation items first (note ``agentdojo/instrumentation_observed``; D.10.10 item 6)."""
        if self._closed_head is not None:
            return self._closed_head
        if self._log is None:
            raise RuntimeError("capture session not started")
        if self._observed and not self.poisoned:
            self.note("agentdojo", "instrumentation_observed", self.observed())
        self._pass = None
        if self.poisoned:
            status = "errored"
        self.final_status = status
        self._closed_head = self._log.close(status)
        self.step("capture", event="end", status=status)
        return self._closed_head

    # ------------------------------------------------------------------ CaptureHooks (D.10.1)

    def _snapshot(self, dump: Any) -> dict[str, Any] | None:
        from agentprov_capture import envstate

        if not self.env_snapshots:
            return None
        return self.put_blob(envstate.snapshot(dump), "application/json")

    def pass_start(self, env_state: Any) -> int:
        """``pass.start``: ``envstate.digest`` (E-2) of the environment dump, plus the snapshot blob."""
        from agentprov_capture import envstate

        index = self._n_pass
        self._n_pass += 1
        self._pass = index
        self.last_messages = []
        dump = to_jsonable(env_state)
        env = dict(envstate.digest(dump))
        snap = self._snapshot(dump)
        if snap is not None:
            env["snapshot"] = snap
        self._pass_before[index] = dump
        self.emit("pass.start", {"env": env})
        self.step("pass_start")
        return index

    def pass_end(self, pass_index: int, native_messages: Any, env_state: Any, *, aborted: bool) -> None:
        self._pass = pass_index
        from agentprov_capture import envstate

        data, exact = serialise_messages(native_messages)
        blob = self.put_blob(data, "application/json")
        dump = to_jsonable(env_state)
        env = envstate.end_env(self._pass_before.pop(pass_index, dump), dump, snapshot_ref=self._snapshot(dump))
        self.emit("pass.end", {"aborted": bool(aborted), "messages": blob, "env": env})
        if not exact:
            self.note("agentdojo", "messages_serialisation_fallback", {"pass": pass_index})
        self.step("pass_end", aborted=bool(aborted))
        self._pass = None

    def tool_dispatch(self, occ: str, provider_call_id: str | None, name: str, requested: Any,
                      args_raw: str | None, at: tuple[int, int] | None) -> None:
        data: dict[str, Any] = {
            "occ": occ,
            "provider_call_id": provider_call_id if isinstance(provider_call_id, str) else None,
            "name": name if isinstance(name, str) else str(name),
            "args": encode_value(to_jsonable(requested)),
        }
        if args_raw is not None:
            data["args_raw"] = args_raw
        if at is not None:
            data["at"] = {"message": at[0], "call": at[1]}
        self.emit("tool.dispatch", data, actor="env")
        self.step("tool_call", occ=occ, phase="dispatch")

    def tool_result(self, occ: str, status: str, args_effective: Any, returned: Any, rendered: str,
                    model_visible: str, error: str | None, decided_by: str | None = None,
                    *, exception: Mapping[str, str] | None = None, has_returned: bool = True) -> None:
        data: dict[str, Any] = {"occ": occ, "status": status, "rendered": rendered, "model_visible": model_visible,
                                "error": error}
        if args_effective is not None:
            data["args_effective"] = encode_value(to_jsonable(args_effective))
        if has_returned:
            value = encode_value(to_jsonable(returned))
            import rfc8785

            raw = rfc8785.dumps(value)
            data["returned"] = value if len(raw) <= INLINE_RETURN_MAX else self.put_blob(raw, "application/json")
        if exception is not None:
            data["exception"] = dict(exception)
        if decided_by is not None:
            data["decided_by"] = decided_by
        self.emit("tool.result", data, actor="env")
        self.step("tool_call", occ=occ, phase="result", status=status)

    def fixture(self, kind: str, vector: str | None, content: Any) -> None:
        data: dict[str, Any] = {"kind": kind, "content": encode_value(to_jsonable(content))}
        if vector is not None:
            data["vector"] = vector
        self.emit("fixture", data, actor="attacker", in_pass=False)

    def outcome(self, judgements: Sequence[Mapping[str, Any]], declared_semantics: Any | None) -> None:
        data: dict[str, Any] = {"judgements": [dict(j) for j in judgements]}
        if declared_semantics is not None:
            data["declared_semantics"] = encode_value(to_jsonable(declared_semantics))
        self.emit("outcome", data, actor="bench", in_pass=False)
        for j in judgements:
            self.step("judgement", name=j.get("name"), origin=j.get("origin"))

    def note(self, ns: str, kind: str, payload: Any) -> None:
        self.emit("note", {"ns": ns, "kind": kind, "payload": encode_value(to_jsonable(payload))})

    def decision(self, actor: str, subject: Mapping[str, Any], verdict: str, *, reason: str | None = None,
                 original: Mapping[str, Any] | None = None, subtype: str | None = None) -> None:
        """``decision`` (C.13.3): a defence or guard verdict the harness observed. ``subject`` is ``{occ}``,
        ``{call}`` or ``{at: {message, call}}``; ``original`` is a blob reference (the content before a
        ``redact``/``modify``)."""
        data: dict[str, Any] = {"actor": actor, "subject": dict(subject), "verdict": verdict}
        if reason is not None:
            data["reason"] = reason
        if original is not None:
            data["original"] = dict(original)
        if subtype is not None:
            data["subtype"] = subtype
        self.emit("decision", data, actor=actor)
        self.step("decision", verdict=verdict, actor=actor)

    # ------------------------------------------------------------------ element support

    def bind_message(self, message: Any, occ: str) -> None:
        """Remember which occurrence produced a tool message (a defence's decision about it names the occurrence)."""
        self._message_occ[id(message)] = (message, occ)

    def occ_of(self, message: Any) -> str | None:
        bound = self._message_occ.get(id(message))
        return bound[1] if bound is not None and bound[0] is message else None

    def observe_messages(self, messages: Sequence[Any]) -> None:
        """The latest message list a harness element saw (used for a pass cut by an exception)."""
        self.last_messages = messages

    def runtime_record(self, record: dict[str, Any]) -> None:
        if self.current_occ is not None:
            self._runtime[self.current_occ] = record

    def take_runtime_record(self, occ: str) -> dict[str, Any] | None:
        return self._runtime.pop(occ, None)
