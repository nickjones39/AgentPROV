"""``--control-file`` (D-394; design.md §4.6): drain and stop requests polled from a file, acknowledged as ``control``
progress events. A stop takes the first-SIGTERM path on every OS; a drain degrades to a stop for a command that does not
honour it, and says so."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from agentprov.cli import control
from agentprov.cli.control import ControlRequest, ControlWatcher, parse_request
from agentprov.progress import ProgressEvent


def _write(path: Path, request: str, nonce: str = "0123456789abcdef", **extra: Any) -> None:
    doc = {"format": "agentprov-control/0.1", "request": request, "issued": "2026-10-14T12:00:00Z", "nonce": nonce,
           **extra}
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(doc))
    os.replace(tmp, path)  # atomic, as the GUI writes it
    st = path.stat()
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))  # a distinct mtime even on a coarse clock


class Events:
    def __init__(self) -> None:
        self.events: list[ProgressEvent] = []

    def emit(self, event: ProgressEvent) -> None:
        self.events.append(event)


@pytest.fixture
def watcher(tmp_path: Path):
    stops: list[int] = []
    events = Events()
    w = ControlWatcher(tmp_path / "control.json", command="import", progress=events, interrupt=lambda: stops.append(1))
    yield w, stops, events
    w.close()
    control.reset()


@pytest.mark.parametrize("data, reason", [
    (b"{", "not strict JSON"),
    (b'{"format": "other/1"}', "not an agentprov-control/0.1 object"),
    (b'{"format": "agentprov-control/0.1", "request": "stop", "issued": "t", "nonce": "XYZ"}', "nonce"),
    (b'{"format": "agentprov-control/0.1", "request": "pause", "issued": "t", "nonce": "0123456789abcdef"}', "unknown"),
    (b" " * 5000, "larger than 4 KiB"),
])
def test_invalid_requests_are_refused_with_a_reason_that_never_echoes_the_file(data, reason):
    found = parse_request(data)
    assert isinstance(found, str) and reason in found


def test_a_request_left_by_an_earlier_invocation_is_never_acted_on(tmp_path, watcher):
    w, stops, events = watcher
    _write(w.path, "stop")
    w.start()
    w.poll()
    assert stops == [] and events.events == []


def test_stop_interrupts_once_and_is_acknowledged(watcher):
    w, stops, events = watcher
    w.start()
    _write(w.path, "stop", nonce="aaaaaaaaaaaaaaaa")
    w.poll()
    w.poll()  # unchanged file: nothing
    _write(w.path, "stop", nonce="aaaaaaaaaaaaaaaa")  # same nonce rewritten: ignored
    w.poll()
    assert stops == [1]
    (ack,) = events.events
    assert ack.kind == "control" and dict(ack.fields) == {"request": "stop", "nonce": "aaaaaaaaaaaaaaaa",
                                                           "accepted": True, "effect": "stop"}
    assert w.notice() == "control file: stop (nonce aaaaaaaaaaaaaaaa): stop"


def test_drain_degrades_to_stop_for_a_command_that_does_not_honour_it(watcher):
    w, stops, events = watcher
    w.start()
    _write(w.path, "drain")
    w.poll()
    assert stops == [1] and not control.draining()
    assert events.events[0].fields["effect"] == "stop (drain is not supported by import yet)"


def test_a_command_that_honours_drain_sees_draining_and_is_not_interrupted(watcher):
    w, stops, events = watcher
    w.start()
    control.drain_supported()
    _write(w.path, "drain")
    w.poll()
    assert stops == [] and control.draining() and w.effect == "drain"


def test_a_broken_file_is_acknowledged_as_not_accepted_and_stops_nothing(watcher):
    w, stops, events = watcher
    w.start()
    w.path.write_text("not json")
    w.poll()
    assert stops == [] and events.events[0].fields["accepted"] is False


def test_a_stop_from_the_control_file_ends_a_command_through_the_clean_path(cli, tmp_path, monkeypatch):
    """End to end: a long command, a stop written by another process, exit 130 with the notice and the ack event."""
    from agentprov.cli import info

    started = threading.Event()

    def long_info(ctx: Any) -> Any:
        started.set()
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            time.sleep(0.02)
        raise AssertionError("the control file stop never arrived")

    monkeypatch.setattr(info, "run_info", long_info)
    path = tmp_path / "control.json"
    events = tmp_path / "events.jsonl"

    def writer() -> None:
        started.wait(10)
        time.sleep(0.2)
        _write(path, "stop", nonce="feedfacefeedface")

    thread = threading.Thread(target=writer)
    thread.start()
    run = cli("info", "--control-file", str(path), "--progress-file", str(events), "--json")
    thread.join()
    assert run.code == 130, run.err
    assert "control file: stop (nonce feedfacefeedface): stop" in run.json()["notices"]
    lines = [json.loads(line) for line in events.read_text().splitlines()]
    (ack,) = [x for x in lines if x["event"] == "control"]
    assert ack["accepted"] is True and ack["nonce"] == "feedfacefeedface"
    assert lines[-1]["event"] == "end" and lines[-1]["outcome"] == "interrupted"


def test_the_control_file_directory_must_exist(cli, tmp_path):
    assert cli("info", "--control-file", str(tmp_path / "missing" / "c.json")).code == 2


def test_the_request_types_are_closed():
    assert control.REQUESTS == ("drain", "stop") and isinstance(
        parse_request(b'{"format":"agentprov-control/0.1","request":"drain","issued":"t","nonce":"0123456789abcdef"}'),
        ControlRequest)
