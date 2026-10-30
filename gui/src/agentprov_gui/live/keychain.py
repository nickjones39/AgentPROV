"""The GUI's side of the keychain (design §8.2; D-395, D-655, D-702): a client of ``agentprov keys``. No Qt; no
``keyring``. One implementation: the CLI's keychain helper process (``agentprov.keys.helper``) does the work.

* :func:`status` and :func:`present`: ``agentprov keys status|list --format json`` (names and presence, never values);
* :func:`store`: ``agentprov keys set NAME --stdin``, the value on the subprocess's stdin (never argv); the caller has
  registered it with the GUI log's redaction first (GR-16/43);
* :func:`delete`: ``agentprov keys delete NAME --yes`` (the GUI asked first);
* a live run reads its key itself: the GUI passes ``run --keychain`` (D-702), so no key passes through the GUI.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Final

from agentprov_gui.jobs.manager import CliLocator, allowlisted_env

__all__ = ["KeychainError", "KeychainStatus", "delete", "present", "status", "store"]

TIMEOUT_S: Final = 60.0
#: what the Linux Secret Service and KWallet need to reach the session bus (the helper's own allowlist keeps them)
_BUS_ENV: Final = ("DBUS_SESSION_BUS_ADDRESS", "XDG_RUNTIME_DIR", "DISPLAY", "WAYLAND_DISPLAY")


class KeychainError(RuntimeError):
    """A failed ``agentprov keys`` call; ``code`` names the exit (never a value)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class KeychainStatus:
    allowed: bool
    backend: str | None
    reason: str | None = None  # why there is none, and the fallback (the CLI's text; G5 P-1)


def _env() -> dict[str, str]:
    import os

    env = allowlisted_env()
    env.update({k: os.environ[k] for k in _BUS_ENV if k in os.environ})
    return env


def _run(cli: CliLocator, argv: Sequence[str], *, stdin: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    if not cli.available:
        raise KeychainError("keychain.no_cli")
    try:
        return subprocess.run(  # noqa: S603 - the configured CLI and a fixed argv
            [*cli.program, "keys", *argv, "--progress", "off", "--no-colour"], input=stdin, capture_output=True,
            env=_env(), timeout=TIMEOUT_S, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise KeychainError("keychain.cli_failed") from None


def _json(done: subprocess.CompletedProcess[bytes]) -> Any:
    try:
        return json.loads(done.stdout)
    except ValueError:
        raise KeychainError(f"keychain.exit_{done.returncode}") from None


def status(cli: CliLocator) -> KeychainStatus:
    doc = _json(_run(cli, ["status", "--format", "json"]))
    backend = doc.get("backend") if isinstance(doc, dict) else None
    reason = doc.get("reason") if isinstance(doc, dict) else None
    return KeychainStatus(bool(isinstance(doc, dict) and doc.get("allowed")),
                          backend if isinstance(backend, str) else None, reason if isinstance(reason, str) else None)


def present(cli: CliLocator, names: Sequence[str]) -> dict[str, bool]:
    done = _run(cli, ["list", "--format", "json"])
    if done.returncode != 0:
        raise KeychainError(f"keychain.exit_{done.returncode}")
    doc = _json(done)
    rows = doc.get("keys") if isinstance(doc, dict) else None
    stored = {r.get("name"): bool(r.get("stored")) for r in rows if isinstance(r, dict)} if isinstance(rows, list) else {}
    return {n: stored.get(n, False) for n in names}


def store(cli: CliLocator, name: str, value: str) -> None:
    done = _run(cli, ["set", name, "--stdin"], stdin=value.encode("utf-8") + b"\n")
    if done.returncode != 0:
        raise KeychainError(f"keychain.exit_{done.returncode}")


def delete(cli: CliLocator, name: str) -> None:
    done = _run(cli, ["delete", name, "--yes"])
    if done.returncode != 0:
        raise KeychainError(f"keychain.exit_{done.returncode}")
