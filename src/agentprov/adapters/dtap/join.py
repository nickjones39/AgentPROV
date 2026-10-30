"""Task-configuration join of a DTap run (docs/architecture D.16.5; D-28 g; layer L4).

**Path rule** (``dtap.config_path_join@1``, D): :func:`agentprov.adapters.dtap.dialect.config_path`.

**Allowlist** (D.16.13): a configuration is parsed with :func:`agentprov.ingest.yamlsafe.safe_load` and immediately
reduced to ``Task``, ``Attack`` and ``Agent.system_prompt`` (:func:`allowlisted`). Every other member, in particular
``Agent.mcp_servers[].env_vars``, is dropped before any other code sees the document, and any ``env_vars`` member left
inside the allowlisted tables is dropped too. Values YAML 1.1 types implicitly (dates) become their ISO text, the
text they were written as; the conversions are counted.

**Verification tier** (``dtap.config_join_tier@1``, D): two text checks, each a deterministic comparison of observed
strings (the census ``c07g``/``c07i`` classification, so step 4 reproduces it):

* *instruction*: ``task_info.original_instruction`` against what the agent receives (benign and indirect:
  ``Task.task_instruction``; direct: the best of the ``prompt`` steps' content and the goal; ``direct_prompt``: the
  goal; ``direct_no_attack``: not applicable);
* *goal*: ``task_info.malicious_instruction`` against ``Attack.malicious_goal`` (benign and no-attack runs: the run text
  must be empty).

Relations, best first: ``exact``; ``whitespace`` (equal after whitespace normalisation); ``prefix_500`` (instruction
only: the run text is exactly 500 characters and a prefix of the configuration text); ``prefix`` (goal only: the
configuration goal is a prefix of the run text, which appends attacker-account details); ``goal_plus_information`` (goal
only: the run text is goal + ``Attack.additional_information``); ``run_prefix`` (the run text is a shorter prefix),
``config_prefix`` (instruction only: the configuration text is a prefix of the run text), ``differs``, ``absent``. Tier ``A``:
both verify; ``B``: one; ``C``: neither. ``task_id`` is a third, recorded check that never changes the tier, with the two
evidenced normalisations (``offset_medical``, ``reformatted``).
"""

from __future__ import annotations

import datetime as _dt
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final

from agentprov.adapters.dtap.dialect import PathFacets

__all__ = [
    "GOAL_OK",
    "INSTRUCTION_OK",
    "Join",
    "allowlisted",
    "attack_steps",
    "compare",
    "task_id_relation",
    "verify",
]

_WS: Final = re.compile(r"\s+")
INSTRUCTION_OK: Final = frozenset({"exact", "whitespace", "prefix_500", "not_applicable"})
GOAL_OK: Final = frozenset({"exact", "whitespace", "prefix", "goal_plus_information"})
_ORDER: Final = ("exact", "whitespace", "prefix_500", "run_prefix", "config_prefix", "differs", "absent")
#: Domains whose task ids differ only in format (D.16.5; ``dtap.task_id_reformatted@1``).
REFORMAT_DOMAINS: Final = frozenset({"telecom", "browser", "customer-service"})
_TRAILING_NUMBER: Final = re.compile(r"^(.*?)([0-9]+)$")
#: The longest trailing number compared as an integer (task numbers have three digits; longer ids just differ).
_MAX_ID_DIGITS: Final = 18


def _nws(text: str) -> str:
    return _WS.sub(" ", text).strip()


def _plain(value: object, counts: list[int]) -> Any:
    """``value`` with YAML-only scalars made JSON (a date becomes its ISO text) and every ``env_vars`` member dropped."""
    if isinstance(value, dict):
        return {str(k): _plain(v, counts) for k, v in value.items() if k != "env_vars"}
    if isinstance(value, list):
        return [_plain(v, counts) for v in value]
    if isinstance(value, (_dt.date, _dt.datetime, _dt.time)):
        counts[0] += 1
        return value.isoformat()
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    counts[0] += 1
    return str(value)


def allowlisted(document: object) -> tuple[dict[str, Any] | None, int]:
    """The allowlisted configuration (``Task``, ``Attack``, ``Agent.system_prompt``) and the number of converted YAML
    scalars; ``None`` when the document is not a mapping."""
    if not isinstance(document, dict):
        return None, 0
    counts = [0]
    out: dict[str, Any] = {}
    for table in ("Task", "Attack"):
        if isinstance(document.get(table), dict):
            out[table] = _plain(document[table], counts)
    agent = document.get("Agent")
    if isinstance(agent, dict) and "system_prompt" in agent:
        out["Agent"] = {"system_prompt": _plain(agent["system_prompt"], counts)}
    return out, counts[0]


def attack_steps(config: Mapping[str, Any]) -> list[tuple[int, int, Mapping[str, Any]]]:
    """``(turn index, step index, step)`` for every ``Attack.attack_turns[].attack_steps[]`` object, in file order."""
    attack = config.get("Attack")
    if not isinstance(attack, dict):
        return []
    out: list[tuple[int, int, Mapping[str, Any]]] = []
    for t, turn in enumerate(attack.get("attack_turns") or []):
        if not isinstance(turn, dict):
            continue
        for s, step in enumerate(turn.get("attack_steps") or []):
            if isinstance(step, dict):
                out.append((t, s, step))
    return out


def compare(run: object, config: object, *, instruction: bool) -> str:
    """The relation of a run text to a configuration text (module docstring)."""
    if not isinstance(run, str) or not isinstance(config, str):
        return "absent"
    if run == config:
        return "exact"
    nr, nc = _nws(run), _nws(config)
    if nr == nc:
        return "whitespace"
    if nr and nc.startswith(nr):
        return "prefix_500" if instruction and len(run) == 500 else "run_prefix"
    if nc and nr.startswith(nc):
        return "config_prefix" if instruction else "prefix"
    return "differs"


def task_id_relation(run_id: object, config_id: object, domain: str) -> str:
    """``equal``, ``offset_medical``, ``reformatted``, ``differs`` or ``absent`` (D.16.5; recorded, never a tier)."""
    if not isinstance(run_id, str) or not isinstance(config_id, str):
        return "absent"
    if run_id == config_id:
        return "equal"
    if domain == "medical":
        a, b = _TRAILING_NUMBER.match(run_id), _TRAILING_NUMBER.match(config_id)
        # bounded before int(): a digit run beyond CPython's 4,300-digit limit raised ValueError (regen item 56)
        if a and b and a.group(1) == b.group(1) and max(len(a.group(2)), len(b.group(2))) <= _MAX_ID_DIGITS \
                and int(a.group(2)) + 1 == int(b.group(2)):
            return "offset_medical"
    if domain in REFORMAT_DOMAINS:
        na, nb = re.sub(r"[^0-9a-z]", "", run_id.lower()), re.sub(r"[^0-9a-z]", "", config_id.lower())
        if na == nb or (na and nb.startswith(na) and nb[len(na):].isdigit()):
            return "reformatted"
    return "differs"


@dataclass
class Join:
    """The join of one run: status, tier and the three recorded checks (``ext.dtap.join``)."""

    config_path: str
    status: str  # joined | missing | unparseable
    tier: str | None = None  # A | B | C (joined only)
    instruction: str | None = None
    goal: str | None = None
    task_id: str | None = None
    yaml_converted: int = 0
    config: dict[str, Any] | None = field(default=None, repr=False)

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"config_path": self.config_path, "status": self.status}
        for name in ("tier", "instruction", "goal", "task_id"):
            value = getattr(self, name)
            if value is not None:
                out[name] = value
        if self.yaml_converted:
            out["yaml_scalars_as_text"] = self.yaml_converted
        return out


def verify(facets: PathFacets, task_info: Mapping[str, Any], config: Mapping[str, Any]) -> tuple[str, str, str, str]:
    """``(tier, instruction relation, goal relation, task_id relation)`` of a joined run."""
    task_value, attack_value = config.get("Task"), config.get("Attack")
    task: Mapping[str, Any] = task_value if isinstance(task_value, dict) else {}
    attack: Mapping[str, Any] = attack_value if isinstance(attack_value, dict) else {}
    goal = attack.get("malicious_goal")
    original = task_info.get("original_instruction")
    split = facets.split_label
    if split in ("benign", "indirect"):
        ins = compare(original, task.get("task_instruction"), instruction=True)
    elif split == "direct":
        candidates = [s.get("content") for _t, _s, s in attack_steps(config)
                      if s.get("type") == "prompt" and isinstance(s.get("content"), str)]
        if isinstance(goal, str):
            candidates.append(goal)
        found = [compare(original, c, instruction=True) for c in candidates] or ["absent"]
        ins = min(found, key=_ORDER.index)
    elif split == "direct_prompt":
        ins = compare(original, goal, instruction=True)
    else:
        ins = "not_applicable"
    malicious = task_info.get("malicious_instruction")
    if split in ("benign", "direct_no_attack"):
        gl = "exact" if malicious == "" else "differs"
    else:
        gl = compare(malicious, goal, instruction=False)
        extra = attack.get("additional_information")
        if gl in ("prefix", "differs") and isinstance(goal, str) and isinstance(extra, str) and isinstance(malicious, str) \
                and _nws(malicious) == _nws(goal + " " + extra):
            gl = "goal_plus_information"
    ok_i, ok_g = ins in INSTRUCTION_OK, gl in GOAL_OK
    tier = "A" if ok_i and ok_g else ("B" if ok_i or ok_g else "C")
    tid = task_id_relation(task_info.get("task_id"), task.get("task_id"), facets.domain)
    return tier, ins, gl, tid
