"""D-1130: start ``agentprov backends rebuild-stale`` as a job, in one call. No Qt.

The update flow calls :func:`start_rebuild_stale` as its last step (after its own confirmation, which shows
:data:`~agentprov_gui.jobs.commands.REBUILD_STALE_NOTES`); the Runs page's **Rebuild Stale Environments…** button
confirms first (``ui.jobdialog.confirm``) and then spawns the same spec. The job is an ordinary job: the Runs page lists
it and shows its progress (one unit per backend). The command needs the repository checkout (``backends/``), so
without one nothing starts and the returned note says why in plain words.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Final

from agentprov_gui.jobs.commands import FORMS, JobSpec, build_spec
from agentprov_gui.jobs.manager import NEEDS_CHECKOUT

__all__ = ["CONFIRM_LINE", "FORM", "NO_CHECKOUT", "PROGRAM_PART", "Started", "after_update", "prepare",
           "rebuild_stale_spec", "start_rebuild_stale"]

#: The job form (``jobs.commands.FORMS``); its command is ``agentprov backends rebuild-stale``.
FORM: Final = "backends_rebuild_stale"
NO_CHECKOUT: Final = "Backend environments were not checked or rebuilt. " + NEEDS_CHECKOUT


#: The update flow's part name for the agentprov program (a package install or a checkout pull); the backend
#: environments follow the program, so only that part is followed by a rebuild.
PROGRAM_PART: Final = "The agentprov program"
#: The line the update's confirmation shows when the program part is planned with a checkout (D-1130).
CONFIRM_LINE: Final = ("Then the backend environments the new version no longer accepts are rebuilt and checked, as a "
                       "job on the Runs page (agentprov backends rebuild-stale --allow-network): it downloads the pinned "
                       "wheels they need and can take about 15 minutes. Earlier environments are left as they are, "
                       "and so is one that holds defence assets (its own rebuild command is named).")


@dataclass(frozen=True, slots=True)
class Started:
    """What :func:`start_rebuild_stale` did: the job id (``None`` when nothing started) and a plain note."""

    job_id: str | None
    note: str
    code: str | None = None  # a SpawnRefused code, or "gui.checkout.missing"


def rebuild_stale_spec(*, allow_network: bool = True, backends: Sequence[str] = (), dry_run: bool = False,
                       label: str = "") -> JobSpec:
    """The job spec of ``agentprov backends rebuild-stale [--allow-network] [--backend ID,...] [--dry-run]``."""
    values: dict[str, Any] = {"allow_network": allow_network, "dry_run": dry_run}
    if backends:
        values["backend"] = ",".join(backends)
    return build_spec(FORMS[FORM], values, label=label or FORMS[FORM].title)


def start_rebuild_stale(manager: Any, *, allow_network: bool = True, backends: Sequence[str] = (),
                        spec: JobSpec | None = None) -> Started:
    """Spawn the job without asking (the caller has confirmed). Never raises for an expected refusal: without a
    checkout, or when the job manager refuses (the backends slot is busy, no CLI), the note says so."""
    from agentprov_gui.jobs.manager import SpawnRefused

    if getattr(manager.cli, "checkout", None) is None:
        return Started(None, NO_CHECKOUT, "gui.checkout.missing")
    try:
        job = manager.spawn(spec if spec is not None else rebuild_stale_spec(allow_network=allow_network,
                                                                             backends=backends))
    except SpawnRefused as exc:
        return Started(None, f"Backend environments were not checked: {exc}", exc.code)
    return Started(job.job_id, f"Checking the backend environments and rebuilding the stale ones (job {job.job_id}); "
                               "its progress is on the Runs page.")


def prepare() -> None:
    """Load now everything :func:`start_rebuild_stale` runs (D-1130 review). The update flow calls it before the first
    part installs: once a macOS or Linux bundle has been swapped, a module first imported by this app would be read
    from the new bundle's archive."""
    import agentprov.jobs.record  # noqa: F401  (the job manager's spawn and refresh)

    from agentprov_gui.jobs.manager import SpawnRefused  # noqa: F401

    rebuild_stale_spec()  # its form's fields and notes


def after_update(manager: Any, notify: Callable[[str], None]) -> Callable[[list[str]], None]:
    """The update flow's ``after_update`` hook (D-1130): once the program part has installed (a package install or a
    checkout pull, then ``uv sync``), start the rebuild with the checkout's new CLI and pass the note to ``notify``.
    An update of the app alone changes no backend environment, so nothing starts for it."""

    def hook(parts: list[str]) -> None:
        if PROGRAM_PART in parts:
            notify(start_rebuild_stale(manager).note)

    return hook
