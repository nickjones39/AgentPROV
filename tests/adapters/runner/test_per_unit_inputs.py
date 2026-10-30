"""Runner items R1-R3 of docs/architecture D.16.14 are additive: a family without ``auxiliary_for`` or
``register_detail`` sees exactly the phase-6 behaviour (the DTap tests in tests/adapters/dtap/test_import.py exercise the
items themselves)."""

from __future__ import annotations

import json

import pytest

from agentprov.adapters.runner import NotOfDialect, map_artefact_total
from agentprov.adapters.runner.importer import _AuxListing
from agentprov.adapters.types import Origin
from agentprov.errors import MalformedArtefact


def test_a_reader_without_a_register_detail_keeps_the_default():
    data = json.dumps({"something": "else"}).encode()
    with pytest.raises(NotOfDialect) as info:
        map_artefact_total(data, Origin.local("/x/a.json"), profile_id="agentdojo-upstream")
    assert info.value.detail is None and isinstance(info.value, MalformedArtefact)


def test_the_listing_answers_siblings_and_context_existence():
    listing = _AuxListing(["a/b/1.json", "a/b/judge.json", "a/c/2.json"], {"tasks": ["x/config.yaml"]})
    assert listing.siblings("a/b/1.json") == ("a/b/1.json", "a/b/judge.json")
    assert listing.exists("a/c/2.json") and listing.exists("tasks:x/config.yaml") and not listing.exists("tasks:y")


def test_families_without_per_unit_inputs_do_not_plan_them():
    from agentprov.adapters.registry import READERS
    from agentprov.adapters.runner import resolve_factory

    for dialect, factory in READERS.items():
        has = callable(getattr(resolve_factory(factory)(), "auxiliary_for", None))
        assert has == (dialect in {"dtap.trajectory", "openhands.events", "agentops.trace", "autogen.runs",
                                   "wirelog.request_response", "geminicli.stream_json",
                                   "qwencode.json"}), dialect
        # agentops: D-194; autogen: D-302; wirelog: D-281; geminicli: D-330; qwencode: D-572
