"""Socket guard for the T2 worker and the backend tests (K.3.2; D.10.8 "offline guarantee"; D.11.5).

``install()`` patches ``socket.socket.connect``/``connect_ex``, ``socket.create_connection`` and ``socket.getaddrinfo``
so that any attempt to reach the network raises ``NetworkBlocked``. Unix-domain sockets are not network and stay
allowed. The worker calls ``install_from_env()`` before it imports any benchmark code, so an import-time download
(AutoDojo's ``nltk.download``) fails loudly. Stdlib only.
"""

from __future__ import annotations

import os
import socket
from typing import Any

__all__ = ["ENV_VAR", "NetworkBlocked", "attempts", "install", "install_from_env", "installed", "uninstall"]

ENV_VAR = "AGENTPROV_BLOCK_NETWORK"


class NetworkBlocked(OSError):
    """A network connection was attempted while the guard was installed."""


_saved: dict[str, Any] | None = None
#: Every blocked attempt, in order (the call name). A library may swallow ``NetworkBlocked`` (``nltk.download`` does),
#: so tests that must show *no attempt* check this list, not only the absence of an exception.
attempts: list[str] = []


def _blocked(call: str) -> NetworkBlocked:
    attempts.append(call)
    return NetworkBlocked(f"network blocked ({ENV_VAR}): {call}")


def _is_unix(sock: Any) -> bool:
    family = getattr(sock, "family", None)
    return getattr(socket, "AF_UNIX", object()) == family


def install() -> None:
    """Install the guard (idempotent)."""
    global _saved
    if _saved is not None:
        return
    saved = {
        "connect": socket.socket.connect,
        "connect_ex": socket.socket.connect_ex,
        "create_connection": socket.create_connection,
        "getaddrinfo": socket.getaddrinfo,
    }
    orig_connect = saved["connect"]
    orig_connect_ex = saved["connect_ex"]

    def connect(self: socket.socket, address: Any) -> Any:
        if _is_unix(self):
            return orig_connect(self, address)
        raise _blocked("connect")

    def connect_ex(self: socket.socket, address: Any) -> Any:
        if _is_unix(self):
            return orig_connect_ex(self, address)
        raise _blocked("connect_ex")

    def create_connection(*args: Any, **kwargs: Any) -> Any:
        raise _blocked("create_connection")

    def getaddrinfo(*args: Any, **kwargs: Any) -> Any:
        raise _blocked("getaddrinfo")

    socket.socket.connect = connect  # type: ignore[method-assign]
    socket.socket.connect_ex = connect_ex  # type: ignore[method-assign]
    socket.create_connection = create_connection  # type: ignore[assignment]
    socket.getaddrinfo = getaddrinfo  # type: ignore[assignment]
    _saved = saved


def uninstall() -> None:
    global _saved
    if _saved is None:
        return
    socket.socket.connect = _saved["connect"]  # type: ignore[method-assign]
    socket.socket.connect_ex = _saved["connect_ex"]  # type: ignore[method-assign]
    socket.create_connection = _saved["create_connection"]  # type: ignore[assignment]
    socket.getaddrinfo = _saved["getaddrinfo"]  # type: ignore[assignment]
    _saved = None


def installed() -> bool:
    return _saved is not None


def install_from_env(environ: Any = None) -> bool:
    """Install the guard when ``AGENTPROV_BLOCK_NETWORK=1``; returns whether it is installed."""
    env = os.environ if environ is None else environ
    if env.get(ENV_VAR) == "1":
        install()
    return installed()
