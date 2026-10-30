"""SPDX licence-family predicates shared by sealing and deposit metadata (HL H.10.6; D-25, D-42).

Licence families are tested per simple term of an SPDX expression (split on whitespace and parentheses, dropping the
``WITH`` / ``AND`` / ``OR`` operators), not by an anchored whole-id match or a substring: ``GPL-2.0+``,
``GPL-2.0-with-classpath-exception`` and ``GPL-3.0-only WITH GCC-exception-3.1`` are all GPL, and
``PolyForm-Noncommercial-1.0.0`` is non-commercial like ``CC-BY-NC-4.0``. The predicates live here, not in
:mod:`agentprov.release.metadata`, because ``release`` imports ``corpus``: :func:`agentprov.corpus.package.seal` sets
``licences.redistribution`` with :func:`is_non_commercial`, the same test the deposit's licence class uses.
"""

from __future__ import annotations

import re
from typing import Final

__all__ = ["is_copyleft", "is_non_commercial", "spdx_terms"]

_NC: Final = re.compile(r"(^|-)NC(-|$)|non-?commercial", re.IGNORECASE)
_COPYLEFT: Final = re.compile(r"(A?GPL|LGPL)-[0-9]", re.IGNORECASE)
_SPDX_OPERATORS: Final = frozenset({"WITH", "AND", "OR"})


def spdx_terms(spdx: str) -> list[str]:
    """The simple terms (licence and exception ids) of an SPDX expression."""
    return [t for t in re.split(r"[\s()]+", spdx) if t and t.upper() not in _SPDX_OPERATORS]


def is_copyleft(spdx: str) -> bool:
    """Whether any term of ``spdx`` is a GPL, AGPL or LGPL licence."""
    return any(_COPYLEFT.match(t) for t in spdx_terms(spdx))


def is_non_commercial(spdx: str) -> bool:
    """Whether any term of ``spdx`` is non-commercial (``…-NC-…``, ``…Noncommercial…``)."""
    return any(_NC.search(t) for t in spdx_terms(spdx))
