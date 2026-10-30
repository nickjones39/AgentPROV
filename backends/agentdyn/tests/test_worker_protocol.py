"""The worker over a real subprocess against AgentDyn (D-688 T1/T2): ``python -I -B -m agentprov_backend.worker`` with
an explicit environment allowlist (no key variable but a fake sentinel), a redirected ``HOME``, the session staging
directory as working directory and ``AGENTPROV_BLOCK_NETWORK=1``. The ``hello_ok`` identity equals what T0 computes from
the environment's files (recomputed here as ``agentprov.cli.live.envs`` does, without importing the core), the
``catalogue`` op answers for ``agentdyn``, and two scripted cells seal with verified artefacts."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from agentprov_backend.worker import PROTOCOL
from support import PIN, REPO, SCENARIOS, SYSTEM_PROMPT_SHA256

SENTINEL = "sk-agentprov-agentdyn-sentinel-7c2d"


def _env(home: Path) -> dict[str, str]:
    return {"PATH": "/usr/bin:/bin", "HOME": str(home), "LANG": "C.UTF-8", "TZ": "UTC",
            "AGENTPROV_BLOCK_NETWORK": "1", "FAKE_PROVIDER_API_KEY": SENTINEL}


def _cell_msg(name: str, req: int, session_dir: Path) -> dict:
    sc = SCENARIOS[name]
    return {"v": PROTOCOL, "op": "run_cell", "req": req, "cell": dict(sc.cell),
            "agent": {**sc.agent, "api_key_env": "FAKE_PROVIDER_API_KEY"},
            "session": {"attempt": 0, "dir": str(session_dir)}, "plan_sha256": "1" * 64, "attack_env": {}}


def _t0_expect() -> dict:
    import importlib.metadata

    dist = importlib.metadata.distribution("agentdojo")
    record = next(f for f in dist.files if f.name == "RECORD" and f.parent.name.endswith(".dist-info"))
    lock = Path(sys.prefix).parent / "uv.lock"
    return {"commit": json.loads(dist.read_text("direct_url.json"))["vcs_info"]["commit_id"],
            "lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest(),
            "record_sha256": hashlib.sha256(Path(dist.locate_file(record)).read_bytes()).hexdigest()}


def test_handshake_catalogue_cells_and_artefacts(tmp_path):
    from agentprov_capture.verify import verify_file

    home = tmp_path / "t2home"
    home.mkdir()
    dirs = {}
    for name in ("s1_shopping_benign", "s2_github_important_instructions"):
        d = tmp_path / "staging" / name
        d.mkdir(parents=True)
        (d / "script.json").write_text(json.dumps(list(SCENARIOS[name].steps)))
        dirs[name] = d
    expect = _t0_expect()
    msgs = [{"v": PROTOCOL, "op": "hello", "nonce": "n-1", "expect": expect},
            {"v": PROTOCOL, "op": "catalogue", "req": 1},
            *(_cell_msg(name, i + 2, d) for i, (name, d) in enumerate(dirs.items())),
            {"v": PROTOCOL, "op": "shutdown"}]
    first = next(iter(dirs.values()))
    proc = subprocess.run([sys.executable, "-I", "-B", "-m", "agentprov_backend.worker"],
                          input="".join(json.dumps(m) + "\n" for m in msgs).encode(), capture_output=True, cwd=first,
                          env=_env(home), timeout=600)
    assert proc.returncode == 0, proc.stderr.decode()[-3000:]
    out = [json.loads(line) for line in proc.stdout.splitlines()]
    hello = out[0]
    assert hello["op"] == "hello_ok" and hello["worker"]["backend"] == "agentdyn"
    ident = hello["identity"]
    assert ident["source"] == {"kind": "git", "repo": REPO, "commit": PIN} and expect["commit"] == PIN
    assert ident["record_digest"] == expect["record_sha256"] and ident["lock_sha256"] == expect["lock_sha256"]
    assert ident["version_reported"] == "0.1.35" and ident["default_system_prompt_sha256"] == SYSTEM_PROMPT_SHA256
    (cat,) = [m for m in out if m["op"] == "catalogue_ok"]
    assert cat["catalogue"]["backend"] == "agentdyn" and len(cat["catalogue"]["suites"]) == 7
    done = [m for m in out if m["op"] == "cell_done"]
    assert [d["status"] for d in done] == ["complete", "complete"]
    for d, sdir in zip(done, dirs.values(), strict=True):
        for a in d["artefacts"]:
            assert hashlib.sha256((sdir / a["label"]).read_bytes()).hexdigest() == a["sha256"]
        (log,) = [sdir / a["label"] for a in d["artefacts"] if a["role"] == "capture_log"]
        rep = verify_file(log)
        assert rep.sealed and rep.head == d["capture_head"] and rep.status == "complete" and not rep.issues
        events = [json.loads(line) for line in log.read_bytes().splitlines()]
        (digests,) = [e["data"]["payload"] for e in events
                      if e["type"] == "note" and e["data"]["kind"] == "identity_digests"]
        assert digests == ident
    for p in (tmp_path / "staging").rglob("*"):
        if p.is_file():
            assert SENTINEL.encode() not in p.read_bytes(), p.name
    assert SENTINEL.encode() not in proc.stdout and SENTINEL.encode() not in proc.stderr
    assert list(home.iterdir()) == []
