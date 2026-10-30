"""K.13 RPR-10, backend half: a second scripted run of the same scenario yields different raw evidence (session ids,
times, chain heads, file digests) but the same projection. The projection here is the backend's own: every event
without its envelope times and chain, with the session identifiers removed, and the native log without its
``evaluation_timestamp`` and ``duration`` (the core ``common_projection`` of K.8.5 runs on the committed fixtures)."""

from __future__ import annotations

import hashlib
import json

import pytest

from support import run_scenario

VOLATILE_START = {"session", "ex"}


def projection(run) -> list:
    out = []
    for e in run.events:
        data = dict(e["data"])
        if e["type"] == "session.start":
            data = {k: v for k, v in data.items() if k not in VOLATILE_START}
        if e["type"] == "native.log":
            data = {}
        if e["type"] == "error":
            data = {k: v for k, v in data.items() if k != "traceback"}
        out.append((e["seq"], e["type"], e["pass"], e["actor"], data))
    native = {k: v for k, v in run.native().items() if k not in ("evaluation_timestamp", "duration")}
    return [out, native]


@pytest.mark.parametrize("name", ["benign_banking_single_pass", "rerun_three_passes", "gateway_compat_malformed_discarded",
                                  "failing_cell_uncaught_400"])
def test_two_runs_differ_in_raw_and_agree_in_projection(tmp_path, name):
    a = run_scenario(tmp_path / "a", name)
    b = run_scenario(tmp_path / "b", name)
    assert a.session.session != b.session.session
    assert a.result.capture_head != b.result.capture_head
    digest = lambda r: hashlib.sha256(r.session.capture_path.read_bytes()).hexdigest()  # noqa: E731
    assert digest(a) != digest(b)
    assert [e["ts"] for e in a.events] != [e["ts"] for e in b.events] or a.events[0]["data"]["ex"] != b.events[0]["data"]["ex"]
    assert json.dumps(projection(a), sort_keys=True) == json.dumps(projection(b), sort_keys=True)
