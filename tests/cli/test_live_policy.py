"""Endpoint classes and the API caps' arithmetic (D-721, D-725; ``agentprov.cli.live.policy``). Pure: no worker, no
network; the capture logs are synthetic JSONL lines."""

from __future__ import annotations

import json

import pytest

from agentprov.cli.live.policy import (
    CALL_INPUT_BOUND,
    CALL_OUTPUT_BOUND,
    CELL_CALL_BOUND,
    Budget,
    Caps,
    endpoint_class,
    log_billing,
)


def _log(*events: tuple[str, dict]) -> bytes:
    return b"".join(json.dumps({"type": kind, "data": data}).encode() + b"\n" for kind, data in events)


def _reply(http: int = 200, usage: dict | None = None) -> tuple[str, dict]:
    data: dict = {"call": "c", "status": "kept", "http_status": http}
    if usage is not None:
        data["usage"] = usage
    return ("llm.response", data)


END = ("session.end", {"status": "complete"})


@pytest.mark.parametrize(("local", "url", "kind"), [
    (True, "http://127.0.0.1:1234/v1", "local"),
    (True, "http://localhost:11434/v1", "local"),
    (True, "http://[::1]:8000/v1", "local"),
    (True, "https://models.example.org/v1", "api"),  # a local entry pointed off loopback is an API endpoint
    (True, "http://192.168.1.20:1234/v1", "api"),  # LAN: its data leaves the machine (D-1067, amending D-721)
    (True, "http://[fd00::5]:1234/v1", "api"),
    (True, None, "api"),
    (False, "http://127.0.0.1:1234/v1", "api"),  # not a local entry, whatever its URL
    (False, "https://openrouter.ai/api/v1", "api"),
])
def test_endpoint_class(local: bool, url: str | None, kind: str) -> None:
    assert endpoint_class(local_entry=local, base_url=url) == kind


def test_the_api_reason_names_a_lan_model_server() -> None:
    """AU-RN-8 / D-1067: a keyless LAN server is api because its data leaves the machine, and the reason says so."""
    from agentprov.cli.live.policy import api_reason, is_lan_base_url

    assert is_lan_base_url("http://192.168.1.20:11434/v1") and is_lan_base_url("http://10.0.0.7:8000/v1")
    assert not is_lan_base_url("http://127.0.0.1:11434/v1") and not is_lan_base_url("https://lan.example/v1")
    assert not is_lan_base_url(None) and not is_lan_base_url("http://[::1:8000/v1")
    lan = api_reason(local_entry=True, base_url="http://192.168.1.20:11434/v1")
    assert "LAN model server is an API endpoint" in lan and "leave this machine" in lan and "D-1067" in lan
    assert api_reason(local_entry=True, base_url="https://models.example.org/v1") == \
        "the resolved base URL is not a local server on loopback"
    assert api_reason(local_entry=False, base_url="http://192.168.1.20:11434/v1") == "the endpoint entry is not local"


def test_billing_counts_2xx_replies_and_sums_every_input_side_token() -> None:
    log = _log(_reply(usage={"input_tokens": 100, "cache_read_tokens": 20, "cache_write_tokens": 5, "output_tokens": 7}),
               _reply(usage={"input_tokens": 50, "output_tokens": 3}),
               _reply(http=429), _reply(http=500), ("llm.response", {"status": "error"}),  # not billed
               _reply(usage={}),  # billed, no usage
               END)
    b = log_billing(log)
    assert (b.billed_calls, b.input_tokens, b.output_tokens, b.without_usage) == (3, 175, 10, 1)
    assert (b.max_call_input, b.max_call_output, b.parent_ended, b.missing) == (125, 7, False, False)


def test_billing_marks_a_parent_ended_or_missing_log() -> None:
    assert log_billing(_log(_reply(), ("session.end", {"status": "aborted", "appended_by": "parent"}))).parent_ended
    assert log_billing(_log(_reply())).parent_ended  # no session.end at all
    assert log_billing(None).missing


def test_billing_skips_lines_it_cannot_parse() -> None:
    b = log_billing(b"not json\n" + _log(_reply(usage={"input_tokens": 1, "output_tokens": 1}), END) + b"{\n")
    assert b.billed_calls == 1


def _caps(**kw: object) -> Caps:
    base: dict = {"max_calls": 100, "max_cost_usd": 1.0, "price_in": 0.15, "price_out": 0.60}
    base.update(kw)
    return Caps(**base)


def test_missing_caps_for_an_api_run() -> None:
    assert Caps().missing_for_api() == ["--max-calls", "--max-cost-usd"]
    assert Caps(max_calls=5).missing_for_api() == ["--max-cost-usd"]
    assert Caps(max_calls=5, max_cost_usd=1.0).missing_for_api() == ["--price-in", "--price-out"]
    assert _caps().missing_for_api() == []


def test_the_cell_bound_uses_the_call_bounds_and_max_tokens() -> None:
    budget = Budget(_caps())
    calls, usd = budget.cell_bound()
    assert calls == CELL_CALL_BOUND == 48
    assert usd == pytest.approx(48 * (CALL_INPUT_BOUND * 0.15 + CALL_OUTPUT_BOUND * 0.60) / 1e6)
    stated = Budget(_caps(max_tokens=1024)).cell_bound()[1]
    assert stated == pytest.approx(48 * (CALL_INPUT_BOUND * 0.15 + 1024 * 0.60) / 1e6)


def test_a_cell_starts_only_while_its_worst_case_fits() -> None:
    budget = Budget(_caps(max_calls=100, max_cost_usd=None, price_in=None, price_out=None))
    assert budget.refusal(0) is None
    for _ in range(2):
        budget.charge(log_billing(_log(*([_reply()] * 25), END)))  # 50 billed calls in two cells
    assert budget.refusal(0) is None  # 50 + 48 <= 100
    assert "cap_reached: --max-calls 100" in (budget.refusal(1) or "")  # 50 + 2 * 48 > 100: one in flight
    budget.charge(log_billing(_log(_reply(), _reply(), _reply(), END)))
    assert budget.refusal(0) is not None  # 53 + 48 > 100


def test_the_cost_cap_counts_spend_plus_the_worst_case() -> None:
    budget = Budget(_caps(max_calls=None, max_cost_usd=0.5))
    assert budget.refusal(0) is None  # about $0.35 worst case for gpt-4o-mini prices
    budget.charge(log_billing(_log(_reply(usage={"input_tokens": 1_000_000, "output_tokens": 0}), END)))  # $0.15
    assert "cap_reached: --max-cost-usd 0.5" in (budget.refusal(0) or "")


def test_unknown_spend_is_charged_conservatively() -> None:
    budget = Budget(_caps())
    budget.charge(log_billing(_log(_reply(usage={}), END)))  # a billed reply without usage: one call at the bound
    assert budget.calls == 1 and budget.cost_usd == pytest.approx(budget.call_bound_usd())
    budget = Budget(_caps())
    budget.charge(log_billing(_log(_reply(usage={"input_tokens": 1, "output_tokens": 1}))))  # killed: +1 call
    assert budget.calls == 2
    budget = Budget(_caps())
    budget.charge(log_billing(None))  # no log: a whole cell
    assert (budget.calls, budget.cost_usd) == (CELL_CALL_BOUND, pytest.approx(budget.cell_bound()[1]))
    budget = Budget(_caps())
    budget.charge_probe()
    assert budget.calls == 1


def test_a_larger_call_raises_the_per_call_bound() -> None:
    budget = Budget(_caps())
    before = budget.call_bound_usd()
    budget.charge(log_billing(_log(_reply(usage={"input_tokens": 100_000, "output_tokens": 9_000}), END)))
    assert budget.call_bound_usd() == pytest.approx((100_000 * 0.15 + 9_000 * 0.60) / 1e6) and budget.call_bound_usd() > before


def test_a_cell_over_the_call_bound_stops_the_campaign() -> None:
    budget = Budget(_caps(max_calls=10_000, max_cost_usd=None, price_in=None, price_out=None))
    budget.charge(log_billing(_log(*([_reply()] * (CELL_CALL_BOUND + 1)), END)), label="banking/user_task_0/none/none")
    assert (budget.refusal(0) or "").startswith("cap_bound_exceeded: banking/user_task_0/none/none")


def test_the_record_holds_decimal_strings_and_an_upper_bound() -> None:
    budget = Budget(_caps(max_cost_usd=1.0, price_in=0.125, price_out=0.5))
    budget.charge(log_billing(_log(_reply(usage={"input_tokens": 1000, "output_tokens": 1000}), END)))
    record = budget.record()
    assert record == {"max_calls": 100, "cell_call_bound": 48, "max_cost_usd": "1", "price_in_usd_per_mtok": "0.125",
                      "price_out_usd_per_mtok": "0.5", "billed_calls": 1, "spend_upper_bound_usd": "0.001"}
    assert not any(isinstance(v, float) for v in record.values())
    assert Budget(Caps(max_calls=3)).record() == {"max_calls": 3, "cell_call_bound": 48, "billed_calls": 0}


def test_no_probe_call_is_sent_at_the_caps_and_probes_are_kept_across_resume() -> None:
    """Review UC-23: a probe is a paid call, so it is checked against the caps before it is sent; the probe count is recorded in live.caps, where a resumed campaign charges it again."""
    from agentprov.cli.common import CommandResult
    from agentprov.cli.run import LiveRefused, _prior_probe_calls, _probe

    prior = Budget(Caps(max_calls=CELL_CALL_BOUND + 1))
    prior.calls = CELL_CALL_BOUND
    assert prior.probe_refusal() is None
    prior.charge_probe()
    assert (prior.probe_refusal() or "").startswith("cap_reached: --max-calls")
    sent: list[int] = []
    with pytest.raises(LiveRefused, match="no probe call is sent"):
        _probe(lambda: sent.append(1) or {}, CommandResult(), Budget(prior.caps), prior)
    assert sent == []  # nothing was sent at the cap

    budget = Budget(Caps(max_calls=1000))
    unconfirmed = {"reachable": True, "roles_accepted": False, "roles": "unconfirmed"}
    _, calls = _probe(lambda: unconfirmed, CommandResult(), budget, Budget(budget.caps))
    assert calls == 3 and budget.record()["probe_calls"] == 3 and budget.calls == 3
    assert _prior_probe_calls({"caps": budget.record()}) == 3
    resumed = Budget(budget.caps)
    resumed.charge_probe(_prior_probe_calls({"caps": budget.record()}))
    assert (resumed.calls, resumed.probe_calls) == (3, 3)
    for bad in (None, {}, {"caps": {"probe_calls": -1}}, {"caps": {"probe_calls": True}}, {"caps": []}):
        assert _prior_probe_calls(bad) == 0
    assert "probe_calls" not in Budget(Caps(max_calls=3)).record()  # absent while no probe was charged


def test_the_prior_spend_of_a_working_corpus_includes_its_recorded_probes(tmp_path) -> None:
    import argparse
    import json as _json

    from agentprov.cli.run import _prior_budget
    from agentprov.corpus.layout import CorpusLayout, partial_dir

    partial = partial_dir(tmp_path / "corpus")
    (partial / "raw" / "objects").mkdir(parents=True)
    CorpusLayout(partial).manifest.write_text(_json.dumps({"live": {"caps": {"probe_calls": 2}}}), encoding="utf-8")
    budget = Budget(Caps(max_calls=2))
    prior = _prior_budget(argparse.Namespace(corpus=str(tmp_path / "corpus")), budget)
    assert (prior.calls, prior.probe_calls) == (2, 2) and budget.calls == 0  # a copy: the campaign charges its own
    assert prior.probe_refusal() is not None
    assert _prior_budget(argparse.Namespace(corpus=str(tmp_path / "none")), budget).calls == 0
    assert _prior_budget(argparse.Namespace(corpus=None), None) is None


def test_the_prior_spend_charges_cells_started_but_never_ledgered(tmp_path) -> None:
    """AU-LIVE-3: a resumed campaign's probe admission and budget charge every cell an earlier invocation started and
    never ledgered (``live.caps.unledgered_cells``) a whole cell at the bound."""
    import argparse
    import json as _json

    from agentprov.cli.run import _prior_budget, _prior_unledgered_cells
    from agentprov.corpus.layout import CorpusLayout, partial_dir

    partial = partial_dir(tmp_path / "corpus")
    (partial / "raw" / "objects").mkdir(parents=True)
    live = {"caps": {"probe_calls": 1, "unledgered_cells": 2}}
    CorpusLayout(partial).manifest.write_text(_json.dumps({"live": live}), encoding="utf-8")
    budget = Budget(_caps(max_calls=100, max_cost_usd=None, price_in=None, price_out=None))
    prior = _prior_budget(argparse.Namespace(corpus=str(tmp_path / "corpus")), budget)
    assert prior.calls == 1 + 2 * CELL_CALL_BOUND and prior.record()["unledgered_cells"] == 2
    assert (prior.refusal(0) or "").startswith("cap_reached")  # 97 + 48 > 100
    for bad in (None, {}, {"caps": {"unledgered_cells": -1}}, {"caps": {"unledgered_cells": True}}, {"caps": []}):
        assert _prior_unledgered_cells(bad) == 0
    assert _prior_unledgered_cells(live) == 2
    costed = Budget(_caps(max_calls=None, max_cost_usd=10.0))
    costed.charge_unledgered(1)
    assert costed.cost_usd == pytest.approx(costed.cell_bound()[1])


def test_a_probe_must_fit_the_cost_cap() -> None:
    budget = Budget(_caps(max_calls=1000, max_cost_usd=0.03))
    assert budget.probe_refusal() is None  # one call at the bound: 32,000 x 0.15 + 4,096 x 0.60 per Mtok
    budget.cost_usd = 0.03 - budget.call_bound_usd() / 2
    assert (budget.probe_refusal() or "").startswith("cap_reached: --max-cost-usd 0.03")


def test_the_cell_bound_counts_the_billed_replies_of_the_llm_element() -> None:
    """AU-LIVE-1: ``gateway_compat`` asks again (up to 8 attempts) on a malformed tool call or an upstream failure
    answered 200, and every one of those replies is billed; one gateway cell billed 128 calls against a bound of 48, so
    a cell was admitted under --max-calls 100 and overran it. The bound now counts each step at the element's billed
    replies: 3 x 16 x 8 for gateway_compat, 3 x 16 x 3 for the AutoDojo fork's native element."""
    from agentprov.cli.live.policy import (
        STEP_ATTEMPTS_AUTODOJO_NATIVE,
        STEP_ATTEMPTS_GATEWAY,
        defence_cell_calls,
        step_attempts,
    )
    from agentprov.cli.run import _defence_cell_calls

    assert step_attempts("gateway_compat", "agentdojo") == STEP_ATTEMPTS_GATEWAY == 8
    assert step_attempts("native", "autodojo") == STEP_ATTEMPTS_AUTODOJO_NATIVE == 3
    assert step_attempts("native", "agentdojo") == step_attempts(None, "agentdyn") == 1
    assert _defence_cell_calls(None, 8) == defence_cell_calls(None, 8) == 384
    assert _defence_cell_calls(None, 3) == 144 and _defence_cell_calls(None) == CELL_CALL_BOUND
    # a defence's own calls (tool_filter: one per pass, a stock client) are added, not multiplied
    assert defence_cell_calls({"extra_calls_per_step": 0.0, "extra_calls_per_pass": 1.0}, 8) == 384 + 3


def test_a_melon_cell_counts_its_masked_calls_at_the_llm_elements_billed_replies() -> None:
    """AU-FR-2: MELON's masked re-run goes through the agent's own LLM element (the port wraps the pipeline's element),
    so under ``gateway_compat`` each masked call may bill 8 replies too; its two embeddings a step use the defence
    endpoint's client and are counted once. The bound was 528 against a worst case of 864."""
    from pathlib import Path

    from agentprov.cli.live.defences import load_registry, registry_path
    from agentprov.cli.live.policy import defence_cell_calls, step_attempts
    from agentprov.cli.run import _defence_cell_calls

    reg = load_registry(registry_path(Path(__file__).resolve().parents[2]))
    gateway = step_attempts("gateway_compat", "agentdojo")
    for name in ("melon", "melon_sm", "melon_at"):
        cost = reg[name].raw.get("cost")
        assert defence_cell_calls(cost, gateway) == _defence_cell_calls(reg[name], gateway) == 384 + 384 + 96 == 864
        assert defence_cell_calls(cost, 3) == 144 + 144 + 96 and defence_cell_calls(cost) == 48 + 48 + 96 == 192
    assert defence_cell_calls(reg["tool_filter"].raw.get("cost"), gateway) == 384 + 3  # its own stock client
    gateway_cell = log_billing(_log(*([_reply()] * 128), END))  # 16 steps of 8 billed replies (7 malformed)
    budget = Budget(Caps(max_calls=100), cell_calls=384, step_calls=8)
    assert (budget.refusal(0) or "").startswith("cap_reached: --max-calls 100")  # not admitted any more
    budget = Budget(Caps(max_calls=10_000), cell_calls=384, step_calls=8)
    budget.charge(gateway_cell, label="c")
    assert budget.calls == 128 and budget.exceeded_bound == [] and budget.refusal(0) is None


def test_a_probe_is_charged_and_admitted_at_the_llm_elements_billed_replies() -> None:
    """AU-LIVE-1: the preflight probe runs through the same LLM element, so it may bill ``step_calls`` replies."""
    from agentprov.cli.common import CommandResult
    from agentprov.cli.run import _probe

    budget = Budget(Caps(max_calls=100), step_calls=8)
    budget.calls = 93
    assert (budget.probe_refusal() or "").startswith("cap_reached: --max-calls 100")  # 93 + 8 > 100
    budget.calls = 92
    assert budget.probe_refusal() is None
    campaign, prior = Budget(Caps(max_calls=1000), step_calls=8), Budget(Caps(max_calls=1000), step_calls=8)
    _, calls = _probe(lambda: {"reachable": True, "roles_accepted": True}, CommandResult(), campaign, prior)
    assert calls == 1 and campaign.calls == prior.calls == 8 and campaign.record()["probe_calls"] == 8


def test_the_step_attempts_match_what_the_backend_declares() -> None:
    """The constants mirror the backend's declared retry ceilings, read as source (the core imports no backend)."""
    import re
    from pathlib import Path

    from agentprov.cli.live.policy import STEP_ATTEMPTS_AUTODOJO_NATIVE, STEP_ATTEMPTS_GATEWAY

    src = Path(__file__).resolve().parents[2] / "backends/shared/src/agentprov_backend"
    runner = (src / "runner.py").read_text(encoding="utf-8")
    for item in ("agentdojo.retry_malformed_tool_json@1", "agentdojo.retry_upstream_failure@1"):
        found = re.search(re.escape(item) + r'", "harness_policy", params=\{"max": (\d+)\}', runner)
        assert found is not None and int(found.group(1)) == STEP_ATTEMPTS_GATEWAY
    attempts = re.search(r"\n    _MAX_ATTEMPTS = (\d+)\n", (src / "_llm.py").read_text(encoding="utf-8"))
    assert attempts is not None and int(attempts.group(1)) == STEP_ATTEMPTS_GATEWAY
    autodojo = (src / "autodojo.py").read_text(encoding="utf-8")
    found = re.search(r'"autodojo\.fork_malformed_json_retry@1", "harness_policy",\s*params=\{"max": (\d+)', autodojo)
    assert found is not None and int(found.group(1)) == STEP_ATTEMPTS_AUTODOJO_NATIVE
