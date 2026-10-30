"""The keychain helper process (D-395, D-655, D-702): ``python -I -m agentprov.keys.helper``.

The **only** core module that imports ``keyring`` (a boundary test enforces it). It runs in its own short-lived process
because keyring's dependency ``jaraco.context`` imports ``urllib.request`` (and with it ``socket``, ``ssl`` and
``http.client``) at module level; neither the CLI process nor the GUI process loads them for keys.

**Back-end allowlist.** The back-end is constructed directly, never through ``keyring.get_keyring()`` (which reads
``keyringrc.cfg``, its ``keyring-path`` ``sys.path`` insertion, ``PYTHON_KEYRING_BACKEND`` and the entry points: all
ways to load other code): macOS Keychain, Windows Credential Locker, Linux Secret Service, then KWallet. It must be
``viable``; anything else is "no secure keychain". Service ``agentprov``, user = the variable name.

**Protocol.** One JSON object on stdin (at most 64 KiB, strict: no duplicate keys, no NaN), ``{"op": ...}``:

* ``status`` → ``{"ok": true, "backend": NAME, "allowed": bool}`` on stdout;
* ``has`` ``{"names": [...]}`` → ``{"ok": true, "present": {NAME: bool}}`` (no value is returned);
* ``set`` ``{"name": N, "value": V}`` → ``{"ok": true}``; ``delete`` ``{"name": N}`` → ``{"ok": true}``;
* ``emit`` ``{"names": [...], "values": {...}}``: stdout receives exactly one line, the object of every named secret
  plus the given non-secret values (``run --keychain`` reads it through a pipe). A missing secret writes nothing and
  exits 3.

Errors: one ``{"ok": false, "error": CODE}`` line (never a value) and exit 2 (usage), 3 (missing), 4 (no keychain).
Names must match ``[A-Z][A-Z0-9_]{0,63}``. Values are never logged, printed in an error or written anywhere but the
keychain and the ``emit`` line.
"""

from __future__ import annotations

import contextlib
import json
import re
import sys
from typing import Any, Final

SERVICE: Final = "agentprov"
MAX_REQUEST: Final = 64 * 1024
MAX_EMIT: Final = 8 * 1024  # fits a pipe buffer, so the helper never blocks before the CLI starts reading
NAME: Final = re.compile(r"[A-Z][A-Z0-9_]{0,63}")
#: (module, class) per platform, in order of preference: the allowlist of design §8.2.
ALLOWED: Final = {
    "darwin": (("keyring.backends.macOS", "Keyring"),),
    "win32": (("keyring.backends.Windows", "WinVaultKeyring"),),
    "linux": (("keyring.backends.SecretService", "Keyring"), ("keyring.backends.kwallet", "DBusKeyring")),
}


def _reject(_: str) -> Any:
    raise ValueError("non-finite number")


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in items:
        if k in out:
            raise ValueError("duplicate key")
        out[k] = v
    return out


def backend() -> Any:
    """The first viable allowlisted back-end of this platform, or ``None``."""
    for module, cls in ALLOWED.get(sys.platform, ()):
        try:
            if module == "keyring.backends.macOS":
                from keyring.backends import macOS as mod
            elif module == "keyring.backends.Windows":
                from keyring.backends import Windows as mod  # type: ignore[no-redef]
            elif module == "keyring.backends.SecretService":
                from keyring.backends import SecretService as mod  # type: ignore[no-redef]
            else:
                from keyring.backends import kwallet as mod  # type: ignore[no-redef]
            klass = getattr(mod, cls)
            if klass.viable:
                return klass()
        except Exception:  # noqa: S112 - an unusable back-end is skipped; the next one is tried
            continue
    return None


def _out(obj: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _fail(code: str, status: int) -> int:
    _out({"ok": False, "error": code})
    return status


def _names(value: Any) -> list[str] | None:
    if not isinstance(value, list) or len(value) > 32 or not all(isinstance(n, str) and NAME.fullmatch(n)
                                                                  for n in value):
        return None
    return list(dict.fromkeys(value))


def main() -> int:
    data = sys.stdin.buffer.read(MAX_REQUEST + 1)
    if len(data) > MAX_REQUEST:
        return _fail("request.too_large", 2)
    try:
        req = json.loads(data, object_pairs_hook=_pairs, parse_constant=_reject)
    except ValueError:
        return _fail("request.invalid", 2)
    if not isinstance(req, dict) or not isinstance(req.get("op"), str):
        return _fail("request.invalid", 2)
    op = req["op"]
    ring = backend()
    if op == "status":
        _out({"ok": True, "backend": type(ring).__name__ if ring is not None else None, "allowed": ring is not None})
        return 0
    if ring is None:
        return _fail("keychain.unavailable", 4)
    if op == "has":
        names = _names(req.get("names"))
        if names is None:
            return _fail("request.names", 2)
        _out({"ok": True, "present": {n: ring.get_password(SERVICE, n) is not None for n in names}})
        return 0
    if op in ("set", "delete"):
        name = req.get("name")
        if not isinstance(name, str) or not NAME.fullmatch(name):
            return _fail("request.name", 2)
        if op == "delete":
            with contextlib.suppress(Exception):  # not stored is fine for a delete
                ring.delete_password(SERVICE, name)
            _out({"ok": True})
            return 0
        value = req.get("value")
        if not isinstance(value, str) or not value or len(value) > 16 * 1024 or any(c in value for c in "\r\n\x00"):
            return _fail("request.value", 2)
        ring.set_password(SERVICE, name, value)
        _out({"ok": True})
        return 0
    if op == "emit":
        names = _names(req.get("names"))
        values = req.get("values", {})
        if names is None or not isinstance(values, dict) or not all(
                isinstance(k, str) and NAME.fullmatch(k) and isinstance(v, str) and len(v) <= 1024
                and not any(c in v for c in "\r\n\x00") for k, v in values.items()):
            return _fail("request.names", 2)
        line: dict[str, str] = dict(values)
        for n in names:
            secret = ring.get_password(SERVICE, n)
            if secret is None:
                sys.stderr.write(f"keychain_helper: {n} is not in the keychain\n")
                return 3  # nothing on stdout: the CLI then reads an empty stdin and refuses
            line[n] = secret
        text = json.dumps(line, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
        if len(text.encode("utf-8")) > MAX_EMIT:
            sys.stderr.write("keychain_helper: the key line is too long\n")
            return 2
        sys.stdout.write(text)
        sys.stdout.flush()
        return 0
    return _fail("request.op", 2)


if __name__ == "__main__":
    raise SystemExit(main())
