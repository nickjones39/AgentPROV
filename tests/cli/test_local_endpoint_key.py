"""A local endpoint's optional key (D-827): oMLX can be set up with an API key, so the ``omlx`` entry names
``OMLX_API_KEY``. Set, it is sent as a bearer header to the loopback server (discovery, the preflight, the per-cell
re-observation and the run); not set, nothing is sent, as before. It never goes to a LAN address and is never shown.

Against :class:`agentprov.testing.local_server.StubServer` with ``api_key``; no real server, no keychain (the suite
sets ``AGENTPROV_NO_KEYCHAIN``) and no ``.env`` (``_read_env_file`` is replaced).
"""

from __future__ import annotations

import io
import json
import sys
from collections.abc import Callable
from typing import Any

import pytest

from agentprov.cli.live import localmodels as lm
from agentprov.testing.local_server import StubServer

KEY = "omlx-test-key-" + "k7Q2" * 6  # a synthetic value; asserted absent from every output


@pytest.fixture
def no_env_file(monkeypatch: pytest.MonkeyPatch) -> None:
    from agentprov.cli import run as run_mod

    monkeypatch.setattr(run_mod, "_read_env_file", lambda args, root: {})


def _stdin(monkeypatch: pytest.MonkeyPatch, document: dict[str, str]) -> None:
    class _In:
        buffer = io.BytesIO(json.dumps(document).encode("utf-8"))

    monkeypatch.setattr(sys, "stdin", _In())


def test_registry_omlx_names_an_optional_key() -> None:
    from agentprov_capture.endpoints import get_endpoint, load_endpoints

    omlx = get_endpoint("omlx")
    assert omlx.local and omlx.api_key_env == "OMLX_API_KEY"
    others = {n: e.api_key_env for n, e in load_endpoints().items() if e.local and n != "omlx"}
    assert others and set(others.values()) == {None}


def test_client_sends_the_key_only_when_given() -> None:
    with StubServer("omlx", api_key=KEY) as srv:
        with pytest.raises(lm.LocalModelError) as exc:
            lm.list_server(srv.base_url, endpoint="omlx", expected_kind="omlx")
        listing = lm.list_server(srv.base_url, endpoint="omlx", expected_kind="omlx", api_key=KEY)
        rec = lm.model_identity(listing, "stub-org/tiny-model-4bit", environ={}, files=False, api_key=KEY)
    assert (exc.value.code, exc.value.exit_code) == ("run.local.unauthorized", 3)
    assert "HTTP 401" in str(exc.value) and "agentprov keys set OMLX_API_KEY" in str(exc.value)
    assert "stub-org/tiny-model-4bit" in listing.ids() and rec["format"] == lm.IDENTITY_FORMAT
    sent = [s["headers"].get("authorization") for s in srv.seen]
    assert sent[0] is None and set(sent[1:]) == {f"Bearer {KEY}"}
    assert KEY not in json.dumps(rec) and KEY not in json.dumps(lm.listing_entry(listing))


def test_a_wrong_key_is_named_not_shown() -> None:
    with StubServer("omlx", api_key=KEY) as srv, pytest.raises(lm.LocalModelError) as exc:
        lm.list_server(srv.base_url, endpoint="omlx", expected_kind="omlx", api_key="not-the-key")
    assert exc.value.code == "run.local.unauthorized" and "OMLX_API_KEY that was sent" in str(exc.value)
    assert "not-the-key" not in str(exc.value)


def test_keyless_endpoint_hint_and_keyless_servers_unchanged() -> None:
    with StubServer("omlx", api_key=KEY) as srv, pytest.raises(lm.LocalModelError) as exc:
        lm.list_server(srv.base_url, endpoint="lmstudio")
    assert "has no key setting" in str(exc.value)
    with StubServer("omlx") as srv:
        lm.list_server(srv.base_url, endpoint="omlx", expected_kind="omlx")
    assert all("authorization" not in s["headers"] for s in srv.seen)


def test_a_key_never_goes_to_a_lan_address() -> None:
    with pytest.raises(lm.LocalModelError) as exc:
        lm.LoopbackClient("http://192.168.1.5:8000/v1", allow_lan=True, api_key=KEY)
    assert (exc.value.code, exc.value.exit_code) == ("run.local.lan_key", 4)


def test_models_command_reads_the_key_from_stdin(cli: Callable[..., Any], monkeypatch: pytest.MonkeyPatch) -> None:
    with StubServer("omlx", api_key=KEY) as srv:
        _stdin(monkeypatch, {"OMLX_API_KEY": KEY})
        ok = cli("models", "--endpoint", "omlx", "--base-url", srv.base_url, "--env-stdin", "--format", "json")
    assert ok.code == 0, ok.err
    assert ok.json()["endpoints"][0]["status"] == "up"
    assert KEY not in ok.out + ok.err


def test_models_command_without_the_key(cli: Callable[..., Any], no_env_file: None) -> None:
    with StubServer("omlx", api_key=KEY) as srv:
        refused = cli("models", "--endpoint", "omlx", "--base-url", srv.base_url)
    with StubServer("omlx") as srv:
        keyless = cli("models", "--endpoint", "omlx", "--base-url", srv.base_url)
    assert refused.code == 3 and "agentprov keys set OMLX_API_KEY" in refused.err
    assert keyless.code == 0, keyless.err


def test_key_options_need_a_keyed_endpoint(cli: Callable[..., Any]) -> None:
    assert cli("models", "--endpoint", "lmstudio", "--keychain").code == 2
    assert cli("models", "--endpoint", "omlx", "--allow-network").code == 2


def test_run_agent_is_keyless_without_the_key_and_refuses_lan(monkeypatch: pytest.MonkeyPatch) -> None:
    import argparse

    from agentprov.cli import run as run_mod
    from agentprov.cli.common import CommandResult

    def args(**kw: Any) -> argparse.Namespace:
        base = {"model": "omlx", "endpoint": None, "model_id": "m", "env_file": None, "env_stdin": False,
                "keychain": False, "base_url": None, "allow_lan_endpoint": False, "allow_custom_endpoint": False,
                "temperature": None, "reasoning_effort": None, "llm_element": None}
        return argparse.Namespace(**{**base, **kw})

    result = CommandResult()
    agent, keys = run_mod._real_agent(args(), {}, result)
    assert agent["api_key_env"] is None and keys == {}  # keyless: the configuration digest input is as before D-827
    assert any("OMLX_API_KEY is not set" in n for n in result.notices)
    agent, keys = run_mod._real_agent(args(), {"OMLX_API_KEY": KEY}, CommandResult())
    assert agent["api_key_env"] == "OMLX_API_KEY" and keys == {"OMLX_API_KEY": KEY}
    agent, _keys = run_mod._real_agent(args(model_id=None), {"OMLX_MODEL": "Qwen3.5-4B-MLX-4bit"}, CommandResult())
    assert agent["model_requested"] == "Qwen3.5-4B-MLX-4bit"  # model_env (D-827 addendum): the served id
    with pytest.raises(run_mod.LiveRefused) as exc:
        run_mod._real_agent(args(base_url="http://192.168.1.5:8000/v1", allow_lan_endpoint=True),
                            {"OMLX_API_KEY": KEY}, CommandResult())
    assert exc.value.code == "cli.refused.lan_key" and KEY not in str(exc.value)
