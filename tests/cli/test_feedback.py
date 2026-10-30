"""Live feedback (MN N.1.14; DECISIONS D-8): levels, renderers, throttling, content, F2.

The renderers read an injectable clock, so every rate limit is tested without sleeping. A sink built with
``start_thread=False`` leaves its queue undrained until ``pump()``: deterministic. The thread tests use a stalled stream
to show that producers never wait on the display (F2).
"""

from __future__ import annotations

import io
import json
import threading
import time

import pytest

from agentprov.cli.feedback import (
    CONTENT_CHARS_MAX,
    FeedbackConfig,
    FeedbackConfigError,
    FeedbackSink,
    PlainRenderer,
    Snapshot,
    TtyRenderer,
    format_status,
    format_summary,
    is_interactive,
    make_sink,
    open_progress_file,
    resolve_feedback_config,
)
from agentprov.progress import NULL_PROGRESS, EVENT_KINDS, ProgressEvent

CLEAR = "\r\x1b[2K"
WALL = 1_700_000_000.0


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


class FakeTty(io.StringIO):
    def __init__(self, tty: bool = True) -> None:
        super().__init__()
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


def build(level: str, fmt: str, *, show_content: bool = False, content_chars: int = 200, clock: Clock | None = None, **kw):
    clock = clock or Clock()
    out = io.StringIO()
    cfg = FeedbackConfig(level, fmt, None, show_content, content_chars)
    sink = FeedbackSink(cfg, out, clock=clock, wall=lambda: WALL, start_thread=False, **kw)
    return sink, out, clock


def start(sink: FeedbackSink, total: int | None = 4, **fields) -> None:
    sink.emit(ProgressEvent("start", total=total, fields={"command": "validate", "workers": 1, **fields}))


def records(out: io.StringIO | str) -> list[dict]:
    """The event lines of a JSON-lines output, without the 0.2 ``run`` header and ``heartbeat`` snapshots."""
    text = out if isinstance(out, str) else out.getvalue()
    return [r for r in map(json.loads, text.splitlines()) if r["event"] not in ("run", "heartbeat")]


def done(sink: FeedbackSink, unit: str = "u", status: str = "ok", **kw) -> None:
    sink.emit(ProgressEvent("unit_start", unit=unit))
    sink.emit(ProgressEvent("unit_done", unit=unit, status=status, duration_s=0.25, **kw))


# ---------------------------------------------------------------------------------------------- configuration


def resolve(**kw):
    defaults = dict(progress=None, progress_format=None, progress_file=None, show_content=False, content_chars=None,
                    quiet=False, env={}, stream=FakeTty(False))  # fmt: skip
    defaults.update(kw)
    return resolve_feedback_config(**defaults)


def test_default_level_is_status_on_a_terminal_else_summary():
    assert resolve(stream=FakeTty(True)).level == "status"
    assert resolve(stream=FakeTty(False)).level == "summary"
    assert resolve(stream=io.StringIO()).level == "summary"  # no isatty at all


def test_quiet_implies_off_unless_progress_is_given():
    assert resolve(quiet=True, stream=FakeTty(True)).level == "off"
    assert resolve(quiet=True, progress="steps").level == "steps"
    assert resolve(quiet=True, env={"AGENTPROV_PROGRESS": "trace"}).level == "trace"  # the env counts as giving it


def test_progress_flag_beats_environment_beats_default():
    assert resolve(progress="off", env={"AGENTPROV_PROGRESS": "trace"}).level == "off"
    assert resolve(env={"AGENTPROV_PROGRESS": "steps"}).level == "steps"
    assert resolve(env={"AGENTPROV_PROGRESS": ""}).level == "summary"


def test_invalid_level_or_format_is_a_usage_error():
    for kw in ({"env": {"AGENTPROV_PROGRESS": "loud"}}, {"progress": "loud"}, {"progress_format": "fancy"}):
        with pytest.raises(FeedbackConfigError) as caught:
            resolve(**kw)
        assert caught.value.exit_code == 2


def test_auto_format_is_tty_on_an_interactive_terminal_else_plain():
    assert resolve(stream=FakeTty(True)).fmt == "tty"
    assert resolve(stream=FakeTty(False)).fmt == "plain"
    assert resolve(stream=FakeTty(True), env={"TERM": "dumb"}).fmt == "plain"
    assert resolve(stream=FakeTty(True), env={"TERM": "xterm-256color"}).fmt == "tty"


def test_explicit_tty_on_a_non_terminal_degrades_to_plain_never_ansi():
    assert resolve(progress_format="tty", stream=FakeTty(False)).fmt == "plain"
    assert resolve(progress_format="tty", stream=FakeTty(True), env={"TERM": "dumb"}).fmt == "plain"
    assert resolve(progress_format="jsonl", stream=FakeTty(True)).fmt == "jsonl"
    assert resolve(progress_format="plain", stream=FakeTty(True)).fmt == "plain"


def test_is_interactive_is_isatty_plus_term_and_survives_a_closed_stream():
    assert is_interactive(FakeTty(True), {}) is True  # TERM unset (a Windows console) is still interactive
    assert is_interactive(FakeTty(True), {"TERM": "dumb"}) is False
    closed = io.StringIO()
    closed.close()
    assert is_interactive(closed, {}) is False


@pytest.mark.parametrize("chars", [0, -1, CONTENT_CHARS_MAX + 1])
def test_content_chars_bounds(chars):
    with pytest.raises(FeedbackConfigError):
        resolve(content_chars=chars)


def test_content_chars_default_and_maximum():
    assert resolve().content_chars == 200
    assert resolve(content_chars=CONTENT_CHARS_MAX).content_chars == 2000


# ---------------------------------------------------------------------------------------------- the event interface


def test_event_kinds_are_closed_and_null_progress_discards():
    assert EVENT_KINDS == ("start", "unit_start", "unit_done", "step", "trace", "stage", "worker", "session", "control")
    with pytest.raises(ValueError):
        ProgressEvent("shout")
    assert NULL_PROGRESS.emit(ProgressEvent("step")) is None


# ---------------------------------------------------------------------------------------------- levels (N.1.14(1))


def test_off_creates_no_sink_and_no_thread_and_emit_is_a_no_op():
    assert make_sink(FeedbackConfig("off", "plain"), io.StringIO()) is None
    sink, out, _ = build("off", "plain")
    start(sink)
    done(sink)
    sink.pump()
    assert out.getvalue() == "" and sink.close() == 0


def test_summary_level_shows_the_banner_and_the_end_table_only():
    sink, out, clock = build("summary", "plain")
    start(sink, 2, source="demo", isolation="enforced")
    for status in ("sealed", "failed"):
        clock.advance(1.5)
        done(sink, f"unit-{status}", status, codes=("aer.x", "aer.y"))
    sink.emit(ProgressEvent("step", unit="u", stage="map"))
    sink.close(1)
    lines = out.getvalue().splitlines()
    assert lines[0] == "agentprov validate demo: units=2 isolation=enforced workers=1"
    assert not any(line.startswith("  unit ") or line.startswith("  step ") for line in lines)
    assert lines[1] == "validate: finished in 3.0s (exit 1)"
    assert "  units    2 of 2: sealed 1, failed 1" in lines
    assert "  issues   aer.x x2, aer.y x2" in lines


def test_status_level_adds_the_live_status_line_and_nothing_per_unit():
    sink, out, clock = build("status", "plain")
    start(sink, 1000)
    for i in range(500):
        done(sink, f"u{i}")
        sink.pump()  # the renderer keeps up, as a thread would
    text = out.getvalue()
    assert "  unit " not in text
    status = [line for line in text.splitlines() if line.startswith("validate | 500/1000 50%")]
    assert len(status) == 1
    assert "elapsed" in status[0] and "ok 500" in status[0] and "cur u499" in status[0]


def test_steps_level_adds_one_line_per_unit_and_per_stage():
    sink, out, _ = build("steps", "plain")
    start(sink)
    sink.emit(ProgressEvent("step", unit="u1", stage="read", duration_s=0.002, fields={"bytes": 120}))
    done(sink, "u1", "sealed_with_issues", codes=("map.x",))
    sink.pump()
    text = out.getvalue()
    assert "  step read u1 2ms bytes=120" in text
    assert "  unit sealed_with_issues u1 250ms codes: map.x" in text
    assert "  trace" not in text


def test_trace_level_adds_internals_and_the_drop_count_row():
    sink, out, _ = build("trace", "plain")
    start(sink)
    sink.emit(ProgressEvent("trace", unit="u1", stage="capture", fields={"seq": 7, "chain_head": "ab12cd34", "rss_mb": 12.3456}))
    done(sink, "u1", fields={"worker_pid": 99})
    sink.close(0)
    text = out.getvalue()
    assert "  trace capture u1 chain_head=ab12cd34 rss_mb=12.3 seq=7" in text
    assert "worker_pid=99" in text
    assert "  dropped  0 feedback events" in text  # always shown at trace


def test_events_above_the_level_are_not_queued():
    sink, _, _ = build("summary", "plain", queue_size=1)
    for _ in range(50):
        sink.emit(ProgressEvent("step", unit="u", stage="map"))
    assert sink.dropped == 0  # filtered at the door, not dropped


# ---------------------------------------------------------------------------------------------- tty renderer


def tty(level: str = "steps", **kw):
    return build(level, "tty", **kw)


def test_tty_status_line_is_redrawn_at_most_ten_times_a_second():
    sink, out, clock = tty("status")
    start(sink, 100000)
    draws = 0
    seen = 0
    for _ in range(200):  # two simulated seconds, an event every 10 ms
        clock.advance(0.01)
        done(sink, "u")
        sink.pump()
        draws = out.getvalue().count(CLEAR + "validate ")
        seen += 1
    assert 15 <= draws <= int(2.0 * 10) + 1
    # a burst inside one instant costs one draw at most
    before = out.getvalue().count(CLEAR + "validate ")
    for _ in range(2000):
        done(sink, "burst")
    sink.pump()
    assert out.getvalue().count(CLEAR + "validate ") - before <= 1
    assert seen == 200


def test_tty_redraws_again_once_the_interval_has_passed():
    sink, out, clock = tty("status")
    start(sink, 10)
    sink.pump()
    first = out.getvalue().count(CLEAR + "validate ")
    done(sink)
    sink.pump()
    assert out.getvalue().count(CLEAR + "validate ") == first  # same instant: throttled
    clock.advance(0.1)
    sink.pump()
    assert out.getvalue().count(CLEAR + "validate ") == first + 1


def test_tty_step_lines_are_printed_above_the_status_line():
    sink, out, clock = tty("steps")
    start(sink, 3)
    sink.pump()
    clock.advance(1.0)
    sink.emit(ProgressEvent("step", unit="u1", stage="map", duration_s=0.01))
    sink.pump()
    text = out.getvalue()
    # the status line is erased, the step line printed with a newline, the status left for the next throttled redraw
    assert CLEAR + "  step map u1 10ms\n" in text
    assert not text.endswith("\n")  # a status line (no newline) is on screen again
    last_line = text.rsplit("\n", 1)[1]
    assert last_line.startswith(CLEAR + "validate ") or last_line == ""


def test_tty_finish_clears_the_status_line_and_prints_the_summary():
    sink, out, _ = tty("status")
    start(sink, 1)
    done(sink)
    sink.pump()
    sink.close(0)
    text = out.getvalue()
    assert text.rstrip("\n").splitlines()[-2].endswith("units    1 of 1: ok 1") or "units    1 of 1: ok 1" in text
    assert "finished in" in text and text.endswith("\n")
    assert CLEAR + "validate: finished" in text  # the live line was erased first


def test_tty_status_line_is_truncated_to_the_terminal_width():
    clock = Clock()
    out = io.StringIO()
    cfg = FeedbackConfig("status", "tty")
    renderer = TtyRenderer(out, cfg, columns=lambda: 30)
    snap = Snapshot("validate", 100, 5, (("ok", 5),), (), "a-very-long-unit-name-that-would-wrap-the-line", 0.0, 0)
    renderer._dirty = True
    renderer.tick(1.0, lambda: snap)
    line = out.getvalue()[len(CLEAR):]
    assert len(line) <= 29 and line.endswith("~")
    assert clock.t == 0.0


def test_ansi_appears_only_in_the_tty_renderer():
    for fmt in ("plain", "jsonl"):
        sink, out, clock = build("trace", fmt, show_content=True)
        start(sink, 2)
        sink.emit(ProgressEvent("step", unit="u", stage="map", content="c\x1b[31m", locator="/x"))
        done(sink, "u\x1b[2J")
        clock.advance(30)
        sink.close(0)
        assert "\x1b" not in out.getvalue(), fmt


# ---------------------------------------------------------------------------------------------- plain renderer


def test_plain_status_every_ten_seconds():
    sink, out, clock = build("status", "plain")
    start(sink, 1000)
    sink.pump()
    for _ in range(25):  # 25 simulated seconds, one unit a second
        clock.advance(1.0)
        done(sink)
        sink.pump()
    status = [line for line in out.getvalue().splitlines() if line.startswith("validate ") and "elapsed" in line]
    assert len(status) == 2  # at t = 10 s and t = 20 s


def test_plain_status_every_500_units_even_inside_ten_seconds():
    sink, out, clock = build("status", "plain")
    start(sink, 5000)
    for _ in range(1200):  # all at one instant
        done(sink)
        sink.pump()
    status = [line for line in out.getvalue().splitlines() if "elapsed" in line]
    assert len(status) == 2  # at 500 and 1000 units; the burst never prints more
    assert status[0].startswith("validate | 500/5000") and status[1].startswith("validate | 1000/5000")


def test_plain_renderer_unit_thresholds_are_injectable():
    out = io.StringIO()
    renderer = PlainRenderer(out, FeedbackConfig("status", "plain"), min_interval_s=1.0, min_units=2, start=0.0)
    snap = Snapshot("validate", 10, 2, (("ok", 2),), (), None, 0.0, 0)
    renderer.tick(0.5, lambda: snap)
    assert out.getvalue().count("elapsed") == 1  # two units since the last status: due by units
    renderer.tick(0.6, lambda: snap)
    assert out.getvalue().count("elapsed") == 1
    renderer.tick(1.6, lambda: snap)
    assert out.getvalue().count("elapsed") == 2  # due by time


# ---------------------------------------------------------------------------------------------- status line content


def test_status_line_has_done_total_percent_rate_eta_elapsed_counters_and_current():
    snap = Snapshot("import", 200, 50, (("sealed", 40), ("sealed_with_issues", 6), ("failed", 3), ("refused", 1)), (), "ex_abc#loc", 100.0, 0)
    line = format_status(snap, 110.0)
    assert line.startswith("import | 50/200 25% | 5.0/s | ETA 30.0s | elapsed 10.0s | sealed 40, sealed_with_issues 6, failed 3, refused 1 | cur ex_abc#loc")


def test_status_line_without_a_total_has_no_percentage_or_eta():
    line = format_status(Snapshot("derive", None, 7, (), (), None, 0.0, 0), 7.0)
    assert line == "derive | 7 done | 1.0/s | elapsed 7.0s"


def test_unknown_statuses_sort_after_the_known_ones():
    sink, out, _ = build("summary", "plain")
    for status in ("zz", "failed", "aa", "sealed"):
        done(sink, status=status)
    sink.close(0)
    assert "sealed 1, failed 1, aa 1, zz 1" in out.getvalue()


def test_end_summary_formats_issue_overflow():
    snap = Snapshot("x", 1, 1, (("ok", 1),), tuple((f"c{i:02d}", 1) for i in range(15)), None, 0.0, 3)
    lines = format_summary(snap, 1.0, None, show_drops=False)
    assert any("and 3 more codes" in line for line in lines)
    assert lines[-1].startswith("  dropped  3")


# ---------------------------------------------------------------------------------------------- untrusted strings


def test_every_data_derived_string_is_escaped_in_text_output():
    sink, out, _ = build("trace", "plain")
    start(sink, 1, source="src\x1b[0m")
    sink.emit(ProgressEvent("step", unit="u\u202e\n", stage="st\x07", fields={"k\x1b": "v\x1b[31m"}))
    done(sink, "u\x00", "ok\x1b", codes=("c\x1b",))
    sink.close(0)
    text = out.getvalue()
    for raw in ("\x1b", "\u202e", "\x07", "\x00"):
        assert raw not in text
    assert text.count("\n") == len(text.splitlines())  # no stray line breaks inside a field
    for escaped in ("<U+001B>", "<U+202E>", "<U+0007>", "<U+0000>"):
        assert escaped in text


# ---------------------------------------------------------------------------------------------- content


def test_content_is_never_shown_without_show_content():
    for fmt in ("plain", "jsonl"):
        sink, out, _ = build("trace", fmt, show_content=False)
        sink.emit(ProgressEvent("step", unit="u", stage="model_call", content="TOP SECRET prompt", locator="/m/1"))
        sink.close(0)
        assert "TOP SECRET" not in out.getvalue(), fmt
        assert "UNTRUSTED" not in out.getvalue()


def test_show_content_uses_quote_untrusted_and_truncates_to_content_chars():
    sink, out, _ = build("steps", "plain", show_content=True, content_chars=10)
    sink.emit(ProgressEvent("step", unit="u", stage="tool_call", content="0123456789abcdef\x1b[2J", locator="loc"))
    sink.pump()
    text = out.getvalue()
    assert "<<UNTRUSTED " in text and "source=loc" in text and "<<END UNTRUSTED " in text
    assert "0123456789[truncated: " in text and "\x1b" not in text
    assert "abcdef" not in text


def test_show_content_needs_the_steps_level():
    sink, out, _ = build("status", "plain", show_content=True)
    sink.emit(ProgressEvent("step", unit="u", stage="x", content="payload"))
    sink.pump()
    assert "payload" not in out.getvalue()


def test_content_source_is_capped_before_it_is_queued():
    sink, _, _ = build("steps", "plain", show_content=True)
    sink.emit(ProgressEvent("step", unit="u", stage="x", content="x" * 100_000))
    queued = sink._queue.get_nowait()
    assert len(queued.event.content) == 8192


def test_jsonl_content_only_with_show_content_and_fenced():
    sink, out, _ = build("steps", "jsonl", show_content=True, content_chars=5)
    sink.emit(ProgressEvent("step", unit="u", stage="x", content="abcdefghij", locator="/l"))
    sink.pump()
    obj = records(out)[0]
    assert obj["content"].startswith("<<UNTRUSTED ") and "abcde[truncated: 5 more chars]" in obj["content"]


# ---------------------------------------------------------------------------------------------- jsonl writer


def test_jsonl_objects_follow_agentprov_progress_0_2_and_keep_the_0_1_shapes():
    sink, out, clock = build("steps", "jsonl")
    start(sink, 2, source="demo")
    sink.emit(ProgressEvent("step", unit="u1", stage="map", duration_s=0.5, fields={"bytes": 3, "ok": True, "x": None, "f": 1.5}))
    done(sink, "u1", "failed", codes=("map.bad",))
    clock.advance(2.0)
    sink.close(1)
    every = [json.loads(line) for line in out.getvalue().splitlines()]
    seen = records(out)
    assert [r["event"] for r in seen] == ["start", "step", "unit_start", "unit_done", "end"]
    assert every[0]["event"] == "run" and every[-2]["event"] == "heartbeat"
    for record in every:
        assert record["v"] == "agentprov-progress/0.2" and record["run"] == sink.run_id
        assert record["ts"] == "2023-11-14T22:13:20.000Z"
        assert record["level"] in ("summary", "status", "steps", "trace")
    assert sorted(r["seq"] for r in every) == list(range(len(every)))  # no event was dropped: no gap
    step = next(r for r in seen if r["event"] == "step")
    assert step | {"ts": "", "seq": 0, "run": ""} == {
        "v": "agentprov-progress/0.2", "ts": "", "seq": 0, "run": "", "level": "steps", "event": "step", "unit": "u1",
        "stage": "map", "duration_s": 0.5, "bytes": 3, "ok": True, "x": None, "f": 1.5}  # fmt: skip
    end = seen[-1]
    assert end["outcome"] == "failures"
    assert end["event"] == "end" and end["exit_code"] == 1 and end["dropped"] == 0
    assert end["counts"] == {"failed": 1} and end["issues"] == {"map.bad": 1} and end["units_done"] == 1 and end["total"] == 2


def test_jsonl_lines_are_canonical_and_reserved_keys_do_not_collide():
    sink, out, _ = build("steps", "jsonl")
    sink.emit(ProgressEvent("step", unit="u", fields={"event": "evil", "v": 9, "ts": "x"}))
    sink.pump()
    line = next(line for line in out.getvalue().splitlines() if '"event":"step"' in line)
    obj = json.loads(line)
    assert obj["event"] == "step" and obj["field_event"] == "evil" and obj["field_v"] == 9 and obj["field_ts"] == "x"
    from agentprov.io.canonical import jcs_bytes

    assert line.encode() == jcs_bytes(obj)


def test_jsonl_non_finite_numbers_become_null():
    sink, out, _ = build("steps", "jsonl")
    sink.emit(ProgressEvent("step", unit="u", duration_s=float("nan"), fields={"a": float("inf")}))
    sink.pump()
    obj = records(out)[0]
    assert "duration_s" not in obj and obj["a"] is None


def test_progress_file_receives_jsonl_at_the_selected_level_and_is_closed(tmp_path):
    path = tmp_path / "events.jsonl"
    cfg = FeedbackConfig("steps", "plain", str(path))
    sink = make_sink(cfg, io.StringIO())
    assert sink is not None
    start(sink, 1)
    sink.emit(ProgressEvent("step", unit="u", stage="map"))
    sink.emit(ProgressEvent("trace", unit="u", stage="deep"))  # above the level: not written
    done(sink)
    sink.close(0)
    raw = path.read_bytes()
    assert b"\r" not in raw and raw.endswith(b"\n")
    events = [r["event"] for r in records(raw.decode())]
    assert events[0] == "start" and "step" in events and "trace" not in events and events[-1] == "end"
    assert sink._file is not None and sink._file.closed


def test_open_progress_file_errors_are_usage_errors(tmp_path):
    with pytest.raises(FeedbackConfigError):
        open_progress_file(str(tmp_path / "missing" / "x.jsonl"))


# ---------------------------------------------------------------------------------------------- drops and counters


def test_a_full_queue_drops_and_counts_and_never_blocks():
    sink, out, _ = build("steps", "plain", queue_size=3)
    for i in range(10):
        sink.emit(ProgressEvent("step", unit=f"u{i}", stage="map"))
    assert sink.dropped == 7
    sink.pump()
    assert out.getvalue().count("  step map") == 3
    sink.close(0)
    assert "  dropped  7 feedback events" in out.getvalue()


def test_counters_survive_dropped_events():
    sink, out, _ = build("steps", "plain", queue_size=2)
    start(sink, 20)
    for i in range(20):
        done(sink, f"u{i}", "ok" if i % 2 else "failed", codes=("c.x",))
    assert sink.dropped > 0
    sink.close(1)
    text = out.getvalue()
    assert "units    20 of 20: ok 10, failed 10" in text
    assert "issues   c.x x20" in text


def test_drop_count_is_in_the_jsonl_end_event():
    sink, out, _ = build("steps", "jsonl", queue_size=2)
    for i in range(5):
        sink.emit(ProgressEvent("step", unit=f"u{i}"))
    sink.close(0)
    assert json.loads(out.getvalue().splitlines()[-1])["dropped"] == 3


def test_distinct_issue_codes_and_statuses_are_bounded():
    sink, _, _ = build("summary", "plain")
    for i in range(1500):
        sink.emit(ProgressEvent("unit_done", unit="u", status=f"s{i}", codes=(f"c{i}",)))
    snap = sink._snapshot()
    assert len(snap.issues) <= 1001 and len(snap.counts) <= 51
    assert dict(snap.issues)["<other>"] == 500 and dict(snap.counts)["<other>"] == 1450


def test_emit_never_raises_and_a_closed_sink_ignores_events():
    sink, out, _ = build("steps", "plain")
    sink.emit(ProgressEvent("step", unit=None, stage=None, fields={"k": object()}))  # type: ignore[dict-item]
    sink.close(0)
    sink.emit(ProgressEvent("step", unit="late"))
    sink.close(0)  # idempotent
    assert "late" not in out.getvalue()


class BrokenPipe(io.StringIO):
    def write(self, s, /):
        raise BrokenPipeError

    def flush(self):
        raise BrokenPipeError


def test_a_failing_output_disables_that_renderer_and_the_producer_is_unaffected():
    clock = Clock()
    cfg = FeedbackConfig("steps", "plain")
    sink = FeedbackSink(cfg, BrokenPipe(), clock=clock, start_thread=False)
    for i in range(10):
        sink.emit(ProgressEvent("step", unit=f"u{i}"))
    sink.pump()
    sink.close(0)  # must not raise
    assert sink.dropped == 0


# ---------------------------------------------------------------------------------------------- the thread, F2


class Stalled(io.StringIO):
    """A terminal that has stopped reading: ``write`` blocks until released."""

    def __init__(self) -> None:
        super().__init__()
        self.release = threading.Event()
        self.entered = threading.Event()

    def write(self, s, /):
        self.entered.set()
        self.release.wait(30)
        return super().write(s)


def threads_named(name: str) -> list[threading.Thread]:
    return [t for t in threading.enumerate() if t.name == name and t.is_alive()]


@pytest.mark.parametrize("stalled", ["stderr", "file"])
def test_f2_a_stalled_display_does_not_block_the_producer(stalled):
    blocker = Stalled()
    cfg = FeedbackConfig("steps", "plain")
    quiet = io.StringIO()
    sink = FeedbackSink(cfg, blocker if stalled == "stderr" else quiet, file=blocker if stalled == "file" else None)
    try:
        sink.emit(ProgressEvent("start", total=100000, fields={"command": "x"}))
        assert blocker.entered.wait(10)  # the renderer thread is now stuck inside write()
        started = time.monotonic()
        for i in range(20000):
            sink.emit(ProgressEvent("step", unit=f"u{i}", stage="map"))
            sink.emit(ProgressEvent("unit_done", unit=f"u{i}", status="ok"))
        elapsed = time.monotonic() - started
        assert elapsed < 5.0, "producers must never wait on the display"
        assert sink.dropped > 0  # the bounded queue filled and dropped, counting
        assert sink._snapshot().done == 20000  # counters were never lost
        t0 = time.monotonic()
        sink.close(0, timeout=0.2)  # close() does not wait forever either
        assert time.monotonic() - t0 < 3.0
    finally:
        blocker.release.set()
        for t in threads_named("agentprov-feedback"):
            t.join(10)
    assert threads_named("agentprov-feedback") == []


def test_the_renderer_thread_drains_and_prints_the_end_table():
    out = io.StringIO()
    cfg = FeedbackConfig("steps", "plain")
    sink = FeedbackSink(cfg, out)
    sink.emit(ProgressEvent("start", total=3, fields={"command": "validate", "isolation": "watchdog"}))
    for i in range(3):
        sink.emit(ProgressEvent("unit_start", unit=f"u{i}"))
        sink.emit(ProgressEvent("unit_done", unit=f"u{i}", status="sealed", duration_s=0.001))
    dropped = sink.close(0)
    text = out.getvalue()
    assert dropped == 0
    assert text.splitlines()[0] == "agentprov validate: units=3 isolation=watchdog"
    assert text.count("  unit sealed u") == 3
    assert "validate: finished in" in text and "units    3 of 3: sealed 3" in text
    assert threads_named("agentprov-feedback") == []


def test_one_producer_thread_per_worker_is_safe():
    out = io.StringIO()
    sink = FeedbackSink(FeedbackConfig("status", "plain"), out)
    sink.emit(ProgressEvent("start", total=4000, fields={"command": "x"}))

    def produce() -> None:
        for _ in range(1000):
            sink.emit(ProgressEvent("unit_done", unit="u", status="ok", codes=("a.b",)))

    threads = [threading.Thread(target=produce) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    sink.close(0)
    assert "units    4000 of 4000: ok 4000" in out.getvalue()
    assert "a.b x4000" in out.getvalue()
