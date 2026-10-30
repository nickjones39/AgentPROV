"""Attack construction without the baseline ``MODEL_NAMES`` mutation (D.10.5; D.10.9 A10; K.8.1).

The baseline wrote ``MODEL_NAMES[model_id] = model_id.replace("-", " ").title()`` into AgentDojo's global table so that
``get_model_name_from_pipeline`` would find a display name (``generate.py:299-302``): a hidden, persistent edit of the
benchmark that put a derived name into the attack payload. ``AttackFactory`` replaces it:

* the stock attack class from ``agentdojo.attacks.attack_registry.ATTACKS`` is constructed against the real suite and
  the pipeline; if that succeeds (the pipeline name contains a ``MODEL_NAMES`` key, or the attack needs no model
  name), nothing else happens;
* if construction fails because the stock table has no name for the pipeline, ``cell.attack_params.
  model_display_name`` is required (``UnsupportedConfiguration`` otherwise). The attack is then constructed inside
  ``scoped_model_name``, a context manager that adds ``MODEL_NAMES[pipeline.name] = display_name`` and **restores the
  table on exit** (construction only: the stock attacks read the name in ``__init__``,
  ``important_instructions_attacks.py:40-43``, ``dos_attacks.py:27-29``), and the result is checked with
  ``attack.model_name == display_name`` for the attacks that take their ``model_name`` from the pipeline. The use is
  declared as instrumentation ``agentdojo.attack_model_display_name@1`` (kind ``attack_parameter``);
* a display name that contradicts the stock table's name for the pipeline is refused;
* instead of a name, ``cell.attack_params.model_display_name_preset`` may name a **declared preset** that derives the
  name from the requested model id (``DISPLAY_NAME_PRESETS``). The only preset is ``adprov-v2.3-title-case``, the
  baseline rule ``model_id.replace("-", " ").title()`` (``generate.py:299-302``), kept so that gate C6 (J.3.4) and a
  v2.3-comparable plan can reproduce the v2.3 attack text (F-13). It applies exactly where an explicit name would
  (only when the stock table has no entry for the pipeline), the item's ``params`` record ``preset`` beside
  ``display_name``, and a preset given together with an explicit name must agree with it.

**Benchmark fallback names (the AutoDojo fork).** The fork's ``get_model_name_from_pipeline`` returns ``"AI assistant"``
instead of raising when ``MODEL_NAMES`` has no entry (fork ``base_attacks.py:145-146``), so stock construction succeeds
silently with that name. The factory detects the fallback (``benchmark_fallback_name``) and (a) with an explicit
``model_display_name`` uses the scoped registration exactly as for stock AgentDojo (the item's ``params`` add
``benchmark_fallback``); (b) without one keeps the fork's stock behaviour and declares it: the item
``agentdojo.attack_model_display_name@1`` with ``params.source = "benchmark_fallback"`` for the attacks that put the name
into the payload. Stock AgentDojo has no fallback, and nothing changes there.

**Scoped environment.** ``create(..., env_overrides=...)`` sets the given variables in ``os.environ`` for the attack's
construction only and restores them afterwards (``scoped_environ``). The fork's ``autodojo`` attack reads
``AUTODOJO_CACHE`` and ``AUTODOJO_VARIANT`` in ``__init__`` (``autodojo_attack.py``), so the worker sets them per cell
from ``run_cell.attack_env``, never from its process environment (D.11.7).

``RecordingAttack`` is a delegating proxy: ``attack()`` returns the stock injections unchanged and records one
``fixture`` event per injection vector (``kind: injection_payload``, ``vector``, ``content`` = that vector's payload).
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any

__all__ = [
    "DISPLAY_NAME_PRESETS",
    "AttackFactory",
    "BuiltAttack",
    "MODEL_NAME_ATTRIBUTES",
    "PIPELINE_NAMED_ATTACKS",
    "RecordingAttack",
    "UnsupportedConfiguration",
    "benchmark_fallback_name",
    "scoped_environ",
    "scoped_model_name",
]

ITEM_DISPLAY_NAME = "agentdojo.attack_model_display_name@1"

#: Stock attacks whose ``model_name`` is the pipeline's display name (checked after a scoped registration).
PIPELINE_NAMED_ATTACKS = frozenset({
    "important_instructions",
    "important_instructions_no_user_name",
    "important_instructions_wrong_user_name",
    "tool_knowledge",
    "dos",
    "swearwords_dos",
    "captcha_dos",
    "offensive_email_dos",
    "felony_dos",
    "autodojo",  # the AutoDojo fork's cache-replay attack: its fallback wrapper names the model (`_model_name`)
})
#: Where an attack keeps the display name it took from the pipeline (default ``model_name``).
MODEL_NAME_ATTRIBUTES: Mapping[str, str] = {"autodojo": "_model_name"}


def _title_case(model_id: str) -> str:
    """``generate.py:301`` at ``579a908``: ``model_id.replace("-", " ").title()``."""
    return model_id.replace("-", " ").title()


#: Declared display-name presets: ``attack_params.model_display_name_preset`` -> rule over the requested model id.
DISPLAY_NAME_PRESETS: Mapping[str, Callable[[str], str]] = {"adprov-v2.3-title-case": _title_case}


class UnsupportedConfiguration(ValueError):
    """A configuration the v0.1 harness refuses (defended pipeline, non-YAML output, unknown attack, missing display
    name, malformed plan)."""


@contextlib.contextmanager
def scoped_model_name(pipeline_name: str, display_name: str) -> Iterator[None]:
    """Temporarily register ``MODEL_NAMES[pipeline_name] = display_name``; the table is restored on exit."""
    from agentdojo.models import MODEL_NAMES

    had = pipeline_name in MODEL_NAMES
    old = MODEL_NAMES.get(pipeline_name)
    MODEL_NAMES[pipeline_name] = display_name
    try:
        yield
    finally:
        if had:
            MODEL_NAMES[pipeline_name] = old  # type: ignore[assignment]
        else:
            del MODEL_NAMES[pipeline_name]


@contextlib.contextmanager
def scoped_environ(overrides: Mapping[str, str] | None) -> Iterator[None]:
    """Temporarily set ``os.environ[k] = v`` for each override; every previous value (or absence) is restored."""
    saved = {k: os.environ.get(k) for k in (overrides or {})}
    try:
        for k, v in (overrides or {}).items():
            os.environ[k] = v
        yield
    finally:
        for k, old in saved.items():
            if old is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = old


def benchmark_fallback_name(pipeline: Any) -> str | None:
    """The name the installed benchmark's ``get_model_name_from_pipeline`` returns when ``MODEL_NAMES`` has no entry
    (the fork's ``"AI assistant"``), or ``None`` when it raises (stock AgentDojo 0.1.35)."""
    from agentdojo.attacks.base_attacks import get_model_name_from_pipeline

    try:
        name = get_model_name_from_pipeline(pipeline)
    except ValueError:
        return None
    return name if isinstance(name, str) else None


def stock_display_name(pipeline_name: str) -> str | None:
    """What ``get_model_name_from_pipeline`` would return for this name, or ``None`` (no stock entry)."""
    from agentdojo.models import MODEL_NAMES

    for full_name, model_name in MODEL_NAMES.items():
        if full_name in pipeline_name:
            return model_name
    return None


@dataclass(frozen=True)
class BuiltAttack:
    attack: Any
    instrumentation: tuple[Mapping[str, Any], ...]


class AttackFactory:
    """Builds stock attacks for one suite and pipeline (see the module docstring)."""

    def __init__(self, suite: Any, pipeline: Any) -> None:
        self.suite = suite
        self.pipeline = pipeline

    def create(self, attack_name: str, attack_params: Mapping[str, Any], *, model_id: str | None = None,
               env_overrides: Mapping[str, str] | None = None) -> BuiltAttack:
        with scoped_environ(env_overrides):
            return self._create(attack_name, attack_params, model_id=model_id)

    def _create(self, attack_name: str, attack_params: Mapping[str, Any], *, model_id: str | None) -> BuiltAttack:
        from agentdojo.attacks.attack_registry import ATTACKS

        if attack_name not in ATTACKS:
            raise UnsupportedConfiguration(f"unknown attack {attack_name!r}")
        cls = ATTACKS[attack_name]
        display = attack_params.get("model_display_name")
        if display is not None and not isinstance(display, str):
            raise UnsupportedConfiguration("attack_params.model_display_name must be a string")
        preset = attack_params.get("model_display_name_preset")
        if preset is not None:
            if preset not in DISPLAY_NAME_PRESETS:
                raise UnsupportedConfiguration(f"unknown attack_params.model_display_name_preset {preset!r}")
            if not isinstance(model_id, str) or not model_id:
                raise UnsupportedConfiguration("a display-name preset needs the requested model id")
            derived = DISPLAY_NAME_PRESETS[preset](model_id)
            if display is not None and display != derived:
                raise UnsupportedConfiguration(
                    f"model_display_name {display!r} contradicts preset {preset!r} ({derived!r})")
        name = self.pipeline.name
        stock = stock_display_name(name) if isinstance(name, str) else None
        if preset is not None and stock is None:
            # the baseline registered its derived name only where the stock table had none (and the stock keys, first
            # in the table, win its substring lookup): the preset applies exactly there
            display = derived
        if display is not None and stock is not None and display != stock:
            raise UnsupportedConfiguration(
                f"model_display_name {display!r} contradicts the stock MODEL_NAMES entry for this pipeline")
        checked = attack_name in PIPELINE_NAMED_ATTACKS
        attribute = MODEL_NAME_ATTRIBUTES.get(attack_name, "model_name")
        fallback = benchmark_fallback_name(self.pipeline) if stock is None else None
        if fallback is not None and display:
            # the fork would silently use its fallback name; the explicit name is registered as for stock AgentDojo
            return self._scoped(cls, attack_name, name, display, preset, checked, attribute, fallback)
        try:
            attack = cls(self.suite, self.pipeline)
        except ValueError as exc:
            if stock is not None or "No valid model name" not in str(exc):
                raise
        else:
            if fallback is not None and checked:
                item = {
                    "id": ITEM_DISPLAY_NAME,
                    "kind": "attack_parameter",
                    "recorded": "full",
                    "params": {"display_name": getattr(attack, attribute, fallback), "attack": attack_name,
                               "checked": True, "source": "benchmark_fallback"},
                    "detail": "MODEL_NAMES has no entry for the pipeline name and the installed benchmark's "
                              "get_model_name_from_pipeline returned its fallback name; nothing was registered",
                }
                return BuiltAttack(attack, (item,))
            return BuiltAttack(attack, ())
        if display is None or not display:
            raise UnsupportedConfiguration(
                f"attack {attack_name!r} names the model, and the pipeline name has no stock MODEL_NAMES entry: "
                "attack_params.model_display_name (--model-display-name) is required")
        return self._scoped(cls, attack_name, name, display, preset, checked, attribute, None)

    def _scoped(self, cls: Any, attack_name: str, name: str, display: str, preset: Any, checked: bool,
                attribute: str, fallback: str | None) -> BuiltAttack:
        with scoped_model_name(name, display):
            attack = cls(self.suite, self.pipeline)
        if checked and getattr(attack, attribute, display) != display:
            raise UnsupportedConfiguration("the attack did not take the scoped display name")
        item = {
            "id": ITEM_DISPLAY_NAME,
            "kind": "attack_parameter",
            "recorded": "full",
            "params": {"display_name": display, "attack": attack_name, "checked": checked,
                       **({"preset": preset} if preset is not None else {}),
                       **({"benchmark_fallback": fallback} if fallback is not None else {})},
            "detail": "MODEL_NAMES had no entry for the pipeline name; a scoped registration was used for attack "
                      "construction only and the table was restored",
        }
        return BuiltAttack(attack, (item,))


class RecordingAttack:
    """Delegating proxy over a stock attack: ``attack()`` records the injections it returns as fixtures."""

    def __init__(self, inner: Any, hooks: Any) -> None:
        object.__setattr__(self, "_inner", inner)
        object.__setattr__(self, "_hooks", hooks)

    def attack(self, user_task: Any, injection_task: Any) -> dict[str, str]:
        injections = self._inner.attack(user_task, injection_task)
        for vector, payload in injections.items():
            self._hooks.fixture("injection_payload", vector, payload)
        return injections

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def __setattr__(self, name: str, value: Any) -> None:
        setattr(self._inner, name, value)
