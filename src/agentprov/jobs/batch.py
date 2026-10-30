"""Batches (D-704; GUI design §4.4 "Batch queue", §6.2; moved from the GUI): an ordered list of job requests with a
concurrency limit (default 1), in ``$AGENTPROV_HOME/batches/<id>.json``. User decision 2026-10-22: **a batch runs as a
job** (``agentprov batch run ID`` under :mod:`.manager`, started by ``batch start``), so it advances whether or not
the GUI is open, and both see the same file.

**Advancing** (:func:`advance`): a running step ends with its job; a step starts only when its corpus is free (the
manager's single-writer check) and, unless ``continue_on_failure``, when no earlier step ended with exit 4 (refused)
or 70 (internal).

**Nothing in the file is trusted** (GR-4). Before a step starts it is checked again: its argv must parse as an
``agentprov`` command (the caller's ``validate``, the CLI's own parser), never start jobs or batches, never be
destructive (``purge`` without ``--dry-run``), and its tier is recomputed from the argv (a step recorded as R1 whose argv
needs R2 waits). A failed check blocks the step with a fixed note.

**R2 steps** (network, a large download, paid calls; GR-48) run only under the driver that was started with
``--confirm-r2``. The batch records that driver's job id, so a driver started again without the confirmation holds at the
first R2 step (``held``) until ``batch resume ID --confirm-r2``.

**The checkout pin** (GR-70): the checkout's path, commit and a digest of its uncommitted diff, recorded at
creation. A changed pin blocks every remaining step, so one batch never mixes CLI versions.

**Dev runs** (D-544, D-529): a step with ``extra.part`` whose import ends with exit 5 and
``import.sample.unsupported`` gets a first-N import of that part inserted after it; a part whose import failed
otherwise has its later steps skipped.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Final

from agentprov.jobs.manager import JobManager, JobRequest, SpawnRefused, atomic_write_json, new_job_id
from agentprov.jobs.record import batches_dir, list_jobs, read_json
from agentprov.jobs.tiers import TIERS, is_destructive, tier_of_argv

__all__ = ["BATCH_FORMAT", "Batch", "BatchStep", "advance", "first_n_argv", "sample_unsupported"]

BATCH_FORMAT: Final = "agentprov-batch/0.1"
BLOCKING_EXITS: Final = (4, 70)
MAX_STEPS: Final = 10_000
HELD_NOTE: Final = "waiting: an R2 step (network or paid) needs 'agentprov batch resume ID --confirm-r2'"
PIN_NOTE: Final = "not run: the checkout changed since this batch was created (GR-70); create a new batch"
SAMPLE_UNSUPPORTED: Final = "import.sample.unsupported"
FALLBACK_NOTE: Final = ("fallback: this part's reader cannot draw this sample (exit 5, import.sample.unsupported); "
                        "first-N used")
SKIPPED_NOTE: Final = "skipped: this part's import failed"
STATES: Final = ("pending", "held", "running", "done", "failed", "blocked", "skipped")


@dataclass(slots=True)
class BatchStep:
    request: JobRequest
    state: str = "pending"
    job_id: str | None = None
    exit_code: int | None = None
    note: str = ""
    recorded_tier: str = ""

    def to_json(self) -> dict[str, Any]:
        r = self.request
        return {"argv": list(r.argv), "label": r.label, "writes": list(r.writes), "reads": list(r.reads),
                "slot": r.slot, "notes": list(r.notes), "with_control_file": r.control_file, "queue_cpu": r.queue_cpu,
                "progress_level": r.progress_level, "conformance_skipped": r.conformance_skipped,
                "extra": dict(r.extra), "tier": self.recorded_tier or r.tier, "state": self.state,
                "job_id": self.job_id, "exit_code": self.exit_code, "note": self.note}

    @classmethod
    def from_json(cls, obj: Mapping[str, Any]) -> BatchStep:
        """A step from a batch file or a ``batch create`` document (strict types; a bad one raises ``ValueError``)."""
        def strs(key: str) -> tuple[str, ...]:
            value = obj.get(key, [])
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                raise ValueError(f"{key} is not a list of strings")
            return tuple(value)

        argv = strs("argv")
        if not argv:
            raise ValueError("a step without argv")
        cpu = obj.get("queue_cpu")
        if cpu is not None and (not isinstance(cpu, int) or isinstance(cpu, bool) or not 1 <= cpu <= 256):
            raise ValueError("queue_cpu is 1 to 256")
        slot = obj.get("slot")
        if slot not in (None, "network", "backends"):
            raise ValueError("slot is network or backends")
        extra = obj.get("extra", {})
        if not isinstance(extra, dict):
            raise ValueError("extra is an object")
        state = obj.get("state", "pending")
        if state not in STATES:
            raise ValueError("an unknown step state")
        code = obj.get("exit_code")
        request = JobRequest(argv, str(obj.get("label", ""))[:200], strs("writes"), strs("reads"), slot, strs("notes"),
                             bool(obj.get("with_control_file")), cpu, str(obj.get("progress_level") or "status"),
                             None, None, bool(obj.get("conformance_skipped")),
                             {str(k)[:40]: v for k, v in extra.items() if isinstance(v, str | int | float | bool)})
        return cls(request, str(state), obj.get("job_id") if isinstance(obj.get("job_id"), str) else None,
                   code if isinstance(code, int) and not isinstance(code, bool) else None,
                   str(obj.get("note", ""))[:300], str(obj.get("tier") or ""))


@dataclass(slots=True)
class Batch:
    batch_id: str
    label: str
    steps: list[BatchStep]
    concurrency: int = 1
    continue_on_failure: bool = False
    created: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    path: Path | None = None
    pin: dict[str, str] | None = None
    driver_job_id: str | None = None  # the job running `batch run` (the last one started)
    r2_confirmed_by: str | None = None  # the driver job id that was started with --confirm-r2

    @classmethod
    def new(cls, home: Path, label: str, steps: Sequence[BatchStep], *, concurrency: int = 1,
            continue_on_failure: bool = False, pin: dict[str, str] | None = None) -> Batch:
        bid = new_job_id()
        batch = cls(bid, label, list(steps), max(1, concurrency), continue_on_failure,
                    path=batches_dir(home) / f"{bid}.json", pin=pin)
        batch.save()
        return batch

    def to_json(self) -> dict[str, Any]:
        return {"format": BATCH_FORMAT, "batch_id": self.batch_id, "label": self.label, "created": self.created,
                "concurrency": self.concurrency, "continue_on_failure": self.continue_on_failure,
                "steps": [s.to_json() for s in self.steps], "pin": self.pin, "driver_job_id": self.driver_job_id,
                "r2_confirmed_by": self.r2_confirmed_by}

    def save(self) -> None:
        assert self.path is not None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(self.path, self.to_json())

    @classmethod
    def load(cls, path: Path) -> Batch | None:
        obj = read_json(path)
        if obj is None or obj.get("format") != BATCH_FORMAT or not isinstance(obj.get("steps"), list):
            return None
        try:
            if len(obj["steps"]) > MAX_STEPS:
                return None
            steps = [BatchStep.from_json(s) for s in obj["steps"]]
            raw_pin = obj.get("pin")
            pin = {str(k): str(v) for k, v in raw_pin.items()} if isinstance(raw_pin, dict) else None
            def opt(key: str) -> str | None:
                return obj[key] if isinstance(obj.get(key), str) else None

            return cls(str(obj["batch_id"]), str(obj.get("label", "")), steps, max(1, int(obj.get("concurrency", 1))),
                       bool(obj.get("continue_on_failure")), str(obj.get("created", "")), path, pin,
                       opt("driver_job_id"), opt("r2_confirmed_by"))
        except (KeyError, TypeError, ValueError, AttributeError):
            return None

    @classmethod
    def load_all(cls, home: Path) -> list[Batch]:
        directory = batches_dir(home)
        if not directory.is_dir():
            return []
        return [b for p in sorted(directory.glob("*.json"), reverse=True) if (b := cls.load(p)) is not None]

    @property
    def finished(self) -> bool:
        return all(s.state in ("done", "failed", "blocked", "skipped") for s in self.steps)

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for s in self.steps:
            out[s.state] = out.get(s.state, 0) + 1
        return out


# ---------------------------------------------------------------------------------------------- dev-run follow-up
def sample_unsupported(exit_code: int | None, summary: Mapping[str, Any] | None) -> bool:
    """D-529: the import refused the sampling mode for this reader (exit 5, ``import.sample.unsupported``)."""
    if exit_code != 5 or not summary:
        return False
    texts = [str(n) for n in summary.get("notices", []) if isinstance(n, str)] if isinstance(
        summary.get("notices"), list) else []
    refusal = summary.get("refusal")
    if isinstance(refusal, dict):
        texts.append(str(refusal.get("code", "")))
    failures = summary.get("failures")
    if isinstance(failures, list):
        texts += [str(f.get("code", "")) for f in failures if isinstance(f, dict)]
    return any(SAMPLE_UNSUPPORTED in t for t in texts)


def first_n_argv(argv: Sequence[str]) -> tuple[str, ...]:
    """The import argv with its sampling mode set to ``first`` and its ``--seed`` dropped (D-529 rules)."""
    out: list[str] = []
    skip = False
    for i, token in enumerate(argv):
        if skip:
            skip = False
            continue
        if token == "--seed":
            skip = True
            continue
        if token.startswith("--seed="):
            continue
        if i > 0 and argv[i - 1] == "--sample-mode":
            out.append("first")
            continue
        out.append(token.replace("--sample-mode=spread", "--sample-mode=first").replace(
            "--sample-mode=random", "--sample-mode=first"))
    return tuple(out)


def _devrun_followup(batch: Batch, index: int, summary: Mapping[str, Any] | None) -> None:
    step = batch.steps[index]
    part = step.request.extra.get("part")
    if not step.request.argv[:1] == ("import",) or not isinstance(part, str):
        return
    argv = step.request.argv
    if (sample_unsupported(step.exit_code, summary) and "--sample-mode" in argv
            and argv[argv.index("--sample-mode") + 1] != "first"):
        fallback = BatchStep(replace(step.request, argv=first_n_argv(argv),
                                     label=f"{step.request.label} (first-N fallback)"), "pending", note=FALLBACK_NOTE)
        batch.steps.insert(index + 1, fallback)
        return
    for later in batch.steps[index + 1:]:
        if later.request.extra.get("part") == part and later.state in ("pending", "held"):
            later.state, later.note = "skipped", SKIPPED_NOTE


# ---------------------------------------------------------------------------------------------- advance
def check_step(step: BatchStep, validate: Callable[[Sequence[str]], str | None]) -> str | None:
    """Why ``step`` may not run (a fixed note), or ``None``. ``validate`` is the CLI's parse of the argv."""
    argv = step.request.argv
    if argv[:1] in (("jobs",), ("batch",)):
        return "not run: a batch step never starts jobs or batches"
    if is_destructive(argv):
        return "not run: an irreversible step is never batched (it needs its own confirmation)"
    reason = validate(argv)
    if reason is not None:
        return f"not run: {reason}"
    now = tier_of_argv(argv)
    if step.recorded_tier in TIERS and TIERS.index(now) > TIERS.index(step.recorded_tier):
        return "not run: its options need a higher tier than the batch recorded"
    return None


def advance(batch: Batch, manager: JobManager, *, validate: Callable[[Sequence[str]], str | None],
            pin_now: Callable[[], dict[str, str] | None], driver_job_id: str | None) -> list[str]:
    """Update running steps from their jobs and start what may start now; returns the job ids started."""
    jobs = {j.job_id: j for j in list_jobs(manager.home)}
    changed = False
    for step in list(batch.steps):
        if step.state == "running" and step.job_id in jobs:
            job = jobs[step.job_id]
            if job.state != "running":
                step.exit_code = job.exit_code
                step.state = "done" if job.exit_code == 0 else "failed"
                if step.state == "failed":
                    _devrun_followup(batch, batch.steps.index(step), read_json(job.file("summary.json")))
                changed = True
    blocked = (not batch.continue_on_failure) and any(
        s.state == "failed" and s.exit_code in BLOCKING_EXITS for s in batch.steps)
    started: list[str] = []
    running = sum(1 for s in batch.steps if s.state == "running")
    pin_checked = False
    r2_ok = driver_job_id is not None and batch.r2_confirmed_by == driver_job_id
    for step in batch.steps:
        if step.state not in ("pending", "held"):
            continue
        if blocked:
            step.state, step.note = "blocked", "an earlier step ended with exit 4 or 70"
            changed = True
            continue
        if running >= batch.concurrency:
            break
        reason = check_step(step, validate)
        if reason is not None:
            step.state, step.note = "blocked", reason
            changed = True
            continue
        if step.request.tier == "R2" and not r2_ok:
            if step.state != "held":
                step.state, step.note = "held", HELD_NOTE
                changed = True
            break
        if batch.pin is not None and not pin_checked:
            pin_checked = True
            if pin_now() != batch.pin:
                for later in batch.steps:
                    if later.state in ("pending", "held"):
                        later.state, later.note = "blocked", PIN_NOTE
                changed = True
                break
        try:
            job = manager.spawn(replace(step.request, batch_id=batch.batch_id))
        except SpawnRefused as exc:
            if exc.code in ("jobs.spawn.failed", "jobs.tool.path", "jobs.argv.recursive", "jobs.queue.unavailable"):
                step.state, step.note = "failed", exc.code  # retrying each tick never helps
                changed = True
                continue
            if step.note != exc.code:
                step.note = exc.code  # a busy corpus or slot: retried on the next tick
                changed = True
            break
        step.state, step.job_id = "running", job.job_id
        step.note = step.note if step.note.startswith("fallback:") else ""
        running += 1
        started.append(job.job_id)
        changed = True
    if changed or started:
        batch.save()
    return started
