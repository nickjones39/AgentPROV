"""No update under a running job (D-1130): the jobs that run from a folder an install is about to replace.

A job is a detached process (its supervisor and its CLI outlive the app, D-704), and it imports modules lazily, so
replacing the files it runs from while it runs can break it part of the way through. With the bundle's own agentprov
the job's interpreter is the app's executable; with a checkout it is the checkout's ``.venv`` interpreter; with a
package install it is that environment's. :func:`jobs_using` lists the running jobs of ``$AGENTPROV_HOME/jobs``
(:func:`agentprov.jobs.record.list_jobs`, read only) whose recorded argv names a file inside one of those folders, and
:func:`refuse_if_busy` stops the install (exit 4, ``update.install.busy``) naming them, so the user stops them in
Runs (``agentprov jobs stop ID``) or waits for them to end. Nothing is stopped or changed here.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Final

from agentprov.update.releases import UpdateError

__all__ = ["jobs_using", "refuse_if_busy"]

MAX_NAMED: Final = 5


def _forms(path: str | Path) -> set[str]:
    """A path as given (made absolute) and resolved: a venv's ``bin/python`` is a link out of the venv."""
    text = os.path.abspath(os.fspath(path))
    out = {os.path.normcase(text)}
    try:
        out.add(os.path.normcase(os.path.realpath(text)))
    except OSError:
        pass
    return out


def _inside(path: str, roots: set[str]) -> bool:
    return any(p == r or p.startswith(r.rstrip(os.sep) + os.sep) for p in _forms(path) for r in roots)


def jobs_using(home: Path, folders: Sequence[Path], *, jobs: Callable[[Path], list[Any]] | None = None
               ) -> list[dict[str, Any]]:
    """The running jobs whose argv names a file inside one of ``folders`` (``job_id``, ``label``, ``command``)."""
    if jobs is None:
        from agentprov.jobs.record import list_jobs

        jobs = list_jobs
    roots = {f for folder in folders for f in _forms(folder)}
    out = []
    for job in jobs(home):
        if job.state != "running":
            continue
        if any(os.path.isabs(a) and _inside(a, roots) for a in job.argv):
            out.append({"job_id": job.job_id, "label": job.record.get("label"), "command": job.command})
    return out


def refuse_if_busy(home: Path, folders: Sequence[Path], what: str, *,
                   jobs: Callable[[Path], list[Any]] | None = None) -> None:
    """Refuse (``update.install.busy``, exit 4) while a job runs from ``folders``; ``what`` names what is replaced."""
    busy = jobs_using(home, folders, jobs=jobs)
    if not busy:
        return
    from agentprov.ingest.quote import escape_untrusted_line

    named = ", ".join(f"{escape_untrusted_line(str(j['job_id']), max_chars=13)} "
                      f"({escape_untrusted_line(str(j['label'] or j['command']), max_chars=40)})" for j in busy[:MAX_NAMED])
    more = f" and {len(busy) - MAX_NAMED} more" if len(busy) > MAX_NAMED else ""
    raise UpdateError(f"{len(busy)} running job{'s' if len(busy) != 1 else ''} run{'' if len(busy) != 1 else 's'} "
                      f"from {what}: {named}{more}; stop {'them' if len(busy) != 1 else 'it'} (Runs › Stop, or "
                      "agentprov jobs stop ID) or wait until they end, then install again; nothing was changed",
                      code="update.install.busy", exit_code=4)
