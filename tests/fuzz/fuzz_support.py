"""Budgets, outcomes and mutations shared by the fuzz suites (K.11.1 F-1, F-2, F-5).

``AGENTPROV_FUZZ=thorough`` multiplies the example counts (the manual ``thorough`` job, ``slow``); the default ``ci``
budget is modest because other test sessions share the machine.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from hypothesis import HealthCheck, settings
from hypothesis import strategies as st

from agentprov.errors import INGEST_CODES, IngestError

THOROUGH = os.environ.get("AGENTPROV_FUZZ") == "thorough"
_SCALE = 20 if THOROUGH else 1
_HEALTH = [HealthCheck.too_slow, HealthCheck.data_too_large, HealthCheck.filter_too_much]


def budget(examples: int, *, deadline: int | None = 2000) -> settings:
    """F-2: a per-input time budget (``deadline`` ms) and a modest example count, scaled for the thorough job."""
    return settings(max_examples=examples * _SCALE, deadline=deadline, derandomize=not THOROUGH,
                    suppress_health_check=_HEALTH)


def outcome(fn: Callable[[], Any], *typed: type[BaseException]) -> tuple[str, Any]:
    """F-1: success, an ``IngestError`` with a G.3.9 code, or one of the ``typed`` errors (its class and code)."""
    try:
        return ("ok", fn())
    except IngestError as exc:
        assert exc.code in INGEST_CODES, exc.code
        return ("ingest", exc.code)
    except typed as exc:
        return (type(exc).__name__, getattr(exc, "code", None))


def byte_mutations(seed: bytes, *, max_ops: int = 6) -> st.SearchStrategy[bytes]:
    """Flip, cut, insert, delete, duplicate a slice, or splice a hostile token, at random offsets of ``seed``."""
    tokens = [b'"', b"{", b"}", b"[", b"]", b",", b":", b"null", b"1e999", b"-0", b"\\u0000", b"\\ud800", b"\xff",
              b"\xef\xbb\xbf", b"\r\n", b"\n", b"\x00", b"9" * 30, b'"$blob"', b'"..": ', b"NaN"]

    def apply(ops: list[tuple[str, int, int, bytes]]) -> bytes:
        data = bytearray(seed)
        for op, pos, val, token in ops:
            i = pos % (len(data) + 1)
            if op == "flip" and data:
                data[i % len(data)] ^= (val % 255) + 1
            elif op == "cut":
                del data[i:]
            elif op == "ins":
                data[i:i] = token
            elif op == "del":
                del data[i : i + 1 + val % 16]
            elif op == "dup":
                data[i:i] = data[i : i + 1 + val % 64]
        return bytes(data)

    op = st.tuples(st.sampled_from(["flip", "cut", "ins", "del", "dup"]), st.integers(0, 1 << 20),
                   st.integers(0, 1 << 20), st.sampled_from(tokens))
    return st.lists(op, max_size=max_ops).map(apply)
