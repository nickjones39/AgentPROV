"""The endpoint registry: ``endpoints.toml`` as validated data (MN M.1.10 item 2; N.2.1, N.2.1a; G.9.2).

Stdlib only (``tomllib``; Python >= 3.12). The registry names environment variables, never values. Rules enforced here:

* a base URL is https, except loopback (``127.0.0.1``, ``[::1]``, ``localhost``);
* a base URL has no userinfo, query or fragment (a key could hide in them; G.6.4);
* a ``local`` entry is loopback and names its ``server`` kind (D-690). Its ``api_key_env`` is optional: a server set up
  with an API key (oMLX's, D-827) gets it as a bearer header when the key is set, and none otherwise. A non-local entry
  names ``api_key_env`` and has no ``server``;
* a custom base URL's host must equal the registered host unless the caller passes ``allow_custom=True``
  (the CLI's ``--allow-custom-endpoint``, recorded in the manifest);
* ``api`` names the wire format the endpoint speaks: ``openai_chat`` (the default; OpenAI-compatible chat completions)
  or ``anthropic_messages`` (the Anthropic Messages API; D-656).
"""

from __future__ import annotations

import ipaddress
import re
import tomllib
from dataclasses import dataclass
from importlib import resources
from typing import Any, Final
from urllib.parse import urlsplit

__all__ = [
    "API_KINDS",
    "LOCAL_SERVERS",
    "LOOPBACK_HOSTS",
    "Endpoint",
    "EndpointError",
    "check_base_url",
    "get_endpoint",
    "is_loopback_host",
    "is_private_lan_host",
    "load_endpoints",
    "parse_registry",
    "validate_base_url",
]

#: The loopback hosts of G.9.2, as ``urllib.parse`` reports them (brackets removed from the IPv6 literal).
LOOPBACK_HOSTS: Final = frozenset({"127.0.0.1", "::1", "localhost"})

#: The wire formats an endpoint may speak (``api``); the first is the default.
API_KINDS: Final = ("openai_chat", "anthropic_messages")
#: The local server kinds of D-690. ``server`` selects the discovery and fingerprint probes of ``agentprov models``.
LOCAL_SERVERS: Final = frozenset({"ollama", "omlx", "lmstudio", "mlx_lm", "llamacpp", "vllm"})

_ENV_NAME: Final = re.compile(r"[A-Z][A-Z0-9_]{0,63}")
_ENDPOINT_NAME: Final = re.compile(r"[a-z][a-z0-9_-]{0,31}")
_HEADER_NAME: Final = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
_ENTRY_KEYS: Final = frozenset(
    {
        "base_url",
        "base_url_env",
        "api_key_env",
        "model_env",
        "local",
        "server_max_concurrency",
        "request_headers",
        "response_headers",
        "api",
        "server",
    }
)


class EndpointError(ValueError):
    """A registry or base-URL violation. ``code`` is stable; messages never carry values from the environment."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


@dataclass(frozen=True, slots=True)
class Endpoint:
    """One registry entry. ``*_env`` fields are environment-variable NAMES (or None), never values."""

    name: str
    base_url: str
    host: str
    base_url_env: str | None
    api_key_env: str | None
    model_env: str | None
    local: bool
    server_max_concurrency: int | None
    #: header NAMES (lower case) whose values wire-capture redaction may record besides the global allowlist
    #: (``redact_allowlist.toml``): for example an API-version header (request) or a request-id header (response).
    #: The hard denylist of G.6.4 wins over them.
    request_headers: tuple[str, ...] = ()
    response_headers: tuple[str, ...] = ()
    #: the wire format (one of :data:`API_KINDS`): which LLM element and recorder the harness uses (D-656)
    api: str = API_KINDS[0]
    #: the local server kind (one of :data:`LOCAL_SERVERS`) for a ``local`` entry; ``None`` for a remote one (D-690)
    server: str | None = None


def is_loopback_host(host: str) -> bool:
    return host.lower() in LOOPBACK_HOSTS


#: The private ranges a LAN endpoint may use (D-698): RFC 1918, the shared address space of RFC 6598 (CGNAT, used by
#: Tailscale-style overlays), and IPv6 unique local addresses. Link-local, loopback and every public range are not.
LAN_NETWORKS: Final = tuple(ipaddress.ip_network(n) for n in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10", "fc00::/7"))


def is_private_lan_host(host: str) -> bool:
    """A literal IP address in :data:`LAN_NETWORKS` (never a name: a name can be made to resolve anywhere), without an
    IPv6 zone id (``%en0`` names an interface of this host, not a LAN peer)."""
    if "%" in host:
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return any(address in net for net in LAN_NETWORKS if net.version == address.version)


def validate_base_url(base_url: str, *, allow_lan: bool = False) -> str:
    """Check the G.9.2 / G.6.4 rules on ``base_url`` and return its host (lower case).

    http is allowed on a loopback host, and, with ``allow_lan`` (the CLI's ``--allow-lan-endpoint``, D-698), on a
    literal private address. Raises :class:`EndpointError` (``endpoint.url.*``). Nothing is fetched or resolved.
    """
    if not isinstance(base_url, str) or not base_url or any(ord(c) < 0x21 or ord(c) == 0x7F for c in base_url):
        raise EndpointError("endpoint.url.malformed", "base URL is empty or contains whitespace or control characters")
    try:
        parts = urlsplit(base_url)
        host = parts.hostname
        parts.port  # noqa: B018 - raises ValueError on a bad port
    except ValueError:
        raise EndpointError("endpoint.url.malformed", "base URL cannot be parsed") from None
    if parts.scheme not in ("http", "https") or not host:
        raise EndpointError("endpoint.url.malformed", "base URL needs an http(s) scheme and a host")
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        raise EndpointError("endpoint.url.userinfo", "base URL must not carry userinfo")
    if parts.query or "?" in base_url:
        raise EndpointError("endpoint.url.query", "base URL must not carry a query string")
    if parts.fragment or "#" in base_url:
        raise EndpointError("endpoint.url.fragment", "base URL must not carry a fragment")
    host = host.lower()
    if parts.scheme != "https" and not is_loopback_host(host) and not (allow_lan and is_private_lan_host(host)):
        raise EndpointError("endpoint.url.not_https", "base URL must be https unless the host is loopback")
    return host


def check_base_url(endpoint: Endpoint, base_url: str, *, allow_custom: bool = False) -> bool:
    """Validate a base URL given for ``endpoint`` (e.g. from its ``base_url_env``). Returns True when it is a custom
    endpoint (its host differs from the registered one), which the caller must record in the manifest.

    The https/loopback/userinfo/query rules always apply. A host mismatch raises ``endpoint.url.host_mismatch``
    unless ``allow_custom`` (the CLI's ``--allow-custom-endpoint``, R-39).
    """
    host = validate_base_url(base_url)
    if host == endpoint.host:
        return False
    if not allow_custom:
        raise EndpointError("endpoint.url.host_mismatch", f"host does not match the registered host of {endpoint.name!r}")
    return True


def _opt_env(entry: dict[str, Any], key: str, name: str) -> str | None:
    value = entry.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not _ENV_NAME.fullmatch(value):
        raise EndpointError("endpoint.registry.env_name", f"endpoint {name!r}: {key} must be an upper-case variable name")
    return value


def _opt_headers(entry: dict[str, Any], key: str, name: str) -> tuple[str, ...]:
    value = entry.get(key, [])
    if not isinstance(value, list) or not all(isinstance(h, str) and _HEADER_NAME.fullmatch(h) for h in value):
        raise EndpointError("endpoint.registry.header", f"endpoint {name!r}: {key} must be a list of lower-case header names")
    return tuple(sorted(set(value)))


def parse_registry(data: dict[str, Any]) -> dict[str, Endpoint]:
    """Validate a parsed ``endpoints.toml`` document and return the entries by name, sorted."""
    if data.get("version") != 1:
        raise EndpointError("endpoint.registry.version", "unsupported registry version")
    entries = data.get("endpoints")
    if not isinstance(entries, dict) or not entries:
        raise EndpointError("endpoint.registry.empty", "registry has no [endpoints.*] tables")
    out: dict[str, Endpoint] = {}
    for name in sorted(entries):
        entry = entries[name]
        if not _ENDPOINT_NAME.fullmatch(name) or not isinstance(entry, dict):
            raise EndpointError("endpoint.registry.name", "bad endpoint name or entry")
        unknown = set(entry) - _ENTRY_KEYS
        if unknown:
            raise EndpointError("endpoint.registry.key", f"endpoint {name!r}: unknown key {sorted(unknown)[0]!r}")
        base_url = entry.get("base_url")
        if not isinstance(base_url, str):
            raise EndpointError("endpoint.registry.base_url", f"endpoint {name!r}: base_url is required")
        host = validate_base_url(base_url)
        local = entry.get("local", False)
        if not isinstance(local, bool):
            raise EndpointError("endpoint.registry.local", f"endpoint {name!r}: local must be a boolean")
        if local and not is_loopback_host(host):
            raise EndpointError("endpoint.registry.local", f"endpoint {name!r}: a local entry must be loopback")
        api_key_env = _opt_env(entry, "api_key_env", name)
        if not local and api_key_env is None:
            raise EndpointError("endpoint.registry.api_key_env", f"endpoint {name!r}: api_key_env is required")
        server = entry.get("server")
        if local and (not isinstance(server, str) or server not in LOCAL_SERVERS):
            raise EndpointError("endpoint.registry.server", f"endpoint {name!r}: a local entry needs server, one of "
                                f"{sorted(LOCAL_SERVERS)}")
        if not local and server is not None:
            raise EndpointError("endpoint.registry.server", f"endpoint {name!r}: server belongs to local entries")
        conc = entry.get("server_max_concurrency")
        if conc is not None and (isinstance(conc, bool) or not isinstance(conc, int) or conc < 1):
            raise EndpointError(
                "endpoint.registry.concurrency", f"endpoint {name!r}: server_max_concurrency must be an integer >= 1"
            )
        api = entry.get("api", API_KINDS[0])
        if api not in API_KINDS:
            raise EndpointError("endpoint.registry.api", f"endpoint {name!r}: api must be one of {list(API_KINDS)}")
        if local and api != API_KINDS[0]:  # every local server kind of D-690 speaks the OpenAI chat wire
            raise EndpointError("endpoint.registry.local_api", f"endpoint {name!r}: a local entry speaks {API_KINDS[0]}")
        out[name] = Endpoint(
            name=name,
            base_url=base_url,
            host=host,
            base_url_env=_opt_env(entry, "base_url_env", name),
            api_key_env=api_key_env,
            model_env=_opt_env(entry, "model_env", name),
            local=local,
            server_max_concurrency=conc,
            request_headers=_opt_headers(entry, "request_headers", name),
            response_headers=_opt_headers(entry, "response_headers", name),
            api=api,
            server=server,
        )
    return out


def load_endpoints() -> dict[str, Endpoint]:
    """Load and validate the packaged ``endpoints.toml`` (read through ``importlib.resources``)."""
    raw = resources.files("agentprov_capture").joinpath("endpoints.toml").read_bytes()
    return parse_registry(tomllib.loads(raw.decode("utf-8")))


def get_endpoint(name: str) -> Endpoint:
    """The registry entry ``name`` (``EndpointError("endpoint.unknown")`` if absent)."""
    registry = load_endpoints()
    try:
        return registry[name]
    except KeyError:
        raise EndpointError("endpoint.unknown", f"unknown endpoint shorthand; known: {sorted(registry)}") from None
