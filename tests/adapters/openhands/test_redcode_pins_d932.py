"""D-932: RedCode-OpenHands declares one primary pin role per trajectory zip (part ``head``), so each zip is imported as
its own snapshot with ``--pin <role> --snapshot <role>`` and verified against its own pin (D-33)."""

from __future__ import annotations

import argparse

import pytest

from agentprov.adapters.profiles import load_profile
from agentprov.cli.import_ import _capability, _pin

ROLES = ["oh-sonnet-s1", "oh-sonnet-s2", "oh-sonnet-s3", "oh-qwen3coder-s1", "oh-qwen3coder-s2", "oh-qwen3coder-s3"]


def args(**kw: object) -> argparse.Namespace:
    return argparse.Namespace(**{"pin": None, "snapshot": None, **kw})


def test_one_primary_pin_role_per_trajectory_zip() -> None:
    pins = load_profile("redcode-exec-openhands").data["source"]["pins"]
    primary = [p for p in pins if p.get("primary") is True]
    assert [p["role"] for p in primary] == ROLES and {p["part"] for p in primary} == {"head"}
    assert [p["file"] for p in primary] == [f"trajectories_OH-{r.split('-')[1]}_S{r[-1]}.zip" for r in ROLES]
    assert len({p["sha256"] for p in primary}) == 6 and [p["role"] for p in pins if not p.get("primary")] == ["supp"]


@pytest.mark.parametrize("role", ROLES)
def test_pin_selects_one_trajectory_zip_of_part_head(role: str) -> None:
    chosen = _pin(load_profile("redcode-exec-openhands"), args(pin=role), "head")
    assert chosen is not None and chosen["role"] == role and chosen["part"] == "head"
    _, capability = _capability("redcode-exec-openhands", None, args(pin=role, snapshot=role))
    assert capability.part == "head"  # the snapshot is named by the role; the registry part stays head
