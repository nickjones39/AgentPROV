"""D-542: ``live.quality`` is a pure function of the corpus: every ledgered session counts, not only the sessions the
current invocation ingested (N.2.1b item 12; D.10.9). Uses the fake worker environment of ``live_fake`` (no benchmark
package); three invocations into one working corpus: ``--repeats 1``, ``--repeats 2``, then a no-op resume.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from live_fake import make_fake_env, repo_root  # noqa: E402

pytestmark = pytest.mark.skipif(os.name == "nt", reason="the fake environment uses a POSIX venv layout")


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "aphome"
    path.mkdir()
    monkeypatch.setenv("AGENTPROV_HOME", str(path))
    monkeypatch.delenv("AGENTPROV_PROGRESS", raising=False)
    monkeypatch.chdir(repo_root())
    return path


def _run(tmp_path: Path, script: Path, repeats: str) -> int:
    from agentprov.cli.main import main

    return main(["run", "agentdojo", "--corpus", str(tmp_path / "corpus"), "--campaign", "t", "--suite", "banking",
                 "--llm-script", str(script), "--max-attempts", "1", "--json", "--progress", "off", "--repeats", repeats])


def _live(tmp_path: Path) -> dict[str, Any]:
    return json.loads((tmp_path / "corpus.partial" / "corpus.json").read_text())["live"]


def _sessions_in_report(live: dict[str, Any]) -> int:
    return sum(m["sessions"] for m in live["quality"]["models"].values())


def test_the_quality_report_covers_every_ledgered_session_across_invocations(home, tmp_path, capsys):
    make_fake_env(home, "ok")
    script = tmp_path / "script.json"
    script.write_text("[]")
    assert _run(tmp_path, script, "1") in (0, 1)
    first = _live(tmp_path)
    assert _sessions_in_report(first) == len(first["sessions"]) == 1
    assert _run(tmp_path, script, "2") in (0, 1)  # resumes: one new session
    second = _live(tmp_path)
    assert len(second["sessions"]) == 2 and _sessions_in_report(second) == 2
    assert _run(tmp_path, script, "2") in (0, 1)  # a no-op resume keeps the report, never wipes it
    third = _live(tmp_path)
    assert third["quality"] == second["quality"]
    capsys.readouterr()
