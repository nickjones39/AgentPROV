"""Regen item 64 (CA-5): a scalar ``artifacts`` in an untrusted header yields findings, not a ``TypeError``.

The validator already iterates ``artifacts`` only when it is a list; ``LocatorResolver`` iterated any truthy value, so
a header with ``"artifacts": 1`` (or ``True``, ``1.5``) validated with a raw store raised from the resolver instead of
reporting the schema finding. The resolver now applies the same list guard and knows no artefacts.
"""

from __future__ import annotations

import pytest
from aer_support import edit, example_records, example_store, validate_example

from agentprov.aer.locators import LocatorError, LocatorResolver

SCALARS = [1, True, 1.5]


@pytest.mark.parametrize("bad", SCALARS, ids=repr)
def test_scalar_artifacts_with_store_reports_schema_finding(bad: object) -> None:
    records = edit(example_records(), "exec", artifacts=bad)
    report = validate_example(records, with_store=True)
    assert not report.ok
    assert ("aer.schema.pattern", "/artifacts") in {(f.code, f.pointer) for f in report.errors}
    without = validate_example(records, with_store=False)
    assert ("aer.schema.pattern", "/artifacts") in {(f.code, f.pointer) for f in without.errors}


@pytest.mark.parametrize("bad", SCALARS, ids=repr)
def test_resolver_ignores_scalar_artifacts(bad: object) -> None:
    resolver = LocatorResolver({"artifacts": bad}, example_store())
    with pytest.raises(LocatorError):
        resolver.artefact_bytes("a0")
