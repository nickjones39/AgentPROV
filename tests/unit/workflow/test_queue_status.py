"""``tools/queue_status.py``: the reader of session status files and the suite queue, with stall flags (D-428)."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest
import queue_status as qs
import session_status as ss
from _workflow import utc_now
from wf_support import git

HOUR = 3600.0


def _stamp(seconds_ago: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - seconds_ago))


def _put(sdir: Path, name: str, worktree: Path, **fields) -> dict:
    doc = {"schema": ss.SCHEMA, "name": name, "worktree": str(worktree), "branch": name, "head": "a" * 40,
           "dirty": False, "base": {"ref": "origin/main", "sha": "b" * 40, "ahead": 1, "behind": 0},
           "state": "building", "waits_on": {"kind": "none", "what": "", "since": utc_now()},
           "updated_at": utc_now(), "heartbeat_at": utc_now()}
    doc.update(fields)
    sdir.mkdir(parents=True, exist_ok=True)
    (sdir / f"{name}.json").write_text(json.dumps(doc), encoding="utf-8")
    return doc


def _rows(sdir: Path, qdir: Path, **kw) -> dict[str, dict]:
    report = qs.collect(sdir, qdir, now=time.time(), stale_hours=kw.pop("stale_hours", 2.0), **kw)
    return {r["name"]: r for r in report["sessions"]}


@pytest.fixture
def dirs(tmp_path: Path) -> tuple[Path, Path, Path]:
    worktree = tmp_path / "wt"
    worktree.mkdir()
    return tmp_path / "sessions", tmp_path / "queue", worktree


def test_stale_only_while_working(dirs: tuple[Path, Path, Path]) -> None:
    sdir, qdir, wt = dirs
    old = _stamp(15 * HOUR)
    _put(sdir, "busy", wt, heartbeat_at=old)
    _put(sdir, "fresh", wt)
    _put(sdir, "parked", wt, state="parked", heartbeat_at=old)
    _put(sdir, "done", wt, state="done", heartbeat_at=old)
    rows = _rows(sdir, qdir)
    assert rows["busy"]["flags"] == ["STALE"]
    assert rows["fresh"]["flags"] == [] and rows["parked"]["flags"] == [] and rows["done"]["flags"] == []
    assert rows["busy"]["idle_s"] > 14 * HOUR


def test_waiting_on_user_is_shown_with_its_age(dirs: tuple[Path, Path, Path]) -> None:
    sdir, qdir, wt = dirs
    _put(sdir, "w", wt, state="waiting-for-user", heartbeat_at=_stamp(15 * HOUR),
         waits_on={"kind": "user", "what": "push yes", "since": _stamp(15 * HOUR)})
    row = _rows(sdir, qdir)["w"]
    assert row["flags"] == ["WAITING-ON-USER"]
    assert row["waiting_s"] > 14 * HOUR
    assert "user: push yes (15h00m)" in qs.render(qs.collect(sdir, qdir, now=time.time(), stale_hours=2))


def test_dead_suite(dirs: tuple[Path, Path, Path]) -> None:
    sdir, qdir, wt = dirs
    _put(sdir, "s", wt, state="suite-running")
    assert _rows(sdir, qdir)["s"]["flags"] == []  # no queue directory: cannot tell
    (qdir / "tickets").mkdir(parents=True)
    assert _rows(sdir, qdir)["s"]["flags"] == ["DEAD"]
    holder = {"pid": os.getpid(), "cwd": str(wt / "sub"), "label": "s", "started_at": utc_now()}
    (qdir / "holder.json").write_text(json.dumps(holder), encoding="utf-8")
    assert _rows(sdir, qdir)["s"]["flags"] == []
    (qdir / "holder.json").unlink()
    ticket = {"pid": os.getpid(), "cwd": str(wt), "label": "s"}
    (qdir / "tickets" / "1-1.json").write_text(json.dumps(ticket), encoding="utf-8")
    assert _rows(sdir, qdir)["s"]["flags"] == []
    ticket["pid"] = 2**22 + 12345  # no such process
    (qdir / "tickets" / "1-1.json").write_text(json.dumps(ticket), encoding="utf-8")
    assert _rows(sdir, qdir)["s"]["flags"] == ["DEAD"]


def test_a_job_in_a_nested_worktree_belongs_to_that_worktree(repo: Path, tmp_path: Path) -> None:
    """Worktrees may live inside the main checkout (``.claude/worktrees/``): another worktree's job must not keep a
    dead suite of the main checkout alive (bug pass BF-13); a job in a plain subdirectory still counts."""
    sdir, qdir = tmp_path / "sessions", tmp_path / "queue"
    nested = repo / ".claude" / "worktrees" / "other"
    git(repo, "worktree", "add", "-q", "-b", "other", str(nested))
    (repo / "sub").mkdir()
    _put(sdir, "main", repo, state="suite-running")
    (qdir / "tickets").mkdir(parents=True)
    holder = {"pid": os.getpid(), "cwd": str(nested), "label": "other", "started_at": utc_now()}
    (qdir / "holder.json").write_text(json.dumps(holder), encoding="utf-8")
    assert _rows(sdir, qdir)["main"]["flags"] == ["DEAD"]
    holder["cwd"] = str(repo / "sub")
    (qdir / "holder.json").write_text(json.dumps(holder), encoding="utf-8")
    assert _rows(sdir, qdir)["main"]["flags"] == []


def test_gone_invalid_and_unreadable(dirs: tuple[Path, Path, Path]) -> None:
    sdir, qdir, wt = dirs
    _put(sdir, "gone", wt.parent / "removed")
    _put(sdir, "bad", wt, state="sleeping")
    (sdir / "junk.json").write_text("{not json", encoding="utf-8")
    (sdir / "huge.json").write_text(" " * (70 * 1024), encoding="utf-8")
    rows = _rows(sdir, qdir)
    assert rows["gone"]["flags"] == ["GONE"]
    assert rows["bad"]["flags"] == ["INVALID"] and "unknown state" in rows["bad"]["errors"][0]
    assert rows["junk"]["flags"] == ["INVALID"] and rows["huge"]["flags"] == ["INVALID"]


def test_a_mistyped_file_is_invalid_and_does_not_break_the_report(dirs: tuple[Path, Path, Path]) -> None:
    """One status file with a non-object ``base`` is that row's problem, never the whole report's (bug pass BF-12)."""
    sdir, qdir, wt = dirs
    _put(sdir, "bad", wt, base="x")
    _put(sdir, "good", wt)
    rows = _rows(sdir, qdir)
    assert rows["bad"]["flags"] == ["INVALID"] and rows["good"]["flags"] == []
    assert "good" in qs.render(qs.collect(sdir, qdir, now=time.time(), stale_hours=2))


def test_candidates_need_green_on_head_and_a_clean_tree(dirs: tuple[Path, Path, Path]) -> None:
    sdir, qdir, wt = dirs
    green = {"commit": "a" * 40, "result": "green"}
    _put(sdir, "ok", wt, state="green", last_suite=green)
    _put(sdir, "slot", wt, state="waiting-for-slot", last_suite=green,
         waits_on={"kind": "slot", "what": "", "since": utc_now()})
    _put(sdir, "old", wt, state="green", last_suite={"commit": "c" * 40, "result": "green"})
    _put(sdir, "dirty", wt, state="green", last_suite=green, dirty=True)
    _put(sdir, "red", wt, state="waiting-for-slot", last_suite={"commit": "a" * 40, "result": "red"},
         waits_on={"kind": "slot", "what": "", "since": utc_now()})
    rows = _rows(sdir, qdir)
    assert {n for n, r in rows.items() if r["candidate"]} == {"ok", "slot"}
    assert rows["old"]["flags"] == ["SUITE-OLD"]
    text = qs.render(qs.collect(sdir, qdir, now=time.time(), stale_hours=2))
    assert "merge-train candidates (green on head, clean): ok, slot" in text


def test_live_head(repo: Path, tmp_path: Path) -> None:
    sdir, qdir = tmp_path / "sessions", tmp_path / "queue"
    head = git(repo, "rev-parse", "HEAD")
    _put(sdir, "live", repo, head=head, state="green", last_suite={"commit": head, "result": "green"})
    assert _rows(sdir, qdir, live=True)["live"]["candidate"]
    (repo / "b.txt").write_text("b\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "b")
    row = _rows(sdir, qdir, live=True)["live"]
    assert "HEAD-MOVED" in row["flags"] and "SUITE-OLD" in row["flags"] and not row["candidate"]


def test_hostile_text_is_escaped(dirs: tuple[Path, Path, Path]) -> None:
    sdir, qdir, wt = dirs
    _put(sdir, "evil", wt, state="blocked",
         waits_on={"kind": "session", "what": "x\x1b[2J\u202egnp.exe\nINJECTED", "since": utc_now()})
    qdir.mkdir()
    (qdir / "holder.json").write_text(json.dumps({"pid": os.getpid(), "label": "l\x07bell", "cwd": "/"}),
                                      encoding="utf-8")
    text = qs.render(qs.collect(sdir, qdir, now=time.time(), stale_hours=2))
    assert "\x1b" not in text and "\u202e" not in text and "\x07" not in text
    assert "\\u001b" in text and "\\u202e" in text and "\\u000a" in text
    assert len(text.splitlines()) == 5  # header, one session, blank, candidates, queue: no injected line
    assert "suite queue: running l\\u0007bell" in text


def test_main_json_and_exit_codes(dirs: tuple[Path, Path, Path], capsys: pytest.CaptureFixture[str]) -> None:
    sdir, qdir, wt = dirs
    _put(sdir, "fine", wt)
    args = ["--sessions-dir", str(sdir), "--queue-dir", str(qdir)]
    assert qs.main([*args, "--json", "--fail-on-stall"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["sessions"][0]["name"] == "fine" and out["sessions"][0]["status"]["state"] == "building"
    _put(sdir, "stuck", wt, heartbeat_at=_stamp(3 * HOUR))
    assert qs.main([*args, "--fail-on-stall"]) == 1
    assert "[STALE]" in capsys.readouterr().out
    assert qs.main([*args, "--fail-on-stall", "--stale-hours", "4"]) == 0
    assert qs.main(args) == 0


def test_suite_queue_dir_resolution(tmp_path: Path) -> None:
    assert qs.suite_queue_dir({"AGENTPROV_SUITE_QUEUE_DIR": str(tmp_path / "q")}) == tmp_path / "q"
    assert qs.suite_queue_dir({"AGENTPROV_HOME": str(tmp_path)}) == tmp_path / "locks" / "suite-queue"


def test_ref_described_sessions_are_not_gone(repo: Path, tmp_path: Path) -> None:
    sdir, qdir = tmp_path / "sessions", tmp_path / "queue"
    git(repo, "branch", "parked")
    head = git(repo, "rev-parse", "parked")
    _put(sdir, "parked", "", source="ref", repo=str(repo), branch="parked", head=head,  # type: ignore[arg-type]
         state="parked")
    assert _rows(sdir, qdir, live=True)["parked"]["flags"] == []
    (repo / "p.txt").write_text("p\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "on main")
    git(repo, "branch", "-f", "parked", "HEAD")
    assert _rows(sdir, qdir, live=True)["parked"]["flags"] == ["HEAD-MOVED"]


def test_the_holders_own_ticket_is_not_a_waiter(dirs: tuple[Path, Path, Path]) -> None:
    """While a suite runs its ticket stays in tickets/ (the flock is the mutex); it must not be listed as waiting."""
    sdir, qdir, wt = dirs
    (qdir / "tickets").mkdir(parents=True)
    me = os.getpid()
    (qdir / "holder.json").write_text(json.dumps({"pid": me, "label": "holder", "cwd": str(wt)}), encoding="utf-8")
    (qdir / "tickets" / "1-a.json").write_text(json.dumps({"pid": me, "label": "holder"}), encoding="utf-8")
    text = qs.render(qs.collect(sdir, qdir, now=time.time(), stale_hours=2))
    assert "suite queue: running holder" in text and "waiting 0" in text
