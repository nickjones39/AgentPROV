"""D-540: the facade ``agentprov.api.check_claim`` forwards every keyword of the claims library (M.6; I.5.6).

Without ``agent_executions_only`` and ``phrase`` a correct ``agent_execution`` or ``coverage_claim`` value always
failed through the facade (CC-17), so DoD Q.11b could not pass for them.
"""

from __future__ import annotations

import inspect

from agentprov import api
from agentprov.adapters.registry import claims


def _keyword_only(fn) -> dict[str, inspect.Parameter]:  # type: ignore[no-untyped-def]
    return {n: p for n, p in inspect.signature(fn).parameters.items() if p.kind is inspect.Parameter.KEYWORD_ONLY}


def test_the_facade_accepts_every_keyword_of_the_library_with_the_same_defaults():
    library, facade = _keyword_only(claims.check_claim), _keyword_only(api.check_claim)
    assert set(library) == set(facade)
    assert {n: p.default for n, p in library.items()} == {n: p.default for n, p in facade.items()}


def test_the_facade_returns_what_the_library_returns():
    assert api.check_claim(["rope"], ["agent_execution"], agent_executions_only=True) == []
    assert api.check_claim(["rope"], ["agent_execution"])  # still a violation without the scope
    phrase = api.coverage_phrase()
    assert api.check_claim([], ["coverage_claim"], phrase=phrase) == []
    assert api.check_claim([], ["coverage_claim"], location="paper.tex:12", phrase="demonstrated on many sources") == \
        claims.check_claim([], ["coverage_claim"], location="paper.tex:12", phrase="demonstrated on many sources")
