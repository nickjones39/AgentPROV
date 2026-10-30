"""Generate the committed ``capture/0.1`` fixtures for core (K.4; K.8.5; ``tests/fixtures/capture/``).

Runs every scripted scenario of ``agentprov_backend.testing.scenarios`` through the real AgentDojo 0.1.35 stock runner,
in process, with ``ScriptedTransport`` under the recording transport of the real OpenAI SDK client (no network, no
keys; the network guard is installed), and copies each session's staging tree (capture log, blobs, native
TraceLogger JSON) to ``tests/fixtures/capture/<scenario>/session/``, with the scenario's script as
``tests/fixtures/capture/<scenario>/script.json`` and a ``SOURCE.json`` listing every file.

Run from the repository root, in the backend environment::

    uv run --offline --project backends/agentdojo python backends/agentdojo/tools/make_capture_fixtures.py
    uv run --offline --project backends/agentdojo python backends/agentdojo/tools/make_capture_fixtures.py --check

Regeneration is deterministic up to the session id (UUIDv7), the wall-clock and monotonic times, the native log's
``evaluation_timestamp``/``duration``, and therefore the chain hashes and file digests; the projection of each session
(events without envelope times and chain, the session id removed) is stable (RPR-10). ``--check`` regenerates into a
temporary directory and compares those projections with the committed fixtures. The sessions are synthetic
(``agentdojo.transport_scripted@1`` = ``test_only``): corpus packaging refuses them in release mode.

The provider-``anthropic`` scenarios (``ANTHROPIC_SCENARIOS``, D-656) run the declared port of ``AnthropicLLM`` on a real
``AsyncAnthropic`` client over ``ScriptedTransport`` in Messages mode, and are written to
``tests/fixtures/capture/anthropic/<scenario>/``.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from agentprov_backend.runner import AgentConfig, AgentDojoBackend, CaptureSession, CellSpec, build_redactor
from agentprov_backend.testing import ScriptedTransport, messages_step_from_dict, netguard, step_from_dict
from agentprov_backend.testing.scenarios import ANTHROPIC_SCENARIOS, DEFENCE_SCENARIOS, PATCHES, SCENARIOS, Scenario

REPO = Path(__file__).resolve().parents[3]
OUT = REPO / "tests" / "fixtures" / "capture"
LICENCE = ("MIT (AgentPROV: self-authored scripted model output and harness records) AND MIT (AgentDojo 0.1.35 suite "
           "content in the requests, environment snapshots and native log: system prompt, tool descriptions, task "
           "prompts, environment data and attack templates; ethz-spylab/agentdojo, PyPI agentdojo==0.1.35)")


def run_scenario(sc: Scenario, workdir: Path, backend: AgentDojoBackend) -> CaptureSession:
    session_dir = workdir / sc.name / "session"
    session_dir.mkdir(parents=True)
    agent = AgentConfig.from_json(sc.agent)
    session = CaptureSession(session_dir, redactor=build_redactor({}, agent))
    to_step = messages_step_from_dict if sc.agent.get("provider") == "anthropic" else step_from_dict
    transport = ScriptedTransport([to_step(s) for s in sc.steps], model=sc.agent["model_requested"])
    with PATCHES[sc.patch]() if sc.patch else contextlib.nullcontext():
        result = backend.execute(CellSpec.from_json(sc.cell), agent, session,
                                 backend_config=sc.backend_config, inner_transport=transport, environ={},
                                 plan_sha256=None)
    if result.status != sc.expect_status:
        raise SystemExit(f"{sc.name}: status {result.status}, expected {sc.expect_status}")
    if transport.remaining:
        raise SystemExit(f"{sc.name}: {transport.remaining} scripted steps unused")
    return session


def _files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file() and p.name != "SOURCE.json")


def write_fixture(sc: Scenario, session: CaptureSession, dest_root: Path) -> None:
    dest = dest_root / sc.name
    if dest.exists():
        shutil.rmtree(dest)
    (dest / "session").mkdir(parents=True)
    shutil.copytree(session.dir / "raw", dest / "session" / "raw")
    script: Any = list(sc.steps)
    if sc.agent.get("provider") == "anthropic":
        script = {"api": "anthropic_messages", "steps": script}
    (dest / "script.json").write_text(json.dumps(script, indent=2) + "\n", encoding="utf-8")
    entries = []
    for p in _files(dest):
        data = p.read_bytes()
        rel = p.relative_to(dest).as_posix()
        entries.append({
            "sample_file": rel,
            "url": None,
            "repository": "https://github.com/nickjones39/AgentPROV",
            "commit_or_revision": None,
            "original_path": "backends/agentdojo/tools/make_capture_fixtures.py",
            "sha256": hashlib.sha256(data).hexdigest(),
            "size_bytes": len(data),
            "licence": LICENCE,
            "licence_class": "permissive",
            "synthetic": True,
            "retrieved_at": None,
            "note": f"scenario {sc.name}: {sc.description}. Synthetic scripted-transport capture (test_only); "
                    "UUIDv7, times, chain hashes and digests change on regeneration.",
        })
    (dest / "SOURCE.json").write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")


def projection(scenario_dir: Path) -> Any:
    (log,) = sorted((scenario_dir / "session" / "raw" / "capture").glob("*.capture.jsonl"))
    events = []
    for line in log.read_bytes().splitlines():
        e = json.loads(line)
        data = dict(e["data"])
        if e["type"] == "session.start":
            data.pop("session"), data.pop("ex"), data.pop("runtime")      # runtime: machine and lock specific
        if e["type"] == "note" and data.get("kind") == "identity_digests":
            data = {**data, "payload": {k: v for k, v in data["payload"].items()
                                        if k not in ("python", "platform", "lock_sha256", "lock_source")}}
        if e["type"] in ("native.log",):
            data = {}
        if e["type"] == "error":
            data.pop("traceback", None)
            # the traceback blob holds interpreter paths, so its digest depends on where the environment lives
            data["redactions"] = [{k: v for k, v in r.items() if k != "blob"} for r in data.get("redactions", [])]
        events.append((e["seq"], e["type"], e["pass"], e["actor"], data))
    (native,) = sorted((scenario_dir / "session" / "raw" / "capture").glob("*.native.json"))
    nat = {k: v for k, v in json.loads(native.read_bytes()).items() if k not in ("evaluation_timestamp", "duration")}
    return [events, nat]


def _subdir(sc: Scenario) -> str:
    if sc.name in DEFENCE_SCENARIOS:  # defended scenarios live under defence/ (D-670)
        return "defence"
    return "anthropic" if sc.agent.get("provider") == "anthropic" else ""


def _tree_digest(root: Path) -> str:
    """sha256 over the relative paths and bytes of a package's ``.py`` and ``.toml`` files (no caches)."""
    h = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file() and p.suffix in (".py", ".toml")
                       and "__pycache__" not in p.parts):
        h.update(path.relative_to(root).as_posix().encode() + b"\0" + path.read_bytes() + b"\0")
    return h.hexdigest()


def check_installed_harness(project: str) -> None:
    """Refuse to generate fixtures with a harness other than this checkout's (review R3-3): an isolated (``-I``)
    interpreter of this environment imports the installed, non-editable ``agentprov_backend`` and
    ``agentprov_capture``, which must equal ``backends/shared/src`` and ``capture/src``."""
    probe = ("import os, agentprov_backend, agentprov_capture; "
             "print(os.path.dirname(agentprov_backend.__file__)); print(os.path.dirname(agentprov_capture.__file__))")
    out = subprocess.run([sys.executable, "-I", "-c", probe], capture_output=True, text=True, check=True).stdout.split()
    pairs = ((Path(out[0]), REPO / "backends" / "shared" / "src" / "agentprov_backend"),
             (Path(out[1]), REPO / "capture" / "src" / "agentprov_capture"))
    stale = [src.name for installed, src in pairs if _tree_digest(installed) != _tree_digest(src)]
    if stale:
        raise SystemExit(f"the installed {', '.join(stale)} differ from this checkout's source; run: uv sync --offline "
                         f"--project {project} --reinstall-package agentprov-backend --reinstall-package agentprov-capture")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--check", action="store_true", help="regenerate into a temporary directory and compare projections")
    ap.add_argument("--only", nargs="*", default=None)
    args = ap.parse_args(argv)
    check_installed_harness("backends/agentdojo")
    netguard.install()
    time.sleep = lambda s: None  # retry back-off of the SDK/agentdojo never changes what is sent
    backend = AgentDojoBackend()
    table = {**SCENARIOS, **ANTHROPIC_SCENARIOS, **DEFENCE_SCENARIOS}
    names = args.only or list(table)
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "work"
        target = Path(tmp) / "out" if args.check else args.out
        for name in names:
            sc = table[name]
            session = run_scenario(sc, work, backend)
            write_fixture(sc, session, target / _subdir(sc))
            print(f"{name}: {sum(p.stat().st_size for p in _files(target / _subdir(sc) / name))} bytes")  # noqa: T201
        if args.check:
            stale = [n for n in names
                     if json.dumps(projection(target / _subdir(table[n]) / n), sort_keys=True)
                     != json.dumps(projection(args.out / _subdir(table[n]) / n), sort_keys=True)]
            for n in stale:
                print(f"stale: {n}")  # noqa: T201
            return 1 if stale else 0
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
