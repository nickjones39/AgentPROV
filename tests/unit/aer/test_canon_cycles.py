"""Regen item 65 (CA-6, C.11.1): a cyclic or too-deep value is a ``CanonError``, never a hang or a bare error.

``dumps_line`` pre-checks a record's types iteratively; a reference cycle (a producer bug) made that walk loop
forever. ``encode_value`` recursed into the cycle and raised a bare ``RecursionError``. The walk now tracks the
containers on the current path (shared acyclic sub-objects stay legal) and ``encode_value`` maps
``RecursionError`` to ``CanonError``.
"""

from __future__ import annotations

import signal
from collections.abc import Callable, Iterator

import pytest

from agentprov.aer.canon import CanonError, LexHints, dumps_line, encode_value


class _Hang(Exception):
    pass


def _alarm(_signum: int, _frame: object) -> None:
    raise _Hang("no result within 3 s")


@pytest.fixture
def guard() -> Iterator[None]:
    """Turn a hang into a failure: ``_Hang`` is raised 3 s in."""
    old = signal.signal(signal.SIGALRM, _alarm)
    signal.alarm(3)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


def _dict_cycle() -> dict[str, object]:
    d: dict[str, object] = {"k": "x"}
    d["self"] = [d]
    return d


def _list_cycle() -> dict[str, object]:
    lst: list[object] = []
    lst.append(lst)
    return {"a": lst}


def _deep(levels: int) -> dict[str, object]:
    v: object = "leaf"
    for _ in range(levels):
        v = [v]
    return {"a": v}


CYCLES: list[Callable[[], dict[str, object]]] = [_dict_cycle, _list_cycle]


@pytest.mark.parametrize("make", CYCLES, ids=["dict-cycle", "list-self-cycle"])
def test_dumps_line_rejects_cycle(make: Callable[[], dict[str, object]], guard: None) -> None:
    with pytest.raises(CanonError):
        dumps_line(make())


@pytest.mark.parametrize("make", CYCLES, ids=["dict-cycle", "list-self-cycle"])
def test_encode_value_rejects_cycle(make: Callable[[], dict[str, object]], guard: None) -> None:
    with pytest.raises(CanonError):
        encode_value(make(), at="", lex=LexHints())


def test_deep_acyclic_value_is_canon_error(guard: None) -> None:
    with pytest.raises(CanonError):
        dumps_line(_deep(5000))
    with pytest.raises(CanonError):
        encode_value(_deep(5000), at="", lex=LexHints())


def test_shared_acyclic_sub_object_stays_legal(guard: None) -> None:
    shared: dict[str, object] = {"x": [1, 2]}
    record: dict[str, object] = {"a": shared, "b": [shared, shared]}
    copied: dict[str, object] = {"a": {"x": [1, 2]}, "b": [{"x": [1, 2]}, {"x": [1, 2]}]}
    assert dumps_line(record) == dumps_line(copied)
    assert encode_value(record, at="", lex=LexHints()) == copied


def test_nesting_at_the_ingest_cap_still_writes(guard: None) -> None:
    assert dumps_line(_deep(256)).endswith(b'"leaf"' + b"]" * 256 + b"}\n")
