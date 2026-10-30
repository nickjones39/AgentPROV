"""The worker over a real subprocess (D.11.3, protocol ``agentprov-backend/0.1``; K.5.7(8); K.12.16 controls that
the backend can check): ``python -I -B -m agentprov_backend.worker`` with an explicit environment allowlist, a
redirected ``HOME``, the session staging directory as working directory, ``AGENTPROV_BLOCK_NETWORK=1``, a scripted
transport file, and a fake key value in the environment that must appear in no staged file and on no channel."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from agentprov_backend.runner import PROBE_KEY
from agentprov_backend.testing.scenarios import SCENARIOS
from agentprov_backend.worker import PROTOCOL

SENTINEL = "sk-agentprov-worker-sentinel-77d2"


def _env(home: Path) -> dict[str, str]:
    return {"PATH": "/usr/bin:/bin", "HOME": str(home), "LANG": "C.UTF-8", "TZ": "UTC",
            "AGENTPROV_BLOCK_NETWORK": "1", "FAKE_PROVIDER_API_KEY": SENTINEL}


def _talk(cwd: Path, home: Path, messages: list[dict], timeout: float = 300) -> tuple[int, list[dict], bytes, bytes]:
    proc = subprocess.run([sys.executable, "-I", "-B", "-m", "agentprov_backend.worker"],
                          input="".join(json.dumps(m) + "\n" for m in messages).encode(), capture_output=True,
                          cwd=cwd, env=_env(home), timeout=timeout)
    lines = proc.stdout.splitlines()
    return proc.returncode, [json.loads(line) for line in lines], proc.stdout, proc.stderr


def _cell_msg(name: str, req: int, session_dir: Path | None = None, ex: str | None = None) -> dict:
    sc = SCENARIOS[name]
    session: dict = {"attempt": 0}
    if ex is not None:
        session["ex"] = ex
    if session_dir is not None:
        session["dir"] = str(session_dir)
    agent = {**sc.agent, "api_key_env": "FAKE_PROVIDER_API_KEY"}
    return {"v": PROTOCOL, "op": "run_cell", "req": req, "cell": dict(sc.cell), "agent": agent, "session": session,
            "plan_sha256": "1" * 64, "attack_env": {}}


def _write_script(d: Path, name: str) -> None:
    d.mkdir(parents=True, exist_ok=True)
    (d / "script.json").write_text(json.dumps(list(SCENARIOS[name].steps)))


@pytest.fixture
def staging(tmp_path):
    home = tmp_path / "t2home"
    home.mkdir()
    return tmp_path / "staging", home


def test_hello_plan_run_cell_shutdown(staging):
    root, home = staging
    s1, s2 = root / "s1", root / "s2"
    _write_script(s1, "benign_banking_single_pass")
    _write_script(s2, "injection_important_instructions")
    ex = "ex_01a11a58-d50f-7001-b660-cec01aed4a91"
    plan_toml = '[plan]\nformat = "agentprov-run-plan/0.1"\nsuites = ["banking"]\nuser_tasks = ["user_task_1"]\n' \
                '[agent]\nmodel_requested = "scripted-fake"\ntransport = "scripted"\nscript = "script.json"\n'
    msgs = [
        {"v": PROTOCOL, "op": "hello", "nonce": "n-1", "expect": {"lock_sha256": "0" * 64}},
        {"v": PROTOCOL, "op": "plan", "req": "p", "plan_toml": plan_toml},
        {"v": PROTOCOL, "op": "plan", "req": "q", "plan_toml": plan_toml.replace("0.1", "9.9")},
        _cell_msg("benign_banking_single_pass", 1, s1, ex),
        _cell_msg("injection_important_instructions", 2, s2),
        {"v": PROTOCOL, "op": "shutdown"},
    ]
    rc, out, raw_out, raw_err = _talk(s1, home, msgs)
    assert rc == 0, raw_err.decode()[-2000:]
    assert all(m["v"] == PROTOCOL for m in out)
    ops = [m["op"] for m in out]
    assert ops[0] == "hello_ok" and out[0]["nonce"] == "n-1"
    ident = out[0]["identity"]
    assert ident["distribution"] == "agentdojo" and ident["version_reported"] == "0.1.35"
    assert len(ident["record_digest"]) == 64 and len(ident["lock_sha256"]) == 64
    assert "agentdojo.agent_pipeline.tool_execution.ToolsExecutor.query" in ident["guarded_sources"]
    assert out[0]["worker"]["agentprov_backend_version"] == "0.1.0"
    assert ops[1:3] == ["plan_ok", "plan_refused"]
    assert out[1]["plan"]["cells"][0]["cell_key"] == "banking/user_task_1/none/none"
    done = [m for m in out if m["op"] == "cell_done"]
    assert [d["req"] for d in done] == [1, 2] and all(d["status"] == "complete" for d in done)
    steps = [m for m in out if m["op"] == "step" and m["req"] == 1]
    assert [s["seq"] for s in steps] == list(range(len(steps)))
    assert {s["kind"] for s in steps} <= {"pass_start", "pass_end", "model_call", "tool_call", "judgement", "capture"}
    assert [m for m in out if m["op"] == "progress" and m["req"] == 1][0]["pass"] == 0
    for d, sdir in zip(done, (s1, s2), strict=True):
        roles = {a["role"] for a in d["artefacts"]}
        assert {"capture_log", "native_log", "blob"} <= roles
        for a in d["artefacts"]:
            p = sdir / a["label"]
            assert hashlib.sha256(p.read_bytes()).hexdigest() == a["sha256"]
        (log,) = [sdir / a["label"] for a in d["artefacts"] if a["role"] == "capture_log"]
        from agentprov_capture.verify import verify_file

        rep = verify_file(log)
        assert rep.sealed and rep.head == d["capture_head"] and rep.status == "complete"
    assert (s1 / f"raw/capture/{ex[3:]}.capture.jsonl").is_file()
    # secrets: absent from every staged file and from both channels
    for p in root.rglob("*"):
        if p.is_file():
            assert SENTINEL.encode() not in p.read_bytes(), p.name
    assert SENTINEL.encode() not in raw_out and SENTINEL.encode() not in raw_err
    # stdout carried the protocol only (every line parsed above); the T2 home stayed empty
    assert list(home.iterdir()) == []


def test_run_cell_in_the_working_directory_session(staging):
    root, home = staging
    s = root / "only"
    _write_script(s, "rerun_three_passes")
    msg = _cell_msg("rerun_three_passes", 7)
    del msg["session"]["attempt"]
    rc, out, _, err = _talk(s, home, [{"v": PROTOCOL, "op": "hello", "nonce": "x"}, msg])
    assert rc == 0, err.decode()[-2000:]
    (done,) = [m for m in out if m["op"] == "cell_done"]
    assert done["status"] == "complete" and done["outcome"] is not None
    assert len([m for m in out if m["op"] == "progress"]) == 3


@pytest.mark.parametrize("bad", [
    b"not json\n",
    b'{"v": "agentprov-backend/0.2", "op": "hello", "nonce": "x"}\n',
    b'{"v": "agentprov-backend/0.1", "op": "hello", "nonce": "x", "nonce": "y"}\n',
    b'{"v": "agentprov-backend/0.1", "op": "run_cell", "req": 1}\n',
    b'{"v": "agentprov-backend/0.1", "op": "launch"}\n',
])
def test_protocol_violations_are_fatal(staging, bad):
    root, home = staging
    root.mkdir()
    proc = subprocess.run([sys.executable, "-I", "-B", "-m", "agentprov_backend.worker"], input=bad,
                          capture_output=True, cwd=root, env=_env(home), timeout=120)
    assert proc.returncode == 2
    (fatal,) = [json.loads(line) for line in proc.stdout.splitlines()]
    assert fatal["op"] == "fatal" and fatal["v"] == PROTOCOL and set(fatal["error"]) == {"type", "message"}


@pytest.mark.parametrize("local_model", ["x", ["x"], {"blob": "y" * 70_000}])
def test_run_cell_local_model_must_be_a_bounded_object(staging, local_model):
    s, home = staging
    s.mkdir()
    _write_script(s, "rerun_three_passes")
    msg = _cell_msg("rerun_three_passes", 7)
    msg["local_model"] = local_model
    rc, out, _, _err = _talk(s, home, [{"v": PROTOCOL, "op": "hello", "nonce": "x"}, msg])
    assert rc == 2 and [m["op"] for m in out][-1] == "fatal"


def test_a_refused_cell_is_sealed_errored(staging):
    root, home = staging
    s = root / "refused"
    _write_script(s, "benign_banking_single_pass")
    msg = _cell_msg("benign_banking_single_pass", 3, s)
    msg["cell"]["defence"] = "no_such_defence"  # not in the registry (D-670)
    rc, out, _, err = _talk(s, home, [{"v": PROTOCOL, "op": "hello", "nonce": "x"}, msg,
                                      {"v": PROTOCOL, "op": "shutdown"}])
    assert rc == 0, err.decode()[-2000:]
    (done,) = [m for m in out if m["op"] == "cell_done"]
    assert done["status"] == "errored" and done["outcome"] is None and done["capture_head"]


def test_probe_op_writes_a_supporting_probe_session(staging):
    root, home = staging
    s = root / "probe"
    s.mkdir(parents=True)
    (s / "probe.json").write_text(json.dumps([{"reply": "tool_calls",
                                               "calls": [{"name": "get_probe_value", "args": {"key": PROBE_KEY}}]}]))
    agent = {"model_requested": "scripted-fake", "transport": "scripted", "script": "probe.json",
             "params": {"temperature": 0.0}}
    rc, out, _, err = _talk(s, home, [{"v": PROTOCOL, "op": "hello", "nonce": "x"},
                                      {"v": PROTOCOL, "op": "probe", "req": "pr", "agent": agent,
                                       "session": {"dir": str(s)}},
                                      {"v": PROTOCOL, "op": "shutdown"}])
    assert rc == 0, err.decode()[-2000:]
    (done,) = [m for m in out if m["op"] == "probe_done"]
    assert done["status"] == "complete" and done["results"]["tool_calls"] == "structured"
    assert done["results"]["roles"] == "accepted" and done["results"]["roles_accepted"] is True
    assert done["results"]["params"]["not_transmitted"] == ["temperature"]
    assert {a["role"] for a in done["artefacts"]} <= {"supporting", "blob"}
