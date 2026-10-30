"""The building commit of a corpus (D-780; HL H.2.7, H.8.4(5)).

After a change to a stage's code a corpus reproduces only at the commit that built it (D-430). Every writer therefore
records, in the working manifest's ``producer`` block, the commit of the AgentPROV checkout that ran it, and an ordered
``build_steps`` list with one record per process that wrote part of the corpus (an import and a later derive are two
steps). A sealed manifest keeps its sealing ``git_commit`` (H.2.7, unchanged) and copies the list.

``corpus/`` runs no subprocess, so the CLI computes the facts (:mod:`agentprov.cli.gitinfo`) and hands a
:class:`BuildStep` to :class:`~agentprov.corpus.writer.CorpusWriter`, which merges it into the manifest it writes. This
module is data and rules only: no I/O, no clock, no environment (a commit can only come from the caller).

A step record is ``{agentprov_version, command, stages, git_commit, git_tree_clean}`` or, when the code did not run from
a git checkout, ``{agentprov_version, command, stages, git_commit_absent_reason, distributions_sha256}``. Never a
placeholder commit (invariant 7). ``stages`` lists only the stages that process wrote (the writer's own record, or the
stages a derivation plans to recompute), by the names ``derivation.json`` uses, sorted.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

__all__ = [
    "ABSENT_REASONS",
    "BUILD_COMMANDS",
    "BUILD_STAGES",
    "BuildStep",
    "BuildStepError",
    "StepTracker",
    "describe_steps",
    "parse_steps",
    "step_problems",
]

BUILD_COMMANDS: Final = ("import", "run", "derive", "recompute")
#: The stage names of ``derivation.json`` (``corpus.derive._ORDER``).
BUILD_STAGES: Final = ("expand", "aer", "sem", "prov", "validation", "views", "compat")
ABSENT_REASONS: Final = ("not_a_source_checkout", "git_unavailable", "git_failed")
_HEX40: Final = re.compile(r"[0-9a-f]{40}")
_SHA: Final = re.compile(r"sha256:[0-9a-f]{64}")
_IDENTITY_KEYS: Final = ("agentprov_version", "command", "distributions_sha256", "git_commit", "git_commit_absent_reason",
                         "git_tree_clean")


class BuildStepError(ValueError):
    """A build step or a ``build_steps`` list is malformed."""


@dataclass(frozen=True)
class BuildStep:
    """What the CLI knows about the process that builds the corpus (everything but the stages, which the writer knows)."""

    command: str
    agentprov_version: str
    git_commit: str | None = None
    git_tree_clean: bool | None = None
    git_commit_absent_reason: str | None = None
    distributions_sha256: str | None = None

    def __post_init__(self) -> None:
        if self.git_commit is not None and (self.git_commit_absent_reason is not None or self.distributions_sha256 is not None):
            raise BuildStepError("a commit and an absent reason are exclusive")
        if self.git_commit is None and self.git_tree_clean is not None:
            raise BuildStepError("git_tree_clean goes with a commit")
        problems = step_problems(self.identity())
        if problems:
            raise BuildStepError("; ".join(problems))

    def identity(self) -> dict[str, Any]:
        """The record without ``stages``: only the keys that apply (a commit, or the absent reason with its digest)."""
        out: dict[str, Any] = {"agentprov_version": self.agentprov_version, "command": self.command}
        if self.git_commit is not None:
            out["git_commit"], out["git_tree_clean"] = self.git_commit, self.git_tree_clean
        else:
            out["git_commit_absent_reason"] = self.git_commit_absent_reason
            out["distributions_sha256"] = self.distributions_sha256
        return out

    def record(self, stages: Iterable[str]) -> dict[str, Any]:
        return {**self.identity(), "stages": sorted(set(stages))}


def step_problems(step: Mapping[str, Any], *, with_stages: bool = False) -> list[str]:
    """Why ``step`` is not a valid record (empty: valid). ``with_stages`` also requires the ``stages`` list."""
    out: list[str] = []
    allowed = set(_IDENTITY_KEYS) | ({"stages"} if with_stages else set())
    if extra := sorted(set(step) - allowed):
        out.append(f"unknown key(s) {extra}")
    if step.get("command") not in BUILD_COMMANDS:
        out.append(f"command is one of {BUILD_COMMANDS}")
    version = step.get("agentprov_version")
    if not isinstance(version, str) or not version:
        out.append("agentprov_version is a non-empty string")
    has_commit = "git_commit" in step or "git_tree_clean" in step
    has_reason = "git_commit_absent_reason" in step or "distributions_sha256" in step
    if has_commit == has_reason:
        out.append("exactly one of (git_commit, git_tree_clean) and (git_commit_absent_reason, distributions_sha256)")
    elif has_commit:
        commit = step.get("git_commit")
        if not isinstance(commit, str) or _HEX40.fullmatch(commit) is None:
            out.append("git_commit is 40 lower-case hex")
        if not isinstance(step.get("git_tree_clean"), bool):
            out.append("git_tree_clean is a boolean")
    else:
        if step.get("git_commit_absent_reason") not in ABSENT_REASONS:
            out.append(f"git_commit_absent_reason is one of {ABSENT_REASONS}")
        digest = step.get("distributions_sha256")
        if not isinstance(digest, str) or _SHA.fullmatch(digest) is None:
            out.append("distributions_sha256 is sha256:<64 hex>")
    if with_stages:
        stages = step.get("stages")
        if (not isinstance(stages, list) or any(s not in BUILD_STAGES for s in stages)
                or stages != sorted(set(stages))):
            out.append(f"stages is a sorted list without repeats of {BUILD_STAGES}")
    return out


def parse_steps(value: Any) -> list[dict[str, Any]]:
    """``value`` (a manifest's ``producer.build_steps``) as a list of valid records; ``None`` is an empty list (a corpus
    built before D-780). Raises :class:`BuildStepError` on anything else."""
    if value is None:
        return []
    if not isinstance(value, list):
        raise BuildStepError("build_steps is a list")
    for i, step in enumerate(value):
        if not isinstance(step, Mapping):
            raise BuildStepError(f"build_steps[{i}] is an object")
        if problems := step_problems(step, with_stages=True):
            raise BuildStepError(f"build_steps[{i}]: " + "; ".join(problems))
    return [dict(s) for s in value]


def _same_process(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    return all(a.get(k) == b.get(k) for k in _IDENTITY_KEYS)


class StepTracker:
    """One writer's record of itself, merged into each manifest it writes (:meth:`apply`).

    The first merge fixes how many steps came before this process. Later merges (an import writes its manifest after
    every batch) replace this process's own entry, so it appears once, with the stages written so far. A resumed corpus
    whose last step is this same process (same command, version and commit) adopts that step and extends its stages.
    """

    def __init__(self, step: BuildStep) -> None:
        self.step = step
        self.written: set[str] = set()
        #: a derivation names the stages it recomputes (carried layers are copied through the writer too, so the write
        #: calls alone would overstate them); ``None``: the writer's own record
        self.planned: frozenset[str] | None = None
        self._carried: int | None = None
        self._adopted: frozenset[str] = frozenset()

    def note(self, stage: str) -> None:
        self.written.add(stage)

    def plan(self, stages: Iterable[str]) -> None:
        names = frozenset(stages)
        if unknown := sorted(names - set(BUILD_STAGES)):
            raise BuildStepError(f"unknown stage(s) {unknown}")
        self.planned = names

    def stages(self) -> list[str]:
        own = self.planned if self.planned is not None else frozenset(self.written)
        return sorted(own | self._adopted)

    def apply(self, producer: Mapping[str, Any], on_disk: Any) -> dict[str, Any]:
        """``producer`` with this process's commit facts and ``build_steps``.

        ``producer["build_steps"]`` (a derivation hands over its source's) wins over ``on_disk``, the steps of the
        manifest already in the working tree (an import or live run resumed)."""
        handed = producer.get("build_steps")
        base = parse_steps(handed if handed is not None else on_disk)
        if self._carried is None:
            self._carried = len(base)
            if handed is None and base and _same_process(base[-1], self.step.identity()):
                self._carried = len(base) - 1
                self._adopted = frozenset(base[-1]["stages"])
        out = {k: v for k, v in producer.items() if k not in ("git_commit", "git_tree_clean", "git_commit_absent_reason",
                                                              "build_steps")}
        facts = self.step.identity()
        for key in ("git_commit", "git_tree_clean", "git_commit_absent_reason"):
            if key in facts:
                out[key] = facts[key]
        out["build_steps"] = [*base[: self._carried], self.step.record(self.stages())]
        return out


def describe_steps(steps: Sequence[Mapping[str, Any]]) -> str:
    """One plain-text clause for a datasheet or a notice: where each step ran and what it wrote."""
    if not steps:
        return "building commit not recorded"
    parts = []
    for step in steps:
        wrote = ", ".join(step.get("stages") or []) or "no stage"
        if "git_commit" in step:
            tree = "" if step.get("git_tree_clean") else " (uncommitted changes)"
            where = f"commit {step['git_commit']}{tree}"
        else:
            where = (f"no git checkout ({step.get('git_commit_absent_reason')}; agentprov {step.get('agentprov_version')}; "
                     f"distributions {step.get('distributions_sha256')})")
        parts.append(f"{step.get('command')} at {where} wrote {wrote}")
    return "; ".join(parts)
