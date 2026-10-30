"""K.17(1), SEC-13, DoD Q.16 and Q.31: what Git tracks, and the files that keep agents away from untrusted data.

Runs on ``git ls-files``. Failures name a path and a rule, never the matching bytes: a key-shaped string or a fixture
text is not repeated in the report.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MIB = 1 << 20

#: Tracked files over 1 MiB outside the fixture tree (the fixture tree has its own caps in tests/FIXTURES.json, K.4.1(5), D-360).
#: Each is a deliberate record, kept in Git by the user's decision (2026-10-11); a new one needs its own reasoned entry.
LARGE_FILE_ALLOWLIST = {
    "docs/reports/systematic-search/data/S1-code/S1-dependents.jsonl": "systematic-search record (D-25), kept verbatim",
    "docs/reports/systematic-search/data/S2-literature/S2-records.jsonl": "systematic-search record (D-25), kept verbatim",
    # examination 2 of the phase-10 corpora (fc777e7): per-corpus scan records behind the report's numbers
    "docs/reports/analysis/phase10-examination-2-data/scan-agentdyn-a-p10.json": "examination-2 record",
    "docs/reports/analysis/phase10-examination-2-data/scan-agentdojo-upstream-head-p10.json": "examination-2 record",
    "docs/reports/analysis/phase10-examination-2-data/scan-agentdojo-upstream-2024-06-p10.json": "examination-2 record",
    "docs/reports/analysis/phase10-examination-2-data/scan-adprov-v1-release-p10.json": "examination-2 record",
    "docs/reports/phase13/figure-inventory.json": "phase-13 figure inventory (manuscript numbers routing record)",
}
#: Where small AER/SEM/PROV files may be tracked: fixtures, goldens and the specification's examples (no corpora).
RECORD_PREFIXES = ("tests/fixtures/", "tests/golden/", "tests/adapters/foobench/golden/", "docs/architecture/examples/")
RECORD_SUFFIXES = (".aer.jsonl", ".sem.jsonl", ".prov.json", ".prov.trig")
CORPUS_FILES = {"corpus.json", "executions.jsonl", "register.jsonl", "derivation.json", "checksums.sha256",
                "origins.jsonl", "members.jsonl"}
AGENT_FILES = {"agents.md", "claude.md", "claude.local.md", "skill.md", "gemini.md", ".cursorrules", ".windsurfrules",
               "copilot-instructions.md", ".clinerules"}
SECRET_PATTERNS = {
    "openai-style key": re.compile(rb"sk-[A-Za-z0-9]{20,}"),
    "aws access key id": re.compile(rb"AKIA[0-9A-Z]{16}"),
    "hugging face token": re.compile(rb"hf_[A-Za-z0-9]{30,}"),
}


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


@pytest.fixture(scope="module")
def tracked() -> list[str]:
    if shutil.which("git") is None or not (ROOT / ".git").exists():
        pytest.skip("not a git checkout")
    return _git("ls-files", "-z").split("\0")[:-1]


def _synthetic_markers() -> list[re.Pattern[bytes]]:
    """The allowlist of ``.gitleaks.toml``: markers carried by every synthetic key in the redaction tests."""
    config = tomllib.loads((ROOT / ".gitleaks.toml").read_text(encoding="utf-8"))
    return [re.compile(m.removeprefix("(?i)").encode(), re.IGNORECASE if m.startswith("(?i)") else 0)
            for m in config["allowlist"]["regexes"]]


# ------------------------------------------------------------------------------------------ what is tracked
def test_no_secret_files_logs_or_local_agent_notes_are_tracked(tracked: list[str]) -> None:
    bad = [p for p in tracked
           if Path(p).name == ".env" or (Path(p).name.startswith(".env.") and Path(p).name != ".env.example")
           or p.endswith(".log") or Path(p).name == "CLAUDE.local.md" or p.endswith(".claude/settings.local.json")]
    assert bad == []


def test_no_corpus_raw_store_or_upstream_clone_is_tracked(tracked: list[str]) -> None:
    records = [p for p in tracked if p.endswith(RECORD_SUFFIXES) and not p.startswith(RECORD_PREFIXES)]
    corpus = [p for p in tracked if Path(p).name in CORPUS_FILES and not p.startswith("tests/fixtures/")]
    store = [p for p in tracked if "/raw/objects/" in f"/{p}" or "/.git/" in f"/{p}"]
    gitlinks = [line for line in _git("ls-files", "-s").splitlines() if line.startswith("160000")]
    assert (records, corpus, store, gitlinks) == ([], [], [], [])


def test_no_large_file_outside_the_fixture_tree_unless_allowlisted(tracked: list[str]) -> None:
    large = [p for p in tracked if not p.startswith(("tests/fixtures/", "tests/golden/"))
             and (ROOT / p).is_file() and (ROOT / p).stat().st_size > MIB]
    assert sorted(set(large) - set(LARGE_FILE_ALLOWLIST)) == []
    assert all(p in tracked for p in LARGE_FILE_ALLOWLIST), "an allowlist entry names a file that no longer exists"


def test_no_key_shaped_string_is_tracked_outside_the_synthetic_markers(tracked: list[str]) -> None:
    markers = _synthetic_markers()
    hits: list[tuple[str, str]] = []
    for path in tracked:
        file = ROOT / path
        if not file.is_file() or file.stat().st_size > 8 * MIB:
            continue
        data = file.read_bytes()
        for name, pattern in SECRET_PATTERNS.items():
            for match in pattern.finditer(data):
                if not any(m.search(match.group()) for m in markers):
                    hits.append((path, name))  # never the value
    assert hits == []


def test_no_agent_instruction_file_inside_the_fixture_tree(tracked: list[str]) -> None:
    assert [p for p in tracked if p.startswith("tests/fixtures/") and Path(p).name.lower() in AGENT_FILES] == []


# ------------------------------------------------------------------------------------------ guard files
def test_gitignore_covers_secrets_logs_and_local_notes() -> None:
    lines = {line.strip() for line in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()}
    assert {".env", ".env.*", "!.env.example", "*.log", "CLAUDE.local.md"} <= lines


def test_gitattributes_marks_the_fixture_tree_binary() -> None:
    lines = {line.strip() for line in (ROOT / ".gitattributes").read_text(encoding="utf-8").splitlines()}
    assert "tests/fixtures/** binary" in lines


@pytest.mark.parametrize("name", [".ignore", ".rgignore"])
def test_search_ignore_files_list_the_fixture_tree(name: str) -> None:
    lines = {line.strip() for line in (ROOT / name).read_text(encoding="utf-8").splitlines()}
    assert "tests/fixtures/" in lines


def _export_excluded() -> set[str]:
    """The paths the public export leaves out (D-943): absent there, checked wherever present."""
    doc = tomllib.loads((ROOT / "docs/reports/release/public-export.toml").read_text(encoding="utf-8"))
    return {e["path"] for e in doc["exclude"]}


def _development_checkout() -> bool:
    return (ROOT / "CLAUDE.md").is_file()


def test_claude_settings_deny_reading_fixtures_and_env() -> None:
    settings = ROOT / ".claude" / "settings.json"
    if not settings.is_file() and not _development_checkout() and ".claude/" in _export_excluded():
        pytest.skip("the public export leaves out .claude/ (D-943)")
    deny = set(json.loads(settings.read_text(encoding="utf-8"))["permissions"]["deny"])
    assert {"Read(./tests/fixtures/**)", "Read(./.env)"} <= deny


def test_agents_md_exists_and_claude_md_points_to_it() -> None:
    if not _development_checkout() and not (ROOT / "AGENTS.md").is_file():
        assert {"AGENTS.md", "CLAUDE.md"} <= _export_excluded()
        pytest.skip("the public export leaves out AGENTS.md and CLAUDE.md (D-943, D-1004)")
    assert (ROOT / "AGENTS.md").is_file()
    if not _development_checkout():
        assert "CLAUDE.md" in _export_excluded()
        pytest.skip("the public export leaves out CLAUDE.md (D-943)")
    assert "AGENTS.md" in (ROOT / "CLAUDE.md").read_text(encoding="utf-8")


#: accounts of CI runners and of the G5 test VMs, whose home paths the docs name on purpose
GENERIC_ACCOUNTS = frozenset({"runner", "runneradmin", "ubuntu", "agentprov"})


def test_no_tracked_file_names_this_machines_home_directory(tracked: list[str]) -> None:
    """The maintainer's home path was masked to ``~`` (D-943, P-5); the path is taken at run time, never written here."""
    home = Path.home()
    if os.environ.get("CI") or home.name in GENERIC_ACCOUNTS or len(str(home)) < 8:
        pytest.skip("a CI runner, a test VM or a short home path")
    needle = str(home).encode()
    hits = [p for p in tracked if (ROOT / p).is_file() and (ROOT / p).stat().st_size <= 8 * MIB
            and needle in (ROOT / p).read_bytes()]
    assert hits == []  # paths only, never the home directory itself


def test_ruff_rejects_invisible_characters_in_source() -> None:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert "PLE2502" in config["tool"]["ruff"]["lint"]["select"]


# ------------------------------------------------------------------------------------------ CI (K.19, D-22, Q.17)
def _workflow() -> dict:
    import yaml

    return yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))


def test_ci_has_no_schedule_trigger() -> None:
    triggers = _workflow()[True]  # YAML 1.1 reads the key `on` as True
    assert "schedule" not in triggers and "workflow_dispatch" in triggers  # D-22: manual dispatch, never a schedule


#: The two job gates of ci.yml (D-431 as updated by D-462). Every job carries exactly one of them.
CI_GATED = "github.event_name == 'workflow_dispatch' || vars.CI_ON_PUSH == 'true'"
CI_DISPATCH_ONLY = "github.event_name == 'workflow_dispatch'"


def _runs(gate: str, event: str, ci_on_push: str | None) -> bool:
    """What GitHub evaluates for one of the two gates (only these two strings are allowed, so this is exact)."""
    dispatch = event == "workflow_dispatch"
    return dispatch or (gate == CI_GATED and ci_on_push == "true")


def test_ci_triggers_are_dispatch_plus_push_and_pull_request_behind_a_variable() -> None:
    """D-431, updated by D-462: push (main) and pull_request trigger the workflow, but every job is gated, so with
    CI_ON_PUSH off (the default) no job can run on those events: no minutes, no failure emails."""
    workflow = _workflow()
    triggers = workflow[True]
    assert set(triggers) == {"workflow_dispatch", "push", "pull_request"}
    assert triggers["push"] == {"branches": ["main"]}
    jobs = workflow["jobs"]
    assert {job: spec.get("if") for job, spec in jobs.items() if spec.get("if") not in (CI_GATED,
                                                                                     CI_DISPATCH_ONLY)} == {}
    for job, spec in jobs.items():
        for event in ("push", "pull_request"):
            for off in (None, "false", "", "TRUE", "1"):
                assert not _runs(spec["if"], event, off), (job, event, off)
        assert _runs(spec["if"], "workflow_dispatch", None), job
        assert _runs(spec["if"], "push", "true") == (spec["if"] == CI_GATED), job
    dispatch_only = {job for job, spec in jobs.items() if spec["if"] == CI_DISPATCH_ONLY}
    assert dispatch_only == {"old-vs-new", "backend-autodojo", "fuzz-thorough"}


def test_ci_runner_variable_never_moves_the_windows_leg() -> None:
    """CI_RUNNER (a self-hosted label) takes every job except core's Windows leg, which stays GitHub-hosted."""
    jobs = _workflow()["jobs"]
    core = jobs["core"]
    assert core["runs-on"] == "${{ matrix.os == 'self-hosted' && vars.CI_RUNNER || matrix.os }}"
    matrix = core["strategy"]["matrix"]["os"]
    assert "'[\"self-hosted\", \"windows-latest\"]'" in matrix and "windows-latest\"]')" in matrix
    for job, spec in jobs.items():
        if job != "core":
            assert spec["runs-on"] == "${{ vars.CI_RUNNER || 'ubuntu-latest' }}", job


def test_ci_scans_every_lockfile_and_checks_every_lock_and_the_interpreter_floor() -> None:
    jobs = _workflow()["jobs"]
    locks = sorted(str(p.relative_to(ROOT)) for p in ROOT.glob("**/uv.lock") if ".venv" not in p.parts
                   and "worktrees" not in p.parts)
    osv = " ".join(str(step.get("with", {}).get("scan-args", "")) for step in jobs["dependencies"]["steps"])
    assert all(f"--lockfile={lock}" in osv for lock in locks), locks
    core = " ".join(str(step.get("run", "")) for step in jobs["core"]["steps"])
    assert "uv lock --check" in core and "(3, 14, 8)" in core and "tools/check_unicode.py" in core
    secrets = jobs["secrets"]["steps"]
    assert any("gitleaks" in str(step.get("uses", "")) for step in secrets)
    assert any(step.get("with", {}).get("fetch-depth") == 0 for step in secrets)  # full history


def test_every_accepted_dependency_advisory_has_a_reason_and_an_expiry() -> None:
    """DoD Q.17: an advisory is accepted only by the user, with its reason and a date to look again (never forever)."""
    import datetime

    configs = [p for p in ROOT.glob("**/osv-scanner.toml") if ".venv" not in p.parts and "worktrees" not in p.parts]
    for config in configs:
        for entry in tomllib.loads(config.read_text(encoding="utf-8")).get("IgnoredVulns", []):
            assert entry.get("id") and len(str(entry.get("reason", ""))) > 40, (config, entry.get("id"))
            until = entry.get("ignoreUntil")
            assert isinstance(until, datetime.datetime), (config, entry["id"], "needs ignoreUntil")


def test_the_execution_id_allowlist_entry_matches_only_a_whole_execution_id() -> None:
    """``.gitleaks.toml`` allows AgentPROV execution ids (analysis records list them; an id can contain "api" or "key").
    The entry must stay anchored to the whole secret so that a real key containing such a string is still reported."""
    config = tomllib.loads((ROOT / ".gitleaks.toml").read_text(encoding="utf-8"))
    (entry,) = [r for r in config["allowlist"]["regexes"] if "ex_" in r]
    assert entry.startswith("^") and entry.endswith("$")
    pattern = re.compile(entry)
    assert pattern.search("ex_inwukq44gvaz5thl2napiszc5y")
    for key in ("sk-ex_inwukq44gvaz5thl2napiszc5y", "ex_inwukq44gvaz5thl2napiszc5yA1", "AKIAex_inwukq44gvaz5thl2napiszc5y"):
        assert not pattern.search(key)


def test_gitleaksignore_holds_only_commit_pinned_fingerprints() -> None:
    """D-462 (user decision 2026-10-14): .gitleaksignore accepts single findings only. Every entry is a full
    ``<40-hex commit>:<path>:<rule>:<line>`` fingerprint naming a tracked file of that commit, so no path, rule or glob
    ignore can slip in and hide a new key."""
    path = ROOT / ".gitleaksignore"
    entries = [line for line in path.read_text(encoding="utf-8").splitlines() if line and not line.startswith("#")]
    pinned = re.compile(r"^(?P<commit>[0-9a-f]{40}):(?P<path>[^:*?\[\]\s]+):(?P<rule>[a-z0-9-]+):(?P<line>[1-9][0-9]*)$")
    assert entries, "an empty ignore file should be deleted instead"
    for entry in entries:
        m = pinned.fullmatch(entry)
        assert m, f"not a commit-pinned fingerprint: {entry!r}"
        shown = subprocess.run(["git", "cat-file", "-e", f"{m['commit']}:{m['path']}"], cwd=ROOT, capture_output=True)
        assert shown.returncode == 0, f"{entry!r}: the commit does not hold that file"
    # D-462 accepted four, its addendum (2026-10-24) eight more, D-1003 (2026-10-30) one; a new one needs a new decision.
    # The public export's second commit (D-980) keeps those its root commit holds: not the one pinned to DECISIONS.md
    # before the D-1003 split, which only the development history has (D-1004).
    assert len(entries) == len(set(entries)) == (13 if _development_checkout() else 12)
