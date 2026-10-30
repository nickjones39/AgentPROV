"""Hostile and diagnostic job kinds for the worker tests (SEC-22; K.12.10). Never in the production table.

The pool merges :data:`TEST_JOB_KINDS` only when constructed with ``test_kinds=True`` (``--test-kinds`` on the
worker command line); a production CLI never sets it. Every function takes a :class:`JobContext` and either
returns counters or misbehaves on purpose (spin, hog, sleep, connect, spawn, write, oversized frames).
"""

from __future__ import annotations

import errno
import os
import socket
import subprocess
import sys
import time
from collections.abc import Mapping
from typing import Any, Final

from agentprov.io.workers import (
    _FRAME_HEAD,
    MIB,
    TAG_DATA,
    TAG_DONE,
    TAG_JSON,
    FrameWriter,
    JobContext,
    jcs,
)

TEST_JOB_KINDS: Final[Mapping[str, str]] = {
    # a test kind of a higher layer is named by its dotted path only (no import here: io sits below raw, M.5.2)
    "test.expand_crash": "agentprov.raw.testjobs:job_expand_crash",
} | {
    f"test.{name}": f"agentprov.io.worker_testjobs:job_{name}"
    for name in (
        "spin",
        "hog",
        "sleep",
        "net",
        "spawn",
        "write",
        "info",
        "crash",
        "raise_error",
        "oversize_json",
        "oversize_total",
        "bad_frame",
        "data_overflow",
        "chatter",
        "memory_error",
    )
}

_FORBIDDEN: Final = (
    "agentdojo",
    "agentprov_backend",
    "inspect_ai",
    "openai",
    "anthropic",
    "google",
    "cohere",
    "httpx",
    "pandas",
    "pyarrow",
    "numpy",
    "networkx",
    "pydot",
    "pyshacl",
)


def _unchecked_writer(ctx: JobContext) -> FrameWriter:
    """A writer without the worker-side frame cap: lets a test job violate the cap so the parent is exercised."""
    return FrameWriter(ctx._writer._stream, max_frame_bytes=1 << 62)  # noqa: SLF001


def job_spin(ctx: JobContext) -> dict[str, Any]:
    """CPU loop until the kernel's ``SIGXCPU`` kills the process (``params['seconds']`` bounds it, default none)."""
    deadline = time.monotonic() + float(ctx.params.get("seconds", 1e9))
    while time.monotonic() < deadline:
        pass
    return {}


def job_hog(ctx: JobContext) -> dict[str, Any]:
    """Allocate and touch ``params['mb']`` MiB in 8 MiB steps, then sleep (the watchdog should kill first).

    The pages must stay resident: a constant fill is shrunk by the macOS memory compressor under pressure (a 1536 MiB
    hog peaked at 610 MB resident, under a 1 GiB cap) and identical pages can be merged (Windows page combining). Each
    step is therefore a copy of one random block with the step number stamped into every 4 KiB page, so no page
    compresses and no two pages are equal (``os.urandom`` per step would be ~15x slower).
    """
    held = []
    step = 8 * MIB
    block = os.urandom(step)
    for n in range(int(ctx.params["mb"]) // 8):
        chunk = bytearray(block)  # writes every page
        stamp = n.to_bytes(8, "little")
        for offset in range(0, step, 4096):
            chunk[offset : offset + 8] = stamp
        held.append(chunk)
        time.sleep(float(ctx.params.get("pause", 0.002)))
    time.sleep(float(ctx.params.get("hold_s", 30)))
    return {"held": len(held)}


def job_sleep(ctx: JobContext) -> dict[str, Any]:
    time.sleep(float(ctx.params["seconds"]))
    return {}


def job_net(ctx: JobContext) -> dict[str, Any]:
    """Try one network event; the audit hook must raise before anything leaves the process."""
    event = ctx.params["event"]
    if event == "connect":
        socket.socket().connect(("127.0.0.1", 9))
    elif event == "bind":
        socket.socket().bind(("127.0.0.1", 0))
    elif event == "getaddrinfo":
        socket.getaddrinfo("localhost", 80)
    elif event == "sendto":
        socket.socket(socket.AF_INET, socket.SOCK_DGRAM).sendto(b"x", ("127.0.0.1", 9))
    else:
        raise ValueError(event)
    return {"reached": 1}


def job_spawn(ctx: JobContext) -> dict[str, Any]:
    """Try one subprocess event; the audit hook must raise before anything is started."""
    event = ctx.params["event"]
    if event == "popen":
        subprocess.run([sys.executable, "-c", "pass"], check=False)
    elif event == "system":
        os.system("exit 0")  # noqa: S605, S607
    elif event == "fork":
        os.fork()  # AttributeError where there is no fork: the test is skipped there
    elif event == "exec":
        os.execv(sys.executable, [sys.executable, "-c", "pass"])  # noqa: S606
    elif event == "fork_exec":  # pure-Python process creation without an audit event (pre-round review D #13)
        import multiprocessing.util

        multiprocessing.util.spawnv_passfds(os.fsencode(sys.executable), [os.fsencode(sys.executable), b"-c", b"pass"], [])
    elif event in ("fork_exec_bound", "fork_exec_reimport"):  # V-4: the other two pure-Python handles on fork_exec
        import _posixsubprocess
        import multiprocessing.util

        if event == "fork_exec_bound":  # subprocess bound the real function when it was imported, before the hook
            _posixsubprocess.fork_exec = subprocess._fork_exec  # type: ignore[attr-defined]
        else:  # a fresh import of the module restores the real function
            del sys.modules["_posixsubprocess"]
            import _posixsubprocess  # noqa: F401, F811
        multiprocessing.util.spawnv_passfds(os.fsencode(sys.executable), [os.fsencode(sys.executable), b"-c", b"pass"], [])
    else:
        raise ValueError(event)
    return {"reached": 1}


def job_write(ctx: JobContext) -> dict[str, Any]:
    """Write one byte to a file: ``RLIMIT_FSIZE = 0`` must give ``EFBIG`` while the pipe keeps working (obs-G5)."""
    seen = None
    try:
        with open("probe.bin", "wb") as handle:
            handle.write(b"x")
            handle.flush()
    except OSError as exc:
        seen = exc.errno
    ctx.emit({"errno": seen, "efbig": errno.EFBIG})  # still works: pipes are unaffected
    return {}


def _rlimits() -> dict[str, list[int]]:
    from agentprov.host import available_rlimits

    names = available_rlimits()
    if not names:
        return {}
    import resource

    return {
        name: [
            -1 if v == resource.RLIM_INFINITY else v
            for v in resource.getrlimit(getattr(resource, f"RLIMIT_{name.upper()}"))
        ]
        for name in names
    }


def job_info(ctx: JobContext) -> dict[str, Any]:
    ctx.emit(
        {
            "env": dict(os.environ),
            "isolated": sys.flags.isolated,
            "dont_write_bytecode": sys.flags.dont_write_bytecode,
            "orig_argv": list(sys.orig_argv),
            "cwd": os.getcwd(),
            "home_listing": sorted(os.listdir(os.environ["HOME"])),
            "forbidden_loaded": sorted(m for m in _FORBIDDEN if m in sys.modules),
            "rlimits": _rlimits(),
            "cwd_mode": os.stat(".").st_mode & 0o777,
            "pid": os.getpid(),
            "pgid": os.getpgid(0) if hasattr(os, "getpgid") else None,
            "sid": os.getsid(0) if hasattr(os, "getsid") else None,
        }
    )
    return {}


def job_crash(ctx: JobContext) -> dict[str, Any]:
    os._exit(int(ctx.params.get("code", 3)))


def job_raise_error(ctx: JobContext) -> dict[str, Any]:
    raise RuntimeError(str(ctx.params.get("message", "boom")))


def job_memory_error(ctx: JobContext) -> dict[str, Any]:
    raise MemoryError


def job_oversize_json(ctx: JobContext) -> dict[str, Any]:
    """Write one JSON frame of ``params['bytes']`` bytes, bypassing the worker-side cap."""
    body = jcs({"pad": "x" * int(ctx.params["bytes"])})
    _unchecked_writer(ctx).write(TAG_JSON, body)
    return {}


def job_oversize_total(ctx: JobContext) -> dict[str, Any]:
    """Many small JSON frames: each under the frame cap, together over the per-job JSON cap."""
    for _ in range(int(ctx.params["frames"])):
        ctx.emit({"pad": "x" * int(ctx.params["bytes"])})
    return {}


def job_bad_frame(ctx: JobContext) -> dict[str, Any]:
    """Protocol violations written raw: unknown tag, DATA without member, bad JSON, huge length, wrong job, ..."""
    stream = ctx._writer._stream  # noqa: SLF001

    def raw(tag: bytes, body: bytes) -> None:
        stream.write(_FRAME_HEAD.pack(tag, len(body)) + body)

    mode = ctx.params["mode"]
    if mode == "unknown_tag":
        raw(b"WHAT", b"{}")
    elif mode == "data_no_member":
        raw(TAG_DATA, b"abc")
    elif mode == "bad_json":
        raw(TAG_JSON, b"{oops")
    elif mode == "dup_keys":
        raw(TAG_JSON, b'{"a":1,"a":2}')
    elif mode == "nan":
        raw(TAG_JSON, b'{"a":NaN}')
    elif mode == "not_object":
        raw(TAG_JSON, b"[1,2]")
    elif mode == "huge_length":
        stream.write(_FRAME_HEAD.pack(TAG_JSON, 1 << 40))  # header only: the parent must not try to read it
    elif mode == "wrong_job":
        raw(TAG_DONE, jcs({"job": ctx.job + 100, "counters": {}}))
    elif mode == "truncated":
        stream.write(_FRAME_HEAD.pack(TAG_JSON, 100) + b"{")
        stream.flush()
        os._exit(0)
    else:
        raise ValueError(mode)
    return {}


def job_data_overflow(ctx: JobContext) -> dict[str, Any]:
    """A member that declares ``size`` bytes and then sends ``sent`` bytes (checked by the parent)."""
    ctx.member({"label": "m", "size": int(ctx.params["size"])})
    _unchecked_writer(ctx).write(TAG_DATA, b"z" * int(ctx.params["sent"]))
    return {}


def job_chatter(ctx: JobContext) -> dict[str, Any]:
    """Prints to stdout and stderr: stdout must not corrupt the frame stream; stderr is kept as a tail."""
    print("stray stdout line", flush=True)  # noqa: T201
    print("stderr-marker", file=sys.stderr)
    ctx.emit({"ok": True})
    return {}

