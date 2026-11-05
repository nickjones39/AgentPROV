"""Known platform limits (D-1064): what does not work on a platform, why, where it does work, and the user-guide section.

One table, read by the CLI's refusals (code ``platform.unsupported``, exit 4, before any work starts), by
``agentprov info`` (its ``platform`` member, which the desktop app reads through ``info --format json`` to disable the
same features with the same explanation) and by the user guide's platform tables. Each entry names a feature, the
platforms where it is unavailable (an operating system as :func:`platform.system` names it, and its architectures, or
all of them), the reason in plain words, the systems it works on, and the user-guide section. Only limits that were
tested and recorded are listed (D-867 and the manuscript's implementation section): a platform is never refused for
being untested.

:func:`unavailable` answers for this host, or for ``system`` and ``machine`` given by a test. Layer 0: the standard
library and :mod:`agentprov.errors` only.
"""

from __future__ import annotations

import platform
import sysconfig
from dataclasses import dataclass
from typing import Any, Final

from agentprov.errors import AgentProvError

__all__ = ["LIMITS", "Limit", "PlatformUnsupported", "Unavailable", "Where", "host", "refuse", "unavailable",
           "unavailable_here"]

UNSUPPORTED_CODE: Final = "platform.unsupported"

#: Architecture spellings of :func:`platform.machine` and :func:`sysconfig.get_platform`, normalised.
_ARCH: Final = {"amd64": "x86_64", "x86_64": "x86_64", "x64": "x86_64", "arm64": "arm64", "aarch64": "arm64",
                "win-amd64": "x86_64", "win-arm64": "arm64", "win32": "x86"}

#: The AgentDojo-family backends whose locks pin cryptography 50.0.2 and cachebox 5.2.3 (a test reads the locks).
AGENTDOJO_FAMILY: Final = ("agentdojo", "autodojo", "agentdyn")
_NO_ARM64_WHEELS: Final = ("its pinned dependencies cryptography 50.0.2 and cachebox 5.2.3 publish no Windows ARM64 "
                           "wheels, and backends install from wheels only")
_UPSTREAM: Final = "AgentDojo itself is tested upstream on Linux only"
_LIVE_GUIDE: Final = ("07-live-runs.md#platforms", "chapter 7, Live runs, section Platforms")


@dataclass(frozen=True, slots=True)
class Where:
    """One platform where a feature is unavailable: ``system`` as :func:`platform.system` names it, ``machines`` the
    normalised architectures (empty: every architecture), ``label`` as a message names it, and why."""

    system: str
    machines: tuple[str, ...]
    label: str
    reason: str


@dataclass(frozen=True, slots=True)
class Limit:
    """One feature and the platforms where it is unavailable. ``subjects`` narrows it (for example to backend ids);
    empty means the whole feature. ``yet`` says the limit is expected to be lifted (the message says "not yet")."""

    feature: str
    name: str
    plural: bool
    works_on: str
    where: tuple[Where, ...]
    guide: str
    guide_title: str
    yet: bool = True
    subjects: tuple[str, ...] = ()


LIMITS: Final[tuple[Limit, ...]] = (
    Limit(
        "live_runs", "Live runs (agentprov run)", True,
        "macOS and Linux",
        (Where("Windows", ("x86_64",), "Windows x86_64",
               "the backend environment builds, but the backend worker exits at start-up for a reason not yet "
               f"diagnosed ({_UPSTREAM})"),
         Where("Windows", ("arm64",), "Windows ARM64",
               f"the AgentDojo backend cannot be installed there, because {_NO_ARM64_WHEELS} ({_UPSTREAM})"),
         Where("Windows", (), "Windows",
               "no backend has run on Windows: on x86_64 the backend worker exits at start-up and on ARM64 the "
               f"AgentDojo backend cannot be installed ({_UPSTREAM})")),
        *_LIVE_GUIDE),
    Limit(
        "backend_build", "Building the agentdojo, autodojo and agentdyn backend environments", False,
        "macOS and Linux",
        (Where("Windows", ("arm64",), "Windows ARM64", _NO_ARM64_WHEELS),),
        *_LIVE_GUIDE, subjects=AGENTDOJO_FAMILY),
    Limit(
        "sandbox_exec", "Enforced containment (--containment sandbox-exec)", False, "macOS only",
        (Where("Linux", (), "Linux", "it runs the backend worker under macOS's sandbox-exec, which Linux does not have; "
               "declare dedicated-user or vm instead"),
         Where("Windows", (), "Windows", "it runs the backend worker under macOS's sandbox-exec, which Windows does "
               "not have")),
        "07-live-runs.md#containment", "chapter 7, Live runs, section Containment", yet=False),
    Limit(
        "job_queue", "The machine-wide job queue (--queue-cpu, tools/suite_queue.py)", False, "macOS and Linux",
        (Where("Windows", (), "Windows", "the queue holds its slots with POSIX file locks (fcntl), which Windows does "
               "not have; jobs run without it"),),
        "10-troubleshooting.md#heavy-jobs-on-a-shared-machine-the-job-queue",
        "chapter 10, Troubleshooting, section Heavy jobs on a shared machine: the job queue", yet=False),
)
_BY_FEATURE: Final = {limit.feature: limit for limit in LIMITS}


@dataclass(frozen=True, slots=True)
class Unavailable:
    """A feature that is unavailable on one platform, with the message every surface shows."""

    limit: Limit
    where: Where

    def message(self) -> str:
        lim = self.limit
        verb, pronoun = ("are", "they are") if lim.plural else ("is", "it is")
        return (f"{lim.name} {verb} available on {lim.works_on}. On {self.where.label} {pronoun} not available"
                f"{' yet' if lim.yet else ''}: {self.where.reason}. See the user guide, {lim.guide_title} "
                f"(docs/user-guide/{lim.guide}).")

    def to_json(self) -> dict[str, Any]:
        lim = self.limit
        return {"feature": lim.feature, "name": lim.name, "platform": self.where.label, "works_on": lim.works_on,
                "reason": self.where.reason, "subjects": list(lim.subjects), "guide": f"docs/user-guide/{lim.guide}",
                "message": self.message()}


def _arch(raw: str) -> str:
    text = raw.strip().lower()
    return _ARCH.get(text, text)


def host() -> tuple[str, str]:
    """This host's operating system (:func:`platform.system`) and normalised architecture. On Windows the architecture
    is the interpreter's (``sysconfig.get_platform()``): :func:`platform.machine` names the emulating host for an x64
    Python on Windows ARM64 (D-867), and an emulated x64 interpreter builds x64 environments."""
    system = platform.system()
    if system == "Windows":
        plat = sysconfig.get_platform().lower()
        return system, _ARCH.get(plat, _arch(platform.machine()))
    return system, _arch(platform.machine())


def unavailable(feature: str, system: str | None = None, machine: str | None = None, *,
                subject: str | None = None) -> Unavailable | None:
    """The limit that makes ``feature`` unavailable on ``system``/``machine`` (default: this host), or ``None``. With
    ``subject``, a limit narrowed to other subjects does not apply. An unknown feature is a programming error."""
    limit = _BY_FEATURE[feature]
    if subject is not None and limit.subjects and subject not in limit.subjects:
        return None
    if system is None or machine is None:
        here_system, here_machine = host()
        system = here_system if system is None else system
        machine = here_machine if machine is None else machine
    arch = _arch(machine)
    for where in limit.where:
        if where.system == system and (not where.machines or arch in where.machines):
            return Unavailable(limit, where)
    return None


def unavailable_here(system: str | None = None, machine: str | None = None) -> list[Unavailable]:
    """Every feature unavailable on ``system``/``machine`` (default: this host), in table order."""
    hits = (unavailable(limit.feature, system, machine) for limit in LIMITS)
    return [hit for hit in hits if hit is not None]


class PlatformUnsupported(AgentProvError):
    """A feature refused on this platform before any work starts (D-1064). Exit 4 (``refused``)."""

    code = UNSUPPORTED_CODE
    exit_code = 4

    def __init__(self, hit: Unavailable) -> None:
        super().__init__(hit.message())
        self.hit = hit


def refuse(feature: str, *, subject: str | None = None) -> None:
    """Raise :class:`PlatformUnsupported` when ``feature`` is unavailable on this host."""
    hit = unavailable(feature, subject=subject)
    if hit is not None:
        raise PlatformUnsupported(hit)
