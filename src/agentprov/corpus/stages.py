"""The stage definitions of ``derivation.json`` as a map (HL H.8.2; D-380).

Every stage occurs once in ``derivation.json`` except ``expand``: one import can run several expansions with
different selections (an archive input, the declared nested archives inside it, and the container dialect's members,
D-380/D-382), and each is its own function with its own ``fn_digest``. So a stage map is keyed by the stage name, and an
``expand`` definition by ``("expand", fn_digest)``: a name-keyed map would keep only the last ``expand`` entry.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Final

__all__ = ["MULTI_STAGES", "StageKey", "has_stage", "in_order", "stage_key", "stage_map", "stages_named"]

#: Stages that may occur more than once, one entry per function digest.
MULTI_STAGES: Final = frozenset({"expand"})

StageKey = str | tuple[str, str]


def stage_key(definition: Mapping[str, Any]) -> StageKey:
    """``"<stage>"``, or ``("expand", fn_digest)`` for an ``expand`` definition."""
    name = str(definition.get("stage"))
    return (name, str(definition.get("fn_digest"))) if name in MULTI_STAGES else name


def stage_map(derivation: Mapping[str, Any] | None) -> dict[StageKey, dict[str, Any]]:
    """The stage definitions of a ``derivation.json`` document by :func:`stage_key`, in document order."""
    out: dict[StageKey, dict[str, Any]] = {}
    for stage in (derivation or {}).get("stages", ()):
        if isinstance(stage, dict) and isinstance(stage.get("stage"), str):
            out[stage_key(stage)] = stage
    return out


def stages_named(stages: Mapping[StageKey, Mapping[str, Any]], name: str) -> list[Mapping[str, Any]]:
    """Every definition of stage ``name``, in map order."""
    return [d for key, d in stages.items() if (key[0] if isinstance(key, tuple) else key) == name]


def has_stage(stages: Mapping[StageKey, Mapping[str, Any]], name: str) -> bool:
    return bool(stages_named(stages, name))


def in_order(stages: Mapping[StageKey, Mapping[str, Any]], order: Iterable[str]) -> list[Mapping[str, Any]]:
    """The definitions in the stage order ``order`` (several ``expand`` entries keep their map order)."""
    return [d for name in order for d in stages_named(stages, name)]
