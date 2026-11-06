"""D-1090: Run Live's caps follow the CLI's suggested caps (``quote.caps``) until the user types one.

The suggestion is agentprov estimate's (the GUI computes none): each field takes it after every new quote, a typed
value stays until "Use the quote's figure", a cap that follows the quote is left out of the estimate's own arguments,
the command card shows the exact caps Start passes, and without a suggestion the caption says why and the cap must
be typed, as before."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from test_g3_live import wait
from test_runlive_form import QUOTE, _dialog, _settle

CAPS = {"available": True, "reason": None, "max_calls": 2210, "max_cost_usd": "25.37", "price_in": "2.5",
        "price_out": "10", "margin_pct": "20", "margin_from": "default", "calls_basis": "calls_p90",
        "cost_basis": "usd_p90", "reserved_cells": 1, "cell_calls": 48, "cell_usd": "5.81", "probe_calls": 1,
        "probe_usd": "0.13", "resumed_units": 0}


def _quote(**caps: Any) -> dict[str, Any]:
    return {**QUOTE, "caps": {**CAPS, **caps}}


def _again(qapp: Any, dlg: Any) -> None:
    """A new estimate of the current selection (what the debounce timer starts after a change)."""
    dlg.refresh_estimate()
    wait(qapp, lambda: dlg.current_estimate() is not None)


def _option(argv: tuple[str, ...], flag: str) -> str | None:
    return argv[argv.index(flag) + 1] if flag in argv else None


def test_the_caps_follow_the_quote_and_the_card_shows_them(qapp: Any, tmp_path: Path,
                                                            monkeypatch: pytest.MonkeyPatch) -> None:
    quote = _quote()
    dlg = _dialog(tmp_path, monkeypatch, scripted=False, quote=quote)
    _settle(qapp, dlg)
    assert dlg.max_cost.value() == pytest.approx(25.37) and dlg.max_calls.value() == 2210
    cost, calls = dlg.cap_rows["cost"], dlg.cap_rows["calls"]
    assert cost.caption.text() == ("Quote: upper cost (p90) + 20 % + room for 1 cell · shipped priors, all-model "
                                   "figures · OpenRouter prices of 2026-10-21")
    assert calls.caption.text() == "Quote: p90 calls + 20 % + room for 1 cell · shipped priors, all-model figures"
    tip = dlg.max_cost.toolTip()
    assert "Suggested $25.37" in tip and "sum of per-cell 90th percentiles" in tip and "+ 20 %" in tip
    assert "48 billed calls, $5.81 each" in tip and "D-725" in tip and "OpenRouter prices of 2026-10-21" in tip
    assert "Suggested 2,210 calls" in dlg.max_calls.toolTip() and "p90 calls" in dlg.max_calls.toolTip()
    assert cost.label.toolTip() == tip  # the label says the same as its field
    assert not dlg.cap_resets["cost"].isVisible() and not dlg.cap_resets["calls"].isVisible()
    # a cap that follows the quote is the quote's own output: the estimate is asked without it
    quote_argv = dlg._estimate_argv()
    assert not {"--max-calls", "--max-cost-usd", "--price-in", "--price-out"} & set(quote_argv)
    run_argv = dlg.run_spec().argv
    assert (_option(run_argv, "--max-calls"), _option(run_argv, "--max-cost-usd")) == ("2210", "25.37")
    (_c1, shown_quote), (_c2, shown_run) = dlg.command_card.commands
    assert shown_quote == quote_argv and shown_run == run_argv  # the card shows the exact caps Start passes
    assert dlg.current_estimate() is not None and dlg._gate() is None  # filled: Start may go ahead
    # a changed selection is quoted again, and the caps follow the new quote
    quote["caps"] = {**CAPS, "max_calls": 4400, "max_cost_usd": "48.10", "reserved_cells": 2}
    dlg.jobs.setValue(2)
    _again(qapp, dlg)
    assert dlg.max_calls.value() == 4400 and dlg.max_cost.value() == pytest.approx(48.10)
    assert "room for 2 cells" in calls.caption.text()
    dlg.close()


def test_a_typed_cap_stays_until_reset(qapp: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    quote = _quote()
    dlg = _dialog(tmp_path, monkeypatch, scripted=False, quote=quote)
    _settle(qapp, dlg)
    dlg.max_calls.setValue(5000)  # typed: a typed cap is an estimate argument (it warns), so the quote is asked again
    qapp.processEvents()
    calls = dlg.cap_rows["calls"]
    # a typed cap never changes the suggestion, so the last quote's still shows while the estimate is asked again
    assert dlg.current_estimate() is None and calls.caption.text() == "Your value; the quote suggests 2,210 calls"
    _again(qapp, dlg)
    assert _option(dlg._estimate_argv(), "--max-calls") == "5000"
    assert not dlg.cap_resets["calls"].isHidden() and dlg.cap_resets["cost"].isHidden()
    quote["caps"] = {**CAPS, "max_calls": 3000, "max_cost_usd": "30.00"}
    dlg.attacks.set_checked(())  # a changed selection
    _again(qapp, dlg)
    assert dlg.max_calls.value() == 5000 and dlg.max_cost.value() == pytest.approx(30.00)  # only the untyped follows
    assert calls.caption.text() == "Your value; the quote suggests 3,000 calls"
    assert "Typed: kept until" in dlg.max_calls.toolTip()
    dlg.cap_resets["calls"].click()  # Use the quote's figure
    qapp.processEvents()
    assert dlg.max_calls.value() == 3000 and calls.caption.text().startswith("Quote: p90 calls + 20 %")
    assert "--max-calls" not in dlg._estimate_argv() and dlg.cap_resets["calls"].isHidden()
    dlg.close()


def test_typed_prices_reach_the_estimate_with_the_cost_cap(qapp: Any, tmp_path: Path,
                                                            monkeypatch: pytest.MonkeyPatch) -> None:
    """The CLI takes --price-in and --price-out only with --max-cost-usd: typed prices go with the following cost cap,
    so the suggestion's worst-case room is priced at them."""
    dlg = _dialog(tmp_path, monkeypatch, scripted=False, quote=_quote())
    _settle(qapp, dlg)
    dlg.price_out.setValue(12.0)  # typed
    argv = dlg._estimate_argv()
    assert (_option(argv, "--max-cost-usd"), _option(argv, "--price-out")) == ("25.37", "12.0")
    assert "--max-calls" not in argv
    dlg.close()


@pytest.mark.parametrize(("reason", "caption"), [
    ("the model has no price at this endpoint (set one with agentprov prices set)",
     "Enter it yourself: the model has no price at this endpoint"),
    ("no recorded figures cover these cells, only your default assumptions (estimate.default.*); build cost figures "
     "with agentprov priors build, or pass --stats-corpus",
     "Enter it yourself: no recorded figures cover these cells, only your default assumptions"),
])
def test_without_a_suggestion_the_caps_are_typed(qapp: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                 reason: str, caption: str) -> None:
    dlg = _dialog(tmp_path, monkeypatch, scripted=False,
                  quote=_quote(available=False, reason=reason, max_calls=None, max_cost_usd=None, price_in=None,
                               price_out=None))
    _settle(qapp, dlg)
    assert dlg.max_calls.number() is None and dlg.max_cost.number() is None
    assert dlg.cap_rows["cost"].caption.text() == caption == dlg.cap_rows["calls"].caption.text()
    assert reason[:60] in dlg.max_cost.toolTip() and "type one" in dlg.max_cost.toolTip()
    assert dlg._gate() == "An API-endpoint run needs both caps: max model calls and max cost (D-725)."
    dlg.max_calls.setValue(100)
    dlg.max_cost.setValue(2)
    qapp.processEvents()
    assert dlg.cap_rows["calls"].caption.text().startswith("Your value (no suggestion: ")
    dlg.close()


def test_an_incomplete_suggestion_is_not_used() -> None:
    from agentprov_gui.live.plan import parse_caps

    caps = parse_caps({**CAPS, "max_cost_usd": "-1"})
    assert caps is not None and not caps.available and caps.max_calls is None
    assert caps.reason == "the CLI's suggestion is incomplete"
    assert parse_caps(None) is None and parse_caps("x") is None
    ok = parse_caps(CAPS)
    assert ok is not None and ok.available and ok.max_calls == 2210 and str(ok.max_cost_usd) == "25.37"


def test_the_words_name_local_priors_and_a_typed_margin() -> None:
    from agentprov_gui.live.capsfill import cap_text
    from agentprov_gui.live.plan import QuoteBasis, parse_caps

    caps = parse_caps({**CAPS, "margin_pct": "35", "margin_from": "setting", "resumed_units": 4})
    basis = QuoteBasis(priors="local", family_specific=True, executions=900, price_source="direct",
                       price_as_of="2026-11-01")
    words = cap_text("cost", caps, basis, typed=False, pending=False)
    assert words.caption == "Quote: upper cost (p90) + 35 % + room for 1 cell · your priors · provider list prices of " \
                            "2026-11-01"
    assert "(Settings › Estimate)" in words.tooltip and "the default" not in words.tooltip
    assert "Add the spend of the units" in words.tooltip and len(words.tooltip) <= 500  # help_tooltip keeps 500 characters
    wide = parse_caps({**CAPS, "resumed_units": 3, "max_calls": 12_345_678, "max_cost_usd": "123456.78",
                       "cell_calls": 864, "cell_usd": "1234.56", "reserved_cells": 16})
    mixed = QuoteBasis(priors="mixed", family_specific=False, executions=9, price_source="override",
                       price_as_of="2026-11-01")
    for which in ("cost", "calls"):
        for typed in (False, True):
            assert len(cap_text(which, wide, mixed, typed=typed, pending=False).tooltip) <= 500
    pending = cap_text("calls", None, None, typed=False, pending=True)
    assert pending.caption == "Filled from the quote once it is in"


def test_the_caps_margin_is_the_cli_setting(qapp: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings › Estimate's "Margin on the quote" is ``estimate.caps_margin_pct`` (unset: 20), written through
    agentprov settings, which agentprov estimate reads for its suggested caps."""
    import json

    from agentprov_gui.ui import livepanes

    calls: list[list[str]] = []
    stored: dict[str, Any] = {}

    def call(_cli: Any, argv: list[str], **_kw: Any) -> tuple[int, bytes, bytes]:
        calls.append(list(argv))
        if argv[:2] == ["settings", "list"]:
            return 0, json.dumps({"format": "agentprov-settings/0.1", "values": stored}).encode(), b""
        return 0, b"", b""

    monkeypatch.setattr(livepanes, "call", call)
    monkeypatch.setattr(livepanes, "submit", lambda _o, fn, done, _f=None: done(fn(None)))
    pane = livepanes.EstimatePane(None)
    assert pane.caps_margin.value() == 20 and livepanes.EstimatePane.KEYS["caps_margin"] == "estimate.caps_margin_pct"
    assert pane.pending() == []  # unset and unchanged: nothing written
    pane.caps_margin.setValue(35)
    assert pane.pending() == [["settings", "set", "estimate.caps_margin_pct", "35"]]
    assert pane.caps_margin.toolTip() and "estimate.caps_margin_pct" in pane.caps_margin.toolTip()
    pane.close()
    stored["estimate.caps_margin_pct"] = 50
    again = livepanes.EstimatePane(None)
    assert again.caps_margin.value() == 50 and again.pending() == []
    again.close()


def test_a_preset_run_is_quoted_with_its_llm_element() -> None:
    """estimate takes no --preset; a preset run uses gateway_compat (D-822), so its quote names that element."""
    from dataclasses import replace

    from agentprov_gui.live.runspec import RunSettings, estimate_argv

    base = RunSettings(campaign="t", suites=("banking",), attacks=("direct",), scripted=False, model="openrouter",
                       model_id="vendor/m", containment="vm")
    assert "--llm-element" not in estimate_argv(base, real_allowed=False)
    preset = estimate_argv(replace(base, extra={"m5ultra": True}), real_allowed=False)
    assert preset[preset.index("--llm-element") + 1] == "gateway_compat" and "--m5ultra" not in preset
    native = estimate_argv(replace(base, extra={"preset": "m5ultra", "llm_element": "native"}), real_allowed=False)
    assert native[native.index("--llm-element") + 1] == "native"
