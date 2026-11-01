"""The defence's own endpoint (D-675) in a real-model run: its key source, endpoint class, consent and caps
(review-uncovered UC-4, UC-5, UC-25). No network, no real key: the keychain is a stub."""

from __future__ import annotations

import argparse
import io
from pathlib import Path
from typing import Any

import pytest

from agentprov.cli.common import CommandResult
from agentprov.cli.live.defences import load_registry, registry_path

ROOT = Path(__file__).resolve().parents[2]
KEY = "sk-test-0123456789abcdef"


def _args(**over: Any) -> argparse.Namespace:
    base = dict(defence_endpoint="openai", allow_custom_endpoint=False, env_file=None, env_stdin=False, keychain=False,
                max_calls=None, max_cost_usd=None, price_in=None, price_out=None, preflight_only=False, judge=None,
                i_consent_to_api_costs=False, i_consent_to_local_run=True)
    return argparse.Namespace(**{**base, **over})


@pytest.fixture
def melon() -> Any:
    return load_registry(registry_path(ROOT))["melon"]


def _keychain(monkeypatch: pytest.MonkeyPatch, held: dict[str, str]) -> None:
    import agentprov.keys
    from agentprov.keys import KeychainError

    def read(names: list[str]) -> dict[str, str]:
        if not all(n in held for n in names):
            raise KeychainError("keychain.missing")
        return {n: held[n] for n in names}

    monkeypatch.setattr(agentprov.keys, "read", read)


# ------------------------------------------------------------------------------------------------------------ UC-25
def test_the_defence_key_comes_from_the_keychain_first(monkeypatch: pytest.MonkeyPatch, melon: Any) -> None:
    from agentprov.cli.run import _defence_endpoint

    _keychain(monkeypatch, {"OPENAI_API_KEY": KEY})
    keys: dict[str, str] = {}
    result = CommandResult()
    spec = _defence_endpoint(_args(), melon, {"OPENAI_API_KEY": "sk-from-dotenv-000000"}, keys, result, scripted=False)
    assert spec is not None and keys == {"OPENAI_API_KEY": KEY}
    assert any("defence endpoint) from the OS keychain" in n for n in result.notices)


def test_the_defence_key_falls_back_to_dotenv_and_a_missing_key_names_both_places(
        monkeypatch: pytest.MonkeyPatch, melon: Any) -> None:
    from agentprov.cli.run import LiveEnvironmentError, _defence_endpoint

    _keychain(monkeypatch, {})
    keys: dict[str, str] = {}
    _defence_endpoint(_args(), melon, {"OPENAI_API_KEY": KEY}, keys, CommandResult(), scripted=False)
    assert keys == {"OPENAI_API_KEY": KEY}
    with pytest.raises(LiveEnvironmentError, match="neither the OS keychain .* nor .env"):
        _defence_endpoint(_args(), melon, {}, {}, CommandResult(), scripted=False)


def test_the_defence_key_follows_an_explicit_key_source(monkeypatch: pytest.MonkeyPatch, melon: Any) -> None:
    from agentprov.cli.run import LiveEnvironmentError, _defence_endpoint

    _keychain(monkeypatch, {"OPENAI_API_KEY": KEY})
    with pytest.raises(LiveEnvironmentError, match="not in the given source"):  # --env-file: that file only
        _defence_endpoint(_args(env_file="x.env"), melon, {}, {}, CommandResult(), scripted=False)
    keys: dict[str, str] = {}
    _defence_endpoint(_args(keychain=True), melon, {}, keys, CommandResult(), scripted=False)
    assert keys == {"OPENAI_API_KEY": KEY}
    _keychain(monkeypatch, {})
    with pytest.raises(LiveEnvironmentError, match="is not in the OS keychain"):  # --keychain: never .env
        _defence_endpoint(_args(keychain=True), melon, {"OPENAI_API_KEY": KEY}, {}, CommandResult(), scripted=False)


# ------------------------------------------------------------------------------------------------------------- UC-4
LOCAL_AGENT = {"endpoint": "ollama", "base_url": "http://127.0.0.1:11434/v1", "model_requested": "qwen3:8b",
               "api_key_env": None, "llm_element": "native", "params": {}}


class _Ctx:
    def __init__(self) -> None:
        self.stderr = io.StringIO()


def _spec(melon: Any, args: argparse.Namespace) -> dict[str, Any]:
    from agentprov.cli.run import _defence_endpoint

    spec = _defence_endpoint(args, melon, {"OPENAI_API_KEY": KEY}, {}, CommandResult(), scripted=False)
    assert spec is not None
    return spec


def test_a_remote_defence_endpoint_makes_a_local_agent_run_an_api_run(monkeypatch: pytest.MonkeyPatch,
                                                                      melon: Any) -> None:
    from agentprov.cli.run import LiveRefused, _class_with_defence, _consent

    _keychain(monkeypatch, {})
    args = _args()
    spec = _spec(melon, args)
    with pytest.raises(LiveRefused, match="defence endpoint is not a local server.*--max-calls, --max-cost-usd"):
        _class_with_defence(args, LOCAL_AGENT, "local", spec, CommandResult())
    capped = _args(max_calls=100, max_cost_usd=1.0, price_in=1.0, price_out=1.0)
    result = CommandResult()
    kind = _class_with_defence(capped, LOCAL_AGENT, "local", spec, result)
    assert kind == "api" and any("endpoint class api" in n for n in result.notices)
    ctx = _Ctx()
    with pytest.raises(LiveRefused, match="--i-consent-to-local-run is consent for a local model server"):
        _consent(capped, agent=LOCAL_AGENT, ctx=ctx, result=CommandResult(), endpoint_kind=kind,
                 defence_endpoint=spec)  # type: ignore[arg-type]
    text = ctx.stderr.getvalue()
    assert "defence endpoint https://api.openai.com/v1 (openai), key variable OPENAI_API_KEY" in text
    assert "may be billed by the provider" in text and "no provider billing" not in text


def test_a_local_agent_without_a_defence_endpoint_stays_local(melon: Any) -> None:
    from agentprov.cli.run import _class_with_defence, _defence_entry_remote

    assert _class_with_defence(_args(), LOCAL_AGENT, "local", None, CommandResult()) == "local"
    assert _defence_entry_remote("openai") and not _defence_entry_remote("ollama")
    assert not _defence_entry_remote(None) and not _defence_entry_remote("no-such-endpoint")


# ------------------------------------------------------------------------------------------------------------- UC-5
def test_the_cell_bound_counts_the_defence_s_declared_calls() -> None:
    from agentprov.cli.live.policy import CELL_CALL_BOUND, defence_cell_calls

    reg = load_registry(registry_path(ROOT))
    assert defence_cell_calls(reg["repeat_user_prompt"].raw.get("cost")) == CELL_CALL_BOUND == 48
    assert defence_cell_calls(reg["tool_filter"].raw.get("cost")) == 48 + 3  # one call per pass
    assert defence_cell_calls(reg["melon"].raw.get("cost")) == 48 + 3 * 48  # a masked call and two embeddings a step
    assert defence_cell_calls(None) == 48
    for bad in ({"extra_calls_per_step": -1}, {"extra_calls_per_step": float("inf")}, {"calls_per_day": 1}, [1]):
        assert defence_cell_calls(bad) is None


def test_a_melon_cell_is_not_admitted_when_its_calls_do_not_fit_the_cap() -> None:
    """The review's case: --max-calls 100 with 52 calls spent; a MELON cell may make up to 192 calls."""
    from agentprov.cli.live.policy import Budget, Caps
    from agentprov.cli.run import _defence_cell_calls

    melon = load_registry(registry_path(ROOT))["melon"]
    budget = Budget(Caps(max_calls=100), cell_calls=_defence_cell_calls(melon))
    budget.calls = 52
    refusal = budget.refusal(0)
    assert refusal is not None and refusal.startswith("cap_reached") and "may need 192" in refusal
    assert budget.record()["cell_call_bound"] == 192
    assert Budget(Caps(max_calls=100), cell_calls=_defence_cell_calls(None)).cell_calls == 48


def test_a_cost_cap_is_refused_when_the_defence_endpoint_has_no_prices_of_its_own(
        monkeypatch: pytest.MonkeyPatch, melon: Any) -> None:
    from agentprov.cli.run import LiveRefused, _check_defence_caps

    _keychain(monkeypatch, {})
    spec = _spec(melon, _args())
    with pytest.raises(LiveRefused, match="cannot price the calls the defence melon makes"):
        _check_defence_caps(_args(max_calls=500, max_cost_usd=1.0, price_in=1.0, price_out=1.0), melon, spec)
    _check_defence_caps(_args(max_calls=500), melon, spec)  # a call cap alone needs no prices
    loopback = {**spec, "endpoint": "ollama", "base_url": "http://127.0.0.1:11434/v1"}
    _check_defence_caps(_args(max_calls=500, max_cost_usd=1.0, price_in=1.0, price_out=1.0), melon, loopback)
