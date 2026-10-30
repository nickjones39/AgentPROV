"""SEC-07 / escaping audit F-08: the archive selection globs of every shipped profile stay linear on hostile labels.

``raw.members`` compiles profile globs with ``glob.translate``. A segment with several ``*`` separated by literals
(``*a*a*a*b*``) backtracks super-linearly (measured: 80 s on a 200-character label), so a profile author could make
member selection a denial of service. Profiles are trusted package data and no shipped pattern has that shape; this
test keeps it so, and since D-59 (phase 12b, the expand bundle) ``Selection`` refuses a segment with more than two ``*``.
"""

from __future__ import annotations

import time

import pytest

from agentprov.adapters.profiles import load_profile
from agentprov.ingest.limits import IngestLimits
from agentprov.raw.members import MembersError, Selection, _compile

PROFILES = {"survey-agentharm": "inspect"}  # the profiles whose reader declares container member patterns


def shipped_patterns() -> list[tuple[str, str]]:
    from agentprov.adapters.inspect.dialect import InspectEvalReader

    return [(pid, p) for pid in PROFILES for p in InspectEvalReader.member_patterns(load_profile(pid))]


def stars_per_segment(pattern: str) -> int:
    return max(seg.count("*") for seg in pattern.split("/") if seg != "**")


def test_sec07_every_shipped_member_pattern_has_at_most_two_wildcards_per_segment() -> None:
    patterns = shipped_patterns()
    assert patterns, "the Inspect profile declares its member patterns"
    assert all(stars_per_segment(p) <= 2 for _, p in patterns), patterns


@pytest.mark.parametrize("filler", ["_epoch_", "a", "*", "_", ".json"])
def test_sec07_shipped_member_patterns_match_hostile_labels_in_linear_time(filler: str) -> None:
    limit = IngestLimits().max_name_bytes
    regex = _compile(sorted({p for _, p in shipped_patterns()}))
    assert regex is not None
    for prefix in ("samples/", "", "header.json/"):
        label = (prefix + filler * limit)[:limit]
        start = time.perf_counter()
        regex.match(label)
        assert time.perf_counter() - start < 0.2


def test_sec07_selection_wildcards_do_not_cross_directories() -> None:
    """The ``expand`` matcher is ``glob`` (a ``*`` stays in its segment), not ``fnmatch`` (whose ``*`` crosses ``/``)."""
    regex = _compile(Selection(include=("samples/*_epoch_*.json",)).include)
    assert regex is not None
    assert regex.match("samples/1-1_epoch_1.json")
    assert not regex.match("samples/x/1-1_epoch_1.json") and not regex.match("samples/1_epoch_/x.json")


@pytest.mark.parametrize("pattern", ["*a*a*a*b*", "runs/*x*y*.json", "a/***/b", "**/*_*_*.json"])
def test_sec07_a_segment_with_more_than_two_wildcards_is_refused(pattern: str) -> None:
    """F-08 / D-59: the super-linear shape is refused when the selection is built, before anything is compiled."""
    with pytest.raises(MembersError):
        Selection(include=(pattern,))
    with pytest.raises(MembersError):
        Selection(nested=(pattern,))


@pytest.mark.parametrize("pattern", ["**", "**/*.json", "samples/*_epoch_*.json", "data/*.tar.gz", "a/**/b/*x*"])
def test_sec07_patterns_with_at_most_two_wildcards_per_segment_are_kept(pattern: str) -> None:
    assert Selection(include=(pattern,)).include == (pattern,)
