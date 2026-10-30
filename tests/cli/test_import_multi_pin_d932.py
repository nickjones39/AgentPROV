"""D-932: ``import`` without ``--pin`` refuses a part with several primary pins (RedCode-OpenHands: six trajectory
zips) instead of reading only its first pin; a part with one primary pin is unchanged."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import pytest

from agentprov.adapters.profiles import load_profile
from agentprov.cli.common import CliUsageError
from agentprov.cli.import_ import _pin

ADAPTERS = Path(__file__).resolve().parents[2] / "src" / "agentprov" / "adapters"


def args(**kw: object) -> argparse.Namespace:
    return argparse.Namespace(**{"pin": None, "snapshot": None, **kw})


def test_without_pin_a_part_with_several_primary_pins_is_refused() -> None:
    profile = load_profile("redcode-exec-openhands")
    roles = [str(p["role"]) for p in profile.data["source"]["pins"] if p.get("primary") is True]
    with pytest.raises(CliUsageError) as exc:
        _pin(profile, args(), "head")
    message = str(exc.value)
    assert f"{len(roles)} primary pins" in message and all(r in message for r in roles) and "--pin" in message


def test_a_part_with_one_primary_pin_is_taken_without_pin() -> None:
    profile = load_profile("kavach-agentdojo")
    assert _pin(profile, args(), "main")["role"] == "main"


def test_no_other_profile_part_has_several_primary_pins() -> None:
    """The guard changes nothing elsewhere."""
    import tomllib

    multi = {}
    for path in sorted(ADAPTERS.glob("*/profiles/*.profile.toml")):
        pins = tomllib.loads(path.read_text()).get("source", {}).get("pins", [])
        counts = Counter(p.get("part") for p in pins if p.get("primary") is True)
        multi.update({f"{path.name}:{part}": n for part, n in counts.items() if n > 1})
    assert multi == {"redcode-exec-openhands.profile.toml:head": 6}
