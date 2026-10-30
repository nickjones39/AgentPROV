"""Endpoint registry: shipped data and loader validation (stdlib + agentprov_capture only; never agentprov)."""

from __future__ import annotations

import ast
import pathlib
import tomllib

import pytest

from agentprov_capture import endpoints as ep

BASELINE = ("deepseek", "openai", "openrouter", "gemini", "llama", "qwen", "glm", "ollama")
LOCAL_D690 = ("lmstudio", "mlx_lm", "llamacpp", "vllm")


def test_registry_has_baseline_and_omlx() -> None:
    reg = ep.load_endpoints()
    assert set(reg) == {*BASELINE, "omlx", "anthropic", *LOCAL_D690}


def test_anthropic_entry_speaks_messages() -> None:
    """D-656: the direct Anthropic Messages endpoint; every other entry keeps the OpenAI chat format."""
    reg = ep.load_endpoints()
    a = reg["anthropic"]
    assert (a.base_url, a.host, a.local) == ("https://api.anthropic.com", "api.anthropic.com", False)
    assert (a.api_key_env, a.base_url_env, a.model_env) == ("ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL", "ANTHROPIC_MODEL")
    assert a.api == "anthropic_messages"
    assert a.request_headers == ("anthropic-beta", "anthropic-version")
    assert a.response_headers == ("request-id", "retry-after", "x-should-retry")
    assert {n for n, e in reg.items() if e.api != "openai_chat"} == {"anthropic"}


def test_anthropic_headers_keep_versions_and_ids_never_the_key() -> None:
    """The hard denylist wins: the key header is dropped by name; the organisation id and rate-limit headers are
    names only; the version, beta, request-id and retry headers keep their values."""
    from agentprov_capture.redact import filter_headers

    req = filter_headers([("x-api-key", "sk-ant-api03-" + "A" * 40), ("anthropic-version", "2023-06-01"),
                          ("anthropic-beta", "b-1"), ("authorization", "Bearer x"), ("x-stainless-retry-count", "0"),
                          ("content-type", "application/json")], direction="request", endpoint="anthropic")
    assert req.kept == {"anthropic-beta": "b-1", "anthropic-version": "2023-06-01", "content-type": "application/json"}
    assert {"x-api-key", "authorization", "x-stainless-retry-count"} <= set(req.dropped)
    resp = filter_headers([("request-id", "req_1"), ("retry-after", "3"), ("x-should-retry", "true"),
                           ("anthropic-organization-id", "org-uuid"), ("anthropic-ratelimit-requests-remaining", "9")],
                          direction="response", endpoint="anthropic")
    assert resp.kept == {"request-id": "req_1", "retry-after": "3", "x-should-retry": "true"}
    assert set(resp.dropped) == {"anthropic-organization-id", "anthropic-ratelimit-requests-remaining"}


def test_anthropic_key_shapes_are_covered() -> None:
    """``sk-ant-...`` keys match the key-shaped pattern (redacted on non-content surfaces), and the key variable is
    scanned for literally while the base URL and model variables are public configuration."""
    from agentprov_capture.redact import Redactor, secrets_from_environ

    key = "sk-ant-api03-" + "Ab9_-" * 16
    assert key not in Redactor([]).scrub_text(f"error talking to api: {key}", non_content=True)
    names = [s.name for s in secrets_from_environ({"ANTHROPIC_API_KEY": key, "ANTHROPIC_BASE_URL": "https://x",
                                                   "ANTHROPIC_MODEL": "claude-haiku-5-5"})]
    assert names == ["ANTHROPIC_API_KEY"]


def test_local_entries() -> None:
    omlx, ollama = ep.get_endpoint("omlx"), ep.get_endpoint("ollama")
    assert omlx.base_url == "http://127.0.0.1:8000/v1" and omlx.local and omlx.api_key_env == "OMLX_API_KEY"  # D-827
    assert omlx.model_env == "OMLX_MODEL"  # D-827 addendum
    assert omlx.server_max_concurrency == 8
    assert ollama.base_url == "http://127.0.0.1:11434/v1" and ollama.local and ollama.api_key_env is None
    assert ollama.server_max_concurrency is None
    assert omlx.host == ollama.host == "127.0.0.1"


@pytest.mark.parametrize(
    "name, url, env, conc",
    [
        ("ollama", "http://127.0.0.1:11434/v1", "LOCAL_LLM_BASE_URL", None),
        ("omlx", "http://127.0.0.1:8000/v1", "OMLX_BASE_URL", 8),
        ("lmstudio", "http://127.0.0.1:1234/v1", "LMSTUDIO_BASE_URL", None),
        ("mlx_lm", "http://127.0.0.1:8080/v1", "MLX_LM_BASE_URL", 1),
        ("llamacpp", "http://127.0.0.1:8080/v1", "LLAMACPP_BASE_URL", None),
        ("vllm", "http://127.0.0.1:8000/v1", "VLLM_BASE_URL", None),
    ],
)
def test_local_servers_d690(name: str, url: str, env: str, conc: int | None) -> None:
    """D-690: each local server kind has its own shorthand, pinned to 127.0.0.1, speaking the OpenAI wire; keyless
    except oMLX's optional key (D-827)."""
    e = ep.get_endpoint(name)
    assert (e.base_url, e.base_url_env, e.server_max_concurrency) == (url, env, conc)
    assert e.local and e.server == name and e.api == "openai_chat" and e.host == "127.0.0.1"
    assert e.api_key_env == ("OMLX_API_KEY" if name == "omlx" else None)


def test_server_is_set_exactly_on_local_entries() -> None:
    for name, entry in ep.load_endpoints().items():
        assert (entry.server is not None) == entry.local, name
        assert entry.server is None or entry.server in ep.LOCAL_SERVERS, name


def test_remote_entries_are_https_and_keyed() -> None:
    for name, entry in ep.load_endpoints().items():
        if not entry.local:
            assert entry.base_url.startswith("https://"), name
            assert entry.api_key_env and entry.model_env, name


def test_openrouter_shorthands_share_key_and_base() -> None:
    reg = ep.load_endpoints()
    shared = {(reg[n].base_url, reg[n].api_key_env, reg[n].base_url_env) for n in ("openrouter", "gemini", "llama", "qwen", "glm")}
    assert len(shared) == 1
    assert {reg[n].model_env for n in ("gemini", "llama", "qwen", "glm")} == {
        "GEMINI_MODEL", "LLAMA_MODEL", "QWEN_MODEL", "GLM_MODEL"
    }


def test_registry_holds_names_not_values() -> None:
    text = (pathlib.Path(ep.__file__).parent / "endpoints.toml").read_text(encoding="utf-8")
    data = tomllib.loads(text)
    for entry in data["endpoints"].values():
        for key in ("base_url_env", "api_key_env", "model_env"):
            if key in entry:
                assert entry[key].isupper() and "sk-" not in entry[key]
    assert "model_id" not in text  # no default model ids (Q5)


@pytest.mark.parametrize(
    "url, host",
    [
        ("https://api.openai.com/v1", "api.openai.com"),
        ("http://127.0.0.1:8000/v1", "127.0.0.1"),
        ("http://[::1]:8000/v1", "::1"),
        ("http://localhost:11434/v1", "localhost"),
        ("HTTPS://Example.COM/v1", "example.com"),
    ],
)
def test_validate_ok(url: str, host: str) -> None:
    assert ep.validate_base_url(url) == host


@pytest.mark.parametrize(
    "url, code",
    [
        ("http://api.openai.com/v1", "endpoint.url.not_https"),
        ("http://192.168.1.5:8000/v1", "endpoint.url.not_https"),
        ("http://127.0.0.2:8000/v1", "endpoint.url.not_https"),
        ("https://x.example/v1?key=abc", "endpoint.url.query"),
        ("https://x.example/v1?", "endpoint.url.query"),
        ("https://x.example/v1#frag", "endpoint.url.fragment"),
        ("https://user:pw@x.example/v1", "endpoint.url.userinfo"),
        ("https://user@x.example/v1", "endpoint.url.userinfo"),
        ("ftp://x.example/v1", "endpoint.url.malformed"),
        ("https:///v1", "endpoint.url.malformed"),
        ("", "endpoint.url.malformed"),
        ("https://x.example/ v1", "endpoint.url.malformed"),
        ("https://x.example:notaport/v1", "endpoint.url.malformed"),
    ],
)
def test_validate_rejects(url: str, code: str) -> None:
    with pytest.raises(ep.EndpointError) as exc:
        ep.validate_base_url(url)
    assert exc.value.code == code


@pytest.mark.parametrize("host, lan", [
    ("10.1.2.3", True), ("172.16.0.9", True), ("172.31.255.1", True), ("192.168.1.20", True), ("100.64.0.1", True),
    ("100.127.255.254", True), ("fd12:3456::1", True), ("172.32.0.1", False), ("100.128.0.1", False), ("8.8.8.8", False),
    ("169.254.1.1", False), ("127.0.0.1", False), ("fe80::1", False), ("my-mac.local", False), ("10.0.0.1.nip.io", False),
    ("fd12:3456::1%en0", False), ("fd00::5%25eth0", False),  # a zone id names an interface of this host (LF nit)
])
def test_private_lan_hosts_are_literal_private_addresses(host: str, lan: bool) -> None:
    assert ep.is_private_lan_host(host) is lan


def test_http_on_a_lan_address_needs_the_opt_in() -> None:
    url = "http://192.168.1.20:1234/v1"
    with pytest.raises(ep.EndpointError) as exc:
        ep.validate_base_url(url)
    assert exc.value.code == "endpoint.url.not_https"
    assert ep.validate_base_url(url, allow_lan=True) == "192.168.1.20"
    assert ep.validate_base_url("http://[fd00::5]:8080/v1", allow_lan=True) == "fd00::5"
    with pytest.raises(ep.EndpointError):
        ep.validate_base_url("http://[fd00::5%25en0]:8080/v1", allow_lan=True)
    for public in ("http://8.8.8.8/v1", "http://lan-box.local:1234/v1"):
        with pytest.raises(ep.EndpointError):
            ep.validate_base_url(public, allow_lan=True)


def test_check_base_url_host_must_match_unless_custom() -> None:
    entry = ep.get_endpoint("openai")
    assert ep.check_base_url(entry, "https://api.openai.com/v1") is False
    with pytest.raises(ep.EndpointError) as exc:
        ep.check_base_url(entry, "https://proxy.example/v1")
    assert exc.value.code == "endpoint.url.host_mismatch"
    assert ep.check_base_url(entry, "https://proxy.example/v1", allow_custom=True) is True
    # the https rule is never waived by allow_custom
    with pytest.raises(ep.EndpointError):
        ep.check_base_url(entry, "http://proxy.example/v1", allow_custom=True)


def _doc(**entry: object) -> dict[str, object]:
    return {"version": 1, "endpoints": {"x": entry}}


@pytest.mark.parametrize(
    "doc, code",
    [
        ({"version": 2, "endpoints": {}}, "endpoint.registry.version"),
        ({"version": 1}, "endpoint.registry.empty"),
        (_doc(base_url="https://a.example/v1"), "endpoint.registry.api_key_env"),
        (_doc(base_url="https://a.example/v1", api_key_env="lower"), "endpoint.registry.env_name"),
        (_doc(base_url="https://a.example/v1", api_key_env="K", local=True), "endpoint.registry.local"),
        (_doc(base_url="http://127.0.0.1:1/v1", local="yes"), "endpoint.registry.local"),
        (_doc(base_url="http://127.0.0.1:1/v1", local=True, server="ollama", server_max_concurrency=0),
         "endpoint.registry.concurrency"),
        (_doc(base_url="http://127.0.0.1:1/v1", local=True), "endpoint.registry.server"),
        (_doc(base_url="http://127.0.0.1:1/v1", local=True, server="lmstudio2"), "endpoint.registry.server"),
        (_doc(base_url="https://a.example/v1", api_key_env="K", server="ollama"), "endpoint.registry.server"),
        (_doc(base_url="http://127.0.0.1:1/v1", local=True, server="vllm", api="anthropic_messages"),
         "endpoint.registry.local_api"),
        (_doc(base_url="http://127.0.0.1:1/v1", local=True, api_key="sk-live"), "endpoint.registry.key"),
        (_doc(base_url="http://a.example/v1", api_key_env="K"), "endpoint.url.not_https"),
        (_doc(local=True), "endpoint.registry.base_url"),
        (_doc(base_url="https://a.example/v1", api_key_env="K", api="grpc"), "endpoint.registry.api"),
    ],
)
def test_parse_registry_rejects(doc: dict[str, object], code: str) -> None:
    with pytest.raises(ep.EndpointError) as exc:
        ep.parse_registry(doc)
    assert exc.value.code == code


def test_unknown_endpoint() -> None:
    with pytest.raises(ep.EndpointError) as exc:
        ep.get_endpoint("nope")
    assert exc.value.code == "endpoint.unknown"


def test_capture_package_imports_only_stdlib_and_rfc8785() -> None:
    root = pathlib.Path(ep.__file__).parent
    allowed = {"rfc8785", "agentprov_capture", "__future__"}
    for path in root.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            for n in names:
                top = n.split(".")[0]
                assert top in allowed or top in __import__("sys").stdlib_module_names, (path.name, n)
                assert top != "agentprov", path.name
