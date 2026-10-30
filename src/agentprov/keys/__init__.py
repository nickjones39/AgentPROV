"""Keys in the OS keychain (D-395, D-655, D-702): the client of the keychain helper process. No ``keyring`` import here.

Every operation runs one short-lived helper, ``python -I -m agentprov.keys.helper`` (:mod:`agentprov.keys.helper`, the
only importer of ``keyring``), with an environment allowlist that never carries key variables, and one JSON request on
stdin:

* :func:`status` and :func:`present`: whether a secure keychain is available and which names are stored (no value);
* :func:`store` and :func:`delete`: the value comes from the caller (``agentprov keys set`` reads it from a no-echo
  prompt or stdin, never argv);
* :func:`read` (``run --keychain``): the named secrets, through a pipe, into the CLI process only, where ``run``
  registers them with the redaction before anything else, exactly as for ``--env-stdin``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from agentprov.errors import AgentProvError

__all__ = ["HELPER", "KeychainError", "KeychainStatus", "delete", "present", "read", "status", "store",
           "unavailable_reason"]

HELPER: Final = "agentprov.keys.helper"
TIMEOUT_S: Final = 30.0
_BASE_ENV: Final = ("PATH", "HOME", "LANG", "TZ", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "SystemRoot", "TMPDIR")
#: what the Linux Secret Service and KWallet need to reach the session bus
_EXTRA_ENV: Final = ("DBUS_SESSION_BUS_ADDRESS", "XDG_RUNTIME_DIR", "DISPLAY", "WAYLAND_DISPLAY")


class KeychainError(AgentProvError):
    """A helper failure; ``code`` is the helper's closed error code (never a value)."""

    code = "keys.helper_failed"
    exit_code = 3

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or f"the keychain helper failed ({code})")
        self.code = code
        self.exit_code = 4 if code == "keychain.unavailable" else 2 if code.startswith("request.") else 3


@dataclass(frozen=True, slots=True)
class KeychainStatus:
    allowed: bool
    backend: str | None


#: ``AGENTPROV_NO_KEYCHAIN=1`` turns the keychain off for this process and its children (CI, headless hosts, the test
#: suite): every call answers as an unavailable back-end, and ``run``'s default key lookup falls back to ``.env``.
NO_KEYCHAIN: Final = "AGENTPROV_NO_KEYCHAIN"

_FALLBACK: Final = "keys then come from .env, --env-file or --env-stdin (the key order: keychain first, then .env)"
#: Linux: keyring's KWallet back-end needs ``dbus-python``, which is not locked, so it is never found; KDE Plasma's
#: wallet is reached through its Secret Service interface instead (G5 note §2.2)
_WHY: Final = {
    "darwin": "the macOS login keychain is not available to this session (locked, or a session without one)",
    "win32": "Windows Credential Manager is not available to this process",
    "linux": ("no Secret Service is answering on this session's D-Bus (start and unlock a keyring that provides it: "
              "GNOME Keyring, KDE Plasma's wallet service, or KeePassXC with its Secret Service integration; a "
              "headless or SSH session usually has none)"),
}


def unavailable_reason(platform: str | None = None, environ: Mapping[str, str] | None = None) -> str:
    """Why there is no allowed keychain on ``platform`` (default this one), and the fallback (G5 note §2.2, P-1)."""
    env = os.environ if environ is None else environ
    if env.get(NO_KEYCHAIN) == "1":
        return f"the keychain is turned off ({NO_KEYCHAIN}=1); {_FALLBACK}"
    name = sys.platform if platform is None else platform
    if name == "linux" and not env.get("DBUS_SESSION_BUS_ADDRESS"):
        return f"there is no D-Bus session (DBUS_SESSION_BUS_ADDRESS is unset), so no Secret Service; {_FALLBACK}"
    why = _WHY.get(name, "this platform has no allowed keychain (macOS Keychain, Windows Credential Manager, Linux "
                         "Secret Service)")
    return f"{why}; {_FALLBACK}"


def helper_argv() -> list[str]:
    if getattr(sys, "frozen", False):  # a frozen GUI bundle dispatches the flag before Qt is imported (G5)
        return [sys.executable, "--keychain-helper"]
    return [sys.executable, "-I", "-m", HELPER]


def helper_env(environ: Mapping[str, str] | None = None) -> dict[str, str]:
    source = os.environ if environ is None else environ
    return {k: source[k] for k in (*_BASE_ENV, *_EXTRA_ENV) if k in source}


def _call(request: Mapping[str, Any]) -> subprocess.CompletedProcess[bytes]:
    data = json.dumps(dict(request), separators=(",", ":")).encode("utf-8")
    if os.environ.get(NO_KEYCHAIN) == "1":  # as an unavailable back-end (exit 4): no helper, no keychain access
        return subprocess.CompletedProcess([], 4, json.dumps({"ok": False, "error": "keychain.disabled"}).encode(), b"")
    try:
        return subprocess.run(  # noqa: S603 - this interpreter and this package's own module
            helper_argv(), input=data, capture_output=True, env=helper_env(), timeout=TIMEOUT_S, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise KeychainError("keychain.helper_failed") from None


def _reply(done: subprocess.CompletedProcess[bytes]) -> dict[str, Any]:
    try:
        reply = json.loads(done.stdout.splitlines()[-1]) if done.stdout else None
    except (ValueError, IndexError):
        reply = None
    if not isinstance(reply, dict):
        raise KeychainError("keychain.helper_failed")
    if not reply.get("ok"):
        raise KeychainError(str(reply.get("error", "keychain.helper_failed"))[:60])
    return reply


def status() -> KeychainStatus:
    """Whether an allowed keychain is available; ``AGENTPROV_NO_KEYCHAIN=1`` answers as an unavailable one."""
    if os.environ.get(NO_KEYCHAIN) == "1":
        return KeychainStatus(False, None)
    reply = _reply(_call({"op": "status"}))
    backend = reply.get("backend")
    return KeychainStatus(bool(reply.get("allowed")), backend if isinstance(backend, str) else None)


def present(names: Sequence[str]) -> dict[str, bool]:
    reply = _reply(_call({"op": "has", "names": list(names)}))
    found = reply.get("present")
    return {n: bool(found.get(n)) for n in names} if isinstance(found, dict) else dict.fromkeys(names, False)


def store(name: str, value: str) -> None:
    _reply(_call({"op": "set", "name": name, "value": value}))


def delete(name: str) -> None:
    _reply(_call({"op": "delete", "name": name}))


def read(names: Sequence[str], values: Mapping[str, str] | None = None) -> dict[str, str]:
    """The named secrets (plus ``values``) for ``run --keychain``. :class:`KeychainError` ``keychain.missing`` when one
    is not stored. The caller registers every value with the redaction at once."""
    done = _call({"op": "emit", "names": list(names), "values": dict(values or {})})
    if done.returncode != 0:
        code = "keychain.missing" if done.returncode == 3 else "keychain.unavailable" if done.returncode == 4 \
            else "keychain.helper_failed"
        raise KeychainError(code)
    try:
        doc = json.loads(done.stdout)
    except ValueError:
        raise KeychainError("keychain.helper_failed") from None
    if not isinstance(doc, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in doc.items()):
        raise KeychainError("keychain.helper_failed")
    return dict(doc)
