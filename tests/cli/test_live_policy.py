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
    (True, "http://192.168.1.20:1234/v1", "api"),  # LAN: not local until the egress proxy forwards it (D-721)
    (True, None, "api"),
    (False, "http://127.0.0.1:1234/v1", "api"),  # not a local entry, whatever its URL
    (False, "https://openrouter.ai/api/v1", "api"),
])
def test_endpoint_class(local: bool, url: str | None, kind: str) -> None:
    assert endpoint_class(local_entry=local, base_url=url) == kind


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
