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


def test_the_quality_report_reads_each_session_once_and_equals_a_full_rebuild(home, tmp_path, capsys, monkeypatch):
    """AU-RN-9: report() runs on every write of the documents; it reads each ledgered session's log and blobs once per
    invocation and returns exactly what a rebuild from every stored log returns (so live.quality's bytes are unchanged).
    Checked at every write of a three-session campaign and of its resume."""
    from agentprov.cli.live import campaign as cm
    from agentprov.cli.live.quality import quality_report
    from agentprov.io.canonical import jcs_bytes
    from agentprov.raw.store import RawObjectStore

    reads = {"n": 0}
    real_read = RawObjectStore.read_bytes

    def counted(self, sha256):
        reads["n"] += 1
        return real_read(self, sha256)

    monkeypatch.setattr(RawObjectStore, "read_bytes", counted)
    real_report = cm.Campaign.report
    checked: list[int] = []

    def report(self):
        first = real_report(self)
        reads["n"] = 0
        again = real_report(self)  # nothing new was ledgered in between: no stored object is read
        assert reads["n"] == 0
        per_cell: dict[str, int] = {}
        for e in self.ledger.entries:
            per_cell[f"{e['cell_key']}#{e['repeat']}"] = per_cell.get(f"{e['cell_key']}#{e['repeat']}", 0) + 1
        rebuilt = quality_report([self._stored_quality(e)[0] for e in self.ledger.entries
                                  if e.get("status") != "quarantined"], per_cell)  # the rule before AU-RN-9
        assert jcs_bytes(first) == jcs_bytes(again) == jcs_bytes(rebuilt)
        checked.append(len(self.ledger.entries))
        return first

    monkeypatch.setattr(cm.Campaign, "report", report)
    make_fake_env(home, "ok")
    script = tmp_path / "script.json"
    script.write_text("[]")
    assert _run(tmp_path, script, "3") in (0, 1)
    assert _sessions_in_report(_live(tmp_path)) == 3 and max(checked) == 3
    checked.clear()
    assert _run(tmp_path, script, "4") in (0, 1)  # its first report reads the three earlier sessions and the new one
    assert _sessions_in_report(_live(tmp_path)) == 4 and checked and set(checked) == {4}
    capsys.readouterr()
