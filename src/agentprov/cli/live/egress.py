"""The T0 egress proxy of real-model runs (D-664; G.4.10, G.6.3; layer L7).

Under ``--containment sandbox-exec`` the T2 profile (:mod:`agentprov.cli.live.sandbox`) denies every outbound connection
except to two loopback ports given as parameters. When the selected endpoint is remote, one of them is this proxy's port,
and the proxy is the only way out of the sandbox:

* it accepts ``CONNECT host:port`` only, for the exact ``(host, port)`` pairs of the run's allowlist (the selected
  endpoint's base URL host and port, after ``check_base_url``; the Inspect judges' endpoints too) other than a forward
  pair, and answers everything else with ``403`` (a pair not on the list) or ``405`` (any other method, and CONNECT to a
  forward pair, so the forward rules below are a boundary and not a convention, LF-2);
* for the run's LAN model server only (D-698: ``--allow-lan-endpoint`` with an ``http://`` base URL on a literal private
  address), it also forwards plain-HTTP requests in absolute form (``GET``, ``POST``, ``HEAD``, ``OPTIONS``) to that
  exact pair: the request line becomes origin form, ``Host`` is regenerated from the pair (RFC 9112 3.2.2),
  ``Connection: close`` replaces the hop-by-hop headers, ``Proxy-*`` headers are dropped, and everything else passes
  through as bytes. The body is exactly the ``Content-Length`` bytes
  (at most 64 MiB; ``Transfer-Encoding`` is refused) and nothing after it is ever passed: one request per connection.
  No other plain-HTTP request is ever forwarded;
* it tunnels the bytes both ways without reading them: TLS is end to end between the worker and the endpoint, nothing
  is decrypted, nothing is recorded but the counts;
* it is bounded: a request head of at most 8 KiB read within 10 s, at most 64 concurrent tunnels, a connect timeout
  of 30 s;
* it keeps counts only, and never a string the worker chose (R1-7, rebuild-window review): tunnels and forwards per
  allowed pair (the pairs T0 itself put on the allowlist), refused attempts per closed kind (``not_allowed``,
  ``allowed_host_other_port``, ``method``, ``malformed``, ``oversize``, ``busy``) and the number of distinct refused
  targets. Distinctness is computed in memory with a keyed digest whose key is random per proxy and never leaves the
  process, so nothing written can confirm a guessed target. A contained T2 can therefore not use a CONNECT target to
  smuggle a value (a planted key) past T0's fail-closed secret scan into ``corpus.json``.

The proxy runs in T0 (the parent process), on an asyncio loop in a daemon thread bound to ``127.0.0.1`` on a port the
kernel chooses. :meth:`EgressProxy.summary` is what the manifest records under ``producer.sandbox.egress``.

Rejected (D-664): a host allowlist in the sandbox profile (sandbox-exec filters by address and port, not by name);
decrypting TLS to filter by request (it would put the key-bearing headers in T0's hands for no gain); an allowlist by
resolved address (CDN addresses change and are shared).
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import ipaddress
import re
import secrets
import socket
import threading
import urllib.parse
from collections import Counter
from collections.abc import Iterable, Iterator
from typing import Any, Final

__all__ = ["EgressProxy", "LOOPBACK_HOSTS", "MAX_HEAD_BYTES", "allow_pair", "endpoint_target", "forward_pairs",
           "loopback_listeners"]

MAX_HEAD_BYTES: Final = 8 * 1024
HEAD_TIMEOUT_S: Final = 10.0
CONNECT_TIMEOUT_S: Final = 30.0
MAX_TUNNELS: Final = 64
#: The closed refusal kinds of :meth:`EgressProxy.summary` (R1-7: no worker-chosen text is ever recorded).
REFUSAL_KINDS: Final = ("not_allowed", "allowed_host_other_port", "method", "malformed", "oversize", "busy")
#: Distinct refused targets are counted up to this many (memory bound); the summary says when the count saturated.
MAX_DISTINCT_TARGETS: Final = 10_000
#: RFC 9110 5.6.2 token: what a header name must be (no whitespace, no separator, no control byte).
_TOKEN: Final = re.compile(rb"[!#$%&'*+\-.^_`|~0-9A-Za-z]+")
#: A request target: visible ASCII only (RFC 9112 3.2), so no worker-chosen control byte or non-ASCII text reaches a
#: rewritten request line or an exception message.
_TARGET: Final = re.compile(rb"[\x21-\x7e]+")
#: The largest request body the forward mode passes (a chat-completions request with a long context fits easily).
MAX_FORWARD_BODY: Final = 64 * 1024 * 1024
#: Idle bound while a forwarded request's body is read.
BODY_IDLE_TIMEOUT_S: Final = 30.0
#: Bound on each shutdown step of stop() (LF-4).
SHUTDOWN_TIMEOUT_S: Final = 5.0
_HOST = re.compile(r"(?:[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?\.)*[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?")
_CHUNK: Final = 64 * 1024


def allow_pair(host: str, port: int) -> tuple[str, int]:
    """A normalised allowlist entry: a DNS name (lower case, no trailing dot) and a port in 1-65535."""
    name = host.lower().rstrip(".")
    bracketed = name.startswith("[") and name.endswith("]")
    if bracketed:
        name = name[1:-1]
    if "%" in name:  # an IPv6 zone id names an interface of this host, never a LAN peer
        raise ValueError("an egress allowlist host must not carry a zone id")
    try:  # an IP literal (a LAN model server, D-698) in its canonical text form
        address = ipaddress.ip_address(name)
    except ValueError:
        if bracketed or not _HOST.fullmatch(name) or len(name) > 253:  # brackets enclose an IPv6 literal only
            raise ValueError("an egress allowlist host must be a DNS name or an IP literal") from None
    else:
        if bracketed and address.version != 6:
            raise ValueError("brackets enclose an IPv6 literal only")
        name = str(address)
    if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
        raise ValueError("an egress allowlist port must be in 1-65535")
    return name, port


LOOPBACK_HOSTS: Final = frozenset({"localhost", "127.0.0.1", "::1"})


def endpoint_target(base_url: str, *, allow_lan: bool = False) -> tuple[str, int, bool]:
    """``(host, port, is_loopback)`` of an endpoint base URL that ``check_base_url`` (or ``validate_base_url``)
    accepted: https (default port 443), or http on a loopback host (default port 80), or, with ``allow_lan`` (the run's
    ``--allow-lan-endpoint``, D-698), http or https on a literal private LAN address
    (``agentprov_capture.endpoints.is_private_lan_host``; never a name). A loopback endpoint is reached directly through
    the profile's ``LOOPBACK_PORT``; any other through the proxy (a LAN http endpoint through its forward mode)."""
    from agentprov_capture.endpoints import is_private_lan_host

    parts = urllib.parse.urlsplit(base_url)
    host = (parts.hostname or "").lower()
    try:
        port = parts.port
    except ValueError as exc:
        raise ValueError("the endpoint base URL has an invalid port") from exc
    loopback = host in LOOPBACK_HOSTS
    lan = allow_lan and not loopback and bool(host) and is_private_lan_host(host)
    if parts.scheme == "https":
        port = 443 if port is None else port
    elif parts.scheme == "http" and (loopback or lan):
        port = 80 if port is None else port
    else:
        raise ValueError("the endpoint base URL must be https, or http on a loopback host (or on a private LAN address "
                         "with --allow-lan-endpoint)")
    if not host:
        raise ValueError("the endpoint base URL has no host")
    if not loopback:
        host, port = allow_pair(host, port)
        if not lan and _is_ip_literal(host):  # D-698 admits literals for the LAN path only; a remote endpoint is named
            raise ValueError("a remote endpoint base URL must name its host (an IP literal is allowed only for a private "
                             "LAN address with --allow-lan-endpoint)")
    return host, port, loopback


def forward_pairs(base_url: str, host: str, port: int, *, allow_lan: bool) -> list[tuple[str, int]]:
    """The proxy's forward pairs for a run's non-loopback endpoint (``endpoint_target``'s ``host`` and ``port``): the
    pair itself for an http LAN server with ``--allow-lan-endpoint`` (D-698; the scheme in any case), else none."""
    lan = allow_lan and _is_ip_literal(host)  # endpoint_target admits a literal only on the LAN path
    return [(host, port)] if lan and urllib.parse.urlsplit(base_url).scheme == "http" else []


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


#: Methods the forward mode passes (an OpenAI-compatible model server needs GET and POST).
_FORWARD_METHODS: Final = frozenset({b"GET", b"POST", b"HEAD", b"OPTIONS"})
#: Hop-by-hop headers (RFC 9110 7.6.1) the forward mode drops; it sends its own ``Connection: close``.
_HOP_BY_HOP: Final = frozenset({b"connection", b"keep-alive", b"te", b"trailer", b"upgrade", b"proxy-connection"})


class EgressProxy:
    """A CONNECT forwarding proxy for an exact ``(host, port)`` allowlist, plus, for the pairs in ``forward`` only, a
    plain-HTTP forward mode (D-698: a LAN model server spoken to over http). Use :meth:`start` and :meth:`stop`, or the
    object as a context manager."""

    def __init__(self, allow: Iterable[tuple[str, int]], *, forward: Iterable[tuple[str, int]] = (),
                 max_tunnels: int = MAX_TUNNELS, head_timeout: float = HEAD_TIMEOUT_S,
                 connect_timeout: float = CONNECT_TIMEOUT_S) -> None:
        self.allow = frozenset(allow_pair(h, p) for h, p in allow)
        self.forward = frozenset(allow_pair(h, p) for h, p in forward)
        if not self.allow:
            raise ValueError("an egress proxy needs at least one allowed host")
        if not self.forward <= self.allow:
            raise ValueError("every forward pair must also be an allowed pair")
        self.max_tunnels = max_tunnels
        self.head_timeout = head_timeout
        self.connect_timeout = connect_timeout
        self.port: int | None = None
        self.tunnels: Counter[str] = Counter()
        self.forwards: Counter[str] = Counter()
        self.refused: Counter[str] = Counter()
        self._target_key = secrets.token_bytes(32)  # per proxy, memory only: distinctness without a recorded digest
        self._targets: set[bytes] = set()
        self._targets_capped = False
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._server: asyncio.Server | None = None
        self._thread: threading.Thread | None = None
        self._active = 0
        self._tasks: set[asyncio.Task[Any]] = set()

    # ------------------------------------------------------------------ lifecycle

    @property
    def url(self) -> str:
        if self.port is None:
            raise RuntimeError("the egress proxy is not running")
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> int:
        ready = threading.Event()
        failure: list[BaseException] = []

        def run() -> None:
            loop = asyncio.new_event_loop()
            self._loop = loop
            try:
                self._server = loop.run_until_complete(asyncio.start_server(self._handle, "127.0.0.1", 0))
                self.port = int(self._server.sockets[0].getsockname()[1])
            except BaseException as exc:  # noqa: BLE001 - reported to start()
                failure.append(exc)
                ready.set()
                loop.close()
                return
            ready.set()
            try:
                loop.run_forever()
            finally:
                loop.run_until_complete(self._shutdown())
                loop.close()

        self._thread = threading.Thread(target=run, name="agentprov-egress", daemon=True)
        self._thread.start()
        ready.wait(timeout=30)
        if failure:
            raise failure[0]
        if self.port is None:
            raise RuntimeError("the egress proxy did not start")
        return self.port

    def stop(self) -> None:
        """Stop accepting, cancel every open tunnel and forward and close both their sides, bounded (LF-4)."""
        loop, thread = self._loop, self._thread
        if loop is not None and thread is not None and thread.is_alive():
            loop.call_soon_threadsafe(loop.stop)
            thread.join(timeout=3 * SHUTDOWN_TIMEOUT_S)

    def __enter__(self) -> EgressProxy:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()

    async def _shutdown(self) -> None:
        # LF-4: cancel the open exchanges first. Server.wait_closed() waits for every live connection (Python 3.12+),
        # so awaiting it first held stop() for its whole timeout behind an upstream that stayed silent.
        if self._server is not None:
            self._server.close()
        for task in list(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.wait(list(self._tasks), timeout=SHUTDOWN_TIMEOUT_S)
        if self._server is not None:
            self._server.abort_clients()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._server.wait_closed(), SHUTDOWN_TIMEOUT_S)

    # ------------------------------------------------------------------ record

    def summary(self) -> dict[str, Any]:
        """``producer.sandbox.egress`` (counts only)."""
        with self._lock:
            return {
                "kind": "connect_proxy",
                "allow": sorted(f"{h}:{p}" for h, p in self.allow),
                "tunnels": dict(sorted(self.tunnels.items())),
                "forwards": dict(sorted(self.forwards.items())),
                "refused": {kind: self.refused[kind] for kind in REFUSAL_KINDS if self.refused[kind]},
                "refused_targets_distinct": len(self._targets),
                "refused_targets_capped": self._targets_capped,
            }

    def _refuse(self, kind: str, target: str | None = None) -> None:
        """Count a refusal by its closed ``kind``; a worker-chosen ``target`` only feeds the in-memory distinct count."""
        if kind not in REFUSAL_KINDS:  # pragma: no cover - a programming error
            raise ValueError(kind)
        with self._lock:
            self.refused[kind] += 1
            if target is not None:
                digest = hashlib.blake2b(target.encode("utf-8", "replace"), key=self._target_key, digest_size=16).digest()
                if digest in self._targets or len(self._targets) < MAX_DISTINCT_TARGETS:
                    self._targets.add(digest)
                else:
                    self._targets_capped = True

    # ------------------------------------------------------------------ protocol

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        if task is not None:
            self._tasks.add(task)
        try:
            await self._serve(reader, writer)
        except (asyncio.CancelledError, ConnectionError, OSError):
            pass
        except Exception:  # noqa: BLE001 - LF-3 backstop: never asyncio's traceback, which would print worker-chosen text
            self._refuse("malformed")
        finally:
            if task is not None:
                self._tasks.discard(task)
            writer.close()

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), self.head_timeout)
        except (TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError):
            self._refuse("malformed")
            return
        if len(head) > MAX_HEAD_BYTES:
            self._refuse("oversize")
            await self._reply(writer, 431, "Request Header Fields Too Large")
            return
        lines = head[:-4].split(b"\r\n")
        parts = lines[0].split(b" ")
        # LF-1: a bare CR or LF (or a NUL) inside a line, a header name that is not a token, or a folded line would let
        # a lenient server read a second request out of one head; the target is visible ASCII only
        if (len(parts) != 3 or parts[2] not in (b"HTTP/1.1", b"HTTP/1.0") or not _TARGET.fullmatch(parts[1])
                or not _TOKEN.fullmatch(parts[0])
                or any(b"\r" in raw or b"\n" in raw or b"\x00" in raw for raw in lines)
                or not all(_TOKEN.fullmatch(raw.partition(b":")[0]) and b":" in raw for raw in lines[1:])):
            self._refuse("malformed")
            await self._reply(writer, 400, "Bad Request")
            return
        method, target = parts[0], parts[1].decode("ascii")
        if method != b"CONNECT":
            if self.forward and method in _FORWARD_METHODS and target[:7].lower() == "http://":  # schemes ignore case
                await self._forward(reader, writer, head, method, target)
                return
            self._refuse("method")
            await self._reply(writer, 405, "Method Not Allowed")
            return
        host, sep, port_text = target.rpartition(":")
        pair: tuple[str, int] | None = None
        if sep and port_text.isdigit():
            try:
                pair = allow_pair(host, int(port_text))
            except ValueError:
                pair = None
        if pair is None or pair not in self.allow:
            other_port = pair is not None and any(h == pair[0] for h, _p in self.allow)
            self._refuse("allowed_host_other_port" if other_port else "not_allowed", target)
            await self._reply(writer, 403, "Forbidden")
            return
        if pair in self.forward:  # LF-2: a forward pair is spoken to through the forward mode's rules only, never a tunnel
            self._refuse("method")
            await self._reply(writer, 405, "Method Not Allowed")
            return
        with self._lock:
            busy = self._active >= self.max_tunnels
            if not busy:
                self._active += 1
        if busy:
            self._refuse("busy")
            await self._reply(writer, 503, "Service Unavailable")
            return
        try:
            try:
                up_reader, up_writer = await asyncio.wait_for(asyncio.open_connection(*pair), self.connect_timeout)
            except (TimeoutError, OSError):
                await self._reply(writer, 502, "Bad Gateway")
                return
            with self._lock:
                self.tunnels[f"{pair[0]}:{pair[1]}"] += 1
            writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await writer.drain()
            try:
                await asyncio.gather(self._pipe(reader, up_writer), self._pipe(up_reader, writer))
            finally:
                up_writer.close()
        finally:
            with self._lock:
                self._active -= 1

    async def _forward(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, head: bytes, method: bytes,
                       target: str) -> None:
        """D-698: one plain-HTTP request in absolute form to an exact ``forward`` pair. Only the request line is
        rewritten (origin form); ``Host`` is the pair's authority; ``Connection: close`` replaces the hop-by-hop headers
        and ``Proxy-*`` headers are dropped; the other headers and the ``Content-Length`` body pass through as bytes. One request per connection:
        bytes after the body are never read (LF-2)."""
        try:  # LF-3: a malformed absolute form (a bad bracketed host, a bad port) is refused, never raised
            parts = urllib.parse.urlsplit(target)
            port = parts.port or 80
        except ValueError:
            self._refuse("malformed", target)
            await self._reply(writer, 400, "Bad Request")
            return
        if parts.username is not None or parts.password is not None:  # userinfo is never forwarded
            self._refuse("malformed", target)
            await self._reply(writer, 400, "Bad Request")
            return
        try:
            pair = allow_pair(parts.hostname or "", port) if parts.scheme == "http" else None
        except ValueError:
            pair = None
        if pair is None or pair not in self.forward:
            other_port = pair is not None and any(h == pair[0] for h, _p in self.allow)
            self._refuse("allowed_host_other_port" if other_port else "not_allowed", target)
            await self._reply(writer, 403, "Forbidden")
            return
        kept = []
        for raw in head[:-4].split(b"\r\n")[1:]:  # every line is a token name and a value without CR, LF or NUL (_serve)
            name = raw.partition(b":")[0].lower()
            if name not in _HOP_BY_HOP and name != b"host" and not name.startswith(b"proxy-"):
                kept.append(raw)
        # LF-2: exactly one request. Its body is the Content-Length bytes and nothing after them is ever passed; a body
        # framed otherwise (Transfer-Encoding, several or malformed lengths) is refused
        fields = [raw.partition(b":") for raw in kept]
        lengths = [value.strip() for name, _sep, value in fields if name.lower() == b"content-length"]
        if any(name.lower() == b"transfer-encoding" for name, _sep, _value in fields) or len(lengths) > 1 or (
                lengths and not (lengths[0].isdigit() and len(lengths[0]) <= 12)):
            self._refuse("malformed")
            await self._reply(writer, 400, "Bad Request")
            return
        length = int(lengths[0]) if lengths else 0
        if length > MAX_FORWARD_BODY:
            self._refuse("oversize")
            await self._reply(writer, 413, "Content Too Large")
            return
        origin = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        try:  # visible ASCII since _serve's target check (LF-1); kept as a refusal, not a raise (LF-3)
            origin_bytes = origin.encode("ascii")
        except UnicodeEncodeError:
            self._refuse("malformed")
            await self._reply(writer, 400, "Bad Request")
            return
        # RFC 9112 3.2.2: a proxy replaces Host with the target's authority (here the canonical forward pair)
        authority = f"[{pair[0]}]:{pair[1]}" if ":" in pair[0] else f"{pair[0]}:{pair[1]}"
        new_head = b"\r\n".join([method + b" " + origin_bytes + b" HTTP/1.1", b"Host: " + authority.encode("ascii"), *kept,
                                  b"Connection: close"])
        with self._lock:
            busy = self._active >= self.max_tunnels
            if not busy:
                self._active += 1
        if busy:
            self._refuse("busy")
            await self._reply(writer, 503, "Service Unavailable")
            return
        try:
            try:
                up_reader, up_writer = await asyncio.wait_for(asyncio.open_connection(*pair), self.connect_timeout)
            except (TimeoutError, OSError):
                await self._reply(writer, 502, "Bad Gateway")
                return
            with self._lock:
                self.forwards[f"{pair[0]}:{pair[1]}"] += 1
            try:
                up_writer.write(new_head + b"\r\n\r\n")
                await up_writer.drain()
                await self._copy_exact(reader, up_writer, length)
                await self._pipe(up_reader, writer)  # the response ends when the server closes (Connection: close)
            except (TimeoutError, asyncio.IncompleteReadError):
                pass  # the body did not arrive: the request is abandoned, both connections close
            finally:
                up_writer.close()
        finally:
            with self._lock:
                self._active -= 1

    @staticmethod
    async def _copy_exact(src: asyncio.StreamReader, dst: asyncio.StreamWriter, n: int) -> None:
        """Copy exactly ``n`` bytes (a request body), each read bounded by :data:`BODY_IDLE_TIMEOUT_S`."""
        while n > 0:
            data = await asyncio.wait_for(src.read(min(_CHUNK, n)), BODY_IDLE_TIMEOUT_S)
            if not data:
                raise asyncio.IncompleteReadError(b"", n)
            dst.write(data)
            await dst.drain()
            n -= len(data)

    @staticmethod
    async def _pipe(src: asyncio.StreamReader, dst: asyncio.StreamWriter) -> None:
        try:
            while data := await src.read(_CHUNK):
                dst.write(data)
                await dst.drain()
        except (ConnectionError, OSError):
            pass
        finally:
            try:
                if dst.can_write_eof():
                    dst.write_eof()
            except (OSError, RuntimeError):
                pass

    @staticmethod
    async def _reply(writer: asyncio.StreamWriter, status: int, reason: str) -> None:
        writer.write(f"HTTP/1.1 {status} {reason}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n".encode("ascii"))
        try:
            await writer.drain()
        except (ConnectionError, OSError):
            pass


@contextlib.contextmanager
def loopback_listeners(n: int, host: str = "127.0.0.1") -> Iterator[tuple[int, ...]]:
    """``n`` loopback TCP listeners on ``host`` that accept and close every connection: the sandbox probe's connection
    targets (``agentprov.cli.live.sandbox.probe``). Kept here so that ``socket`` is imported by this one module of the
    core's live side (M.5.3)."""
    socks = []
    stop = threading.Event()
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    try:
        for _ in range(n):
            sock = socket.socket(family, socket.SOCK_STREAM)
            socks.append(sock)
            sock.bind((host, 0))
            sock.listen(8)
            sock.settimeout(0.2)

        def serve(sock: socket.socket) -> None:
            while not stop.is_set():
                try:
                    conn, _ = sock.accept()
                except (TimeoutError, OSError):
                    continue
                conn.close()

        threads = [threading.Thread(target=serve, args=(s,), daemon=True) for s in socks]
        for t in threads:
            t.start()
        yield tuple(int(s.getsockname()[1]) for s in socks)
    finally:
        stop.set()
        for s in socks:
            s.close()
