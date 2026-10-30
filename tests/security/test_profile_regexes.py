"""SEC-21 / escaping audit F-11: the regular expressions shipped in source profiles are anchored and linear.

Profile regexes (denial patterns, the defence-suffix rule) run over source strings: error texts and pipeline names
from untrusted logs. Profiles are trusted data, so the hazard is a future profile edit; this test pins the shape of
every shipped one and times it on hostile 10 KB strings.
"""

from __future__ import annotations

import re
import time
import tomllib
from collections.abc import Iterator
from importlib import resources
from typing import Any

import pytest

from agentprov.adapters.profiles import profile_families

NESTED_QUANTIFIER = re.compile(r"\((?:[^()\\]|\\.)*[*+](?:[^()\\]|\\.)*\)[*+{]")  # (a+)+ / (x*)* shapes


def _walk(value: Any, path: str) -> Iterator[tuple[str, str]]:
    if isinstance(value, dict):
        for key, item in value.items():
            if "regex" in key and isinstance(item, str):
                yield f"{path}.{key}", item
            else:
                yield from _walk(item, f"{path}.{key}")
    elif isinstance(value, list):
        for i, item in enumerate(value):
            yield from _walk(item, f"{path}[{i}]")


def shipped_regexes() -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for family in profile_families():
        folder = resources.files("agentprov").joinpath("adapters", family, "profiles")
        for entry in sorted(folder.iterdir(), key=lambda e: e.name):
            if entry.name.endswith(".profile.toml"):
                found += _walk(tomllib.loads(entry.read_text(encoding="utf-8")), entry.name)
    return found


REGEXES = shipped_regexes()


def test_sec21_the_profiles_ship_regexes() -> None:
    assert len(REGEXES) >= 3, REGEXES  # agentdyn and rope denial patterns, the mandate defence suffix


@pytest.mark.parametrize(("where", "pattern"), REGEXES, ids=[w for w, _ in REGEXES])
def test_sec21_profile_regexes_are_anchored_and_have_no_nested_quantifier(where: str, pattern: str) -> None:
    re.compile(pattern)
    assert pattern.startswith("^") or pattern.endswith("$"), f"{where}: unanchored"
    assert NESTED_QUANTIFIER.search(pattern) is None, f"{where}: nested quantifier"


@pytest.mark.parametrize(("where", "pattern"), REGEXES, ids=[w for w, _ in REGEXES])
def test_sec21_profile_regexes_run_in_linear_time_on_hostile_strings(where: str, pattern: str) -> None:
    regex = re.compile(pattern)
    hostile = ["'" * 10_000, "The tool '" * 1_000, "ValidationError: The tool '" + "x" * 10_000,
               "-mandate_" * 1_000, "a" * 10_000 + "\n", "-mandate_intent\n", "\u2028" * 5_000]
    for text in hostile:
        start = time.perf_counter()
        regex.search(text)
        assert time.perf_counter() - start < 0.2, where


def test_sec21_the_defence_suffix_rule_rejects_a_trailing_newline() -> None:
    """``$`` matches before a final newline; ``identity.resolve`` also requires the match to end the name (F-11)."""
    from agentprov.adapters.agentdojo import identity

    table = {"model_from": "pipeline_name_minus_suffix", "defence_suffix_regex": "-(mandate_(?:envelope|scoped|intent))$"}
    good = identity.resolve(table, {}, "gpt-4o-mandate_intent")
    assert good.model == "gpt-4o" and good.defences == ("mandate_intent",)
    for hostile in ("gpt-4o-mandate_intent\n", "-mandate_intent", "gpt-4o-mandate_intent\u2028"):
        assert identity.resolve(table, {}, hostile).defences == ()
