"""The recording HTTP transport (D.10.5; AD-09; K.5.7(8)).

It sits between the SDK client of the LLM element and the real (or scripted) transport. For every wire exchange it
hands the exact request body, the HTTP status and the exact response body to an observer, and it **never modifies a
request or a response**: the request object it receives is passed on unchanged, and the response object the inner
transport returns is returned unchanged (its body is read into memory first, which the SDK would do anyway for a
non-streaming call). Retries made by the SDK itself are separate wire exchanges and are recorded separately.

What is recorded about bodies: the request body as built by the SDK (``Request.read()``), and the response *entity*
body after content decoding (``Response.read()``, i.e. what the SDK parses); content-encoding framing (gzip) is not
recorded. Headers are not recorded (``capture/0.1`` has no header field); see ``gateway.WireRecorder``.

If the observer raises before the request is sent (for example the capture redactor's fail-closed scan), the request
is **not** sent: an exchange is never made unrecorded.

``AsyncRecordingTransport`` is the async twin, for SDK clients that send through an async transport (AgentDojo's stock
``AnthropicLLM`` uses ``AsyncAnthropic``; D-656). Same observer, same guarantees; the observer is called synchronously
inside the event loop. A streamed (``text/event-stream``) response is read to its end before it is returned, so the
SDK parses the same bytes, all at once; the stock element waits for the final message anyway, so the pipeline sees no
difference (design note §1).
"""

from __future__ import annotations

from types import ModuleType
from typing import Any, Protocol

from agentprov_backend._http import sdk_httpx

__all__ = [
    "AsyncRecordingTransport",
    "RecordingTransport",
    "WireObserver",
    "async_recording_transport_class",
    "default_async_inner_transport",
    "default_inner_transport",
    "egress_proxy",
    "recording_transport_class",
]

#: D-664 (agreed with the D-656 session): the loopback CONNECT proxy T0 runs when outbound connections are contained.
EGRESS_PROXY_ENV = "AGENTPROV_EGRESS_PROXY"
_LOOPBACK = ("127.0.0.1", "localhost", "::1")


class WireObserver(Protocol):
    def on_request(self, request: Any, body: bytes) -> object: ...

    def on_response(self, token: object, status: int, headers: Any, body: bytes) -> None: ...

    def on_error(self, token: object, exc: BaseException) -> None: ...


_classes: dict[str, type] = {}
_async_classes: dict[str, type] = {}


def recording_transport_class(module: ModuleType | None = None) -> type:
    """The recording transport class for an httpx-family module (default: the SDK's, ``_http.sdk_httpx()``)."""
    mod = module or sdk_httpx()
    key = mod.__name__
    cls = _classes.get(key)
    if cls is not None:
        return cls

    class _RecordingTransport(mod.BaseTransport):  # type: ignore[name-defined, misc]
        """Records every exchange through ``observer``; delegates to ``inner`` unchanged."""

        def __init__(self, inner: Any, observer: WireObserver) -> None:
            self._inner = inner
            self._observer = observer

        @property
        def inner(self) -> Any:
            return self._inner

        def handle_request(self, request: Any) -> Any:
            body = request.read()
            token = self._observer.on_request(request, bytes(body))
            try:
                response = self._inner.handle_request(request)
                data = response.read()
            except BaseException as exc:
                self._observer.on_error(token, exc)
                raise
            self._observer.on_response(token, response.status_code, response.headers, bytes(data))
            return response

        def close(self) -> None:
            self._inner.close()

    _RecordingTransport.__name__ = _RecordingTransport.__qualname__ = "RecordingTransport"
    _classes[key] = _RecordingTransport
    return _RecordingTransport


def RecordingTransport(inner: Any, observer: WireObserver, *, module: ModuleType | None = None) -> Any:  # noqa: N802
    """Construct a recording transport around ``inner`` (a transport of the same httpx-family module)."""
    return recording_transport_class(module)(inner, observer)


def egress_proxy() -> str | None:
    """The egress proxy URL from ``AGENTPROV_EGRESS_PROXY``, or ``None`` when it is unset or empty (no change).

    A transport passed to an SDK client no longer reads ``HTTPS_PROXY``, so the inner transports are given the proxy
    explicitly. The value must be exactly ``http://<loopback>:<port>`` (host ``127.0.0.1``, ``localhost`` or ``[::1]``,
    port 1-65535, no userinfo, query or fragment, path empty or ``/``). Anything else raises ``ValueError``: a
    malformed value never falls back to a direct connection."""
    import os
    from urllib.parse import urlsplit

    value = os.environ.get(EGRESS_PROXY_ENV)
    if not value:
        return None
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError:
        raise ValueError(f"{EGRESS_PROXY_ENV} is not a URL") from None
    if (parts.scheme != "http" or parts.hostname not in _LOOPBACK or port is None or not 1 <= port <= 65535
            or parts.username is not None or parts.password is not None or "@" in parts.netloc
            or parts.path not in ("", "/") or parts.query or parts.fragment or "?" in value or "#" in value):
        raise ValueError(f"{EGRESS_PROXY_ENV} must be http://<loopback>:<port>")
    return value


def async_recording_transport_class(module: ModuleType) -> type:
    """The async recording transport class for an httpx-family module (the SDK's: ``_http.anthropic_httpx()``)."""
    key = module.__name__
    cls = _async_classes.get(key)
    if cls is not None:
        return cls

    class _AsyncRecordingTransport(module.AsyncBaseTransport):  # type: ignore[name-defined, misc]
        """Records every exchange through ``observer``; delegates to ``inner`` unchanged."""

        def __init__(self, inner: Any, observer: WireObserver) -> None:
            self._inner = inner
            self._observer = observer

        @property
        def inner(self) -> Any:
            return self._inner

        async def handle_async_request(self, request: Any) -> Any:
            body = await request.aread()
            token = self._observer.on_request(request, bytes(body))
            try:
                response = await self._inner.handle_async_request(request)
                data = await response.aread()
            except BaseException as exc:
                self._observer.on_error(token, exc)
                raise
            self._observer.on_response(token, response.status_code, response.headers, bytes(data))
            return response

        async def aclose(self) -> None:
            await self._inner.aclose()

    _AsyncRecordingTransport.__name__ = _AsyncRecordingTransport.__qualname__ = "AsyncRecordingTransport"
    _async_classes[key] = _AsyncRecordingTransport
    return _AsyncRecordingTransport


def AsyncRecordingTransport(inner: Any, observer: WireObserver, *, module: ModuleType) -> Any:  # noqa: N802
    """Construct an async recording transport around ``inner`` (an async transport of the same module)."""
    return async_recording_transport_class(module)(inner, observer)


def default_async_inner_transport(module: ModuleType) -> Any:
    """The real async HTTP transport with the settings the ``anthropic`` SDK's default client would build
    (``anthropic._base_client._DefaultAsyncHttpxClient`` in 1.11.0: ``DEFAULT_CONNECTION_LIMITS``, certificate
    verification on, and TCP keep-alive socket options). Passing a transport replaces the one the client would have
    built itself, so these settings are reproduced here (as :func:`default_inner_transport` does for the OpenAI SDK).

    One deliberate difference (D-656, risk R-1, confirmed by the live pilot's Part B): **no keep-alive connections**.
    AgentDojo's ``AnthropicLLM`` runs every query under a fresh ``asyncio.run`` while it keeps one ``AsyncAnthropic``,
    so a pooled connection opened in a closed event loop would be reused by the next query and fail ("Event loop is
    closed"), costing a failed attempt and an SDK retry per call. Without keep-alive each request opens its own
    connection; no request or response changes. Declared on ``agentdojo.recording_transport@1``
    (``params.inner_keepalive = 0``).
    Environment proxies are not mounted (the worker's environment, G.6.3, carries none); the D-664 egress proxy is
    passed explicitly when :func:`egress_proxy` names one."""
    import socket
    import sys

    kwargs: dict[str, Any] = {}
    try:
        from anthropic._constants import DEFAULT_CONNECTION_LIMITS

        kwargs["limits"] = module.Limits(max_connections=DEFAULT_CONNECTION_LIMITS.max_connections,
                                         max_keepalive_connections=0)
    except ImportError:  # pragma: no cover - every supported SDK has it
        kwargs["limits"] = module.Limits(max_keepalive_connections=0)
    options: list[tuple[int, int, int | bool]] = [(socket.SOL_SOCKET, socket.SO_KEEPALIVE, True)]
    keepintvl = getattr(socket, "TCP_KEEPINTVL", None)
    if keepintvl is not None:
        options.append((socket.IPPROTO_TCP, keepintvl, 60))
    elif sys.platform == "darwin":
        options.append((socket.IPPROTO_TCP, getattr(socket, "TCP_KEEPALIVE", 0x10), 60))
    keepcnt = getattr(socket, "TCP_KEEPCNT", None)
    if keepcnt is not None:
        options.append((socket.IPPROTO_TCP, keepcnt, 5))
    keepidle = getattr(socket, "TCP_KEEPIDLE", None)
    if keepidle is not None:
        options.append((socket.IPPROTO_TCP, keepidle, 60))
    kwargs["socket_options"] = options
    proxy = egress_proxy()
    if proxy is not None:  # D-664: the contained worker reaches the endpoint only through T0's CONNECT proxy
        kwargs["proxy"] = proxy
    return module.AsyncHTTPTransport(**kwargs)


def default_inner_transport(module: ModuleType | None = None) -> Any:
    """The real HTTP transport with the settings the SDK's default client would use (``DEFAULT_CONNECTION_LIMITS``,
    certificate verification on, HTTP/1.1). Passing a transport to an SDK client replaces the one the client would
    have built itself, so these settings are reproduced here. Under D-664's egress proxy (``AGENTPROV_EGRESS_PROXY``
    set by T0, validated by :func:`egress_proxy`) the transport tunnels through it, because a client given its own
    transport ignores ``HTTPS_PROXY``; without the variable (scripted runs, loopback endpoints) there is no proxy."""
    mod = module or sdk_httpx()
    kwargs: dict[str, Any] = {}
    try:
        from openai._constants import DEFAULT_CONNECTION_LIMITS

        kwargs["limits"] = DEFAULT_CONNECTION_LIMITS
    except ImportError:  # pragma: no cover - every supported SDK has it
        pass
    proxy = egress_proxy()
    if proxy is not None:
        kwargs["proxy"] = proxy
    return mod.HTTPTransport(**kwargs)
