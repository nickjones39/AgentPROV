"""The Inspect worker end to end over ``agentprov-backend/0.1`` with the scripted transport (D-669).

Needs an environment with ``inspect_ai`` and ``inspect_evals`` and the provisioned dataset (``backends build
inspect-agentharm``, or a development environment prepared the same way); skipped otherwise. The worker runs as a
subprocess with the network guard on: no network, no key. Sample ids only; no dataset text is read or printed.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from agentprov_backend_inspect.benchmarks import agentharm
from agentprov_backend_inspect.provision import env_dataset_dir

pytest.importorskip("inspect_evals")
if not (env_dataset_dir(agentharm) / next(iter(agentharm.DATASET_FILES))).is_file():
    pytest.skip("the environment has no provisioned AgentHarm dataset", allow_module_level=True)

V = "agentprov-backend/0.1"
PLAN = """
[plan]
format = "agentprov-run-plan/0.1"
backend = "inspect-agentharm"
[inspect]
task = "inspect_evals/agentharm"
params = { split = "test_public" }
samples = { limit = 2 }
limits = { message_limit = 20, token_limit = 60000, time_limit_s = 600 }
max_connections = 1
[agent]
model_requested = "scripted-fake"
endpoint = "scripted"
transport = "scripted"
script = "llm-script.json"
[judges.refusal_judge]
model_requested = "scripted-judge"
endpoint = "scripted"
transport = "scripted"
script = "llm-script.json"
[judges.semantic_judge]
model_requested = "scripted-judge"
endpoint = "scripted"
transport = "scripted"
script = "llm-script.json"
"""


class Conversation:
    def __init__(self, home: Path) -> None:
        env = {"PATH": "/usr/bin:/bin", "HOME": str(home), "LANG": "C.UTF-8", "TZ": "UTC",
               "AGENTPROV_BLOCK_NETWORK": "1", "AGENTPROV_INSPECT_BACKEND": "inspect-agentharm"}
        if "PYTHONPATH" in os.environ:  # development environments (sources not installed)
            env["PYTHONPATH"] = os.environ["PYTHONPATH"]
        self.proc = subprocess.Popen([sys.executable, "-B", "-m", "agentprov_backend_inspect.worker"],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
                                     cwd=home)

    def ask(self, op: str, **fields: object) -> dict:
        assert self.proc.stdin is not None and self.proc.stdout is not None
        self.proc.stdin.write((json.dumps({"v": V, "op": op, **fields}) + "\n").encode())
        self.proc.stdin.flush()
        while True:
            line = self.proc.stdout.readline()
            assert line, self.proc.stderr.read().decode(errors="replace")[-3000:] if self.proc.stderr else "eof"
            msg = json.loads(line)
            if msg["op"] not in ("step", "progress"):
                return msg

    def close(self) -> None:
        if self.proc.stdin is not None:
            self.proc.stdin.write((json.dumps({"v": V, "op": "shutdown"}) + "\n").encode())
            self.proc.stdin.close()
        self.proc.wait(timeout=60)


@pytest.fixture
def worker(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    conv = Conversation(home)
    yield conv
    conv.close()


def test_hello_plan_catalogue(worker):
    hello = worker.ask("hello", nonce="n1")
    assert hello["op"] == "hello_ok" and hello["worker"]["backend"] == "inspect-agentharm"
    ident = hello["identity"]
    assert ident["distribution"] == "inspect-ai" and ident["version_reported"] == "0.3.263"
    assert ident["benchmark"]["version"] == "0.20.0" and ident["task_files_sha256"].startswith("sha256:")
    assert set(ident["dataset"]["files"]) == set(agentharm.DATASET_FILES)
    plan = worker.ask("plan", req=1, plan_toml=PLAN)
    assert plan["op"] == "plan_ok" and len(plan["plan"]["cells"]) == 1
    refused = worker.ask("plan", req=2, plan_toml=PLAN.replace("limit = 2", "limit = 0"))
    assert refused["op"] == "plan_refused"
    from agentprov_backend.worker import Worker

    if hasattr(Worker, "op_catalogue"):  # the shared dispatch of the catalogue op comes with D-652 (gui-g3)
        cat = worker.ask("catalogue", req=3)
        assert cat["op"] == "catalogue_ok" and cat["catalogue"]["format"] == "agentprov-inspect-catalogue/0.1"


AGENT = {"model_requested": "scripted-fake", "provider": "openai", "endpoint": "scripted", "api_key_env": None,
         "params": {}, "llm_element": "native", "transport": "scripted", "script": "llm-script.json", "base_url": None}


def _combined_script(verdict: str) -> str:
    """One staged script for the agent and every judge role (agent and judge calls interleave)."""
    judge = [{"reply": "text", "content": f"Answer: {verdict}"}] * 20
    return json.dumps({"agent": [{"reply": "text", "content": "I will not help with that request."}] * 4,
                       "judges": {"refusal_judge": judge, "semantic_judge": judge}})


def _run_cell(worker, session, plan, cell):
    agent = {k: v for k, v in AGENT.items() if v is not None}
    return worker.ask("run_cell", req=2, cell=cell, agent=agent, plan_sha256=plan["plan_sha256"],
                      backend_config=plan["backend_config"],
                      session={"ex": "ex_01890000-0000-7000-8000-000000000001", "attempt": 0, "dir": str(session)})


def test_a_scripted_cell_writes_an_eval_and_a_verified_wire_log(worker, tmp_path):
    session = tmp_path / "session"
    session.mkdir()
    (session / "llm-script.json").write_text(_combined_script("Yes"))
    assert worker.ask("hello", nonce="n1")["op"] == "hello_ok"
    plan = worker.ask("plan", req=1, plan_toml=PLAN)["plan"]
    cell = plan["cells"][0]
    done = _run_cell(worker, session, plan, cell)
    assert done["op"] == "cell_done", done
    assert done["status"] == "complete" and done["outcome"]["samples"] == 2
    roles = {a["role"] for a in done["artefacts"]}
    assert {"capture_log", "native_log", "blob"} <= roles
    native = next(a for a in done["artefacts"] if a["role"] == "native_log")
    assert native["label"].startswith("raw/inspect/") and native["label"].endswith(".eval")
    import zipfile_zstd  # noqa: F401 - Inspect writes .eval members with method 93 (zstd); Python 3.12 reads it via this
    # (the core importer reads it with Python 3.14's compression.zstd, agentprov.ingest.archives)

    with zipfile.ZipFile(session / native["label"]) as z:
        header = json.loads(z.read("header.json"))
    assert header["eval"]["packages"] == {"inspect_ai": "0.3.263", "inspect_evals": "0.20.0"}
    assert header["eval"]["model"] == "openai-api/scripted/scripted-fake"
    # the client's name only, and the SDK client's own retries off (models.py; D-740)
    assert header["eval"]["model_args"] == {"http_client": None, "max_retries": 0}
    # the wire log: a chain-verified capture/0.1 session with one llm.request per exchange, agent and judges
    from agentprov_capture.verify import verify_file

    log = next(a for a in done["artefacts"] if a["role"] == "capture_log")
    report = verify_file(session / log["label"])
    assert report.sealed and not report.issues and report.status == "complete", report
    assert report.head == done["capture_head"]
    events = [json.loads(line) for line in (session / log["label"]).read_text().splitlines()]
    requests = [e for e in events if e["type"] == "llm.request"]
    assert {e["data"]["role"] for e in requests} == {"agent", "auxiliary"}
    assert sum(e["data"]["role"] == "agent" for e in requests) == 2
    assert events[-1]["type"] == "session.end" and events[-1]["data"]["status"] == "complete"


def test_a_run_cell_whose_cell_was_altered_is_refused(worker, tmp_path):
    session = tmp_path / "session"
    session.mkdir()
    (session / "llm-script.json").write_text(_combined_script("Yes"))
    assert worker.ask("hello", nonce="n1")["op"] == "hello_ok"
    plan = worker.ask("plan", req=1, plan_toml=PLAN)["plan"]
    cell = dict(plan["cells"][0], sample_ids=["1-3", "1-4"])  # other samples under the same key
    done = _run_cell(worker, session, plan, cell)
    assert done["op"] == "fatal" and "cell key" in done["error"]["message"]



def test_judges_on_the_agents_model_and_later_cells_get_their_own_models(worker, tmp_path):
    """D-743: the probe's shape (judges on the agent's model, one sample per cell, several cells in one worker).
    Inspect's memoized get_model handed the judges the agent's Model and the second cell the first cell's (its capture
    session closed): every sample after the first errored without a request."""
    plan_toml = (PLAN.replace('model_requested = "scripted-judge"', 'model_requested = "scripted-fake"')
                 .replace("max_connections = 1", "max_connections = 1\ncell_size = 1"))
    assert worker.ask("hello", nonce="n1")["op"] == "hello_ok"
    plan = worker.ask("plan", req=1, plan_toml=plan_toml)["plan"]
    assert len(plan["cells"]) == 2
    for i, cell in enumerate(plan["cells"]):
        session = tmp_path / f"session{i}"
        session.mkdir()
        (session / "llm-script.json").write_text(_combined_script("Yes"))
        agent = {k: v for k, v in AGENT.items() if v is not None}
        done = worker.ask("run_cell", req=10 + i, cell=cell, agent=agent, plan_sha256=plan["plan_sha256"],
                          backend_config=plan["backend_config"],
                          session={"ex": f"ex_01890000-0000-7000-8000-00000000000{i + 2}", "attempt": 0,
                                   "dir": str(session)})
        assert done["op"] == "cell_done" and done["status"] == "complete", done
        assert done["outcome"] == {"status": "success", "samples": 1, "samples_errored": 0}, done["outcome"]
        log = next(a for a in done["artefacts"] if a["role"] == "capture_log")
        events = [json.loads(line) for line in (session / log["label"]).read_text().splitlines()]
        requests = [e for e in events if e["type"] == "llm.request"]
        assert sum(e["data"]["role"] == "agent" for e in requests) == 1, i
        judges = {e["actor"] for e in requests if e["data"]["role"] == "auxiliary"}
        assert judges and judges <= {"judge0", "judge1"}, i  # the semantic judge runs only if the grading uses it
        assert all(e["actor"] == "agent" for e in requests if e["data"]["role"] == "agent"), i


def test_a_cell_whose_sample_errored_is_incomplete(worker, tmp_path):
    """D-743: Inspect's log status stays "success" when a sample errors (fail_on_error=False); the cell is reported
    incomplete with an ``inspect/samples_errored`` note, so T0 counts it inconclusive and the run exits 1."""
    session = tmp_path / "session"
    session.mkdir()
    judge = [{"reply": "text", "content": "Answer: No"}] * 20
    (session / "llm-script.json").write_text(json.dumps({"agent": [{"fail": "http", "status": 500}] * 8,
                                                         "judges": {"refusal_judge": judge, "semantic_judge": judge}}))
    assert worker.ask("hello", nonce="n1")["op"] == "hello_ok"
    plan = worker.ask("plan", req=1, plan_toml=PLAN)["plan"]
    done = _run_cell(worker, session, plan, plan["cells"][0])
    assert done["op"] == "cell_done" and done["status"] == "incomplete", done
    assert done["outcome"]["status"] == "success" and done["outcome"]["samples_errored"] == 2, done["outcome"]
    log = next(a for a in done["artefacts"] if a["role"] == "capture_log")
    events = [json.loads(line) for line in (session / log["label"]).read_text().splitlines()]
    (note,) = [e["data"]["payload"] for e in events if e["type"] == "note" and e["data"]["kind"] == "samples_errored"]
    assert note["count"] == 2 and len(note["sample_ids"]) == 2
    assert events[-1]["type"] == "session.end" and events[-1]["data"]["status"] == "incomplete"

# ------------------------------------------------------------------ the preflight probe (D-742)

PROBE_CALL = {"reply": "tool_calls", "calls": [{"name": "get_probe_value", "args": {"key": "q7f3-probe"}}]}


def _probe(worker, session, script, **agent_extra):
    (session / "llm-script.json").write_text(json.dumps(script))
    agent = {**{k: v for k, v in AGENT.items() if v is not None}, **agent_extra}
    return worker.ask("probe", req="probe", agent=agent,
                      session={"ex": "ex_01890000-0000-7000-8000-0000000000aa", "dir": str(session)})


def test_the_probe_runs_through_the_inspect_model_without_agentdojo(worker, tmp_path):
    """D-742: the Inspect worker's own probe (the shared one needs AgentDojo's LLM element): one canned two-tool
    request through Inspect's model and the recording transport, judged by the shared verdicts."""
    import importlib.util

    assert importlib.util.find_spec("agentdojo") is None  # the environment the probe must work in
    session = tmp_path / "session"
    session.mkdir()
    assert worker.ask("hello", nonce="n1")["op"] == "hello_ok"
    done = _probe(worker, session, [PROBE_CALL], params={"temperature": 0.0})
    assert done["op"] == "probe_done", done
    assert done["status"] == "complete"
    results = done["results"]
    assert results["reachable"] and results["http_status"] == 200 and results["tool_calls"] == "structured"
    assert results["roles"] == "accepted" and results["roles_accepted"]
    # a configured sampling parameter is not transmitted, as in a cell (A3)
    assert results["params"]["not_transmitted"] == ["temperature"]
    roles = {a["role"] for a in done["artefacts"]}
    assert "supporting" in roles and "capture_log" not in roles and "native_log" not in roles
    from agentprov_capture.verify import verify_file

    log = next(a for a in done["artefacts"] if a["role"] == "supporting" and a["label"].endswith(".capture.jsonl"))
    report = verify_file(session / log["label"])
    assert report.sealed and not report.issues and report.status == "complete", report
    events = [json.loads(line) for line in (session / log["label"]).read_text().splitlines()]
    requests = [e for e in events if e["type"] == "llm.request"]
    assert len(requests) == 1 and requests[0]["data"]["role"] == "agent"
    (items,) = [e["data"]["items"] for e in events if e["type"] == "instrumentation"]
    ids = {i["id"] for i in items}
    assert {"inspect.preflight_probe@1", "inspect.transport_scripted@1", "inspect.harness_settings@2"} <= ids


@pytest.mark.parametrize(("step", "roles", "tool_calls"), [
    ({"reply": "text", "content": "Probe received."}, "unconfirmed", "none"),
    ({"reply": "text", "content": "<function=get_probe_value>{\"key\": \"q7f3-probe\"}</function>"}, "accepted",
     "text_encoded"),
    ({"fail": "http", "status": 400}, "refused", "error"),
])
def test_the_probe_verdicts_come_from_the_reply(worker, tmp_path, step, roles, tool_calls):
    session = tmp_path / "session"
    session.mkdir()
    assert worker.ask("hello", nonce="n1")["op"] == "hello_ok"
    done = _probe(worker, session, [step] * 2)  # a 4xx is not retried; a second step covers a retried one
    assert done["op"] == "probe_done", done
    assert done["results"]["roles"] == roles and done["results"]["tool_calls"] == tool_calls, done["results"]
