"""The one message-role grouping of the analysis tools (tools/analysis, tools/analysis2; DTap sample check §9.1 b4).

AER keeps a message's ``role`` verbatim (C.3.4; D.15.1 forbids relabelling it): DTap-Bench writes ``agent`` where the
other sources write ``assistant`` (D-28; D.16.17 item 3). The screens that look at the model's own messages (A01
arguments, A03 empty turns, SA07 text-encoded calls, the marker probes) group the two here, so a DTap corpus is screened
like any other. The grouping mirrors phase 11's ``stats/field_groups.toml`` ``[message_roles]`` (``assistant = ["assistant",
"agent"]``); when that file is on ``main``, this table must stay equal to it. Only the analysis tools read it; the AER is
never changed.

Standard library only; imported by path (the tools are scripts, not a package).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

__all__ = ["MESSAGE_ROLES", "group_counts", "is_assistant", "role_group"]

#: group -> the verbatim AER message roles it holds.
MESSAGE_ROLES: Final[Mapping[str, tuple[str, ...]]] = {"assistant": ("assistant", "agent")}
_GROUP_OF: Final[Mapping[str, str]] = {role: group for group, roles in MESSAGE_ROLES.items() for role in roles}


def role_group(role: object) -> object:
    """The group of a verbatim message role (``agent`` -> ``assistant``); any other value is returned unchanged."""
    return _GROUP_OF.get(role, role) if isinstance(role, str) else role


def is_assistant(role: object) -> bool:
    """Whether ``role`` is a model-output message role (``assistant`` or DTap's ``agent``)."""
    return role_group(role) == "assistant"


def group_counts(counts: Mapping[str, int]) -> dict[str, int]:
    """Per-role counts (``{"agent": 3, "user": 1}``) summed per group (``{"assistant": 3, "user": 1}``)."""
    out: dict[str, int] = {}
    for role, n in counts.items():
        key = str(role_group(role))
        out[key] = out.get(key, 0) + n
    return out
