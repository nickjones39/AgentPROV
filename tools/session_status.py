"""Session status files: what each parallel session is doing, machine-readable (proposal D-428, user-approved 2026-10-14).

Usage, from inside a session's worktree::

    uv run python tools/session_status.py set --state building --detail "phase 2 tests"
    uv run python tools/session_status.py set --state waiting-for-user --waits-on user "approval of D-420..D-429"
    uv run python tools/session_status.py suite-start
    uv run python tools/session_status.py suite --result green --passed 6912 --failed 0 --skipped 107
    uv run python tools/session_status.py touch
    uv run python tools/session_status.py show

Each session owns one file, ``<sessions-dir>/<name>.json``. The sessions directory is ``$AGENTPROV_SESSIONS_DIR``, else
``$AGENTPROV_HOME/sessions``, else ``~/.agentprov/sessions``. ``<name>`` is ``--name``, else ``$AGENTPROV_SESSION_NAME``,
else the current branch, made safe for a file name. The schema is ``agentprov-session-status/1``
(``docs/workflow/schemas/session-status-1.schema.json``). ``tools/queue_status.py`` reads every file and flags stalls.

* ``branch``, ``head``, ``worktree``, ``dirty`` and ``base`` (ahead/behind ``origin/main``) are computed from git in the
  current directory on every write, so a session never types a commit id.
* ``suite --result green`` is refused unless the tree is clean: a green result is recorded for exactly ``HEAD``.
* ``--branch REF`` describes a ref instead of the current checkout (``source: "ref"``): a parked branch with no
  worktree of its own, or a ``review/*`` branch, needs no checkout switch. It reads no worktree at all (``worktree``
  is empty, ``dirty`` false) and never touches the ref. ``--head SHA`` pins the head. The status file is named after
  the ref unless ``--name`` is given.
* Writes are atomic and serialised by an ``flock`` on ``<name>.lock``, so a suite wrapper and the session can both
  update the file.
* ``heartbeat_at`` changes on every write; ``updated_at`` only when something other than the heartbeat changes.

Nothing here reads the network or the repository's product code.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
import socket
import sys
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _workflow import agentprov_home, git_ok, read_json, safe_name, utc_now, write_json_atomic  # noqa: E402

SCHEMA = "agentprov-session-status/1"
STATES = ("building", "suite-running", "green", "waiting-for-user", "waiting-for-slot", "waiting-on-session",
          "blocked", "parked", "done")
WAIT_KINDS = ("user", "orchestrator", "session", "slot", "job", "none")
SUITE_RESULTS = ("green", "red", "error")
#: States that need a ``waits_on`` other than ``none``, with the kind used when ``--waits-on`` gives none.
WAITING_STATES = {"waiting-for-user": "user", "waiting-for-slot": "slot", "waiting-on-session": "session",
                  "blocked": None}
REQUIRED = ("schema", "name", "worktree", "branch", "head", "dirty", "base", "state", "waits_on", "updated_at",
            "heartbeat_at")
_HEARTBEAT_ONLY = {"heartbeat_at", "updated_at"}


def sessions_dir(environ: Mapping[str, str] = os.environ) -> Path:
    """``$AGENTPROV_SESSIONS_DIR``, else ``$AGENTPROV_HOME/sessions``, else ``~/.agentprov/sessions``."""
    explicit = environ.get("AGENTPROV_SESSIONS_DIR")
    return Path(explicit).expanduser() if explicit else agentprov_home(environ) / "sessions"


def git_facts(cwd: Path, base_ref: str = "origin/main", ref: str | None = None,
              pin: str | None = None) -> dict[str, Any]:
    """Branch, head, worktree, dirty flag and ahead/behind ``base_ref``.

    Without ``ref``: for the checkout at ``cwd`` (``source`` ``checkout``). With ``ref`` (``--branch``): for that ref
    alone (``source`` ``ref``): its head comes from ``git rev-parse`` (or ``pin``, ``--head``), and neither the HEAD nor
    the status of any worktree is read, so ``worktree`` is empty and ``dirty`` false. That describes a parked branch
    with no checkout of its own, or a ``review/*`` branch, without touching it.
    """
    top = git_ok(["rev-parse", "--show-toplevel"], cwd)
    if top is None:
        raise RuntimeError(f"{cwd} is not inside a git worktree")
    if ref is None:
        head = git_ok(["rev-parse", "HEAD"], cwd) or ""
        branch = git_ok(["symbolic-ref", "--quiet", "--short", "HEAD"], cwd) or "(detached)"
        worktree = top
        porcelain = git_ok(["status", "--porcelain"], cwd)
    else:
        head = git_ok(["rev-parse", "--verify", "--quiet", f"{pin or ref}^{{commit}}"], cwd) or ""
        if not head:
            raise RuntimeError(f"no commit {pin or ref!r}")
        branch, worktree, porcelain = ref, "", None
    base: dict[str, Any] = {"ref": base_ref, "sha": None, "ahead": None, "behind": None}
    base_sha = git_ok(["rev-parse", "--verify", "--quiet", f"{base_ref}^{{commit}}"], cwd)
    if base_sha and head:
        base["sha"] = base_sha
        counts = git_ok(["rev-list", "--left-right", "--count", f"{base_sha}...{head}"], cwd)
        if counts:
            behind, ahead = (int(x) for x in counts.split())
            base["ahead"], base["behind"] = ahead, behind
    return {"worktree": worktree, "repo": top, "source": "checkout" if ref is None else "ref", "branch": branch,
            "head": head, "dirty": bool(porcelain), "base": base}


def validate(doc: Any) -> list[str]:
    """Problems with a status document (empty if it is valid). Mirrors the JSON Schema; tests keep them in step."""
    if not isinstance(doc, dict):
        return ["not a JSON object"]
    errors = [f"missing {key}" for key in REQUIRED if key not in doc]
    if doc.get("schema") != SCHEMA:
        errors.append(f"schema is not {SCHEMA}")
    if doc.get("state") not in STATES:
        errors.append(f"unknown state {doc.get('state')!r}")
    waits = doc.get("waits_on")
    if not isinstance(waits, dict) or waits.get("kind") not in WAIT_KINDS:
        errors.append("waits_on.kind missing or unknown")
    elif doc.get("state") in WAITING_STATES and waits.get("kind") == "none":
        errors.append(f"state {doc.get('state')} needs waits_on")
    for key in ("name", "worktree", "branch", "head"):
        if key in doc and not isinstance(doc[key], str):
            errors.append(f"{key} is not a string")
    if "dirty" in doc and not isinstance(doc["dirty"], bool):
        errors.append("dirty is not a boolean")
    for key in ("updated_at", "heartbeat_at"):
        if key in doc and not isinstance(doc[key], str):
            errors.append(f"{key} is not a string")
    if isinstance(waits, dict) and "since" in waits and not isinstance(waits["since"], str):
        errors.append("waits_on.since is not a string")
    base = doc.get("base")
    if "base" in doc and not (isinstance(base, dict) and isinstance(base.get("ref"), str)
                              and all(key in base for key in ("sha", "ahead", "behind"))
                              and (base["sha"] is None or isinstance(base["sha"], str))
                              and all(base[key] is None or (type(base[key]) is int and base[key] >= 0)
                                      for key in ("ahead", "behind"))):
        errors.append("base needs ref, sha (or null) and ahead/behind (integers >= 0 or null)")
    suite = doc.get("last_suite")
    if suite is not None:
        if not isinstance(suite, dict) or suite.get("result") not in SUITE_RESULTS or not isinstance(
                suite.get("commit"), str):
            errors.append("last_suite needs a commit and a result in " + "/".join(SUITE_RESULTS))
    return errors


@contextlib.contextmanager
def _locked(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path.with_suffix(".lock"), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def load(path: Path) -> dict[str, Any] | None:
    """The status document at ``path``, or None if there is none (an unreadable file counts as none)."""
    try:
        doc = read_json(path, max_bytes=64 * 1024)
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) else None


def update(path: Path, cwd: Path, changes: Mapping[str, Any], *, name: str, base_ref: str = "origin/main",
           now: str | None = None, branch: str | None = None, pin: str | None = None) -> dict[str, Any]:
    """Apply ``changes`` (a None value removes that key) to the status file at ``path`` with fresh git facts, and
    write it atomically."""
    now = now or utc_now()
    with _locked(path):
        old = load(path) or {}
        doc: dict[str, Any] = {"schema": SCHEMA, "name": name, "state": "building",
                               "waits_on": {"kind": "none", "what": "", "since": now}, **old}
        doc.update(git_facts(cwd, base_ref, branch, pin))
        doc.update(changes)
        for key in [k for k, v in changes.items() if v is None]:  # None removes a key
            del doc[key]
        doc["schema"], doc["name"], doc["host"] = SCHEMA, name, socket.gethostname()
        doc["heartbeat_at"] = now
        if {k: v for k, v in doc.items() if k not in _HEARTBEAT_ONLY} != {
                k: v for k, v in old.items() if k not in _HEARTBEAT_ONLY} or "updated_at" not in old:
            doc["updated_at"] = now
        else:
            doc["updated_at"] = old["updated_at"]
        errors = validate(doc)
        if errors:
            raise ValueError("; ".join(errors))
        write_json_atomic(path, doc)
    return doc


def _waits_on(state: str, given: list[str] | None, old: Mapping[str, Any] | None, now: str) -> dict[str, str]:
    if given:
        kind, what = given[0], " ".join(given[1:])
        if kind not in WAIT_KINDS:
            raise ValueError(f"--waits-on kind must be one of {', '.join(WAIT_KINDS)}")
    elif state in WAITING_STATES:
        kind = WAITING_STATES[state] or ""
        if not kind:
            raise ValueError(f"state {state} needs --waits-on KIND [WHAT]")
        what = ""
    else:
        return {"kind": "none", "what": "", "since": now}
    previous = (old or {}).get("waits_on") or {}
    since = previous.get("since", now) if previous.get("kind") == kind and previous.get("what") == what else now
    return {"kind": kind, "what": what, "since": since}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(allow_abbrev=False, description=__doc__.split("\n\n")[0])
    p.add_argument("--name", help="session name (default $AGENTPROV_SESSION_NAME, else the current branch)")
    p.add_argument("--sessions-dir", type=Path, help="default $AGENTPROV_SESSIONS_DIR, else $AGENTPROV_HOME/sessions")
    p.add_argument("--base", default="origin/main", help="ref for ahead/behind (default origin/main)")
    p.add_argument("-C", dest="cwd", type=Path, default=Path.cwd(), help="worktree to describe (default: here)")
    p.add_argument("--branch", metavar="REF", help="describe this ref (e.g. a parked branch or review/*) instead of the "
                                                   "checkout; reads no worktree; the name defaults to the ref")
    p.add_argument("--head", dest="pin", metavar="SHA", help="with --branch: record this commit as the head")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("set", allow_abbrev=False, help="change state, detail, what the session waits on, title or decisions")
    s.add_argument("--state", choices=STATES)
    s.add_argument("--detail")
    s.add_argument("--waits-on", nargs="+", metavar=("KIND", "WHAT"), help=f"KIND in {', '.join(WAIT_KINDS)}")
    s.add_argument("--title")
    s.add_argument("--decisions", help="e.g. D-420–D-429")
    r = sub.add_parser("suite", allow_abbrev=False, help="record a finished full suite on the current HEAD")
    r.add_argument("--result", choices=SUITE_RESULTS, required=True)
    for count in ("passed", "failed", "skipped", "xfailed"):
        r.add_argument(f"--{count}", type=int)
    r.add_argument("--started-at", help="UTC start time (default: the suite-start record, else now)")
    r.add_argument("--command", dest="suite_command", help="the gate command that ran")
    sub.add_parser("suite-start", allow_abbrev=False, help="state suite-running, with the start time")
    sub.add_parser("touch", allow_abbrev=False, help="heartbeat only")
    sub.add_parser("show", allow_abbrev=False, help="print the file")
    sub.add_parser("path", allow_abbrev=False, help="print the file's path")
    a = p.parse_args(argv)
    if a.pin and not a.branch:
        p.error("--head needs --branch")

    cwd = a.cwd.resolve()
    branch = a.branch or git_ok(["symbolic-ref", "--quiet", "--short", "HEAD"], cwd) or "detached"
    try:
        name = safe_name(a.name or os.environ.get("AGENTPROV_SESSION_NAME") or branch)
    except ValueError as exc:
        print(f"session-status: {exc}", file=sys.stderr)
        return 2
    path = (a.sessions_dir or sessions_dir()).expanduser() / f"{name}.json"
    if a.cmd == "path":
        print(path)
        return 0
    if a.cmd == "show":
        doc = load(path)
        if doc is None:
            print(f"session-status: no status file at {path}", file=sys.stderr)
            return 1
        print(json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=True))
        return 0

    now = utc_now()
    old = load(path)
    changes: dict[str, Any] = {}
    try:
        if a.cmd == "set":
            state = a.state or (old or {}).get("state", "building")
            changes["state"] = state
            if a.state is not None or a.waits_on is not None:
                changes["waits_on"] = _waits_on(state, a.waits_on, old, now)
            for key in ("detail", "title", "decisions"):
                if getattr(a, key) is not None:
                    changes[key] = getattr(a, key)
        elif a.cmd == "suite-start":
            try:
                started_on = git_facts(cwd, a.base, a.branch, a.pin)["head"]
            except RuntimeError as exc:
                print(f"session-status: {exc}", file=sys.stderr)
                return 2
            changes = {"state": "suite-running", "suite_started_at": now, "suite_head": started_on,
                       "waits_on": {"kind": "job", "what": "full suite", "since": now}}
        elif a.cmd == "suite":
            try:
                facts = git_facts(cwd, a.base, a.branch, a.pin)
            except RuntimeError as exc:
                print(f"session-status: {exc}", file=sys.stderr)
                return 2
            if a.result == "green" and facts["dirty"]:
                print("session-status: refusing a green result for a dirty tree (commit first; green means this "
                      "exact HEAD)", file=sys.stderr)
                return 1
            tested = (old or {}).get("suite_head") or facts["head"]
            if a.result == "green" and tested != facts["head"]:
                print(f"session-status: refusing a green result: HEAD moved from {tested[:10]} since suite-start "
                      "(green means the head the suite ran on)", file=sys.stderr)
                return 1
            suite: dict[str, Any] = {"commit": tested, "result": a.result, "ended_at": now,
                                     "started_at": a.started_at or (old or {}).get("suite_started_at") or now}
            for count in ("passed", "failed", "skipped", "xfailed"):
                if getattr(a, count) is not None:
                    suite[count] = getattr(a, count)
            if a.suite_command:
                suite["command"] = a.suite_command
            changes["last_suite"] = suite
            changes["suite_head"] = None  # used once: a later suite needs its own suite-start
            if a.result == "green":
                changes["state"] = "green"
                changes["waits_on"] = {"kind": "none", "what": "", "since": now}
            elif (old or {}).get("state") == "suite-running":
                changes["state"] = "building"
                changes["waits_on"] = {"kind": "none", "what": "", "since": now}
                changes["detail"] = f"suite {a.result} on {facts['head'][:10]}"
        doc = update(path, cwd, changes, name=name, base_ref=a.base, now=now, branch=a.branch, pin=a.pin)
    except (ValueError, RuntimeError) as exc:
        print(f"session-status: {exc}", file=sys.stderr)
        return 2
    print(f"session-status: {name}: {doc['state']} ({path})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
