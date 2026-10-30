"""K.13 RPR-10, backend half, on the fork: two scripted runs of a scenario differ in raw evidence (session ids, times,
chain heads) but agree in the projection that ``tools/make_capture_fixtures.py --check`` compares."""

from __future__ import annotations

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


@pytest.mark.parametrize("name", ["autodojo_banking_cache_replay", "autodojo_error_skipped_json_decode"])
def test_two_runs_differ_in_raw_and_agree_in_projection(tmp_path, name):
    a = run_scenario(tmp_path / "a", name)
    b = run_scenario(tmp_path / "b", name)
    assert a.session.session != b.session.session and a.result.capture_head != b.result.capture_head
    assert json.dumps(projection(a), sort_keys=True) == json.dumps(projection(b), sort_keys=True)
