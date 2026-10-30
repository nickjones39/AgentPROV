"""Batches: a client of ``agentprov batch`` (D-704; design §4.4 "Batch queue", §6.2). No Qt.

A batch is the core's (:mod:`agentprov.jobs.batch`): ``$AGENTPROV_HOME/batches/<id>.json``, run by one driver job
(``agentprov batch run ID``; user decision 2026-10-22), so it advances whether or not the GUI is open. The GUI
**creates** one with ``agentprov batch create --stdin`` (the steps as JSON on stdin), **starts** it with ``batch start``
(``--confirm-r2`` when the user started it in this session, which is the confirmation of its R2 steps), **resumes** a
held one with ``batch resume --confirm-r2`` after the tier confirmation, and **stops** it with ``batch stop``. It reads
the batch files strictly to show them (:class:`Batch`); the CLI checks every step again before it starts (GR-4), holds
R2 steps under an unconfirmed driver (GR-48) and blocks the rest when the checkout changed (GR-70).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from agentprov.jobs.record import batches_dir, read_json

from agentprov_gui.jobs.commands import JobSpec, tier_of_argv
from agentprov_gui.jobs.manager import JobManager, SpawnRefused

__all__ = ["BATCH_FORMAT", "Batch", "BatchStep", "create", "resume", "start", "stop"]

BATCH_FORMAT: Final = "agentprov-batch/0.1"
#: the step facts a batch carries for the GUI (a dev run's; ``agentprov devrun``)
_EXTRA_KEYS: Final = ("devrun", "part")


@dataclass(slots=True)
class BatchStep:
    spec: JobSpec
    state: str = "pending"  # pending | held | running | done | failed | blocked | skipped
    job_id: str | None = None
    exit_code: int | None = None
    note: str = ""

    @classmethod
    def from_json(cls, obj: Mapping[str, Any]) -> BatchStep:
        argv = tuple(str(a) for a in obj.get("argv", []) if isinstance(a, str))
        two = argv[:1] in (("backends",), ("migrate",)) and len(argv) > 1 and not argv[1].startswith("-")
        extra = obj.get("extra") if isinstance(obj.get("extra"), dict) else {}
        spec = JobSpec(
            command=" ".join(argv[: 2 if two else 1]) if argv else "", argv=argv,
            tier=str(obj.get("tier") or tier_of_argv(argv, "R1")), label=str(obj.get("label", "")),
            writes=tuple(str(w) for w in obj.get("writes", []) if isinstance(w, str)),
            reads=tuple(str(r) for r in obj.get("reads", []) if isinstance(r, str)),
            slot=obj.get("slot") if isinstance(obj.get("slot"), str) else None,
            extra={k: v for k, v in (extra or {}).items() if isinstance(v, str | int | float | bool)},
        )  # fmt: skip
        code = obj.get("exit_code")
        return cls(spec, str(obj.get("state", "pending")), obj.get("job_id") if isinstance(obj.get("job_id"), str)
                   else None, code if isinstance(code, int) and not isinstance(code, bool) else None,
                   str(obj.get("note", "")))


@dataclass(slots=True)
class Batch:
    """A batch file as the GUI shows it (read-only)."""

    batch_id: str
    label: str
    steps: list[BatchStep]
    continue_on_failure: bool = False
    created: str = ""
    driver_job_id: str | None = None
    path: Path | None = field(default=None, repr=False)

    @classmethod
    def load(cls, path: Path) -> Batch | None:
        obj = read_json(path)
        if obj is None or obj.get("format") != BATCH_FORMAT or not isinstance(obj.get("steps"), list):
            return None
        try:
            steps = [BatchStep.from_json(s) for s in obj["steps"] if isinstance(s, dict)]
            driver = obj.get("driver_job_id")
            return cls(str(obj["batch_id"]), str(obj.get("label", "")), steps, bool(obj.get("continue_on_failure")),
                       str(obj.get("created", "")), driver if isinstance(driver, str) else None, path)
        except (KeyError, TypeError, ValueError):
            return None

    @classmethod
    def load_all(cls, home: Path) -> list[Batch]:
        """Every batch of ``home``, oldest first."""
        directory = batches_dir(home)
        if not directory.is_dir():
            return []
        return [b for p in sorted(directory.glob("*.json")) if (b := cls.load(p)) is not None]

    @property
    def finished(self) -> bool:
        return all(s.state in ("done", "failed", "blocked", "skipped") for s in self.steps)

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for s in self.steps:
            out[s.state] = out.get(s.state, 0) + 1
        return out


def _step_json(spec: JobSpec) -> dict[str, Any]:
    extra = dict(spec.extra or {})
    out: dict[str, Any] = {"argv": list(spec.argv), "label": spec.label, "writes": list(spec.writes),
                           "reads": list(spec.reads), "notes": list(spec.notes),
                           "conformance_skipped": spec.conformance_skipped,
                           "extra": {k: extra[k] for k in _EXTRA_KEYS if isinstance(extra.get(k), str | int)}}
    if spec.slot:
        out["slot"] = spec.slot
    cpu = extra.get("queue_cpu")
    if isinstance(cpu, int) and not isinstance(cpu, bool):
        out["queue_cpu"] = cpu
    if extra.get("progress_level") == "steps":
        out["progress_level"] = "steps"
    return out


def _json_out(code: int, out: bytes, err: bytes) -> dict[str, Any]:
    if code != 0:
        raise JobManager._refusal(code, err)
    try:
        doc = json.loads(out)
    except ValueError:
        raise SpawnRefused("agentprov batch gave no JSON", "gui.batch.output") from None
    if not isinstance(doc, dict):
        raise SpawnRefused("agentprov batch gave no JSON object", "gui.batch.output")
    return doc


def create(manager: JobManager, label: str, specs: Sequence[JobSpec], *, continue_on_failure: bool | None = None,
           concurrency: int = 1) -> str:
    """``agentprov batch create --stdin``: the new batch's id (:class:`SpawnRefused` with the CLI's reason). Without
    ``continue_on_failure`` the CLI follows ``jobs.continue_on_failure``."""
    argv = ["batch", "create", "--stdin", "--format", "json", "--label", label[:200], "--concurrency",
            str(max(1, min(16, concurrency)))]
    if continue_on_failure is not None:
        argv.append("--continue-on-failure" if continue_on_failure else "--no-continue-on-failure")
    stdin = json.dumps({"steps": [_step_json(s) for s in specs]}, ensure_ascii=False).encode("utf-8")
    return str(_json_out(*manager.call(argv, stdin=stdin))["batch_id"])


def start(manager: JobManager, batch_id: str, *, confirm_r2: bool) -> str:
    """``agentprov batch start``: the driver job's id."""
    argv = ["batch", "start", batch_id, "--format", "json", *(["--confirm-r2"] if confirm_r2 else [])]
    return str(_json_out(*manager.call(argv))["driver_job_id"])


def resume(manager: JobManager, batch_id: str, *, confirm_r2: bool) -> str:
    argv = ["batch", "resume", batch_id, "--format", "json", *(["--confirm-r2"] if confirm_r2 else [])]
    return str(_json_out(*manager.call(argv))["driver_job_id"])


def stop(manager: JobManager, batch_id: str, *, steps: bool = False) -> bool:
    return manager.call(["batch", "stop", batch_id, *(["--steps"] if steps else [])])[0] == 0
