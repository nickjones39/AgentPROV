"""``tools/session_status.py``: the session-side writer of ``agentprov-session-status/1`` files (D-428)."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
import session_status as ss
from wf_support import commit, git, write

SCHEMA_FILE = Path(__file__).resolve().parents[3] / "docs" / "workflow" / "schemas" / "session-status-1.schema.json"
#: The public export leaves out docs/workflow/ (D-1004); the schema checks run where the file is.
needs_schema = pytest.mark.skipif(not SCHEMA_FILE.is_file(), reason="docs/workflow/ is not in this tree (D-1004)")


def _run(repo: Path, *args: str) -> int:
    return ss.main(["-C", str(repo), *args])


def _doc(home: Path, name: str) -> dict:
    return json.loads((home / "sessions" / f"{name}.json").read_text(encoding="utf-8"))


def test_set_records_git_facts(repo: Path, isolated_env: Path) -> None:
    git(repo, "switch", "-q", "-c", "claude/feature-x")
    write(repo, "a.txt", "a\n")
    head = commit(repo, "a")
    assert _run(repo, "set", "--state", "building", "--detail", "phase 1", "--title", "feature x") == 0
    doc = _doc(isolated_env, "claude-feature-x")
    assert doc["schema"] == ss.SCHEMA
    assert doc["branch"] == "claude/feature-x" and doc["head"] == head and doc["dirty"] is False
    assert doc["base"]["ref"] == "origin/main" and doc["base"]["ahead"] == 1 and doc["base"]["behind"] == 0
    assert doc["worktree"] == str(repo.resolve())
    assert doc["state"] == "building" and doc["detail"] == "phase 1" and doc["waits_on"]["kind"] == "none"
    assert ss.validate(doc) == []


def test_name_option_and_environment(repo: Path, isolated_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert _run(repo, "--name", "Phase 8 setup", "touch") == 0
    assert (isolated_env / "sessions" / "Phase-8-setup.json").is_file()
    monkeypatch.setenv("AGENTPROV_SESSION_NAME", "orchestrator")
    assert _run(repo, "touch") == 0
    assert (isolated_env / "sessions" / "orchestrator.json").is_file()


def test_waiting_states_need_what_they_wait_on(repo: Path, isolated_env: Path) -> None:
    assert _run(repo, "set", "--state", "blocked") == 2
    assert not (isolated_env / "sessions" / "main.json").exists()
    assert _run(repo, "set", "--state", "blocked", "--waits-on", "session", "regen-items-2-12", "push") == 0
    doc = _doc(isolated_env, "main")
    assert doc["waits_on"]["kind"] == "session" and doc["waits_on"]["what"] == "regen-items-2-12 push"
    assert _run(repo, "set", "--state", "waiting-for-user") == 0
    assert _doc(isolated_env, "main")["waits_on"]["kind"] == "user"
    assert _run(repo, "set", "--state", "building", "--waits-on", "nobody") == 2


def test_wait_since_survives_repeats_and_heartbeats(repo: Path, isolated_env: Path,
                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    times = iter(["2026-10-14T01:00:00Z", "2026-10-14T05:00:00Z", "2026-10-14T09:00:00Z", "2026-10-14T10:00:00Z"])
    monkeypatch.setattr(ss, "utc_now", lambda: next(times))
    assert _run(repo, "set", "--state", "waiting-for-user", "--waits-on", "user", "approve D-420") == 0
    assert _run(repo, "touch") == 0
    doc = _doc(isolated_env, "main")
    assert doc["waits_on"]["since"] == "2026-10-14T01:00:00Z"
    assert doc["updated_at"] == "2026-10-14T01:00:00Z" and doc["heartbeat_at"] == "2026-10-14T05:00:00Z"
    assert _run(repo, "set", "--state", "waiting-for-user", "--waits-on", "user", "approve D-420") == 0
    assert _doc(isolated_env, "main")["waits_on"]["since"] == "2026-10-14T01:00:00Z"
    assert _run(repo, "set", "--state", "waiting-for-user", "--waits-on", "user", "approve D-421") == 0
    assert _doc(isolated_env, "main")["waits_on"]["since"] == "2026-10-14T10:00:00Z"


def test_green_is_refused_on_a_dirty_tree(repo: Path, isolated_env: Path) -> None:
    write(repo, "untracked.txt", "x\n")
    assert _run(repo, "suite", "--result", "green", "--passed", "1", "--failed", "0") == 1
    assert not (isolated_env / "sessions" / "main.json").exists()
    assert _run(repo, "suite", "--result", "red", "--failed", "3") == 0
    assert _doc(isolated_env, "main")["last_suite"]["result"] == "red"


def test_suite_cycle(repo: Path, isolated_env: Path) -> None:
    head = git(repo, "rev-parse", "HEAD")
    assert _run(repo, "suite-start") == 0
    doc = _doc(isolated_env, "main")
    assert doc["state"] == "suite-running" and doc["waits_on"]["kind"] == "job"
    assert _run(repo, "suite", "--result", "red", "--passed", "10", "--failed", "2") == 0
    doc = _doc(isolated_env, "main")
    assert doc["state"] == "building" and doc["last_suite"]["commit"] == head
    assert doc["last_suite"]["started_at"] == doc["suite_started_at"]
    assert _run(repo, "suite-start") == 0
    assert _run(repo, "suite", "--result", "green", "--passed", "12", "--failed", "0", "--skipped", "1",
                "--command", "pytest -n auto") == 0
    doc = _doc(isolated_env, "main")
    assert doc["state"] == "green" and doc["waits_on"]["kind"] == "none"
    assert doc["last_suite"] == {"commit": head, "result": "green", "passed": 12, "failed": 0, "skipped": 1,
                                 "command": "pytest -n auto", "started_at": doc["suite_started_at"],
                                 "ended_at": doc["last_suite"]["ended_at"]}


def test_green_is_refused_when_head_moved_since_suite_start(repo: Path, isolated_env: Path) -> None:
    """The suite ran on A; the session committed B meanwhile: green for B is refused, red goes to A (bug pass BF-9)."""
    head_a = git(repo, "rev-parse", "HEAD")
    assert _run(repo, "suite-start") == 0
    assert _doc(isolated_env, "main")["suite_head"] == head_a
    write(repo, "b.txt", "b\n")
    head_b = commit(repo, "b")
    assert _run(repo, "suite", "--result", "green", "--passed", "1", "--failed", "0") == 1
    assert "last_suite" not in _doc(isolated_env, "main")
    assert _run(repo, "suite", "--result", "red", "--failed", "1") == 0
    doc = _doc(isolated_env, "main")
    assert doc["last_suite"]["commit"] == head_a and "suite_head" not in doc
    assert _run(repo, "suite", "--result", "green", "--passed", "1", "--failed", "0") == 0
    assert _doc(isolated_env, "main")["last_suite"]["commit"] == head_b


def test_detached_head_and_missing_base(tmp_path: Path, isolated_env: Path) -> None:
    root = tmp_path / "solo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    write(root, "x", "x\n")
    sha = commit(root, "x")
    git(root, "switch", "-q", "--detach", sha)
    assert _run(root, "--name", "solo", "touch") == 0
    doc = _doc(isolated_env, "solo")
    assert doc["branch"] == "(detached)"
    assert doc["base"] == {"ref": "origin/main", "sha": None, "ahead": None, "behind": None}


def test_outside_git_is_an_error(tmp_path: Path) -> None:
    assert ss.main(["-C", str(tmp_path), "--name", "x", "touch"]) == 2


def test_show_and_path(repo: Path, isolated_env: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _run(repo, "show") == 1
    assert _run(repo, "set", "--detail", "hello\x1b[31m") == 0
    capsys.readouterr()
    assert _run(repo, "show") == 0
    shown = capsys.readouterr().out
    assert "\\u001b" in shown and "\x1b" not in shown
    assert _run(repo, "path") == 0
    assert capsys.readouterr().out.strip() == str(isolated_env / "sessions" / "main.json")


def _valid_doc() -> dict:
    return {"schema": ss.SCHEMA, "name": "s", "worktree": "/w", "branch": "b", "head": "abc", "dirty": False,
            "base": {"ref": "origin/main", "sha": None, "ahead": None, "behind": None}, "state": "building",
            "waits_on": {"kind": "none", "what": "", "since": "2026-10-14T00:00:00Z"},
            "updated_at": "2026-10-14T00:00:00Z", "heartbeat_at": "2026-10-14T00:00:00Z"}


INVALID = [
    {"state": "sleeping"},
    {"schema": "agentprov-session-status/2"},
    {"waits_on": {"kind": "elsewhere"}},
    {"state": "blocked"},
    {"dirty": "no"},
    {"last_suite": {"commit": "abc", "result": "amber"}},
    {"last_suite": {"result": "green"}},
    # wrong types the readers would crash on (bug pass BF-12)
    {"base": "x"},
    {"base": ["origin/main"]},
    {"base": {"ref": "origin/main", "sha": None, "ahead": "1", "behind": 0}},
    {"base": {"ref": "origin/main", "sha": 5, "ahead": None, "behind": None}},
    {"base": {"ref": "origin/main", "sha": None, "ahead": -1, "behind": None}},
    {"base": {"ref": "origin/main", "sha": None, "ahead": True, "behind": None}},
    {"base": {"sha": None, "ahead": None, "behind": None}},
    {"heartbeat_at": 5},
    {"updated_at": None},
    {"waits_on": {"kind": "none", "since": 5}},
]


@needs_schema
def test_validator_and_json_schema_agree() -> None:
    schema = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    validator = jsonschema.Draft202012Validator(schema)
    good = _valid_doc()
    assert ss.validate(good) == [] and validator.is_valid(good)
    for change in INVALID:
        bad = {**good, **change}
        assert ss.validate(bad), change
        assert not validator.is_valid(bad), change
    for key in ss.REQUIRED:
        bad = {k: v for k, v in good.items() if k != key}
        assert ss.validate(bad) and not validator.is_valid(bad), key
    assert schema["properties"]["state"]["enum"] == list(ss.STATES)
    assert schema["properties"]["waits_on"]["properties"]["kind"]["enum"] == list(ss.WAIT_KINDS)
    assert schema["required"] == list(ss.REQUIRED)
    waiting = schema["allOf"][0]["if"]["properties"]["state"]["enum"]
    assert waiting == list(ss.WAITING_STATES)


# --------------------------------------------------------------------------------------------------- --branch REF


def test_branch_describes_a_ref_without_reading_any_worktree(repo: Path, isolated_env: Path,
                                                            monkeypatch: pytest.MonkeyPatch) -> None:
    git(repo, "switch", "-q", "-c", "deferrals-c")
    write(repo, "c.txt", "c\n")
    parked = commit(repo, "parked work")
    git(repo, "switch", "-q", "main")
    write(repo, "dirty.txt", "uncommitted\n")  # the worktree it runs in is dirty and on another branch
    calls: list[list[str]] = []
    real = ss.git_ok
    monkeypatch.setattr(ss, "git_ok", lambda args, cwd=None: calls.append(list(args)) or real(args, cwd))
    assert _run(repo, "--branch", "deferrals-c", "set", "--state", "parked", "--detail", "held by the user") == 0
    assert not any(c[:1] == ["status"] or "HEAD" in c for c in calls), calls
    doc = _doc(isolated_env, "deferrals-c")
    assert doc["source"] == "ref" and doc["branch"] == "deferrals-c" and doc["head"] == parked
    assert doc["worktree"] == "" and doc["dirty"] is False and doc["repo"] == str(repo.resolve())
    assert doc["base"]["ahead"] == 1 and doc["base"]["behind"] == 0
    assert ss.validate(doc) == []
    if SCHEMA_FILE.is_file():  # not in the public export (D-1004)
        schema = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
        assert jsonschema.Draft202012Validator(schema).is_valid(doc)
    assert _run(repo, "--branch", "deferrals-c", "suite", "--result", "green", "--passed", "5") == 0
    assert _doc(isolated_env, "deferrals-c")["last_suite"]["commit"] == parked  # green for the ref, not this tree
    assert _run(repo, "touch") == 0
    assert _doc(isolated_env, "main")["source"] == "checkout" and _doc(isolated_env, "main")["dirty"] is True


def test_branch_review_refs_head_pin_and_errors(repo: Path, isolated_env: Path) -> None:
    base = git(repo, "rev-parse", "HEAD")
    git(repo, "branch", "review/live-capture")
    assert _run(repo, "--branch", "review/live-capture", "set", "--state", "parked") == 0
    assert _doc(isolated_env, "review-live-capture")["head"] == base
    assert git(repo, "rev-parse", "review/live-capture") == base  # the ref is never touched
    write(repo, "n.txt", "n\n")
    newer = commit(repo, "newer")
    assert _run(repo, "--branch", "review/live-capture", "--head", newer, "touch") == 0
    assert _doc(isolated_env, "review-live-capture")["head"] == newer
    assert _run(repo, "--branch", "no-such-branch", "touch") == 2
    with pytest.raises(SystemExit):
        _run(repo, "--head", newer, "touch")  # --head needs --branch
