"""The parallel sessions at a glance: states, merge-train candidates, stalls and the suite queue (D-428).

Usage::

    uv run python tools/queue_status.py                  # table
    uv run python tools/queue_status.py --json           # for tools (the merge train)
    uv run python tools/queue_status.py --stale-hours 2 --live --fail-on-stall

It reads every ``<sessions-dir>/*.json`` written by ``tools/session_status.py`` and the suite queue's ``holder.json``
and ``tickets/`` (``tools/suite_queue.py``, D-403). It writes nothing.

Flags per session:

* ``STALE``: no heartbeat for more than ``--stale-hours`` while ``building`` or ``suite-running``;
* ``DEAD``: ``suite-running``, but the suite queue has no live holder or ticket from that worktree;
* ``WAITING-ON-USER``: shown with its age: not a session fault, but what went unnoticed overnight on 2026-10-13;
* ``SUITE-OLD``: state ``green`` but the last suite ran on another commit than the head;
* ``GONE``: the worktree no longer exists;
* ``INVALID``: the file does not match ``agentprov-session-status/1``.

``parked`` and ``done`` are never flagged. Every string from a status file is printed through ``safe_text``: the files
are written by other processes.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _workflow import agentprov_home, git_ok, parse_utc, read_json, safe_text  # noqa: E402
from session_status import sessions_dir, validate  # noqa: E402

ACTIVE_STATES = ("building", "suite-running")
CANDIDATE_STATES = ("green", "waiting-for-slot")


def suite_queue_dir(environ: Mapping[str, str] = os.environ) -> Path:
    """The suite queue's directory, resolved as ``tools/suite_queue.py`` does (D-403)."""
    explicit = environ.get("AGENTPROV_SUITE_QUEUE_DIR")
    return Path(explicit).expanduser() if explicit else agentprov_home(environ) / "locks" / "suite-queue"


def pid_alive(pid: object) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def read_queue(qdir: Path) -> dict[str, Any]:
    """The live holder and the live tickets of the suite queue (``exists`` False if there is no queue dir)."""
    if not qdir.is_dir():
        return {"exists": False, "holder": None, "tickets": []}
    holder = None
    try:
        doc = read_json(qdir / "holder.json", max_bytes=64 * 1024)
        if isinstance(doc, dict) and pid_alive(doc.get("pid")):
            holder = doc
    except (OSError, ValueError):
        pass
    tickets = []
    for path in sorted((qdir / "tickets").glob("*.json")) if (qdir / "tickets").is_dir() else []:
        try:
            doc = read_json(path, max_bytes=64 * 1024)
        except (OSError, ValueError):
            continue
        if isinstance(doc, dict) and pid_alive(doc.get("pid")):
            tickets.append(doc)
    return {"exists": True, "holder": holder, "tickets": tickets}


def _within(path: object, root: str) -> bool:
    if not isinstance(path, str) or not root:
        return False
    try:
        return Path(path).resolve().is_relative_to(Path(root).resolve())
    except (OSError, ValueError):
        return False


def _job_of(job_cwd: object, worktree: str) -> bool:
    """Whether a queue job started in ``job_cwd`` belongs to ``worktree``: inside it and, when ``job_cwd`` is in a git
    checkout, in that very checkout (worktrees may be nested inside the main checkout, under ``.claude/worktrees/``)."""
    if not _within(job_cwd, worktree):
        return False
    top = git_ok(["rev-parse", "--show-toplevel"], str(job_cwd))
    return top is None or Path(top).resolve() == Path(worktree).resolve()


def assess(doc: dict[str, Any], *, now: float, stale_hours: float, queue: dict[str, Any],
           live: bool = False) -> dict[str, Any]:
    """One session's row: its facts and flags. ``live`` re-reads head and ahead/behind from its worktree."""
    errors = validate(doc)
    row: dict[str, Any] = {"name": doc.get("name", "?"), "state": doc.get("state", "?"), "flags": [],
                           "errors": errors, "doc": doc}
    if errors:
        row["flags"].append("INVALID")
        return row
    head = doc["head"]
    worktree = doc["worktree"]
    if doc.get("source") == "ref":  # described from a ref, not a checkout (session_status --branch)
        if live and isinstance(doc.get("repo"), str):
            live_head = git_ok(["rev-parse", "--verify", "--quiet", f"{doc['branch']}^{{commit}}"], doc["repo"])
            if live_head and live_head != head:
                row["flags"].append("HEAD-MOVED")
                head = live_head
    elif not Path(worktree).is_dir():
        row["flags"].append("GONE")
    elif live:
        live_head = git_ok(["rev-parse", "HEAD"], worktree)
        if live_head and live_head != head:
            row["flags"].append("HEAD-MOVED")
            head = live_head
    row["head"] = head
    heartbeat = parse_utc(doc["heartbeat_at"])
    row["idle_s"] = None if heartbeat is None else max(0.0, now - heartbeat)
    state = doc["state"]
    if state in ACTIVE_STATES and (row["idle_s"] is None or row["idle_s"] > stale_hours * 3600):
        row["flags"].append("STALE")
    if state == "suite-running" and queue["exists"]:
        mine = [j for j in [queue["holder"], *queue["tickets"]] if j and _job_of(j.get("cwd"), worktree)]
        if not mine:
            row["flags"].append("DEAD")
    if state == "waiting-for-user":
        row["flags"].append("WAITING-ON-USER")
    suite = doc.get("last_suite") or {}
    row["suite_on_head"] = suite.get("commit") == head and suite.get("result") == "green"
    if state == "green" and not row["suite_on_head"]:
        row["flags"].append("SUITE-OLD")
    since = parse_utc((doc.get("waits_on") or {}).get("since", ""))
    row["waiting_s"] = None if since is None or doc["waits_on"].get("kind") == "none" else max(0.0, now - since)
    row["candidate"] = (state in CANDIDATE_STATES and row["suite_on_head"] and not doc["dirty"]
                        and "GONE" not in row["flags"])
    return row


def collect(sdir: Path, qdir: Path, *, now: float, stale_hours: float, live: bool = False) -> dict[str, Any]:
    queue = read_queue(qdir)
    rows = []
    for path in sorted(sdir.glob("*.json")) if sdir.is_dir() else []:
        try:
            doc = read_json(path, max_bytes=64 * 1024)
        except (OSError, ValueError) as exc:
            rows.append({"name": path.stem, "state": "?", "flags": ["INVALID"], "errors": [str(exc)], "doc": {}})
            continue
        rows.append(assess(doc if isinstance(doc, dict) else {}, now=now, stale_hours=stale_hours, queue=queue,
                           live=live))
    return {"sessions": rows, "queue": queue, "now": now}


def _age(seconds: float | None) -> str:
    if seconds is None:
        return "-"
    seconds = int(seconds)
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h{(seconds % 3600) // 60:02d}m"
    return f"{seconds // 86400}d{(seconds % 86400) // 3600}h"


def render(report: dict[str, Any]) -> str:
    lines = [f"{'session':<34} {'state':<19} {'head':<10} {'+/-main':<9} {'suite':<14} {'idle':<7} waits on / flags"]
    for row in report["sessions"]:
        doc = row["doc"]
        if row["errors"]:
            lines.append(f"{safe_text(row['name'], 34):<34} {'?':<19} INVALID: {safe_text('; '.join(row['errors']))}")
            continue
        base = doc.get("base") or {}
        ab = f"+{base.get('ahead')}/-{base.get('behind')}" if base.get("ahead") is not None else "?"
        suite = doc.get("last_suite") or {}
        suite_txt = "-" if not suite else f"{suite.get('result')}{'@head' if suite.get('commit') == row['head'] else '@old'}"
        waits = doc.get("waits_on") or {}
        wait_txt = "" if waits.get("kind") == "none" else (
            f"{waits.get('kind')}: {safe_text(waits.get('what', ''), 60)} ({_age(row['waiting_s'])})")
        flags = " ".join(f"[{f}]" for f in row["flags"])
        if doc.get("dirty"):
            flags = (flags + " [dirty]").strip()
        lines.append(f"{safe_text(row['name'], 34):<34} {safe_text(row['state'], 19):<19} {row['head'][:10]:<10} "
                     f"{ab:<9} {suite_txt:<14} {_age(row['idle_s']):<7} {wait_txt} {flags}".rstrip())
    candidates = [safe_text(r["name"]) for r in report["sessions"] if r.get("candidate")]
    lines.append("")
    lines.append("merge-train candidates (green on head, clean): " + (", ".join(candidates) or "none"))
    queue = report["queue"]
    if not queue["exists"]:
        lines.append("suite queue: no queue directory")
    else:
        holder = queue["holder"]
        running = "nothing running" if holder is None else "running " + (
            f"{safe_text(holder.get('label') or holder.get('branch') or '?', 40)} "
            f"(pid {holder.get('pid')}, since {safe_text(holder.get('started_at', '?'), 30)})")
        waiting = [safe_text(t.get("label") or t.get("branch") or "?", 40) for t in queue["tickets"]
                   if holder is None or t.get("pid") != holder.get("pid")]
        lines.append(f"suite queue: {running}; waiting {len(waiting)}"
                     + (f": {', '.join(waiting)}" if waiting else ""))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(allow_abbrev=False, description=__doc__.split("\n\n")[0])
    p.add_argument("--sessions-dir", type=Path, help="default $AGENTPROV_SESSIONS_DIR, else $AGENTPROV_HOME/sessions")
    p.add_argument("--queue-dir", type=Path, help="suite queue dir (default as tools/suite_queue.py resolves it)")
    p.add_argument("--stale-hours", type=float, default=2.0, help="heartbeat age that counts as STALE (default 2)")
    p.add_argument("--live", action="store_true", help="re-read each worktree's HEAD (flags HEAD-MOVED)")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument("--fail-on-stall", action="store_true", help="exit 1 if any session is STALE, DEAD or INVALID")
    a = p.parse_args(argv)
    report = collect((a.sessions_dir or sessions_dir()).expanduser(), (a.queue_dir or suite_queue_dir()).expanduser(),
                     now=time.time(), stale_hours=a.stale_hours, live=a.live)
    if a.json:
        out = {"now": report["now"], "queue": report["queue"],
               "sessions": [{k: v for k, v in r.items() if k != "doc"} | {"status": r["doc"]}
                            for r in report["sessions"]]}
        print(json.dumps(out, indent=2, sort_keys=True, ensure_ascii=True))
    else:
        print(render(report))
    stalled = any({"STALE", "DEAD", "INVALID"} & set(r["flags"]) for r in report["sessions"])
    return 1 if a.fail_on_stall and stalled else 0


if __name__ == "__main__":
    raise SystemExit(main())
