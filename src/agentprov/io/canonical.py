"""Canonical bytes and digests (docs/architecture: C.4.1, C.11.1; MN M.1.2).

This module is the **only** importer of ``rfc8785`` in the core. Everything that needs RFC 8785 (JCS)
canonical JSON, a SHA-256 digest, a ``sha256:<hex>`` reference or the base32 spelling of an identifier goes
through the helpers below, so that the byte encoding of each component is defined in exactly one place.

The helpers are pure and deterministic: no dependence on dict order (JCS sorts members), locale or time.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from typing import Any, Final

import rfc8785

__all__ = [
    "SHA256_REF_PREFIX",
    "base32_lower_nopad",
    "is_sha256_hex",
    "is_sha256_ref",
    "jcs_bytes",
    "sha256_hex",
    "sha256_of_ref",
    "sha256_ref",
]

SHA256_REF_PREFIX: Final = "sha256:"
_HEX64 = re.compile(r"[0-9a-f]{64}")


def jcs_bytes(obj: Any) -> bytes:
    """RFC 8785 canonical JSON of ``obj`` (UTF-8, members sorted by UTF-16 code units, no whitespace).

    Raises the ``rfc8785`` error types for values JCS cannot represent (non-finite floats, integers outside
    the I-JSON range, lone surrogates, non-string keys); callers in ``agentprov.aer.canon`` map them to
    ``CanonError``. Note that JCS prints negative zero as ``0`` and integral floats without a fraction, which is
    why the AER encodes ``-0`` and the int/float distinction explicitly (C.11.3, C.11.4).

    ``rfc8785`` is the reference. A *plain* value (:func:`_plain`) is encoded by the stdlib ``json`` encoder instead,
    which writes the same bytes on that domain and is about four times faster (D-416). Anything else, and any error,
    goes to ``rfc8785`` as before, so its errors and its handling of every other value are unchanged.
    """
    try:  # the guard is inside: near the recursion limit it, like the encoder, may raise where rfc8785 would not
        if _plain(obj, 0):
            return _JSON_ENCODE(obj).encode("utf-8")
    except (UnicodeEncodeError, ValueError, RecursionError):  # a lone surrogate, say: rfc8785 decides
        pass
    return rfc8785.dumps(obj)


# D-416. On a plain value the stdlib encoder and rfc8785 agree byte for byte:
# - null, true, false and integers: the same literals and int.__repr__, inside rfc8785's own integer bounds;
# - strings: both escape exactly '"', '\\', \b, \f, \n, \r, \t and the other C0 controls (as lower-case \u00xx) and
#   write everything else as UTF-8 (tests/unit/io/test_canonical_fastpath.py checks every code point);
# - members: rfc8785 sorts keys by UTF-16BE bytes, which for keys without an astral character is code-point order,
#   Python's str order.
# The guard admits exact types only: rfc8785 reads an int subclass through int() (so __int__) and a dict subclass
# through dict() (its real storage), where json uses int.__repr__ and items(); those can differ (core review B, B1/B2).
# Floats never take this path: JCS formats numbers as ECMAScript does, which float.__repr__ does not.
_JSON_ENCODE: Final = json.JSONEncoder(
    ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False, check_circular=True
).encode
_INT_MAX: Final = 2**53 - 1  # rfc8785's bounds; outside them it raises IntegerDomainError
_MAX_DEPTH: Final = 128  # deeper values (and cycles) take the reference path


def _plain(obj: Any, depth: int) -> bool:
    """Whether ``obj`` is exact dict/list/str/int/bool/None, integers within ±(2**53-1), keys without astral characters."""
    if depth > _MAX_DEPTH:
        return False
    t = type(obj)
    if t is str or t is bool or obj is None:
        return True
    if t is int:
        return -_INT_MAX <= obj <= _INT_MAX
    if t is dict:
        for key, value in obj.items():
            if type(key) is not str or (not key.isascii() and max(map(ord, key)) > 0xFFFF):
                return False
            if not _plain(value, depth + 1):
                return False
        return True
    if t is list:
        for value in obj:  # a loop, not all(...): one frame per level, as in rfc8785
            if not _plain(value, depth + 1):
                return False
        return True
    return False


def sha256_hex(data: bytes | bytearray | memoryview) -> str:
    """Lower-case hexadecimal SHA-256 of ``data`` (64 characters)."""
    return hashlib.sha256(data).hexdigest()


def sha256_ref(data: bytes | bytearray | memoryview) -> str:
    """``"sha256:<hex>"`` reference (the ``Digest`` type of C.0.3) of ``data``."""
    return SHA256_REF_PREFIX + sha256_hex(data)


def is_sha256_hex(value: object) -> bool:
    """True iff ``value`` is exactly 64 lower-case hexadecimal digits."""
    return isinstance(value, str) and _HEX64.fullmatch(value) is not None


def is_sha256_ref(value: object) -> bool:
    """True iff ``value`` is ``"sha256:"`` followed by 64 lower-case hexadecimal digits."""
    return isinstance(value, str) and value.startswith(SHA256_REF_PREFIX) and is_sha256_hex(value[7:])


def sha256_of_ref(ref: str) -> str:
    """The hex digest inside a ``sha256:<hex>`` reference; ``ValueError`` if ``ref`` is malformed."""
    if not is_sha256_ref(ref):
        raise ValueError("not a sha256 reference")
    return ref[len(SHA256_REF_PREFIX) :]


def base32_lower_nopad(data: bytes) -> str:
    """RFC 4648 base32, lower-case, without padding (C.4.1): the spelling of the 26-character id body."""
    return base64.b32encode(data).decode("ascii").lower().rstrip("=")
