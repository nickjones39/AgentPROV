"""The DTap text matcher ``dtap.alnum_norm@1`` (docs/architecture D.16.6, D.16.8; layer L4).

One deterministic normaliser serves three uses, so that the import reproduces the step-1 census exactly:

* injection markers (the SEM profile ``dtap.tools@1``): is a configured payload's text in something the run logged?
* the judge-to-attempt link of a re-run directory (the mapper, ``dtap.judge_attempt_by_content@1``);
* the census reproduction tool (``tools/dtap/census_reproduce.py``).

The normaliser (census ``c08_obs.an``): literal backslash escapes ``\\n``, ``\\r`` and ``\\t`` (two characters each) are
replaced by a space, the text is NFKC-folded and case-folded, and only alphanumeric characters (``str.isalnum``) are
kept. A **needle** is every string value of a payload whose normalised form has at least :data:`MIN_NEEDLE` characters.
A needle *fully* matches when it is a substring of the normalised haystack; otherwise one of its three
:data:`WINDOW`-character windows (start, middle, end) matching is a *partial* (window-only) match.

Values that are not strings are serialised as compact JSON (``ensure_ascii=False``) before normalisation, as the census
did. Nothing here evaluates text, and nothing reads a clock or the environment. Standard library only.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Iterable, Iterator
from typing import Any, Final, Literal

__all__ = [
    "JUDGE_LINK_MIN",
    "MIN_NEEDLE",
    "NORMALISER",
    "WINDOW",
    "Match",
    "match",
    "needles",
    "normalise",
    "serialise",
    "strings",
    "windows",
]

#: The rule reference of the normaliser (catalogue ``dtap`` v1).
NORMALISER: Final = "dtap.alnum_norm@1"
#: Minimum normalised length of a payload needle (D.16.6; profile ``matcher.min_needle``).
MIN_NEEDLE: Final = 24
#: Window length of a partial match (D.16.6; profile ``matcher.window``).
WINDOW: Final = 40
#: Minimum normalised length of a judge string used to link a judge to an attempt (D.16.8; ``matcher.judge_link_min``).
JUDGE_LINK_MIN: Final = 40
_ESC: Final = re.compile(r"\\[nrt]")

Match = Literal["full", "partial", "none"]


def normalise(text: str) -> str:
    """``dtap.alnum_norm@1``: escapes removed, NFKC, casefold, alphanumerics only."""
    folded = unicodedata.normalize("NFKC", _ESC.sub(" ", text)).casefold()
    return "".join(ch for ch in folded if ch.isalnum())


def serialise(value: object) -> str:
    """The text a value is matched as: a string verbatim, anything else as compact JSON (census ``ser``)."""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def strings(value: object) -> Iterator[str]:
    """Every string value inside ``value`` (object members and array items, depth first, source order)."""
    stack: list[Any] = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, str):
            yield item
        elif isinstance(item, dict):
            stack.extend(reversed(list(item.values())))
        elif isinstance(item, list):
            stack.extend(reversed(item))


def needles(value: object, *, minimum: int = MIN_NEEDLE) -> list[str]:
    """The normalised needles of a payload value: every string value at least ``minimum`` characters long once
    normalised, in source order, duplicates removed."""
    out: list[str] = []
    for text in strings(value):
        norm = normalise(text)
        if len(norm) >= minimum and norm not in out:
            out.append(norm)
    return out


def windows(needle: str, width: int = WINDOW) -> list[str]:
    """The start, middle and end windows of ``needle`` (the needle itself when it is not longer than ``width``)."""
    if len(needle) <= width:
        return [needle]
    middle = len(needle) // 2 - width // 2
    return [needle[:width], needle[middle:middle + width], needle[-width:]]


def match(needle_set: Iterable[str], haystack: str) -> Match:
    """The best match of any needle in a normalised haystack: ``full`` > ``partial`` (a window only) > ``none``."""
    best: Match = "none"
    if not haystack:
        return best
    for needle in needle_set:
        if needle in haystack:
            return "full"
        if best == "none" and any(w in haystack for w in windows(needle)):
            best = "partial"
    return best
