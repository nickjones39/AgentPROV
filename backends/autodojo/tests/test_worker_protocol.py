"""The worker over a real subprocess against the fork (D.11.3, D.11.5): ``python -I -B -m agentprov_backend.worker``
with an explicit environment allowlist (no key variable but a fake sentinel), a redirected ``HOME``, the session staging
directory as working directory and ``AGENTPROV_BLOCK_NETWORK=1``.

* identity handshake: the digests T0 computes from the environment's files (here recomputed by the test the way
  ``agentprov.cli.live.envs.compute_identity`` does, without importing the core) equal ``hello_ok`` and the capture's
  ``identity`` event and ``agentdojo/identity_digests`` note;
* a fork banking cell under ``important_instructions`` and an ``autodojo`` cache-replay cell (the parent stages the
  synthetic cache under ``raw/attack/``): sealed, chain verified, every reported artefact hash verified, the cache
  reported ``supporting``;
* a forced kill mid-cell: the parent appends ``session.end{aborted, appended_by: parent}``
  (``agentprov_capture.log.append_terminal``, as ``agentprov.cli.live.campaign`` does) and the log verifies sealed.
"""

from __future__ import annotations

import hashlib
import json
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from agentprov_backend.testing.scenarios import (
    AUTODOJO_CACHE_LABEL,
    AUTODOJO_KILL_SCRIPT,
    AUTODOJO_SCENARIOS,
    autodojo_cache_bytes,
)
from agentprov_backend.worker import PROTOCOL

SENTINEL = "sk-agentprov-autodojo-sentinel-5be1"
PIN = "aa458794b7eb7f082e94daeac4c0f55bfc0c90cc"


def _env(home: Path) -> dict[str, str]:
    return {"PATH": "/usr/bin:/bin", "HOME": str(home), "LANG": "C.UTF-8", "TZ": "UTC",
            "AGENTPROV_BLOCK_NETWORK": "1", "FAKE_PROVIDER_API_KEY": SENTINEL}


def _argv() -> list[str]:
    return [sys.executable, "-I", "-B", "-m", "agentprov_backend.worker"]


def _cell_msg(name: str, req: int, session_dir: Path, ex: str | None = None) -> dict:
    sc = AUTODOJO_SCENARIOS[name]
    session: dict = {"attempt": 0, "dir": str(session_dir)}
    if ex is not None:
        session["ex"] = ex
    agent = {**sc.agent, "api_key_env": "FAKE_PROVIDER_API_KEY"}
    return {"v": PROTOCOL, "op": "run_cell", "req": req, "cell": dict(sc.cell), "agent": agent, "session": session,
            "plan_sha256": "1" * 64, "attack_env": dict(sc.attack_env)}


def _stage(d: Path, steps) -> None:
    d.mkdir(parents=True, exist_ok=True)
    (d / "script.json").write_text(json.dumps(list(steps)))


def _t0_expect() -> dict:
    """What T0 computes before spawn (D.10.6; ``envs.compute_identity`` + ``EnvIdentity.expect``), from files only."""
    import importlib.metadata

    dist = importlib.metadata.distribution("agentdojo")
    record = next(f for f in dist.files if f.name == "RECORD" and f.parent.name.endswith(".dist-info"))
    lock = Path(sys.prefix).parent / "uv.lock"          # the in-project layout (D.10.10 item 3(b))
    return {"commit": json.loads(dist.read_text("direct_url.json"))["vcs_info"]["commit_id"],
            "lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest(),
            "record_sha256": hashlib.sha256(Path(dist.locate_file(record)).read_bytes()).hexdigest()}


@pytest.fixture
def staging(tmp_path):
    home = tmp_path / "t2home"
    home.mkdir()
    return tmp_path / "staging", home


def test_handshake_cells_and_artefacts(staging):
    root, home = staging
    s1, s2 = root / "s1", root / "s2"
    _stage(s1, AUTODOJO_SCENARIOS["autodojo_banking_important_instructions"].steps)
    _stage(s2, AUTODOJO_SCENARIOS["autodojo_banking_cache_replay"].steps)
    (s2 / AUTODOJO_CACHE_LABEL).parent.mkdir(parents=True)
    (s2 / AUTODOJO_CACHE_LABEL).write_bytes(autodojo_cache_bytes())
    expect = _t0_expect()
    msgs = [{"v": PROTOCOL, "op": "hello", "nonce": "n-1", "expect": expect},
            _cell_msg("autodojo_banking_important_instructions", 1, s1, "ex_01a11a58-d50f-7001-b660-cec01aed4a92"),
            _cell_msg("autodojo_banking_cache_replay", 2, s2),
            {"v": PROTOCOL, "op": "shutdown"}]
    proc = subprocess.run(_argv(), input="".join(json.dumps(m) + "\n" for m in msgs).encode(), capture_output=True,
                          cwd=s1, env=_env(home), timeout=600)
    assert proc.returncode == 0, proc.stderr.decode()[-3000:]
    out = [json.loads(line) for line in proc.stdout.splitlines()]
    hello = out[0]
    assert hello["op"] == "hello_ok" and hello["worker"]["backend"] == "autodojo"
    ident = hello["identity"]
    # T0 expect == hello_ok
    assert ident["source"]["commit"] == expect["commit"] == PIN
    assert ident["record_digest"] == expect["record_sha256"] and ident["lock_sha256"] == expect["lock_sha256"]
    assert ident["version_reported"] == "0.1.35"
    done = [m for m in out if m["op"] == "cell_done"]
    assert [d["status"] for d in done] == ["complete", "complete"]
    from agentprov_capture.verify import verify_file

    for d, sdir in zip(done, (s1, s2), strict=True):
        for a in d["artefacts"]:
            assert hashlib.sha256((sdir / a["label"]).read_bytes()).hexdigest() == a["sha256"]
        (log,) = [sdir / a["label"] for a in d["artefacts"] if a["role"] == "capture_log"]
        rep = verify_file(log)
        assert rep.sealed and rep.head == d["capture_head"] and rep.status == "complete" and not rep.issues
        events = [json.loads(line) for line in log.read_bytes().splitlines()]
        # hello_ok == the capture identity event and the identity_digests note
        (ident_event,) = [e for e in events if e["type"] == "identity"]
        assert ident_event["data"]["benchmark"]["commit"] == expect["commit"]
        (digests,) = [e["data"]["payload"] for e in events
                      if e["type"] == "note" and e["data"]["kind"] == "identity_digests"]
        assert digests == ident
        items = [i["id"] for i in [e for e in events if e["type"] == "instrumentation"][0]["data"]["items"]]
        assert "agentdojo.transport_scripted@1" in items
    roles = {a["label"]: a["role"] for a in done[1]["artefacts"]}
    assert roles[AUTODOJO_CACHE_LABEL] == "supporting"
    assert next(a for a in done[1]["artefacts"] if a["label"] == AUTODOJO_CACHE_LABEL)["sha256"] == \
        hashlib.sha256(autodojo_cache_bytes()).hexdigest()
    for p in root.rglob("*"):
        if p.is_file():
            assert SENTINEL.encode() not in p.read_bytes(), p.name
    assert SENTINEL.encode() not in proc.stdout and SENTINEL.encode() not in proc.stderr
    assert list(home.iterdir()) == []


def test_a_forced_kill_is_sealed_aborted_by_the_parent(staging):
    from agentprov_capture.log import append_terminal
    from agentprov_capture.verify import verify_file

    root, home = staging
    s = root / "killed"
    _stage(s, AUTODOJO_KILL_SCRIPT)
    session = "01a11a58-d50f-7001-b660-cec01aed4a93"
    msg = _cell_msg("autodojo_banking_important_instructions", 9, s, "ex_" + session)
    proc = subprocess.Popen(_argv(), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            cwd=s, env=_env(home))
    watchdog = threading.Timer(300, proc.kill)
    watchdog.start()
    try:
        assert proc.stdin is not None and proc.stdout is not None
        proc.stdin.write((json.dumps({"v": PROTOCOL, "op": "hello", "nonce": "k"}) + "\n" + json.dumps(msg) + "\n").encode())
        proc.stdin.flush()
        seen = []
        while True:
            line = proc.stdout.readline()
            assert line, "the worker ended before the cell started"
            m = json.loads(line)
            seen.append(m["op"])
            if m["op"] == "step" and m.get("kind") == "pass_start":
                break
        log = s / f"raw/capture/{session}.capture.jsonl"
        deadline = time.monotonic() + 120
        while b'"type":"llm.request"' not in log.read_bytes():   # the first wire request is now stalled in the cell
            assert time.monotonic() < deadline, "no llm.request was recorded"
            threading.Event().wait(0.05)
        proc.send_signal(signal.SIGKILL)
        proc.wait(timeout=60)
    finally:
        watchdog.cancel()
    assert proc.returncode == -signal.SIGKILL and "cell_done" not in seen
    before = verify_file(log)
    assert not before.sealed
    head = append_terminal(log, "aborted")
    rep = verify_file(log)
    assert rep.sealed and rep.status == "aborted" and rep.appended_by == "parent" and rep.head == head
    assert not rep.issues
    events = [json.loads(line) for line in log.read_bytes().splitlines()]
    assert [e["type"] for e in events][:3] == ["session.start", "instrumentation", "identity"]
    assert events[-1]["data"] == {"status": "aborted", "n_events": len(events), "appended_by": "parent"}
    assert any(e["type"] == "llm.request" for e in events)      # the stalled request was recorded before the send
