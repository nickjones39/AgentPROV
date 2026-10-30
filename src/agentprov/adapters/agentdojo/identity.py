"""Identity resolution of AgentDojo-family logs, driven by the profile's tables (docs/architecture D.4.3-D.4.5, D.6.12
item 4; C.6.6).

Pure: a function of the file's layout facets, the logged ``pipeline_name`` and the ``[family.agentdojo.identity]`` table
(with its identity-table rows) only. ``model_from`` selects the mode:

* ``pipeline_dir`` / ``model_dir``: the model comes from that **directory** of the layout, never from ``pipeline_name``
  (``agentdojo.pipeline_dir_is_model_identity@1`` or the profile's ``rule``, class I).

  - With an identity ``table`` (D.4.5) the directory must have exactly one row; the row supplies model, defence
    (``none`` for none) and provider. An unknown directory resolves nothing (``identity_unresolved``).
  - Otherwise a ``[[identity.dir]]`` row whose ``pipeline_dir`` glob matches supplies the model and the rule it is
    asserted under (e.g. ``agentdojo.local_dir_model_identity@1``); else the model is the directory with its defence
    suffixes removed. Defences are the registered directory suffixes ``-<defence>``, stripped right to left and returned
    sorted by name (``agentdojo.defence_suffix@1``, class I; actors ``def0``, ``def1``, … in that order, erratum E6).
* ``pipeline_name_minus_suffix`` (Mandate): the model is the logged ``pipeline_name`` minus the suffix matched by
  ``defence_suffix_regex``; the matched suffix names the defence. The source pointer is ``/pipeline_name``.
* ``results_dir_slug`` (survey runs): the model is ``slug_to_model[<results_dir>]``; an unknown slug resolves nothing.

``pipeline_name_policy`` decides whether ``pipeline_name`` is compared at all: ``verbatim_unreliable_when_differs``
reports a value that differs from the directory (or from the row's ``pipeline_name`` list) as
``agentdojo.pipeline_name_mismatch``, never used to correct the identity; ``config_tag_never_model`` and
``constant_not_model`` never compare (the field is a configuration tag or a constant). Nothing is guessed.
"""

from __future__ import annotations

import fnmatch
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, Literal

__all__ = ["DEFAULT_MODEL_RULE", "Identity", "resolve", "resolve_identity"]

DEFAULT_MODEL_RULE: Final = "agentdojo.pipeline_dir_is_model_identity@1"


@dataclass(frozen=True, slots=True)
class Identity:
    """The resolved identity of one log."""

    pipeline_dir: str | None  # the directory the identity was read from (None: none, or not a directory mode)
    model: str | None  # None: unresolved
    model_rule: str
    defences: tuple[str, ...]  # sorted by name
    pipeline_name_mismatch: bool
    row: Mapping[str, Any] | None = None
    #: Where the identity was read: the origin path (a layout facet) or the logged ``/pipeline_name``.
    source: Literal["path", "pipeline_name"] = "path"
    provider: str | None = None

    @property
    def resolved(self) -> bool:
        """Whether anything was resolved (a directory or name was read); an unresolved file has no defence facts."""
        return self.model is not None or self.pipeline_dir is not None


def _strip_suffixes(name: str, suffixes: Sequence[str]) -> tuple[str, list[str]]:
    found: list[str] = []
    base = name
    changed = True
    while changed:
        changed = False
        for suffix in sorted(suffixes, key=len, reverse=True):
            tail = "-" + suffix
            if base.endswith(tail) and len(base) > len(tail):
                base = base[: -len(tail)]
                found.append(suffix)
                changed = True
                break
    return base, found


def _compares(table: Mapping[str, Any]) -> bool:
    return str(table.get("pipeline_name_policy", "verbatim_unreliable_when_differs")) == "verbatim_unreliable_when_differs"


def resolve_identity(pipeline_dir: str | None, pipeline_name: object, table: Mapping[str, Any],
                     rows: Mapping[str, Mapping[str, Any]] | None = None) -> Identity:
    """Resolve model and defences for a log whose run directory is ``pipeline_dir`` (``None`` when unknown)."""
    rule_default = str(table.get("rule") or DEFAULT_MODEL_RULE)
    if pipeline_dir is None or not pipeline_dir:
        return Identity(None, None, rule_default, (), False)
    compares = _compares(table)
    if rows:  # D.4.5: exactly one row per discovered directory; an unknown one resolves nothing
        row = rows.get(pipeline_dir)
        if row is None:
            return Identity(pipeline_dir, None, rule_default, (), False)
        defence = str(row.get("defence", "none"))
        named = row.get("pipeline_name")
        mismatch = compares and (pipeline_name != named if named is not None else pipeline_name != pipeline_dir)
        # phase-10d R4: a row may name a defence and no model (absent or "not_recorded"): the model resolves to nothing
        # (unk /model not_recorded, identity_unresolved), the row's defence is still written; no model is guessed (D-92)
        model = row.get("model")
        model = None if model is None or model == "not_recorded" else str(model)
        return Identity(pipeline_dir, model, rule_default, () if defence == "none" else (defence,), mismatch,
                        row, "path", row.get("provider"))
    suffixes = [str(s) for s in table.get("defence_suffixes", ())]
    base, defences = _strip_suffixes(pipeline_dir, suffixes)
    found = None
    for candidate in table.get("dir", ()):
        if fnmatch.fnmatchcase(pipeline_dir, str(candidate.get("pipeline_dir", ""))):
            found = candidate
            break
    if found is not None:
        model, rule = str(found["model"]), str(found.get("rule") or rule_default)
        names = found.get("pipeline_name")
        mismatch = compares and bool(names) and pipeline_name not in names
    else:
        model, rule = base, rule_default
        mismatch = compares and pipeline_name != pipeline_dir
    return Identity(pipeline_dir, model, rule, tuple(sorted(defences)), mismatch, found, "path",
                    found.get("provider") if found is not None else None)


def resolve(table: Mapping[str, Any], facets: Mapping[str, str | None], pipeline_name: object,
            rows: Mapping[str, Mapping[str, Any]] | None = None) -> Identity:
    """Dispatch on ``model_from`` (module docstring). ``facets`` are the file's layout components."""
    mode = str(table.get("model_from", "pipeline_dir"))
    rule = str(table.get("rule") or DEFAULT_MODEL_RULE)
    if mode in ("pipeline_dir", "model_dir"):
        key = facets.get(mode)
        if mode == "model_dir" and not key and table.get("model_dir_fallback") == "pipeline_dir":
            # regeneration-batch item 106 (D-254 addendum): a log with no experiment path above its pipeline directory
            # is keyed by that directory (a profile opt-in; D-104 tables keyed by the optional component)
            key = facets.get("pipeline_dir")
        return resolve_identity(key, pipeline_name, table, rows)
    if mode == "pipeline_name_minus_suffix":
        if not isinstance(pipeline_name, str) or not pipeline_name:
            return Identity(None, None, rule, (), False, source="pipeline_name")
        found = re.search(str(table["defence_suffix_regex"]), pipeline_name)
        if found is None or found.end() != len(pipeline_name) or found.start() == 0:
            return Identity(None, pipeline_name, rule, (), False, source="pipeline_name")
        defence = found.group(1) if found.groups() and found.group(1) else found.group(0).lstrip("-")
        return Identity(None, pipeline_name[: found.start()], rule, (defence,), False, source="pipeline_name")
    if mode == "results_dir_slug":
        slug = facets.get("results_dir")
        model = table.get("slug_to_model", {}).get(slug) if slug is not None else None
        return Identity(slug, str(model) if model is not None else None, rule, (), False)
    return Identity(None, None, rule, (), False)
