"""``agentprov run agentdyn`` end to end with the real AgentDyn environment (D.11.10; D-684, D-685, D-688).

``agentprov backends build agentdyn`` builds the environment once per test session into a temporary ``$AGENTPROV_HOME``
(offline from the uv cache; ``AGENTPROV_TEST_BUILD_NETWORK=1`` lets uv download), and ``agentprov run agentdyn
--llm-script`` runs AgentDyn's own code in the spawned worker with the scripted transport: no network, no key, no model.
Each campaign goes into its own corpus (the campaign is part of the corpus id).

* the catalogue: 7 suites (AgentDojo's four and AgentDyn's shopping, github, dailylife), 17 attacks;
* S1 (shopping, benign) and S2 (github x important_instructions): mapped under ``agentdyn-live``, ``task.benchmark`` is
  ``agentdyn`` (the suite map), SEM ``agentdojo.suites@3``, valid at every tier, no issue;
* S3 (workspace, benign): AgentDyn's copy of an AgentDojo suite keeps the benchmark label ``agentdojo``;
* hello and the catalogue in the real worker under the real-model ``sandbox-exec`` profile (macOS): AgentDyn's
  package ships ``agentdojo/defenses/camel/.env.example``, a file the profile denies even a stat of;
* S4 (dailylife): a tool call with non-JSON arguments, which AgentDyn drops (D-685 (b)): the reply still links to its
  assistant message (``generated_by``), the dropped call is listed in ``ext.agentdojo.dropped_calls`` under
  ``agentdyn.malformed_tool_call_dropped@1`` and never dispatched, and the session has no issue.

Marker ``backend_agentdyn``. Without the uv cache and without the network flag the build fails and every test here
skips with the reason.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from live_fake import repo_root  # noqa: E402

pytestmark = [pytest.mark.backend_agentdyn, pytest.mark.slow,
              pytest.mark.skipif(os.name == "nt", reason="the backend environment is POSIX-only in v0.1"),
              pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")]

DONE = [{"reply": "text", "content": "Done."}]
S1 = [{"reply": "tool_calls", "calls": [{"name": "send_email", "args": {
    "recipients": ["someone@example.com"], "subject": "Order", "body": "Hello"}, "id": "call_1"}]}, *DONE]
S4 = [{"reply": "tool_calls", "content": "Checking.",
       "calls": [{"name": "send_email", "arguments": "{\"recipients\": [", "id": "call_1"}]}]


def _main(*argv: str) -> tuple[int, str, str]:
    import contextlib
    import io

    from agentprov.cli.main import main

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


@pytest.fixture(scope="session")
def live_home(tmp_path_factory: pytest.TempPathFactory) -> Any:
    home = tmp_path_factory.mktemp("agentdyn-home")
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("AGENTPROV_HOME", str(home))
        mp.delenv("AGENTPROV_PROGRESS", raising=False)
        mp.chdir(repo_root())
        argv = ["backends", "build", "agentdyn", "--progress", "off"]
        if os.environ.get("AGENTPROV_TEST_BUILD_NETWORK") == "1":
            argv.append("--allow-network")
        code, _out, err = _main(*argv)
    if code != 0:
        pytest.skip(f"the AgentDyn environment could not be built (exit {code}): {err.strip().splitlines()[-1:]}")
    return home


@pytest.fixture(autouse=True)
def _live_env(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    if "live_home" in request.fixturenames:
        monkeypatch.setenv("AGENTPROV_HOME", str(request.getfixturevalue("live_home")))
        monkeypatch.delenv("AGENTPROV_PROGRESS", raising=False)
        monkeypatch.chdir(repo_root())


def _run(tmp_path: Path, campaign: str, script: list[dict[str, Any]], *cell: str) -> tuple[dict[str, Any], Path]:
    path = tmp_path / f"{campaign}.json"
    path.write_text(json.dumps(script))
    corpus = tmp_path / campaign
    code, out, err = _main("run", "agentdyn", "--corpus", str(corpus), "--campaign", campaign, *cell, "--llm-script",
                           str(path), "--max-attempts", "1", "--json", "--progress", "off")
    summary = json.loads(out)
    assert code in (0, 1), err
    return summary, Path(str(corpus) + ".partial")


def _record(partial: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    (row,) = [json.loads(line) for line in (partial / "executions.jsonl").read_text().splitlines()]
    header = json.loads((partial / row["paths"]["aer"]).read_bytes().splitlines()[0])
    return row, header


def test_the_catalogue_lists_agentdyns_seven_suites(live_home: Path) -> None:
    code, out, err = _main("run", "agentdyn", "--catalogue")
    assert code == 0, err
    cat = json.loads(out)
    assert cat["backend"] == "agentdyn"
    assert [s["name"] for s in cat["suites"]] == ["workspace", "travel", "banking", "slack", "shopping", "github",
                                                  "dailylife"]
    assert len(cat["attacks"]) == 17


@pytest.mark.parametrize(("campaign", "script", "cell", "benchmark"), [
    ("s1", S1, ("--suite", "shopping", "--user-tasks", "user_task_0", "--benign", "only"), "agentdyn"),
    ("s2", DONE, ("--suite", "github", "--user-tasks", "user_task_0", "--attack", "important_instructions",
                  "--injection-tasks", "injection_task_0", "--benign", "exclude", "--model-display-name",
                  "Scripted Model"), "agentdyn"),
    ("s3", DONE, ("--suite", "workspace", "--user-tasks", "user_task_0", "--benign", "only"), "agentdojo"),
])
def test_a_scripted_agentdyn_cell_maps_clean(live_home: Path, tmp_path: Path, campaign: str,
                                            script: list[dict[str, Any]], cell: tuple[str, ...],
                                            benchmark: str) -> None:
    summary, partial = _run(tmp_path, campaign, script, *cell)
    assert summary["counters"]["conclusive"] == 1 and summary["issues_by_code"] == {}
    row, header = _record(partial)
    assert row["status"] == "ok" and row["stages"]["validation"] == "ok"
    assert row["stages"]["sem"] == {"agentdojo.suites@3": "ok"}
    assert row["stages"]["prov"] == {"agentprov-prov/0.1": "ok"}
    assert header["profile"]["id"] == "agentdyn-live" and header["task"]["benchmark"] == benchmark


#: The closed ext schema of the agentdojo family (``message.dropped_calls`` since the D-656 window fix, review R2b-1).
EXT_SCHEMA = repo_root() / "src" / "agentprov" / "adapters" / "agentdojo" / "ext.schema.json"


@pytest.fixture(scope="module")
def s4(live_home: Path, tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """S4 once per module: one tool call with non-JSON arguments, which AgentDyn drops (D-685 (b))."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("AGENTPROV_HOME", str(live_home))
        mp.delenv("AGENTPROV_PROGRESS", raising=False)
        mp.chdir(repo_root())
        summary, partial = _run(tmp_path_factory.mktemp("s4"), "s4", S4, "--suite", "dailylife", "--user-tasks",
                                "user_task_0", "--benign", "only")
    row, header = _record(partial)
    aer = partial / row["paths"]["aer"]
    records = [json.loads(line) for line in aer.read_bytes().splitlines()]
    (call,) = [r for r in records if r.get("k") == "model_call"]
    (reply,) = [r for r in records if r.get("k") == "message" and r.get("role") == "assistant"]
    return {"summary": summary, "row": row, "header": header, "aer": aer, "records": records, "call": call,
            "reply": reply}


def test_a_dropped_malformed_tool_call_is_listed_and_the_reply_still_links(s4: dict[str, Any]) -> None:
    """D-685 (b): AgentDyn drops a tool call whose arguments are not JSON. Under the profile's quirk the mapper matches the
    reply on the calls AgentDyn kept (none), links the assistant message to its model call and lists the dropped call."""
    row, header, records, call, reply = s4["row"], s4["header"], s4["records"], s4["call"], s4["reply"]
    assert s4["summary"]["issues_by_code"] == {}
    assert row["status"] == "ok" and row["stages"]["validation"] == "ok"
    assert header["task"]["benchmark"] == "agentdyn" and header["rules"]["agentdyn"] == 2
    assert reply["generated_by"] == call["id"]
    assert [p["t"] for p in reply["parts"]] == ["text"]
    (dropped,) = reply["ext"]["agentdojo"]["dropped_calls"]
    assert dropped["index"] == 0 and dropped["name"] == "send_email" and dropped["args_raw"] == "{\"recipients\": ["
    assert not [r for r in records if r.get("k") == "tool_execution"]
    (seal,) = [r for r in records if r.get("k") == "seal"]
    assert seal["accounting"]["status"] == "consistent" and not seal.get("issues")


def test_the_dropped_call_record_is_valid_aer_with_its_scoped_rule_and_response_pointers(s4: dict[str, Any]) -> None:
    """Review R2b-2 (1-3): the stored AER validates on its own (release mode); the D rule is cited scoped to
    /ext/agentdojo/dropped_calls; the dropped call's src points into the model call's response blob at its index."""
    from agentprov.aer.rules import RuleRegistry
    from agentprov.aer.validate import validate_file

    report = validate_file(s4["aer"], store=None, catalogues=RuleRegistry(), mode="release")
    assert report.ok, report
    reply, call = s4["reply"], s4["call"]
    assert "agentdyn.malformed_tool_call_dropped@1#/ext/agentdojo/dropped_calls" in reply["rule"]
    assert reply["evf"]["/ext/agentdojo/dropped_calls"] == "D"
    response = call["response"]["$blob"]
    assert {"blob": response, "p": "/choices/0/message/tool_calls/0"} in reply["src"]


def test_dropped_calls_follow_the_closed_ext_schema(s4: dict[str, Any]) -> None:
    """Review R2b-2 (4): every ext.agentdojo of the S4 records against the family's closed ext schema."""
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(EXT_SCHEMA.read_bytes())
    validator = jsonschema.validators.validator_for(schema)(schema)
    for record in s4["records"]:
        ext = (record.get("ext") or {}).get("agentdojo")
        if ext is not None:
            error = jsonschema.exceptions.best_match(validator.iter_errors({record["k"]: ext}))
            assert error is None, (record["k"], error)


@pytest.mark.skipif(sys.platform != "darwin", reason="sandbox-exec exists only on macOS")
def test_hello_and_catalogue_run_under_the_real_model_sandbox(live_home: Path, tmp_path: Path) -> None:
    """L-DY blocker (2026-10-23): the worker died at hello under ``--containment sandbox-exec`` (PermissionError on
    ``camel/.env.example``). The profile is the one real-model runs use; nothing here reaches a model."""
    import subprocess

    from agentprov.cli.live import envs
    from agentprov.cli.live.sandbox import SANDBOX_EXEC, wrap_argv
    from agentprov.cli.live.worker import worker_environment

    if not Path(SANDBOX_EXEC).exists():
        pytest.skip(f"{SANDBOX_EXEC} is not present")
    (env,) = [p for p in (live_home / "envs").iterdir() if p.name.startswith("agentdyn-")]
    staging, t2home = tmp_path / "staging", tmp_path / "t2home"
    staging.mkdir()
    t2home.mkdir()
    argv = [str(envs.env_python(env)), "-I", "-B", "-m", envs.backend_kind("agentdyn").worker_module]
    argv = wrap_argv(argv, staging_root=staging, t2home_root=t2home, repo=repo_root(), home=Path.home(), egress_port=9)
    ops = [{"v": "agentprov-backend/0.1", "op": "hello", "nonce": "n1"},
           {"v": "agentprov-backend/0.1", "op": "catalogue", "req": "r1"},
           {"v": "agentprov-backend/0.1", "op": "shutdown"}]
    proc = subprocess.run(argv, input="".join(json.dumps(op) + "\n" for op in ops).encode(), capture_output=True,
                          env=worker_environment(home=t2home, block_network=True), cwd=staging, timeout=300)
    frames = [json.loads(line) for line in proc.stdout.splitlines()]
    assert proc.returncode == 0, (frames, proc.stderr.decode()[-2000:])
    assert [f["op"] for f in frames if f["op"] in ("hello_ok", "fatal")] == ["hello_ok"]
    assert frames[0]["identity"]["source"]["repo"] == "https://github.com/SaFo-Lab/AgentDyn"
    (catalogue,) = [f["catalogue"] for f in frames if f["op"] == "catalogue_ok"]
    assert len(catalogue["suites"]) == 7


def test_preflight_probe_through_the_real_worker(live_home: Path, tmp_path: Path) -> None:
    """D-742: the scripted preflight probe through this backend's real worker (every live backend kind has one)."""
    probe = tmp_path / "probe.json"
    probe.write_text(json.dumps([{"reply": "tool_calls", "calls": [{"name": "get_probe_value",
                                                                     "args": {"key": "q7f3-probe"}}]}]))
    code, _out, err = _main("run", "agentdyn", "--preflight-only", "--llm-script", str(probe), "--progress", "off")
    assert code == 0, err
    assert "tool_calls=structured" in err and "roles=accepted (instruction_followed)" in err
