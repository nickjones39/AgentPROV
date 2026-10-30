"""R-9b-3: ``LiveSessionPipeline.ingest`` returns the index status the session's row will have, before the flush.

Rows are queued until :meth:`CorpusWriter.flush`; :meth:`CorpusWriter.pending_row` builds the queued row by the same rule,
so the outcome's ``status`` equals the ``executions.jsonl`` row written afterwards. ``None`` is kept for a session that
yields no execution.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agentdojo"))

from capture_support import c13_8_session, session_objects  # noqa: E402

from agentprov.adapters.runner.session import LiveSessionPipeline  # noqa: E402
from agentprov.corpus.writer import CorpusWriter  # noqa: E402
from agentprov.ingest.limits import IngestLimits  # noqa: E402


def _files(s) -> list[tuple[str, bytes]]:  # type: ignore[no-untyped-def]
    log = s.log_bytes()
    return [(o.label, log if o.label.endswith(".jsonl") else s.blobs[o.sha256])
            for o in session_objects(log, s.blobs, None, s.session)]


def _ingest(tmp_path: Path, sessions) -> tuple[list, dict[str, str]]:  # type: ignore[no-untyped-def]
    final = tmp_path / "live"
    with CorpusWriter(final, limits=IngestLimits(), command="run") as writer:
        pipeline = LiveSessionPipeline(writer, source_id="agentdojo", part="live", profile_id="agentdojo-live",
                                       corpus_id="r9b3-live", snapshot_id="live", workers=0, in_process=True,
                                       limits=IngestLimits())
        outcomes = []
        for s in sessions:
            outcomes.append(pipeline.ingest(s.session, 0, _files(s)))
            assert writer.has_execution(outcomes[-1].ex or "") is None  # still queued: no flush happened
        writer.flush()
        rows = {}
        for line in (writer.partial / "executions.jsonl").read_bytes().splitlines():
            row = json.loads(line)
            rows[row["ex"]] = row["status"]
    return outcomes, rows


def test_the_outcome_status_is_the_row_status_before_the_flush(tmp_path: Path) -> None:
    clean = c13_8_session()
    outcomes, rows = _ingest(tmp_path, [clean])
    (outcome,) = outcomes
    assert outcome.ex is not None and outcome.status == rows[outcome.ex] == "ok"


def test_a_failed_session_reports_failed_before_the_flush(tmp_path: Path) -> None:
    s = c13_8_session()
    s.close(status="interrupted")  # a second, interrupted session.end: the capture is unsealed (an error issue)
    outcomes, rows = _ingest(tmp_path, [s])
    (outcome,) = outcomes
    assert outcome.status == rows[outcome.ex] == "failed" and "map.capture_unsealed" in outcome.issues


def test_no_execution_keeps_none(tmp_path: Path) -> None:
    final = tmp_path / "live"
    with CorpusWriter(final, limits=IngestLimits(), command="run") as writer:
        pipeline = LiveSessionPipeline(writer, source_id="agentdojo", part="live", profile_id="agentdojo-live",
                                       corpus_id="r9b3-live", snapshot_id="live", workers=0, in_process=True,
                                       limits=IngestLimits())
        outcome = pipeline.ingest("0" * 8 + "-0000-7000-8000-" + "0" * 12, 0, [])
    assert outcome.ex is None and outcome.status is None


def test_pending_row_is_none_for_an_unqueued_execution(tmp_path: Path) -> None:
    with CorpusWriter(tmp_path / "c", limits=IngestLimits(), command="run") as writer:
        assert writer.pending_row("ex_nothing") is None
