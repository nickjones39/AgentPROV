"""API providers' model lists (D-730..D-735): fetch, cache, price join and the CLI, against stub servers only.

No real network: the HTTPS connection factory is replaced with a plain-HTTP connection to a loopback
:class:`~agentprov.testing.local_server.StubServer` that serves synthetic bodies in each provider's documented shape.
"""

from __future__ import annotations

import http.client
import json
import types
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from agentprov.cli.common import CommandResult
from agentprov.cli.live import providermodels as pm
from agentprov.testing.local_server import StubServer

NOW = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)
KEY = "sk-test-not-a-real-key-0123456789abcdef"


@pytest.fixture
def stub(monkeypatch: pytest.MonkeyPatch) -> Iterator[StubServer]:
    """A loopback stub standing in for every provider host (the HTTPS factory connects to it instead)."""
    with StubServer("vllm", models=[]) as srv:
        def plain(host: str, port: int, timeout: float) -> http.client.HTTPConnection:
            srv.seen.append({"method": "CONNECT-TARGET", "path": f"{host}:{port}", "body": b"", "headers": {}})
            return http.client.HTTPConnection("127.0.0.1", srv.port, timeout=timeout)

        monkeypatch.setattr(pm, "_https", plain)
        yield srv


def _openrouter(*ids: str) -> dict[str, Any]:
    return {"data": [{"id": i, "name": i.upper(), "created": 1_700_000_000, "context_length": 8192,
                      "pricing": {"prompt": "0.000001", "completion": "0.000002"}} for i in ids]}


class _Book:
    def __init__(self, priced: dict[str, set[str]]) -> None:
        self.priced = priced

    def lookup(self, endpoint: str, model: str) -> object | None:
        import re

        known = self.priced.get(endpoint, set())
        alias = re.sub(r"-20[0-9]{6}$", "", model)  # the D-701 follow-up: a dated id is priced by its alias
        name = model if model in known else alias if alias in known else None
        return types.SimpleNamespace(model=name) if name else None

    def models_for(self, endpoint: str) -> list[str]:
        return sorted(self.priced.get(endpoint, set()))


# ---- fetch -------------------------------------------------------------------------------------------------------


def test_openrouter_list_is_public_cached_and_joined_with_prices(stub: StubServer, tmp_path: Path) -> None:
    stub.set("/api/v1/models", 200, _openrouter("openai/gpt-x", "google/gemini-y", "../bad"))
    doc = pm.fetch("openrouter", {}, now=NOW)
    assert [m["id"] for m in doc["models"]] == ["google/gemini-y", "openai/gpt-x"]  # the path-like id is dropped
    assert doc["fetched_at"] == "2026-10-22T12:00:00Z" and doc["host"] == "openrouter.ai"
    assert doc["models"][1]["listed_price_per_token"] == {"prompt": "0.000001", "completion": "0.000002"}
    assert "authorization" not in stub.seen[-1]["headers"]  # public: no key sent unless one was given
    targets = [s["path"] for s in stub.seen if s["method"] == "CONNECT-TARGET"]
    assert targets == ["openrouter.ai:443"]  # egress to the registry host only
    pm.write_cache(tmp_path, doc)
    cached = pm.read_cache(tmp_path, "openrouter")
    assert cached == doc
    out = pm.document("openrouter", cached, source="cache", now=NOW + timedelta(hours=1),
                      price_book=_Book({"openrouter": {"openai/gpt-x", "old/model"}}))
    status = {m["id"]: m["price_status"] for m in out["models"]}
    assert status == {"google/gemini-y": "no_price", "openai/gpt-x": "priced"}
    assert out["not_listed"] == [{"id": "old/model", "listed": False, "price_status": "priced"}]
    assert out["stale"] is False
    assert pm.document("openrouter", cached, source="cache", now=NOW + timedelta(hours=25))["stale"] is True


def test_openrouter_shorthands_filter_by_vendor_prefix(stub: StubServer) -> None:
    stub.set("/api/v1/models", 200, _openrouter("google/gemini-y", "openai/gpt-x", "z-ai/glm-5", "thudm/glm-4"))
    assert [m["id"] for m in pm.fetch("gemini", {})["models"]] == ["google/gemini-y"]
    assert [m["id"] for m in pm.fetch("glm", {})["models"]] == ["thudm/glm-4", "z-ai/glm-5"]


def test_anthropic_pages_with_the_key_header(stub: StubServer) -> None:
    page1 = {"data": [{"id": "claude-opus-5-5", "display_name": "Claude Opus 5.5", "created_at": "2026-09-21T00:00:00Z",
                       "lifecycle": "active", "max_input_tokens": 1_000_000, "max_tokens": 128_000, "type": "model"}],
             "has_more": True, "first_id": "claude-opus-5-5", "last_id": "claude-opus-5-5"}
    page2 = {"data": [{"id": "claude-haiku-5-5", "display_name": "Claude Haiku 5.5", "lifecycle": "deprecated",
                       "type": "model"}], "has_more": False, "last_id": "claude-haiku-5-5"}
    stub.set("/v1/models?limit=1000", 200, page1)
    stub.set("/v1/models?limit=1000&after_id=claude-opus-5-5", 200, page2)
    doc = pm.fetch("anthropic", {"ANTHROPIC_API_KEY": KEY})
    assert [(m["id"], m.get("lifecycle")) for m in doc["models"]] == [("claude-haiku-5-5", "deprecated"),
                                                                      ("claude-opus-5-5", "active")]
    assert len(doc["responses"]) == 2
    asked = [s for s in stub.seen if s["method"] == "GET"]
    assert all(s["headers"]["x-api-key"] == KEY and s["headers"]["anthropic-version"] == pm.ANTHROPIC_VERSION
               for s in asked)
    assert KEY not in json.dumps(doc)  # the key is never in the document


def test_keyed_providers_need_their_key_and_send_it_as_bearer(stub: StubServer) -> None:
    with pytest.raises(pm.ProviderModelError) as exc:
        pm.fetch("openai", {})
    assert exc.value.code == "models.provider.credential" and not [s for s in stub.seen if s["method"] == "GET"]
    stub.set("/v1/models", 200, {"object": "list", "data": [{"id": "gpt-x", "object": "model", "owned_by": "o"}]})
    stub.set("/models", 200, {"object": "list", "data": [{"id": "deepseek-chat", "object": "model"}]})
    assert [m["id"] for m in pm.fetch("openai", {"OPENAI_API_KEY": KEY})["models"]] == ["gpt-x"]
    assert [m["id"] for m in pm.fetch("deepseek", {"DEEPSEEK_API_KEY": KEY})["models"]] == ["deepseek-chat"]
    assert {s["headers"]["authorization"] for s in stub.seen if s["method"] == "GET"} == {f"Bearer {KEY}"}


@pytest.mark.parametrize("status, body, code", [
    (302, b"", "models.provider.http_status"),
    (401, b'{"error": "nope"}', "models.provider.http_status"),
    (200, b'{"data": "x"}', "models.provider.bad_list"),
    (200, b'{"data": [], "data": []}', "models.provider.bad_list"),
    (200, b"not json", "models.provider.bad_list"),
])
def test_hostile_answers_fail_closed(stub: StubServer, status: int, body: bytes, code: str) -> None:
    stub.set("/api/v1/models", status, body)
    with pytest.raises(pm.ProviderModelError) as exc:
        pm.fetch("openrouter", {})
    assert exc.value.code == code and exc.value.exit_code == 3


def test_a_damaged_cache_is_never_half_read(tmp_path: Path) -> None:
    path = pm.cache_path(tmp_path, "openrouter")
    path.parent.mkdir(parents=True)
    for bad in (b"{", json.dumps({"format": pm.CACHE_FORMAT, "endpoint": "openai", "fetched_at": "2026-10-22T12:00:00Z",
                                   "models": []}).encode(),
                json.dumps({"format": pm.CACHE_FORMAT, "endpoint": "openrouter", "fetched_at": "yesterday",
                            "models": []}).encode(),
                json.dumps({"format": pm.CACHE_FORMAT, "endpoint": "openrouter", "fetched_at": "2026-10-22T12:00:00Z",
                            "models": [{"id": "../x"}]}).encode()):
        path.write_bytes(bad)
        assert pm.read_cache(tmp_path, "openrouter") is None


def test_the_static_endpoint_lists_equal_the_registry() -> None:
    from agentprov.cli.live.localmodels import local_endpoint_names
    from agentprov.cli.models import MODELS_ENDPOINTS
    from agentprov_capture.endpoints import load_endpoints

    registry = load_endpoints()
    assert sorted(pm.PROVIDER_ENDPOINTS) == sorted(n for n, e in registry.items() if not e.local)
    assert sorted(MODELS_ENDPOINTS) == sorted([*pm.PROVIDER_ENDPOINTS, *local_endpoint_names()])


# ---- the command -------------------------------------------------------------------------------------------------


def test_models_shows_the_cache_and_fetches_only_with_allow_network(cli: Callable[..., Any], stub: StubServer) -> None:
    stub.set("/api/v1/models", 200, _openrouter("openai/gpt-x"))
    none = cli("models", "--endpoint", "openrouter", "--format", "json")
    assert none.code == 0 and none.json()["source"] == "none" and none.json()["models"] == []
    assert not [s for s in stub.seen if s["method"] == "GET"]  # no network without the flag
    fetched = cli("models", "--endpoint", "openrouter", "--allow-network", "--format", "json")
    assert fetched.code == 0, fetched.err
    assert fetched.json()["source"] == "network" and [m["id"] for m in fetched.json()["models"]] == ["openai/gpt-x"]
    again = cli("models", "--endpoint", "openrouter", "--format", "json")
    assert again.json()["source"] == "cache" and again.json()["stale"] is False
    assert len([s for s in stub.seen if s["method"] == "GET"]) == 1
    assert {m["price_status"] for m in again.json()["models"]} <= {"priced", "no_price"}


def test_refresh_if_stale_needs_the_setting(cli: Callable[..., Any], stub: StubServer) -> None:
    from agentprov import settings

    stub.set("/api/v1/models", 200, _openrouter("openai/gpt-x"))
    off = cli("models", "--endpoint", "openrouter", "--refresh-if-stale", "--format", "json")
    assert off.code == 0 and off.json()["source"] == "none"
    assert not [s for s in stub.seen if s["method"] == "GET"]  # the setting is off: no network
    settings.set("models.auto_refresh", True)
    on = cli("models", "--endpoint", "openrouter", "--refresh-if-stale", "--format", "json")
    fresh = cli("models", "--endpoint", "openrouter", "--refresh-if-stale", "--format", "json")
    assert on.json()["source"] == "network" and fresh.json()["source"] == "cache"  # at most once per 24 h
    assert len([s for s in stub.seen if s["method"] == "GET"]) == 1


def test_a_failed_refresh_shows_the_cached_list_marked(cli: Callable[..., Any], stub: StubServer) -> None:
    stub.set("/api/v1/models", 200, _openrouter("openai/gpt-x"))
    assert cli("models", "--endpoint", "openrouter", "--allow-network").code == 0
    stub.set("/api/v1/models", 503, b"")
    run = cli("models", "--endpoint", "openrouter", "--allow-network", "--format", "json")
    assert run.code == 0 and run.json()["source"] == "cache"
    assert run.json()["refresh_error"] == "models.provider.http_status"
    assert [m["id"] for m in run.json()["models"]] == ["openai/gpt-x"]


def test_keychain_supplies_the_key_and_it_is_never_printed(cli: Callable[..., Any], stub: StubServer,
                                                           monkeypatch: pytest.MonkeyPatch) -> None:
    import agentprov.keys

    monkeypatch.setattr(agentprov.keys, "read", lambda names: {n: KEY for n in names})
    stub.set("/v1/models", 200, {"data": [{"id": "gpt-x"}]})
    run = cli("models", "--endpoint", "openai", "--allow-network", "--keychain", "--format", "json")
    assert run.code == 0, run.err
    assert KEY not in run.out and KEY not in run.err
    from agentprov.cli import run as run_cmd

    def no_key(names: list[str]) -> dict[str, str]:
        raise agentprov.keys.KeychainError("keychain.missing")

    monkeypatch.setattr(agentprov.keys, "read", no_key)
    monkeypatch.setattr(run_cmd, "_read_env_file", lambda args, root: {})
    before = len([s for s in stub.seen if s["method"] == "GET"])
    missing = cli("models", "--endpoint", "deepseek", "--allow-network", "--format", "json")
    assert missing.code == 3  # no key from any source: refused before any request
    assert len([s for s in stub.seen if s["method"] == "GET"]) == before


def test_option_groups_are_exclusive(cli: Callable[..., Any]) -> None:
    assert cli("models", "--endpoint", "lmstudio", "--allow-network").code == 2
    assert cli("models", "--endpoint", "openrouter", "--base-url", "http://127.0.0.1:1/v1").code == 2
    assert cli("models", "--endpoint", "openai", "--keychain", "--env-stdin", "--allow-network").code == 2


# ---- the run warning (D-734) --------------------------------------------------------------------------------------


def test_run_warns_when_the_cached_list_lacks_the_model(tmp_path: Path) -> None:
    from agentprov.cli.run import _warn_unlisted

    doc = {"format": pm.CACHE_FORMAT, "endpoint": "openai", "host": "api.openai.com", "fetched_at": "2026-10-22T12:00:00Z",
           "responses": [], "models": [{"id": "gpt-x"}]}
    pm.write_cache(tmp_path, doc)
    ctx = types.SimpleNamespace(env={"AGENTPROV_HOME": str(tmp_path)})
    listed, unlisted, no_cache = CommandResult(), CommandResult(), CommandResult()
    _warn_unlisted(ctx, {"endpoint": "openai", "model_requested": "gpt-x"}, listed)  # type: ignore[arg-type]
    _warn_unlisted(ctx, {"endpoint": "openai", "model_requested": "gpt-y"}, unlisted)  # type: ignore[arg-type]
    _warn_unlisted(ctx, {"endpoint": "deepseek", "model_requested": "z"}, no_cache)  # type: ignore[arg-type]
    assert listed.notices == [] and no_cache.notices == []
    assert len(unlisted.notices) == 1 and "gpt-y is not in openai's cached model list" in unlisted.notices[0]


# ---- key sources: the keychain is the source of truth, .env the fallback (user decision 2026-10-22) ---------------


def _openai_stub(stub: StubServer) -> None:
    stub.set("/v1/models", 200, {"data": [{"id": "gpt-x"}]})


def test_the_keychain_wins_over_env(cli: Callable[..., Any], stub: StubServer, monkeypatch: pytest.MonkeyPatch) -> None:
    import agentprov.keys
    from agentprov.cli import run as run_cmd

    _openai_stub(stub)
    monkeypatch.setattr(agentprov.keys, "read", lambda names: {n: KEY for n in names})
    monkeypatch.setattr(run_cmd, "_read_env_file", lambda args, root: {"OPENAI_API_KEY": "sk-from-env-file-0123456789"})
    run = cli("models", "--endpoint", "openai", "--allow-network", "--format", "json")
    assert run.code == 0, run.err
    assert {s["headers"]["authorization"] for s in stub.seen if s["method"] == "GET"} == {f"Bearer {KEY}"}


@pytest.mark.parametrize("failure", ["keychain.missing", "keys.helper_failed"])
def test_env_is_the_fallback_when_the_keychain_has_no_key(cli: Callable[..., Any], stub: StubServer,
                                                          monkeypatch: pytest.MonkeyPatch, failure: str) -> None:
    import agentprov.keys
    from agentprov.cli import run as run_cmd

    _openai_stub(stub)
    env_key = "sk-from-env-file-0123456789"

    def no_key(names: list[str]) -> dict[str, str]:
        raise agentprov.keys.KeychainError(failure)

    monkeypatch.setattr(agentprov.keys, "read", no_key)
    monkeypatch.setattr(run_cmd, "_read_env_file", lambda args, root: {"OPENAI_API_KEY": env_key})
    run = cli("models", "--endpoint", "openai", "--allow-network", "--format", "json")
    assert run.code == 0, run.err
    assert {s["headers"]["authorization"] for s in stub.seen if s["method"] == "GET"} == {f"Bearer {env_key}"}
    assert env_key not in run.out and env_key not in run.err


def test_explicit_keychain_never_falls_back_to_env(cli: Callable[..., Any], stub: StubServer,
                                                   monkeypatch: pytest.MonkeyPatch) -> None:
    import agentprov.keys
    from agentprov.cli import run as run_cmd

    _openai_stub(stub)

    def no_key(names: list[str]) -> dict[str, str]:
        raise agentprov.keys.KeychainError("keychain.missing")

    monkeypatch.setattr(agentprov.keys, "read", no_key)
    monkeypatch.setattr(run_cmd, "_read_env_file", lambda args, root: {"OPENAI_API_KEY": "sk-from-env-file-0123456789"})
    run = cli("models", "--endpoint", "openai", "--allow-network", "--keychain", "--format", "json")
    assert run.code == 3 and not [s for s in stub.seen if s["method"] == "GET"]


def test_a_dated_id_priced_by_its_alias_is_not_reported_not_listed() -> None:
    cache = {"format": pm.CACHE_FORMAT, "endpoint": "anthropic", "host": "api.anthropic.com",
             "fetched_at": "2026-10-22T12:00:00Z", "responses": [],
             "models": [{"id": "claude-haiku-4-5-20251001"}, {"id": "claude-opus-5-5"}]}
    book = _Book({"anthropic": {"claude-haiku-4-5", "claude-opus-5-5", "claude-mythos-5"}})
    out = pm.document("anthropic", cache, source="cache", price_book=book, now=NOW)
    rows = {m["id"]: m for m in out["models"]}
    assert rows["claude-haiku-4-5-20251001"]["price_status"] == "priced"
    assert rows["claude-haiku-4-5-20251001"]["priced_as"] == "claude-haiku-4-5"
    assert "priced_as" not in rows["claude-opus-5-5"]
    assert [m["id"] for m in out["not_listed"]] == ["claude-mythos-5"]  # the alias is covered; mythos is not listed
