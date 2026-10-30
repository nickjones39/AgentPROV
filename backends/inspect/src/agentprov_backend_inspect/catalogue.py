"""``agentprov-inspect-catalogue/0.1``: what a plan of an Inspect backend can select (D-663; GUI D-652 peer format).

Names and counts only: tasks, their declared parameters, the solvers, the scorers with their judge roles, the sample
count per split and the size of the tool definitions a sample sends (mean and maximum per split, in characters of the
definitions' JSON, which the estimate adds to every model call's input). Never a prompt, a behaviour text, a target or
a tool body. The dataset is read from the environment's provisioned copy; only ``id`` and the *names* in
``target_functions`` are looked at.

Shape::

    {format, backend, benchmark, inspect_ai, dataset: {repo, revision},
     tasks: [{name, splits: [{name, samples, tool_definition_chars: {mean, max}}],
              params: [{name, type, default, choices?, minimum?, maximum?}],
              solvers: [name], default_solver, fixed: {...},
              scorers: [{name, judge_roles: [{role, default_model, calls_per_sample}]}]}]}
"""

from __future__ import annotations

import json
from types import ModuleType
from typing import Any

from agentprov_backend_inspect.provision import env_dataset_dir, verify_dataset

__all__ = ["CATALOGUE_FORMAT", "build_catalogue"]

CATALOGUE_FORMAT = "agentprov-inspect-catalogue/0.1"


def _tool_sizes(tools_module: ModuleType) -> dict[str, int]:
    """Characters of each tool definition's JSON (name, description, parameters), as Inspect builds it."""
    from inspect_ai.tool import ToolDef

    sizes: dict[str, int] = {}
    for name in sorted(n for n in dir(tools_module) if not n.startswith("_")):
        factory = getattr(tools_module, name)
        if not callable(factory):
            continue
        try:
            tdef = ToolDef(factory())
        except Exception:  # noqa: BLE001 - not a tool factory
            continue
        doc = {"name": tdef.name, "description": tdef.description,
               "parameters": tdef.parameters.model_dump(exclude_none=True)}
        sizes[tdef.name] = len(json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    return sizes


def build_catalogue(bench: ModuleType, backend_id: str, *, prefix: str | None = None) -> dict[str, Any]:
    import inspect_ai

    root = env_dataset_dir(bench, prefix)
    verify_dataset(root, bench.DATASET_FILES)
    tool_sizes = {name: _tool_sizes(module) for name, module in bench.tool_modules().items()}
    tasks = []
    for name, spec in bench.TASKS.items():
        splits = []
        for split, rel in spec["splits"].items():
            behaviours = json.loads((root / rel).read_bytes())["behaviors"]
            sizes = [sum(tool_sizes[spec["dataset"]].get(str(f), 0) for f in b.get("target_functions") or [])
                     for b in behaviours]
            splits.append({"name": split, "samples": len(behaviours),
                           "tool_definition_chars": {"mean": round(sum(sizes) / len(sizes)) if sizes else 0,
                                                     "max": max(sizes, default=0)}})
        tasks.append({"name": name, "splits": splits, "params": [dict(p) for p in bench.PARAMS],
                      "solvers": list(bench.SOLVERS), "default_solver": bench.DEFAULT_SOLVER,
                      "fixed": dict(bench.TASK_FIXED), "scorers": [dict(s) for s in bench.SCORERS]})
    return {"format": CATALOGUE_FORMAT, "backend": backend_id, "benchmark": bench.BENCHMARK,
            "inspect_ai": inspect_ai.__version__,
            "dataset": {"repo": bench.DATASET_REPO, "revision": bench.DATASET_REVISION}, "tasks": tasks}
