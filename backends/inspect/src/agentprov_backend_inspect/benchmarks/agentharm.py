"""AgentHarm (``inspect_evals`` 0.20.0, tasks ``agentharm`` and ``agentharm_benign``; D-660, D-661).

What a plan may select and what the catalogue reports, by name and count only. The behaviour prompts are harmful
requests: nothing here reads, returns or logs a prompt, a detailed prompt or a target-function body. Only the
behaviour ids, the split sizes and the *names* in ``target_functions`` (to size the tool definitions) are read.

The dataset is the pinned Hugging Face snapshot ``ai-safety-institute/AgentHarm@e23b3fe6`` (the revision
``inspect_evals.agentharm.utils.AGENTHARM_DATASET_REVISION`` names at 0.20.0). ``backends build`` provisions it into the
environment; the worker copies it, digest-checked, into the session's ``INSPECT_EVALS_CACHE_DIR`` (where
``load_dataset`` finds it and skips the download, and where it writes its ``.jsonl`` copies).
"""

from __future__ import annotations

from types import ModuleType
from typing import Any, Final

BENCHMARK: Final = "agentharm"
PACKAGE: Final = "inspect_evals"
#: The package directory whose files the task-files digest covers (T0 hashes them without importing anything).
TASK_PACKAGE_DIR: Final = "inspect_evals/agentharm"

DATASET_REPO: Final = "ai-safety-institute/AgentHarm"
DATASET_REVISION: Final = "e23b3fe60a0da9037314b88e5ee3a0c054970dad"
#: The pinned snapshot's benchmark files: path -> (sha256, bytes). Verified against the revision's git blob ids when
#: fetched (acquisitions.jsonl, 2026-10-22). The README and LICENSE are not needed by the task.
DATASET_FILES: Final[dict[str, tuple[str, int]]] = {
    "benchmark/benign_behaviors_test_public.json": ("65b4ebd4d8d2e7c9a79db4e11bc642f1800e642be0626ba0a990c763a325957a", 138721),
    "benchmark/benign_behaviors_validation.json": ("b74ffb781ce54182775a8b2843ea341ab2fb4cfea5743bfa89a368e52a76c27a", 23508),
    "benchmark/chat_public_test.json": ("699a8325ce6dc355fd6ebef07bd2a9e76cca4c0ca7b6971774f2ff117e8f4512", 17984),
    "benchmark/chat_validation.json": ("06684a6968e0bb65bcb15bc1cdaf3bd8c486fc54164e7623a35e3ee58bf93565", 3134),
    "benchmark/harmful_behaviors_test_public.json": ("fc3e4abbcd812022b85150b0e6f81c0bdbdfabb486e5b82ec46f1ba135f3ba08", 134140),
    "benchmark/harmful_behaviors_validation.json": ("40cd099915258b41142acfc88a9f2b4e15cd631c5490ad02a0dce0cf2b9c175e", 22584),
}
#: Where ``inspect_evals.agentharm.utils.load_dataset`` looks under ``INSPECT_EVALS_CACHE_DIR``.
CACHE_SUBDIR: Final = "agentharm_dataset/AgentHarm"

#: task -> (the task function's name in ``inspect_evals.agentharm``, dataset name, split -> file). ``test_private`` is
#: not in the public snapshot, and the ``chat`` dataset has no grading function (scores NaN): both are refused.
TASKS: Final[dict[str, dict[str, Any]]] = {
    "inspect_evals/agentharm": {
        "function": "agentharm", "dataset": "harmful",
        "splits": {"test_public": "benchmark/harmful_behaviors_test_public.json",
                   "val": "benchmark/harmful_behaviors_validation.json"},
    },
    "inspect_evals/agentharm_benign": {
        "function": "agentharm_benign", "dataset": "benign",
        "splits": {"test_public": "benchmark/benign_behaviors_test_public.json",
                   "val": "benchmark/benign_behaviors_validation.json"},
    },
}

#: The task parameters a plan may set (D-663): name -> {type, default, choices}. ``behavior_ids`` is not offered: the
#: plan selects samples by id through Inspect's own ``sample_id`` (the same ids). ``refusal_judge``/``semantic_judge``
#: are judge roles, set through ``[judges]``; ``force_redownload`` and ``chat_dataset`` are fixed (no network; no
#: grading).
PARAMS: Final[tuple[dict[str, Any], ...]] = (
    {"name": "split", "type": "str", "default": "test_public", "choices": ["test_public", "val"]},
    {"name": "agent", "type": "str", "default": "default", "choices": ["default", "refusal"]},
    {"name": "detailed_behaviors", "type": "bool|null", "default": None},
    {"name": "hint_included", "type": "bool|null", "default": None},
    {"name": "n_irrelevant_tools", "type": "int", "default": 0, "minimum": 0, "maximum": 64},
    {"name": "tool_choice", "type": "str", "default": "auto", "choices": ["auto", "forced_first", "none"],
     "maps_to": "agent_kwargs.tool_choice"},
    {"name": "prompt_technique", "type": "str", "default": "standard", "choices": ["standard", "cot", "react", "refusal"],
     "maps_to": "agent_kwargs.prompt_technique"},
)
SOLVERS: Final = ("default", "refusal")
DEFAULT_SOLVER: Final = "default"
#: The scorer and its judge roles. Calls per sample vary: the refusal judge is called once per assistant message with
#: text until a refusal is found, the semantic judge as the sample's grading function requires (0 or more). The priors
#: (survey AgentHarm, 1,056 samples: 1.2-2.0 judge calls per sample) live with the estimate, not here.
SCORERS: Final[tuple[dict[str, Any], ...]] = (
    {"name": "combined_scorer", "judge_roles": [
        {"role": "refusal_judge", "default_model": "openai/gpt-4o-2024-08-06", "calls_per_sample": "varies"},
        {"role": "semantic_judge", "default_model": "openai/gpt-4o-2024-08-06", "calls_per_sample": "varies"},
    ]},
)
#: Fixed by the task itself (``Task(max_messages=20, config=GenerateConfig(...))``) and reported, never overridden.
TASK_FIXED: Final[dict[str, Any]] = {"max_messages": 20, "max_tokens": 4096, "temperature": 0.0, "seed": 0,
                                     "max_retries": 3}


def task_args(params: dict[str, Any], judges: dict[str, Any]) -> dict[str, Any]:
    """The ``task_args`` for Inspect from checked plan parameters and the judge ``Model`` objects (or names)."""
    args: dict[str, Any] = {"force_redownload": False}
    kwargs: dict[str, Any] = {}
    for spec in PARAMS:
        name = spec["name"]
        if name not in params:
            continue
        target = spec.get("maps_to")
        if target is None:
            args[name] = params[name]
        else:
            kwargs[target.split(".", 1)[1]] = params[name]
    if kwargs:
        args["agent_kwargs"] = kwargs
    args["refusal_judge"] = judges["refusal_judge"]
    args["semantic_judge"] = judges["semantic_judge"]
    return args


def tool_modules() -> dict[str, ModuleType]:
    """The tool modules per dataset name (imported lazily: only inside the environment)."""
    from inspect_evals.agentharm.benchmark import benign_tools, harmful_tools

    return {"harmful": harmful_tools, "benign": benign_tools}
