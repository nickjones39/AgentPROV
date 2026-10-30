"""The pin a profile census reads (``tools/agentdojo/profile_census.py`` ``census_pin``; D.6.12 item 15).

A part with ``observed`` counts is censused over its own git pin, or, when it has none, over the primary pin that serves it
through ``[import] variant_labels`` (agentdyn's ``c`` is a variant of the ``head`` pin, whose ``part`` is ``a``). Before
this, both the tool and ``tests/full_corpus/test_profile_census.py`` looked only for ``part == X and primary``, so
``(agentdyn, c)`` was always skipped as "no primary git pin" and the tool raised a bare ``StopIteration``.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from agentprov.adapters.profiles import load_profile
from agentprov.errors import ProfileError

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "agentdojo"))

import profile_census  # noqa: E402


def test_a_part_served_by_another_parts_pin_through_variant_labels_is_censused_over_that_pin():
    profile = load_profile("agentdyn")
    head = next(p for p in profile.data["source"]["pins"] if p.get("role") == "head")
    assert profile_census.census_pin(profile, "c") == dict(head)
    assert profile_census.census_pin(profile, "a") == dict(head)


def test_a_part_with_its_own_pin_is_censused_over_it():
    profile = load_profile("kavach-agentdojo")
    for part in ("main", "nav-fixer2", "rearch-forcedformat-fix"):
        assert profile_census.census_pin(profile, part)["part"] == part


def test_a_part_with_no_pin_is_a_profile_error_not_a_stop_iteration():
    with pytest.raises(ProfileError):
        profile_census.census_pin(load_profile("agentdyn"), "no-such-part")


def test_every_censused_part_resolves_a_pin():
    spec = importlib.util.spec_from_file_location("_full_corpus_profile_census", REPO / "tests" / "full_corpus" / "test_profile_census.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for profile_id, part in module._parts():
        assert profile_census.census_pin(load_profile(profile_id), part).get("kind"), (profile_id, part)
