"""A fake backend environment for the T0 tests of live runs (K.8.4(1), K.8.4(7), K.12.16).

:func:`make_fake_env` builds, under a temporary ``$AGENTPROV_HOME``, an environment that ``agentprov run`` accepts as
``$AGENTPROV_HOME/envs/agentdojo-<commit8>/``: a ``venv`` of the running interpreter (no pip), fake dist-info directories
for ``agentdojo``, ``agentprov-backend`` and ``agentprov-capture`` whose ``RECORD`` files hash the files written here
(the guarded modules included), a ``.pth`` line that makes the real ``agentprov_capture`` importable, a fake
``agentprov_backend.worker`` module speaking ``agentprov-backend/0.1``, and a complete ``AGENTPROV_ENV.json`` marker
computed with the same T0 code ``backends build`` uses. No benchmark package is installed or imported.

The fake worker's behaviour is a ``MODE`` constant baked into its source, because the T2 environment is an explicit
allowlist (a test cannot pass it a variable). Modes:

* ``ok``: a sealed capture log (``session.start``, ``instrumentation``, ``identity`` and its ``identity_digests``
  note) and an honest ``cell_done``;
* ``dotdot``, ``absolute``, ``symlink``, ``hardlink``, ``unreported``, ``mismatch``: the hostile reports of K.8.4(7);
* ``secret``: a staged file carrying :data:`SENTINEL` (T0 holds it as an environment secret);
* ``poisoned``: a capture log poisoned by a failed redaction scan (C.13.10 item 6): the worker's redactor holds a value
  only the worker knows (:data:`WORKER_ONLY_SECRET`), an event whose keys collide once it is redacted is refused, and
  ``close`` seals the log ``errored`` with the constant ``capture.redact`` error; no staged file holds that value, so
  T0's literal scan finds nothing (D-290);
* ``hang``: a started, unsealed log, then no reply (the per-cell timeout kills it);
* ``envdump``: the worker's environment and ``HOME`` written to a reported supporting file;
* ``badhello``: ``hello_ok`` with another RECORD digest; ``badcapture``: a capture identity note differing from
  ``hello_ok``.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

SENTINEL = "sk-agentprov-t0-scan-sentinel-5a1f9c"
WORKER_ONLY_SECRET = "worker-only-redaction-value-81d0"

GUARDED_FILES = (
    "agentdojo/agent_pipeline/llms/anthropic_llm.py",
    "agentdojo/agent_pipeline/llms/openai_llm.py",
    "agentdojo/agent_pipeline/tool_execution.py",
    "agentdojo/benchmark.py",
    "agentdojo/functions_runtime.py",
    "agentdojo/logging.py",
    "agentdojo/task_suite/task_suite.py",
)

_WORKER = r'''
import hashlib, json, os, platform, sys, time
MODE = __MODE__
IDENT = json.loads(__IDENT__)
HELLO_IDENT = json.loads(__HELLO_IDENT__)
SENTINEL = __SENTINEL__
WORKER_ONLY_SECRET = __WORKER_ONLY_SECRET__
P = "agentprov-backend/0.1"
out = os.fdopen(os.dup(1), "wb", buffering=0)
os.dup2(2, 1)

def send(op, **f):
    out.write((json.dumps({"v": P, "op": op, **f}) + "\n").encode())

def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()

def write_log(d, session, attempt, *, seal=True, ident=IDENT, local_model=None):
    from agentprov_capture.log import CaptureLog
    log_path = os.path.join(d, "raw", "capture", session + ".capture.jsonl")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    os.makedirs(os.path.join(d, "raw", "blobs"), exist_ok=True)
    kwargs = {}
    if MODE in ("poisoned", "poisoned_mislabelled"):
        from agentprov_capture.redact import Redactor, Secret
        kwargs["redactor"] = Redactor([Secret("WORKER_ONLY_TOKEN", WORKER_ONLY_SECRET)])
    log = CaptureLog(__import__("pathlib").Path(log_path), session, blobs_dir=__import__("pathlib").Path(d, "raw", "blobs"), **kwargs)
    log.emit("session.start", {"capture": "0.1", "session": session, "ex": "ex_" + session, "attempt": attempt,
             "cell": {"benchmark": "agentdojo", "suite": "banking", "task_id": "user_task_1", "attack_id": None,
                      "attack_target_id": None, "defense_id": None, "attack_params": {}},
             "writer": {"dist": "agentprov-capture", "version": "0.1.0"},
             "backend": {"id": "agentdojo", "version": "0.1.0"},
             "runtime": {"python": ident["python"], "platform": ident["platform"], "lock_sha256": ident["lock_sha256"]},
             "actors": {"agent": {"kind": "llm_agent"}}, "config_sha256": "0" * 64})
    log.emit("instrumentation", {"items": [{"id": "agentdojo.transport_scripted@1", "kind": "test_only", "recorded": "full"}]})
    log.emit("identity", {"benchmark": {"name": "agentdojo", "dist": "agentdojo", "dist_version": ident["version_reported"],
             "suite_set": ident["benchmark_version"], "tool_definitions_sha256": ident["tool_definitions_sha256"],
             "system_prompt_sha256": ident["default_system_prompt_sha256"]},
             "harness": {"dist": "agentprov-backend", "version": "0.1.0"},
             "agent": {"model_requested": "scripted-fake", "provider": "openai_compatible", "endpoint_host": "scripted.invalid"}})
    log.emit("note", {"ns": "agentdojo", "kind": "identity_digests", "payload": ident})
    log.emit("note", {"ns": "agentdojo", "kind": "cell", "payload": {"cell_key": "banking/user_task_1/none/none",
             "kind": "user_task", "benchmark_version": "v1.2.2", "plan_sha256": "0" * 64}})
    if local_model is not None:  # D-693: T0's per-cell observation, recorded as given (as the real backend does)
        log.emit("note", {"ns": "agentdojo", "kind": "local_model", "payload": local_model})
    if MODE in ("poisoned", "poisoned_mislabelled"):
        from agentprov_capture.errors import RedactionError
        try:  # two keys that are equal once the secret is redacted: the scan fails and nothing is written
            log.emit("note", {"ns": "agentdojo", "kind": "x", "payload": {WORKER_ONLY_SECRET: 1, "<redacted:secret>": 2}})
        except RedactionError:
            pass
        assert log.poisoned
    if MODE == "setuprefusal":  # the worker's typed refusal at cell setup (agentprov_backend.attacks), as the real one
        log.emit("error", {"where": "setup", "exception": {"type": "UnsupportedConfiguration", "message":
                 "attack 'important_instructions' names the model: --model-display-name is required"}, "fatal": True})
        return log_path, log.close("errored")
    if seal:
        return log_path, log.close("complete")
    return log_path, None

def artefacts(d):
    res = []
    for root, _dirs, files in os.walk(os.path.join(d, "raw")):
        for name in sorted(files):
            p = os.path.join(root, name)
            if os.path.islink(p):
                continue
            label = os.path.relpath(p, d).replace(os.sep, "/")
            role = "capture_log" if label.endswith(".capture.jsonl") else "blob" if "/blobs/" in label else "supporting"
            res.append({"label": label, "sha256": sha(p), "role": role})
    return res

def run_cell(msg):
    d = msg["session"]["dir"]
    session = msg["session"]["ex"][3:]
    attempt = msg["session"]["attempt"]
    if MODE == "hang":
        write_log(d, session, attempt, seal=False)
        time.sleep(3600)
    path, head = write_log(d, session, attempt, ident=(dict(IDENT, record_digest="f" * 64) if MODE == "badcapture" else IDENT),
                           local_model=msg.get("local_model"))
    arts = artefacts(d)
    if MODE == "dotdot":
        open(os.path.join(d, "..", "x-" + session), "w").write("outside")
        arts.append({"label": "../x-" + session, "sha256": "0" * 64, "role": "supporting"})
    elif MODE == "absolute":
        arts.append({"label": "/etc/hosts", "sha256": "0" * 64, "role": "supporting"})
    elif MODE == "symlink":
        target = os.path.join(os.environ["HOME"], "private.txt")
        open(target, "w").write("private")
        link = os.path.join(d, "raw", "capture", "linked.json")
        os.symlink(target, link)
        arts.append({"label": "raw/capture/linked.json", "sha256": sha(target), "role": "supporting"})
    elif MODE == "hardlink":
        target = os.path.join(os.environ["HOME"], "private.txt")
        open(target, "w").write("private")
        os.link(target, os.path.join(d, "raw", "capture", "hard.json"))
        arts.append({"label": "raw/capture/hard.json", "sha256": sha(target), "role": "supporting"})
    elif MODE == "unreported":
        open(os.path.join(d, "raw", "planted.bin"), "w").write("planted")
    elif MODE == "mismatch":
        arts = [dict(a, sha256="0" * 64) if a["role"] == "capture_log" else a for a in arts]
    elif MODE == "secret":
        open(os.path.join(d, "raw", "leak.txt"), "w").write("key=" + SENTINEL)
        arts = artefacts(d)
    elif MODE == "junksecret":  # an AppleDouble-style name the directory walk of the T0 re-scan skips (CC-2)
        open(os.path.join(d, "raw", "capture", "._leak.json"), "w").write("key=" + SENTINEL)
        arts = artefacts(d)
    elif MODE == "poisoned_mislabelled":  # the poisoned log reported with another role (CC-3)
        arts = [dict(a, role="supporting") if a["role"] == "capture_log" else a for a in arts]
    elif MODE == "envdump":
        p = os.path.join(d, "raw", "env.json")
        json.dump({"environ": dict(os.environ), "home_entries": sorted(os.listdir(os.environ["HOME"]))}, open(p, "w"))
        arts = artefacts(d)
    send("cell_done", req=msg["req"], status="errored" if MODE == "setuprefusal" else "complete", artefacts=arts,
         capture_head=head, outcome=None)

for line in sys.stdin.buffer:
    msg = json.loads(line)
    op = msg["op"]
    if op == "hello":
        ident = dict(HELLO_IDENT, record_digest="e" * 64) if MODE == "badhello" else HELLO_IDENT
        send("hello_ok", nonce=msg["nonce"], identity=ident, worker={"python": platform.python_version(),
             "agentprov_backend_version": "0.1.0", "agentprov_capture_version": "0.1.0"})
    elif op == "plan":
        send("plan_ok", req=msg["req"], plan={"format": "agentprov-run-plan/0.1", "plan_sha256": "0" * 64,
             "cells": [{"cell_key": "banking/user_task_1/none/none", "suite": "banking", "user_task_id": "user_task_1",
                        "injection_task_id": None, "attack": None, "defence": None, "kind": "user_task", "attack_params": {}}],
             "agent": {}, "backend_config": {}})
    elif op == "catalogue":  # D-652; "oldworker" answers as a worker built before the op existed
        if MODE == "oldworker":
            send("fatal", error={"type": "ProtocolError", "message": "unknown op 'catalogue'"})
            sys.exit(2)
        suites = [{"name": "banking", "user_tasks": ["user_task_0", "user_task_1"], "injection_tasks": ["injection_task_0"],
                   "tool_definition_chars": 4321}]
        if MODE == "badcatalogue":
            suites = [{"name": "../banking", "user_tasks": [], "injection_tasks": []}]
        send("catalogue_ok", req=msg["req"], catalogue={
            "format": "agentprov-backend-catalogue/0.1", "backend": "agentdojo",
            "benchmark_version": msg.get("benchmark_version") or "v1.2.2", "benchmark_versions": ["v1.1", "v1.2.2"],
            "suites": suites, "extra_member": "dropped",
            "attacks": [{"name": "important_instructions", "dos": False, "refused": None, "needs": []},
                        {"name": "dos", "dos": True, "refused": None, "needs": []},
                        {"name": "autodojo", "dos": False, "refused": None,
                         "needs": ["--autodojo-cache", "--autodojo-variant"]}]})
    elif op == "run_cell":
        run_cell(msg)
    elif op == "probe":
        # D-729 modes: each probe call is counted in a file at the environment root (one worker process per probe)
        counter = os.path.join(sys.prefix, "probe_calls")
        calls = (int(open(counter).read()) if os.path.exists(counter) else 0) + 1
        open(counter, "w").write(str(calls))
        roles = {"probeunconfirmed": "unconfirmed", "proberefused": "refused",
                 "probeflaky": "unconfirmed" if calls == 1 else "accepted"}.get(MODE, "accepted")
        reason = {"accepted": "instruction_followed", "unconfirmed": "instruction_not_evidenced",
                  "refused": "role_rejected"}[roles]
        send("probe_done", req=msg["req"], status="complete", capture_head=None, artefacts=[],
             results={"reachable": True, "roles_accepted": roles == "accepted", "roles": roles, "roles_reason": reason,
                      "http_status": 200,
                      "params": {"configured": {}, "transmitted": {}, "not_transmitted": []}, "tool_calls": "structured"})
    elif op == "shutdown":
        break
'''


def _record_line(rel: str, data: bytes) -> str:
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
    return f"{rel},sha256={digest},{len(data)}"


def _dist(sp: Path, name: str, version: str, files: dict[str, bytes]) -> None:
    info = sp / f"{name.replace('-', '_')}-{version}.dist-info"
    info.mkdir(parents=True)
    metadata = f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n\n".encode()
    files = {**files, f"{info.name}/METADATA": metadata}
    lines = []
    for rel, data in sorted(files.items()):
        target = sp / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        lines.append(_record_line(rel, data))
    lines.append(f"{info.name}/RECORD,,")
    (info / "RECORD").write_text("\n".join(lines) + "\n")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def make_fake_env(home: Path, mode: str = "ok") -> Path:
    """Build the fake environment and its complete marker; returns the environment directory."""
    from agentprov.cli.live import envs, sandbox

    project = envs.backend_project("agentdojo", repo_root())
    env = envs.env_dir(project, home)
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(env)], check=True, capture_output=True)
    sp = envs.site_packages(env)
    guarded = {rel: f"# fake guarded module {rel}\n".encode() for rel in GUARDED_FILES}
    _dist(sp, "agentdojo", "0.1.35", {"agentdojo/__init__.py": b"", **guarded})
    _dist(sp, "agentprov-capture", "0.1.0", {"agentprov_capture_fake/__init__.py": b""})
    ident: dict[str, Any] = {
        "distribution": "agentdojo", "version_reported": "0.1.35", "source": {"kind": "pypi"}, "record_digest": "",
        "guarded_sources": {"agentdojo.benchmark.run_task_with_injection_tasks": "1" * 64}, "suite_set": ["banking"],
        "benchmark_version": "v1.2.2", "default_system_prompt_sha256": "2" * 64, "tool_definitions_sha256": "3" * 64,
        "python": platform.python_version(), "platform": platform.platform(), "lock_sha256": project.lock_sha256,
        "lock_source": "marker",
    }  # fmt: skip
    record = (next(sp.glob("agentdojo-0.1.35.dist-info")) / "RECORD").read_bytes()
    ident["record_digest"] = hashlib.sha256(record).hexdigest()
    worker = (_WORKER.replace("__MODE__", repr(mode)).replace("__IDENT__", repr(json.dumps(ident)))
              .replace("__HELLO_IDENT__", repr(json.dumps(ident))).replace("__SENTINEL__", repr(SENTINEL))
              .replace("__WORKER_ONLY_SECRET__", repr(WORKER_ONLY_SECRET)))
    _dist(sp, "agentprov-backend", "0.1.0", {"agentprov_backend/__init__.py": b"", "agentprov_backend/worker.py": worker.encode()})
    import agentprov_capture
    import rfc8785

    paths = {str(Path(agentprov_capture.__file__).resolve().parents[1]), str(Path(rfc8785.__file__).resolve().parents[1])}
    (sp / "zz_core_test_paths.pth").write_text("\n".join(sorted(paths)) + "\n")
    identity = envs.compute_identity(env, project)
    marker = {
        "format": envs.MARKER_FORMAT, "backend": "agentdojo", "status": "complete", "env_name": project.env_name,
        "commit": None, "commit8": project.commit8, "commit8_source": project.commit8_source,
        "lock_sha256": project.lock_sha256, "python": platform.python_version(), "nltk_sha256": None,
        "t0_identity": identity.to_json(), "hello_identity": ident,
        "sandbox_probe": {"kind": "sandbox_exec", "status": "failed", "profile_sha256": sandbox.PROFILE_SHA256,
                          "reason": "fake environment", "checks": {}},
        "sandbox_status": "failed",
    }  # fmt: skip
    (env / envs.ENV_MARKER).write_text(json.dumps(marker, indent=2, sort_keys=True) + "\n")
    return env


def env_without(*names: str) -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k not in names}
