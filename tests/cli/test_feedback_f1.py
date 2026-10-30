"""F1 (MN N.1.14(4)): the outputs of a command are byte-identical at every feedback level and format.

stdout, the ``--summary-json`` file and every file the command could touch must not depend on ``--progress``,
``--progress-format``, ``--progress-file``, ``--show-content``, ``-q`` or ``AGENTPROV_PROGRESS``. Feedback goes to stderr
only, and the drop count never enters the summary document.
"""

from __future__ import annotations

import hashlib
import itertools
import threading
from pathlib import Path

import pytest

LEVELS = ["off", "summary", "status", "steps", "trace"]
FORMATS = ["auto", "tty", "plain", "jsonl"]


def tree_digest(root: Path) -> dict[str, str]:
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob("*")) if p.is_file()
    }


def feedback_threads() -> list[threading.Thread]:
    return [t for t in threading.enumerate() if t.name == "agentprov-feedback" and t.is_alive()]


@pytest.fixture
def baseline(cli, valid_aer, tmp_path):
    summary = tmp_path / "base-summary.json"
    run = cli("validate", str(valid_aer), "--json", "--summary-json", str(summary), "--progress", "off")
    assert run.code == 0, run.err
    return run, summary.read_bytes(), valid_aer


@pytest.mark.parametrize(("level", "fmt"), list(itertools.product(LEVELS, FORMATS)))
def test_outputs_are_byte_identical_at_every_level_and_format(cli, baseline, tmp_path, level, fmt):
    base_run, base_summary, aer = baseline
    before = tree_digest(aer.parent)
    summary = tmp_path / f"s-{level}-{fmt}.json"
    run = cli("validate", str(aer), "--json", "--summary-json", str(summary), "--progress", level, "--progress-format", fmt)
    assert run.code == base_run.code
    assert run.out == base_run.out  # stdout, byte for byte
    assert summary.read_bytes() == base_summary
    after = tree_digest(aer.parent)
    after.pop(summary.name)
    assert after == before  # nothing else was written or changed
    assert feedback_threads() == []


def test_quiet_show_content_progress_file_and_the_environment_change_nothing(cli, baseline, tmp_path, monkeypatch):
    base_run, base_summary, aer = baseline
    variants = [
        ["-q"],
        ["--show-content", "--progress", "trace"],
        ["--show-content", "--content-chars", "5", "--progress", "steps", "--progress-format", "jsonl"],
        ["--progress", "trace", "--progress-file", str(tmp_path / "events.jsonl")],
        ["-v", "--log-format", "json", "--log-file", str(tmp_path / "log.jsonl")],
    ]
    for i, extra in enumerate(variants):
        summary = tmp_path / f"v{i}.json"
        run = cli("validate", str(aer), "--json", "--summary-json", str(summary), *extra)
        assert run.out == base_run.out, extra
        assert summary.read_bytes() == base_summary, extra
    monkeypatch.setenv("AGENTPROV_PROGRESS", "trace")
    summary = tmp_path / "env.json"
    from agentprov.cli.main import main

    assert main(["validate", str(aer), "--summary-json", str(summary)]) == 0
    assert summary.read_bytes() == base_summary


def test_failing_runs_are_also_identical_across_levels(cli, broken_aer, tmp_path):
    outputs = set()
    for level in LEVELS:
        run = cli("validate", str(broken_aer), "--json", "--progress", level)
        assert run.code == 1
        outputs.add(run.out)
    assert len(outputs) == 1


def test_feedback_only_ever_writes_to_stderr_and_the_progress_file(cli, valid_aer, tmp_path):
    events = tmp_path / "events.jsonl"
    run = cli("validate", str(valid_aer), "--json", "--progress", "trace", "--progress-file", str(events))
    assert "agentprov validate" in run.err and "finished in" in run.err  # on stderr
    assert "finished in" not in run.out and "units=" not in run.out
    assert events.read_text().count('"agentprov-progress/0.2"') >= 3


def test_the_drop_count_never_enters_the_summary(cli, valid_aer):
    document = cli("validate", str(valid_aer), "--json", "--progress", "trace").json()
    assert "dropped" not in repr(document)
