"""Units of the live parent side: the plan TOML writer, the canary and quality report (D.10.9), the protocol client's
strictness (D.11.3), the worker environment (G.6.3), and the run-time gates that a test can reach without keys (consent,
containment, endpoint rules; N.1.11)."""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
import tomllib
from pathlib import Path

import pytest

from agentprov.cli.live.quality import canary_conditions, quality_report, session_quality


def _log(*events: dict) -> bytes:
    return b"".join(json.dumps({"seq": i, **e}).encode() + b"\n" for i, e in enumerate(events))


def _blob(store: dict[str, bytes], value: object) -> dict:
    import hashlib

    data = json.dumps(value).encode()
    digest = hashlib.sha256(data).hexdigest()
    store[digest] = data
    return {"$blob": "sha256:" + digest, "bytes": len(data), "media": "application/json"}


def test_toml_writer_round_trips_a_plan():
    from agentprov.cli.run import toml_dumps

    doc = {"plan": {"format": "agentprov-run-plan/0.1", "suites": ["banking"], "user_tasks": "0-2", "benign": "include"},
           "agent": {"model_requested": "m \"q\"", "params": {"temperature": 0.0}, "transport": "scripted"},
           "attack_params": {"model_display_name": "GPT-4"}}
    assert tomllib.loads(toml_dumps(doc)) == doc


def test_toml_writer_round_trips_astral_control_and_quote_characters():
    from agentprov.cli.run import toml_dumps

    # An astral character (JSON writes a surrogate pair, which TOML rejects), controls, DEL, quote, backslash, a bidi
    # override, and keys that need the same escaping (escaping audit F-05).
    text = "m \U0001f600 \u202e \x00\x07\x1b\x7f \" \\ \n\t é \U0010ffff"
    doc = {"plan": {"format": "agentprov-run-plan/0.1", "suites": ["b\U0001f600"], "k\U0001f600\n": text},
           "agent": {"model_requested": text, "params": {"temperature": 0.0}},
           "t\U0001f600": {"x": text}}  # fmt: skip
    written = toml_dumps(doc)
    assert written.isascii() and "\\ud83d" not in written and "\\U0001f600" in written
    assert tomllib.loads(written) == doc


def test_toml_writer_refuses_a_lone_surrogate():
    from agentprov.cli.common import CliUsageError
    from agentprov.cli.run import toml_dumps

    with pytest.raises(CliUsageError):
        toml_dumps({"agent": {"model_requested": "cut mid-emoji \ud83d"}})


@pytest.mark.parametrize("provider, finishes, abnormal", [
    ("anthropic", ["end_turn", "tool_use", "stop_sequence"], 0),
    ("anthropic", ["max_tokens", "refusal", "pause_turn", "stop"], 4),
    ("openai_compatible", ["end_turn", "tool_use"], 2),
    (None, ["stop", "tool_calls"], 0),
])
def test_a6_normal_finishes_follow_the_provider(provider, finishes, abnormal):
    """D-656 (live pilot Part B finding 2): the Messages API's end_turn and tool_use are normal for provider anthropic."""
    agent = {"model_requested": "m1", **({"provider": provider} if provider else {})}
    events = [{"type": "identity", "data": {"agent": agent}}, {"type": "pass.start", "data": {}}]
    for n, finish in enumerate(finishes):
        events += [{"type": "llm.request", "data": {"call": f"c{n}", "attempt": 0, "params": {}}},
                   {"type": "llm.response", "data": {"call": f"c{n}", "status": "kept", "http_status": 200,
                                                     "finish_reason": finish, "served_model": "m1"}}]
    events.append({"type": "session.end", "data": {"status": "complete", "appended_by": "worker"}})
    q = session_quality("s", _log(*events), {}.get)
    assert q.kept == len(finishes) and q.abnormal_finish == abnormal


def test_session_quality_and_the_canary():
    store: dict[str, bytes] = {}
    request = _blob(store, {"tools": [{"function": {"name": "send_money"}}]})
    text_call = _blob(store, {"choices": [{"message": {"content": "<function=send_money>{}</function>"}}]})
    fine = _blob(store, {"choices": [{"message": {"content": "done", "tool_calls": None}}]})
    log = _log(
        {"type": "identity", "data": {"agent": {"model_requested": "m1"}}},
        {"type": "note", "data": {"ns": "agentdojo", "kind": "cell", "payload": {"cell_key": "s/u/none/none"}}},
        {"type": "pass.start", "data": {}},
        {"type": "llm.request", "data": {"call": "c0", "attempt": 0, "request": request,
                                         "params": {"configured": {"temperature": 0.0}, "transmitted": {}}}},
        {"type": "llm.response", "data": {"call": "c0", "status": "kept", "http_status": 200, "finish_reason": "length",
                                          "response": text_call, "served_model": "m1"}},
        {"type": "llm.request", "data": {"call": "c1", "attempt": 1, "request": request, "params": {}}},
        {"type": "llm.response", "data": {"call": "c1", "status": "kept", "http_status": 200, "finish_reason": "stop",
                                          "response": fine, "served_model": "m1"}},
        {"type": "session.end", "data": {"status": "errored", "appended_by": "worker"}},
    )
    q = session_quality("s1", log, store.get)
    assert q.cell_key == "s/u/none/none" and q.model == "m1" and q.passes == 1 and q.kept == 2 and q.retries == 1
    assert q.not_transmitted == {"temperature"} and q.abnormal_finish == 1 and q.text_tool_call_suspect == 1
    found = canary_conditions([q])
    assert [c.split()[0] for c in found] == ["A3", "A4", "A6", "1"]
    report = quality_report([q], {"s/u/none/none#0": 2})
    assert report["models"]["m1"]["statuses"] == {"errored": 1} and report["attempts_per_cell"] == {"2": 1}
    assert canary_conditions([]) == []


def _served_log(store: dict[str, bytes], served: list[str | None], *, matches_plan: bool | None = None) -> bytes:
    request = _blob(store, {"model": "qwen3-8b", "messages": []})
    reply = _blob(store, {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]})
    events: list[dict] = [{"type": "identity", "data": {"agent": {"model_requested": "qwen3-8b"}}}]
    if matches_plan is not None:
        events.append({"type": "note", "data": {"ns": "agentdojo", "kind": "local_model",
                                                "payload": {"matches_plan": matches_plan}}})
    for i, name in enumerate(served):
        events.append({"type": "llm.request", "data": {"call": f"c{i}", "attempt": 0, "request": request}})
        data = {"call": f"c{i}", "status": "kept", "http_status": 200, "finish_reason": "stop", "response": reply}
        if name is not None:
            data["served_model"] = name
        events.append({"type": "llm.response", "data": data})
    events.append({"type": "session.end", "data": {"status": "complete", "appended_by": "worker"}})
    return _log(*events)


def test_a12_served_model_must_equal_the_requested_one_unless_accepted():
    store: dict[str, bytes] = {}
    same = session_quality("a", _served_log(store, ["qwen3-8b", "qwen3-8b"]), store.get)
    other = session_quality("b", _served_log(store, ["qwen3-8b", "qwen3-8b-2025"]), store.get)
    absent = session_quality("c", _served_log(store, [None]), store.get)
    assert canary_conditions([same]) == []
    (cond,) = canary_conditions([other])
    assert cond.startswith("A12") and "qwen3-8b -> qwen3-8b-2025" in cond
    assert canary_conditions([other], accepted_served=["qwen3-8b-2025"]) == []
    assert [c.split()[0] for c in canary_conditions([absent], accepted_served=["qwen3-8b-2025"])] == ["A12"]
    report = quality_report([same, other, absent], {})["models"]["qwen3-8b"]
    assert report["served_models"] == {"none": 1, "qwen3-8b": 3, "qwen3-8b-2025": 1}
    assert report["served_model_mismatch"] == 2


def test_a14_local_model_drift():
    store: dict[str, bytes] = {}
    fine = session_quality("a", _served_log(store, ["qwen3-8b"], matches_plan=True), store.get)
    moved = session_quality("b", _served_log(store, ["qwen3-8b"], matches_plan=False), store.get)
    assert (fine.local_model_drift, moved.local_model_drift) == (0, 1)
    assert [c.split()[0] for c in canary_conditions([fine, moved])] == ["A14"]
    assert quality_report([fine, moved], {})["models"]["qwen3-8b"]["local_model_drift"] == 1


def test_a_hostile_log_line_is_counted_not_parsed_loosely():
    q = session_quality("s", b'{"seq": 0, "type": "x", "type": "y"}\nnot json\n', lambda _h: None)
    assert q.unparsed_lines == 2 and q.status is None
    assert canary_conditions([q])  # an unsealed session is a canary condition


def test_the_worker_environment_is_an_allowlist(tmp_path):
    from agentprov.cli.live.worker import worker_environment

    env = worker_environment(home=tmp_path, key_variables={"OPENAI_API_KEY": "k" * 20}, block_network=False,
                             parent_environ={"HOME": "/real", "UV_INDEX_URL": "x", "PATH": "/opt/bin", "SECRET_TOKEN": "t"})
    assert env == {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "LANG": "C.UTF-8", "TZ": "UTC", "OPENAI_API_KEY": "k" * 20}
    assert worker_environment(home=tmp_path, block_network=True, parent_environ={})["AGENTPROV_BLOCK_NETWORK"] == "1"
    # D-664: the egress proxy URL reaches the recording transports and environment-reading clients, nothing else
    proxied = worker_environment(home=tmp_path, block_network=False, parent_environ={}, egress_proxy="http://127.0.0.1:4")
    assert {k: v for k, v in proxied.items() if "PROXY" in k.upper()} == {
        "AGENTPROV_EGRESS_PROXY": "http://127.0.0.1:4", "HTTPS_PROXY": "http://127.0.0.1:4", "https_proxy": "http://127.0.0.1:4"}


@pytest.mark.skipif(os.name == "nt", reason="the child gets a POSIX PATH only")
@pytest.mark.parametrize("line", [b'{"v":"agentprov-backend/0.1","op":"x","op":"y"}\n', b"\xff\n", b"[1]\n",
                                  b'{"v":"agentprov-backend/0.2","op":"hello_ok"}\n', b'{"v":"agentprov-backend/0.1","op":"hello_ok","n":NaN}\n'])
def test_the_protocol_reader_refuses_non_strict_lines(tmp_path, line):
    from agentprov.cli.live.worker import BackendWorker, WorkerDied, WorkerSpec

    script = tmp_path / "w.py"
    script.write_text(f"import sys\nsys.stdout.buffer.write({line!r})\nsys.stdout.flush()\nsys.stdin.read()\n")
    worker = BackendWorker(WorkerSpec([sys.executable, "-I", "-B", str(script)], {"PATH": "/usr/bin:/bin"}, tmp_path,
                                      tmp_path / "err.log"))
    worker.start()
    try:
        with pytest.raises(WorkerDied):
            worker.receive(30)
        assert worker.violation is not None
    finally:
        worker.close()


@pytest.mark.skipif(os.name == "nt", reason="the child gets a POSIX PATH only")
def test_an_oversized_protocol_line_is_a_violation(tmp_path):
    from agentprov.cli.live.worker import BackendWorker, WorkerDied, WorkerSpec

    script = tmp_path / "w.py"
    script.write_text("import sys\nsys.stdout.buffer.write(b'{' + b' ' * (1024 * 1024 + 10) + b'}\\n')\nsys.stdout.flush()\n")
    worker = BackendWorker(WorkerSpec([sys.executable, "-I", "-B", str(script)], {"PATH": "/usr/bin:/bin"}, tmp_path,
                                      tmp_path / "err.log"))
    worker.start()
    try:
        with pytest.raises(WorkerDied):
            worker.receive(30)
        assert "1 MiB" in str(worker.violation)
    finally:
        worker.close()


def _args(**kw) -> argparse.Namespace:
    base = dict(containment=None, i_consent_to_api_costs=False, i_consent_to_local_run=False, model="deepseek", endpoint=None, model_id=None,
                allow_custom_endpoint=False, temperature=None, reasoning_effort=None, llm_element=None,
                allow_text_tool_calls=False, temperature_policy=None)
    base.update(kw)
    return argparse.Namespace(**base)


def test_containment_gates():
    from agentprov.cli.live.sandbox import PROFILE_SHA256
    from agentprov.cli.run import LiveRefused, _containment

    with pytest.raises(LiveRefused):
        _containment(_args(), {})
    with pytest.raises(LiveRefused):
        _containment(_args(containment="sandbox-exec"), {"sandbox_probe": {"status": "failed", "profile_sha256": PROFILE_SHA256}})
    with pytest.raises(LiveRefused):
        _containment(_args(containment="sandbox-exec"), {"sandbox_probe": {"status": "passed", "profile_sha256": "sha256:0"}})
    assert _containment(_args(containment="sandbox-exec"), {"sandbox_probe": {"status": "passed", "profile_sha256": PROFILE_SHA256}}) == {
        "kind": "sandbox_exec", "declared_by": "probe", "profile_sha256": PROFILE_SHA256}
    assert _containment(_args(containment="dedicated-user"), {}) == {"kind": "dedicated_user", "declared_by": "operator"}


def test_consent_is_required_without_a_terminal(monkeypatch):
    from agentprov.cli.common import CommandResult, Context
    from agentprov.cli.run import LiveRefused, ResumeState, _consent

    monkeypatch.setattr(sys, "stdin", io.StringIO("y\n"))  # not a TTY: the prompt is not offered
    ctx = Context(args=_args(), stderr=io.StringIO())
    resume = ResumeState(units=4, settled=1, attempts_due=6, max_attempts=2)
    with pytest.raises(LiveRefused):
        _consent(_args(), agent={"base_url": "https://api.deepseek.com/v1"}, ctx=ctx, result=CommandResult(), resume=resume)
    result = CommandResult()
    _consent(_args(i_consent_to_api_costs=True), agent={}, ctx=ctx, result=result, resume=resume)
    assert "consent: --i-consent-to-api-costs" in result.notices and "may be billed" in ctx.stderr.getvalue()
    # CC-28: the bound counts the settled units and --max-attempts, as the campaign does
    assert ("up to 6 cell attempt(s): 3 of 4 unit(s) to run, at most 2 attempt(s) each across invocations; "
            "1 already complete") in ctx.stderr.getvalue()


def test_real_agent_resolution_never_records_the_key(monkeypatch):
    from agentprov.cli.common import CommandResult
    from agentprov.cli.run import LiveEnvironmentError, LiveRefused, _real_agent

    key = "sk-test-not-a-real-key-0123456789"
    with pytest.raises(LiveEnvironmentError):
        _real_agent(_args(), {"DEEPSEEK_API_KEY": key}, CommandResult())  # no model id
    with pytest.raises(LiveEnvironmentError):
        _real_agent(_args(model_id="m"), {}, CommandResult())  # no key
    with pytest.raises(LiveRefused):
        _real_agent(_args(model_id="m"), {"DEEPSEEK_API_KEY": key, "DEEPSEEK_BASE_URL": "https://evil.example/v1"}, CommandResult())
    with pytest.raises(LiveRefused):
        _real_agent(_args(model_id="m"), {"DEEPSEEK_API_KEY": key, "DEEPSEEK_BASE_URL": "https://api.deepseek.com/v1?k=1"},
                    CommandResult())
    agent, keys = _real_agent(_args(), {"DEEPSEEK_API_KEY": key, "DEEPSEEK_MODEL": "deepseek-chat"}, CommandResult())
    assert keys == {"DEEPSEEK_API_KEY": key} and agent["api_key_env"] == "DEEPSEEK_API_KEY"
    assert key not in json.dumps(agent) and agent["model_requested"] == "deepseek-chat" and agent["transport"] == "http"


def test_anthropic_agent_resolution_and_max_tokens_modes():
    """D-656: the registry's api decides the provider; --max-tokens is stated or the harness default, never absent."""
    from agentprov.cli.common import CommandResult
    from agentprov.cli.run import _real_agent

    key = "sk-ant-test-not-a-real-key-0123456789"
    values = {"ANTHROPIC_API_KEY": key, "REASONING_EFFORT": "high"}
    result = CommandResult()
    agent, keys = _real_agent(_args(model="anthropic", model_id="claude-haiku-5-5", max_tokens=4096), values, result)
    assert agent["provider"] == "anthropic" and agent["endpoint"] == "anthropic"
    assert agent["base_url"] == "https://api.anthropic.com" and keys == {"ANTHROPIC_API_KEY": key}
    assert agent["params"] == {"max_tokens": 4096, "max_tokens_mode": "explicit"}   # REASONING_EFFORT is not used
    assert any("REASONING_EFFORT" in n for n in result.notices) and key not in json.dumps(agent)
    agent, _ = _real_agent(_args(model="anthropic", model_id="claude-haiku-5-5", max_tokens="harness-default",
                                 temperature=0.2), values, CommandResult())
    assert agent["params"] == {"temperature": 0.2, "max_tokens": 16000, "max_tokens_mode": "harness_default"}
    agent, _ = _real_agent(_args(), {"DEEPSEEK_API_KEY": "sk-test-not-a-real-key-0123456789",
                                     "DEEPSEEK_MODEL": "deepseek-chat"}, CommandResult())
    assert agent["provider"] == "openai_compatible"


@pytest.mark.parametrize("kw, message", [
    ({"model": "anthropic"}, "needs --max-tokens"),
    ({"model": "anthropic", "max_tokens": 10, "reasoning_effort": "high"}, "--reasoning-effort"),
    ({"model": "anthropic", "max_tokens": 10, "llm_element": "gateway_compat"}, "gateway_compat"),
    ({"model": "deepseek", "max_tokens": 10}, "Anthropic endpoints only"),
    ({"model": None, "endpoint": "anthropic", "model_id": "m"}, "needs --max-tokens"),
])
def test_provider_options_are_checked(kw, message):
    from agentprov.cli.common import CliUsageError
    from agentprov.cli.run import _check_provider_options

    with pytest.raises(CliUsageError, match=message):
        _check_provider_options(_args(**{"llm_script": None, "max_tokens": None, **kw}))
    _check_provider_options(_args(llm_script=None, max_tokens=None, model="openrouter"))
    _check_provider_options(_args(llm_script=None, max_tokens="harness-default", model="anthropic"))


def test_an_anthropic_script_selects_the_provider(tmp_path: Path):
    from agentprov.cli.run import _scripted_agent, selected_provider

    script = tmp_path / "s.json"
    script.write_text(json.dumps({"api": "anthropic_messages", "steps": [{"reply": "text", "content": "x"}]}))
    args = _args(model=None, llm_script=str(script), max_tokens=512, model_id=None)
    assert selected_provider(args) == "anthropic"
    agent = _scripted_agent(args)
    assert agent["provider"] == "anthropic" and agent["params"] == {"max_tokens": 512, "max_tokens_mode": "explicit"}
    script.write_text(json.dumps([{"reply": "text", "content": "x"}]))
    assert selected_provider(_args(model=None, llm_script=str(script))) == "openai_compatible"


def test_max_tokens_argument_type():
    from agentprov.cli.run import _max_tokens

    assert _max_tokens("2048") == 2048 and _max_tokens("harness-default") == "harness-default"
    for bad in ("0", "-3", "lots"):
        with pytest.raises((argparse.ArgumentTypeError, ValueError)):
            _max_tokens(bad)


def test_staging_collection_without_a_report_takes_every_raw_file(tmp_path: Path):
    from agentprov.cli.live.staging import collect_session

    (tmp_path / "raw" / "capture").mkdir(parents=True)
    (tmp_path / "raw" / "capture" / "s.capture.jsonl").write_bytes(b"{}\n")
    (tmp_path / "raw" / "other.bin").write_bytes(b"x")
    (tmp_path / "llm-script.json").write_bytes(b"[]")
    files = collect_session(tmp_path, "s", None, parent_files={"llm-script.json"})
    assert not files.reported and sorted(f.label for f in files.files) == ["raw/capture/s.capture.jsonl", "raw/other.bin"]
    assert files.capture_log is not None and files.unreported == []


def test_a_failed_redaction_scan_is_recognised_only_from_a_parsed_error_event():
    """D-290: ``redaction_failed`` reads the constant ``error`` event a poisoned capture log is sealed with (C.13.10
    item 6); the same words anywhere else, or on a line that does not parse, do not count."""
    from agentprov.cli.live.staging import redaction_failed

    poisoned = {"type": "error", "data": {"where": "capture.redact", "fatal": True,
                                          "exception": {"type": "RedactionError", "message": "redaction failed"}}}
    end = {"type": "session.end", "data": {"status": "errored"}}
    assert redaction_failed(_log({"type": "session.start", "data": {}}, poisoned, end))
    assert not redaction_failed(_log({"type": "session.start", "data": {}}, end))
    assert not redaction_failed(_log({"type": "note", "data": {"ns": "x", "kind": "y", "payload": {"where": "capture.redact"}}}))
    assert not redaction_failed(_log({"type": "error", "data": {"where": "cell", "exception": {"message": "capture.redact"}}}))
    assert not redaction_failed(b'{"type": "error", "data": {"where": "capture.redact", "where": "x"}}\n')  # duplicate key
    assert not redaction_failed(b'{"type": "error", "data": {"where": "capture.redact"}\n')  # does not parse


# ------------------------------------------------------------------------------------------------ campaign stop (N.1.10)
class _FakeCellWorker:
    """Stands in for a backend worker: a cell runs for ``durations[cell_key]`` seconds unless the worker is killed."""

    alive = True

    def __init__(self, log: list[str], durations: dict[str, float]) -> None:
        self.log, self.durations, self.killed = log, durations, False

    def request(self, op, replies, timeout, **fields):
        import time

        from agentprov.cli.live.worker import WorkerDied

        key = fields["cell"]["cell_key"]
        self.log.append(f"start {key}")
        end = time.monotonic() + self.durations.get(key, 0.0)
        while time.monotonic() < end:
            if self.killed:
                raise WorkerDied("killed")
            time.sleep(0.01)
        self.log.append(f"end {key}")
        return {"op": "cell_done", "req": fields["req"], "status": "complete", "artefacts": []}

    def kill(self) -> None:
        self.killed = True

    def close(self) -> None:
        pass

    def shutdown(self) -> None:
        pass


def _campaign(monkeypatch, tmp_path: Path, *, jobs: int, stagger: float, durations: dict[str, float], ingest=None):
    from agentprov.cli.live import campaign as cm

    log: list[str] = []

    def ensure(slot):
        if slot.worker is None:
            log.append(f"spawn {slot.index}")
            slot.worker = _FakeCellWorker(log, durations)
        return slot.worker

    def default_ingest(self, result):
        return {"session": result.session, "cell_key": result.task.cell_key, "config_digest": "d", "repeat": 0,
                "status": result.status}

    monkeypatch.setattr(cm.Slot, "ensure", ensure)
    monkeypatch.setattr(cm.Campaign, "_ingest", ingest or default_ingest)
    pipeline = argparse.Namespace(limits=None, counters={"derived": 0, "failed": 0})
    campaign = cm.Campaign(pipeline=pipeline, writer=None, argv=["x"], env_for=lambda h: {}, identity=None, marker={},
                           expect={}, home=tmp_path, agent={}, plan={"plan_sha256": "p"}, config_digest="d", jobs=jobs,
                           start_stagger=stagger, cell_timeout=60, max_attempts=1, retry_inconsistent=False, repeats=1,
                           canary=0, limit=None, script=None, redactor=None, snapshot_id="s", ledger=cm.Ledger())
    return campaign, log


def test_an_interrupt_stops_slots_still_in_their_start_stagger(monkeypatch, tmp_path: Path):
    """CC-5: after the first SIGINT no new unit starts (N.1.10(2)): a slot still waiting out its start stagger neither
    spawns a worker nor creates a session directory, and the command does not wait for the stagger to pass."""
    import time

    from agentprov.cli.live import campaign as cm

    campaign, log = _campaign(monkeypatch, tmp_path, jobs=3, stagger=6.0, durations={f"c{i}": 5.0 for i in range(3)})

    def interrupted(futures, return_when):
        time.sleep(0.2)
        raise KeyboardInterrupt

    monkeypatch.setattr(cm, "wait", interrupted)
    started = time.monotonic()
    with pytest.raises(KeyboardInterrupt):
        campaign.run([{"cell_key": f"c{i}"} for i in range(3)], write_documents=lambda: None)
    assert time.monotonic() - started < 1.5
    assert [e for e in log if e.startswith("spawn")] == ["spawn 0"]  # slots 1 and 2 (waiting 2 s, 4 s) never spawn
    assert len([e for e in log if e.startswith("start")]) == 1 and not any(e.startswith("end") for e in log)
    assert len(list((tmp_path / "staging").iterdir())) == 1  # only the interrupted session's directory


def test_a_campaign_aborting_error_kills_the_other_in_flight_workers(monkeypatch, tmp_path: Path):
    """CC-6: when the campaign aborts (here an identity mismatch found while ingesting one session), the other
    in-flight cells are stopped at once, not run to completion (N.1.10(4))."""
    import time

    from agentprov.errors import IdentityMismatch

    def ingest(self, result):
        raise IdentityMismatch("IdentityMismatch: test")

    campaign, log = _campaign(monkeypatch, tmp_path, jobs=3, stagger=0, durations={"c0": 0.1, "c1": 5.0, "c2": 5.0},
                              ingest=ingest)
    started = time.monotonic()
    with pytest.raises(IdentityMismatch):
        campaign.run([{"cell_key": f"c{i}"} for i in range(3)], write_documents=lambda: None)
    assert time.monotonic() - started < 2.5
    assert "end c1" not in log and "end c2" not in log

# ------------------------------------------------------------------------------------------------ core review C fixes
def test_a_dry_run_never_lets_the_attack_cache_check_fetch(monkeypatch):
    """CC-24: ``run --dry-run --allow-network`` fetched the AutoDojo pin; a dry run never uses the network (N.1.6)."""
    from agentprov.cli import run as run_mod
    from agentprov.cli.common import CommandResult, Context

    seen: list[bool] = []

    def verify(path: str, **kw: object) -> None:
        seen.append(bool(kw["allow_network"]))
        raise RuntimeError("stop")

    monkeypatch.setattr(run_mod, "_verify_attack_cache", verify)
    live = {"attack_cache": {"attack": "x"}, "pins": {"repo": "https://example.invalid/r", "commit": "0" * 40}}
    for dry_run, expected in ((True, False), (False, True)):
        args = argparse.Namespace(autodojo_cache="c.json", autodojo_variant="0", allow_network=True, dry_run=dry_run)
        with pytest.raises(RuntimeError):
            run_mod._attack_cache(args, live, Context(args=args, env={}), CommandResult())
        assert seen[-1] is expected


def test_worker_supplied_preflight_values_are_escaped(monkeypatch):
    """CC-30: the probe's reachable, roles_accepted, http_status and not_transmitted reached stderr raw."""
    from agentprov.cli.common import CommandResult
    from agentprov.cli.run import _evaluate_probe

    hostile = "\x1b]0;owned\x07\nfake: line"
    result = CommandResult()
    with pytest.raises(Exception):  # noqa: B017,PT011 - the verdict does not matter here, only what was printed
        _evaluate_probe({"reachable": hostile, "roles_accepted": hostile, "http_status": hostile,
                         "params": {"not_transmitted": [hostile]}}, _args(allow_text_tool_calls=False), result)
    shown = "".join(text for _, text in result.messages)
    assert "\x1b" not in shown and "\x07" not in shown and "\n" not in shown


def test_a_plan_digest_that_is_not_64_hex_is_a_protocol_error(monkeypatch, tmp_path):
    """CC-30: plan_sha256 is printed by the dry run, so it is checked before anything uses it."""
    from agentprov.cli import run as run_mod
    from agentprov.cli.live import worker as worker_mod

    class Fake:
        def __init__(self, spec: object) -> None: ...
        def start(self) -> None: ...
        def shutdown(self) -> None: ...

        def request(self, *a: object, **k: object) -> dict:
            return {"op": "plan_ok", "plan": {"cells": [], "plan_sha256": "\x1b[2J" + "0" * 60}}

    monkeypatch.setattr(worker_mod, "BackendWorker", Fake)
    monkeypatch.setattr(run_mod, "_hello", lambda *a, **k: {"identity": {}})
    with pytest.raises(run_mod.LiveEnvironmentError, match="malformed plan"):
        run_mod._hello_and_plan(["x"], {}, None, None, {}, "", tmp_path)


_SECOND_SIGNAL = r"""
import signal, sys, time
from pathlib import Path
from agentprov.cli.common import install_signal_handlers
from agentprov.cli.live.worker import BackendWorker, WorkerSpec

home = Path(sys.argv[1])
spec = WorkerSpec(argv=[sys.executable, "-c", "import time; time.sleep(120)"], env={"PATH": "/usr/bin:/bin"},
                  cwd=home, stderr_path=home / "w.log")
with install_signal_handlers():
    worker = BackendWorker(spec)
    worker.start()
    print(worker.pid, flush=True)
    try:
        signal.raise_signal(signal.SIGINT)
        time.sleep(5)
    except KeyboardInterrupt:
        signal.raise_signal(signal.SIGINT)  # the second signal: os._exit(130), after killing the worker tree
        time.sleep(5)
sys.exit(0)
"""


@pytest.mark.skipif(os.name != "posix", reason="POSIX process groups")
def test_the_second_signal_kills_the_backend_workers_before_it_exits(tmp_path):
    """CC-27: the second signal os._exit-ed and left the T2 worker (its own session) running its cell."""
    import subprocess

    proc = subprocess.run([sys.executable, "-c", _SECOND_SIGNAL, str(tmp_path)], capture_output=True, text=True,
                          timeout=60)
    assert proc.returncode == 130, proc.stderr
    pid = int(proc.stdout.split()[0])
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.1)
    os.kill(pid, 9)
    raise AssertionError("the backend worker outlived the second signal")
