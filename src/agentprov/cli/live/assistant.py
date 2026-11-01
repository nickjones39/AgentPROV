"""The Assistant's model call (D-1010): one chat request to one endpoint of the registry, for ``agentprov assist``.

The desktop app's Help › Assistant page runs ``agentprov assist`` for every message, so the GUI process never opens a
connection and never holds a key (S11, D-396). This module is the only place the request is made.

**Network.** The endpoint's registry base URL only (never a base URL from ``.env``): an API provider over HTTPS with the
default TLS context (certificate and host name verified), or a local server on a loopback address (its registry URL, or
the ``endpoints.<name>.base_url`` setting when that is loopback). ``http.client``: no proxy, no redirect (anything but
HTTP 200 is a failure), a 120 s timeout, the body bounded at 4 MiB. The key travels only in its header; it is
registered for redaction by the caller before the request.

**Wire formats.** The registry's ``api``: ``openai_chat`` (``POST {base}/chat/completions``) or ``anthropic_messages``
(``POST {base}/v1/messages``). No tools, no streaming: one text answer.

**Untrusted data.** The answer is parsed by ``agentprov.ingest`` (strict JSON under ``IngestLimits``) and only the
reply text and the token counts are kept. The reply is model output: the caller shows it as plain text and never runs
or follows it. No response text is quoted in an error.
"""

from __future__ import annotations

import http.client
import json
import re
import ssl
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final
from urllib.parse import SplitResult, urlsplit

from agentprov.errors import AgentProvError, IngestError

__all__ = ["LOCAL_SERVERS", "MAX_REPLY_CHARS", "AssistantError", "Reply", "ServedModel", "Target", "chat",
           "list_models", "local_target", "target"]

MAX_BODY_BYTES: Final = 4 * 1024 * 1024
MAX_REPLY_CHARS: Final = 60_000
MAX_OUTPUT_TOKENS: Final = 2048
TIMEOUT_S: Final = 120.0
ANTHROPIC_VERSION: Final = "2023-06-01"
_LOOPBACK: Final = ("127.0.0.1", "::1", "localhost")
MAX_MODELS: Final = 2000
#: Local model servers the Assistant knows by name (``--server``; Settings › Assistant): the default base URL, and the
#: registry endpoint whose optional key it shares (D-827), if any. Strata has no fixed default port: its URL is given.
LOCAL_SERVERS: Final[dict[str, tuple[str | None, str | None]]] = {
    "omlx": ("http://127.0.0.1:8000/v1", "omlx"),
    "mlx_lm": ("http://127.0.0.1:8080/v1", "mlx_lm"),
    "lmstudio": ("http://127.0.0.1:1234/v1", "lmstudio"),
    "ollama": ("http://127.0.0.1:11434/v1", "ollama"),
    "splash": ("http://127.0.0.1:8003/v1", None),
    "strata": (None, None),
    "llamacpp": ("http://127.0.0.1:8080/v1", "llamacpp"),
    "vllm": ("http://127.0.0.1:8000/v1", "vllm"),
    "other": (None, None),
}
_MODEL_ID: Final = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.:/@+-]{0,199}")

Connection = Callable[[str, int, float, bool], http.client.HTTPConnection]


class AssistantError(AgentProvError):
    """A model-call condition: exit 3 (unreachable, refused, malformed) or 2 (usage). No response text is quoted."""

    code = "assist.model"
    exit_code = 3


def _fail(code: str, message: str, exit_code: int = 3) -> AssistantError:
    return AssistantError(message, code=f"assist.model.{code}", exit_code=exit_code)


@dataclass(frozen=True, slots=True)
class Target:
    endpoint: str
    api: str
    local: bool
    https: bool
    host: str
    port: int
    base_path: str
    key_variable: str | None


@dataclass(frozen=True, slots=True)
class Reply:
    text: str
    input_tokens: int | None
    output_tokens: int | None
    truncated: bool


def target(endpoint: str, local_base_url: str | None = None) -> Target:
    """Where ``endpoint`` is reached: the registry's base URL, or for a local server ``local_base_url`` (the
    ``endpoints.<name>.base_url`` setting) when it is on loopback. A local server is reached on loopback only."""
    from agentprov_capture.endpoints import EndpointError, get_endpoint

    try:
        entry = get_endpoint(endpoint)
    except EndpointError:
        raise _fail("unknown", f"unknown endpoint {endpoint!r}", exit_code=2) from None
    url = local_base_url if entry.local and local_base_url else entry.base_url
    parts = urlsplit(url)
    host = parts.hostname or ""
    if entry.local:
        if parts.scheme not in ("http", "https") or host not in _LOOPBACK:
            raise _fail("not_loopback", "the Assistant reaches a local server on a loopback address only", exit_code=2)
    elif parts.scheme != "https" or not host:
        raise _fail("url", "the registry base URL is not https")
    https = parts.scheme == "https"
    return Target(endpoint, entry.api, entry.local, https, host, _port(parts, https),
                  parts.path.rstrip("/"), entry.api_key_env if isinstance(entry.api_key_env, str) else None)


def _port(parts: SplitResult, https: bool) -> int:
    """The URL's port, or the scheme's default; a port that is not 1..65535 is a usage error, not a crash (UC-31)."""
    try:
        port = parts.port
    except ValueError:
        port = 0
    if port == 0:
        raise _fail("url", "the base URL's port is not a number from 1 to 65535", exit_code=2)
    return port or (443 if https else 80)


def local_target(base_url: str, endpoint: str | None = None) -> Target:
    """An OpenAI-compatible server at ``base_url`` on loopback (``--base-url``); ``endpoint``, a local entry of the
    registry, lends its optional key variable (oMLX's ``OMLX_API_KEY``)."""
    parts = urlsplit(base_url)
    host = parts.hostname or ""
    if parts.scheme not in ("http", "https") or host not in _LOOPBACK or parts.username or parts.password \
            or parts.query or parts.fragment:
        raise _fail("not_loopback", "--base-url is an http(s) URL on a loopback address (127.0.0.1, ::1, localhost)",
                    exit_code=2)
    variable = None
    if endpoint is not None:
        entry = target(endpoint)
        if not entry.local:
            raise _fail("not_local", f"{endpoint} is an API provider; --base-url is for a local server", exit_code=2)
        variable = entry.key_variable
    https = parts.scheme == "https"
    return Target(endpoint or "local", "openai_chat", True, https, host, _port(parts, https),
                  parts.path.rstrip("/"), variable)


def _connect(host: str, port: int, timeout: float, https: bool) -> http.client.HTTPConnection:
    if https:
        return http.client.HTTPSConnection(host, port, timeout=timeout, context=ssl.create_default_context())
    return http.client.HTTPConnection(host, port, timeout=timeout)


def _request(t: Target, model: str, system: str, messages: Sequence[Mapping[str, str]],
             key: str | None) -> tuple[str, dict[str, str], bytes]:
    """``(path, headers, body)`` for the target's wire format."""
    headers = {"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "agentprov-assist"}
    turns = [{"role": m["role"], "content": m["content"]} for m in messages]
    if t.api == "anthropic_messages":
        if key:
            headers["x-api-key"] = key
        headers["anthropic-version"] = ANTHROPIC_VERSION
        body: dict[str, Any] = {"model": model, "max_tokens": MAX_OUTPUT_TOKENS, "system": system, "messages": turns}
        return f"{t.base_path}/v1/messages", headers, json.dumps(body).encode("utf-8")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    body = {"model": model, "messages": [{"role": "system", "content": system}, *turns]}
    return f"{t.base_path}/chat/completions", headers, json.dumps(body).encode("utf-8")


def _count(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _parse(api: str, doc: Any) -> tuple[str, int | None, int | None]:
    """The reply text and the token counts; a missing or ill-typed member is a malformed answer."""
    if not isinstance(doc, Mapping):
        raise _fail("malformed", "the answer is not a JSON object")
    raw_usage = doc.get("usage")
    usage: Mapping[str, Any] = raw_usage if isinstance(raw_usage, Mapping) else {}
    if api == "anthropic_messages":
        blocks = doc.get("content")
        if not isinstance(blocks, list):
            raise _fail("malformed", "the answer has no content")
        text = "".join(b["text"] for b in blocks
                       if isinstance(b, Mapping) and b.get("type") == "text" and isinstance(b.get("text"), str))
        return text, _count(usage.get("input_tokens")), _count(usage.get("output_tokens"))
    choices = doc.get("choices")
    first = choices[0] if isinstance(choices, list) and choices else None
    message = first.get("message") if isinstance(first, Mapping) else None
    content = message.get("content") if isinstance(message, Mapping) else None
    if not isinstance(content, str):
        raise _fail("malformed", "the answer has no message content")
    return content, _count(usage.get("prompt_tokens")), _count(usage.get("completion_tokens"))


def chat(t: Target, model: str, system: str, messages: Sequence[Mapping[str, str]], key: str | None, *,
         connect: Connection = _connect) -> Reply:
    """Send one chat request and return the model's text answer (bounded at :data:`MAX_REPLY_CHARS`)."""
    from agentprov.ingest.limits import IngestLimits
    from agentprov.ingest.loaders import strict_json_loads

    path, headers, payload = _request(t, model, system, messages, key)
    conn = connect(t.host, t.port, TIMEOUT_S, t.https)
    try:
        try:
            conn.request("POST", path or "/", body=payload, headers=headers)
            resp = conn.getresponse()
            status = resp.status
            body = resp.read(MAX_BODY_BYTES + 1)
        except (OSError, http.client.HTTPException, ValueError):
            raise _fail("unreachable", f"the {t.endpoint} endpoint did not answer") from None
    finally:
        conn.close()
    if len(body) > MAX_BODY_BYTES:
        raise _fail("too_large", "the answer is larger than the limit")
    if status in (401, 403):
        hint = f" (is {t.key_variable} set? agentprov keys set {t.key_variable})" if t.key_variable else ""
        raise _fail("refused", f"the {t.endpoint} endpoint refused the key: HTTP {status}{hint}")
    if status != 200:  # a redirect is never followed; the body is never quoted
        raise _fail("http_status", f"the {t.endpoint} endpoint answered HTTP {status}")
    try:
        doc = strict_json_loads(bytes(body), IngestLimits().replace(max_json_bytes=MAX_BODY_BYTES))
    except IngestError:
        raise _fail("malformed", "the answer is not valid JSON") from None
    text, tokens_in, tokens_out = _parse(t.api, doc)
    truncated = len(text) > MAX_REPLY_CHARS
    return Reply(text[:MAX_REPLY_CHARS], tokens_in, tokens_out, truncated)


@dataclass(frozen=True, slots=True)
class ServedModel:
    id: str
    loaded: bool | None  # None: the server does not say


def _get_json(t: Target, path: str, key: str | None, connect: Connection) -> Any:
    """One GET on the local server; ``None`` when it does not answer 200 with JSON (a hint that is missing)."""
    from agentprov.ingest.limits import IngestLimits
    from agentprov.ingest.loaders import strict_json_loads

    headers = {"Accept": "application/json", "User-Agent": "agentprov-assist"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    conn = connect(t.host, t.port, 10.0, t.https)
    try:
        try:
            conn.request("GET", path, headers=headers)
            resp = conn.getresponse()
            status, body = resp.status, resp.read(MAX_BODY_BYTES + 1)
        except (OSError, http.client.HTTPException, ValueError):
            return None
    finally:
        conn.close()
    if status != 200 or len(body) > MAX_BODY_BYTES:
        return None
    try:
        return strict_json_loads(bytes(body), IngestLimits().replace(max_json_bytes=MAX_BODY_BYTES))
    except IngestError:
        return None


def _loaded(t: Target, server: str | None, key: str | None, connect: Connection) -> set[str] | None:
    """The ids the server reports as loaded, where it says (Splash ``/status``, Ollama ``/api/ps``, LM Studio
    ``/api/v0/models``); ``None`` when it does not."""
    root = t.base_path.removesuffix("/v1")
    if server == "splash":
        doc = _get_json(t, f"{root}/status", key, connect)
        active = doc.get("active_model") if isinstance(doc, Mapping) else None
        return {active} if isinstance(active, str) else None
    if server == "ollama":
        doc = _get_json(t, f"{root}/api/ps", key, connect)
        rows = doc.get("models") if isinstance(doc, Mapping) else None
        if not isinstance(rows, list):
            return None
        return {str(r.get("name") or r.get("model")) for r in rows if isinstance(r, Mapping)}
    if server == "lmstudio":
        doc = _get_json(t, f"{root}/api/v0/models", key, connect)
        rows = doc.get("data") if isinstance(doc, Mapping) else None
        if not isinstance(rows, list):
            return None
        return {str(r.get("id")) for r in rows if isinstance(r, Mapping) and r.get("state") == "loaded"}
    return None


def list_models(t: Target, key: str | None, server: str | None = None, *,
                connect: Connection = _connect) -> list[ServedModel]:
    """The models a local server serves (``GET {base}/models``), the loaded ones first where the server says which.
    Ids are labels: one that is not a plain model id is dropped."""
    doc = _get_json(t, f"{t.base_path}/models", key, connect)
    rows = doc.get("data") if isinstance(doc, Mapping) else None
    if not isinstance(rows, list):
        raise _fail("unreachable", f"no model list at {t.host}:{t.port}{t.base_path}/models")
    ids = [r["id"] for r in rows[:MAX_MODELS]
           if isinstance(r, Mapping) and isinstance(r.get("id"), str) and _MODEL_ID.fullmatch(r["id"])]
    loaded = _loaded(t, server, key, connect)
    models = [ServedModel(i, None if loaded is None else i in loaded) for i in dict.fromkeys(ids)]
    return sorted(models, key=lambda m: not m.loaded)
