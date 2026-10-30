"""T1 job entry: ``python -I -B -m agentprov.worker --protocol agentprov-job/0.1`` (G.4; A3; MN M.1.2).

A thin L6 shell. The pool in :mod:`agentprov.io.workers` starts this module by name only; the frame writer, the
closed job table (:data:`JOB_KINDS`), the rlimits, the audit hook and the dispatch live there so that the
``--in-process`` debugging path runs the same code.

Order of events in the worker (G.4.3, G.4.4):

1. apply the kernel limits (before any job is read, no ``preexec_fn``);
2. import every module the job table names;
3. install the audit hook (network and subprocess events only);
4. loop: read one JSON line, validate it, arm the per-job CPU budget, run the job, write ``DONE`` or ``FAIL``.

Frames go to a private duplicate of file descriptor 1; fd 1 itself is redirected to stderr, so a stray ``print``
in a job can never corrupt the protocol. A ``FAIL`` ends the worker (recycling policy, G.4.7).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from agentprov.io.workers import (
    JOB_KINDS,
    MAX_REQUEST_BYTES,
    MIB,
    PROTOCOL,
    TAG_FAIL,
    FrameWriter,
    WorkerError,
    WorkerProtocolError,
    apply_start_rlimits,
    arm_job_cpu_budget,
    install_audit_hook,
    jcs,
    kind_table,
    preload_job_kinds,
    run_job_request,
    strict_loads,
    validate_request,
)

__all__ = ["JOB_KINDS", "main"]

_MAX_REQUEST_LINE = MAX_REQUEST_BYTES  # one constant for the parent's check and this read (D #11)


def _parse_args(argv: list[str]) -> dict[str, str | bool]:
    """Tiny strict parser (the worker avoids ``argparse`` to keep start-up and surface small)."""
    values: dict[str, str | bool] = {"test_kinds": False}
    flags_with_value = {
        "--protocol": "protocol",
        "--cpu-hard": "cpu_hard",
        "--nofile": "nofile",
        "--as-bytes": "as_bytes",
        "--store-root": "store_root",
    }
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--test-kinds":
            values["test_kinds"] = True
            i += 1
        elif arg in flags_with_value and i + 1 < len(argv):
            values[flags_with_value[arg]] = argv[i + 1]
            i += 2
        else:
            raise WorkerProtocolError(f"unexpected worker argument {arg!r}")
    if values.get("protocol") != PROTOCOL:
        raise WorkerProtocolError(f"unsupported protocol {values.get('protocol')!r}")
    return values


def _fail(writer: FrameWriter, job: object, code: str, message: str) -> None:
    number = job if isinstance(job, int) and not isinstance(job, bool) else -1
    writer.max_frame_bytes = MIB
    writer.write(
        TAG_FAIL, jcs({"job": number, "code": code, "message": message[:500], "type": "WorkerProtocolError"})
    )
    writer.flush()


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    frames_fd = os.dup(1)
    os.dup2(2, 1)  # stray prints go to stderr, never into the frame stream
    writer = FrameWriter(os.fdopen(frames_fd, "wb", buffering=1 << 16))

    cpu_hard = int(args.get("cpu_hard", 3600))
    apply_start_rlimits(
        cpu_hard_s=cpu_hard,
        nofile=int(args.get("nofile", 64)),
        as_bytes=int(args.get("as_bytes", 0)),
    )
    functions = preload_job_kinds(kind_table(test_kinds=bool(args["test_kinds"])))
    install_audit_hook()  # after every import the job kinds need (G.4.4)
    store_root = Path(str(args["store_root"])) if "store_root" in args else None

    stdin = sys.stdin.buffer
    while True:
        line = stdin.readline(_MAX_REQUEST_LINE + 1)
        if not line:
            return 0  # parent closed stdin: normal recycling
        job: object = None
        try:
            if len(line) > _MAX_REQUEST_LINE:
                raise WorkerProtocolError("request line too long")
            raw = strict_loads(line)
            job = raw.get("job") if isinstance(raw, dict) else None
            request = validate_request(raw, functions)
            limits = request["limits"]
            writer.max_frame_bytes = int(limits.get("max_frame_bytes", 16 * MIB))
            arm_job_cpu_budget(int(limits.get("cpu_s", 300)), cpu_hard)
        except (WorkerError, ValueError, TypeError) as exc:
            _fail(writer, job, "worker.protocol", str(exc))
            return 2
        if not run_job_request(request, functions, writer, store_root=store_root):
            return 0  # FAIL was written: this worker is replaced (G.4.7)


if __name__ == "__main__":
    raise SystemExit(main())
