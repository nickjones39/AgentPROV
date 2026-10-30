"""The run's use of the injected environment (regeneration-batch item 5, analysis C2; DECISIONS D-370).

AgentDojo's suite loads the task environment with the run's injections before the agent runs
(``TaskSuite.run_task_with_pipeline`` -> ``load_and_inject_default_environment(injections)``), so the run used every
injection payload. aer/0.1 has no field for a scope's inputs, so the TraceLogger mapper (``agentdojo``, and any other
mapper of the harness that is not a gate-D migration mapper) writes one generic ``activity`` (AD-15) of the run scope: type
``agentdojo:load_environment``, performed by the benchmark actor ``bench``, whose inputs are the payload fixtures. The
engine's existing rules then give ``used(x:ac0, x:fx<i>)`` (``aprov.g_use@1``), ``wasAssociatedWith(x:ac0, x:bench)``
and ``apv:partOf x:run``. The transcript/v1 mapper does not write it: gate D requires 0 generic records in v1
migration AERs (J, ``pv.profiles.migration_generic``), so adprov fixtures stay attribute-linked; gate D's never-emit
check admits this one type in the native goldens (``migration.gate_d_worker.EXEMPT_ACTIVITY_TYPES``). User decisions
2026-10-13. Pure.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, Final

__all__ = ["ENV_LOAD_RULE", "environment_load"]

ENV_LOAD_RULE: Final = "agentdojo.environment_loaded_with_injections@1"


def environment_load(fixtures: Sequence[str], rule: Callable[..., str], cls: Callable[[str], str]) -> dict[str, Any]:
    """The ``agentdojo:load_environment`` activity whose inputs are ``fixtures`` (payload fixture ids, in AER order).

    ``rule`` is the mapper's citation function (``rule(id, pointer=None)``: the D rule or its ``_unverified`` twin) and
    ``cls`` the class of what it cites; every input is tagged at that class with the rule scoped to it. The activity's
    time is not logged (``unk``)."""
    c = cls(ENV_LOAD_RULE)
    return {"k": "activity", "id": "ac0", "type": "agentdojo:load_environment", "actor": "bench", "scope": "run",
            "inputs": list(fixtures), "ev": c, "evf": {f"/inputs/{i}": c for i in range(len(fixtures))},
            "rule": [rule(ENV_LOAD_RULE), *(rule(ENV_LOAD_RULE, f"/inputs/{i}") for i in range(len(fixtures)))],
            "unk": {"/t": "not_recorded"}}
