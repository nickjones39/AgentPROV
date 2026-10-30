"""A hostile ``expand`` job kind for the nested-archive tests (D-383). Never in the production table.

``agentprov.io.worker_testjobs.TEST_JOB_KINDS`` names it by its dotted path (``io`` sits below ``raw``, M.5.2); the pool
merges it only when constructed with ``test_kinds=True``.
"""

from __future__ import annotations

import os
import sys
from typing import Any

from agentprov.io.workers import JobContext
from agentprov.raw.members import job_expand

__all__ = ["job_expand_crash"]


def job_expand_crash(ctx: JobContext) -> dict[str, Any]:
    """The real ``expand`` job, killed (``os._exit``) after ``params['crash_after_chunks']`` DATA chunks of a member: a
    worker that dies in the middle of a streamed member (D-383)."""
    after = int(ctx.params.get("crash_after_chunks", 1))
    send = ctx.data
    sent = 0

    def data(chunk: bytes) -> None:
        nonlocal sent
        send(chunk)
        sent += 1
        if sent >= after:
            sys.stdout.flush()
            os._exit(9)

    ctx.data = data  # type: ignore[method-assign]
    return job_expand(ctx)
